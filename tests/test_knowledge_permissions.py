"""Role isolation, immutable sharing and private-RAG side-channel protection."""
import base64,json
import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.control import password_hash
from app.evidence import digest
ADMIN="Knowledge-admin-2026"
PASSWORD="Member12!"
@pytest.fixture
def client(tmp_path):
    settings=Settings(_env_file=None,runtime_dir=str(tmp_path),database_url="",redis_url="",milvus_uri="",
        use_llm=False,auth_enabled=True,admin_password_hash=password_hash(ADMIN),document_daily_limit=100)
    with TestClient(create_app(tmp_path,"fallback",settings)) as c:
        c.headers["X-Proclab-Request"]="1"
        for name in ("member_a","member_b"):
            r=c.post("/api/auth/register",json={"username":name,"password":PASSWORD});assert r.status_code==201
        yield c
def login(c,name="admin"):
    r=c.post("/api/auth/login",json={"username":name,"password":ADMIN if name=="admin" else PASSWORD})
    assert r.status_code==200
    return r.json()["id"]
def upload(c,text,approved=True):
    r=c.post("/api/documents/parse",json={"filename":"personal.md","content_base64":base64.b64encode(text.encode()).decode()})
    assert r.status_code==200,r.text
    ident=r.json()["id"]
    if approved:
        r=c.post("/api/documents/"+ident+"/review",json={"approved":True,"note":"持有人逐字核对原文"});assert r.status_code==200
    return ident
def submit(c,ident,title="共享申请"):
    return c.post("/api/knowledge/submissions",json={"document_id":ident,"title":title})
def review(c,ident,approved=True):
    return c.post("/api/knowledge/submissions/"+ident+"/review",json={"approved":approved,"note":"管理员核对提交快照"})
def test_audit_is_administrator_only_and_omits_employee_private_notes(client):
    c=client;owner=login(c,"member_a")
    ident=upload(c,"琥珀夹具私人保养记录")
    c.post("/api/documents/"+ident+"/correct",json={"text":"琥珀夹具私人记录第二版","note":"敏感备注PRIVATE-SENTINEL"}).raise_for_status()
    assert c.get("/api/audit").status_code==403
    with pytest.raises(PermissionError):c.app.state.service.control.audit_list(owner)
    login(c);r=c.get("/api/audit")
    assert r.status_code==200 and "PRIVATE-SENTINEL" not in r.text
def test_personal_catalog_auto_retrieves_only_for_owner_even_against_admin(client):
    c=client;owner=login(c,"member_a")
    marker="青鹭夹具专用复位：切断电源17分钟，检查银色锁销。"
    ident=upload(c,marker)
    assert any(d.get("scope")=="personal" and marker in d["content"] for d in c.get("/api/knowledge?scope=personal").json())
    task=c.post("/api/tasks",json={"question":"青鹭夹具专用复位步骤是什么？","intent":"knowledge","remember_result":True}).json()
    assert task["status"]=="completed",task.get("review_reason")
    assert any(d.get("scope")=="personal" and marker in d["content"] for d in task["docs"])
    c.post("/api/memories",json={"content":"私人记忆："+marker}).raise_for_status()
    for name in ("member_b","admin"):
        login(c,name)
        assert not c.get("/api/documents").json()
        assert marker not in c.get("/api/knowledge").text
        assert c.get("/api/knowledge?scope=personal").json()==[]
        for path in ("/api/documents/"+ident,"/api/tasks/"+task["task_id"],"/api/conversations/"+task["conversation_id"],
                     "/api/tasks/"+task["task_id"]+"/execution","/api/tasks/"+task["task_id"]+"/report"):
            assert c.get(path).status_code==404,(name,path)
        assert task["conversation_id"] not in c.get("/api/conversations").text
        assert marker not in c.get("/api/memories").text
        assert marker not in json.dumps(c.get("/api/reviews").json(),ensure_ascii=False)
        assert c.post("/api/documents/"+ident+"/correct",json={"text":"越权修改","note":"越权修改说明"}).status_code==404
    login(c)
    assert c.post("/api/knowledge/publish",json={"document_id":ident,"title":"越权发布员工私有资料"}).status_code==404
def test_submission_freezes_only_selected_version_and_admin_publishes_that_copy(client):
    c=client;login(c,"member_a")
    original="白鹭夹具共享手册：先冷却23分钟，再按橙色复位键。"
    ident=upload(c,original)
    pending=c.app.state.service._reserve("白鹭夹具怎么复位？",owner_id=c.get("/api/auth/me").json()["id"],intent="knowledge")
    r=submit(c,ident);assert r.status_code==201
    sub=r.json();assert submit(c,ident).json()["id"]==sub["id"]
    assert c.post("/api/knowledge/submissions/"+sub["id"]+"/review",json={"approved":True,"note":"员工不能自行发布"}).status_code==403
    changed="新版私人草稿NEW-PRIVATE-SENTINEL，不在提交内容中。"
    c.post("/api/documents/"+ident+"/correct",json={"text":changed,"note":"此修改保持个人范围"}).raise_for_status()
    old=c.app.state.service.evidence.documents(pending)
    assert any(original in d["content"] for d in old)
    login(c,"member_b")
    assert c.get("/api/knowledge/submissions").json()==[]
    assert c.get("/api/knowledge/submissions/"+sub["id"]).status_code==404
    assert original not in c.get("/api/knowledge").text
    login(c)
    r=c.get("/api/knowledge/submissions/"+sub["id"]);assert r.status_code==200
    assert r.json()["snapshot"]["text"]==original and changed not in r.text
    assert c.get("/api/documents/"+ident).status_code==404
    result=review(c,sub["id"]);assert result.status_code==200
    assert result.json()["status"]=="approved"
    assert review(c,sub["id"]).status_code==422
    login(c,"member_b")
    catalog=c.get("/api/knowledge").json()
    assert any(d.get("scope")=="company" and original in d["content"] for d in catalog)
    assert changed not in json.dumps(catalog,ensure_ascii=False)
    task=c.post("/api/tasks",json={"question":"白鹭夹具共享手册怎么复位？","intent":"knowledge"}).json()
    assert task["status"]=="completed"
    assert any(d["origin"]=="admin_published" and original in d["content"] for d in task["docs"])
def test_unreviewed_or_foreign_upload_cannot_be_submitted_and_rejection_keeps_private(client):
    c=client;login(c,"member_a");ident=upload(c,"未共享的个人记录",False)
    assert submit(c,ident).status_code==422
    c.post("/api/documents/"+ident+"/review",json={"approved":True,"note":"核对原文完成"}).raise_for_status()
    r=submit(c,ident);sub=r.json()["id"]
    login(c,"member_b")
    assert submit(c,ident).status_code==404
    login(c);assert review(c,sub,False).json()["status"]=="rejected"
    assert not c.get("/api/knowledge/releases").json()
    assert c.get("/api/documents/"+ident).status_code==404
def test_tampered_submission_is_rejected_before_publication(client):
    c=client;login(c,"member_a");ident=upload(c,"翠鸟夹具共享申请")
    sub=submit(c,ident).json()["id"]
    control=c.app.state.service.control
    item=control.get("knowledge_submission",sub)
    item["snapshot"]["text"]="伪造提交文本"
    item["snapshot"]["text_sha256"]=digest(item["snapshot"]["text"])
    control.put("knowledge_submission",item,item["owner_id"])
    login(c);assert review(c,sub).status_code==422
    assert not c.get("/api/knowledge/releases").json()
def test_admin_owns_own_uploads_and_legacy_unbound_memory_remains_visible(client):
    c=client;login(c)
    ident=upload(c,"管理员公司资料：海燕夹具先检查绿色锁销。")
    r=c.post("/api/knowledge/publish",json={"document_id":ident,"title":"海燕夹具公司资料"})
    assert r.status_code==201
    assert c.get("/api/documents/"+ident).status_code==200
    c.app.state.service.store.remember("历史管理员未绑定的手动备注")
    assert "历史管理员未绑定" in c.get("/api/memories").text
    login(c,"member_a")
    assert "海燕夹具" in c.get("/api/knowledge").text
    assert c.get("/api/documents/"+ident).status_code==404
