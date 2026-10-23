"""Business steps and independent evidence verification, shared by both runtimes."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from .planner import make_plan
from .rag import load_docs
from .tools import search_process_docs, query_batch_data, check_process_limits, PARAMETERS, reading_source
from .engineering import simulate_heating, process_statistics


def event(name, detail, **extra):
    return {"node": name, "detail": detail, "time": datetime.now(timezone.utc).isoformat(), **extra}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def plan_step(s, llm_enabled=False, settings=None):
    plan, provider = make_plan(s["question"], s.get("batch_id", ""), llm_enabled, s.get("intent", "auto"), settings)
    return {"plan": plan, "step_index": 0, "completed_steps": [], "plan_provider": provider,
            "trace": s.get("trace", []) + [event("planner", "已拆解为 " + str(len(plan)) + " 个可验证步骤", steps=plan,
                memory_hits=len(s.get("recalled_memories", [])), context_messages=len(s.get("context", [])))]}


def search_step(s, knowledge=None, evidence=None):
    q = s["question"] + (" 热压成型 工艺规范 温度 压力 黏度" if s.get("batch_id") else "")
    if knowledge:
        docs, retrieval = knowledge.search(q)
    else:
        docs, retrieval = search_process_docs(q), {"backend": "lexical", "status": "local"}
    if evidence:
        from .rag import retrieve
        extra=evidence.documents(s)
        library=[d for d in extra if d.get('origin')=='admin_published' or d.get('scope')=='personal']
        attached=[d for d in extra if d not in library]
        hits=retrieve(q,limit=4,catalog=library)
        docs=attached+hits+docs
        retrieval['reviewed_uploads']=len(attached)
        retrieval['personal_hits']=sum(d.get('scope')=='personal' for d in hits)
        retrieval['shared_releases']=sum(not k.startswith('private:') for k in s.get('knowledge_versions',{}))
        retrieval['shared_retrieval']='BM25+character-bigram; owner-scoped frozen text'
    if s.get("batch_id") or s.get("intent")=="optimization":
        spec = next(d for d in load_docs() if d["doc_id"] == "SOP-003" and d["status"] == "active")
        docs = [spec] + [d for d in docs if d["doc_id"] != "SOP-003"][:3]
        retrieval["required_active_sop"] = "SOP-003"
    trace = s.get("trace", []) + [event("search_process_docs", f"检索到 {len(docs)} 条有效资料",
        tool_args={"query": q}, retrieval=retrieval, doc_refs=[d["doc_id"] + " " + d["revision"] for d in docs])]
    if not docs:
        docs = search_process_docs("热压成型 工艺规范 温度 压力 黏度") if s.get("batch_id") else []
        trace.append(event("retrieval_retry", f"补充检索返回 {len(docs)} 条"))
    return {"docs": docs, "retrieval": retrieval, "trace": trace, "step_index": s.get("step_index", 0) + 1,
            **({"review_reason": "工艺规范无可用证据"} if not docs else {})}


def query_step(s, evidence=None):
    trace = list(s.get("trace", []))
    mode = s.get("inject_timeout", "none")
    for attempt in range(1, 3):
        try:
            if mode == "always" or (mode == "once" and attempt == 1):
                raise TimeoutError("模拟工具超时")
            rows = evidence.rows(s) if evidence else query_batch_data(s.get("batch_id", ""))
            trace.append(event("query_batch_data", f"第 {attempt} 次调用成功，返回 {len(rows)} 行",
                               attempt=attempt, tool_args={"batch_id": s.get("batch_id")}, rows=[r["row_id"] for r in rows]))
            return {"readings": rows, "trace": trace, "step_index": s.get("step_index", 0) + 1,
                    **({"review_reason": "批次不存在或未查到数据"} if not rows else {})}
        except TimeoutError:
            trace.append(event("query_batch_data", f"第 {attempt} 次调用模拟超时", attempt=attempt, error="TimeoutError"))
    return {"readings": [], "trace": trace, "review_reason": "批次查询工具连续两次模拟超时，未获得批次数据"}


def analyze_step(s):
    result = check_process_limits(s.get("readings", []), s.get("docs", []))
    return {"analysis": result, "step_index": s.get("step_index", 0) + 1,
            "trace": s.get("trace", []) + [event("check_process_limits", f"检出 {len(result['findings'])} 个超限项、{len(result['missing'])} 个缺失项")]}


def statistics_step(s):
    result = process_statistics(s.get("readings", []), s.get("docs", []))
    return {"statistics": result, "step_index": s.get("step_index", 0) + 1,
            "trace": s.get("trace", []) + [event("process_statistics", f"完成 {len(result['parameters'])} 个参数的描述统计")]}


def simulation_step(s):
    try:
        result = simulate_heating(s.get("simulation_params"))
        return {"simulation": result, "step_index": s.get("step_index", 0) + 1,
                "trace": s.get("trace", []) + [event("simulate_heating", f"RK4/解析解最大误差 {result['max_error_c']:.8f} ℃", tool_args=result["parameters"])]}
    except (ValueError, ArithmeticError):
        return {"review_reason": "升温模型参数或数值计算无效",
                "trace": s.get("trace", []) + [event("simulate_heating", "模型输入或计算失败")]}


def validate_step(s, evidence=None):
    reason = s.get("review_reason")
    docs = s.get("docs", [])
    catalog = {(d["doc_id"], d["revision"], d["section"]): d for d in load_docs() if d["status"] == "active"}
    if evidence:
        catalog.update({(d['doc_id'], d['revision'], d['section']): d for d in evidence.documents(s)})
    valid_refs = bool(docs) and all(
        (d["doc_id"], d["revision"], d["section"]) in catalog and
        d.get("content") == catalog[(d["doc_id"], d["revision"], d["section"])]["content"] and
        d.get("limits") == catalog[(d["doc_id"], d["revision"], d["section"])].get("limits")
        for d in docs)
    if not valid_refs:
        reason = reason or "规范版本、内容或引用未通过核实"
    details = {"source_versions_verified": valid_refs, "independent_numeric_check": None}
    if s.get("batch_id"):
        rows, analysis = s.get("readings", []), s.get("analysis", {})
        if not rows or rows != (evidence.rows(s) if evidence else query_batch_data(s["batch_id"])):
            reason = reason or "原始批次记录缺失或已变化"
        if analysis.get("error") or analysis.get("missing"):
            reason = reason or analysis.get("error") or f"存在 {len(analysis['missing'])} 个缺失/错误参数，无法完整校验"
        specs = [d for d in docs if d["doc_id"] == "SOP-003" and d["status"] == "active" and d.get("limits")]
        if len(specs) != 1:
            reason = reason or "没有唯一现行工艺参数标准"
        else:
            expected = []
            invalid_values = []
            spec = specs[0]
            for row in rows:
                for param in PARAMETERS:
                    try:
                        value = Decimal(str(row.get(param)))
                        lim = spec["limits"][param]
                        if not value.is_finite():
                            invalid_values.append((row.get("row_id"), param))
                            continue
                        if not Decimal(str(lim["min"])) <= value <= Decimal(str(lim["max"])):
                            expected.append({"row_id": row["row_id"], "parameter": param, "actual": float(value),
                                "allowed": [lim["min"], lim["max"]], "unit": lim["unit"],
                                "citation": f"{reading_source(row)}；{spec['doc_id']} {spec['revision']} §{spec['section']}"})
                    except (InvalidOperation, KeyError, ValueError, TypeError):
                        invalid_values.append((row.get("row_id"), param))
                        continue
            if invalid_values:
                reason = reason or f"独立复算发现 {len(invalid_values)} 个缺失/无效原始参数"
            verified = expected == analysis.get("findings", [])
            details["independent_numeric_check"] = verified
            details["readings_sha256"] = digest(rows)
            if not verified:
                reason = reason or "独立 Decimal 复算与工具结论或引用不一致"
    if s.get("evidence_bundle_id"):
        details["supplement_id"] = s["evidence_bundle_id"]
        details["evidence_origin"] = "human_supplied_reviewed; arithmetic_verified_not_sensor_authenticated"
    if s.get("simulation"):
        result = s["simulation"]
        details["simulation_verified"] = result["verified"]
        if not result["verified"]:
            reason = reason or "升温模型独立复算误差超限"
    if s.get("design_loop"):
        from .design import verify_design
        details["design_verified"]=verify_design(s["design_loop"])
        if not details["design_verified"]:reason=reason or "升温方案的独立数值与约束核验未通过"
    reason = reason or None
    return {"review_reason": reason, "validation": "needs_review" if reason else "passed", "validation_details": details,
            "step_index": s.get("step_index", 0) + 1,
            "trace": s.get("trace", []) + [event("validate_evidence", reason or "通过：现行资料、原始记录和独立计算一致", checks=details)]}


def report_step(s, settings=None):
    findings = s.get("analysis", {}).get("findings", [])
    missing = s.get("analysis", {}).get("missing", [])
    if s.get("batch_id"):
        if findings:
            summary = f"{s['batch_id']} 批次检测到 {len(findings)} 个参数超限项；只证明存在偏差，不足以推断质量异常的根本原因。"
        elif s.get("readings") and not missing and not s.get("review_reason"):
            summary = f"{s['batch_id']} 批次所检查的参数均在模拟现行规范区间内；不代表已完成全面质量认证。"
        else:
            summary = f"{s['batch_id']} 批次的测量数据或工艺证据不完整，无法形成完整参数合规结论。"
    elif s.get("design_loop"):
        from .design import design_summary
        summary=design_summary(s["design_loop"])
    elif s.get("simulation"):
        result = s["simulation"]
        summary = f"简化升温模型计算完成，末端温度 {result['final_c']:.2f} ℃。解析解与 RK4 复算{'一致' if result['verified'] else '不一致'}。"
    else:
        excerpts = " ".join(d["content"] for d in s.get("docs", [])[:2])
        summary = excerpts or "没有可用工艺资料。"
    answer_meta = None
    if s.get("candidate_answer"):
        summary, answer_meta = s["candidate_answer"], s.get("candidate_answer_metadata", {})
    elif not s.get("batch_id") and not s.get("simulation") and not s.get("design_loop") and not s.get("review_reason"):
        from .config import Settings
        from .models import ModelRouter
        settings = settings or Settings(_env_file=None)
        try:
            summary, answer_meta = ModelRouter(settings).answer(s)
        except Exception as exc:
            answer_meta = {"status": "fallback", "error": type(exc).__name__,
                           "purpose": s.get("intent"), "model": ModelRouter(settings).model_for(s.get("intent")),
                           "failure": __import__("app.harness",fromlist=["classify_failure"]).classify_failure(exc)}
            if s.get("intent") == "chat":
                summary = "当前模型暂不可用。ProcLab可以分析模拟批次、检索工艺资料、执行简化升温仿真，并保留证据与人工复核记录。请稍后重试普通问答。"
            elif s.get("intent") == "extract":
                summary = "字段抽取未完成或证据校验失败；请保留原文并人工复核，不能使用未经验证的字段。"
            else:
                summary = "模型回答暂不可用，以下仅展示检索原文：\n" + "\n".join(
                    f"[{d['doc_id']}] {d['content']}" for d in s.get("docs", []))
    if s.get("review_reason"):
        summary += f" 风险提示：{s['review_reason']}。"
    review = s.get("review")
    if review is not None:
        summary += (" 本报告仅作为人工批准发布的限制性说明；审批不改变证据不足的事实。" if review["approved"]
                    else " 人工驳回发布，报告不得作为正式分析结论。")
    status = "rejected" if review is not None and not review["approved"] else "completed_reviewed" if review else "completed"
    refs = [f"{d['doc_id']} {d['revision']} §{d['section']}" for d in s.get("docs", [])]
    sources = list(dict.fromkeys(refs + [reading_source(r) for r in s.get("readings", [])]))
    direct = s.get("intent") in ("chat", "extract")
    validation = "not_applicable" if direct else s.get("validation", "")
    trace = s.get("trace", [])
    if answer_meta:
        trace = trace + [event("answer_question", "已生成回答" if answer_meta["status"] == "success" else "模型调用或输出校验失败，已明确降级", **answer_meta)]
    return {"status": status, "validation": validation, "answer_metadata": answer_meta or {}, "report": {
        "title": "项目助手回答" if direct else "工业工艺分析报告", "summary": summary, "findings": findings, "missing": missing, "sources": sources,
        "documents": s.get("docs", []), "readings": s.get("readings", []), "statistics": s.get("statistics"),
        "simulation": s.get("simulation"), "design":s.get("design_loop"), "validation": s.get("validation_details", {}),
        "recommendations": (["复核传感器与校准记录，补充设备日志及重复测量。", "超限批次交由工艺负责人复核，避免直接据此认定根因。"] if findings or missing else ["核对模型假设与资料适用范围后再进行下一步分析。"]),
        "warning": "工艺规范及批次为自制模拟数据；公开资料单独标注。简化工程模型未经设备标定，仅供技术演示。" + (" 本版本包含人工补充测量；数值复算不证明传感器真实性，原始缺失记录保留。" if s.get("evidence_bundle_id") else ""),
        "lineage": {"parent_task_id": s.get("parent_task_id"), "repair_version": s.get("repair_version", 0), "supplement_id": s.get("evidence_bundle_id")},
        "review_reason": s.get("review_reason"), "human_review": review, "answer_metadata": answer_meta,
    }, "trace": trace + [event("finalize", f"报告状态：{status}")]}
