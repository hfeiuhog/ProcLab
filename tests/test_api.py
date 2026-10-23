
def submit(client,batch='B-102',failure='none'):
    r=client.post('/api/tasks',json={'question':'请根据工艺规范分析批次质量参数，并核对证据','batch_id':batch,'inject_timeout':failure})
    assert r.status_code==200,r.text
    return r.json()

def test_health(client):
    r=client.get('/health')
    assert r.json()['execution_engine']=='fallback'
    assert r.json()['data_policy']=='synthetic_measurements_and_attributed_public_summaries'

def test_anomalies_do_not_claim_root_cause(client):
    s=submit(client)
    assert s['status']=='completed'
    assert len(s['report']['findings'])>=3
    assert '不足以推断' in s['report']['summary']
    assert any(x['node']=='check_process_limits' for x in s['trace'])
    assert client.get('/api/tasks/'+s['task_id']).status_code==200

def test_normal(client):
    s=submit(client,'B-101')
    assert s['status']=='completed'
    assert s['report']['findings']==[]

def test_one_timeout_retries_successfully(client):
    s=submit(client,'B-102','once')
    assert s['status']=='completed'
    attempts=[x for x in s['trace'] if x['node']=='query_batch_data']
    assert len(attempts)==2
    assert '超时' in attempts[0]['detail']

def test_permanent_timeout_requires_review(client):
    s=submit(client,'B-102','always')
    assert s['status']=='pending_review'
    assert '连续两次' in s['review_reason']
    assert s.get('report') is None
    response=client.post('/api/tasks/'+s['task_id']+'/review',json={'approved':True,'note':'仅同意发出缺数据说明'})
    assert response.status_code==200
    finished=response.json()
    assert finished['status']=='completed_reviewed'
    assert '无法形成完整' in finished['report']['summary']
    assert client.post('/api/tasks/'+s['task_id']+'/review',json={'approved':True}).status_code==409

def test_missing_data_human_reject(client):
    s=submit(client,'B-103')
    assert s['status']=='pending_review'
    res=client.post('/api/tasks/'+s['task_id']+'/review',json={'approved':False,'note':'应补采数据'})
    assert res.json()['status']=='rejected'
    assert '不得作为正式分析结论' in res.json()['report']['summary']

def test_unknown_batch_does_not_hallucinate(client):
    s=submit(client,'B-999')
    assert s['status']=='pending_review'
    assert not s.get('report')

def test_schema_validation(client):
    assert client.post('/api/tasks',json={'question':'短','batch_id':'../etc/passwd'}).status_code==422

def test_document_only(client):
    s=submit(client,'')
    assert s['status']=='completed'
    assert s['plan']==['search_process_docs','validate_evidence']
    assert s['report']['sources']
