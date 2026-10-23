"""Offline retriever: simple lexical + Chinese character bigram RRF, NOT vector dense retrieval."""
import json
import math
import re
import hashlib
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / 'data'


def tokens(text: str) -> list[str]:
    text = text.lower()
    en = re.findall(r'[a-z]+(?:[-_][a-z0-9]+)*|\d+(?:\.\d+)?', text)
    chinese = re.findall(r'[\u4e00-\u9fff]+', text)
    return en + [s for x in chinese for s in ([x] + [x[i:i+2] for i in range(max(len(x)-1, 0))])]


def bigrams(text: str) -> set[str]:
    clean = re.sub(r'\s+', '', text.lower())
    return {clean[i:i+2] for i in range(len(clean)-1)}


def load_docs() -> list[dict]:
    docs = json.loads((DATA / 'process_sop.json').read_text(encoding='utf-8'))
    for d in docs:
        d['origin'] = 'synthetic'
        d['source'] = 'data/process_sop.json'
    public = DATA / 'public_knowledge.json'
    docs += json.loads(public.read_text(encoding='utf-8')) if public.exists() else []
    handbook = DATA / 'project_handbook.json'
    return docs + (json.loads(handbook.read_text(encoding='utf-8')) if handbook.exists() else [])


def retrieve(query: str, limit: int = 2, catalog=None) -> list[dict]:
    docs = [d for d in (load_docs() if catalog is None else catalog) if d['status'] == 'active']
    if not query.strip():
        return []
    q = Counter(tokens(query))
    corpus = [Counter(tokens(' '.join([d['title'], d['content'], d['doc_id']]))) for d in docs]
    avdl = sum(sum(t.values()) for t in corpus) / max(len(corpus), 1)
    dfs = Counter(t for counter in corpus for t in counter)
    bm = []
    overlap = []
    qgrams = bigrams(query)
    for d, t in zip(docs, corpus):
        dl = sum(t.values())
        score = 0.0
        for word in q:
            if word not in t:
                continue
            idf = math.log(1 + (len(docs) - dfs[word] + 0.5)/(dfs[word] + 0.5))
            tf = t[word]
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * dl / max(avdl, 1)))
        bm.append(score)
        gs = bigrams(d['title'] + d['content'])
        overlap.append(len(qgrams & gs) / max(len(qgrams), 1))
    bm_order = sorted(range(len(docs)), key=lambda i: -bm[i])
    char_order = sorted(range(len(docs)), key=lambda i: -overlap[i])
    scores = {i: 1/(60+bm_order.index(i)+1)+1/(60+char_order.index(i)+1) for i in range(len(docs))}
    indices = sorted(range(len(docs)), key=lambda i: -scores[i])
    # Empty common vocabulary means the documents are NOT evidence for that query.
    return [{**docs[i], 'retrieval_score': round(scores[i], 5)} for i in indices if bm[i] > 0 or overlap[i] > 0][:limit]


class KnowledgeIndex:
    """BM25/bigram + Milvus vectors with RRF. Hash vectors are labeled explicitly."""
    def __init__(self, settings):
        import threading
        self.settings = settings
        self.lock = threading.RLock()
        self.client = None
        self.last_error = None
        self.indexed = False
        self.embedding_model = None
        corpus = json.dumps(load_docs(), sort_keys=True, ensure_ascii=False)
        signature = f'{settings.embedding_provider}:{settings.embedding_model}:{settings.embedding_dimension}:{corpus}' 
        self.collection = settings.milvus_collection + '_' + hashlib.sha256(signature.encode()).hexdigest()[:10]

    def close(self):
        if self.client:
            self.client.close()

    def connect(self):
        if self.client is None:
            from pymilvus import MilvusClient
            self.client = MilvusClient(uri=self.settings.milvus_uri, token=self.settings.milvus_token, timeout=5)
        return self.client

    def embed(self, texts, query=False):
        dim = self.settings.embedding_dimension
        if self.settings.embedding_provider == 'fastembed':
            from fastembed import TextEmbedding
            if self.embedding_model is None:
                self.embedding_model = TextEmbedding(self.settings.embedding_model,
                    cache_dir=str(Path(self.settings.runtime_dir) / 'models'), threads=2)
            method = self.embedding_model.query_embed if query else self.embedding_model.passage_embed
            vectors = [v.tolist() for v in method(texts)]
            if any(len(v) != dim for v in vectors):
                raise ValueError('Local embedding dimension mismatch')
            return vectors
        if self.settings.embedding_provider in ('openai', 'siliconflow'):
            from openai import OpenAI
            silicon = self.settings.embedding_provider == 'siliconflow'
            key = self.settings.siliconflow_api_key if silicon else self.settings.embedding_api_key or self.settings.openai_api_key
            base = self.settings.siliconflow_base_url if silicon else self.settings.embedding_base_url or self.settings.openai_base_url or None
            if not key:
                raise ValueError('Embedding key is not configured')
            with OpenAI(api_key=key, base_url=base, timeout=15, max_retries=0) as client:
                result = client.embeddings.create(model=self.settings.embedding_model, input=texts)
            vectors = [item.embedding for item in sorted(result.data, key=lambda x: x.index)]
            if any(len(v) != dim or not all(math.isfinite(x) for x in v) for v in vectors) or len(vectors) != len(texts):
                raise ValueError('Embedding dimension or values are invalid')
            return vectors
        vectors = []
        for t in texts:
            vector = [0.0] * dim
            for word in tokens(t):
                h = hashlib.sha256(word.encode()).digest()
                vector[int.from_bytes(h[:4], 'big') % dim] += 1 if h[4] & 1 else -1
            norm = math.sqrt(sum(x*x for x in vector)) or 1
            vectors.append([x / norm for x in vector])
        return vectors

    @staticmethod
    def ident(doc):
        return doc['doc_id'] + ':' + doc['revision'] + ':' + doc['section']

    def reindex(self, force=True):
        with self.lock:
            client = self.connect()
            docs = [d for d in load_docs() if d['status'] == 'active']
            if not client.has_collection(collection_name=self.collection):
                client.create_collection(collection_name=self.collection, dimension=self.settings.embedding_dimension,
                    primary_field_name='id', id_type='string', max_length=128, metric_type='COSINE', consistency_level='Strong')
            elif not force and int(client.get_collection_stats(collection_name=self.collection).get('row_count', -1)) == len(docs):
                self.indexed, self.last_error = True, None
                return {'indexed': len(docs), 'collection': self.collection, 'reused': True}
            for start in range(0, len(docs), self.settings.embedding_batch_size):
                batch = docs[start:start+self.settings.embedding_batch_size]
                vectors = self.embed([d['title'] + ' ' + d['content'] for d in batch])
                client.upsert(collection_name=self.collection, data=[{'id': self.ident(d), 'vector': v} for d, v in zip(batch, vectors)])
            client.flush(collection_name=self.collection)
            self.indexed, self.last_error = True, None
            return {'indexed': len(docs), 'collection': self.collection, 'embedding_provider': self.settings.embedding_provider}

    def rerank(self, query, docs, limit):
        if not (self.settings.reranker_enabled and self.settings.siliconflow_api_key and docs):
            return docs[:limit], {'status': 'disabled'}
        try:
            import httpx
            with httpx.Client(timeout=15, trust_env=False) as client:
                r = client.post(self.settings.siliconflow_base_url.rstrip('/') + '/rerank',
                    headers={'Authorization': 'Bearer ' + self.settings.siliconflow_api_key},
                    json={'model': self.settings.reranker_model, 'query': query,
                          'documents': [d['title'] + ' ' + d['content'] for d in docs], 'top_n': min(limit, len(docs))})
                r.raise_for_status()
                results = r.json()['results']
            indices = [x['index'] for x in results]
            if (not indices or len(set(indices)) != len(indices) or any(type(i) is not int or not 0 <= i < len(docs) for i in indices)
                    or any(not math.isfinite(x['relevance_score']) for x in results)):
                raise ValueError('InvalidRerankerResponse')
            return [{**docs[x['index']], 'rerank_score': x['relevance_score']} for x in results][:limit], {
                'status': 'ready', 'model': self.settings.reranker_model, 'candidates': len(docs)}
        except Exception as exc:
            return docs[:limit], {'status': 'fallback', 'error': type(exc).__name__}

    def search(self, query, limit=None):
        limit = limit or self.settings.retrieval_limit
        candidates = self.settings.retrieval_candidates
        lexical = retrieve(query, limit=candidates)
        if not self.settings.milvus_uri:
            result, rerank = self.rerank(query, lexical, limit)
            return result, {'backend': 'lexical', 'status': 'local', 'embedding': None, 'reranker': rerank}
        try:
            with self.lock:
                if not self.indexed:
                    self.reindex(force=False)
                hits = self.connect().search(collection_name=self.collection, data=self.embed([query], query=True), limit=candidates,
                    search_params={'metric_type': 'COSINE'}, consistency_level='Strong')[0]
            catalog = {self.ident(d): d for d in load_docs() if d['status'] == 'active'}
            # Never trust vector payload as authoritative source content or version.
            dense = [str(h['id']) for h in hits if str(h['id']) in catalog and h['distance'] > 0]
            ranks = {}
            for ids in ([self.ident(d) for d in lexical], dense):
                for rank, ident in enumerate(ids):
                    ranks[ident] = ranks.get(ident, 0) + 1 / (61 + rank)
            result = [{**catalog[k], 'retrieval_score': round(v, 6)} for k, v in sorted(ranks.items(), key=lambda kv: -kv[1])[:candidates]]
            result, rerank = self.rerank(query, result, limit)
            self.last_error = None
            return result, {'backend': 'milvus+lexical_rrf', 'status': 'ready', 'embedding': self.settings.embedding_provider,
                            'semantic': self.settings.embedding_provider != 'hash', 'sparse': 'bm25_lexical', 'reranker': rerank}
        except Exception as exc:
            self.last_error = type(exc).__name__
            return lexical[:limit], {'backend': 'lexical_fallback', 'status': 'degraded', 'error': self.last_error}

    def health(self):
        if not self.settings.milvus_uri:
            return {'backend': 'lexical', 'status': 'local', 'documents': len(load_docs())}
        try:
            self.connect().list_collections(timeout=3)
            return {'backend': 'milvus', 'status': 'ready', 'embedding': self.settings.embedding_provider,
                    'semantic': self.settings.embedding_provider != 'hash', 'collection': self.collection}
        except Exception as exc:
            return {'backend': 'milvus', 'status': 'unavailable', 'error': type(exc).__name__}
