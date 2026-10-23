from app.engine import TaskService

def test_resume_pending_review_after_restart(tmp_path):
    first=TaskService(tmp_path,mode='fallback')
    task=first.create('演示工艺数据不完整后的持久化人工复核','B-103')
    assert task['status']=='pending_review'
    first.close()
    second=TaskService(tmp_path,mode='fallback')
    assert second.get(task['task_id'])['status']=='pending_review'
    saved=second.review(task['task_id'],approved=False,note='先补全数据')
    assert saved['status']=='rejected'
    second.close()
