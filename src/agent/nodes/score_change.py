from src.agent.state import AgentState, Decision
from src.scoring.engine import ScoringEngine


async def score_change(
    state: AgentState,
) -> AgentState:
    if state.errors:
        state.decision = Decision.REJECT
        return state

    engine = ScoringEngine()

    result = engine.compute_scores(
        check_results=state.check_results,
        diff_content=state.generated_diff,
        affected_files=state.affected_files,
    )

    state.quality_score = result.quality_score
    state.risk_score = result.risk_score
    state.decision = result.decision

    if result.gate_failures:
        state.errors.extend(result.gate_failures)

    return state
