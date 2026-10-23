"""Synchronous LangGraph saver for this graph's ordinary state channels.

Uses the same SQLAlchemy engine as task storage, including MySQL. No DeltaChannel
or distributed worker scheduling is claimed. Deploy one API process per database.
"""
import threading
from sqlalchemy import select, insert, delete, update, and_
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple, WRITES_IDX_MAP
from .store import checkpoints as cp, writes as wr


class SQLCheckpointSaver(BaseCheckpointSaver):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.lock = threading.RLock()

    @staticmethod
    def config(thread, ns, checkpoint_id):
        return {"configurable": {"thread_id": thread, "checkpoint_ns": ns, "checkpoint_id": checkpoint_id}}

    def get_tuple(self, config):
        c = config["configurable"]
        where = and_(cp.c.thread_id == c["thread_id"], cp.c.ns == c.get("checkpoint_ns", ""))
        if c.get("checkpoint_id"):
            where = and_(where, cp.c.checkpoint_id == c["checkpoint_id"])
        with self.lock, self.engine.connect() as cn:
            row = cn.execute(select(cp).where(where).order_by(cp.c.checkpoint_id.desc()).limit(1)).mappings().first()
            if not row:
                return None
            pending = list(cn.execute(select(wr).where(and_(wr.c.thread_id == row["thread_id"], wr.c.ns == row["ns"], wr.c.checkpoint_id == row["checkpoint_id"])).order_by(wr.c.task_id, wr.c.idx)).mappings())
        return CheckpointTuple(self.config(row["thread_id"], row["ns"], row["checkpoint_id"]),
            self.serde.loads_typed((row["type"], row["data"])), row["meta"],
            self.config(row["thread_id"], row["ns"], row["parent_id"]) if row["parent_id"] else None,
            [(r["task_id"], r["channel"], self.serde.loads_typed((r["type"], r["data"]))) for r in pending])

    def list(self, config, *, filter=None, before=None, limit=None):
        stmt = select(cp).order_by(cp.c.checkpoint_id.desc())
        if config:
            c = config["configurable"]
            stmt = stmt.where(cp.c.thread_id == c["thread_id"])
            if "checkpoint_ns" in c:
                stmt = stmt.where(cp.c.ns == c["checkpoint_ns"])
        if before:
            stmt = stmt.where(cp.c.checkpoint_id < before["configurable"]["checkpoint_id"])
        with self.lock, self.engine.connect() as cn:
            rows = list(cn.execute(stmt).mappings())
        count = 0
        for row in rows:
            if filter and any(row["meta"].get(k) != v for k, v in filter.items()):
                continue
            if limit is not None and count >= limit:
                break
            yield self.get_tuple(self.config(row["thread_id"], row["ns"], row["checkpoint_id"]))
            count += 1

    def put(self, config, checkpoint, metadata, new_versions):
        c = config["configurable"]
        typ, data = self.serde.dumps_typed(checkpoint)
        values = dict(thread_id=c["thread_id"], ns=c.get("checkpoint_ns", ""), checkpoint_id=checkpoint["id"],
                      parent_id=c.get("checkpoint_id"), type=typ, data=data, meta=metadata)
        with self.lock, self.engine.begin() as cn:
            cn.execute(insert(cp).values(**values))
        return self.config(values["thread_id"], values["ns"], checkpoint["id"])

    def put_writes(self, config, writes, task_id, task_path=""):
        c = config["configurable"]
        with self.lock, self.engine.begin() as cn:
            for idx, (channel, value) in enumerate(writes):
                index = WRITES_IDX_MAP.get(channel, idx)
                key = dict(thread_id=c["thread_id"], ns=c.get("checkpoint_ns", ""), checkpoint_id=c["checkpoint_id"], task_id=task_id, idx=index)
                where = and_(*(getattr(wr.c, k) == v for k, v in key.items()))
                exists = cn.execute(select(wr.c.idx).where(where)).first()
                typ, data = self.serde.dumps_typed(value)
                if not exists:
                    cn.execute(insert(wr).values(**key, channel=channel, type=typ, data=data))
                elif index < 0:
                    cn.execute(update(wr).where(where).values(channel=channel, type=typ, data=data))

    def delete_thread(self, thread_id):
        with self.lock, self.engine.begin() as cn:
            cn.execute(delete(wr).where(wr.c.thread_id == thread_id))
            cn.execute(delete(cp).where(cp.c.thread_id == thread_id))
