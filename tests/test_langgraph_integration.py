"""Only runs when full optional LangGraph dependencies are installed."""
import importlib.util
import pytest
from app.engine import TaskService

@pytest.mark.skipif(importlib.util.find_spec('langgraph') is None, reason='Optional LangGraph is not installed')
def test_langgraph_invoke_interrupt_and_resume(tmp_path):
    s=TaskService(tmp_path,mode='langgraph')
    try:
        result=s.create('分析 B-102 工艺参数是否超限','B-102')
        assert s.mode=='langgraph'
        assert result['status']=='completed'
        assert result['report']['findings']
        pending=s.create('分析 B-103 并对数据缺失实施人工复核','B-103')
        assert pending['status']=='pending_review'
        completed=s.review(pending['task_id'],approved=False,note='缺失压力参数')
        assert completed['status']=='rejected'
    finally:
        s.close()
