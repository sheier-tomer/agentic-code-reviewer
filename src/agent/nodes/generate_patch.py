from pathlib import Path
from typing import Any

from src.agent.state import AgentState
from src.agent.tools.diff_generator import DiffGenerator
from src.config import settings


async def generate_patch(
    state: AgentState,
) -> AgentState:
    if state.errors or not state.change_plan:
        return state

    diff_generator = DiffGenerator()
    all_diffs: list[str] = []
    repo_path = Path(state.repo_path)

    for change in state.change_plan.changes:
        file_path = Path(change.file_path)
        
        if file_path.is_absolute():
            full_path = file_path
            relative_path = str(file_path.relative_to(repo_path)) if file_path.is_relative_to(repo_path) else file_path.name
        else:
            full_path = repo_path / change.file_path
            relative_path = change.file_path

        if not full_path.exists():
            state.errors.append(f"File not found: {change.file_path}")
            continue

        try:
            current_content = full_path.read_text(encoding="utf-8")
        except Exception as e:
            state.errors.append(f"Failed to read {change.file_path}: {e}")
            continue

        context = _build_context(state.retrieved_chunks, str(full_path))

        try:
            diff = await diff_generator.generate_diff(
                file_path=relative_path,
                current_content=current_content,
                description=change.description,
                context=context,
            )

            if diff:
                all_diffs.append(diff)

        except Exception as e:
            state.errors.append(f"Failed to generate diff for {change.file_path}: {e}")
            continue

    if all_diffs:
        state.generated_diff = "\n\n".join(all_diffs)

        total_lines = sum(
            diff.count("\n+") + diff.count("\n-") for diff in all_diffs
        )
        if total_lines > settings.max_diff_lines:
            state.errors.append(
                f"Generated diff too large: {total_lines} lines > {settings.max_diff_lines}"
            )
            state.generated_diff = None
    else:
        state.errors.append("No diffs generated")

    return state


def _build_context(chunks: list[Any], file_path: str) -> str:
    relevant = [c for c in chunks if c.file_path == file_path]

    if not relevant:
        return "No additional context available."

    parts = []
    for chunk in relevant[:5]:
        if chunk.docstring:
            parts.append(f"Documentation for {chunk.symbol_name}:\n{chunk.docstring}")

    return "\n\n".join(parts) if parts else "No additional context available."
