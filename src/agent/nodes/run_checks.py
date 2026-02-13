from typing import Any

from src.agent.state import AgentState
from src.validation.pipeline import ValidationPipeline, ValidationConfig


async def run_checks(
    state: AgentState,
    config: ValidationConfig | None = None,
) -> AgentState:
    if state.errors or not state.patch_applied:
        return state

    config = config or ValidationConfig()
    pipeline = ValidationPipeline(config)

    try:
        results = await pipeline.run(cwd=state.repo_path)
        state.check_results = results

    except Exception as e:
        state.errors.append(f"Failed to run checks: {e}")

    return state
