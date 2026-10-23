from app.tools import query_batch_data,check_process_limits,search_process_docs

def test_real_csv_query():
    rows=query_batch_data('B-102')
    assert len(rows)==3
    assert rows[1]['row_id']=='5'

def test_anomaly_and_citation():
    result=check_process_limits(query_batch_data('B-102'),search_process_docs('热压 工艺 温度 压力 黏度'))
    assert len(result['findings'])>=3
    assert any('SOP-003 R2' in x['citation'] for x in result['findings'])
    assert not result['missing']

def test_missing_parameter():
    result=check_process_limits(query_batch_data('B-103'),search_process_docs('工艺规范 温度 压力 黏度'))
    assert len(result['missing'])==1
    assert result['missing'][0]['parameter']=='pressure_mpa'

def test_obsolete_version_excluded():
    docs=search_process_docs('热压成型工艺规范')
    assert docs and all(d['status']=='active' for d in docs)
