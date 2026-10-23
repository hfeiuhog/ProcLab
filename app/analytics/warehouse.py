"""Independent SQLite ODS/DWD/ADS demo warehouse with read-only query execution."""
import csv
import hashlib
import json
import math
import sqlite3
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from ..rag import DATA, load_docs
from ..tools import PARAMETERS
from ..orchestration.contracts import digest
from .semantic import METRICS, SEMANTIC_VERSION
from .sql_guard import compile_query, SQLGuard


class Warehouse:
    def __init__(self, runtime_dir):
        self.path=Path(runtime_dir)/"analytics"/"industrial-warehouse.sqlite3"
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS dataset_manifest(tenant_id TEXT,project_id TEXT,factory_id TEXT,dataset_version TEXT,payload TEXT,PRIMARY KEY(tenant_id,project_id,factory_id,dataset_version));
            CREATE TABLE IF NOT EXISTS ods_measurements(tenant_id TEXT,project_id TEXT,factory_id TEXT,dataset_version TEXT,row_id TEXT,payload TEXT,PRIMARY KEY(tenant_id,project_id,factory_id,dataset_version,row_id));
            CREATE TABLE IF NOT EXISTS dwd_parameter_checks(tenant_id TEXT,project_id TEXT,factory_id TEXT,dataset_version TEXT,row_id TEXT,batch_id TEXT,device_id TEXT,day TEXT,parameter TEXT,value TEXT,valid INTEGER,exceeded INTEGER,PRIMARY KEY(tenant_id,project_id,factory_id,dataset_version,row_id,parameter));
            CREATE TABLE IF NOT EXISTS ads_batch_quality(tenant_id TEXT,project_id TEXT,factory_id TEXT,dataset_version TEXT,batch_id TEXT,device_id TEXT,day TEXT,total_count INTEGER,valid_count INTEGER,exceed_count INTEGER,PRIMARY KEY(tenant_id,project_id,factory_id,dataset_version,batch_id,device_id,day));
            CREATE VIEW IF NOT EXISTS dws_device_daily AS SELECT tenant_id,project_id,factory_id,dataset_version,device_id,day,SUM(total_count) AS total_count,SUM(valid_count) AS valid_count,SUM(exceed_count) AS exceed_count FROM ads_batch_quality GROUP BY tenant_id,project_id,factory_id,dataset_version,device_id,day;
            CREATE TABLE IF NOT EXISTS consumed_events(event_id TEXT PRIMARY KEY,payload TEXT,ingested_at TEXT);
            CREATE TABLE IF NOT EXISTS dwd_result_revisions(revision_id TEXT PRIMARY KEY,root_task_id TEXT,tenant_id TEXT,project_id TEXT,verdict TEXT,publication TEXT,version INTEGER,payload TEXT);
            """)

    def connect(self):
        return sqlite3.connect(str(self.path),timeout=10)

    def ensure_dataset(self, scope):
        raw=(DATA/"batches.csv").read_bytes()
        spec=next(d for d in load_docs() if d["doc_id"]=="SOP-003" and d["status"]=="active")
        source_sha=hashlib.sha256(raw).hexdigest();version=digest([source_sha,spec])
        key=(scope["tenant_id"],scope["project_id"],scope["factory_id"],version)
        with self.lock,self.connect() as db:
            prior=db.execute("SELECT payload FROM dataset_manifest WHERE tenant_id=? AND project_id=? AND factory_id=? AND dataset_version=?",key).fetchone()
            if prior:return json.loads(prior[0])
            rows=list(csv.DictReader(raw.decode("utf-8").splitlines()));groups=defaultdict(lambda:[0,0,0]);days=[]
            for row in rows:
                db.execute("INSERT INTO ods_measurements VALUES(?,?,?,?,?,?)",(*key,row["row_id"],json.dumps(row,ensure_ascii=False)))
                day=row.get("measured_at","")[:10];days.append(day)
                group=groups[(row["batch_id"],row.get("device_id","unknown"),day)]
                for parameter in PARAMETERS:
                    valid=0;exceeded=0
                    try:
                        val=Decimal(str(row.get(parameter)));valid=int(val.is_finite())
                        if valid: exceeded=int(not Decimal(str(spec["limits"][parameter]["min"]))<=val<=Decimal(str(spec["limits"][parameter]["max"])))
                    except (InvalidOperation,ValueError,TypeError):pass
                    group[0]+=1;group[1]+=valid;group[2]+=exceeded
                    db.execute("INSERT INTO dwd_parameter_checks VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(*key,row["row_id"],row["batch_id"],row.get("device_id","unknown"),day,parameter,str(row.get(parameter,"")),valid,exceeded))
            for (batch,device,day),counts in groups.items():db.execute("INSERT INTO ads_batch_quality VALUES(?,?,?,?,?,?,?,?,?,?)",(*key,batch,device,day,*counts))
            manifest={"dataset_version":version,"source_sha256":source_sha,"sop_version":spec["revision"],"sop_sha256":digest(spec),
                "row_count":len(rows),"parameter_count":len(rows)*len(PARAMETERS),"batch_count":len({r["batch_id"] for r in rows}),
                "watermark":max(days) if days else None,"min_date":min(days) if days else None,"ingested_at":datetime.now(timezone.utc).isoformat(),
                "origin":"synthetic","timezone":"Asia/Shanghai","layers":["ODS","DWD","DWS","ADS"],"scope":scope}
            db.execute("INSERT INTO dataset_manifest VALUES(?,?,?,?,?)",(*key,json.dumps(manifest,ensure_ascii=False)))
        return manifest

    def execute(self,intent,scope):
        manifest=self.ensure_dataset(scope);version=manifest["dataset_version"]
        sql,params=compile_query(intent,scope,version);guard=SQLGuard.validate(sql,params,intent,scope,version)
        deadline=time.monotonic()+3
        db=sqlite3.connect(self.path.resolve().as_uri()+"?mode=ro",uri=True,timeout=3)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        allowed_functions={"count","sum","coalesce","round","nullif"}
        def authorize(action,a,b,database,source):
            if action==sqlite3.SQLITE_SELECT:return sqlite3.SQLITE_OK
            if action==sqlite3.SQLITE_READ and a=="ads_batch_quality":return sqlite3.SQLITE_OK
            if action==sqlite3.SQLITE_FUNCTION and (b or a or "").lower() in allowed_functions:return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        db.set_authorizer(authorize);db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        try: rows=[dict(r) for r in db.execute(sql,params).fetchall()]
        finally: db.close()
        result={"intent":intent.model_dump(),"sql":sql,"bindings":params,"guard":guard,"rows":rows,"row_count":len(rows),
            "metric":METRICS[intent.metric],"semantic_version":SEMANTIC_VERSION,"manifest":manifest,
            "scope":scope,"result_sha256":digest(rows),"query_id":digest([sql,params,rows,scope]),
            "time_range":{"start_inclusive":intent.start,"end_exclusive":intent.end,"timezone":"Asia/Shanghai"},
            "warning":"基于自制模拟数据；历史分布不代表当前异常根因；NULL表示无可用分母。"}
        return result

    def verify(self, result, scope):
        if result.get("scope")!=scope or result.get("semantic_version")!=SEMANTIC_VERSION:return False
        if digest(result.get("rows"))!=result.get("result_sha256"):return False
        from ..orchestration.contracts import QueryIntent
        intent=QueryIntent.model_validate(result["intent"])
        SQLGuard.validate(result["sql"],result["bindings"],intent,scope,result["manifest"]["dataset_version"])
        # Recompute from the immutable DWD grain using Python Decimal, independent of ADS SQL.
        params=result["bindings"];key=(scope["tenant_id"],scope["project_id"],scope["factory_id"],params["dataset"],intent.start,intent.end)
        with self.connect() as db:
            source=db.execute("SELECT row_id,batch_id,device_id,day,parameter,valid,exceeded FROM dwd_parameter_checks WHERE tenant_id=? AND project_id=? AND factory_id=? AND dataset_version=? AND day>=? AND day<?",key).fetchall()
        grouped=defaultdict(list)
        for row in source:
            if intent.batch_id and row[1]!=intent.batch_id:continue
            dimension={"total":"合计","device_id":row[2],"day":row[3],"batch_id":row[1]}[intent.group_by];grouped[dimension].append(row)
        if intent.group_by=="total" and not grouped:grouped["合计"]=[]
        expected=[]
        for dimension,points in sorted(grouped.items())[:intent.limit]:
            valid=sum(r[5] for r in points);exceeded=sum(r[6] for r in points);total=len(points)
            if intent.metric=="batch_count":n=len({r[1] for r in points});d=1
            elif intent.metric=="batch_overlimit_rate":n=len({r[1] for r in points if r[6]});d=len({r[1] for r in points if r[5]})
            elif intent.metric=="parameter_overlimit_rate":n=exceeded;d=valid
            else:n=valid;d=total
            value=n if intent.metric=="batch_count" else float((Decimal(n)*100/Decimal(d)).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)) if d else None
            expected.append(dict(dimension=dimension,numerator=n,denominator=d,value=value,missing_parameters=total-valid))
        return expected==result["rows"]

    def consume(self,event):
        revision=event["revision"];scope=event["scope"]
        with self.lock,self.connect() as db:
            if db.execute("SELECT 1 FROM consumed_events WHERE event_id=?",(event["id"],)).fetchone():return False
            db.execute("INSERT INTO consumed_events VALUES(?,?,?)",(event["id"],json.dumps(event,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
            db.execute("INSERT OR IGNORE INTO dwd_result_revisions VALUES(?,?,?,?,?,?,?,?)",(revision["id"],revision["root_task_id"],scope["tenant_id"],scope["project_id"],revision["verdict"],revision["publication"],revision["version"],json.dumps(revision,ensure_ascii=False)))
        return True

    def health(self):
        with self.connect() as db:
            rows=db.execute("SELECT count(*) FROM consumed_events").fetchone()[0]
        return {"status":"ready","backend":"independent_sqlite_warehouse","layers":["ODS","DWD","DWS","ADS"],"consumed_events":rows,"arbitrary_sql":False}
