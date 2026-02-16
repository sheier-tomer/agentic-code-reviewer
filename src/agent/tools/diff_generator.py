import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from src.agent.tools.llm import LLMClient


@dataclass
class DiffContext:
    before_content: str
    after_content: str
    file_path: str
    start_line: int
    end_line: int


class DiffGenerationRequest(BaseModel):
    file_path: str
    current_content: str
    description: str
    context: str


class DiffGenerator:
    SYSTEM_PROMPT = """You are an expert code refactoring assistant.
Your task is to generate a unified diff for the requested changes.

RULES:
1. Output ONLY a valid unified diff format
2. Include 3 lines of context before and after each change
3. Use proper diff headers (--- a/path and +++ b/path)
4. Do not add comments explaining the diff
5. Keep changes minimal and focused
6. Preserve existing code style and formatting
7. Do not modify unrelated code"""

    DIFF_PROMPT = """Generate a unified diff for the following change request.

File: {file_path}

Current content:
```
{current_content}
```

Requested change:
{description}

Additional context:
{context}

Output the unified diff:"""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    async def generate_diff(
        self,
        file_path: str,
        current_content: str,
        description: str,
        context: str | None = None,
    ) -> str:
        prompt = self.DIFF_PROMPT.format(
            file_path=file_path,
            current_content=current_content,
            description=description,
            context=context or "No additional context provided.",
        )

        response = await self.llm.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.0,
        )

        diff = self._extract_diff(response)
        return self._normalize_hunk_headers(diff)

    def _extract_diff(self, response: str) -> str:
        diff_pattern = r"```diff\n(.*?)\n```"
        match = re.search(diff_pattern, response, re.DOTALL)

        if match:
            return match.group(1).strip()

        if response.startswith("---") or response.startswith("diff --git"):
            return response.strip()

        lines = response.split("\n")
        diff_lines = []
        in_diff = False

        for line in lines:
            if line.startswith("---") or line.startswith("diff --git"):
                in_diff = True
            if in_diff:
                diff_lines.append(line)

        return "\n".join(diff_lines).strip() if diff_lines else response.strip()

    def _normalize_hunk_headers(self, diff: str) -> str:
        lines = diff.split("\n")
        result = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            if line.startswith("@@"):
                hunk_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("---") and not lines[i].startswith("diff --git"):
                    hunk_lines.append(lines[i])
                    i += 1
                
                cleaned_hunk = self._clean_hunk(hunk_lines)
                
                removed = sum(1 for l in cleaned_hunk if l.startswith("-") and not l.startswith("---"))
                added = sum(1 for l in cleaned_hunk if l.startswith("+") and not l.startswith("+++"))
                context = sum(1 for l in cleaned_hunk if not l.startswith(("+", "-")))
                
                match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
                if match:
                    old_start = int(match.group(1))
                    new_start = int(match.group(2))
                    old_count = removed + context
                    new_count = added + context
                    
                    if old_count == 0:
                        old_count = 1
                        old_start = 1
                    if new_count == 0:
                        new_count = 1
                        new_start = 1
                    
                    result.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@")
                else:
                    result.append(line)
                result.extend(cleaned_hunk)
            else:
                result.append(line)
                i += 1
        
        return "\n".join(result)

    def _clean_hunk(self, hunk_lines: list[str]) -> list[str]:
        cleaned = []
        for line in hunk_lines:
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
                content = line[1:]
                stripped = content.rstrip()
                if stripped == "" and content != "":
                    continue
                cleaned.append(line[0] + stripped)
            elif line == "" or line == " ":
                cleaned.append("")
            else:
                cleaned.append(line.rstrip())
        
        return cleaned

    async def generate_multi_file_diff(
        self,
        files: list[DiffGenerationRequest],
    ) -> str:
        diffs = []

        for file_req in files:
            diff = await self.generate_diff(
                file_path=file_req.file_path,
                current_content=file_req.current_content,
                description=file_req.description,
                context=file_req.context,
            )
            diffs.append(diff)

        return "\n\n".join(diffs)


def format_diff_for_display(diff: str) -> str:
    lines = diff.split("\n")
    formatted_lines = []

    for line in lines:
        if line.startswith("+") and not line.startswith("+++"):
            formatted_lines.append(f"\033[32m{line}\033[0m")
        elif line.startswith("-") and not line.startswith("---"):
            formatted_lines.append(f"\033[31m{line}\033[0m")
        elif line.startswith("@@"):
            formatted_lines.append(f"\033[36m{line}\033[0m")
        else:
            formatted_lines.append(line)

    return "\n".join(formatted_lines)
