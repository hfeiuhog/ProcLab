import base64
import time
from datetime import datetime,timedelta,timezone
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.control import password_hash,BudgetExceeded
from app.documents import DocumentService,DocumentFailure
from app.engine import TaskService
from app.evidence import digest
from app.harness import boundary_reason
from app.steps import validate_step

ADMIN='Admin-test-password-2026'
HR='Hr-test-password-2026'

def settings(tmp_path,**kw):
    return Settings(_env_file=None,runtime_dir=str(tmp_path),database_url='',redis_url='',milvus_uri='',use_llm=False,
        auth_enabled=True,admin_password_hash=password_hash(ADMIN),hr_password_hash=password_hash(HR),**kw)

def login(c,name='hr',password=HR):
    r=c.post('/api/auth/login',json={'username':name,'password':password},headers={'X-Proclab-Request':'1'})
    assert r.status_code==200,r.text
    c.headers['X-Proclab-Request']='1'
    return r

def wait(service,ident):
    for _ in range(300):
        state=service.get(ident)
        if state['status'] not in ('queued','running'):return state
        time.sleep(.02)
    raise AssertionError('task timeout')

def correction(parent):
    f=parent['analysis']['missing'][0]
    return [{'row_id':f['row_id'],'parameter':f['parameter'],'value':2.01,'unit':'MPa'}]

def test_password_login_csrf_revocable_logout_and_scoped_resources(tmp_path):
    with TestClient(create_app(tmp_path,'langgraph',settings(tmp_path))) as c:
        assert c.get('/api/conversations').status_code==401
        assert c.get('/api/auth/me').status_code==401
        assert c.post('/api/auth/login',json={'username':'hr','password':HR}).status_code==403
        assert c.post('/api/auth/login',json={'username':'hr','password':'wrong'},headers={'X-Proclab-Request':'1'}).status_code==401
        r=login(c);assert r.json()['role']=='demo'
        assert 'httponly' in r.headers['set-cookie'].lower()
        assert 'samesite=lax' in r.headers['set-cookie'].lower()
        old_cookie=c.cookies.get('proclab_session')
        assert c.get('/api/admin/users').status_code==403
        assert c.post('/api/memories',json={'content':'不应创建此备注'},headers={'Origin':'https://evil.example'}).status_code==403
        a=c.post('/api/tasks',json={'question':'分析 B-102 批次','remember_result':True}).json()
        m=c.post('/api/memories',json={'content':'HR 独有的温度校准记录'}).json()
        assert a['status']=='completed' and a['owner_id']!='admin'
        assert len(c.get('/api/memories').json())==2
        login(c,'admin',ADMIN)
        assert c.get('/api/tasks/'+a['task_id']).status_code==404  # Private employee results are not an admin bypass.
        c.post('/api/admin/users',json={'username':'second','password':'Second-test-2026'}) .raise_for_status()
        login(c,'second','Second-test-2026')
        assert c.get('/api/conversations').json()==[]
        assert c.get('/api/memories').json()==[]
        for path in ['/api/tasks/'+a['task_id'],'/api/conversations/'+a['conversation_id'],'/api/tasks/'+a['task_id']+'/events','/api/tasks/'+a['task_id']+'/report']:
            assert c.get(path).status_code==404
        assert c.post('/api/tasks/'+a['task_id']+'/review',json={'approved':True}).status_code==404
        assert c.post('/api/tasks/'+a['task_id']+'/retry',json={}).status_code==404
        assert c.delete('/api/memories/'+m['id']).status_code==404
        other=c.post('/api/tasks',json={'question':'温度校准规范是什么','intent':'knowledge'}).json()
        assert other['recalled_memories']==[]
        login(c)
        assert len(c.get('/api/conversations').json())==1
        assert c.post('/api/auth/logout').status_code==200
        c.cookies.set('proclab_session',old_cookie)
        # Logging out revokes the current session; older valid sessions can remain.
        assert c.get('/api/auth/me').status_code==200
        c.post('/api/auth/logout').raise_for_status()
        c.cookies.set('proclab_session',old_cookie)
        assert c.get('/api/auth/me').status_code==401


def test_sessions_survive_service_restart_and_owner_does_not_change(tmp_path):
    config=settings(tmp_path)
    with TestClient(create_app(tmp_path,'fallback',config)) as c:
        login(c)
        token=c.cookies.get('proclab_session')
        task=c.post('/api/tasks',json={'question':'分析 B-101 批次'}).json()
    with TestClient(create_app(tmp_path,'fallback',config)) as c:
        c.cookies.set('proclab_session',token)
        assert c.get('/api/auth/me').json()['id']==task['owner_id']
        assert c.get('/api/tasks/'+task['task_id']).status_code==200


def test_reviewed_measurement_creates_new_verified_snapshot_original_remains_missing(tmp_path):
    service=TaskService(tmp_path,'langgraph',settings=settings(tmp_path))
    try:
        hr=next(u['id'] for u in service.control.list_users() if u['username']=='hr')
        p=service.create('分析 B-103 批次',owner_id=hr)
        assert p['status']=='pending_review'
        s=service.evidence.submit(p,correction(p),'模拟补采记录 2026-10-20；人工录入，仅供演示',None,hr)
        with pytest.raises(ValueError):service.retry(p['task_id'],hr,evidence_bundle_id=s['id'])
        with pytest.raises(KeyError):service.control.get('supplement',s['id'],'other')
        service.evidence.approve(s['id'],hr,True,'与模拟补采记录一致')
        c=service.retry(p['task_id'],hr,evidence_bundle_id=s['id']);child=wait(service,c['task_id'])
        assert child['status']=='completed',child.get('review_reason')
        assert child['validation_details']['independent_numeric_check'] is True
        assert child['parent_task_id']==p['task_id'] and child['repair_version']==1
        assert not child['analysis']['missing']
        assert any(s['id'] in source for source in child['report']['sources'])
        assert service.get(p['task_id'])['analysis']['missing']
        assert service.get(p['task_id'])['status']=='pending_review'
        from app.tools import query_batch_data
        assert query_batch_data('B-103')[0]['pressure_mpa']==''
        tampered=deepcopy(child);tampered['readings'][0]['pressure_mpa']='9.99'
        assert validate_step(tampered,service.evidence)['validation']=='needs_review'
        c2=service.retry(child['task_id'],hr);assert wait(service,c2['task_id'])['status']=='completed'
        with pytest.raises(ValueError):service.retry(c2['task_id'],hr)
        with pytest.raises(BudgetExceeded):service.retry(p['task_id'],hr,evidence_bundle_id=s['id'])
    finally:service.close()


def test_document_failure_manual_repair_review_and_version_pin(tmp_path,monkeypatch):
    config=settings(tmp_path)
    service=TaskService(tmp_path,'fallback',settings=config)
    doc=DocumentService(config,service.control)
    try:
        monkeypatch.setattr(doc,'_paddle',lambda *a:(_ for _ in ()).throw(TimeoutError()))
        with pytest.raises(DocumentFailure) as failure:doc.parse('fixture.png',base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode())
        ident=failure.value.document_id
        assert service.control.get('document',ident)['status']=='needs_repair'
        monkeypatch.setattr(doc,'_paddle',lambda *a:('压力 2.01 MPa',{'provider':'test'}))
        parsed=doc.retry(ident,'admin','precision')
        assert parsed['attempts']==2
        with pytest.raises(ValueError):service.create('压力资料说明',intent='knowledge',evidence_document_ids=[ident])
        doc.correct(ident,'admin','压力 2.02 MPa','依据原始文件人工核对')
        approved=doc.review(ident,'admin',True,'与原文核对通过')
        assert approved['approved_version']==2
        state=service.create('压力资料说明',intent='knowledge',evidence_document_ids=[ident])
        assert state['evidence_document_versions'][ident]==2
        assert any(d['origin']=='user_supplied_reviewed' for d in state['docs'])
        with pytest.raises(ValueError):doc.retry(ident,'admin','precision')
        assert service.control.get('document',ident)['status']=='approved'
        doc.correct(ident,'admin','压力 2.03 MPa','第二次人工修订待审核')
        assert service.evidence.documents(state)[0]['content']=='压力 2.02 MPa'
        job=service.control.get('document',ident)
        job['versions'][1]['text']='被篡改的压力'
        service.control.put('document',job,'admin')
        with pytest.raises(ValueError,match='快照'):service.evidence.documents(state)
    finally:service.close()


def test_harness_budget_both_runtimes_and_deadline(tmp_path):
    config=settings(tmp_path,harness_max_tool_calls=3)
    state={'run_started_at':(datetime.now(timezone.utc)-timedelta(seconds=181)).isoformat(),'tool_budget':12}
    assert '时间预算' in boundary_reason(state,config)
    assert boundary_reason({'tool_budget':0},config)
    assert boundary_reason({'tool_budget':0},config,check_budget=False) is None
    for mode in ['langgraph','fallback']:
        service=TaskService(tmp_path/mode,mode,settings=config)
        try:
            result=service.create('分析 B-102 批次')
            assert result['status']=='pending_review'
            assert result['tool_budget']==0
            assert len(result['completed_steps'])==3
            assert '预算' in result['review_reason']
        finally:service.close()


def test_daily_quota_failure_does_not_consume_global_capacity(tmp_path):
    service=TaskService(tmp_path,'fallback',settings=settings(tmp_path,demo_daily_tasks=1,demo_global_daily_tasks=2))
    try:
        service.control.task_quota('one')
        for _ in range(3):
            with pytest.raises(BudgetExceeded):service.control.task_quota('one')
        service.control.task_quota('two')
        with pytest.raises(BudgetExceeded):service.control.task_quota('three')
    finally:service.close()
