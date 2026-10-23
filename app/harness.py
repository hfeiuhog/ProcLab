"""Execution harness: explicit budgets, allowlisted tools, recovery advice and lineage."""
from datetime import datetime,timezone
ALLOWED_TOOLS={'search_process_docs','query_batch_data','check_process_limits','process_statistics','simulate_heating','validate_evidence'}

def classify_failure(error):
    name=type(error).__name__
    status=getattr(error,'status_code',None)
    if status in (401,403): return {'category':'provider_auth','retryable':False,'message':'模型服务鉴权失败','actions':['联系管理员核对服务密钥与权限']}
    if status==429: return {'category':'rate_limit','retryable':True,'message':'远程服务限流或额度不足','actions':['稍后重试','联系管理员检查额度']}
    if 'Timeout' in name or 'Connection' in name or (status and status>=500):
        return {'category':'transient','retryable':True,'message':'远程调用超时或暂不可用','actions':['限次重试','图片可更换解析方式']}
    return {'category':'invalid_output','retryable':False,'message':'输入、输出格式或证据校验未通过','actions':['核对原始文件','更换解析方式','人工修订后重新提交审核']}

def policy(settings):
    return {'max_tool_calls':settings.harness_max_tool_calls,'step_boundary_timeout_seconds':settings.harness_timeout_seconds,
            'max_repair_versions':settings.harness_max_repairs,'query_attempts':2,'model_output_validation':True,
            'tool_scope':'allowlisted_python_tools','checkpoint':'sql','review_does_not_fill_missing_evidence':True}

def boundary_reason(state,settings,check_budget=True):
    started=state.get('run_started_at')
    if started:
        elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(started)).total_seconds()
        if elapsed>settings.harness_timeout_seconds: return '执行时间预算耗尽，请缩小任务范围或重试'
    if check_budget and state.get('tool_budget',settings.harness_max_tool_calls)<=0: return '工具调用预算耗尽'
    return None
