"""Accounts, revocable sessions, resource ownership, evidence versions and audit."""
import base64
import hashlib
import hmac
import json
import secrets
import string
import re
import threading
import time
import uuid
from datetime import datetime,timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import Table,Column,String,Integer,BigInteger,JSON,MetaData,select,insert,update,delete,func

meta=MetaData()
users=Table('users_v22',meta,Column('id',String(80),primary_key=True),Column('username',String(80),unique=True),Column('password_hash',String(300)),Column('role',String(20)),Column('active',Integer),Column('created_at',String(40)))
sessions=Table('sessions_v22',meta,Column('token_hash',String(64),primary_key=True),Column('user_id',String(80),index=True),Column('expires',BigInteger))
owners=Table('owners_v22',meta,Column('kind',String(24),primary_key=True),Column('id',String(120),primary_key=True),Column('owner',String(80),index=True))
objects=Table('evidence_objects_v22',meta,Column('id',String(36),primary_key=True),Column('kind',String(24),index=True),Column('owner',String(80),index=True),Column('status',String(32),index=True),Column('state',JSON),Column('updated_at',String(40)))
counters=Table('budget_counters_v22',meta,Column('id',String(180),primary_key=True),Column('used',Integer))
audits=Table('audit_events_v22',meta,Column('id',String(36),primary_key=True),Column('owner',String(80),index=True),Column('actor',String(80)),Column('action',String(64)),Column('target',String(120)),Column('details',JSON),Column('created_at',String(40)))

bootstrap=Table('account_bootstrap_v23',meta,Column('id',String(24),primary_key=True),Column('user_id',String(80)),Column('created_at',String(40)))

def now(): return datetime.now(timezone.utc).isoformat()
def password_hash(password,salt=None):
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,600000)
    return 'pbkdf2_sha256:600000:'+base64.urlsafe_b64encode(salt).decode()+':'+base64.urlsafe_b64encode(digest).decode()
def password_matches(password,encoded):
    try:
        method,iterations,salt,digest=encoded.split(':')
        if method!='pbkdf2_sha256' or int(iterations)!=600000: return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),base64.urlsafe_b64decode(salt),int(iterations))
        return hmac.compare_digest(actual,base64.urlsafe_b64decode(digest))
    except (ValueError,TypeError): return False

def validate_password(password,role='user'):
    if role=='admin':
        if not 12<=len(password)<=256:raise ValueError('管理员密码需12至256位')
        return
    if not 8<=len(password)<=256:raise ValueError('密码需8至256位')
    if (any(c.isspace() for c in password) or
        not all((any('a'<=c<='z' for c in password),
                 any('A'<=c<='Z' for c in password),
                 any('0'<=c<='9' for c in password),
                 any(c in string.punctuation for c in password)))):
        raise ValueError('密码需包含大写字母、小写字母、数字和特殊字符，且不能包含空白')

PRIVATE_KINDS={'document','task','conversation','supplement','memory'}

class BudgetExceeded(RuntimeError): pass

class ControlPlane:
    def __init__(self,engine,settings):
        self.engine,self.settings=engine,settings
        self.lock=threading.RLock()
        meta.create_all(engine)
        if settings.auth_enabled:
            self.seed(settings.admin_username,settings.admin_password_hash,'admin','admin')
            if settings.hr_password_hash:
                self.seed(settings.hr_username,settings.hr_password_hash,'demo',None)
    def seed(self,username,encoded,role,ident):
        # Seed once; DB changes survive restart, including deletion of the HR.
        if not username or not encoded:return
        key='seed:'+role
        with self.lock,self.engine.begin() as cn:
            if cn.execute(select(bootstrap.c.id).where(bootstrap.c.id==key)).first():return
            stmt=select(users).where(users.c.id==ident) if ident else select(users).where(users.c.username==username)
            row=cn.execute(stmt).mappings().first()
            if row and row['role']!=role:raise ValueError('Seed account role changed')
            user_id=row['id'] if row else ident or str(uuid.uuid4())
            if not row:cn.execute(insert(users).values(id=user_id,username=username,password_hash=encoded,role=role,active=1,created_at=now()))
            cn.execute(insert(bootstrap).values(id=key,user_id=user_id,created_at=now()))

    @staticmethod
    def principal(row): return {'id':row['id'],'username':row['username'],'role':row['role']}
    def authenticate(self,username,password,ip):
        bucket=str(int(time.time())//600)
        self.consume('login:'+hashlib.sha256(ip.encode()).hexdigest()[:24]+':'+bucket,12)
        with self.engine.connect() as cn:
            row=cn.execute(select(users).where(users.c.username==username)).mappings().first()
        encoded=row['password_hash'] if row else self.settings.admin_password_hash
        ok=password_matches(password,encoded)
        if not row or not row['active'] or not ok: return None
        self.audit(row['id'],row['id'],'login','account',{})
        return self.principal(row)
    def create_session(self,principal):
        token=secrets.token_urlsafe(32)
        with self.engine.begin() as cn:
            cn.execute(insert(sessions).values(token_hash=hashlib.sha256(token.encode()).hexdigest(),user_id=principal['id'],expires=int(time.time())+self.settings.session_ttl_seconds))
        return token
    def session(self,token):
        if not token: return None
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.engine.connect() as cn:
            row=cn.execute(select(users).join(sessions,sessions.c.user_id==users.c.id).where((sessions.c.token_hash==digest)&(sessions.c.expires>int(time.time()))&(users.c.active==1))).mappings().first()
        return self.principal(row) if row else None
    def logout(self,token):
        with self.engine.begin() as cn:
            cn.execute(delete(sessions).where(sessions.c.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    @staticmethod
    def public_user(row):return {k:row[k] for k in ('id','username','role','active','created_at')}
    def get_user(self,ident):
        with self.engine.connect() as cn:row=cn.execute(select(users).where(users.c.id==ident)).mappings().first()
        if not row:raise KeyError('账号不存在')
        return self.public_user(row)
    def list_users(self,q='',active=None):
        stmt=select(users).order_by(users.c.created_at,users.c.username).limit(200)
        if q:stmt=stmt.where(users.c.username.contains(q,autoescape=True))
        if active is not None:stmt=stmt.where(users.c.active==int(active))
        with self.engine.connect() as cn:return [self.public_user(r) for r in cn.execute(stmt).mappings()]
    @staticmethod
    def check_username(username):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{2,60}',username):raise ValueError('账号需2至60位字母、数字、下划线、点或短横线')
    def add_user(self,username,password):
        self.check_username(username)
        validate_password(password)
        ident=str(uuid.uuid4())
        try:
            with self.lock,self.engine.begin() as cn:
                if cn.execute(select(users.c.id).where(func.lower(users.c.username)==username.lower())).first():raise ValueError('账号已存在')
                cn.execute(insert(users).values(id=ident,username=username,password_hash=password_hash(password),role='user',active=1,created_at=now()))
        except IntegrityError:raise ValueError('账号已存在') from None
        return self.get_user(ident)
    def register(self,username,password,ip):
        bucket=str(int(time.time())//3600)
        self.consume('register:'+hashlib.sha256(ip.encode()).hexdigest()[:24]+':'+bucket,5)
        if username.lower() in ('admin',self.settings.admin_username.lower()):raise ValueError('账号已存在')
        user=self.add_user(username,password)
        self.audit(user['id'],user['id'],'register','account',{'role':'user'})
        return self.principal(user)
    def update_user(self,ident,username=None,password=None,active=None):
        changes={}
        if username is not None:self.check_username(username);changes['username']=username
        if password is not None:
            changes['password_hash']=password_hash(password)
        if active is not None:changes['active']=int(active)
        if not changes:raise ValueError('请至少修改一项')
        try:
            with self.lock,self.engine.begin() as cn:
                row=cn.execute(select(users).where(users.c.id==ident).with_for_update()).mappings().first()
                if not row:raise KeyError('账号不存在')
                if password is not None:validate_password(password,row['role'])
                if row['role']=='admin' and active is False:raise PermissionError('不能封禁系统管理员')
                cn.execute(update(users).where(users.c.id==ident).values(**changes))
                revoke=password is not None or username is not None or active is False
                if revoke:cn.execute(delete(sessions).where(sessions.c.user_id==ident))
        except IntegrityError:raise ValueError('账号已存在') from None
        self.audit(ident,'admin','update_user',ident,{'username_changed':username is not None,'password_reset':password is not None,'active':active,'sessions_revoked':revoke})
        return {**self.get_user(ident),'sessions_revoked':revoke}
    def delete_user(self,ident):
        with self.lock,self.engine.begin() as cn:
            row=cn.execute(select(users).where(users.c.id==ident).with_for_update()).mappings().first()
            if not row:raise KeyError('账号不存在')
            if row['role']=='admin':raise PermissionError('不能删除系统管理员')
            cn.execute(delete(sessions).where(sessions.c.user_id==ident))
            cn.execute(delete(users).where(users.c.id==ident))
        # Preserve evidence and audit. Recreated usernames receive a fresh ID.
        self.audit(ident,'admin','delete_user',ident,{'analysis_records_retained':True})

    def bind(self,kind,ident,owner):
        with self.lock,self.engine.begin() as cn:
            row=cn.execute(select(owners.c.owner).where((owners.c.kind==kind)&(owners.c.id==ident))).first()
            if row and row[0]!=owner: raise PermissionError('Resource owner mismatch')
            if not row: cn.execute(insert(owners).values(kind=kind,id=ident,owner=owner))
    def owner(self,kind,ident):
        with self.engine.connect() as cn:
            row=cn.execute(select(owners.c.owner).where((owners.c.kind==kind)&(owners.c.id==ident))).first()
        return row[0] if row else 'admin'
    def require(self,kind,ident,actor):
        if self.owner(kind,ident)!=actor and (actor!='admin' or kind in PRIVATE_KINDS):raise KeyError('资源不存在')
    def ids(self,kind,owner):
        if owner=='admin':
            if kind not in PRIVATE_KINDS:return None
            from .store import conversations,memories,tasks
            table={'conversation':conversations,'memory':memories,'task':tasks}.get(kind)
            if table is not None:
                stmt=select(table.c.id).select_from(table.outerjoin(owners,(owners.c.kind==kind)&(owners.c.id==table.c.id))).where((owners.c.owner==owner)|(owners.c.owner.is_(None)))
                with self.engine.connect() as cn:return [r[0] for r in cn.execute(stmt)]
        with self.engine.connect() as cn:
            return [r[0] for r in cn.execute(select(owners.c.id).where((owners.c.kind==kind)&(owners.c.owner==owner)))]
    def consume(self,key,limit,units=1):
        if limit<=0: raise BudgetExceeded('额度已用完')
        with self.lock,self.engine.begin() as cn:
            row=cn.execute(select(counters.c.used).where(counters.c.id==key).with_for_update()).first()
            used=row[0] if row else 0
            if used+units>limit: raise BudgetExceeded('额度已用完，请稍后再试或联系管理员')
            if row: cn.execute(update(counters).where(counters.c.id==key).values(used=used+units))
            else: cn.execute(insert(counters).values(id=key,used=units))
    def task_quota(self,actor):
        if actor=='admin': return
        today=now()[:10]
        limits=[('task-global:'+today,self.settings.demo_global_daily_tasks),('task-user:'+actor+':'+today,self.settings.demo_daily_tasks)]
        with self.lock,self.engine.begin() as cn:
            values=[]
            for key,limit in limits:
                row=cn.execute(select(counters.c.used).where(counters.c.id==key).with_for_update()).first()
                used=row[0] if row else 0
                if used>=limit: raise BudgetExceeded('今日分析额度已用完，请联系管理员')
                values.append((key,used,row is not None))
            for key,used,exists in values:
                if exists: cn.execute(update(counters).where(counters.c.id==key).values(used=used+1))
                else: cn.execute(insert(counters).values(id=key,used=1))
    def audit(self,owner,actor,action,target,details=None):
        # Only selected business metadata is recorded; no model keys, passwords or headers.
        with self.engine.begin() as cn:
            cn.execute(insert(audits).values(id=str(uuid.uuid4()),owner=owner,actor=actor,action=action,target=target,details=details or {},created_at=now()))
    def audit_list(self,actor):
        if actor!='admin':raise PermissionError('只有管理员可以查看审计记录')
        stmt=select(audits).order_by(audits.c.created_at.desc()).limit(100)
        with self.engine.connect() as cn:rows=[dict(r) for r in cn.execute(stmt).mappings()]
        safe={'version','attempt','mode','category','validation','repair_version','password_reset','username_changed','active','sessions_revoked','role','analysis_records_retained','audio_retained'}
        for row in rows:
            if row['owner']!='admin':row['details']={k:v for k,v in row['details'].items() if k in safe}
        return rows
    def put(self,kind,state,owner):
        state={**state,'owner_id':owner}
        with self.lock,self.engine.begin() as cn:
            existing=cn.execute(select(objects).where(objects.c.id==state['id']).with_for_update()).mappings().first()
            if existing and existing['owner']!=owner: raise PermissionError('Evidence owner mismatch')
            values=dict(kind=kind,owner=owner,status=state['status'],state=state,updated_at=now())
            if existing: cn.execute(update(objects).where(objects.c.id==state['id']).values(**values))
            else: cn.execute(insert(objects).values(id=state['id'],**values))
        self.bind(kind,state['id'],owner)
        return state
    def get(self,kind,ident,actor='admin'):
        self.require(kind,ident,actor)
        with self.engine.connect() as cn:
            row=cn.execute(select(objects.c.state).where((objects.c.id==ident)&(objects.c.kind==kind))).first()
        if not row: raise KeyError('证据不存在')
        return row[0]
    def list(self,kind,actor):
        stmt=select(objects.c.state).where(objects.c.kind==kind).order_by(objects.c.updated_at.desc()).limit(100)
        if actor!='admin' or kind in PRIVATE_KINDS:stmt=stmt.where(objects.c.owner==actor)
        with self.engine.connect() as cn: return [r[0] for r in cn.execute(stmt)]
