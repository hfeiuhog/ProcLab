import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.control import password_hash

ADMIN='Admin-register-test-2026'
PASSWORD='Registration-test-2026'
HEADERS={'X-Proclab-Request':'1'}

def config(tmp_path,**kw):
    return Settings(_env_file=None,runtime_dir=str(tmp_path),database_url='',redis_url='',milvus_uri='',use_llm=False,auth_enabled=True,admin_password_hash=password_hash(ADMIN),**kw)

def signup(c,name='new_user',**extra):
    return c.post('/api/auth/register',json={'username':name,'password':PASSWORD,**extra},headers=HEADERS)

def test_register_logs_in_as_user_with_business_features_and_no_account_management(tmp_path):
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path))) as c:
        assert c.get('/api/auth/status').json()['registration']
        r=signup(c);assert r.status_code==201,r.text
        u=r.json();assert u['role']=='user' and 'password' not in u and 'password_hash' not in u
        assert 'httponly' in r.headers['set-cookie'].lower() and 'samesite=lax' in r.headers['set-cookie'].lower()
        assert c.get('/api/auth/me').json()['id']==u['id']
        c.headers.update(HEADERS)
        for path in ['/api/projects','/api/agents','/api/analytics/semantic-model','/api/analytics/status','/api/knowledge','/api/batches','/api/reviews']:
            assert c.get(path).status_code==200,path
        task=c.post('/api/tasks',json={'question':'按设备统计全部批次的超限批次比例','intent':'analytics'}).json()
        assert task['status']=='completed' and task['owner_id']==u['id']
        assert c.get('/api/tasks/'+task['task_id']+'/execution').status_code==200
        assert c.get('/api/tasks/'+task['task_id']+'/report').status_code==200
        assert c.post('/api/memories',json={'content':'注册用户的工艺复核备注'}).status_code==201
        for method,path,body in [('GET','/api/admin/users',None),('GET','/api/admin/users/admin',None),('POST','/api/admin/users',{'username':'other','password':PASSWORD}),('PATCH','/api/admin/users/'+u['id'],{'active':False}),('DELETE','/api/admin/users/'+u['id'],None)]:
            assert c.request(method,path,**({'json':body} if body else {})).status_code==403
        c.post('/api/auth/logout').raise_for_status()
        c.post('/api/auth/login',json={'username':'new_user','password':PASSWORD}).raise_for_status()
        assert c.get('/api/auth/me').json()['role']=='user'

@pytest.mark.parametrize('payload',[{'role':'admin'},{'active':True},{'id':'admin'}])
def test_registration_rejects_privilege_fields(tmp_path,payload):
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path))) as c:
        assert signup(c,**payload).status_code==422
        assert c.get('/api/auth/me').status_code==401
        assert len(c.app.state.service.control.list_users())==1

def test_signup_validates_origin_duplicate_and_ip_budget(tmp_path):
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path))) as c:
        body={'username':'registered','password':PASSWORD}
        assert c.post('/api/auth/register',json=body).status_code==403
        assert c.post('/api/auth/register',json=body,headers={**HEADERS,'Origin':'https://evil.example'}).status_code==403
        assert signup(c,password='short').status_code==422
        assert signup(c,name='contains space').status_code==422
        assert signup(c,name='registered').status_code==201
        assert signup(c,name='registered').status_code==422
        assert signup(c,name='REGISTERED').status_code==422
        assert signup(c,name='ADMIN').status_code==422
        assert signup(c,name='last_one').status_code==201
        assert signup(c,name='over_limit').status_code==429

def test_signup_can_be_disabled(tmp_path):
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path,registration_enabled=False))) as c:
        assert not c.get('/api/auth/status').json()['registration']
        assert signup(c).status_code==403

def test_registered_account_survives_restart_and_admin_can_ban_and_delete(tmp_path):
    settings=config(tmp_path)
    with TestClient(create_app(tmp_path,'fallback',settings)) as c:
        ident=signup(c).json()['id'];cookie=c.cookies.get('proclab_session')
    with TestClient(create_app(tmp_path,'fallback',settings)) as c:
        c.cookies.set('proclab_session',cookie);assert c.get('/api/auth/me').json()['id']==ident
        c.headers.update(HEADERS)
        c.post('/api/auth/login',json={'username':'admin','password':ADMIN}).raise_for_status()
        assert c.get('/api/admin/users/'+ident).json()['role']=='user'
        assert c.patch('/api/admin/users/'+ident,json={'active':False}).status_code==200
        assert c.get('/api/auth/me',headers={'Cookie':'proclab_session='+cookie}).status_code==401
        assert c.post('/api/auth/login',json={'username':'new_user','password':PASSWORD}).status_code==401
        assert c.patch('/api/admin/users/'+ident,json={'active':True}).status_code==200
        assert c.get('/api/auth/me',headers={'Cookie':'proclab_session='+cookie}).status_code==401
        assert c.delete('/api/admin/users/'+ident).status_code==204
        assert c.get('/api/admin/users/'+ident).status_code==404
