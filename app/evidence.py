"""Reviewed evidence supplements are immutable inputs to a NEW analysis version."""
import copy
import hashlib
import json
import math
import uuid
from .rag import load_docs
from .tools import query_batch_data,PARAMETERS
from .control import now

def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class EvidenceService:
    def __init__(self,control): self.control=control
    def submit(self,parent,corrections,source_note,document_id,actor):
        if not parent.get('batch_id'): raise ValueError('只支持对已有批次补充测量证据')
        rows=query_batch_data(parent['batch_id'])
        catalog={r['row_id']:r for r in rows}
        if not rows or not corrections or len(corrections)>24 or len(source_note.strip())<4:
            raise ValueError('需要现有批次、补充字段和来源说明')
        if document_id:
            document=self.control.get('document',document_id,actor)
            if document['status']!='approved': raise ValueError('来源文档须先完成审核')
        spec=next(d for d in load_docs() if d['doc_id']=='SOP-003' and d['status']=='active')
        seen=set(); normalized=[]
        for c in corrections:
            row_id=str(c.get('row_id','')); param=c.get('parameter'); key=(row_id,param)
            if row_id not in catalog or param not in PARAMETERS or key in seen: raise ValueError('数据行、字段或重复补证无效')
            value=float(c['value'])
            if not math.isfinite(value) or c.get('unit')!=spec['limits'][param]['unit']: raise ValueError('数值必须有限且单位须匹配原始列')
            seen.add(key)
            normalized.append({'row_id':row_id,'parameter':param,'value':str(c['value']),'unit':c['unit'],'original_value':catalog[row_id].get(param)})
        state={'id':str(uuid.uuid4()),'status':'pending_review','parent_task_id':parent['task_id'],
               'batch_id':parent['batch_id'],'corrections':normalized,'source_note':source_note[:1000],
               'document_id':document_id,'original_rows_sha256':digest(rows),'created_at':now()}
        owner=parent.get('owner_id','admin')
        result=self.control.put('supplement',state,owner)
        self.control.audit(owner,actor,'submit_supplement',state['id'],{'parent_task_id':parent['task_id'],'fields':len(normalized)})
        return result
    def approve(self,ident,actor,approved,note):
        with self.control.lock:
            state=self.control.get('supplement',ident,actor)
            if state['status']!='pending_review': raise ValueError('补证已审核，不能重复审核')
            rows=query_batch_data(state['batch_id'])
            if digest(rows)!=state['original_rows_sha256']: raise ValueError('原始记录已变化，请重新提交补证')
            rows=copy.deepcopy(rows)
            for c in state['corrections']:
                row=next(r for r in rows if r['row_id']==c['row_id'])
                row[c['parameter']]=c['value']
                row['_source_ref']=f"batches.csv 第 {row['row_id']} 行；补充证据 {ident} R1（人工输入并审核）"
            state.update(status='approved' if approved else 'rejected',review={'actor':actor,'approved':approved,'note':note[:1000],'at':now()})
            if approved:
                state.update(approved_rows=rows,approved_rows_sha256=digest(rows))
            self.control.put('supplement',state,state['owner_id'])
            self.control.audit(state['owner_id'],actor,'approve_supplement' if approved else 'reject_supplement',ident,{'note':note[:500]})
            return state
    def rows(self,state):
        ident=state.get('evidence_bundle_id')
        if not ident: return query_batch_data(state.get('batch_id',''))
        item=self.control.get('supplement',ident,state.get('owner_id','admin'))
        if item['status']!='approved' or item['batch_id']!=state['batch_id']:
            raise ValueError('补证未审核或批次不匹配')
        rows=item['approved_rows']
        if digest(rows)!=item['approved_rows_sha256']: raise ValueError('补证快照校验失败')
        return copy.deepcopy(rows)
    def documents(self,state):
        from .knowledge_library import KnowledgeLibrary
        result=KnowledgeLibrary(self.control).documents(state.get('knowledge_versions',{}),state.get('owner_id','admin'))
        for ident in state.get('evidence_document_ids',[]):
            item=self.control.get('document',ident,state.get('owner_id','admin'))
            revision=state.get('evidence_document_versions',{}).get(ident,item.get('approved_version'))
            if revision is None: raise ValueError('文档尚未审核')
            version=next(v for v in item['versions'] if v['version']==revision)
            if not version.get('review',{}).get('approved'): raise ValueError('指定文档版本未通过审核')
            text=version['text']
            if digest(text)!=version['text_sha256']: raise ValueError('文档快照已变化')
            result.append({'doc_id':'UPLOAD-'+ident,'title':item['filename'],'revision':'R'+str(version['version']),
                'section':'reviewed_text','status':'active','origin':'user_supplied_reviewed',
                'content':text[:12000],'source':'document:'+ident,'file_sha256':item['sha256'],'limits':{},
                'review':version.get('review'),'note':'用户上传及人工核对资料，不自动成为现行SOP'})
        return result
