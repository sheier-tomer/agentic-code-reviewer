import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.agent.state import CheckResult
from src.validation.checks.base import BaseCheck, MypyRunner, PytestRunner, RuffFormatRunner, RuffRunner, SemgrepRunner


@dataclass
class ValidationConfig:
    run_tests: bool = True
    run_lint: bool = True
    run_format: bool = True
    run_typecheck: bool = True
    run_security: bool = True

    test_path: str = "tests/"
    lint_path: str = "."
    typecheck_path: str = "src/"
    security_path: str = "src/"

    fail_fast: bool = True


class ValidationPipeline:
    def __init__(self, config: ValidationConfig | None = None):
        self.config = config or ValidationConfig()
        self._checks: list[tuple[str, BaseCheck]] = []

        self._setup_checks()

    def _setup_checks(self) -> None:
        if self.config.run_lint:
            self._checks.append(("lint", RuffRunner(self.config.lint_path)))

        if self.config.run_format:
            self._checks.append(("format", RuffFormatRunner(self.config.lint_path)))

        if self.config.run_typecheck:
            self._checks.append(("typecheck", MypyRunner(self.config.typecheck_path)))

        if self.config.run_security:
            self._checks.append(("security", SemgrepRunner(self.config.security_path)))

        if self.config.run_tests:
            self._checks.append(("tests", PytestRunner(self.config.test_path)))

    async def run(self, sandbox_id: str | None = None, cwd: str | None = None) -> dict[str, CheckResult]:
        results: dict[str, CheckResult] = {}

        for name, check in self._checks:
            result = await check.execute(sandbox_id=sandbox_id, cwd=cwd)
            results[name] = result

            if self.config.fail_fast and result.has_critical_failure:
                break

        return results

    async def run_parallel(
        self, sandbox_id: str | None = None, cwd: str | None = None
    ) -> dict[str, CheckResult]:
        tasks = [(name, check.execute(sandbox_id=sandbox_id, cwd=cwd)) for name, check in self._checks]

        results: dict[str, CheckResult] = {}
        completed = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)

        for (name, _), result in zip(tasks, completed):
            if isinstance(result, Exception):
                results[name] = CheckResult(
                    check_name=name,
                    passed=False,
                    output=str(result),
                    error_count=1,
                    warning_count=0,
                    details=[],
                    duration_ms=0,
                    timestamp=datetime.utcnow(),
                    has_critical_failure=True,
                )
            else:
                results[name] = result

        return results

    def get_summary(self, results: dict[str, CheckResult]) -> dict[str, Any]:
        total_passed = sum(1 for r in results.values() if r.passed)
        total_failed = sum(1 for r in results.values() if not r.passed)
        total_errors = sum(r.error_count for r in results.values())
        total_warnings = sum(r.warning_count for r in results.values())
        total_duration_ms = sum(r.duration_ms for r in results.values())

        has_critical = any(r.has_critical_failure for r in results.values())

        return {
            "total_checks": len(results),
            "passed": total_passed,
            "failed": total_failed,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "total_duration_ms": total_duration_ms,
            "has_critical_failure": has_critical,
            "all_passed": total_failed == 0 and not has_critical,
        }
