from src.agent.state import AgentState
from src.agent.tools.llm import LLMClient


SYSTEM_PROMPT = """You are a code review assistant. Your task is to explain code changes clearly and concisely.

Provide:
1. A brief summary of what was changed
2. The reasoning behind each change
3. Any potential concerns or edge cases
4. References to specific lines where relevant

Be factual and avoid speculation."""


async def explain_diff(
    state: AgentState,
    llm: LLMClient | None = None,
) -> AgentState:
    if not state.generated_diff:
        state.explanation = "No changes were made."
        return state

    llm = llm or LLMClient()

    check_summary = _format_check_summary(state.check_results)

    prompt = f"""Explain the following code changes:

Task: {state.task_description}

Decision: {state.decision}
Quality Score: {state.quality_score}
Risk Score: {state.risk_score}

Diff:
```
{state.generated_diff}
```

Validation Results:
{check_summary}

Provide a clear, concise explanation of the changes."""

    try:
        state.explanation = await llm.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
        )
    except Exception as e:
        state.explanation = f"Failed to generate explanation: {e}"

    state.final_diff = state.generated_diff

    return state


def _format_check_summary(check_results: dict) -> str:
    if not check_results:
        return "No validation results available."

    lines = []
    for name, result in check_results.items():
        status = "✓ PASSED" if result.passed else "✗ FAILED"
        errors = f" ({result.error_count} errors, {result.warning_count} warnings)"
        lines.append(f"- {name}: {status}{errors if not result.passed else ''}")

    return "\n".join(lines)
