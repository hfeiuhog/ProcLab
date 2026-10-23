"""Owner-scoped personal knowledge and immutable, explicitly submitted company releases."""
import copy
import uuid
from .control import now
from .evidence import digest

class KnowledgeLibrary:
    def __init__(self,control):self.control=control
    @staticmethod
    def check_title(title):
        title=title.strip()
        if not title or len(title)>120:raise ValueError('资料名称需1至120字')
        return title
    @staticmethod
    def approved_snapshot(doc):
        if doc['status']!='approved':raise ValueError('请先核对文档文本并用于个人库')
        v=next(v for v in doc['versions'] if v['version']==doc['approved_version'])
        if not v.get('review',{}).get('approved') or digest(v['text'])!=v['text_sha256']:raise ValueError('文档核对或摘要无效')
        return {'document_id':doc['id'],'document_version':v['version'],'filename':doc['filename'],
            'file_sha256':doc['sha256'],'text':v['text'],'text_sha256':v['text_sha256'],'review':copy.deepcopy(v['review'])}
    @staticmethod
    def chunks(snapshot,title,ident,scope,review=None):
        if digest(snapshot['text'])!=snapshot['text_sha256']:raise ValueError('知识文本快照已变化')
        result=[]
        for start in range(0,len(snapshot['text']),1800):
            text=snapshot['text'][start:start+1800]
            result.append({'doc_id':('PRIVATE-' if scope=='personal' else 'KB-')+ident.replace('-','').upper()[:24],
                'title':title,'revision':'R'+str(snapshot['document_version']),'section':str(start//1800+1),
                'status':'active','origin':'user_supplied_reviewed' if scope=='personal' else 'admin_published',
                'scope':scope,'content':text,'source':'document:'+snapshot['document_id'],'file_sha256':snapshot['file_sha256'],
                'limits':{},'review':review or snapshot['review'],'character_range':[start,start+len(text)],
                'note':'本人核对的个人资料，仅供本人检索' if scope=='personal' else '管理员核对后发布的固定文本，不替换现行SOP'})
        if not result:raise ValueError('文档没有可用文本')
        return result
    def releases(self):
        from sqlalchemy import select
        from .control import objects
        with self.control.engine.connect() as cn:
            return [r[0] for r in cn.execute(select(objects.c.state).where(
                (objects.c.kind=='knowledge')&(objects.c.owner=='admin')&(objects.c.status=='active')).order_by(objects.c.updated_at.desc()))]
    def snapshot(self,actor='admin'):
        versions={r['id']:r['content_sha256'] for r in self.releases()}
        for doc in self.control.list('document',actor):
            if doc['status']!='approved':continue
            snap=self.approved_snapshot(doc)
            key='private:'+doc['id']+':'+str(snap['document_version'])
            versions[key]=digest(self.chunks(snap,doc['filename'],doc['id'],'personal'))
        return versions
    def documents(self,versions=None,actor='admin'):
        versions=self.snapshot(actor) if versions is None else versions
        result=[]
        for ident,sha in versions.items():
            if ident.startswith('private:'):
                _,document_id,version=ident.split(':')
                doc=self.control.get('document',document_id,actor)
                v=next(v for v in doc['versions'] if v['version']==int(version))
                if not v.get('review',{}).get('approved'):raise ValueError('个人文档版本未经核对')
                snap={'document_id':document_id,'document_version':v['version'],'filename':doc['filename'],
                    'file_sha256':doc['sha256'],'text':v['text'],'text_sha256':v['text_sha256'],'review':v['review']}
                chunks=self.chunks(snap,doc['filename'],doc['id'],'personal')
                if digest(chunks)!=sha:raise ValueError('个人知识版本或文本已变化')
            else:
                item=self.control.get('knowledge',ident,'admin')
                if item['owner_id']!='admin' or item['content_sha256']!=sha or digest(item['chunks'])!=sha:raise ValueError('公司知识版本或文本已变化')
                chunks=item['chunks']
            result.extend(copy.deepcopy(chunks))
        return result
    def _publish_snapshot(self,actor,snapshot,title,submission_id=None,review=None):
        if actor!='admin':raise PermissionError('只有管理员可以发布公司知识')
        title=self.check_title(title)
        if digest(snapshot['text'])!=snapshot['text_sha256']:raise ValueError('提交文本快照已变化')
        releases=self.releases()
        for r in releases:
            if r['document_id']==snapshot['document_id'] and r['document_version']==snapshot['document_version']:return r
        if len(releases)>=20:raise ValueError('公司共享资料已达20份，请先停用不再使用的资料')
        ident=str(uuid.uuid4())
        chunks=self.chunks(snapshot,title,ident,'company',review)
        item={'id':ident,'status':'active','scope':'company','title':title,'document_id':snapshot['document_id'],
            'document_version':snapshot['document_version'],'created_at':now(),'chunks':chunks,
            'content_sha256':digest(chunks),'submission_id':submission_id}
        self.control.put('knowledge',item,'admin')
        self.control.audit('admin',actor,'publish_knowledge',ident,{'document_id':snapshot['document_id'],'version':snapshot['document_version'],'submission_id':submission_id})
        return item
    def publish(self,actor,document_id,title):
        if actor!='admin':raise PermissionError('只有管理员可以发布公司知识')
        with self.control.lock:
            doc=self.control.get('document',document_id,actor)
            return self._publish_snapshot(actor,self.approved_snapshot(doc),title)
    def submit(self,actor,document_id,title):
        title=self.check_title(title)
        with self.control.lock:
            doc=self.control.get('document',document_id,actor)
            snapshot=self.approved_snapshot(doc)
            for item in self.control.list('knowledge_submission',actor):
                if item['owner_id']==actor and item['document_id']==document_id and item['document_version']==snapshot['document_version'] and item['status'] in ('pending_review','approved'):
                    return item
            user=self.control.get_user(actor)
            item={'id':str(uuid.uuid4()),'status':'pending_review','title':title,
                'document_id':document_id,'document_version':snapshot['document_version'],'snapshot':snapshot,
                'snapshot_sha256':digest(snapshot),'submitted_by':user['username'],'created_at':now()}
            item=self.control.put('knowledge_submission',item,actor)
            self.control.audit(actor,actor,'submit_company_knowledge',item['id'],{'version':snapshot['document_version']})
            return item
    def submissions(self,actor):
        return self.control.list('knowledge_submission',actor)
    def submission(self,actor,ident):
        return self.control.get('knowledge_submission',ident,actor)
    def review_submission(self,actor,ident,approved,note):
        if actor!='admin':raise PermissionError('只有管理员可以审核公司共享申请')
        if len(note.strip())<4:raise ValueError('请填写至少4字的共享审核说明')
        with self.control.lock:
            item=self.control.get('knowledge_submission',ident,'admin')
            if item['status']!='pending_review':raise ValueError('申请已经处理，请刷新后查看')
            snap=item['snapshot']
            if digest(snap)!=item['snapshot_sha256'] or digest(snap['text'])!=snap['text_sha256']:raise ValueError('提交的固定版本校验失败')
            review={'actor':actor,'approved':approved,'note':note[:1000],'at':now()}
            if approved:
                release=self._publish_snapshot(actor,snap,item['title'],ident,review)
                item['release_id']=release['id']
            item.update(status='approved' if approved else 'rejected',review=review)
            result=self.control.put('knowledge_submission',item,item['owner_id'])
            self.control.audit(item['owner_id'],actor,'approve_company_knowledge' if approved else 'reject_company_knowledge',ident,{'version':item['document_version']})
            return result
    def withdraw(self,actor,ident):
        if actor!='admin':raise PermissionError('只有管理员可以停用公司知识')
        with self.control.lock:
            item=self.control.get('knowledge',ident,'admin');item['status']='withdrawn';self.control.put('knowledge',item,'admin')
            self.control.audit('admin',actor,'withdraw_knowledge',ident,{})
            return item
