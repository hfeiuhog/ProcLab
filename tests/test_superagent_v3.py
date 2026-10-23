"""End-to-end invariants for real industrial orchestration, scopes and analytics."""
from copy import deepcopy
import time
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.engine import TaskService
from app.api import create_app
from app.orchestration.contracts import QueryIntent
from app.orchestration.superagent import PlanValidator
from app.analytics.sql_guard import SQLGuard,compile_query
from app.analytics.semantic import parse_question


@pytest.fixture
def service(tmp_path):
    s=TaskService(tmp_path,"fallback",settings=Settings(_env_file=None,database_url="",redis_url="",milvus_uri="",use_llm=False))
    yield s
    s.close()


def test_industrial_team_calls_and_formal_result_are_traceable(service):
    s=service.create("分析 B-102 工艺参数")
    assert s["status"]=="completed" and s["business_verdict"]=="nonconforming"
    assert len(s["analysis"]["findings"])==6
    detail=service.platform.detail(s)
    assert len(detail["agent_calls"])>=8 and detail["tool_calls"] and detail["evidence"]
    assert detail["harness_runs"][0]["payload"]["verdict"]=="nonconforming"
    revision=detail["result_revisions"][0]["payload"]
    assert revision["plan_version"]==1 and revision["evidence_ids"] and revision["harness_id"]
    assert len(detail["plan_versions"])==1
    assert not detail["handoffs"]
    assert service.platform.health()["pending_outbox"]==0


def test_nl2sql_is_real_readonly_and_independently_recomputed(service):
    s=service.create("按设备统计全部模拟批次的超限批次比例",intent="analytics")
    assert s["status"]=="completed",s.get("review_reason")
    a=s["analytics"]
    assert a["rows"] and "ads_batch_quality" in a["sql"]
    assert a["guard"]["arbitrary_sql"] is False
    assert s["validation_details"]["analytics_independent_check"] is True
    assert a["manifest"]["row_count"]==487
    assert "process.assess" not in s["execution_plan"]["team"]
    tampered=deepcopy(a);tampered["rows"][0]["value"]=999
    assert not service.platform.warehouse.verify(tampered,s["scope"])


def test_composite_runs_both_branches_without_filtering_history_to_current_batch(service):
    s=service.create("分析 B-102 并对比近30天各设备的超限批次比例",intent="composite")
    assert s["status"]=="completed",s.get("review_reason")
    assert s["batch_id"]=="B-102" and s["analytics"]["intent"]["batch_id"]==""
    assert s["validation_details"]["independent_numeric_check"] is True
    assert s["validation_details"]["analytics_independent_check"] is True


@pytest.mark.parametrize("mutation",["union","write","tenant","function","export"])
def test_sql_guard_rejects_sql_or_binding_bypass(service,mutation):
    scope=service.platform.repo.scope("admin").model_dump()
    intent=parse_question("全部批次的超限比例")
    sql,params=compile_query(intent,scope,"test-version")
    if mutation=="tenant":params["tenant"]="other-tenant"
    else:sql+={"union":" UNION SELECT 1,2,3,4,5","write":"; DELETE FROM ads_batch_quality","function":"; SELECT load_extension('x')","export":" INTO OUTFILE '/tmp/x'"}[mutation]
    with pytest.raises(PermissionError):SQLGuard.validate(sql,params,intent,scope,"test-version")


def test_plan_validator_rejects_missing_gate_and_invalid_dependency(service):
    s=service.create("分析 B-101")
    p=deepcopy(s["execution_plan"]);p["nodes"]=[n for n in p["nodes"] if n["id"]!="harness"]
    with pytest.raises(ValueError):PlanValidator.validate(p)
    p=deepcopy(s["execution_plan"])
    next(n for n in p["nodes"] if n["id"]=="process")["depends_on"]=["data"]
    with pytest.raises(ValueError):PlanValidator.validate(p)


def test_project_membership_revocation_and_stage_gate(service):
    scope=service.platform.repo.scope("admin")
    user=service.control.add_user("member-v3","Member-password-2026")
    ident=user["id"]
    with pytest.raises(KeyError):service.platform.repo.scope(ident,scope.project_id)
    service.platform.repo.configure_project("admin",scope.project_id,member=ident,role="analyst")
    assert service.platform.repo.scope(ident,scope.project_id,write=True).tenant_id=="admin"
    service.platform.repo.configure_project("admin",scope.project_id,member=ident,role="revoked")
    with pytest.raises(KeyError):service.platform.repo.scope(ident,scope.project_id)
    service.platform.repo.configure_project("admin",scope.project_id,stage="archived")
    with pytest.raises(PermissionError):service.create("分析 B-101",project_id=scope.project_id)


def test_missing_evidence_approval_does_not_turn_into_conformance(service):
    s=service.create("分析 B-103")
    assert s["status"]=="pending_review" and s["business_verdict"]=="indeterminate"
    result=service.review(s["task_id"],True,"仅发布限制性说明")
    assert result["validation"]=="needs_review" and result["business_verdict"]=="indeterminate"
    assert result["result_revision"]["publication"]=="limited"


def test_outbox_retries_do_not_block_result_and_are_idempotent(service,monkeypatch):
    original=service.platform.warehouse.consume
    monkeypatch.setattr(service.platform.warehouse,"consume",lambda e:(_ for _ in ()).throw(ConnectionError()))
    s=service.create("分析 B-101")
    assert s["status"]=="completed" and service.platform.repo.pending_events()
    monkeypatch.setattr(service.platform.warehouse,"consume",original)
    event=service.platform.repo.pending_events()[0]["payload"]
    assert service.platform.drain_outbox()["pending"]==0
    assert service.platform.warehouse.consume(event) is False


def test_replan_is_versioned_and_does_not_refill_budget(service):
    s=service.create("分析 B-999")
    budget=s["tool_budget"]
    service.platform.prepare_replan(s,"admin","再次检查来源是否已补齐")
    assert s["tool_budget"]==budget
    result=service._execute(s["task_id"],True)
    assert result["plan_version"]==2
    assert len(service.platform.repo.list("plan_versions",s["task_id"]))==2


def test_api_has_scope_protected_execution_and_semantics(tmp_path):
    with TestClient(create_app(tmp_path,"fallback",Settings(_env_file=None))) as c:
        assert c.get("/api/agents").json()["agents"]
        assert c.get("/api/analytics/semantic-model").json()["query_mode"].startswith("typed")
        s=c.post("/api/tasks",json={"question":"全部批次的超限比例","intent":"analytics"}).json()
        assert s["status"]=="completed",s
        detail=c.get("/api/tasks/"+s["task_id"]+"/execution").json()
        assert detail["query_snapshots"] and detail["result_revisions"]
        assert c.post("/api/tasks",json={"question":"分析B-101","project_id":"unknown"}).status_code==404


def test_restart_recovers_after_tool_return_before_agent_commit(tmp_path,monkeypatch):
    config=Settings(_env_file=None)
    a=TaskService(tmp_path,"fallback",settings=config)
    old=a.platform.specialists.process
    def crash(s,g):
        old(s,g)
        raise SystemExit("simulated process death before durable agent output")
    monkeypatch.setattr(a.platform.specialists,"process",crash)
    s=a._reserve("分析 B-102")
    with pytest.raises(SystemExit):a._execute(s["task_id"])
    a.close()
    b=TaskService(tmp_path,"fallback",settings=config)
    try:
        b.recover()
        for _ in range(300):
            result=b.get(s["task_id"])
            if result["status"] not in ("queued","running"):break
            time.sleep(.03)
        assert result["status"]=="completed",result.get("review_reason")
        calls=b.platform.repo.list("agent_calls",s["task_id"])
        data=[x for x in calls if x["payload"]["step_id"]=="data"]
        assert len(data)==1 and len(data[0]["payload"]["attempts"])==1
        process=[x for x in calls if x["payload"]["step_id"]=="process"][0]
        assert len(process["payload"]["attempts"])==2
    finally:b.close()


def test_real_agent_contract_passes_query_origin_to_semantic_verifier(tmp_path,monkeypatch):
    seen=[]
    def model(settings,name,description,properties,required,payload):
        meta={"provider":"native_function","model":"mock","usage":{"total_tokens":12}}
        if name=="propose_industrial_team":return {"capabilities":payload["allowed_capabilities"],"goal":payload["question"],"gaps":[]},meta
        if name=="propose_metric_query":return {k:payload["resolved"][k] for k in ("metric","group_by")},meta
        sources=payload["sources"]
        query=next(x for x in sources if x.get("type")=="verified_query_snapshot_candidate")
        assert query["semantic_version"] and query["metric_definition"]["definition"] and query["dataset_version"]
        assert payload["claims"][0]["source"]==query["id"]
        seen.append(query["id"])
        return {"status":"supported","reason":"定义与查询快照来源齐备"},meta
    monkeypatch.setattr("app.orchestration.superagent.native_function",model)
    monkeypatch.setattr("app.orchestration.specialists.native_function",model)
    service=TaskService(tmp_path,"fallback",llm_enabled=True,settings=Settings(_env_file=None,use_llm=True,openai_api_key="test",openai_model="mock"))
    try:
        s=service.create("按设备统计全部模拟批次的超限批次比例",intent="analytics")
        assert seen and s["status"]=="completed" and s["plan_provider"]=="native_tools"
        assert s["semantic_analysis"]["status"]=="supported"
    finally:service.close()


def test_identical_queries_get_distinct_execution_snapshots(service):
    first=service.create("查询全部批次的超限比例",intent="analytics")
    second=service.create("查询全部批次的超限比例",intent="analytics")
    assert first["status"]==second["status"]=="completed"
    assert first["analytics"]["query_id"]!=second["analytics"]["query_id"]
    assert first["analytics"]["query_fingerprint"]==second["analytics"]["query_fingerprint"]


def test_frozen_plan_rejects_changed_simulation_inputs(service):
    from app.orchestration.runtime import ToolGateway,PolicyError
    from app.orchestration.contracts import Step
    s=service.create("分析 B-101")
    s["simulation_params"]={"oven_c":999}
    gateway=ToolGateway(service.platform,s,Step(id="data",capability="process.data"),"test",1)
    with pytest.raises(PolicyError,match="输入依据"):gateway.check()


def test_fresh_warehouse_rebuilds_from_durable_events(service,tmp_path):
    from app.analytics.warehouse import Warehouse
    s=service.create("分析 B-101")
    other=Warehouse(tmp_path/"rebuilt")
    assert other.health()["consumed_events"]==0
    for payload in service.platform.repo.historical_events():other.consume(payload)
    assert other.health()["consumed_events"]==1
    for payload in service.platform.repo.historical_events():assert other.consume(payload) is False
