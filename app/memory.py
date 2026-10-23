"""Redis caches bounded conversation context; SQL remains authoritative."""
import json


class Memory:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.redis = None
        self.last_error = None
        if settings.redis_url:
            from redis import Redis
            self.redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)

    def close(self):
        if self.redis:
            self.redis.close()

    def context(self, conversation_id):
        key = f"industrial:context:{conversation_id}"
        if self.redis:
            try:
                value = self.redis.get(key)
                self.last_error = None
                if value:
                    return json.loads(value)
            except Exception as exc:
                self.last_error = type(exc).__name__
        conv = self.store.conversation(conversation_id)
        result = [{k: m[k] for k in ("role", "content", "task_id")} for m in (conv or {}).get("messages", [])[-12:]]
        if self.redis:
            try:
                self.redis.setex(key, self.settings.short_memory_ttl, json.dumps(result, ensure_ascii=False))
                self.last_error = None
            except Exception as exc:
                self.last_error = type(exc).__name__
        return result

    def invalidate(self, conversation_id):
        if self.redis:
            try:
                self.redis.delete(f"industrial:context:{conversation_id}")
            except Exception as exc:
                self.last_error = type(exc).__name__

    def recall(self, question, allowed_ids=None):
        from .rag import tokens
        q = set(tokens(question))
        ranked = sorted(self.store.list_memories(allowed_ids), key=lambda m: -len(q & set(tokens(m["content"]))))
        return [m for m in ranked if q & set(tokens(m["content"]))][:4]

    def health(self):
        if not self.redis:
            return {"backend": "sql_recent_messages", "status": "local", "ttl_seconds": None}
        try:
            self.redis.ping()
            return {"backend": "redis", "status": "ready", "ttl_seconds": self.settings.short_memory_ttl}
        except Exception as exc:
            return {"backend": "redis", "status": "unavailable", "error": type(exc).__name__}
