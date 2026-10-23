"""Real local tools; synthetic process data, no external business secrets."""
import csv
import math
from pathlib import Path
from .rag import retrieve, DATA

def reading_source(row):
    return row.get('_source_ref') or f"batches.csv 第 {row['row_id']} 行"

PARAMETERS = ('temperature_c', 'pressure_mpa', 'viscosity_pas')


def search_process_docs(query: str) -> list[dict]:
    """Search active process specifications using an offline retrieval index."""
    return retrieve(query)


def query_batch_data(batch_id: str) -> list[dict]:
    """Read CSV and preserve real source row identifiers for citations."""
    with (DATA / 'batches.csv').open(encoding='utf-8', newline='') as f:
        return [row for row in csv.DictReader(f) if row['batch_id'] == batch_id]


def check_process_limits(readings: list[dict], specs: list[dict]) -> dict:
    """Deterministically check values against a CURRENT document revision."""
    active = [s for s in specs if s.get('doc_id') == 'SOP-003' and s.get('status') == 'active' and s.get('limits')]
    if len(active) != 1:
        return {'error': '当前有效工艺规范缺失或存在冲突', 'findings': [], 'missing': []}
    spec = active[0]
    findings = []
    missing = []
    for row in readings:
        for param in PARAMETERS:
            raw = row.get(param)
            if raw is None or raw == '':
                missing.append({'row_id': row.get('row_id'), 'parameter': param})
                continue
            if param not in spec['limits']:
                missing.append({'row_id': row.get('row_id'), 'parameter': param, 'cause':'无参数规范'})
                continue
            try:
                value = float(raw)
            except (ValueError, TypeError):
                missing.append({'row_id': row.get('row_id'), 'parameter': param, 'cause':'值非数值'})
                continue
            lim = spec['limits'][param]
            if not math.isfinite(value):
                missing.append({'row_id': row.get('row_id'), 'parameter': param, 'cause':'非有限数值'})
                continue
            if not lim['min'] <= value <= lim['max']:
                findings.append({
                    'row_id': row['row_id'], 'parameter':param, 'actual':value,
                    'allowed':[lim['min'],lim['max']], 'unit':lim['unit'],
                    'citation':f"{reading_source(row)}；{spec['doc_id']} {spec['revision']} §{spec['section']}"
                })
    return {'findings':findings, 'missing':missing, 'error':None}
