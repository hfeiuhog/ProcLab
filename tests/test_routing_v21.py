import base64
import json
from pathlib import Path
import pytest
from app.config import Settings
from app.models import ModelRouter
from app.planner import infer_intent, make_plan
from app.rag import load_docs, DATA
from app.tools import query_batch_data, check_process_limits
from app.documents import DocumentService


def test_routing_does_not_plan_industrial_tools_for_hr_chat():
    assert infer_intent('你好') == 'chat'
    assert infer_intent('介绍一下这个项目用了哪些数据库') == 'chat'
    assert infer_intent('热压温度有什么规范') == 'knowledge'
    assert infer_intent('这个项目的升温仿真是怎么实现的') == 'chat'
    assert infer_intent('请提取以下参数字段：压力下限1.8 MPa') == 'extract'
    assert infer_intent('复杂规则推理：能否根据缺失数据放行') == 'reasoning'
    assert make_plan('介绍这个项目', '', True, settings=Settings(_env_file=None))[0] == []


def test_answer_rejects_unknown_citation(monkeypatch):
    monkeypatch.setattr(ModelRouter,'complete',lambda *a,**kw: ({'answer':'已有行业认证','citations':['FABRICATED']},{'status':'success'}))
    with pytest.raises(ValueError,match='Citations'):
        ModelRouter(Settings(_env_file=None)).answer({'intent':'knowledge','question':'温度规范','docs':load_docs()[:1]})


def test_extraction_rejects_invented_value(monkeypatch):
    monkeypatch.setattr(ModelRouter,'complete',lambda *a,**kw: ({'fields':[{'name':'温度','value':'230','unit':'℃','evidence_quote':'温度为220 ℃'}]},{'status':'success'}))
    with pytest.raises(ValueError,match='EvidenceMismatch'):
        ModelRouter(Settings(_env_file=None)).extract('温度为220 ℃')


def test_all_synthetic_labels_and_physical_row_numbers():
    labels=json.loads((DATA/'batch_labels.json').read_text(encoding='utf-8'))
    specs=[d for d in load_docs() if d['doc_id']=='SOP-003' and d['status']=='active']
    total=0
    for batch,label in labels.items():
        rows=query_batch_data(batch)
        total+=len(rows)
        result=check_process_limits(rows,specs)
        assert len(result['findings'])==label['expected_findings'], batch
        assert len(result['missing'])==label['expected_missing'], batch
    assert total==487 and len(labels)==63
    assert len([v for v in labels.values() if v['split']=='holdout'])==10
    import csv
    with (DATA/'batches.csv').open(encoding='utf-8',newline='') as f:
        assert all(int(row['row_id'])==line for line,row in enumerate(csv.DictReader(f),2))


def test_document_rejects_fake_file_and_persists_budget(tmp_path):
    settings=Settings(_env_file=None,runtime_dir=str(tmp_path),document_daily_limit=1)
    service=DocumentService(settings)
    with pytest.raises(ValueError):
        service.decode('test.png',base64.b64encode(b'not a PNG').decode(),1024)
    with pytest.raises(ValueError):
        service.decode('../test.pdf',base64.b64encode(b'%PDF-demo').decode(),1024)
    service._reserve()
    with pytest.raises(RuntimeError,match='DailyLimit'):
        DocumentService(settings)._reserve()


def test_project_question_after_batch_does_not_reuse_batch(tmp_path):
    from app.engine import TaskService
    service=TaskService(tmp_path, "fallback", settings=Settings(_env_file=None))
    try:
        first=service.create("分析 B-102 批次")
        second=service.create("刚才的项目用了哪些数据库和工具调用架构？", conversation_id=first["conversation_id"])
        assert second["intent"]=="chat" and not second["batch_id"] and second["plan"]==[]
    finally:
        service.close()


def test_answer_rejects_fabricated_inline_citation(monkeypatch):
    monkeypatch.setattr(ModelRouter,'complete',lambda *a,**kw: ({'answer':'范围见[SOP-FAKE]','citations':['SOP-003']},{'status':'success'}))
    with pytest.raises(ValueError,match='InlineCitations'):
        ModelRouter(Settings(_env_file=None)).answer({'intent':'knowledge','question':'温度规范','docs':load_docs()[:1]})


def test_grounded_answer_cannot_be_promoted_to_verified_numeric_memory(tmp_path):
    from app.engine import TaskService
    service=TaskService(tmp_path,"fallback",settings=Settings(_env_file=None))
    try:
        state=service.create("热压成型的温度要求是什么",intent="knowledge",remember_result=True)
        assert state["status"]=="completed" and state["validation"]=="passed"
        assert not service.store.list_memories()
        with pytest.raises(ValueError,match="独立数值"):
            service.save_result_memory(state["task_id"])
    finally:
        service.close()
