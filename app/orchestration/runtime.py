"""Durable AgentCall runtime and the sole tool access boundary."""
import copy
import time
from datetime import datetime, timezone
from ..steps import event
from ..harness import boundary_reason
from ..store import now
from .contracts import AgentResult, Outcome, digest
from .registry import definition
from .superagent import basis


class PolicyError(ValueError):pass


class ToolGateway:
    def __init__(self,platform,state,step,call_id,attempt):
        self.platform,self.state,self.step,self.call_id,self.attempt=platform,state,step,call_id,attempt
        self.sequence=0

    def check(self):
        p,s=self.platform,self.state
        current=p.repo.scope(s["owner_id"],s["scope"]["project_id"],write=True).model_dump()
        if current!=s["scope"]:raise PermissionError("项目范围或阶段已变化，需要重新规划")
        plan=s.get("execution_plan")
        if plan:
            check={k:v for k,v in plan.items() if k!="sha256"}
            if digest(check)!=plan["sha256"] or p.repo.get("plan_versions",plan["id"])!=plan:raise PolicyError("执行计划冻结校验失败")
            if basis(s,p.settings)!=plan["basis"]:raise PolicyError("输入依据或模型配置已变化，请创建新计划版本")
        reason=boundary_reason(s,p.settings,check_budget=False)
        if reason:raise PolicyError(reason)

    def invoke(self,tool,fn,*,input_details=None):
        self.check()
        if tool not in definition(self.step.capability)["tools"]:raise PermissionError("Agent未获授权调用此工具")
        s,p=self.state,self.platform
        if s.get("tool_budget",0)<=0:raise PolicyError("工具调用预算耗尽")
        s["tool_budget"]-=1;self.sequence+=1
        ident=digest([self.call_id,self.attempt,self.sequence,tool])
        payload={"id":ident,"agent_call_id":self.call_id,"step_id":self.step.id,"tool":tool,"attempt":self.attempt,
            "scope":s["scope"],"started_at":now(),"input_refs":{"batch_id":s.get("batch_id"),"simulation_params":s.get("simulation_params"),"document_versions":s.get("evidence_document_versions"),"plan_sha256":s.get("execution_plan",{}).get("sha256"),"readings_sha256":digest(s.get("readings",[])),"analysis_sha256":digest(s.get("analysis",{}))},
            "input_sha256":digest([s.get("batch_id"),s.get("scope"),s.get("plan_version"),s.get("simulation_params"),s.get("readings"),s.get("analysis"),tool])}
        payload["bound_action"]=input_details
        self.last_call_id=ident
        p.repo.put("tool_calls",ident,payload,s,"running");p.repo.checkpoint(s)
        started=time.monotonic()
        try:
            value=fn()
            self.check()
            payload.update(status="succeeded",output_sha256=digest(value),latency_ms=round((time.monotonic()-started)*1000))
            if isinstance(value,tuple) and len(value)==2 and isinstance(value[1],dict):payload["model_metadata"]=value[1]
            p.repo.put("tool_calls",ident,payload,s,"succeeded")
            return value
        except Exception as exc:
            payload.update(status="failed",error=type(exc).__name__,latency_ms=round((time.monotonic()-started)*1000))
            p.repo.put("tool_calls",ident,payload,s,"failed");raise


class AgentRuntime:
    def __init__(self,platform):self.platform=platform

    def invoke(self,state,step,handler):
        p=self.platform
        ident=digest([state["task_id"],state.get("_planning_version",state.get("plan_version",1)),step.id])
        old=p.repo.get("agent_calls",ident)
        if old and old.get("status")=="succeeded":
            return AgentResult.model_validate(old["result"])
        call=old or {"id":ident,"step_id":step.id,"capability":step.capability,"agent":definition(step.capability),
            "scope":state["scope"],"input_sha256":digest([state["scope"],state.get("execution_plan",{}).get("sha256"),
                state.get("batch_id"),state.get("evidence_bundle_id"),step.depends_on]),"attempts":[],"started_at":now()}
        if old and old.get("status")=="running":
            for previous in call["attempts"]:
                if previous.get("status")=="running":previous.update(status="interrupted",observed_at=now())
        while len(call["attempts"])<step.max_attempts:
            attempt=len(call["attempts"])+1;detail={"attempt":attempt,"status":"running","started_at":now()};call["attempts"].append(detail)
            call["status"]="running";p.repo.put("agent_calls",ident,call,state,"running")
            gateway=ToolGateway(p,state,step,ident,attempt)
            try:
                gateway.check();result=AgentResult.model_validate(handler(state,gateway))
                prohibited={"owner_id","scope","task_id","execution_plan","plan_version","tool_budget"}&set(result.patch)
                if prohibited:raise PolicyError("Agent输出试图改变可信执行范围")
                detail.update(status="succeeded",finished_at=now(),outcome=result.outcome.value)
                call.update(status="succeeded",result=result.model_dump(mode="json"),finished_at=now())
                p.repo.put("agent_calls",ident,call,state,"succeeded")
                if result.handoff:
                    target=result.handoff.get("capability")
                    if target not in ("evidence.conflict","review.prepare"):raise PolicyError("Handoff不在允许拓扑中")
                    handoff={"source_call_id":ident,"target_capability":target,"reason":result.handoff.get("reason"),
                        "state":"requested","input_sha256":call["input_sha256"],"plan_version":state.get("plan_version")}
                    p.repo.put("handoffs",digest([ident,target]),handoff,state,"requested",True)
                return result
            except (PermissionError,KeyError):
                detail.update(status="denied",finished_at=now());call["status"]="denied"
                p.repo.put("agent_calls",ident,call,state,"denied");raise
            except Exception as exc:
                retryable=isinstance(exc,(TimeoutError,ConnectionError))
                detail.update(status="retryable_failed" if retryable else "failed",error=type(exc).__name__,finished_at=now())
                if step.capability=="process.data":
                    state["trace"].append(event("query_batch_data",f"第 {attempt} 次调用模拟超时" if state.get("inject_timeout")!="none" else f"第 {attempt} 次数据调用失败",attempt=attempt,error=type(exc).__name__))
                if retryable and attempt<step.max_attempts:
                    p.repo.put("agent_calls",ident,call,state,"retryable_failed");p.repo.checkpoint(state);continue
                reason="批次查询工具连续两次模拟超时，未获得批次数据" if step.capability=="process.data" and state.get("inject_timeout")=="always" else str(exc) if isinstance(exc,PolicyError) else "专业节点执行未完成："+type(exc).__name__
                result=AgentResult(outcome=Outcome.NEEDS_EVIDENCE,patch={"review_reason":reason},gaps=[reason],handoff={"capability":"review.prepare","reason":reason})
                call.update(status="failed",result=result.model_dump(mode="json"));p.repo.put("agent_calls",ident,call,state,"failed")
                p.repo.put("handoffs",digest([ident,"review.prepare"]),{"source_call_id":ident,"target_capability":"review.prepare","reason":reason,"state":"requested"},state,"requested",True)
                return result
        reason="中断后的调用已达到尝试上限，需人工复核"
        return AgentResult(outcome=Outcome.NEEDS_EVIDENCE,patch={"review_reason":reason},gaps=[reason])
