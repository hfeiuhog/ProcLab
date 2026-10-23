"""Dependency-driven Supervisor. Published topology gates every execution."""
from pathlib import Path
from ..steps import event,report_step
from ..store import now
from .contracts import Step,Outcome,digest
from .repository import Repository
from .runtime import AgentRuntime
from .registry import catalog
from .specialists import Specialists
from .superagent import SuperAgent,PlanValidator
from ..analytics.warehouse import Warehouse
from ..analytics.semantic import semantic_model

TOOLS={"evidence.retrieve":("search_process_docs","docs"),"process.data":("query_batch_data","readings"),
    "process.assess":("check_process_limits","analysis"),"process.statistics":("process_statistics","statistics"),
    "process.simulate":("simulate_heating","simulation"),"analytics.query":("analytics_query","analytics"),
    "harness.evaluate":("validate_evidence","validation_details")}


class Platform:
    def __init__(self,service):
        self.service,self.settings=service,service.settings
        self.repo=Repository(service.store,service.control)
        self.warehouse=Warehouse(service.runtime_dir)
        self.superagent=SuperAgent(self.settings)
        self.specialists=Specialists(self)
        self.runtime=AgentRuntime(self)
        if self.warehouse.health()["consumed_events"]==0:self.replay_history()
        self.drain_outbox()

    def replay_history(self):
        scanned=0;inserted=0
        for payload in self.repo.historical_events():
            scanned+=1;inserted+=int(self.warehouse.consume(payload))
        return {"scanned":scanned,"inserted":inserted}

    def model_enabled(self,state):
        return bool(state.get("llm_enabled") and self.settings.use_llm and self.settings.openai_api_key and self.settings.openai_model)

    def drain_outbox(self):
        failures=0
        for event in self.repo.pending_events():
            try:self.warehouse.consume(event["payload"]);self.repo.acknowledge(event["id"])
            except Exception:failures+=1
        return {"pending":len(self.repo.pending_events()),"failures":failures}

    def execute(self,s):
        handlers=self.specialists.handlers()
        if not s.get("execution_plan"):
            s["status"]="running";s.setdefault("step_states",{})
            reqstep=Step(id="requirements",capability="requirement.extract",max_attempts=1)
            result=self.runtime.invoke(s,reqstep,handlers[reqstep.capability])
            s.update(result.patch)
            if not s.get("requirement_set"):
                s.update(status="pending_review",validation="needs_review");self.repo.checkpoint(s);return s
            plan=self.superagent.freeze(s,s["requirement_set"])
            self.repo.put("plan_versions",plan["id"],plan,s,"frozen",True)
            s.update(execution_plan=plan,plan_version=plan["version"],project_profile=plan["profile"],plan_provider=s["requirement_set"]["provider"])
            s["step_states"]={n["id"]:("succeeded" if n["id"]=="requirements" else "pending") for n in plan["nodes"]}
            s["plan"]=[TOOLS[n["capability"]][0] for n in plan["nodes"] if n["capability"] in TOOLS]
            s["trace"].append(event("planner","SuperAgent已冻结执行计划与专业团队",steps=s["plan"],plan_version=s["plan_version"],provider=s["plan_provider"]))
            self.repo.checkpoint(s)
        plan=s["execution_plan"];nodes=PlanValidator.validate(plan)
        complete={"succeeded","completed_with_gaps","skipped"}
        while True:
            waiting=[n for n in nodes if s["step_states"].get(n.id) not in complete]
            if not waiting:break
            ready=[n for n in waiting if all(s["step_states"].get(d) in complete for d in n.depends_on)]
            if not ready:raise ValueError("执行计划没有可运行节点")
            # The first implementation intentionally runs one ready node at a time on each task.
            # Independent tasks use the existing bounded thread pool; dependency semantics do not imply parallel capacity.
            node=ready[0]
            if node.condition=="conflict" and not s.get("evidence_conflict"):
                s["step_states"][node.id]="skipped";self.repo.checkpoint(s);continue
            if len(self.repo.list("agent_calls",s["task_id"]))>=plan["budget"]["max_agent_calls"]:
                s["review_reason"]="Agent调用预算耗尽";break
            if s.get("tool_budget",0)<=0:
                s["review_reason"]=s.get("review_reason") or "工具调用预算耗尽";break
            s["step_states"][node.id]="running"
            s["trace"].append(event("supervisor","按依赖调度："+node.id,capability=node.capability,depends_on=list(node.depends_on),plan_version=s["plan_version"]))
            self.repo.checkpoint(s)
            result=self.runtime.invoke(s,node,handlers[node.capability])
            s.update(result.patch)
            s["step_states"][node.id]="succeeded" if result.outcome==Outcome.SUCCESS else "completed_with_gaps"
            if node.capability in TOOLS:
                tool,key=TOOLS[node.capability]
                if key in result.patch and tool not in s.get("completed_steps",[]):s.setdefault("completed_steps",[]).append(tool)
            if result.gaps:s["review_reason"]=s.get("review_reason") or "；".join(result.gaps)
            self.repo.checkpoint(s)
        if s.get("review_reason") or s.get("validation")!="passed" or not s.get("harness_id"):
            s.update(status="pending_review",validation="needs_review",business_verdict="indeterminate")
            s["review_reason"]=s.get("review_reason") or "必要校验尚未完成"
            s["review_packet"]={"reason":s["review_reason"],"evidence_ids":s.get("evidence_ids",[]),"plan_version":s["plan_version"],
                "actions":["补充测量或资料并审核后创建修复版本","预算内重规划","发布保留缺口的限制性说明","驳回"],"approval_does_not_change_verdict":True}
            self.repo.checkpoint(s);return s
        self.make_report(s)
        self.repo.checkpoint(s);self.repo.publish(s);s["warehouse_sync"]=self.drain_outbox()
        self.repo.checkpoint(s)
        return s

    def make_report(self,s):
        if s["intent"]=="analytics" and not s.get("batch_id"):
            a=s.get("analytics",{});r=a.get("rows",[])
            summary=("指标查询未完成："+s.get("review_reason", "证据不足")) if not a else a.get("metric",{}).get("name","指标查询")+"："+"；".join(str(x["dimension"])+" "+("无可用分母" if x["value"] is None else str(x["value"])+a["metric"]["unit"]) for x in r)
            s.update(status="completed",report={"title":"工业数据分析报告","summary":summary,"findings":[],"missing":[],"readings":[],"documents":[],
                "sources":["查询快照 "+a.get("query_id","")],"recommendations":["核对时间范围、指标口径与数据水位。"],"warning":a.get("warning",""),
                "validation":s.get("validation_details",{}),"review_reason":s.get("review_reason"),"human_review":s.get("review")})
            if s.get("review"):
                s["status"]="completed_reviewed" if s["review"]["approved"] else "rejected"
                s["report"]["summary"]+=(" 本报告仅为保留证据缺口的限制性说明。" if s["review"]["approved"] else " 人工驳回，报告不得作为正式分析结论。")
        else:s.update(report_step(s,self.settings))
        if s.get("analytics"):
            s["report"]["analytics"]=s["analytics"]
            if s["intent"]=="composite":s["report"]["summary"]+=" 历史指标查询已完成，口径与数据水位见指标结果。"
        s["report"]["business_verdict"]=s.get("business_verdict","indeterminate")
        s["report"]["execution"]={"plan_version":s.get("plan_version"),"plan_sha256":s.get("execution_plan",{}).get("sha256"),"harness_id":s.get("harness_id"),"evidence_ids":s.get("evidence_ids",[])}

    def review(self,s,approved,note,actor):
        self.repo.scope(actor,s["scope"]["project_id"],review=True)
        s["review"]={"approved":approved,"note":note[:500],"actor":actor}
        s["business_verdict"]="indeterminate"
        s["trace"].append(event("human_review","人工批准限制性说明" if approved else "人工驳回"))
        self.make_report(s);self.repo.checkpoint(s);self.repo.publish(s)
        s["warehouse_sync"]=self.drain_outbox();self.repo.checkpoint(s)
        return s

    def prepare_replan(self,s,actor,note):
        self.repo.scope(actor,s["scope"]["project_id"],write=True)
        if s["status"] not in ("pending_review","failed"):raise ValueError("仅挂起或失败的执行可重规划")
        if s.get("plan_version",0)>=self.settings.harness_max_repairs+1:raise ValueError("已达到计划版本上限")
        if s.get("tool_budget",0)<=0:raise ValueError("剩余工具预算不足；补证后请创建有界修复任务")
        self.service.control.consume("replan:"+s["task_id"],self.settings.harness_max_repairs)
        s["_planning_version"]=s.get("plan_version",0)+1
        for key in ("execution_plan","report","harness_id","result_revision","requirement_set","candidate_answer","candidate_answer_metadata","analytics","semantic_analysis","evidence_conflict","readings","docs","analysis","statistics","simulation","design_loop","evidence_verification","evidence_ids","validation_details","run_started_at"):
            s.pop(key,None)
        s.update(status="queued",review_reason=None,review=None,validation="",completed_steps=[],step_states={})
        s["trace"].append(event("replan","已申请新计划版本；保留剩余调用预算",actor=actor,note=note[:500],next_version=s["_planning_version"]))
        self.repo.checkpoint(s)
        return s

    def detail(self,s):
        return {"execution_id":s["task_id"],"scope":s.get("scope"),"profile":s.get("project_profile"),"requirements":s.get("requirement_set"),
            "plan":s.get("execution_plan"),"step_states":s.get("step_states",{}),
            **{kind:self.repo.list(kind,s["task_id"]) for kind in ("plan_versions","agent_calls","tool_calls","handoffs","evidence","harness_runs","result_revisions","query_snapshots")}}

    def health(self):
        result=self.warehouse.health();result["pending_outbox"]=len(self.repo.pending_events());return result
