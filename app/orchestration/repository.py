"""Additive v3 schema; existing v2 tasks and account data remain compatible."""
import threading
import uuid
from sqlalchemy import MetaData, Table, Column, String, Integer, JSON, select, insert, update, case
from ..store import tasks, now
from .contracts import Scope, digest

metadata = MetaData()
projects = Table("sa_projects", metadata, Column("id", String(64), primary_key=True),
    Column("tenant_id", String(80), nullable=False), Column("name", String(120)),
    Column("factory_id", String(64)), Column("stage", String(24)), Column("created_by", String(80)))
members = Table("sa_project_members", metadata, Column("project_id", String(64), primary_key=True),
    Column("actor_id", String(80), primary_key=True), Column("role", String(24)))


def record_table(name):
    return Table(name, metadata, Column("id", String(100), primary_key=True),
        Column("execution_id", String(36), index=True), Column("owner_id", String(80), index=True),
        Column("project_id", String(64), index=True), Column("status", String(32), index=True),
        Column("payload", JSON, nullable=False), Column("created_at", String(40)), Column("updated_at", String(40)))


TABLES = {kind: record_table("sa_" + kind) for kind in (
    "executions", "plan_versions", "agent_calls", "tool_calls", "handoffs", "evidence",
    "harness_runs", "result_revisions", "outbox", "query_snapshots")}


def demo_project_name(actor):
    if actor=='admin':return '星澜复材 · 热压成型工艺验证（模拟）'
    orgs=['青屿材料','云杉复材','澄川新材','远辰制造','江澜材料','知行复材','沐川新材','松岳制造']
    value=int(digest(actor)[:12],16)
    return f'{orgs[value%len(orgs)]} · 热压工艺验证 {value%900+100}（模拟）'

class Repository:
    def __init__(self, store, control):
        self.store, self.engine, self.control = store, store.engine, control
        self.lock = threading.RLock()
        metadata.create_all(self.engine)
        # Rename only the original generic seed labels; preserve custom names and scope IDs.
        with self.engine.begin() as cn:
            for row in cn.execute(select(projects.c.id,projects.c.created_by).where(projects.c.name=='工业演示项目')).mappings():
                cn.execute(update(projects).where(projects.c.id==row['id']).values(name=demo_project_name(row['created_by'])))

    def assert_actor(self, actor):
        if self.control.settings.auth_enabled:
            user = self.control.get_user(actor)
            if not user.get("active"):
                raise PermissionError("账号已停用")

    def default_project(self, actor):
        ident = "demo-" + digest(actor)[:24]
        with self.lock, self.engine.begin() as cn:
            if not cn.execute(select(projects.c.id).where(projects.c.id == ident)).first():
                cn.execute(insert(projects).values(id=ident, tenant_id=actor, name=demo_project_name(actor), factory_id="demo-factory", stage="analysis", created_by=actor))
                cn.execute(insert(members).values(project_id=ident, actor_id=actor, role="owner"))
        return ident

    def _permissions(self, actor, project, membership):
        role = "admin" if actor == "admin" else membership["role"] if membership else "revoked"
        active_owner = True
        if self.control.settings.auth_enabled:
            try: active_owner = self.control.get_user(project["created_by"])["active"]
            except KeyError: active_owner = False
        return {"role": role,
                "analyze": bool(active_owner and project["stage"] == "analysis" and role in ("admin", "owner", "analyst")),
                "review": bool(active_owner and project["stage"] in ("analysis", "review") and role in ("admin", "owner", "reviewer"))}

    def scope(self, actor, project_id=None, write=False, review=False):
        self.assert_actor(actor)
        ident = project_id or self.default_project(actor)
        with self.engine.connect() as cn:
            p = cn.execute(select(projects).where(projects.c.id == ident)).mappings().first()
            m = cn.execute(select(members).where((members.c.project_id == ident) & (members.c.actor_id == actor))).mappings().first()
        if not p or ((not m or m["role"] == "revoked") and actor != "admin"):
            raise KeyError("项目不存在或无访问权限")
        permissions = self._permissions(actor, p, m)
        if write and not permissions["analyze"]:
            raise PermissionError("当前项目阶段或角色不允许分析、补证或重规划")
        if review and not permissions["review"]:
            raise PermissionError("当前项目阶段或角色不允许复核")
        return Scope(actor_id=actor, tenant_id=p["tenant_id"], project_id=ident,
                     factory_id=p["factory_id"], stage=p["stage"])

    def task_permissions(self, actor, state):
        ident = state.get("scope", {}).get("project_id")
        if not ident:
            ident = self.default_project(actor)
        try:
            self.scope(actor, ident)
        except (KeyError, PermissionError):
            return {"analyze": False, "review": False}
        with self.engine.connect() as cn:
            p = cn.execute(select(projects).where(projects.c.id == ident)).mappings().one()
            m = cn.execute(select(members).where((members.c.project_id == ident) & (members.c.actor_id == actor))).mappings().first()
        return self._permissions(actor, p, m)

    def list_projects(self, actor):
        self.assert_actor(actor)
        default=self.default_project(actor)
        stmt = select(projects)
        if actor=='admin' and self.control.settings.auth_enabled:
            from ..control import users
            stmt=stmt.where(projects.c.created_by.in_(select(users.c.id).where(users.c.active==1)))
        if actor != "admin":
            stmt = stmt.join(members, members.c.project_id == projects.c.id).where((members.c.actor_id == actor) & (members.c.role != "revoked"))
        with self.engine.connect() as cn:
            result = []
            for row in cn.execute(stmt.order_by(case((projects.c.id==default,0),else_=1),projects.c.name)).mappings():
                m = cn.execute(select(members).where((members.c.project_id == row["id"]) & (members.c.actor_id == actor))).mappings().first()
                result.append({**dict(row), "permissions": self._permissions(actor, row, m)})
            return result

    def project_members(self, actor, project_id):
        if actor != "admin": raise PermissionError("只有管理员可以查看项目成员权限")
        self.scope(actor, project_id)
        with self.engine.connect() as cn:
            rows = list(cn.execute(select(members).where(members.c.project_id == project_id)).mappings())
        result = []
        for row in rows:
            try:
                user = self.control.get_user(row["actor_id"])
                result.append({"id": user["id"], "username": user["username"], "active": user["active"], "role": row["role"]})
            except KeyError:
                result.append({"id": row["actor_id"], "username": "已删除账号", "active": False, "role": row["role"]})
        return result

    def configure_project(self, actor, project_id, stage=None, member=None, role=None):
        if actor != "admin": raise PermissionError("只有管理员可以修改项目阶段和成员权限")
        if not stage and not member: raise ValueError("请选择项目阶段或成员权限")
        if bool(member) != bool(role): raise ValueError("成员与角色必须同时提供")
        self.scope(actor, project_id)
        with self.lock, self.engine.begin() as cn:
            p = cn.execute(select(projects).where(projects.c.id == project_id)).mappings().one()
            if stage:
                if stage not in ("analysis", "review", "archived"): raise ValueError("无效项目阶段")
                cn.execute(update(projects).where(projects.c.id == project_id).values(stage=stage))
            if member:
                if role not in ("analyst", "reviewer", "viewer", "revoked"): raise ValueError("无效项目角色")
                if member == p["created_by"]: raise ValueError("不能修改项目负责人身份")
                user = self.control.get_user(member)
                if role != "revoked" and not user["active"]: raise ValueError("不能给已停用账号授予项目权限")
                exists = cn.execute(select(members).where((members.c.project_id == project_id) & (members.c.actor_id == member))).first()
                values = dict(project_id=project_id, actor_id=member, role=role)
                if exists: cn.execute(update(members).where((members.c.project_id == project_id) & (members.c.actor_id == member)).values(role=role))
                else: cn.execute(insert(members).values(**values))
        self.control.audit(p["tenant_id"], actor, "project_policy_changed", project_id, {"stage":stage, "member":member, "role":role})

    def put(self, kind, ident, payload, state, status="recorded", immutable=False, cn=None):
        table = TABLES[kind]
        scope = state.get("scope", {})
        values = dict(execution_id=state["task_id"], owner_id=state.get("owner_id", "admin"),
            project_id=scope.get("project_id", ""), status=status, payload=payload, updated_at=now())
        def write(conn):
            old = conn.execute(select(table.c.payload).where(table.c.id == ident)).first()
            if old:
                if immutable:
                    if digest(old[0]) != digest(payload): raise ValueError("冻结版本不可覆盖")
                    return
                conn.execute(update(table).where(table.c.id == ident).values(**values))
            else: conn.execute(insert(table).values(id=ident, created_at=now(), **values))
        if cn is not None: write(cn)
        else:
            with self.lock, self.engine.begin() as conn: write(conn)
        return ident

    def get(self, kind, ident):
        table = TABLES[kind]
        with self.engine.connect() as cn:
            r = cn.execute(select(table.c.payload).where(table.c.id == ident)).first()
        return r[0] if r else None

    def list(self, kind, task_id=None, actor=None, limit=200):
        table = TABLES[kind]
        stmt = select(table).order_by(table.c.created_at).limit(limit)
        if task_id: stmt = stmt.where(table.c.execution_id == task_id)
        if actor and actor != "admin": stmt = stmt.where(table.c.owner_id == actor)
        with self.engine.connect() as cn:
            return [dict(r) for r in cn.execute(stmt).mappings()]

    def checkpoint(self, state):
        self.put("executions", state["task_id"], {"status": state["status"], "scope":state["scope"],
            "plan_version":state.get("plan_version"), "step_states":state.get("step_states",{}),
            "profile":state.get("project_profile",{}), "runtime":"single_process_durable_calls"}, state, state["status"])
        self.store.save(state)

    def publish(self, state):
        if not state.get("report"): return
        self.scope(state["owner_id"], state["scope"]["project_id"])
        revision_id = state["task_id"] + ":" + state["status"]
        if self.get("result_revisions", revision_id): return
        revision = {"id":revision_id, "task_id":state["task_id"], "root_task_id":state.get("root_task_id") or state["task_id"],
            "parent_task_id":state.get("parent_task_id"), "version":state.get("repair_version",0),
            "publication":"rejected" if state["status"]=="rejected" else "limited" if state.get("review_reason") else "published",
            "verdict":state.get("business_verdict","indeterminate"), "plan_version":state.get("plan_version"),
            "harness_id":state.get("harness_id"), "evidence_ids":state.get("evidence_ids",[]),
            "report_sha256":digest(state["report"]), "report":state["report"], "created_at":now()}
        state["result_revision"] = {k:v for k,v in revision.items() if k!="report"}
        eid = digest([revision_id,"result_published"])
        event = {"id":eid,"kind":"result_published","scope":state["scope"],"revision":revision,
            "call_count":len(self.list("agent_calls",state["task_id"])),"created_at":now()}
        with self.lock, self.engine.begin() as cn:
            self.put("result_revisions",revision_id,revision,state,revision["publication"],True,cn)
            self.put("outbox",eid,event,state,"pending",True,cn)
            cn.execute(update(tasks).where(tasks.c.id==state["task_id"]).values(state=state,status=state["status"],updated_at=now()))

    def pending_events(self):
        table=TABLES["outbox"]
        with self.engine.connect() as cn:
            return [dict(r) for r in cn.execute(select(table).where(table.c.status=="pending").limit(100)).mappings()]

    def acknowledge(self, ident):
        table=TABLES["outbox"]
        with self.engine.begin() as cn:
            cn.execute(update(table).where(table.c.id==ident).values(status="delivered",updated_at=now()))

    def historical_events(self):
        table=TABLES["outbox"];cursor=""
        while True:
            with self.engine.connect() as cn:
                batch=[dict(r) for r in cn.execute(select(table).where(table.c.id>cursor).order_by(table.c.id).limit(200)).mappings()]
            if not batch:return
            for row in batch:yield row["payload"]
            cursor=batch[-1]["id"]
