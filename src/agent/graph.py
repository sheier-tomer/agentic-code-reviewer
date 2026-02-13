from typing import Literal

from langgraph.graph import END, StateGraph

from src.agent.nodes import (
    apply_patch_sandbox,
    escalate_or_finalize,
    explain_diff,
    generate_patch,
    ingest_repo,
    plan_change,
    retrieve_context,
    run_checks,
    score_change,
)
from src.agent.state import AgentState, RunStatus


def should_continue(state: AgentState) -> Literal["continue", "end"]:
    if state.errors:
        return "end"
    if state.retry_count > 2:
        return "end"
    return "continue"


def route_after_patch(state: AgentState) -> Literal["run_checks", "retry", "end"]:
    if state.patch_result and not state.patch_result.success:
        if state.retry_count < 2:
            return "retry"
        return "end"
    return "run_checks"


def route_after_scoring(state: AgentState) -> Literal["explain", "end"]:
    if state.errors:
        return "end"
    return "explain"


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("ingest_repo", ingest_repo)
    workflow.add_node("retrieve_context", retrieve_context_node)
    workflow.add_node("plan_change", plan_change)
    workflow.add_node("generate_patch", generate_patch)
    workflow.add_node("apply_patch", apply_patch_sandbox)
    workflow.add_node("run_checks", run_checks)
    workflow.add_node("score_change", score_change)
    workflow.add_node("explain_diff", explain_diff)
    workflow.add_node("escalate_finalize", escalate_or_finalize)

    workflow.set_entry_point("ingest_repo")

    workflow.add_edge("ingest_repo", "retrieve_context")
    workflow.add_conditional_edges(
        "retrieve_context",
        should_continue,
        {"continue": "plan_change", "end": "escalate_finalize"},
    )
    workflow.add_conditional_edges(
        "plan_change",
        should_continue,
        {"continue": "generate_patch", "end": "escalate_finalize"},
    )
    workflow.add_conditional_edges(
        "generate_patch",
        should_continue,
        {"continue": "apply_patch", "end": "escalate_finalize"},
    )
    workflow.add_conditional_edges(
        "apply_patch",
        route_after_patch,
        {"run_checks": "run_checks", "retry": "generate_patch", "end": "escalate_finalize"},
    )
    workflow.add_conditional_edges(
        "run_checks",
        should_continue,
        {"continue": "score_change", "end": "escalate_finalize"},
    )
    workflow.add_conditional_edges(
        "score_change",
        route_after_scoring,
        {"explain": "explain_diff", "end": "escalate_finalize"},
    )
    workflow.add_edge("explain_diff", "escalate_finalize")
    workflow.add_edge("escalate_finalize", END)

    return workflow.compile()


async def retrieve_context_node(state: AgentState) -> AgentState:
    from src.db.models import async_session

    async with async_session() as db:
        return await retrieve_context(state, db)


graph = build_graph()
