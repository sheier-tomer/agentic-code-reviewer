import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.agent.state import CheckResult, Decision, Scores
from src.config import settings


@dataclass
class ScoringWeights:
    tests: float = 0.40
    lint: float = 0.15
    format: float = 0.05
    typecheck: float = 0.25
    security: float = 0.15


@dataclass
class ScoringThresholds:
    quality_approve: float = 80.0
    quality_review: float = 60.0
    risk_review: float = 0.3
    risk_reject: float = 0.7


@dataclass
class ScoringResult:
    quality_score: float
    risk_score: float
    decision: Decision
    scores: Scores
    gate_failures: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)


class ScoringEngine:
    def __init__(
        self,
        weights: ScoringWeights | None = None,
        thresholds: ScoringThresholds | None = None,
    ):
        self.weights = weights or ScoringWeights()
        self.thresholds = thresholds or ScoringThresholds()

    def compute_scores(
        self,
        check_results: dict[str, CheckResult],
        diff_content: str | None = None,
        affected_files: list[str] | None = None,
    ) -> ScoringResult:
        scores = self._compute_check_scores(check_results)
        quality_score = self._compute_quality_score(scores)
        risk_score = 0.0
        risk_flags: list[str] = []

        if diff_content and affected_files:
            risk_score, risk_flags = self._compute_risk_score(diff_content, affected_files, check_results)

        gate_failures = self._check_hard_gates(check_results, affected_files)

        decision = self._compute_decision(quality_score, risk_score, gate_failures)

        return ScoringResult(
            quality_score=quality_score,
            risk_score=risk_score,
            decision=decision,
            scores=scores,
            gate_failures=gate_failures,
            risk_flags=risk_flags,
        )

    def _compute_check_scores(self, check_results: dict[str, CheckResult]) -> Scores:
        test_score = 100.0
        lint_score = 100.0
        typecheck_score = 100.0
        security_score = 100.0
        has_hard_gate_failure = False

        if "tests" in check_results:
            result = check_results["tests"]
            if not result.passed:
                test_score = 0.0
                has_hard_gate_failure = True

        if "lint" in check_results:
            result = check_results["lint"]
            error_penalty = min(result.error_count * 5, 50)
            warning_penalty = min(result.warning_count * 2, 20)
            lint_score = max(100 - error_penalty - warning_penalty, 0)

        if "format" in check_results:
            result = check_results["format"]
            if not result.passed:
                lint_score = max(lint_score - 10, 0)

        if "typecheck" in check_results:
            result = check_results["typecheck"]
            error_penalty = min(result.error_count * 10, 60)
            warning_penalty = min(result.warning_count * 2, 20)
            typecheck_score = max(100 - error_penalty - warning_penalty, 0)

        if "security" in check_results:
            result = check_results["security"]
            critical_penalty = result.error_count * 40
            high_penalty = 0
            for detail in result.details:
                if detail.severity == "error":
                    high_penalty += 20
            medium_penalty = result.warning_count * 5
            security_score = max(100 - critical_penalty - high_penalty - medium_penalty, 0)
            if result.has_critical_failure:
                has_hard_gate_failure = True

        return Scores(
            quality_score=0.0,
            risk_score=0.0,
            test_score=test_score,
            lint_score=lint_score,
            typecheck_score=typecheck_score,
            security_score=security_score,
            has_hard_gate_failure=has_hard_gate_failure,
        )

    def _compute_quality_score(self, scores: Scores) -> float:
        quality = (
            scores.test_score * self.weights.tests
            + scores.lint_score * self.weights.lint
            + scores.typecheck_score * self.weights.typecheck
            + scores.security_score * self.weights.security
        )
        return round(quality, 2)

    def _compute_risk_score(
        self,
        diff_content: str,
        affected_files: list[str],
        check_results: dict[str, CheckResult],
    ) -> tuple[float, list[str]]:
        flags: list[str] = []

        diff_size_risk = self._compute_diff_size_risk(diff_content, flags)
        sensitive_path_risk = self._compute_sensitive_path_risk(affected_files, flags)
        test_coverage_risk = self._compute_test_coverage_risk(affected_files, check_results, flags)
        complexity_risk = self._compute_complexity_risk(diff_content, flags)
        dependency_risk = self._compute_dependency_risk(affected_files, flags)
        new_code_risk = self._compute_new_code_risk(diff_content, flags)

        combined = (
            diff_size_risk * 0.15
            + sensitive_path_risk * 0.25
            + test_coverage_risk * 0.20
            + complexity_risk * 0.10
            + dependency_risk * 0.15
            + new_code_risk * 0.15
        )

        return round(combined, 3), flags

    def _compute_diff_size_risk(self, diff_content: str, flags: list[str]) -> float:
        lines_added = diff_content.count("\n+")
        lines_removed = diff_content.count("\n-")

        total_lines = lines_added + lines_removed

        if total_lines > 500:
            flags.append(f"Large diff: {total_lines} lines changed")
            return 1.0
        elif total_lines > 200:
            flags.append(f"Moderate diff: {total_lines} lines changed")
            return 0.6
        elif total_lines > 100:
            return 0.3
        return 0.0

    def _compute_sensitive_path_risk(self, affected_files: list[str], flags: list[str]) -> float:
        max_risk = 0.0

        for file_path in affected_files:
            for sensitive_path in settings.sensitive_paths:
                if sensitive_path.rstrip("/") in file_path:
                    flags.append(f"Sensitive file modified: {file_path}")
                    max_risk = max(max_risk, 0.8)

        if any(kw in " ".join(affected_files) for kw in ["auth", "security", "payment", "secret", "credential"]):
            flags.append("Sensitive keywords in file paths")
            max_risk = max(max_risk, 0.9)

        return max_risk

    def _compute_test_coverage_risk(
        self, affected_files: list[str], check_results: dict[str, CheckResult], flags: list[str]
    ) -> float:
        code_files = [f for f in affected_files if f.endswith(".py") and not f.startswith("tests/")]
        test_files = [f for f in affected_files if f.startswith("tests/")]

        if not code_files:
            return 0.0

        if not test_files and len(code_files) > 0:
            flags.append("Code changes without test updates")
            return 0.5

        return 0.0

    def _compute_complexity_risk(self, diff_content: str, flags: list[str]) -> float:
        complexity_keywords = ["if ", "elif ", "for ", "while ", "try:", "except ", "with "]
        complexity_count = sum(diff_content.count(kw) for kw in complexity_keywords)

        if complexity_count > 20:
            flags.append(f"High complexity change: {complexity_count} control structures")
            return 0.8
        elif complexity_count > 10:
            return 0.4
        return 0.0

    def _compute_dependency_risk(self, affected_files: list[str], flags: list[str]) -> float:
        dependency_files = [
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "Pipfile",
            "poetry.lock",
        ]

        for file_path in affected_files:
            for dep_file in dependency_files:
                if dep_file in file_path:
                    flags.append(f"Dependency file modified: {file_path}")
                    return 0.7

        return 0.0

    def _compute_new_code_risk(self, diff_content: str, flags: list[str]) -> float:
        added_lines = [line[1:] for line in diff_content.split("\n") if line.startswith("+") and not line.startswith("+++")]
        modified_lines = [line[1:] for line in diff_content.split("\n") if line.startswith("-") and not line.startswith("---")]

        total_changes = len(added_lines) + len(modified_lines)
        if total_changes == 0:
            return 0.0

        new_ratio = len(added_lines) / total_changes

        if new_ratio > 0.8:
            flags.append("Mostly new code (low refactor ratio)")
            return 0.5

        return 0.0

    def _check_hard_gates(
        self, check_results: dict[str, CheckResult], affected_files: list[str] | None
    ) -> list[str]:
        failures: list[str] = []

        if "tests" in check_results and not check_results["tests"].passed:
            failures.append("Tests failed")

        if "security" in check_results and check_results["security"].has_critical_failure:
            failures.append("Critical security issue detected")

        if affected_files and len(affected_files) > settings.max_files_per_run:
            failures.append(f"Too many files affected: {len(affected_files)} > {settings.max_files_per_run}")

        return failures

    def _compute_decision(
        self, quality_score: float, risk_score: float, gate_failures: list[str]
    ) -> Decision:
        if gate_failures:
            return Decision.REJECT

        if risk_score >= self.thresholds.risk_reject:
            return Decision.REJECT

        if risk_score >= self.thresholds.risk_review:
            return Decision.NEEDS_REVIEW

        if quality_score < self.thresholds.quality_review:
            return Decision.REJECT

        if quality_score < self.thresholds.quality_approve:
            return Decision.NEEDS_REVIEW

        return Decision.AUTO_APPROVE
