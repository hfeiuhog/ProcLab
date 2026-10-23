"""Password policy gates, persisted sessions and registration behavior."""
import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.control import password_hash, validate_password

ADMIN="Administrator-test-2026"
GOOD="Eight12!"

@pytest.mark.parametrize("password",[
    "12345678","abcdefgh","ABCDEFGH","Abcdefgh","Abcdefg1",
    "abcdef1!","ABCDEF1!","Ab1!234","Ab1! 234",
])
def test_normal_password_rejects_short_or_missing_character_groups(password):
    with pytest.raises(ValueError):validate_password(password)

def test_normal_password_accepts_eight_or_more_and_admin_retains_its_minimum():
    validate_password(GOOD)
    validate_password(GOOD+"x"*248)
    with pytest.raises(ValueError):validate_password(GOOD+"x"*249)
    with pytest.raises(ValueError,match="管理员"):validate_password(GOOD,"admin")
    validate_password("long-admin-password","admin")

def settings(path):
    return Settings(_env_file=None,runtime_dir=str(path),database_url="",redis_url="",milvus_uri="",
        use_llm=False,auth_enabled=True,admin_password_hash=password_hash(ADMIN))

def test_eight_character_create_reset_and_session_revocation(tmp_path):
    with TestClient(create_app(tmp_path,"fallback",settings(tmp_path))) as c:
        c.headers["X-Proclab-Request"]="1"
        def login(name,pwd):
            r=c.post("/api/auth/login",json={"username":name,"password":pwd})
            assert r.status_code==200
        login("admin",ADMIN)
        r=c.post("/api/admin/users",json={"username":"eight_user","password":GOOD})
        assert r.status_code==201
        ident=r.json()["id"]
        assert not {"password","password_hash"} & r.json().keys()
        login("eight_user",GOOD)
        token=c.cookies.get("proclab_session")
        assert c.get("/api/admin/users").status_code==403
        login("admin",ADMIN)
        path="/api/admin/users/"+ident
        assert c.patch(path,json={"password":"12345678"}).status_code==422
        assert c.app.state.service.control.session(token)
        assert c.patch("/api/admin/users/admin",json={"password":GOOD}).status_code==422
        assert c.get("/api/auth/me").json()["role"]=="admin"
        assert c.patch(path,json={"password":"Reset34!"}).json()["sessions_revoked"]
        assert c.app.state.service.control.session(token) is None
        login("eight_user","Reset34!")

def test_registration_uses_same_eight_character_complexity_rule(tmp_path):
    with TestClient(create_app(tmp_path,"fallback",settings(tmp_path))) as c:
        c.headers["X-Proclab-Request"]="1"
        for weak in ("12345678","Onlylower123!","NoSpecial123"):
            # First string lacks letters; the latter two omit an upper or special group.
            if weak=="Onlylower123!":weak="onlylower123!"
            assert c.post("/api/auth/register",json={"username":"new_user","password":weak}).status_code==422
        r=c.post("/api/auth/register",json={"username":"new_user","password":GOOD})
        assert r.status_code==201 and r.json()["role"]=="user"
        assert c.get("/api/auth/me").json()["username"]=="new_user"
