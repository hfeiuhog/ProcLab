"""Industrial specialists with private inputs, constrained tools and typed outputs."""
import copy
from ..steps import search_step,analyze_step,statistics_step,simulation_step,validate_step,event
from ..tools import reading_source
from ..rag import load_docs
from ..models import ModelRouter,task_settings
from .contracts import AgentResult,Outcome,QueryIntent,digest
from .superagent import native_function
from ..analytics.semantic import parse_question,SEMANTIC_VERSION


def wrapped(patch,evidence=None):
    gap=patch.get("review_reason")
    return AgentResult(patch=patch,evidence=evidence or [],outcome=Outcome.NEEDS_EVIDENCE if gap else Outcome.SUCCESS,
        gaps=[gap] if gap else [])


class Specialists:
    def __init__(self,platform):self.p=platform

    def requirements(self,s,g):
        req=self.p.superagent.requirements(s,g)
        return AgentResult(patch={"requirement_set":req})

    def retrieval(self,s,g):return wrapped(g.invoke("search_process_docs",lambda:search_step(copy.deepcopy(s),self.p.service.knowledge,self.p.service.evidence)))

    def data(self,s,g):
        def read():
            mode=s.get("inject_timeout","none")
            if mode=="always" or (mode=="once" and g.attempt==1):raise TimeoutError("模拟工具超时")
            return self.p.service.evidence.rows(s)
        rows=g.invoke("query_batch_data",read)
        patch={"readings":rows,"step_index":s.get("step_index",0)+1,"trace":s["trace"]+[event("query_batch_data",f"第 {g.attempt} 次调用成功，返回 {len(rows)} 行",attempt=g.attempt,rows=[r["row_id"] for r in rows])]}
        if not rows:patch["review_reason"]="批次不存在或未查到数据"
        return wrapped(patch)

    def process(self,s,g):
        if not s.get("readings"):return wrapped({"review_reason":s.get("review_reason") or "没有可分析的批次数据"})
        return wrapped(g.invoke("check_process_limits",lambda:analyze_step(copy.deepcopy(s))))

    def statistics(self,s,g):
        if not s.get("readings"):return wrapped({"review_reason":s.get("review_reason") or "没有可统计的批次数据"})
        return wrapped(g.invoke("process_statistics",lambda:statistics_step(copy.deepcopy(s))))

    def simulation(self,s,g):
        if s.get("intent")=="optimization":
            from ..design import run_design
            return wrapped(run_design(self.p,s,g))
        return wrapped(g.invoke("simulate_heating",lambda:simulation_step(copy.deepcopy(s))))

    def analytics(self,s,g):
        q=s["question"]
        # A composite query compares historical batches; the selected current batch is not an implicit historical filter.
        if s["intent"]=="composite":
            import re
            q=re.sub(r"\bB-\d{3,8}\b","",q,flags=re.I)
        try:intent=parse_question(q)
        except ValueError as exc:
            return AgentResult(outcome=Outcome.NEEDS_EVIDENCE,patch={"review_reason":str(exc)},gaps=[str(exc)])
        capture_id=digest([s["task_id"],s.get("plan_version"),intent.model_dump(),s["scope"]])
        prior=self.p.repo.get("query_snapshots",capture_id)
        if prior:
            if not self.p.warehouse.verify(prior,s["scope"]):raise ValueError("已保存查询快照核验失败")
            return AgentResult(patch={"analytics":prior,"trace":s["trace"]+[event("analytics_query","恢复已冻结查询快照",query_id=capture_id)]})
        provider="semantic_rules";metadata={}
        if self.p.model_enabled(s):
            try:
                result,metadata=g.invoke("model.query",lambda:native_function(task_settings(self.p.settings,s),"propose_metric_query","确认已批准的指标和分组。日期和权限由服务端绑定。",
                    {"metric":{"type":"string","enum":[intent.metric]},"group_by":{"type":"string","enum":[intent.group_by]}},["metric","group_by"],
                    {"question":q,"resolved":intent.model_dump(),"semantic_version":SEMANTIC_VERSION}))
                if result!={"metric":intent.metric,"group_by":intent.group_by}:raise ValueError("指标选择与受控语义解析不一致")
                provider="native_function"
            except Exception as exc:provider="semantic_rules_fallback";metadata={"error":type(exc).__name__}
        result=g.invoke("analytics.query",lambda:self.p.warehouse.execute(intent,s["scope"]))
        result.update(query_fingerprint=result["query_id"],raw_query_sha256=digest(result))
        result["query_id"]=capture_id
        result.update(planner=provider,model_metadata=metadata)
        self.p.repo.put("query_snapshots",result["query_id"],result,s,"captured",True)
        return AgentResult(patch={"analytics":result,"trace":s["trace"]+[event("analytics_query","已执行只读指标查询，返回 "+str(len(result["rows"]))+" 行",query_id=result["query_id"],metric=intent.metric)]})

    def evidence(self,s,g):
        if s.get("design_loop"):
            # These are code-generated, model-scoped numeric claims. Their proof is
            # the source/receipt verifier and independent Harness below, not an
            # LLM's free-text inference about unrelated factory acceptance criteria.
            design=s["design_loop"]
            claims=[{"id":"heating-design","claim_type":"numerical_model_only",
                     "claim":design.get("summary",""),"source":"model:scipy-heating-design-1",
                     "selected_trial":design.get("selected_trial"),
                     "real_device_conformance":False,"global_optimum_claimed":False}] if design.get("trials") else []
            return wrapped({"semantic_analysis":{"method":"typed_scientific_claim_alignment",
                "status":"candidate","claims":claims,
                "limitations":"仅给定数值模型；须通过来源、工具调用、参数边界和独立解析复算；不证明真实设备行为"},
                "trace":s["trace"]+[event("evidence_analysis","已将数值模型主张交给来源核验和独立复算，未扩展为真实产线验收",
                    method="typed_scientific_claim_alignment")]})
        findings=s.get("analysis",{}).get("findings",[])
        claims=[{"id":"finding-"+str(i+1),"claim":f"{f['row_id']}行{f['parameter']}={f['actual']} {f['unit']}，范围{f['allowed']}","source":f["citation"]} for i,f in enumerate(findings)]
        if s.get("analytics"):claims.append({"id":"analytics","claim":s["analytics"]["metric"]["definition"],"source":s["analytics"]["query_id"]})
        if s.get("simulation"):claims.append({"id":"simulation","claim":"在记录的模型假设下计算升温轨迹","source":"model:heating-v1"})
        if s.get("design_loop",{}).get("trials"):
            claims.append({"id":"heating-design","claim":s["design_loop"].get("summary","升温方案计算"),"source":"model:scipy-heating-design-1"})
        patch={"semantic_analysis":{"method":"structured_alignment","status":"candidate","claims":claims,"limitations":"语义候选不能替代来源核验和独立复算"}}
        if not self.p.model_enabled(s) and not s.get("batch_id") and not s.get("analytics") and not s.get("simulation") and not s.get("design_loop"):
            patch["candidate_answer"]="模型未启用，以下展示检索原文：\n"+"\n".join(f"[{d['doc_id']}] {d['content']}" for d in s.get("docs",[]))
            patch["candidate_answer_metadata"]={"status":"fallback","purpose":s["intent"],"model":self.p.settings.openai_model,"error":"ModelNotConfigured"}
        if self.p.model_enabled(s) and not s.get("batch_id") and not s.get("analytics") and not s.get("simulation") and not s.get("design_loop") and not s.get("review_reason"):
            try:
                answer,meta=g.invoke("model.evidence",lambda:ModelRouter(self.p.settings).answer(s))
                patch.update(candidate_answer=answer,candidate_answer_metadata=meta)
                claims=[{"id":"answer","claim":answer[:4000],"source":meta.get("citations",[])}]
            except Exception as exc:
                patch["semantic_analysis"]={"method":"source_excerpts","status":"model_unavailable","error":type(exc).__name__,"claims":[]}
                if not self.p.model_enabled(s):
                    patch["candidate_answer"]="模型未启用，以下展示检索原文：\n"+"\n".join(f"[{d['doc_id']}] {d['content']}" for d in s.get("docs",[]))
                    patch["candidate_answer_metadata"]={"status":"fallback","purpose":s["intent"],"model":self.p.settings.openai_model,"error":"ModelNotConfigured"}
        if self.p.model_enabled(s) and claims:
            semantic_sources=[{"id":d["doc_id"],"revision":d["revision"],"content":d["content"][:1600]} for d in s.get("docs",[])]
            if s.get("analytics"):
                a=s["analytics"]
                semantic_sources.append({"id":a["query_id"],"type":"verified_query_snapshot_candidate",
                    "semantic_version":a["semantic_version"],"metric_definition":a["metric"],"sql":a["sql"],
                    "dataset_version":a["manifest"]["dataset_version"],"sop_version":a["manifest"]["sop_version"],
                    "origin":"synthetic","rows":a["rows"][:20],"time_range":a["time_range"]})
            if s.get("simulation"):
                sim=s["simulation"]
                semantic_sources.append({"id":"model:heating-v1","type":"engineering_model_output","formula":sim.get("formula"),
                    "assumptions":sim.get("assumptions"),"parameters":sim.get("parameters"),"verified":sim.get("verified")})
            if s.get("design_loop",{}).get("trials"):
                design=s["design_loop"]
                semantic_sources.append({"id":"model:scipy-heating-design-1","type":"scientific_experiment_outputs",
                    "origin":"synthetic_model_not_real_device","constraints":design["constraints"],
                    "assumptions":design["assumptions"],"selected_trial":design["selected_trial"],
                    "trials":[{"id":t["id"],"input":t["result"]["input"],"final_c":t["result"]["final_c"],
                               "reached_at_s":t["result"]["reached_at_s"],"solver":t["result"]["solver"],"inverse_design":t["result"]["inverse_design"]} for t in design["trials"]]})
            try:
                output,meta=g.invoke("model.evidence",lambda:native_function(task_settings(self.p.settings,s),"assess_source_support","检查主张是否受到给定来源支持；缺少依据应标为insufficient，不修改数值或引用。",
                    {"status":{"type":"string","enum":["supported","insufficient","conflict"]},"reason":{"type":"string"}},["status","reason"],
                    {"claims":claims[:12],"sources":semantic_sources,
                     "claim_scope":"仅给定的一阶热模型与输入假设下的数值设计，不主张真实设备达标或完整SOP验收" if s.get("design_loop") else "按主张的对象与适用范围核验",
                     "measurement_rows":s.get("readings",[])[:20],"analytics_rows":s.get("analytics",{}).get("rows",[])[:10],"model_assumptions":s.get("simulation",{}).get("assumptions")}))
                if output.get("status") not in ("supported","insufficient","conflict"):raise ValueError("InvalidSemanticAssessment")
                patch["semantic_analysis"]={"method":"model_semantic_assessment","status":output["status"],"reason":str(output.get("reason",""))[:1000],"claims":claims,"model_metadata":meta}
                if output["status"]=="conflict":
                    patch["evidence_conflict"]=True
                    return AgentResult(outcome=Outcome.HANDOFF,patch=patch,handoff={"capability":"evidence.conflict","reason":output.get("reason")})
                if output["status"]=="insufficient":patch["review_reason"]="语义证据支持不足："+str(output.get("reason",""))[:300]
            except Exception as exc:
                patch["semantic_analysis"].update(status="assessment_unavailable",error=type(exc).__name__)
                # Structured numeric claims remain subject to independent proof; free text cannot silently pass as entailed.
                if patch.get("candidate_answer"):patch["review_reason"]="语义核验未完成，请复核资料回答"
        patch["trace"]=s["trace"]+[event("evidence_analysis","已整理主张、来源关系与证据缺口",method=patch["semantic_analysis"]["method"])]
        return wrapped(patch)

    def conflict(self,s,g):
        return AgentResult(outcome=Outcome.NEEDS_EVIDENCE,patch={"review_reason":"证据存在冲突，需核对对象、版本、时间与单位后人工复核",
            "conflict_analysis":{"status":"unresolved","basis":"保留各来源；不以Agent投票替代规则和原始证据"}},gaps=["unresolved_evidence_conflict"],
            handoff={"capability":"review.prepare","reason":"unresolved_evidence_conflict"})

    def verify(self,s,g):
        def check():
            refs=[];errors=[]
            catalog={(d["doc_id"],d["revision"],d["section"]):d for d in load_docs() if d["status"]=="active"}
            catalog.update({(d["doc_id"],d["revision"],d["section"]):d for d in self.p.service.evidence.documents(s)})
            for d in s.get("docs",[]):
                key=(d["doc_id"],d["revision"],d["section"]);valid=key in catalog and digest(d)==digest(catalog[key])
                # Retrieval may attach transient ranking fields; compare authoritative content/limits and identity.
                if not valid and key in catalog:valid=all(d.get(k)==catalog[key].get(k) for k in ("content","limits","origin"))
                refs.append({"type":"document","reference":list(key),"sha256":digest({k:d.get(k) for k in ("doc_id","revision","section","content","limits")}),"valid":valid})
                if not valid:errors.append("文档版本或原文不一致")
            if s.get("batch_id"):
                rows=self.p.service.evidence.rows(s);valid=bool(rows) and rows==s.get("readings")
                refs.append({"type":"measurement","batch_id":s["batch_id"],"sha256":digest(s.get("readings",[])),"row_ids":[r["row_id"] for r in s.get("readings",[])],"valid":valid,"supplement_id":s.get("evidence_bundle_id")})
                if not valid:errors.append("原始数据缺失或已变化")
            if s.get("analytics"):
                a=s["analytics"];valid=self.p.warehouse.verify(a,s["scope"])
                refs.append({"type":"query","query_id":a["query_id"],"sha256":a["result_sha256"],"watermark":a["manifest"]["watermark"],"valid":valid})
                if not valid:errors.append("查询快照或指标独立复算失败")
            if s.get("simulation"):
                refs.append({"type":"simulation","model_version":"heating-v1","sha256":digest(s["simulation"]),"valid":s["simulation"].get("verified") is True})
            if s.get("design_loop"):
                from ..design import verify_design
                loop=s["design_loop"];valid=verify_design(loop,self.p.repo.list("tool_calls",s["task_id"]))
                refs.append({"type":"scientific_experiment","model_version":"scipy-heating-design-1",
                    "sha256":digest({"schema":"scientific-results-v1","results":[t["result_sha256"] for t in loop["trials"]],
                        "selected_trial":loop.get("selected_trial")}),
                    "encoding":"ordered-scientific-result-digests-v1","valid":valid,
                    "tool_call_ids":[t["tool_call_id"] for t in loop["trials"]]})
                if not valid:errors.append("科学计算结果、约束或工具调用来源未通过独立核验")
            if not refs:errors.append("没有可核验的证据")
            return {"refs":refs,"errors":errors,"passed":not errors}
        result=g.invoke("verify_sources",check);ids=[]
        for ref in result["refs"]:
            ident=digest([s["task_id"],ref]);ref={**ref,"id":ident,"scope":s["scope"]}
            self.p.repo.put("evidence",ident,ref,s,"verified" if ref["valid"] else "invalid",True);ids.append(ident)
        patch={"evidence_ids":ids,"evidence_verification":result,"trace":s["trace"]+[event("evidence_verifier","证据来源核验通过" if result["passed"] else "证据来源核验发现缺口")]}
        if result["errors"]:patch["review_reason"]=s.get("review_reason") or "；".join(result["errors"])
        return wrapped(patch)

    def harness(self,s,g):
        def run():
            if s["intent"]=="analytics":
                patch={"validation":"passed","validation_details":{"source_versions_verified":s.get("evidence_verification",{}).get("passed",False)},"trace":list(s["trace"])}
            else:patch=validate_step(copy.deepcopy(s),self.p.service.evidence)
            if s.get("analytics"):
                valid=self.p.warehouse.verify(s["analytics"],s["scope"]);patch["validation_details"]["analytics_independent_check"]=valid
                if not valid:patch.update(validation="needs_review",review_reason="指标复算未通过")
            reason=patch.get("review_reason") or s.get("review_reason")
            if reason or not s.get("evidence_verification",{}).get("passed"):
                patch.update(validation="needs_review",review_reason=reason or "必要证据核验未完成")
            verdict="indeterminate" if patch["validation"]!="passed" else "nonconforming" if s.get("analysis",{}).get("findings") else "conforming" if s.get("batch_id") else "not_applicable"
            patch["business_verdict"]=verdict
            return patch
        patch=g.invoke("validate_evidence",run)
        ident=digest([s["task_id"],s["plan_version"],patch["validation_details"],patch["business_verdict"]])
        self.p.repo.put("harness_runs",ident,{"id":ident,"verdict":patch["business_verdict"],"validation":patch["validation"],"checks":patch["validation_details"],"evidence_ids":s.get("evidence_ids",[]),"rule_basis":s["execution_plan"]["basis"]},s,patch["validation"],True)
        patch["harness_id"]=ident
        return wrapped(patch)

    def handlers(self):
        return {"requirement.extract":self.requirements,"evidence.retrieve":self.retrieval,"process.data":self.data,
            "process.assess":self.process,"process.statistics":self.statistics,"process.simulate":self.simulation,
            "analytics.query":self.analytics,"evidence.analyze":self.evidence,"evidence.conflict":self.conflict,
            "evidence.verify":self.verify,"harness.evaluate":self.harness}
