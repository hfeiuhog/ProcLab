"""Versioned metric semantics and bounded natural-language query planning."""
import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from ..orchestration.contracts import QueryIntent

METRICS = {
    "batch_count": {"name":"批次数", "unit":"批", "definition":"指定范围内不同批次编号的数量"},
    "batch_overlimit_rate": {"name":"超限批次比例", "unit":"%", "definition":"至少一个有效参数超限的批次数 / 已有有效参数的批次数；缺测另列，不等同于合格率"},
    "parameter_overlimit_rate": {"name":"超限参数项占比", "unit":"%", "definition":"超限的有效参数项 / 有适用模拟SOP规则的有效参数项"},
    "data_completeness": {"name":"测量数据完整率", "unit":"%", "definition":"有限且有效的参数项 / 应有参数项"},
}
SEMANTIC_VERSION = "industrial-metrics-1.0.0"


def semantic_model():
    return {"version":SEMANTIC_VERSION, "metrics":METRICS,
        "dimensions":["total","device_id","day","batch_id"], "timezone":"Asia/Shanghai",
        "source":"自制模拟批次；无真实产线、能耗或设备因果数据", "dialect":"sqlite",
        "query_mode":"typed_semantic_plan_to_sql; arbitrary_sql_disabled"}


def parse_question(question, today=None):
    today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if re.search(r"能耗|成本|费用|良品率|合格率|Cpk|cpk|根因|产量|预测|供应商", question):
        raise ValueError("当前语义层不支持该指标；可查询批次数、超限批次比例、超限参数项占比和数据完整率")
    if re.search(r"各工厂|按工厂|各供应商|按产品",question):raise ValueError("当前只支持设备、日期、批次或合计分组")
    if re.search(r"缺失率|缺测率",question):raise ValueError("当前提供数据完整率及缺失参数项数，请明确选择已发布指标")
    if re.search(r"完整率|数据完整|完整性",question) and re.search(r"超限比例|超限率|超限批次比例|超限参数项占比",question):raise ValueError("单次查询支持一个指标，请分别查询完整率与超限比例")
    if re.search(r"完整率|数据完整|完整性", question): metric="data_completeness"
    elif re.search(r"参数项|参数.*占比|参数.*超限率",question): metric="parameter_overlimit_rate"
    elif re.search(r"超限|异常",question): metric="batch_overlimit_rate"
    elif re.search(r"多少|数量|批次数|批次总数",question): metric="batch_count"
    else: raise ValueError("请明确要查询的指标，例如近30天各设备的超限批次比例")
    group = "device_id" if re.search(r"各设备|按设备|设备.*对比|设备分布|各产线|按产线",question) else "day" if re.search(r"每天|逐日|按日|趋势",question) else "batch_id" if re.search(r"各批次|按批次|每个批次",question) else "total"
    start,end=date(2000,1,1),date(2100,1,1)
    dates=re.findall(r"\d{4}-\d{2}-\d{2}",question)
    if len(dates)==2: start,end=date.fromisoformat(dates[0]),date.fromisoformat(dates[1])+timedelta(days=1)
    elif dates: raise ValueError("请提供完整起止日期，例如2026-09-01至2026-10-20")
    elif re.search(r"上个?月",question):
        end=today.replace(day=1);start=(end-timedelta(days=1)).replace(day=1)
    elif re.search(r"本月|这个月",question): start=today.replace(day=1);end=today+timedelta(days=1)
    elif re.search(r"近|最近|过去",question):
        match=re.search(r"(?:近|最近|过去)\s*(\d{1,3})\s*[天日]",question)
        days=int(match.group(1)) if match else 30 if re.search(r"一个?月|30天",question) else 0
        if not 1<=days<=366: raise ValueError("请明确1至366天的查询时间范围")
        end=today+timedelta(days=1);start=end-timedelta(days=days)
    elif re.search(r"今天",question): start=today;end=today+timedelta(days=1)
    if start>=end: raise ValueError("起始日期必须早于结束日期")
    ids=re.findall(r"\bB-\d{3,8}\b",question.upper())
    if len(set(ids))>1: raise ValueError("单次指标查询仅支持一个批次过滤；跨批次比较请使用按批次分组")
    return QueryIntent(metric=metric,group_by=group,start=start.isoformat(),end=end.isoformat(),batch_id=ids[0] if ids else "")
