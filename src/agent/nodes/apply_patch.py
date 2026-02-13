from pathlib import Path

from src.agent.state import AgentState
from src.sandbox.executor import PatchApplier


async def apply_patch_sandbox(
    state: AgentState,
    patch_applier: PatchApplier | None = None,
) -> AgentState:
    if state.errors or not state.generated_diff:
        return state

    patch_applier = patch_applier or PatchApplier()

    repo_path = Path(state.repo_path)

    validation = patch_applier.validate_diff(state.generated_diff)

    if not validation.valid:
        state.errors.extend(validation.errors)
        return state

    result = patch_applier.apply_patch(
        repo_path=repo_path,
        diff_content=state.generated_diff,
        sandbox_id=state.sandbox_id,
    )

    state.patch_result = result
    state.patch_applied = result.success

    if not result.success:
        state.errors.append(f"Failed to apply patch: {result.error}")
    else:
        state.sandbox_id = result.sandbox_id

    return state
