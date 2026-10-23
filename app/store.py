"""SQL source of truth: MySQL on ECS, SQLite for zero-config local development."""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import (JSON, Column, Integer, LargeBinary, MetaData, String, Table, Text,
                        create_engine, delete, insert, select, update, func, or_)

metadata = MetaData()
tasks = Table("tasks_v2", metadata,
    Column("id", String(36), primary_key=True), Column("conversation_id", String(36), index=True),
    Column("status", String(32), index=True), Column("state", JSON, nullable=False), Column("updated_at", String(40)))
conversations = Table("conversations", metadata,
    Column("id", String(36), primary_key=True), Column("title", String(120)),
    Column("created_at", String(40)), Column("updated_at", String(40)))
# Additive table: old MySQL/SQLite conversation schemas remain compatible.
conversation_settings = Table("conversation_settings_v3", metadata,
    Column("conversation_id", String(36), primary_key=True),
    Column("pinned", Integer, nullable=False, default=0),
    Column("custom_title", Integer, nullable=False, default=0),
    Column("deleted_at", String(40)))
messages = Table("messages", metadata,
    Column("id", String(80), primary_key=True), Column("conversation_id", String(36), index=True),
    Column("role", String(16)), Column("content", Text), Column("task_id", String(36)), Column("created_at", String(40)))
memories = Table("memories", metadata,
    Column("id", String(80), primary_key=True), Column("content", Text),
    Column("source_task_id", String(36)), Column("kind", String(32)), Column("created_at", String(40)))
checkpoints = Table("agent_checkpoints", metadata,
    Column("thread_id", String(36), primary_key=True), Column("ns", String(128), primary_key=True),
    Column("checkpoint_id", String(64), primary_key=True), Column("parent_id", String(64)),
    Column("type", String(16)), Column("data", LargeBinary(length=16777215)), Column("meta", JSON))
writes = Table("agent_checkpoint_writes", metadata,
    Column("thread_id", String(36), primary_key=True), Column("ns", String(128), primary_key=True),
    Column("checkpoint_id", String(64), primary_key=True), Column("task_id", String(64), primary_key=True),
    Column("idx", Integer, primary_key=True), Column("channel", String(128)),
    Column("type", String(16)), Column("data", LargeBinary(length=16777215)))


def now():
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    def __init__(self, filename: str | Path, database_url: str = ""):
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        url = database_url or f"sqlite:///{Path(filename).as_posix()}"
        kw = {"connect_args": {"check_same_thread": False, "timeout": 30}} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, pool_pre_ping=True, **kw)
        metadata.create_all(self.engine)

    def close(self):
        self.engine.dispose()

    def save(self, state: dict):
        values = dict(conversation_id=state.get("conversation_id"), status=state["status"], state=state, updated_at=now())
        with self.engine.begin() as cn:
            if cn.execute(select(tasks.c.id).where(tasks.c.id == state["task_id"])).first():
                cn.execute(update(tasks).where(tasks.c.id == state["task_id"]).values(**values))
            else:
                cn.execute(insert(tasks).values(id=state["task_id"], **values))

    def get(self, task_id):
        with self.engine.connect() as cn:
            row = cn.execute(select(tasks.c.state).where(tasks.c.id == task_id)).first()
        return row[0] if row else None

    def list_tasks(self, conversation_id=None, statuses=None, limit=100):
        stmt = select(tasks.c.state).order_by(tasks.c.updated_at.desc()).limit(limit)
        if conversation_id:
            stmt = stmt.where(tasks.c.conversation_id == conversation_id)
        if statuses:
            stmt = stmt.where(tasks.c.status.in_(statuses))
        with self.engine.connect() as cn:
            return [r[0] for r in cn.execute(stmt)]

    def create_conversation(self, title="新的工艺分析"):
        result = dict(id=str(uuid.uuid4()), title=title[:120], created_at=now(), updated_at=now())
        with self.engine.begin() as cn:
            cn.execute(insert(conversations).values(**result))
        return result

    def _visible_conversations(self):
        return select(conversations, func.coalesce(conversation_settings.c.pinned, 0).label("pinned")).select_from(
            conversations.outerjoin(conversation_settings, conversations.c.id == conversation_settings.c.conversation_id)
        ).where(conversation_settings.c.deleted_at.is_(None))

    def list_conversations(self, allowed_ids=None, query="", limit=100):
        stmt = self._visible_conversations()
        query = query.strip()
        if allowed_ids is not None:
            stmt = stmt.where(conversations.c.id.in_(allowed_ids))
        if query:
            # Match literal text (including % and _), before applying the result limit.
            matching = select(messages.c.content).where(
                messages.c.conversation_id == conversations.c.id,
                messages.c.role == "user", messages.c.content.icontains(query, autoescape=True)
            ).order_by(messages.c.created_at.desc(), messages.c.id).limit(1).correlate(conversations).scalar_subquery()
            stmt = stmt.add_columns(matching.label("matched_question")).where(or_(
                conversations.c.title.icontains(query, autoescape=True), matching.is_not(None)))
        stmt = stmt.order_by(func.coalesce(conversation_settings.c.pinned, 0).desc(),
                             conversations.c.updated_at.desc(), conversations.c.id).limit(min(100, max(1, limit)))
        with self.engine.connect() as cn:
            return [{**dict(r), "pinned": bool(r["pinned"])} for r in cn.execute(stmt).mappings()]

    def conversation(self, conversation_id):
        with self.engine.connect() as cn:
            row = cn.execute(self._visible_conversations().where(conversations.c.id == conversation_id)).mappings().first()
            if not row:
                return None
            result = {**dict(row), "pinned": bool(row["pinned"])}
            result["messages"] = [dict(r) for r in cn.execute(select(messages).where(messages.c.conversation_id == conversation_id).order_by(messages.c.created_at, messages.c.id)).mappings()]
        return result

    def update_conversation(self, conversation_id, *, title=None, pinned=None, remove=False):
        with self.engine.begin() as cn:
            # Serialize first metadata creation and edits for this conversation on MySQL.
            row = cn.execute(select(conversations).where(conversations.c.id == conversation_id).with_for_update()).mappings().first()
            if not row:
                raise KeyError(conversation_id)
            prefs = cn.execute(select(conversation_settings).where(conversation_settings.c.conversation_id == conversation_id)).mappings().first()
            if prefs and prefs["deleted_at"]:
                raise KeyError(conversation_id)
            values = {"pinned": prefs["pinned"] if prefs else 0,
                      "custom_title": prefs["custom_title"] if prefs else 0,
                      "deleted_at": now() if remove else None}
            if pinned is not None:
                values["pinned"] = int(pinned)
            if title is not None:
                title = title.strip()
                if not title or len(title) > 120:
                    raise ValueError("分析名称应为 1–120 个字符")
                values["custom_title"] = 1
                cn.execute(update(conversations).where(conversations.c.id == conversation_id).values(title=title))
            if prefs:
                cn.execute(update(conversation_settings).where(conversation_settings.c.conversation_id == conversation_id).values(**values))
            else:
                cn.execute(insert(conversation_settings).values(conversation_id=conversation_id, **values))
            # A tombstone removes history/search access while execution/evidence audits stay intact.
            return {**dict(row), "title": title if title is not None else row["title"], "pinned": bool(values["pinned"])}

    def add_message(self, conversation_id, role, content, task_id):
        ident = f"{task_id}:{role}"
        with self.engine.begin() as cn:
            if not cn.execute(select(messages.c.id).where(messages.c.id == ident)).first():
                cn.execute(insert(messages).values(id=ident, conversation_id=conversation_id, role=role, content=content, task_id=task_id, created_at=now()))
            else:
                cn.execute(update(messages).where(messages.c.id == ident).values(content=content))
            cn.execute(update(conversations).where(conversations.c.id == conversation_id).values(updated_at=now()))
            if role == "user" and not cn.execute(select(conversation_settings.c.conversation_id).where(conversation_settings.c.conversation_id == conversation_id, conversation_settings.c.custom_title == 1)).first():
                cn.execute(update(conversations).where((conversations.c.id == conversation_id) & (conversations.c.title == "新的工艺分析")).values(title=content[:40]))

    def remember(self, content, source_task_id=None, kind="user_note"):
        ident = f"task:{source_task_id}" if source_task_id else str(uuid.uuid4())
        item = dict(id=ident, content=content, source_task_id=source_task_id, kind=kind, created_at=now())
        with self.engine.begin() as cn:
            if not cn.execute(select(memories.c.id).where(memories.c.id == ident)).first():
                cn.execute(insert(memories).values(**item))
        return item

    def list_memories(self, allowed_ids=None):
        with self.engine.connect() as cn:
            stmt=select(memories).order_by(memories.c.created_at.desc()).limit(100)
            if allowed_ids is not None: stmt=stmt.where(memories.c.id.in_(allowed_ids))
            return [dict(r) for r in cn.execute(stmt).mappings()]

    def forget(self, ident):
        with self.engine.begin() as cn:
            return cn.execute(delete(memories).where(memories.c.id == ident)).rowcount > 0

    def ping(self):
        with self.engine.connect() as cn:
            cn.execute(select(1))
        return self.engine.dialect.name
