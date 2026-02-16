import json
from typing import Any

from pydantic import BaseModel

from src.agent.state import AgentState, ChangePlan, PlannedChange
from src.agent.tools.llm import LLMClient
from src.config import settings


class PlanResponse(BaseModel):
    description: str
    files_to_modify: list[str]
    changes: list[dict[str, Any]]
    rationale: str
    confidence: float


SYSTEM_PROMPT = """You are a senior software architect planning code changes.

Analyze the requested change and the provided code context to create a structured change plan.

RULES:
1. Keep changes minimal and focused
2. Limit scope to essential modifications
3. Consider dependencies and side effects
4. Provide clear rationale for each change
5. Set confidence level (0.0-1.0) based on context clarity

OUTPUT: JSON with the following structure:
{
    "description": "Brief description of the planned changes",
    "files_to_modify": ["list of file paths"],
    "changes": [
        {
            "file_path": "<actual file path from Code Context>",
            "change_type": "modify|add|refactor",
            "description": "What will be changed",
            "affected_symbols": ["list of function/class names"]
        }
    ],
    "rationale": "Why these changes are needed",
    "confidence": 0.0-1.0,
    "estimated_impact": "low|medium|high"
}

IMPORTANT: Only use file paths that exist in the Code Context section above. Do not invent or use placeholder paths."""


async def plan_change(
    state: AgentState,
    llm: LLMClient | None = None,
) -> AgentState:
    if state.errors:
        return state

    llm = llm or LLMClient()

    context_parts = []
    for chunk in state.retrieved_chunks[:10]:
        context_parts.append(
            f"File: {chunk.file_path}\n"
            f"Symbol: {chunk.symbol_name or 'module'}\n"
            f"Lines: {chunk.start_line}-{chunk.end_line}\n"
            f"```\n{chunk.content}\n```\n"
        )

    context = "\n---\n".join(context_parts) if context_parts else "No relevant code context found. Analyze the repository structure."

    prompt = f"""Task: {state.task_description}
Task Type: {state.task_type}

Code Context:
{context}

Affected Files: {', '.join(state.affected_files) if state.affected_files else 'All relevant files'}

Create a structured change plan. Output JSON only."""

    try:
        response = await llm.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
        )

        if not response or not response.strip():
            state.errors.append("LLM returned empty response")
            return state

        response_text = response.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        plan_data = json.loads(response_text)

        state.change_plan = ChangePlan(
            description=plan_data.get("description", ""),
            files_to_modify=plan_data.get("files_to_modify", []),
            changes=[
                PlannedChange(
                    file_path=c.get("file_path", ""),
                    change_type=c.get("change_type", "modify"),
                    description=c.get("description", ""),
                    affected_symbols=c.get("affected_symbols", []),
                )
                for c in plan_data.get("changes", [])
            ],
            rationale=plan_data.get("rationale", ""),
            confidence=plan_data.get("confidence", 0.5),
            estimated_impact=plan_data.get("estimated_impact", "medium"),
        )

        state.plan_confidence = state.change_plan.confidence

        if len(state.change_plan.files_to_modify) > settings.max_files_per_run:
            state.errors.append(
                f"Plan affects too many files: {len(state.change_plan.files_to_modify)} > {settings.max_files_per_run}"
            )

        state.affected_files = state.change_plan.files_to_modify

    except json.JSONDecodeError as e:
        state.errors.append(f"Failed to parse plan: {e}")
    except Exception as e:
        state.errors.append(f"Failed to generate plan: {e}")

    return state
