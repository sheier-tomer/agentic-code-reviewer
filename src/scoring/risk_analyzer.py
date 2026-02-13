from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import settings


@dataclass
class RiskFactor:
    name: str
    weight: float
    value: float
    contribution: float
    flags: list[str]


class RiskAnalyzer:
    def __init__(self, sensitive_paths: list[str] | None = None):
        self.sensitive_paths = sensitive_paths or settings.sensitive_paths

    def analyze(
        self,
        diff_content: str,
        affected_files: list[str],
        check_results: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        factors: list[RiskFactor] = []

        diff_size_factor = self._analyze_diff_size(diff_content)
        factors.append(diff_size_factor)

        sensitive_path_factor = self._analyze_sensitive_paths(affected_files)
        factors.append(sensitive_path_factor)

        complexity_factor = self._analyze_complexity(diff_content)
        factors.append(complexity_factor)

        dependency_factor = self._analyze_dependencies(affected_files)
        factors.append(dependency_factor)

        coverage_factor = self._analyze_coverage(affected_files, check_results)
        factors.append(coverage_factor)

        total_weight = sum(f.weight for f in factors)
        combined_score = sum(f.contribution for f in factors) / total_weight if total_weight > 0 else 0

        all_flags: list[str] = []
        for f in factors:
            all_flags.extend(f.flags)

        return {
            "combined_score": round(combined_score, 3),
            "factors": [
                {
                    "name": f.name,
                    "weight": f.weight,
                    "value": f.value,
                    "contribution": f.contribution,
                    "flags": f.flags,
                }
                for f in factors
            ],
            "flags": all_flags,
            "is_high_risk": combined_score >= settings.scoring_risk_threshold_reject,
            "needs_review": combined_score >= settings.scoring_risk_threshold_review,
        }

    def _analyze_diff_size(self, diff_content: str) -> RiskFactor:
        lines = diff_content.split("\n")
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        total = added + removed

        flags: list[str] = []
        value = 0.0

        if total > 500:
            value = 1.0
            flags.append(f"Very large diff ({total} lines)")
        elif total > 200:
            value = 0.7
            flags.append(f"Large diff ({total} lines)")
        elif total > 100:
            value = 0.4
        elif total > 50:
            value = 0.2

        return RiskFactor(
            name="diff_size",
            weight=0.15,
            value=value,
            contribution=value * 0.15,
            flags=flags,
        )

    def _analyze_sensitive_paths(self, affected_files: list[str]) -> RiskFactor:
        flags: list[str] = []
        max_risk = 0.0

        for file_path in affected_files:
            file_lower = file_path.lower()

            for sensitive_path in self.sensitive_paths:
                sensitive_lower = sensitive_path.lower().rstrip("/")
                if sensitive_lower in file_lower:
                    risk = 0.9
                    flags.append(f"Sensitive path: {file_path}")
                    max_risk = max(max_risk, risk)

            sensitive_keywords = [
                "auth",
                "login",
                "password",
                "secret",
                "key",
                "token",
                "credential",
                "payment",
                "billing",
                "config",
            ]
            for keyword in sensitive_keywords:
                if keyword in file_lower:
                    risk = 0.6
                    flags.append(f"Sensitive keyword in path: {file_path}")
                    max_risk = max(max_risk, risk)

        return RiskFactor(
            name="sensitive_paths",
            weight=0.25,
            value=max_risk,
            contribution=max_risk * 0.25,
            flags=flags,
        )

    def _analyze_complexity(self, diff_content: str) -> RiskFactor:
        control_structures = [
            "if ",
            "elif ",
            "else:",
            "for ",
            "while ",
            "try:",
            "except ",
            "finally:",
            "with ",
            "match ",
            "case ",
        ]

        count = sum(diff_content.count(s) for s in control_structures)

        flags: list[str] = []
        value = 0.0

        if count > 30:
            value = 1.0
            flags.append(f"Very high complexity ({count} control structures)")
        elif count > 20:
            value = 0.7
            flags.append(f"High complexity ({count} control structures)")
        elif count > 10:
            value = 0.4
        elif count > 5:
            value = 0.2

        return RiskFactor(
            name="complexity",
            weight=0.10,
            value=value,
            contribution=value * 0.10,
            flags=flags,
        )

    def _analyze_dependencies(self, affected_files: list[str]) -> RiskFactor:
        dependency_files = {
            "requirements.txt": 0.8,
            "pyproject.toml": 0.8,
            "setup.py": 0.8,
            "Pipfile": 0.8,
            "poetry.lock": 0.9,
            "Pipfile.lock": 0.9,
        }

        flags: list[str] = []
        max_risk = 0.0

        for file_path in affected_files:
            file_name = Path(file_path).name
            if file_name in dependency_files:
                risk = dependency_files[file_name]
                flags.append(f"Dependency file changed: {file_name}")
                max_risk = max(max_risk, risk)

        return RiskFactor(
            name="dependencies",
            weight=0.15,
            value=max_risk,
            contribution=max_risk * 0.15,
            flags=flags,
        )

    def _analyze_coverage(
        self, affected_files: list[str], check_results: dict[str, Any] | None
    ) -> RiskFactor:
        flags: list[str] = []
        value = 0.0

        source_files = [
            f
            for f in affected_files
            if f.endswith(".py") and not f.startswith("tests/") and not f.startswith("test_")
        ]
        test_files = [f for f in affected_files if f.startswith("tests/") or f.startswith("test_")]

        if source_files and not test_files:
            value = 0.5
            flags.append("Source changes without test updates")

        return RiskFactor(
            name="test_coverage",
            weight=0.20,
            value=value,
            contribution=value * 0.20,
            flags=flags,
        )
