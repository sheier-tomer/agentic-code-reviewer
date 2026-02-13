import json
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from src.config import settings


@dataclass
class JudgeScore:
    code_quality: float
    error_handling: float
    documentation: float
    edge_cases: float
    overall: float
    concerns: list[str]
    recommendation: str


class LLMJudge:
    SYSTEM_PROMPT = """You are a senior code reviewer evaluating code changes.
Your role is to provide an objective assessment of code quality, not to make merge decisions.

Evaluate the changes on:
1. Code quality and style consistency (1-10)
2. Error handling completeness (1-10)
3. Documentation quality (1-10)
4. Potential for bugs or edge cases (1-10)

Provide your scores and concerns in JSON format."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model or settings.llm_model
        self.client = AsyncOpenAI(
            api_key=api_key or settings.openai_api_key,
            base_url=base_url or settings.openai_base_url,
        )

    async def judge(self, diff: str, explanation: str | None = None) -> JudgeScore:
        prompt = f"""Review this code change for quality and safety.

Diff:
```
{diff}
```

{"Context: " + explanation if explanation else ""}

Return JSON with this structure:
{{
    "scores": {{
        "code_quality": <1-10>,
        "error_handling": <1-10>,
        "documentation": <1-10>,
        "edge_cases": <1-10>
    }},
    "concerns": ["<list of specific concerns>"],
    "recommendation": "<approve/review/reject>"
}}
"""

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        return self._parse_response(content)

    def _parse_response(self, content: str | None) -> JudgeScore:
        if not content:
            return JudgeScore(
                code_quality=5.0,
                error_handling=5.0,
                documentation=5.0,
                edge_cases=5.0,
                overall=5.0,
                concerns=["Unable to parse LLM response"],
                recommendation="review",
            )

        try:
            data = json.loads(content)
            scores = data.get("scores", {})

            code_quality = float(scores.get("code_quality", 5))
            error_handling = float(scores.get("error_handling", 5))
            documentation = float(scores.get("documentation", 5))
            edge_cases = float(scores.get("edge_cases", 5))

            overall = (code_quality + error_handling + documentation + edge_cases) / 4

            return JudgeScore(
                code_quality=code_quality,
                error_handling=error_handling,
                documentation=documentation,
                edge_cases=edge_cases,
                overall=overall,
                concerns=data.get("concerns", []),
                recommendation=data.get("recommendation", "review"),
            )
        except (json.JSONDecodeError, ValueError) as e:
            return JudgeScore(
                code_quality=5.0,
                error_handling=5.0,
                documentation=5.0,
                edge_cases=5.0,
                overall=5.0,
                concerns=[f"Parse error: {str(e)}"],
                recommendation="review",
            )
