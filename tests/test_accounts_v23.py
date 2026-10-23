import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.control import password_hash
from app.engine import TaskService

ADMIN='Admin-test-password-2026'
HR='Hr-test-password-2026'
def config(tmp_path):
    return Settings(_env_file=None,runtime_dir=str(tmp_path),database_url='',redis_url='',milvus_uri='',use_llm=False,auth_enabled=True,admin_password_hash=password_hash(ADMIN),hr_password_hash=password_hash(HR))
def login(c,username='admin',password=ADMIN):
    r=c.post('/api/auth/login',json={'username':username,'password':password},headers={'X-Proclab-Request':'1'});r.raise_for_status();c.headers['X-Proclab-Request']='1';return r.json()

def test_admin_crud_ban_activate_and_password_reset_revoke_sessions(tmp_path):
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path))) as c:
        login(c)
        r=c.post('/api/admin/users',json={'username':'managed','password':'Managed-old-password-2026'});assert r.status_code==201
        user=r.json();ident=user['id'];path='/api/admin/users/'+ident
        assert 'password_hash' not in user and 'password' not in user
        assert len(c.get('/api/admin/users?q=managed&active=true').json())==1
        assert c.get(path).json()['username']=='managed'
        assert c.post('/api/admin/users',json={'username':'managed','password':'Duplicate-password-2026'}).status_code==422
        login(c,'managed','Managed-old-password-2026');old=c.cookies.get('proclab_session')
        for method,route,body in [('get','/api/admin/users',None),('get',path,None),('patch',path,{'active':False}),('delete',path,None)]:
            assert c.request(method,route,**({'json':body} if body else {})).status_code==403
        login(c)
        assert c.patch(path,json={'active':False}).json()['active']==0
        # An already-issued cookie stops working immediately on ban.
        assert c.get('/api/auth/me',headers={'Cookie':'proclab_session='+old}).status_code==401
        assert c.post('/api/auth/login',json={'username':'managed','password':'Managed-old-password-2026'}).status_code==401
        assert c.patch(path,json={'active':True}).json()['active']==1
        assert c.get('/api/auth/me',headers={'Cookie':'proclab_session='+old}).status_code==401
        login(c,'managed','Managed-old-password-2026');before_reset=c.cookies.get('proclab_session');login(c)
        r=c.patch(path,json={'username':'renamed','password':'Managed-new-password-2026'});assert r.status_code==200 and r.json()['sessions_revoked']
        assert c.get('/api/auth/me',headers={'Cookie':'proclab_session='+before_reset}).status_code==401
        assert c.patch(path,json={'password':'short'}).status_code==422
        assert c.post('/api/auth/login',json={'username':'managed','password':'Managed-old-password-2026'}).status_code==401
        login(c,'renamed','Managed-new-password-2026');deleted_cookie=c.cookies.get('proclab_session');login(c)
        assert c.delete(path).status_code==204
        assert c.get(path).status_code==404
        assert c.get('/api/auth/me',headers={'Cookie':'proclab_session='+deleted_cookie}).status_code==401
        assert c.get('/api/admin/users?q=renamed').json()==[]
        assert c.patch('/api/admin/users/admin',json={'active':False}).status_code==403
        assert c.delete('/api/admin/users/admin').status_code==403
        assert c.patch('/api/admin/users/missing',json={'active':False}).status_code==404
        assert c.patch('/api/admin/users/admin',json={}).status_code==422


def test_seed_account_changes_and_deletion_survive_restart(tmp_path):
    settings=config(tmp_path)
    a=TaskService(tmp_path,'fallback',settings=settings)
    hr=next(u for u in a.control.list_users() if u['username']=='hr');ident=hr['id']
    task=a.create('分析 B-101 批次',owner_id=ident)
    a.control.update_user(ident,username='hr_renamed',password='Changed-hr-password-2026',active=False);a.close()
    b=TaskService(tmp_path,'fallback',settings=settings)
    assert b.control.get_user(ident)['username']=='hr_renamed' and b.control.get_user(ident)['active']==0
    assert not b.control.list_users(q='hr',active=True)
    b.control.delete_user(ident);b.close()
    c=TaskService(tmp_path,'fallback',settings=settings)
    try:
        assert not c.control.list_users(q='hr')
        new=c.control.add_user('hr','Brand-new-password-2026');assert new['id']!=ident
        with pytest.raises(KeyError):c.control.require('task',task['task_id'],new['id'])
        assert c.get(task['task_id'])
    finally:c.close()


def test_admin_password_changes_not_overwritten_by_env_restart(tmp_path):
    settings=config(tmp_path)
    a=TaskService(tmp_path,'fallback',settings=settings)
    a.control.update_user('admin',password='Updated-admin-password-2026');a.close()
    b=TaskService(tmp_path,'fallback',settings=settings)
    try:
        assert b.control.authenticate('admin',ADMIN,'127.0.0.1') is None
        assert b.control.authenticate('admin','Updated-admin-password-2026','127.0.0.1')['role']=='admin'
    finally:b.close()


def test_siliconflow_compatibility_fields_use_provided_provider_credentials():
    s=Settings(_env_file=None,model_provider='siliconflow',embedding_provider='siliconflow',siliconflow_api_key='fake-provider-test-key',siliconflow_base_url='https://provider.example/v1',agent_model='test-agent')
    assert s.openai_api_key==s.embedding_api_key==s.siliconflow_api_key
    assert s.openai_base_url==s.embedding_base_url==s.siliconflow_base_url
    assert s.openai_model=='test-agent'

def test_local_admin_reset_refuses_production_and_remote_database():
    from scripts.reset_local_admin import validate_local_target
    from types import SimpleNamespace
    with pytest.raises(ValueError,match='development'):
        validate_local_target(SimpleNamespace(app_env='production',database_url=''))
    with pytest.raises(ValueError,match='remote'):
        validate_local_target(SimpleNamespace(app_env='development',database_url='mysql+pymysql://user:password@192.0.2.1:3306/demo'))
    validate_local_target(SimpleNamespace(app_env='development',database_url='mysql+pymysql://user:password@127.0.0.1:13306/demo'))
