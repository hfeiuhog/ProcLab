import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI,HTTPException,Request,Query
from fastapi.responses import FileResponse,JSONResponse,Response,StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,ConfigDict,field_validator
from .config import Settings
from .engine import TaskService,TERMINAL
from .engineering import HeatingInput
from .design import HeatingDesignInput
from .reports import markdown_report
from .control import BudgetExceeded
from .harness import policy
from .documents import DocumentService,DocumentFailure

class TaskInput(BaseModel):
    question:str=Field(min_length=1,max_length=12000)
    batch_id:str=Field(default='',pattern=r'^[A-Za-z0-9-]{0,30}$')
    conversation_id:str|None=Field(default=None,pattern=r'^[a-f0-9-]{36}$')
    inject_timeout:str=Field(default='none',pattern=r'^(none|once|always)$')
    intent:str=Field(default='auto',pattern=r'^(auto|chat|batch|knowledge|simulation|optimization|extract|reasoning|analytics|composite)$')
    simulation_params:HeatingInput|None=None
    design_params:HeatingDesignInput|None=None
    project_id:str|None=Field(default=None,max_length=64)
    orchestration_mode:str=Field(default="auto",pattern=r"^(auto|superagent|legacy)$")
    analysis_mode:str=Field(default="fast",pattern=r"^(fast|thinking)$")
    remember_result:bool=False
    evidence_document_ids:list[str]=Field(default_factory=list,max_length=3)
class ConversationUpdateInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    title:str|None=Field(default=None,min_length=1,max_length=120)
    pinned:bool|None=None

    @field_validator('title')
    @classmethod
    def clean_title(cls,value):
        if value is not None and not value.strip():
            raise ValueError('分析名称不能为空')
        return value.strip() if value is not None else value

class DocumentInput(BaseModel):
    filename:str=Field(min_length=1,max_length=100)
    content_base64:str=Field(min_length=4,max_length=5_400_000)
    mode:str=Field(default='precision',pattern=r'^(precision|fallback|complex)$')
class KnowledgePublishInput(BaseModel):
    document_id:str=Field(min_length=1,max_length=36)
    title:str=Field(min_length=1,max_length=120)
class SpeechInput(BaseModel):
    filename:str=Field(min_length=1,max_length=80)
    content_base64:str=Field(min_length=4,max_length=5_600_000)
class ReviewInput(BaseModel):
    approved:bool
    note:str=Field(default='',max_length=1000)
class ProjectPolicyInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    stage:str|None=None
    member:str|None=None
    role:str|None=None
class ReplanInput(BaseModel):
    note:str=Field(min_length=4,max_length=500)
class MemoryInput(BaseModel):
    content:str=Field(min_length=4,max_length=1500)
class LoginInput(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=256)
class UserInput(BaseModel):
    username:str=Field(min_length=2,max_length=60,pattern=r'^[A-Za-z0-9_.-]+$')
    password:str=Field(min_length=8,max_length=256)
class RegistrationInput(UserInput):
    model_config=ConfigDict(extra='forbid')
class UserUpdateInput(BaseModel):
    username:str|None=Field(default=None,min_length=2,max_length=60,pattern=r'^[A-Za-z0-9_.-]+$')
    password:str|None=Field(default=None,min_length=8,max_length=256)
    active:bool|None=None
class RetryInput(BaseModel):
    design_params:HeatingDesignInput|None=None
    evidence_bundle_id:str|None=None
    batch_id:str|None=None
    evidence_document_ids:list[str]|None=Field(default=None,max_length=3)
class ModeInput(BaseModel):
    mode:str=Field(default='precision',pattern=r'^(precision|fallback|complex)$')
class CorrectionInput(BaseModel):
    text:str=Field(min_length=1,max_length=30000)
    note:str=Field(min_length=4,max_length=1000)
class MeasurementInput(BaseModel):
    row_id:str
    parameter:str
    value:float
    unit:str
class SupplementInput(BaseModel):
    corrections:list[MeasurementInput]=Field(min_length=1,max_length=24)
    source_note:str=Field(min_length=4,max_length=1000)
    document_id:str|None=None


def create_app(runtime_dir=None,graph_mode=None,settings=None):
    settings=(settings or Settings()).check()
    cookie='__Host-proclab_session' if settings.app_env=='production' else 'proclab_session'
    @asynccontextmanager
    async def lifespan(app):
        if settings.local_temp_dir:
            import os,tempfile
            Path(settings.local_temp_dir).mkdir(parents=True,exist_ok=True)
            os.environ['TEMP']=os.environ['TMP']=os.environ['TMPDIR']=settings.local_temp_dir
            tempfile.tempdir=settings.local_temp_dir
        app.state.service=TaskService(runtime_dir or settings.runtime_dir,mode=graph_mode or settings.graph_mode,llm_enabled=settings.use_llm,settings=settings)
        app.state.documents=DocumentService(settings,app.state.service.control)
        app.state.service.recover()
        yield
        app.state.service.close()
    app=FastAPI(title='Industrial Process Agent',version='3.0.0',lifespan=lifespan,
        docs_url='/docs' if settings.app_env!='production' else None,redoc_url=None,openapi_url='/openapi.json' if settings.app_env!='production' else None)
    static=Path(__file__).parent/'static'
    app.mount('/static',StaticFiles(directory=static),name='static')
    def principal(request):
        token=request.headers.get('Authorization','').removeprefix('Bearer ')
        if settings.api_token and secrets.compare_digest(token,settings.api_token):
            return {'id':'admin','username':settings.admin_username,'role':'admin','method':'service_token'}
        found=app.state.service.control.session(request.cookies.get(cookie,'')) if settings.auth_enabled else None
        if found: return {**found,'method':'session'}
        if not settings.auth_enabled and not settings.api_token:
            return {'id':'admin','username':'local','role':'admin','method':'development'}
        return None
    def actor(request):
        p=getattr(request.state,'principal',None) or principal(request)
        if not p: raise HTTPException(401,'请登录后使用')
        return p
    def owner(request): return actor(request)['id']
    def require(kind,ident,request):
        try: app.state.service.control.require(kind,ident,owner(request))
        except KeyError: raise HTTPException(404,'资源不存在')
    def admin(request):
        if actor(request)['role']!='admin': raise HTTPException(403,'需要管理员权限')
    def csrf(request):
        origin=request.headers.get('Origin')
        if request.headers.get('X-Proclab-Request')!='1': return False
        if origin and urlparse(origin).netloc!=request.headers.get('Host'): return False
        return True
    @app.middleware('http')
    async def authentication(request,call_next):
        if request.url.path.startswith('/api/') and not request.url.path.startswith('/api/auth/'):
            p=principal(request)
            if not p: return JSONResponse({'detail':'请登录后使用'},status_code=401)
            request.state.principal=p
            if p['method']=='session' and request.method not in ('GET','HEAD','OPTIONS') and not csrf(request):
                return JSONResponse({'detail':'请求来源校验失败'},status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        if request.url.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
        return response
    @app.exception_handler(PermissionError)
    async def permission_error(request,exc): return JSONResponse({"detail":str(exc)},status_code=403)
    @app.exception_handler(BudgetExceeded)
    async def quota_error(request,exc): return JSONResponse({'detail':str(exc)},status_code=429)
    @app.exception_handler(DocumentFailure)
    async def document_error(request,exc):
        return JSONResponse({'detail':exc.failure['message'],'document_id':exc.document_id,'status':'needs_repair','failure':exc.failure},status_code=422)
    @app.get('/')
    def index(): return FileResponse(static/'index.html')
    @app.get('/health')
    def health(): return app.state.service.health()
    @app.get('/ready')
    def ready():
        result=app.state.service.health()
        return JSONResponse(result,status_code=200 if result['ok'] else 503)
    @app.get('/api/auth/status')
    def auth_status(): return {'required':settings.auth_enabled,'registration':settings.auth_enabled and settings.registration_enabled,'model_keys_required':False}
    @app.get('/api/auth/me')
    def me(request:Request): return actor(request)
    def session_response(p,status_code=200):
        token=app.state.service.control.create_session(p)
        response=JSONResponse(p,status_code=status_code)
        response.set_cookie(cookie,token,max_age=settings.session_ttl_seconds,httponly=True,secure=settings.app_env=='production',samesite='lax',path='/')
        return response
    @app.post('/api/auth/login')
    def login(data:LoginInput,request:Request):
        if not settings.auth_enabled: raise HTTPException(409,'当前部署未启用账号登录')
        if not csrf(request): raise HTTPException(403,'请求来源校验失败')
        ip=request.headers.get('X-Real-IP') or (request.client.host if request.client else 'unknown')
        p=app.state.service.control.authenticate(data.username,data.password,ip)
        if not p: raise HTTPException(401,'账号或密码错误')
        return session_response(p)
    @app.post('/api/auth/logout')
    def logout(request:Request):
        if not csrf(request): raise HTTPException(403,'请求来源校验失败')
        token=request.cookies.get(cookie,'')
        if token: app.state.service.control.logout(token)
        response=JSONResponse({'logged_out':True})
        response.delete_cookie(cookie,path='/',secure=settings.app_env=='production',httponly=True,samesite='lax')
        return response
    def user_operation(fn):
        try:return fn()
        except KeyError:raise HTTPException(404,'账号不存在')
        except PermissionError as exc:raise HTTPException(403,str(exc))
        except ValueError as exc:raise HTTPException(422,str(exc))
    @app.post('/api/auth/register',status_code=201)
    def register(data:RegistrationInput,request:Request):
        if not settings.auth_enabled or not settings.registration_enabled:raise HTTPException(403,'当前部署未开放注册')
        if not csrf(request):raise HTTPException(403,'请求来源校验失败')
        ip=request.headers.get('X-Real-IP') or (request.client.host if request.client else 'unknown')
        p=user_operation(lambda:app.state.service.control.register(data.username,data.password,ip))
        return session_response(p,201)
    @app.get('/api/admin/users')
    def users(request:Request,q:str='',active:bool|None=None):
        admin(request)
        if len(q)>80:raise HTTPException(422,'查询过长')
        return app.state.service.control.list_users(q,active)
    @app.get('/api/admin/users/{ident}')
    def user_detail(ident:str,request:Request):
        admin(request);return user_operation(lambda:app.state.service.control.get_user(ident))
    @app.post('/api/admin/users',status_code=201)
    def add_user(data:UserInput,request:Request):
        admin(request)
        result=user_operation(lambda:app.state.service.control.add_user(data.username,data.password))
        app.state.service.control.audit(result['id'],'admin','create_user',result['id'],{})
        return result
    @app.patch('/api/admin/users/{ident}')
    def update_user(ident:str,data:UserUpdateInput,request:Request):
        admin(request)
        return user_operation(lambda:app.state.service.control.update_user(ident,**data.model_dump(exclude_none=True)))
    @app.delete('/api/admin/users/{ident}',status_code=204)
    def delete_user(ident:str,request:Request):
        admin(request);user_operation(lambda:app.state.service.control.delete_user(ident))
        return Response(status_code=204)
    @app.get('/api/conversations')
    def conversations(request:Request,q:str=Query(default='',max_length=200)):
        return app.state.service.store.list_conversations(app.state.service.control.ids('conversation',owner(request)),query=q)
    @app.post('/api/conversations',status_code=201)
    def create_conversation(request:Request):
        result=app.state.service.store.create_conversation()
        app.state.service.control.bind('conversation',result['id'],owner(request));return result
    @app.get('/api/conversations/{conversation_id}')
    def conversation(conversation_id:str,request:Request):
        require('conversation',conversation_id,request)
        result=app.state.service.store.conversation(conversation_id)
        if result is None: raise HTTPException(404,'会话不存在')
        result['tasks']=[]
        for state in app.state.service.store.list_tasks(conversation_id):
            try: result['tasks'].append(get_task(state['task_id'],request))
            except HTTPException as exc:
                if exc.status_code!=404: raise
        visible_ids={t['task_id'] for t in result['tasks']}
        result['messages']=[m for m in result.get('messages',[]) if m.get('task_id') in visible_ids]
        return result
    @app.patch('/api/conversations/{conversation_id}')
    def update_conversation(conversation_id:str,data:ConversationUpdateInput,request:Request):
        require('conversation',conversation_id,request)
        values=data.model_dump(exclude_none=True)
        if not values: raise HTTPException(422,'请填写名称或置顶状态')
        try: result=app.state.service.store.update_conversation(conversation_id,**values)
        except KeyError: raise HTTPException(404,'会话不存在')
        app.state.service.control.audit(app.state.service.control.owner('conversation',conversation_id),owner(request),'conversation_updated',conversation_id,values)
        return result
    @app.delete('/api/conversations/{conversation_id}',status_code=204)
    def delete_conversation(conversation_id:str,request:Request):
        require('conversation',conversation_id,request)
        try: app.state.service.store.update_conversation(conversation_id,remove=True)
        except KeyError: raise HTTPException(404,'会话不存在')
        app.state.service.control.audit(app.state.service.control.owner('conversation',conversation_id),owner(request),'conversation_deleted',conversation_id)
        return Response(status_code=204)
    @app.get('/api/batches')
    def batches():
        import csv
        from collections import Counter
        from .rag import DATA
        with (DATA/'batches.csv').open(encoding='utf-8',newline='') as f: counts=Counter(r['batch_id'] for r in csv.DictReader(f))
        return [{'batch_id':b,'row_count':n} for b,n in sorted(counts.items())]
    def task_view(state,request):
        return {**state,"permissions":app.state.service.platform.repo.task_permissions(owner(request),state)}
    def task_write(state,request):
        return app.state.service.platform.repo.scope(owner(request),state.get("scope",{}).get("project_id"),write=True)
    def handle_submit(task,background,request):
        try:
            return task_view((app.state.service.submit if background else app.state.service.create)(**task.model_dump(),owner_id=owner(request)),request)
        except BudgetExceeded: raise
        except KeyError: raise HTTPException(404,'会话或来源不存在')
        except ValueError as exc: raise HTTPException(422,str(exc))
        except RuntimeError: raise HTTPException(429,'任务队列已满，请稍后重试')
    @app.post('/api/tasks')
    def create_task(task:TaskInput,request:Request): return handle_submit(task,False,request)
    @app.post('/api/tasks/submit',status_code=202)
    def submit_task(task:TaskInput,request:Request): return handle_submit(task,True,request)
    @app.get('/api/tasks/{task_id}')
    def get_task(task_id:str,request:Request):
        require('task',task_id,request)
        state=app.state.service.get(task_id)
        if state is None: raise HTTPException(404,'任务不存在')
        if state.get("scope"):
            try:app.state.service.platform.repo.scope(owner(request),state["scope"]["project_id"])
            except KeyError:raise HTTPException(404,"项目不存在或访问已撤销")
        return task_view(state,request)
    @app.get('/api/tasks/{task_id}/events')
    async def events(task_id:str,request:Request):
        get_task(task_id,request)
        async def stream():
            previous=None
            for _ in range(1200):
                if await request.is_disconnected(): break
                # Recheck existing streams after account or project access is revoked.
                p=await asyncio.to_thread(principal,request)
                if not p or p["id"]!=owner(request):
                    yield 'event: done\ndata: {}\n\n';break
                try:
                    state=await asyncio.to_thread(get_task,task_id,request)
                except (HTTPException,PermissionError):
                    yield 'event: done\ndata: {}\n\n';break
                data=json.dumps(state,ensure_ascii=False)
                if data!=previous:
                    yield 'event: state\ndata: '+data+'\n\n'; previous=data
                else: yield ': heartbeat\n\n'
                if state['status'] in TERMINAL or state['status']=='pending_review':
                    yield 'event: done\ndata: {}\n\n';break
                await asyncio.sleep(.5)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
    @app.post('/api/tasks/{task_id}/review')
    def review_task(task_id:str,decision:ReviewInput,request:Request):
        get_task(task_id,request)
        try: return task_view(app.state.service.review(task_id,decision.approved,decision.note,owner(request)),request)
        except ValueError as exc: raise HTTPException(409,str(exc))
    @app.post('/api/tasks/{task_id}/retry',status_code=202)
    def retry_task(task_id:str,data:RetryInput,request:Request):
        get_task(task_id,request)
        try: return app.state.service.retry(task_id,owner(request),evidence_bundle_id=data.evidence_bundle_id,batch_id=data.batch_id,evidence_document_ids=data.evidence_document_ids,design_params=data.design_params.model_dump() if data.design_params else None)
        except ValueError as exc: raise HTTPException(409,str(exc))
    @app.post('/api/tasks/{task_id}/supplements',status_code=201)
    def supplement(task_id:str,data:SupplementInput,request:Request):
        state=get_task(task_id,request)
        task_write(state,request)
        try: return app.state.service.evidence.submit(state,[c.model_dump() for c in data.corrections],data.source_note,data.document_id,owner(request))
        except ValueError as exc: raise HTTPException(422,str(exc))
    def visible_supplements(request):
        result=[]
        for item in app.state.service.control.list('supplement',owner(request)):
            try: parent=get_task(item['parent_task_id'],request)
            except HTTPException as exc:
                if exc.status_code==404: continue
                raise
            result.append({**item,'permissions':parent['permissions']})
        return result
    @app.get('/api/supplements')
    def supplements(request:Request): return visible_supplements(request)
    @app.post('/api/supplements/{ident}/review')
    def review_supplement(ident:str,data:ReviewInput,request:Request):
        require('supplement',ident,request)
        if not data.note.strip(): raise HTTPException(422,'请填写审核说明')
        try:
            service=app.state.service
            item=service.control.get('supplement',ident,owner(request))
            task_write(get_task(item['parent_task_id'],request),request)
            result=service.evidence.approve(ident,owner(request),data.approved,data.note)
            if data.approved:
                try:
                    result['new_task']=service.retry(result['parent_task_id'],owner(request),evidence_bundle_id=ident)
                except (ValueError,RuntimeError) as exc:
                    result['launch_error']=str(exc)
                    service.control.put('supplement',result,result['owner_id'])
                    return result
                persisted={k:v for k,v in result.items() if k!='new_task'}
                persisted['new_task_id']=result['new_task']['task_id']
                service.control.put('supplement',persisted,result['owner_id'])
            return result
        except ValueError as exc: raise HTTPException(409,str(exc))
    @app.get('/api/tasks/{task_id}/report')
    def export_report(task_id:str,request:Request,format:str='markdown'):
        state=get_task(task_id,request)
        if not state.get('report'): raise HTTPException(409,'报告尚未生成')
        if format=='json': return Response(json.dumps(state,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="report-{task_id}.json"'})
        if format!='markdown': raise HTTPException(422,'format must be markdown/json')
        return Response(markdown_report(state),media_type='text/markdown',headers={'Content-Disposition':f'attachment; filename="report-{task_id}.md"'})
    @app.get('/api/knowledge')
    def knowledge(request:Request,scope:str=Query(default='company',pattern=r'^(company|personal)$')):
        from .rag import load_docs
        library=app.state.service.library
        versions=library.snapshot(owner(request))
        versions={k:v for k,v in versions.items() if k.startswith('private:')==(scope=='personal')}
        docs=(load_docs() if scope=='company' else [])+library.documents(versions,owner(request))
        return [{**d,'scope':d.get('scope','company')} for d in docs]
    @app.get('/api/knowledge/releases')
    def knowledge_releases(request:Request):
        return [{k:r[k] for k in ('id','title','status','document_version','created_at')} for r in app.state.service.library.releases()]
    @app.post('/api/knowledge/publish',status_code=201)
    def publish_knowledge(data:KnowledgePublishInput,request:Request):
        admin(request)
        try:
            r=app.state.service.library.publish(owner(request),data.document_id,data.title)
            return {k:r[k] for k in ('id','title','status','document_version','created_at')}
        except KeyError:raise HTTPException(404,'文档不存在')
        except ValueError as exc:raise HTTPException(422,str(exc))
    @app.get('/api/knowledge/submissions')
    def knowledge_submissions(request:Request):
        return app.state.service.library.submissions(owner(request))
    @app.post('/api/knowledge/submissions',status_code=201)
    def submit_knowledge(data:KnowledgePublishInput,request:Request):
        return user_operation(lambda:app.state.service.library.submit(owner(request),data.document_id,data.title))
    @app.get('/api/knowledge/submissions/{ident}')
    def knowledge_submission(ident:str,request:Request):
        return user_operation(lambda:app.state.service.library.submission(owner(request),ident))
    @app.post('/api/knowledge/submissions/{ident}/review')
    def review_knowledge_submission(ident:str,data:ReviewInput,request:Request):
        admin(request)
        return user_operation(lambda:app.state.service.library.review_submission(owner(request),ident,data.approved,data.note))
    @app.post('/api/knowledge/{ident}/withdraw')
    def withdraw_knowledge(ident:str,request:Request):
        admin(request)
        try:
            r=app.state.service.library.withdraw(owner(request),ident);return {'id':r['id'],'status':r['status']}
        except KeyError:raise HTTPException(404,'共享资料不存在')
    @app.post('/api/knowledge/reindex')
    def reindex(request:Request):
        admin(request)
        if not settings.milvus_uri: raise HTTPException(409,'当前使用本地检索')
        try: return app.state.service.knowledge.reindex()
        except Exception as exc: raise HTTPException(503,'知识索引失败：'+type(exc).__name__)
    @app.get('/api/projects')
    def projects_v3(request:Request):
        return app.state.service.platform.repo.list_projects(owner(request))
    @app.get('/api/projects/{ident}/members')
    def project_members_v3(ident:str,request:Request):
        admin(request)
        return user_operation(lambda:app.state.service.platform.repo.project_members(owner(request),ident))
    @app.patch('/api/projects/{ident}')
    def project_policy_v3(ident:str,data:ProjectPolicyInput,request:Request):
        admin(request)
        try:
            app.state.service.platform.repo.configure_project(owner(request),ident,**data.model_dump())
            return app.state.service.platform.repo.list_projects(owner(request))
        except KeyError:raise HTTPException(404,'项目或成员不存在')
        except ValueError as exc:raise HTTPException(422,str(exc))
    @app.get('/api/agents')
    def agents_v3():
        from .orchestration.registry import catalog
        return {'agents':catalog(),'topology_version':'industrial-dag-1.0.0','runtime':'single_process_durable_calls','max_parallel_nodes_per_execution':1}
    @app.get('/api/analytics/semantic-model')
    def semantic_v3():
        from .analytics.semantic import semantic_model
        return semantic_model()
    @app.get('/api/analytics/status')
    def warehouse_status_v3(request:Request,project_id:str|None=None):
        try:
            platform=app.state.service.platform
            scope=platform.repo.scope(owner(request),project_id).model_dump()
            return {'scope':scope,'dataset':platform.warehouse.ensure_dataset(scope),'warehouse':platform.health()}
        except KeyError:raise HTTPException(404,'项目不存在')
    @app.get('/api/tasks/{task_id}/execution')
    def execution_v3(task_id:str,request:Request):
        state=get_task(task_id,request)
        if state.get('orchestration')!='superagent':return {'execution_id':task_id,'mode':'legacy','agent_calls':[]}
        return app.state.service.platform.detail(state)
    @app.post('/api/tasks/{task_id}/replan',status_code=202)
    def replan_v3(task_id:str,data:ReplanInput,request:Request):
        get_task(task_id,request)
        try:return app.state.service.replan(task_id,owner(request),data.note)
        except ValueError as exc:raise HTTPException(409,str(exc))
        except RuntimeError as exc:raise HTTPException(429,str(exc))
    @app.get('/api/tasks/{task_id}/results')
    def results_v3(task_id:str,request:Request):
        state=get_task(task_id,request)
        root=state.get("root_task_id") or task_id
        return [r for r in app.state.service.platform.repo.list("result_revisions",actor=state.get("owner_id")) if r["payload"].get("root_task_id")==root]
    @app.post('/api/admin/analytics/replay')
    def replay_v3(request:Request):
        admin(request)
        return app.state.service.platform.replay_history()
    @app.post('/api/admin/analytics/sync')
    def sync_v3(request:Request):
        admin(request)
        return app.state.service.platform.drain_outbox()
    @app.get('/api/capabilities')
    def capabilities():
        return {'agent':settings.openai_model,'extract':settings.high_risk_extract_model,'reasoning':settings.rule_reasoning_model,
            'embedding':settings.embedding_model,'reranker':settings.reranker_model,'sparse':'BM25 lexical (not BGE sparse)',
            'harness':policy(settings),'speech':{'enabled':bool(settings.speech_enabled and settings.siliconflow_api_key),'max_bytes':4_000_000,'max_seconds':60,'retained':False},'documents':{'enabled':settings.document_enabled,'max_bytes':settings.document_max_bytes,'max_pages':2,'daily_limit':settings.document_daily_limit,'precision_model':settings.vision_precision_model,'fallback_model':settings.vision_fallback_model,'complex_model':settings.complex_vision_model}}
    def parse_result(fn):
        try: return fn()
        except DocumentFailure: raise
        except KeyError: raise HTTPException(404,'文档不存在')
        except ValueError as exc: raise HTTPException(422,str(exc))
        except RuntimeError: raise HTTPException(429,'解析服务繁忙、额度用完或未配置')
    @app.post('/api/audio/transcribe')
    def transcribe(data:SpeechInput,request:Request):
        from .speech import transcribe_audio
        try:return transcribe_audio(settings,app.state.service.control,owner(request),data.filename,data.content_base64)
        except ValueError as exc:raise HTTPException(422,str(exc))
        except BudgetExceeded:raise
        except Exception:raise HTTPException(503,'语音识别暂不可用，请稍后重试或直接输入文字')
    @app.post('/api/documents/parse')
    def parse_document(data:DocumentInput,request:Request):
        return parse_result(lambda:app.state.documents.parse(**data.model_dump(),owner_id=owner(request)))
    @app.get('/api/engineering/tools')
    def engineering_tools(request:Request):
        owner(request)
        from importlib.metadata import version,PackageNotFoundError
        try:solver_version=version("scipy");available=True
        except PackageNotFoundError:solver_version=None;available=False
        return {"tool":"scipy.integrate.solve_ivp","inverse_tool":"scipy.optimize.brentq","version":solver_version,"available":available,
                "adapter":"isolated_fixed_python_worker","model":"first_order_lumped_heating",
                "arbitrary_code":False,"calibrated_device":False,"max_trials":3}
    @app.get('/api/documents')
    def documents(request:Request):
        return app.state.service.control.list('document',owner(request))
    @app.get('/api/documents/{ident}')
    def document(ident:str,request:Request):
        require('document',ident,request)
        return app.state.service.control.get('document',ident,owner(request))
    @app.post('/api/documents/{ident}/retry')
    def retry_document(ident:str,data:ModeInput,request:Request):
        require('document',ident,request)
        return parse_result(lambda:app.state.documents.retry(ident,owner(request),data.mode))
    @app.post('/api/documents/{ident}/correct')
    def correct_document(ident:str,data:CorrectionInput,request:Request):
        require('document',ident,request)
        return parse_result(lambda:app.state.documents.correct(ident,owner(request),data.text,data.note))
    @app.post('/api/documents/{ident}/review')
    def review_document(ident:str,data:ReviewInput,request:Request):
        require('document',ident,request)
        return parse_result(lambda:app.state.documents.review(ident,owner(request),data.approved,data.note))
    @app.get('/api/reviews')
    def reviews(request:Request):
        ident=owner(request);control=app.state.service.control
        tasks=app.state.service.store.list_tasks(statuses=['pending_review'])
        visible=[]
        for t in tasks:
            if t.get('owner_id','admin')!=ident: continue
            try: visible.append(get_task(t['task_id'],request))
            except HTTPException as exc:
                if exc.status_code!=404: raise
        tasks=visible
        return {'tasks':tasks,'documents':control.list('document',ident),'supplements':visible_supplements(request),'role':actor(request)['role']}
    @app.get('/api/audit')
    def audit(request:Request):
        admin(request)
        return app.state.service.control.audit_list(owner(request))
    @app.get('/api/memories')
    def memories(request:Request):
        return app.state.service.store.list_memories(app.state.service.control.ids('memory',owner(request)))
    @app.post('/api/memories',status_code=201)
    def remember(item:MemoryInput,request:Request):
        result=app.state.service.store.remember(item.content)
        app.state.service.control.bind('memory',result['id'],owner(request));return result
    @app.post('/api/tasks/{task_id}/remember',status_code=201)
    def remember_result(task_id:str,request:Request):
        get_task(task_id,request)
        try: return app.state.service.save_result_memory(task_id)
        except ValueError as exc: raise HTTPException(409,str(exc))
    @app.delete('/api/memories/{ident}',status_code=204)
    def forget(ident:str,request:Request):
        require('memory',ident,request)
        app.state.service.store.forget(ident);return Response(status_code=204)
    return app
app=create_app()
