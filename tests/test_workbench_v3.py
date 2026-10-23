import base64,io,wave
import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.control import password_hash
from app.engine import TaskService
from app.models import ModelRouter

ADMIN='Workbench-admin-test-2026'
USER='Workbench-user-test-2026'

def config(tmp_path,**kw):return Settings(_env_file=None,runtime_dir=str(tmp_path),database_url='',redis_url='',milvus_uri='',use_llm=False,auth_enabled=True,admin_password_hash=password_hash(ADMIN),**kw)
def login(c,name='admin',password=ADMIN):c.post('/api/auth/login',json={'username':name,'password':password}).raise_for_status()
def document(c,text='星舟夹具断电复位流程：先断电30秒，检查锁止件，再按蓝色复位按钮。'):
    r=c.post('/api/documents/parse',json={'filename':'夹具复位说明.txt','content_base64':base64.b64encode(text.encode()).decode()});r.raise_for_status();ident=r.json()['id']
    c.post('/api/documents/'+ident+'/review',json={'approved':True,'note':'已逐字核对原始文件'}).raise_for_status();return ident

def test_shared_knowledge_requires_admin_review_and_retrieves_for_registered_user(tmp_path):
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path)),headers={'X-Proclab-Request':'1'}) as c:
        login(c);ident=document(c)
        result=c.post('/api/knowledge/publish',json={'document_id':ident,'title':'星舟夹具复位指南'});assert result.status_code==201,result.text
        release=result.json()['id'];assert c.post('/api/knowledge/publish',json={'document_id':ident,'title':'重复发布'}).json()['id']==release
        c.post('/api/auth/register',json={'username':'worker','password':USER}).raise_for_status()
        assert c.post('/api/knowledge/publish',json={'document_id':ident,'title':'越权'}).status_code==403
        assert c.post('/api/knowledge/'+release+'/withdraw').status_code==403
        assert c.get('/api/documents/'+ident).status_code==404
        task=c.post('/api/tasks',json={'question':'星舟夹具断电后怎么复位？'}).json()
        assert task['intent']=='knowledge' and task['status']=='completed',task.get('review_reason')
        assert any(d['origin']=='admin_published' and '蓝色复位按钮' in d['content'] for d in task['docs'])
        assert task['evidence_verification']['passed'] and task['validation']=='passed'
        assert any('KB-' in d['reference'][0] for d in task['evidence_verification']['refs'])
        private=document(c,'私人资料：紫色夹具只能由本人查看。')
        assert c.post('/api/knowledge/publish',json={'document_id':private,'title':'私人'}).status_code==403
        assert not any('紫色夹具' in d['content'] for d in c.get('/api/knowledge').json())

def test_frozen_shared_release_survives_withdrawal_but_new_tasks_do_not_retrieve_it(tmp_path):
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path)),headers={'X-Proclab-Request':'1'}) as c:
        login(c);ident=document(c);release=c.post('/api/knowledge/publish',json={'document_id':ident,'title':'星舟复位'}).json()['id']
        service=c.app.state.service
        pending=service._reserve('星舟夹具断电后怎么复位？',intent='knowledge')
        assert release in pending['knowledge_versions']
        c.post('/api/knowledge/'+release+'/withdraw').raise_for_status()
        old=service._execute(pending['task_id']);assert old['status']=='completed'
        assert any(d['origin']=='admin_published' for d in old['docs'])
        new=service.create('星舟夹具断电后怎么复位？',intent='knowledge')
        assert release not in new['knowledge_versions']
        assert not any(d.get('origin')=='admin_published' for d in new.get('docs',[]))

def test_unapproved_document_cannot_be_published(tmp_path):
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path)),headers={'X-Proclab-Request':'1'}) as c:
        login(c)
        d=c.post('/api/documents/parse',json={'filename':'test.md','content_base64':base64.b64encode('未经核对的说明'.encode()).decode()}).json()
        assert c.post('/api/knowledge/publish',json={'document_id':d['id'],'title':'未审核'}).status_code==422

def test_analysis_modes_select_configured_models_and_remain_frozen(tmp_path,monkeypatch):
    s=Settings(_env_file=None,openai_model='fast-model',rule_reasoning_model='reason-model')
    calls=[]
    def complete(self,purpose,messages,**kw):calls.append((self.settings.openai_model,purpose));return 'test',{'model':self.settings.openai_model}
    monkeypatch.setattr(ModelRouter,'complete',complete)
    assert ModelRouter(s).answer({'question':'你好','intent':'chat','analysis_mode':'fast'})[1]['model']=='fast-model'
    assert ModelRouter(s).answer({'question':'你好','intent':'chat','analysis_mode':'thinking'})[1]['model']=='reason-model'
    with _service(tmp_path) as service:
        task=service.create('分析 B-102 工艺参数',analysis_mode='thinking')
        assert task['analysis_mode']=='thinking' and task['validation']=='passed'
        from app.orchestration.superagent import basis
        before=basis(task,service.settings);task['analysis_mode']='fast';assert basis(task,service.settings)!=before

from contextlib import contextmanager
@contextmanager
def _service(path):
    s=TaskService(path,'fallback',settings=Settings(_env_file=None,runtime_dir=str(path),database_url='',redis_url='',milvus_uri='',use_llm=False))
    try:yield s
    finally:s.close()

def wav_audio(seconds=1):
    buf=io.BytesIO()
    with wave.open(buf,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*int(16000*seconds))
    return base64.b64encode(buf.getvalue()).decode()

def test_voice_is_authenticated_bounded_and_uses_server_credential_without_retaining_audio(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path,siliconflow_api_key='test-speech-key')),headers={'X-Proclab-Request':'1'}) as c:
        body={'filename':'recording.wav','content_base64':wav_audio()}
        assert c.post('/api/audio/transcribe',json=body).status_code==401
        login(c)
        seen=[]
        class Reply:
            def raise_for_status(self):pass
            def json(self):return {'text':'查询各设备的批次总数'}
        class Client:
            def __init__(self,**kw):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def post(self,url,**kw):seen.append((url,kw));return Reply()
        monkeypatch.setattr('app.speech.httpx.Client',Client)
        result=c.post('/api/audio/transcribe',json=body);assert result.status_code==200,result.text
        assert result.json()['text']=='查询各设备的批次总数' and result.json()['audio_retained'] is False
        assert seen[0][1]['headers']['Authorization']=='Bearer test-speech-key'
        assert seen[0][1]['data']['model']=='FunAudioLLM/SenseVoiceSmall'
        assert c.post('/api/audio/transcribe',json={'filename':'recording.wav','content_base64':wav_audio(61)}).status_code==422
        assert c.post('/api/audio/transcribe',json={'filename':'recording.wav','content_base64':base64.b64encode(b'fake').decode()}).status_code==422
        assert not list(tmp_path.rglob('*.wav'))
        events=c.get('/api/audit').json();event=next(e for e in events if e['action']=='transcribe_audio')
        assert event['details']['audio_retained'] is False and 'text' not in event['details']


def test_word_text_is_extracted_without_ocr_and_can_be_reviewed(tmp_path):
    import zipfile
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>工艺资料核对：原文压力为2.0 MPa。</w:t></w:r></w:p></w:body></w:document>')
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path)),headers={'X-Proclab-Request':'1'}) as c:
        login(c)
        r=c.post('/api/documents/parse',json={'filename':'说明.docx','content_base64':base64.b64encode(buf.getvalue()).decode()})
        assert r.status_code==200,r.text
        assert r.json()['metadata']['provider']=='local_text'
        assert '2.0 MPa' in r.json()['text'] and r.json()['status']=='awaiting_review'


def test_generic_project_names_are_migrated_without_changing_scope_or_custom_names(tmp_path):
    from sqlalchemy import update
    from app.orchestration.repository import projects
    with _service(tmp_path) as service:
        repo=service.platform.repo;own=repo.default_project('admin');other=repo.default_project('operator')
        with repo.engine.begin() as cn:
            cn.execute(update(projects).where(projects.c.id==own).values(name='工业演示项目',stage='review'))
            cn.execute(update(projects).where(projects.c.id==other).values(name='我命名的材料试制项目'))
    with _service(tmp_path) as service:
        records={r['id']:r for r in service.platform.repo.list_projects('admin')}
        assert records[own]['name']=='星澜复材 · 热压成型工艺验证（模拟）'
        assert records[own]['stage']=='review' and records[own]['tenant_id']=='admin'
        assert records[other]['name']=='我命名的材料试制项目'
        assert service.platform.repo.default_project('admin')==own

def test_project_choices_default_to_self_and_exclude_disabled_accounts_without_deleting_history(tmp_path):
    from app.orchestration.repository import demo_project_name
    with TestClient(create_app(tmp_path,'fallback',config(tmp_path)),headers={'X-Proclab-Request':'1'}) as c:
        login(c);service=c.app.state.service;other=service.control.add_user('project_user','Project-user-test-2026')
        repo=service.platform.repo;own=repo.default_project('admin');foreign=repo.default_project(other['id'])
        choices=c.get('/api/projects').json()
        assert choices[0]['id']==own and any(p['id']==foreign for p in choices)
        assert all(p['name']!='工业演示项目' for p in choices)
        assert demo_project_name('admin')!=demo_project_name(other['id'])
        service.control.update_user(other['id'],active=False)
        assert foreign not in [p['id'] for p in c.get('/api/projects').json()]
        assert repo.scope('admin',foreign).project_id==foreign
