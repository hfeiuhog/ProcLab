"""Platform administration, project write gates and private history isolation."""
import copy
import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.control import password_hash

ADMIN="Review-admin-2026"
PASSWORD="Member12!"
@pytest.fixture
def client(tmp_path):
    settings=Settings(_env_file=None,runtime_dir=str(tmp_path),database_url="",redis_url="",milvus_uri="",
        use_llm=False,auth_enabled=True,admin_password_hash=password_hash(ADMIN))
    with TestClient(create_app(tmp_path,"fallback",settings)) as c:
        c.headers["X-Proclab-Request"]="1"
        for name in ("employee","colleague"):
            c.post("/api/auth/register",json={"username":name,"password":PASSWORD}).raise_for_status()
        yield c

def login(c,name="admin"):
    r=c.post("/api/auth/login",json={"username":name,"password":ADMIN if name=="admin" else PASSWORD})
    r.raise_for_status()
    return r.json()["id"]
def task(c,project=None):
    r=c.post("/api/tasks",json={"question":"分析 B-103","project_id":project})
    assert r.status_code==200,r.text
    assert r.json()["status"]=="pending_review"
    return r.json()
def policy(c,project,**values):
    return c.patch("/api/projects/"+project,json=values)
def supplement(c,t):
    row=t["analysis"]["missing"][0]
    return c.post("/api/tasks/"+t["task_id"]+"/supplements",json={
        "corrections":[{"row_id":row["row_id"],"parameter":row["parameter"],"value":181,"unit":"℃"}],
        "source_note":"模拟校准后的补充测量"} )

def test_employee_cannot_manage_accounts_projects_or_company_library(client):
    c=client;employee=login(c,"employee");project=c.get("/api/projects").json()[0]["id"]
    for method,path,body in [
        ("GET","/api/admin/users",None),("GET","/api/admin/users/admin",None),
        ("POST","/api/admin/users",{"username":"intruder","password":PASSWORD}),
        ("PATCH","/api/admin/users/admin",{"active":False}),("DELETE","/api/admin/users/admin",None),
        ("GET","/api/audit",None),("GET","/api/projects/"+project+"/members",None),
        ("PATCH","/api/projects/"+project,{"stage":"archived"}),
        ("POST","/api/knowledge/publish",{"document_id":"unknown","title":"越权发布"}),
        ("POST","/api/knowledge/unknown/withdraw",None),
        ("POST","/api/knowledge/submissions/unknown/review",{"approved":True,"note":"不能自行通过"}),
        ("POST","/api/knowledge/reindex",None),("POST","/api/admin/analytics/replay",None),
        ("POST","/api/admin/analytics/sync",None)]:
        r=c.request(method,path,json=body);assert r.status_code==403,(method,path,r.text)
    with pytest.raises(PermissionError):c.app.state.service.platform.repo.configure_project(employee,project,stage="archived")
    assert c.get("/api/projects").json()[0]["stage"]=="analysis"

@pytest.mark.parametrize("role",["viewer","reviewer"])
def test_readonly_roles_cannot_analyze_repair_or_change_frozen_inputs(client,role):
    c=client;login(c);project=c.get("/api/projects").json()[0]["id"]
    employee=login(c,"employee");login(c);policy(c,project,member=employee,role="analyst").raise_for_status()
    login(c,"employee");t=task(c,project);ident=t["task_id"]
    # A valid pending supplement is present before access is narrowed.
    service=c.app.state.service
    item=service.evidence.submit(t,[{"row_id":t["readings"][0]["row_id"],"parameter":"temperature_c","value":181,"unit":"℃"}],
        "模拟补充测量来源",None,employee)
    login(c);policy(c,project,member=employee,role=role).raise_for_status()
    login(c,"employee");before=copy.deepcopy(service.get(ident))
    selected=next(p for p in c.get("/api/projects").json() if p["id"]==project)
    assert selected["permissions"]["analyze"] is False
    assert c.get("/api/tasks/"+ident).json()["permissions"]["analyze"] is False
    assert c.post("/api/tasks",json={"question":"分析 B-101","project_id":project}).status_code==403
    assert c.post("/api/tasks/"+ident+"/retry",json={}).status_code==403
    assert c.post("/api/tasks/"+ident+"/replan",json={"note":"不能借重规划执行"}).status_code==403
    assert supplement(c,t).status_code==403
    assert c.post("/api/supplements/"+item["id"]+"/review",json={"approved":True,"note":"不能隐式触发重试"}).status_code==403
    assert service.get(ident)==before
    assert service.control.get("supplement",item["id"],employee)["status"]=="pending_review"
    if role=="viewer":
        assert c.post("/api/tasks/"+ident+"/review",json={"approved":True,"note":"不能越权复核"}).status_code==403
    else:
        assert c.post("/api/tasks/"+ident+"/review",json={"approved":True,"note":"仅发布个人限制性说明"}).status_code==200

def test_review_and_archive_stage_gate_all_mutations_and_keep_readable_history(client):
    c=client;employee=login(c,"employee");t=task(c);ident=t["task_id"];project=t["scope"]["project_id"]
    login(c);policy(c,project,stage="review").raise_for_status()
    login(c,"employee")
    assert c.get("/api/tasks/"+ident).status_code==200
    assert c.post("/api/tasks/"+ident+"/retry",json={}).status_code==403
    assert supplement(c,t).status_code==403
    assert c.get("/api/tasks/"+ident).json()["permissions"]["review"] is True
    assert c.post("/api/tasks/"+ident+"/review",json={"approved":True,"note":"复核阶段可发布限制性说明"}).status_code==200
    login(c);policy(c,project,stage="archived").raise_for_status()
    login(c,"employee")
    for suffix,body in [("review",{"approved":True,"note":"归档不能改变结果"}),("replan",{"note":"归档不能重规划"}),("retry",{})]:
        assert c.post("/api/tasks/"+ident+"/"+suffix,json=body).status_code==403
    assert c.get("/api/tasks/"+ident+"/report").status_code==200
    detail=c.get("/api/conversations/"+t["conversation_id"]).json()["tasks"][0]
    assert detail["permissions"]["analyze"] is False and detail["permissions"]["review"] is False

def test_revocation_cannot_be_bypassed_through_history_reviews_exports_or_mutations(client):
    c=client;login(c);project=c.get("/api/projects").json()[0]["id"]
    employee=login(c,"employee");login(c);policy(c,project,member=employee,role="analyst").raise_for_status()
    login(c,"employee");t=task(c,project);ident=t["task_id"]
    login(c);policy(c,project,member=employee,role="revoked").raise_for_status()
    login(c,"employee")
    for suffix in ("","/report","/execution","/results","/events"):
        assert c.get("/api/tasks/"+ident+suffix).status_code==404
    for suffix,body in [("review",{"approved":True}),("retry",{}),("replan",{"note":"尝试越过撤权"})]:
        assert c.post("/api/tasks/"+ident+"/"+suffix,json=body).status_code==404
    history=c.get("/api/conversations/"+t["conversation_id"]).json()
    assert history["tasks"]==[] and history["messages"]==[]
    assert not c.get("/api/supplements").json()
    assert not c.get("/api/reviews").json()["tasks"]
    assert c.post("/api/tasks/"+ident+"/remember").status_code==404
    follow=c.post("/api/tasks",json={"question":"你好","conversation_id":t["conversation_id"]}).json()
    assert follow["status"]=="completed"
    assert all(m.get("task_id")!=ident for m in follow["context"])

def test_admin_project_controls_validate_atomic_changes_and_disabled_members(client):
    c=client;employee=login(c,"employee");login(c);project=c.get("/api/projects").json()[0]["id"]
    assert c.get("/api/projects/"+project+"/members").status_code==200
    for data in ({},{"role":"viewer"},{"member":employee},{"stage":"archived","member":employee,"role":"bad"},{"stage":"analysis","extra":True}):
        assert policy(c,project,**data).status_code==422
    assert c.get("/api/projects").json()[0]["stage"]=="analysis"
    c.patch("/api/admin/users/"+employee,json={"active":False}).raise_for_status()
    assert policy(c,project,member=employee,role="analyst").status_code==422
    assert policy(c,project,member=employee,role="revoked").status_code==200

def test_disabled_project_owner_blocks_new_work_but_preserves_colleague_history(client):
    c=client;employee=login(c,"employee");project=c.get("/api/projects").json()[0]["id"]
    colleague=login(c,"colleague");login(c);policy(c,project,member=colleague,role="analyst").raise_for_status()
    login(c,"colleague");t=task(c,project)
    login(c);c.patch("/api/admin/users/"+employee,json={"active":False}).raise_for_status()
    login(c,"colleague")
    assert c.get("/api/tasks/"+t["task_id"]).status_code==200
    assert c.post("/api/tasks",json={"question":"分析 B-101","project_id":project}).status_code==403
    assert c.post("/api/tasks/"+t["task_id"]+"/retry",json={}).status_code==403

def test_stream_rechecks_session_before_sending_state(client,monkeypatch):
    c=client;login(c,"employee");t=task(c)
    control=c.app.state.service.control
    session=control.session
    count=[0]
    def expire(token):
        count[0]+=1
        return session(token) if count[0]==1 else None
    monkeypatch.setattr(control,"session",expire)
    r=c.get("/api/tasks/"+t["task_id"]+"/events")
    assert r.status_code==200 and "event: state" not in r.text and "event: done" in r.text
