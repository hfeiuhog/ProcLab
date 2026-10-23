import time
from copy import deepcopy
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.engine import TaskService
from app.engineering import simulate_heating, HeatingInput
from app.steps import validate_step
from app.tools import query_batch_data, search_process_docs, check_process_limits
from app.planner import select_tool, make_plan


def local(**kwargs):
    return Settings(_env_file=None, database_url="", redis_url="", milvus_uri="", use_llm=False, **kwargs)


def test_engineering_cross_validation_and_invalid_parameters():
    result = simulate_heating()
    assert result["verified"] and result["target_reached"]
    assert result["max_error_c"] < 1e-3
    assert 300 < result["minimum_time_s"] < 400
    assert abs(result["curve"][0]["temperature_c"] - 25) < 1e-8
    with pytest.raises(ValueError):
        HeatingInput(oven_c=190, target_c=200)
    with pytest.raises(ValueError):
        HeatingInput(tau_s=float("nan"))


def test_nan_is_not_a_process_reading():
    rows = query_batch_data("B-101")
    rows[0]["temperature_c"] = "nan"
    result = check_process_limits(rows, search_process_docs("热压成型工艺规范"))
    assert any(m["parameter"] == "temperature_c" for m in result["missing"])


def evidence_state():
    docs = search_process_docs("热压成型 工艺规范 温度 压力 黏度")
    rows = query_batch_data("B-102")
    return dict(batch_id="B-102", docs=docs, readings=rows, analysis=check_process_limits(rows, docs), trace=[])


def test_independent_gate_rejects_tampered_findings_citations_and_source():
    original = evidence_state()
    assert validate_step(original)["validation"] == "passed"
    for mutate in (
        lambda s: s["analysis"]["findings"].clear(),
        lambda s: s["analysis"]["findings"][0].update(citation="invented"),
        lambda s: s["readings"][0].update(pressure_mpa="0"),
        lambda s: s["docs"][0].update(content="changed source"),
    ):
        state = deepcopy(original)
        mutate(state)
        assert validate_step(state)["validation"] == "needs_review"


def test_gate_checks_missing_values_even_if_tool_says_complete():
    s = evidence_state()
    s["batch_id"], s["readings"] = "B-103", query_batch_data("B-103")
    s["analysis"] = {"findings": [], "missing": []}
    assert validate_step(s)["validation"] == "needs_review"


def test_graph_memory_is_opt_in_and_scoped_to_verified_results(tmp_path):
    service = TaskService(tmp_path, "langgraph", settings=local())
    try:
        first = service.create("分析 B-102 批次", remember_result=True)
        assert first["status"] == "completed"
        assert len(service.store.list_memories()) == 1
        follow = service.create("继续分析刚才的批次，核对温度", conversation_id=first["conversation_id"])
        assert follow["batch_id"] == "B-102"
        assert follow["context"] and follow["recalled_memories"]
        pending = service.create("分析 B-103 缺失数据", remember_result=True)
        with pytest.raises(ValueError):
            service.save_result_memory(pending["task_id"])
        service.review(pending["task_id"], True)
        assert len(service.store.list_memories()) == 1
        ident = service.store.list_memories()[0]["id"]
        assert service.store.forget(ident)
        assert service.memory.recall("温度") == []
    finally:
        service.close()


def test_graph_review_survives_restart_with_sql_checkpointer(tmp_path):
    a = TaskService(tmp_path, "langgraph", settings=local())
    pending = a.create("分析 B-103 批次数据", "B-103")
    assert pending["status"] == "pending_review"
    a.close()
    b = TaskService(tmp_path, "langgraph", settings=local())
    try:
        result = b.review(pending["task_id"], False, "补采测量")
        assert result["status"] == "rejected"
        assert b.store.conversation(pending["conversation_id"])["messages"][-1]["role"] == "assistant"
    finally:
        b.close()


def test_recover_execution_from_saved_superstep(tmp_path):
    a = TaskService(tmp_path, "langgraph", settings=local())
    state = a._reserve("分析 B-102 断点恢复", "B-102")
    state["status"] = "running"
    config = {"configurable": {"thread_id": state["task_id"]}, "recursion_limit": 50}
    stream = a.graph.stream(state, config, stream_mode="values")
    for _ in range(4):
        snapshot = next(stream)
        a.store.save({k: v for k, v in snapshot.items() if not k.startswith("__")})
    stream.close()
    a.close()
    b = TaskService(tmp_path, "langgraph", settings=local())
    try:
        b.recover()
        for _ in range(100):
            result = b.get(state["task_id"])
            if result["status"] == "completed":
                break
            time.sleep(.02)
        assert result["status"] == "completed"
        assert len([t for t in result["trace"] if t["node"] == "search_process_docs"]) == 1
    finally:
        b.close()


def test_background_api_stream_export_and_auth(tmp_path):
    settings = local(api_token="a" * 32)
    with TestClient(create_app(tmp_path, "langgraph", settings)) as c:
        assert c.get("/api/conversations").status_code == 401
        c.headers["Authorization"] = "Bearer " + "a" * 32
        r = c.post("/api/tasks/submit", json={"question": "用一阶模型仿真升温过程", "intent": "simulation"})
        assert r.status_code == 202
        state = r.json()
        events = c.get("/api/tasks/" + state["task_id"] + "/events")
        assert "event: state" in events.text and "event: done" in events.text
        state = c.get("/api/tasks/" + state["task_id"]).json()
        assert state["status"] == "completed" and state["report"]["simulation"]["verified"]
        report = c.get("/api/tasks/" + state["task_id"] + "/report")
        assert report.status_code == 200 and "简化工程模型" in report.text
        assert c.get("/api/tasks/" + state["task_id"] + "/report?format=json").json()["task_id"] == state["task_id"]
        assert c.get("/api/conversations/" + state["conversation_id"]).json()["messages"]
        m = c.post("/api/memories", json={"content": "分析温度时核对校准记录"}).json()
        assert c.delete("/api/memories/" + m["id"]).status_code == 204


def test_conflicting_batch_and_fault_guard(tmp_path):
    service = TaskService(tmp_path, "fallback", settings=local(allow_fault_injection=False))
    try:
        with pytest.raises(ValueError):
            service.create("分析 B-101", "B-102")
        with pytest.raises(ValueError):
            service.create("分析 B-102", "B-102", "always")
    finally:
        service.close()


def mock_native(monkeypatch, function, arguments):
    import openai
    def create(**kwargs):
        assert kwargs["tools"] and kwargs["tool_choice"] == "required"
        call = SimpleNamespace(id="call_test", function=SimpleNamespace(name=function, arguments=arguments))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[call]))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return fake
        def __exit__(self, *args): pass
    monkeypatch.setattr(openai, "OpenAI", Client)


def test_native_function_scope_rejects_unavailable_tool(monkeypatch):
    mock_native(monkeypatch, "check_process_limits", "{}")
    state = dict(question="分析 B-102", batch_id="B-102", plan_provider="native_tools",
                 plan=["search_process_docs", "query_batch_data", "check_process_limits", "validate_evidence"])
    name, provider, _ = select_tool(state, local(openai_api_key="test", openai_model="test"))
    assert (name, provider) == ("search_process_docs", "rules_fallback")


def test_native_planner_cannot_skip_evidence_gate(monkeypatch):
    mock_native(monkeypatch, "propose_analysis_plan", '{"steps":["search_process_docs"]}')
    plan, provider = make_plan("分析 B-102 批次", "B-102", True, settings=local(openai_api_key="test", openai_model="test"))
    assert plan[-1] == "validate_evidence" and provider == "rules_fallback"


def test_production_configuration_requires_all_services():
    with pytest.raises(ValueError):
        local(app_env="production").check()
