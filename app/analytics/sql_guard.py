"""Only compiler-owned SQL is executable. No free SQL reaches a database."""
from datetime import date
from ..orchestration.contracts import QueryIntent

DIMENSIONS={"total":"'合计'", "device_id":"device_id", "day":"day", "batch_id":"batch_id"}


def compile_query(intent, scope, dataset_version):
    intent=QueryIntent.model_validate(intent)
    if date.fromisoformat(intent.start)>=date.fromisoformat(intent.end): raise ValueError("无效时间范围")
    dim=DIMENSIONS[intent.group_by]
    if intent.metric=="batch_count":
        num="COUNT(DISTINCT batch_id)";den="1";value=num
    elif intent.metric=="batch_overlimit_rate":
        num="COUNT(DISTINCT CASE WHEN exceed_count>0 THEN batch_id END)"
        den="COUNT(DISTINCT CASE WHEN valid_count>0 THEN batch_id END)"
        value=f"ROUND(100.0*({num})/NULLIF(({den}),0),4)"
    elif intent.metric=="parameter_overlimit_rate":
        num="COALESCE(SUM(exceed_count),0)";den="COALESCE(SUM(valid_count),0)"
        value=f"ROUND(100.0*({num})/NULLIF(({den}),0),4)"
    else:
        num="COALESCE(SUM(valid_count),0)";den="COALESCE(SUM(total_count),0)"
        value=f"ROUND(100.0*({num})/NULLIF(({den}),0),4)"
    sql=f"SELECT {dim} AS dimension, {num} AS numerator, {den} AS denominator, {value} AS value, COALESCE(SUM(total_count-valid_count),0) AS missing_parameters FROM ads_batch_quality WHERE tenant_id=:tenant AND project_id=:project AND factory_id=:factory AND dataset_version=:dataset AND day>=:start AND day<:end"
    if intent.batch_id: sql+=" AND batch_id=:batch"
    if intent.group_by!="total": sql+=f" GROUP BY {dim}"
    sql+=" ORDER BY dimension LIMIT :limit"
    params={"tenant":scope["tenant_id"],"project":scope["project_id"],"factory":scope["factory_id"],
        "dataset":dataset_version,"start":intent.start,"end":intent.end,"limit":intent.limit}
    if intent.batch_id: params["batch"]=intent.batch_id
    return sql,params


class SQLGuard:
    @staticmethod
    def validate(sql, params, intent, scope, dataset_version):
        expected,bindings=compile_query(intent,scope,dataset_version)
        if sql!=expected or params!=bindings:
            raise PermissionError("查询不匹配受控编译模板或可信权限参数")
        return {"passed":True,"policy":"compiler-owned-select-v1", "tables":["ads_batch_quality"],
                "scope_enforced":True,"arbitrary_sql":False,"max_rows":bindings["limit"],"timeout_seconds":3}
