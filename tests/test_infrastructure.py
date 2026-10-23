"""Run only with --env local Docker URLs configured and RUN_INFRA_TESTS=1."""
import os
import uuid
import pytest
from app.config import Settings
from app.engine import TaskService

pytestmark = [pytest.mark.infrastructure, pytest.mark.skipif(os.getenv("RUN_INFRA_TESTS") != "1", reason="Docker infrastructure not requested")]


def test_real_mysql_redis_milvus_resume(tmp_path):
    settings = Settings(use_llm=False)
    assert all([settings.database_url, settings.redis_url, settings.milvus_uri])
    service = TaskService(tmp_path, "langgraph", settings=settings)
    task = None
    try:
        assert service.health()["components"]["database"]["backend"] == "mysql"
        assert service.memory.health()["status"] == "ready"
        indexed = service.knowledge.reindex()
        assert indexed["indexed"] >= 4
        task = service.create("分析 B-102 批次参数", "B-102")
        assert task["status"] == "completed"
        assert task["retrieval"]["backend"] == "milvus+lexical_rrf"
        assert task["retrieval"]["semantic"] is True
        assert task["retrieval"]["embedding"] == settings.embedding_provider
        assert task["retrieval"]["reranker"]["status"] == "ready"
        context = service.memory.context(task["conversation_id"])
        assert context
        assert service.memory.redis.ttl("industrial:context:" + task["conversation_id"]) > 0
        pending = service.create("分析 B-103 参数", "B-103")
    finally:
        service.close()
    reopened = TaskService(tmp_path, "langgraph", settings=settings)
    try:
        assert reopened.get(task["task_id"])["status"] == "completed"
        assert reopened.review(pending["task_id"], False)["status"] == "rejected"
    finally:
        reopened.close()
