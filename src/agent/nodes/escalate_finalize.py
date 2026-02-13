from datetime import datetime

from src.agent.state import AgentState, Decision, RunStatus
from src.db.audit import AuditLogger


async def escalate_or_finalize(
    state: AgentState,
    audit_logger: AuditLogger | None = None,
) -> AgentState:
    state.completed_at = datetime.utcnow()

    if state.errors:
        state.status = RunStatus.FAILED
        state.decision = Decision.REJECT
    else:
        state.status = RunStatus.COMPLETED

    if audit_logger:
        await audit_logger.log(
            run_id=state.run_id,
            event_type="RUN_COMPLETED",
            event_data={
                "status": state.status,
                "decision": state.decision.value if state.decision else None,
                "quality_score": state.quality_score,
                "risk_score": state.risk_score,
                "errors": state.errors,
                "files_affected": state.affected_files,
            },
        )

    return state
