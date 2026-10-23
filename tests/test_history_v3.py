from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from app.api import create_app
from app.config import Settings
from app.control import password_hash
from app.store import TaskStore

HEADERS={"X-Proclab-Request":"1"}
PASSWORD="History-test-password-2026"

def settings(path):
    return Settings(_env_file=None,runtime_dir=str(path),database_url="",redis_url="",milvus_uri="",use_llm=False,auth_enabled=True,admin_password_hash=password_hash(PASSWORD))

def register(c,name):
    r=c.post("/api/auth/register",json={"username":name,"password":PASSWORD});assert r.status_code==201,r.text
    return r.json()

def test_history_permissions_mutations_and_search_survive_restart(tmp_path):
    config=settings(tmp_path)
    with TestClient(create_app(tmp_path,"fallback",config),headers=HEADERS) as c:
        owner=register(c,"history_owner")["id"]
        first=c.post("/api/conversations").json()["id"]
        second=c.post("/api/conversations").json()["id"]
        c.app.state.service.store.add_message(first,"user","寻找隐含在以前问题里的聚合釜波动原因", "fixture-history")
        assert c.patch("/api/conversations/"+first,json={"title":"  星澜复材质量复核  ","pinned":True}).json()["title"]=="星澜复材质量复核"
        assert c.get("/api/conversations").json()[0]["id"]==first
        assert c.get("/api/conversations",params={"q":"聚合釜"}).json()[0]["matched_question"].startswith("寻找隐含")
        c.post("/api/auth/logout");register(c,"history_other")
        assert c.get("/api/conversations").json()==[]
        assert c.get("/api/conversations",params={"q":"聚合釜"}).json()==[]
        for method,body in [("GET",None),("PATCH",{"title":"越权改名"}),("PATCH",{"pinned":False}),("DELETE",None)]:
            assert c.request(method,"/api/conversations/"+first,**({"json":body} if body else {})).status_code==404
        c.post("/api/auth/logout");c.post("/api/auth/login",json={"username":"history_owner","password":PASSWORD}).raise_for_status()
        cookie=c.cookies.get("proclab_session")
    with TestClient(create_app(tmp_path,"fallback",config),headers=HEADERS) as c:
        c.cookies.set("proclab_session",cookie)
        row=c.get("/api/conversations/"+first).json();assert row["pinned"] and row["title"]=="星澜复材质量复核"
        assert c.patch("/api/conversations/"+first,json={"pinned":False}).json()["pinned"] is False
        assert c.get("/api/conversations").json()[0]["id"]==first # actual latest message time
        assert c.delete("/api/conversations/"+first).status_code==204
        assert c.get("/api/conversations/"+first).status_code==404
        assert c.patch("/api/conversations/"+first,json={"pinned":True}).status_code==404
        assert c.delete("/api/conversations/"+first).status_code==404
        assert c.get("/api/conversations",params={"q":"聚合釜"}).json()==[]
        assert [x["id"] for x in c.get("/api/conversations").json()]==[second]
        assert c.get("/api/audit").status_code==403
        c.post("/api/auth/login",json={"username":"admin","password":PASSWORD}).raise_for_status()
        audit=c.get("/api/audit")
        assert {x["action"] for x in audit.json()} >= {"conversation_updated","conversation_deleted"}
        assert "星澜复材质量复核" not in audit.text


def test_search_filters_before_limit_and_treats_wildcards_literally(tmp_path):
    store=TaskStore(tmp_path/"store.sqlite")
    target=store.create_conversation("旧分析")
    store.add_message(target["id"],"user","含有 100%_特殊/原料 的历史问题","target")
    store.add_message(target["id"],"assistant","只在回答中出现的词语不会匹配","target")
    for i in range(106):store.create_conversation("新分析 "+str(i))
    assert target["id"] not in [x["id"] for x in store.list_conversations()]
    for q in ["特殊/原料","100%_","%_","历史问题"]:
        assert [x["id"] for x in store.list_conversations(query=q)]==[target["id"]]
    assert len(store.list_conversations(query="%"))==1
    assert store.list_conversations(query="只在回答中出现")==[]
    assert store.list_conversations(allowed_ids=[],query="原料")==[]
    store.update_conversation(target["id"],pinned=True)
    assert store.list_conversations()[0]["id"]==target["id"]
    store.close()


def test_history_tombstone_preserves_execution_and_is_not_resurrected(tmp_path):
    with TestClient(create_app(tmp_path,"fallback",settings(tmp_path)),headers=HEADERS) as c:
        register(c,"archive_user")
        task=c.post("/api/tasks",json={"question":"分析 B-102 的超限参数","intent":"batch","batch_id":"B-102"}).json()
        ident=task["conversation_id"];assert task["status"]=="completed"
        assert c.delete("/api/conversations/"+ident).status_code==204
        assert c.get("/api/tasks/"+task["task_id"]).json()["status"]=="completed"
        assert c.get("/api/tasks/"+task["task_id"]+"/execution").status_code==200
        # A late completion may still write its audit/message but must never restore the history.
        c.app.state.service.store.add_message(ident,"assistant","晚到的完成消息",task["task_id"])
        assert c.get("/api/conversations").json()==[]
        assert c.get("/api/conversations/"+ident).status_code==404
        r=c.post("/api/tasks",json={"question":"继续","conversation_id":ident})
        assert r.status_code==404


def test_history_validation_and_csrf(tmp_path):
    with TestClient(create_app(tmp_path,"fallback",settings(tmp_path)),headers=HEADERS) as c:
        register(c,"validate_user");ident=c.post("/api/conversations").json()["id"]
        for body in [{"title":"   "},{"title":"x"*121},{"pinned":"yes"},{"owner_id":"admin"},{},{"title":None}]:
            assert c.patch("/api/conversations/"+ident,json=body).status_code==422,body
        assert c.get("/api/conversations",params={"q":"x"*201}).status_code==422
        assert c.patch("/api/conversations/"+ident,json={"title":"x"},headers={"Origin":"https://evil.example"}).status_code==403
        assert c.delete("/api/conversations/"+ident,headers={"Origin":"https://evil.example"}).status_code==403
        assert c.get("/api/conversations/"+ident).status_code==200


def test_additive_migration_keeps_old_titles_messages_and_custom_title(tmp_path):
    path=tmp_path/"old.sqlite";engine=create_engine("sqlite:///"+str(path))
    with engine.begin() as cn:
        cn.execute(text("CREATE TABLE conversations (id VARCHAR(36) PRIMARY KEY, title VARCHAR(120), created_at VARCHAR(40), updated_at VARCHAR(40))"))
        cn.execute(text("INSERT INTO conversations VALUES ('old-id','旧版名称','2026-01-01','2026-01-01')"))
    engine.dispose();store=TaskStore(path)
    assert store.conversation("old-id")["title"]=="旧版名称"
    assert store.conversation("old-id")["pinned"] is False
    store.update_conversation("old-id",title="新的工艺分析",pinned=True)
    store.add_message("old-id","user","不得覆盖手动设置的标题","legacy-task")
    assert store.conversation("old-id")["title"]=="新的工艺分析"
    store.close();store=TaskStore(path);assert store.conversation("old-id")["pinned"]
    store.update_conversation("old-id",remove=True);store.close();store=TaskStore(path)
    assert store.conversation("old-id") is None and store.list_conversations()==[];store.close()
