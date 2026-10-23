"""Behavioral proofs for model-directed scientific experiments and their failure boundaries."""
from copy import deepcopy
import time
import pytest
from app.config import Settings
from app.engine import TaskService
from app.design import (DEMO_QUESTION,request_from_text,scientific_solve,verify_trial,verify_design,canonical_question)
from app.orchestration.contracts import Step
from app.orchestration.runtime import ToolGateway,PolicyError

PARAMS,_=request_from_text(DEMO_QUESTION)

@pytest.fixture
def service(tmp_path):
    service=TaskService(tmp_path,"fallback",settings=Settings(_env_file=None))
    yield service
    service.close()

def install_model(monkeypatch,choose=None):
    observed=[]
    def call(settings,name,description,properties,required,payload):
        meta={"provider":"native_function","model":"test-model","model_call_id":name+"-"+str(len(observed)),
              "usage":{"total_tokens":20}}
        if name=="propose_industrial_team":
            return {"capabilities":payload["allowed_capabilities"],"goal":payload["question"],"gaps":[]},meta
        if name=="choose_heating_action":
            observations=payload["observations"];observed.append(deepcopy(observations))
            if choose:return choose(payload),meta
            if not observations:oven=200
            elif not observations[-1]["meets_deadline"]:oven=217
            else:return {"action":"finish","oven_c":None,"selected_trial":2,"reason":"实际计算的217℃方案满足时限，结束并保留对比。"},meta
            return {"action":"simulate","oven_c":oven,"selected_trial":None,"reason":"根据已有计算反馈验证下一候选炉温。"},meta
        if name=="assess_source_support":
            assert any(x.get("type")=="scientific_experiment_outputs" for x in payload["sources"]) or not payload["claims"]
            return {"status":"supported","reason":"主张仅适用于给定模型与已执行试算。"},meta
        raise AssertionError(name)
    monkeypatch.setattr("app.orchestration.superagent.native_function",call)
    monkeypatch.setattr("app.orchestration.specialists.native_function",call)
    return observed

def model_service(tmp_path):
    return TaskService(tmp_path,"fallback",llm_enabled=True,settings=Settings(
        _env_file=None,use_llm=True,openai_api_key="test",openai_model="test-model"))

def test_text_inputs_bind_physics_and_do_not_guess_missing_values():
    assert PARAMS["tau_s"]==180 and PARAMS["deadline_s"]==300
    converted,gaps=request_from_text(DEMO_QUESTION.replace("时间常数180秒","时间常数3分钟"))
    assert not gaps and converted==PARAMS
    assert request_from_text("设计升温方案")[0] is None
    assert request_from_text(DEMO_QUESTION+"，初温30℃")[0] is None
    assert request_from_text(DEMO_QUESTION,dict(PARAMS,deadline_s=299))[0] is None
    assert request_from_text(DEMO_QUESTION.replace("在达温时限内尽量降低炉温","缩短升温时间"))[0]["objective"]=="fastest_within_bounds"

def test_real_scipy_process_is_checked_against_independent_solution():
    result=scientific_solve(PARAMS,217)
    assert result["solver"]["name"]=="scipy.integrate.solve_ivp"
    assert result["solver"]["pid"]>0 and result["reached_at_s"]<300
    inverse=result["inverse_design"]
    assert inverse["tool"]=="scipy.optimize.brentq" and 216<inverse["minimum_oven_c"]<217
    altered=deepcopy(result);altered["inverse_design"]["minimum_oven_c"]=200
    assert not verify_trial(altered,PARAMS)
    assert verify_trial(result,PARAMS)
    for key,value in [("final_c",999),("reached_at_s",1)]:
        altered=deepcopy(result);altered[key]=value
        assert not verify_trial(altered,PARAMS)
    with pytest.raises(ValueError):scientific_solve(PARAMS,221)

def test_model_reads_failure_and_selects_new_parameter_then_stops(tmp_path,monkeypatch):
    observed=install_model(monkeypatch);service=model_service(tmp_path)
    try:
        s=service.create(DEMO_QUESTION)
        assert s["status"]=="completed",s.get("review_reason")
        d=s["design_loop"]
        assert [t["result"]["input"]["oven_c"] for t in d["trials"]]==[200,217]
        assert observed[0]==[] and observed[1][0]["meets_deadline"] is False
        assert observed[2][1]["meets_deadline"] is True
        assert d["selected_trial"]==2 and d["stop_reason"]=="agent_finished"
        assert all(x["provider"]=="native_function" for x in d["decisions"])
        assert s["validation_details"]["design_verified"] is True
        assert verify_design(d,service.platform.repo.list("tool_calls",s["task_id"]))
        assert s["business_verdict"]=="not_applicable"
        assert "未证明全局最优" in s["report"]["summary"]
    finally:service.close()

def test_offline_fallback_is_explicit_and_executes_real_solver(service):
    s=service.create(DEMO_QUESTION)
    assert s["status"]=="completed",s.get("review_reason")
    assert all(d["provider"]=="rules" for d in s["design_loop"]["decisions"])
    assert len(s["design_loop"]["trials"])==2

@pytest.mark.parametrize("action",[
    {"action":"simulate","oven_c":221,"selected_trial":None,"reason":"超出允许炉温"},
    {"action":"finish","oven_c":None,"selected_trial":None,"reason":"尚未计算就结束"},
])
def test_model_cannot_bypass_bounds_or_invent_completion(tmp_path,monkeypatch,action):
    install_model(monkeypatch,lambda payload:action);service=model_service(tmp_path)
    try:
        s=service.create(DEMO_QUESTION)
        assert s["status"]=="pending_review" and not s["design_loop"]["trials"]
        assert s["design_loop"]["stop_reason"]=="invalid_model_action"
        calls=service.platform.repo.list("tool_calls",s["task_id"])
        assert not any(x["payload"]["tool"]=="engineering.solve" for x in calls)
    finally:service.close()

def test_missing_conditions_never_trigger_solver_and_can_be_repaired(service):
    s=service.create("请设计升温方案")
    assert s["intent"]=="optimization" and s["status"]=="pending_review"
    assert s["design_loop"]["stop_reason"]=="missing_inputs" and not s["design_loop"]["trials"]
    assert "初温" in s["review_reason"] and "TypeError" not in s["review_reason"]
    child=service.retry(s["task_id"],design_params=PARAMS)
    for _ in range(250):
        latest=service.get(child["task_id"])
        if latest["status"] not in ("queued","running"):break
        time.sleep(.04)
    assert latest["status"]=="completed",latest.get("review_reason")
    assert latest["parent_task_id"]==s["task_id"]
    assert service.get(s["task_id"])["status"]=="pending_review"

def test_receipt_and_observation_tampering_cannot_pass_evidence_gate(service):
    s=service.create(DEMO_QUESTION);d=s["design_loop"]
    calls=service.platform.repo.list("tool_calls",s["task_id"])
    assert verify_design(d,calls)
    altered=deepcopy(d);altered["trials"][0]["result"]["final_c"]=999
    assert not verify_design(altered,calls)
    altered=deepcopy(d);altered["trials"][1]["tool_call_id"]="invented"
    assert not verify_design(altered,calls)
    altered=deepcopy(d);altered["decisions"][1]["observed_trials"]=[]
    assert not verify_design(altered,calls)

def test_solver_timeout_becomes_a_visible_gap(service,monkeypatch):
    def timeout(*args):raise TimeoutError()
    monkeypatch.setattr("app.design.scientific_solve",timeout)
    s=service.create(DEMO_QUESTION)
    assert s["status"]=="pending_review" and not s["design_loop"]["trials"]
    assert s["design_loop"]["stop_reason"]=="solver_failed"

def test_frozen_physical_constraints_cannot_be_modified(service):
    s=service.create(DEMO_QUESTION)
    s["design_params"]["deadline_s"]=1000
    with pytest.raises(PolicyError,match="输入依据"):
        ToolGateway(service.platform,s,Step(id="simulation",capability="process.simulate"),"test",1).check()

def test_resume_reuses_committed_trial_and_decision(tmp_path,monkeypatch):
    a=TaskService(tmp_path,"fallback",settings=Settings(_env_file=None))
    original=a.platform.repo.checkpoint;crashed=False
    def checkpoint(s):
        nonlocal crashed
        original(s)
        d=s.get("design_loop",{})
        if not crashed and len(d.get("trials",[]))==1 and not d.get("pending_action"):
            crashed=True;raise SystemExit("after first committed experiment")
    monkeypatch.setattr(a.platform.repo,"checkpoint",checkpoint)
    s=a._reserve(DEMO_QUESTION)
    with pytest.raises(SystemExit):a._execute(s["task_id"])
    a.close()
    b=TaskService(tmp_path,"fallback",settings=Settings(_env_file=None))
    try:
        result=b._execute(s["task_id"],True)
        assert result["status"]=="completed",result.get("review_reason")
        assert [t["result"]["input"]["oven_c"] for t in result["design_loop"]["trials"]]==[200,220]
        calls=b.platform.repo.list("tool_calls",s["task_id"])
        solves=[x for x in calls if x["payload"]["tool"]=="engineering.solve" and x["status"]=="succeeded"]
        assert len(solves)==2
    finally:b.close()

def test_api_publishes_tool_capabilities_and_rejects_invalid_constraints(client):
    tools=client.get("/api/engineering/tools").json()
    assert tools["available"] and tools["arbitrary_code"] is False
    s=client.post("/api/tasks",json={"question":DEMO_QUESTION}).json()
    assert s["status"]=="completed"
    report=client.get("/api/tasks/"+s["task_id"]+"/report").text
    assert "试算与决策" in report and "scipy" in client.get("/api/tasks/"+s["task_id"]+"/execution").text.lower()
    invalid=dict(PARAMS,oven_max_c=999)
    assert client.post("/api/tasks",json={"question":DEMO_QUESTION,"design_params":invalid}).status_code==422

def test_optimization_cannot_silently_use_legacy_or_exhaust_gate_budget(tmp_path):
    s=TaskService(tmp_path,"fallback",settings=Settings(_env_file=None,harness_max_tool_calls=4))
    try:
        with pytest.raises(ValueError,match="运行时"):s.create(DEMO_QUESTION,orchestration_mode="legacy")
        result=s.create(DEMO_QUESTION)
        assert result["status"]=="pending_review"
        assert result["design_loop"]["stop_reason"]=="tool_budget_reserved"
    finally:s.close()


def test_fastest_goal_selects_faster_candidate_instead_of_lower_oven(tmp_path,monkeypatch):
    def choose(payload):
        ovens=[200,220,217];i=len(payload["observations"])
        return {"action":"simulate","oven_c":ovens[i],"selected_trial":None,"reason":"根据实际观察比较达温时间。"}
    install_model(monkeypatch,choose);service=model_service(tmp_path)
    try:
        q=DEMO_QUESTION.replace("在达温时限内尽量降低炉温","缩短升温时间")
        result=service.create(q)
        assert result["status"]=="completed",result.get("review_reason")
        assert result["design_loop"]["selected_trial"]==2
        assert result["design_loop"]["constraints"]["objective"]=="fastest_within_bounds"
        assert "最短达温时间" in result["report"]["summary"]
    finally:service.close()

def test_provider_outage_is_marked_as_fallback_not_native_success(tmp_path,monkeypatch):
    original=[]
    def broken(settings,name,description,properties,required,payload):
        if name=="propose_industrial_team":
            return {"capabilities":payload["allowed_capabilities"],"goal":payload["question"],"gaps":[]},{"provider":"native_function"}
        if name=="choose_heating_action":raise TimeoutError()
        return {"status":"supported","reason":"已试方案的数值证据齐备。"},{"provider":"native_function"}
    monkeypatch.setattr("app.orchestration.superagent.native_function",broken)
    monkeypatch.setattr("app.orchestration.specialists.native_function",broken)
    service=model_service(tmp_path)
    try:
        result=service.create(DEMO_QUESTION)
        assert result["status"]=="completed",result.get("review_reason")
        decisions=result["design_loop"]["decisions"]
        assert decisions and all(d["provider"]=="rules_fallback" for d in decisions)
        assert all(d["model_metadata"]["error"]=="TimeoutError" for d in decisions)
    finally:service.close()


@pytest.mark.parametrize("deadline,status",[(100,"not_reachable_in_bounds"),(2000,"lower_bound_feasible")])
def test_inverse_solver_handles_infeasible_and_already_feasible_bounds(deadline,status):
    params=dict(PARAMS,deadline_s=deadline)
    result=scientific_solve(params,200)
    assert result["inverse_design"]["status"]==status
    assert verify_trial(result,params)


def test_irrelevant_selection_on_simulate_does_not_publish_uncomputed_result(tmp_path,monkeypatch):
    def choose(payload):
        i=len(payload["observations"])
        if i==2:return {"action":"finish","oven_c":None,"selected_trial":2,"reason":"依据实际试算结束。"}
        return {"action":"simulate","oven_c":200 if i==0 else 217,"selected_trial":1,"reason":"请求实际计算，选择字段与当前动作无关。"}
    install_model(monkeypatch,choose);service=model_service(tmp_path)
    try:
        result=service.create(DEMO_QUESTION)
        assert result["status"]=="completed",result.get("review_reason")
        loop=result["design_loop"]
        assert len(loop["trials"])==2 and loop["selected_trial"]==2
        assert loop["decisions"][0]["selected_trial"] is None
        assert loop["decisions"][0]["model_metadata"]["raw_selected_trial"]==1
    finally:service.close()


def test_numeric_model_claims_use_independent_proof_not_unrelated_factory_semantics(tmp_path,monkeypatch):
    called=[]
    def model(settings,name,description,properties,required,payload):
        called.append(name)
        meta={"provider":"native_function","model":"test-model","model_call_id":name,"usage":{"total_tokens":10}}
        if name=="propose_industrial_team":
            return {"capabilities":payload["allowed_capabilities"],"goal":payload["question"],"gaps":[]},meta
        if name=="choose_heating_action":
            n=len(payload["observations"])
            if n==2:return {"action":"finish","oven_c":None,"selected_trial":2,"reason":"已取得可行试算，结束。"},meta
            return {"action":"simulate","oven_c":200 if n==0 else 217,"selected_trial":None,"reason":"依据实际计算反馈选择下一候选。"},meta
        return {"status":"insufficient","reason":"缺少与本次模型计算无关的真实工厂测量。"},meta
    monkeypatch.setattr("app.orchestration.superagent.native_function",model)
    monkeypatch.setattr("app.orchestration.specialists.native_function",model)
    service=model_service(tmp_path)
    try:
        result=service.create(DEMO_QUESTION)
        assert result["status"]=="completed",result.get("review_reason")
        assert "assess_source_support" not in called
        assert result["semantic_analysis"]["method"]=="typed_scientific_claim_alignment"
        assert result["semantic_analysis"]["claims"][0]["real_device_conformance"] is False
        assert result["validation_details"]["design_verified"] is True
        assert result["evidence_verification"]["passed"] is True
        assert result["business_verdict"]=="not_applicable"
    finally:service.close()


def test_lossless_scientific_snapshot_survives_mysql_numeric_json_roundtrip(service):
    import json
    from app.design import authoritative_design
    result=service.create(DEMO_QUESTION)
    original=result["design_loop"];calls=service.platform.repo.list("tool_calls",result["task_id"])
    def mysql_numbers(value):
        if isinstance(value,float):return float(format(value,".15g"))
        if isinstance(value,dict):return {k:mysql_numbers(v) for k,v in value.items()}
        if isinstance(value,list):return [mysql_numbers(v) for v in value]
        return value
    stored=mysql_numbers(deepcopy(original))
    assert stored["trials"][0]["result"]!=original["trials"][0]["result"]
    assert stored["trials"][0]["result_json"]==original["trials"][0]["result_json"]
    assert verify_design(stored,calls)
    assert authoritative_design(stored)["trials"][0]["result"]==original["trials"][0]["result"]
    corrupt=deepcopy(stored)
    raw=json.loads(corrupt["trials"][0]["result_json"]);raw["final_c"]+=.01
    corrupt["trials"][0]["result_json"]=json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    assert not verify_design(corrupt,calls)
    corrupt=deepcopy(stored);corrupt["trials"][0]["result"]["final_c"]+=.01
    assert not verify_design(corrupt,calls)
