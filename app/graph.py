"""LangGraph supervisor -> selected tools -> evidence gate -> HITL/report."""
from typing import Any, TypedDict
from .steps import (plan_step, search_step, query_step, analyze_step, statistics_step,
                    simulation_step, validate_step, report_step, event)
from .planner import select_tool
from .harness import boundary_reason, ALLOWED_TOOLS


class AgentState(TypedDict, total=False):
    task_id: str
    conversation_id: str
    created_at: str
    question: str
    batch_id: str
    intent: str
    analysis_mode: str
    knowledge_versions: dict
    simulation_params: dict
    remember_result: bool
    inject_timeout: str
    status: str
    plan: list[str]
    plan_provider: str
    step_index: int
    completed_steps: list[str]
    next_tool: str
    tool_budget: int
    trace: list[dict[str, Any]]
    context: list[dict]
    recalled_memories: list[dict]
    docs: list[dict]
    retrieval: dict
    readings: list[dict]
    analysis: dict
    statistics: dict
    simulation: dict
    validation: str
    validation_details: dict
    review_reason: str | None
    review: dict | None
    report: dict
    answer_metadata: dict
    owner_id: str
    parent_task_id: str | None
    root_task_id: str | None
    repair_version: int
    evidence_bundle_id: str | None
    evidence_document_ids: list[str]
    evidence_document_versions: dict
    harness: dict
    run_started_at: str
    failure: dict


def build_graph(checkpointer, llm_enabled=False, settings=None, knowledge=None, evidence=None):
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import interrupt
    from .config import Settings
    settings = settings or Settings()
    builder = StateGraph(AgentState)
    builder.add_node("planner", lambda s: plan_step(s, llm_enabled, settings))
    nodes = {
        "search_process_docs": lambda s: search_step(s, knowledge, evidence),
        "query_batch_data": lambda s: query_step(s, evidence), "check_process_limits": analyze_step,
        "process_statistics": statistics_step, "simulate_heating": simulation_step,
        "validate_evidence": lambda s: validate_step(s, evidence),
    }
    for name, fn in nodes.items():
        def execute(s, name=name, fn=fn):
            reason = boundary_reason(s, settings, check_budget=False)
            if reason: return {'review_reason': reason, 'validation':'needs_review', 'trace':s.get('trace',[])+[event('harness_guard',reason)]}
            result = fn(s)
            result["completed_steps"] = s.get("completed_steps", []) + [name]
            return result
        builder.add_node(name, execute)

    def supervisor(s):
        if s.get("review_reason"):
            return {"next_tool": "human_review", "validation": "needs_review"}
        if len(s.get('completed_steps',[])) == len(s.get('plan',[])):
            return {'next_tool':'finalize'}
        reason=boundary_reason(s,settings)
        if reason:
            return {"next_tool":"human_review","validation":"needs_review","review_reason":reason}
        name, provider, call_id = select_tool(s, settings)
        if name not in ALLOWED_TOOLS and name!='finalize':
            return {'next_tool':'human_review','review_reason':'工具不在允许范围','validation':'needs_review'}
        return {"next_tool": name, "tool_budget": s.get("tool_budget", 12) - 1,
                "trace": s.get("trace", []) + [event("supervisor", "选择下一步：" + name,
                    provider=provider, tool_call_id=call_id)]}

    def review_node(s):
        response = interrupt({"kind": "approval", "reason": s.get("review_reason"),
                              "question": "是否发布保留证据缺失说明的限制性报告？"})
        if not isinstance(response, dict) or type(response.get("approved")) is not bool:
            raise ValueError("Resume requires {approved: bool, note: str}")
        return {"review": {"approved": response["approved"], "note": str(response.get("note", ""))[:500], "actor":response.get("actor","admin")},
                "trace": s.get("trace", []) + [event("human_review", "人工批准限制性说明" if response["approved"] else "人工驳回")]}

    builder.add_node("supervisor", supervisor)
    builder.add_node("human_review", review_node)
    builder.add_node("finalize", lambda s: report_step(s, settings))
    builder.add_edge(START, "planner")
    builder.add_edge("planner", "supervisor")
    builder.add_conditional_edges("supervisor", lambda s: s["next_tool"],
                                  {n: n for n in [*nodes, "human_review", "finalize"]})
    for name in nodes:
        builder.add_edge(name, "supervisor")
    builder.add_edge("human_review", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)
