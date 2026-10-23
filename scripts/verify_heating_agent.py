"""Real-model acceptance with isolated local state; no secrets in exported evidence."""
import argparse
import json
from pathlib import Path
from app.config import Settings
from app.engine import TaskService
from app.design import DEMO_QUESTION,verify_design
from app.reports import markdown_report

def isolated_settings():
    original=Settings()
    return original.model_copy(update={"app_env":"development","database_url":"","redis_url":"","milvus_uri":"",
        "auth_enabled":False,"api_token":"","embedding_provider":"hash","registration_enabled":False,
        "harness_timeout_seconds":240})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True);parser.add_argument("--offline",action="store_true")
    args=parser.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    config=isolated_settings()
    enabled=not args.offline
    if enabled and not (config.openai_api_key and config.openai_model):
        raise SystemExit("Real model not configured; use --offline explicitly for a rules-only run.")
    config=config.model_copy(update={"use_llm":enabled})
    runtime=out/"运行数据"
    service=TaskService(runtime,"fallback",llm_enabled=enabled,settings=config)
    try:
        state=service.create(DEMO_QUESTION)
        detail=service.platform.detail(state);loop=state.get("design_loop",{})
        calls=detail["tool_calls"];native=[d for d in loop.get("decisions",[]) if d["provider"]=="native_function"]
        proof={"real_model_requested":enabled,"native_decisions":len(native),
            "rules_fallback_decisions":sum(d["provider"]!="native_function" for d in loop.get("decisions",[])),
            "status":state["status"],"validation":state.get("validation"),
            "independent_design_check":verify_design(loop,calls) if loop.get("trials") else False,
            "solver_versions":sorted({t["result"]["solver"]["version"] for t in loop.get("trials",[])}),
            "constraints":loop.get("constraints"),"stop_reason":loop.get("stop_reason"),
            "trials":[{"id":t["id"],"oven_c":t["result"]["input"]["oven_c"],"final_c":t["result"]["final_c"],
                       "reached_at_s":t["result"]["reached_at_s"],"tool_call_id":t["tool_call_id"]} for t in loop.get("trials",[])],
            "decisions":loop.get("decisions",[]),"conversation_id":state["conversation_id"],"task_id":state["task_id"],
            "review_reason":state.get("review_reason"),"model_used_observations":any(d["observed_trials"] for d in native)}
        (out/"模型与工具验收.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding="utf-8")
        (out/"完整任务.json").write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
        (out/"完整调用与证据.json").write_text(json.dumps(detail,ensure_ascii=False,indent=2),encoding="utf-8")
        report=markdown_report(state) if state.get("report") else "# 升温方案尚未发布\n\n"+str(state.get("review_reason") or "计算或证据校验未完成")+"\n"
        (out/"升温方案分析报告.md").write_text(report,encoding="utf-8")
        print(json.dumps(proof,ensure_ascii=False))
        if state["status"]!="completed" or not proof["independent_design_check"]:
            raise SystemExit("Execution or evidence validation did not pass; see saved proof.")
        if enabled and (len(native)<2 or not proof["model_used_observations"]):
            raise SystemExit("Real feedback-driven model decisions were not demonstrated; see saved proof.")
    finally:service.close()
if __name__=="__main__":main()
