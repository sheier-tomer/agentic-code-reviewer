import asyncio
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agent.state import CheckDetail, CheckResult


@dataclass
class CheckConfig:
    timeout_seconds: int = 120
    cwd: str | None = None
    env: dict[str, str] | None = None


class BaseCheck(ABC):
    name: str
    timeout_seconds: int = 120

    @abstractmethod
    async def execute(self, sandbox_id: str | None = None, cwd: str | None = None) -> CheckResult:
        pass

    def _run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        timeout = timeout or self.timeout_seconds
        cwd = cwd or "."

        merged_env = subprocess.os.environ.copy()
        if env:
            merged_env.update(env)

        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=merged_env,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return -1, "", str(e)


class PytestRunner(BaseCheck):
    name = "tests"
    timeout_seconds = 120

    def __init__(self, test_path: str = "tests/", extra_args: list[str] | None = None):
        self.test_path = test_path
        self.extra_args = extra_args or []

    async def execute(self, sandbox_id: str | None = None, cwd: str | None = None) -> CheckResult:
        start_time = datetime.utcnow()

        command = [
            "pytest",
            self.test_path,
            "-v",
            "--tb=short",
            "--no-header",
            "-q",
            *self.extra_args,
        ]

        returncode, stdout, stderr = self._run_command(command, cwd=cwd, timeout=self.timeout_seconds)

        output = f"{stdout}\n{stderr}".strip()
        passed = returncode == 0

        error_count, warning_count, details = self._parse_output(output)

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return CheckResult(
            check_name=self.name,
            passed=passed,
            output=output,
            error_count=error_count,
            warning_count=warning_count,
            details=details,
            duration_ms=duration_ms,
            timestamp=datetime.utcnow(),
            has_critical_failure=not passed,
        )

    def _parse_output(self, output: str) -> tuple[int, int, list[CheckDetail]]:
        details: list[CheckDetail] = []
        error_count = 0
        warning_count = 0

        lines = output.split("\n")
        current_file = ""

        for line in lines:
            if line.startswith("tests/") or "::" in line:
                if "FAILED" in line:
                    error_count += 1
                    parts = line.split("::")
                    if parts:
                        file_part = parts[0].strip()
                        if " " in file_part:
                            file_part = file_part.split()[0]
                        details.append(
                            CheckDetail(
                                file_path=file_part,
                                line=0,
                                column=0,
                                severity="error",
                                message=line.strip(),
                                rule_id="test_failure",
                            )
                        )
                elif "ERROR" in line:
                    error_count += 1

            if " passed" in line or " failed" in line:
                pass_count = 0
                fail_count = 0
                for part in line.split():
                    if "passed" in part:
                        try:
                            pass_count = int(part.replace("passed", ""))
                        except ValueError:
                            pass
                    if "failed" in part:
                        try:
                            fail_count = int(part.replace("failed", ""))
                        except ValueError:
                            pass
                error_count = fail_count

        return error_count, warning_count, details


class RuffRunner(BaseCheck):
    name = "lint"
    timeout_seconds = 30

    def __init__(self, target_path: str = ".", extra_args: list[str] | None = None):
        self.target_path = target_path
        self.extra_args = extra_args or []

    async def execute(self, sandbox_id: str | None = None, cwd: str | None = None) -> CheckResult:
        start_time = datetime.utcnow()

        command = ["ruff", "check", self.target_path, "--output-format=json", *self.extra_args]

        returncode, stdout, stderr = self._run_command(command, cwd=cwd, timeout=self.timeout_seconds)

        output = f"{stdout}\n{stderr}".strip()
        passed = returncode == 0

        error_count, warning_count, details = self._parse_output(stdout)

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return CheckResult(
            check_name=self.name,
            passed=passed,
            output=output,
            error_count=error_count,
            warning_count=warning_count,
            details=details,
            duration_ms=duration_ms,
            timestamp=datetime.utcnow(),
            has_critical_failure=False,
        )

    def _parse_output(self, output: str) -> tuple[int, int, list[CheckDetail]]:
        import json

        details: list[CheckDetail] = []
        error_count = 0
        warning_count = 0

        try:
            results = json.loads(output) if output.strip() else []
            for item in results:
                severity = "error" if item.get("fix", None) is not None else "warning"
                if severity == "error":
                    error_count += 1
                else:
                    warning_count += 1

                details.append(
                    CheckDetail(
                        file_path=item.get("filename", ""),
                        line=item.get("location", {}).get("row", 0),
                        column=item.get("location", {}).get("column", 0),
                        severity=severity,
                        message=item.get("message", ""),
                        rule_id=item.get("code", ""),
                    )
                )
        except json.JSONDecodeError:
            if "error" in output.lower():
                error_count = 1
                details.append(
                    CheckDetail(
                        file_path="",
                        line=0,
                        column=0,
                        severity="error",
                        message=output,
                        rule_id="parse_error",
                    )
                )

        return error_count, warning_count, details


class RuffFormatRunner(BaseCheck):
    name = "format"
    timeout_seconds = 30

    def __init__(self, target_path: str = "."):
        self.target_path = target_path

    async def execute(self, sandbox_id: str | None = None, cwd: str | None = None) -> CheckResult:
        start_time = datetime.utcnow()

        command = ["ruff", "format", "--check", self.target_path]

        returncode, stdout, stderr = self._run_command(command, cwd=cwd, timeout=self.timeout_seconds)

        output = f"{stdout}\n{stderr}".strip()
        passed = returncode == 0

        details: list[CheckDetail] = []
        error_count = 0

        for line in output.split("\n"):
            if "would reformat" in line:
                error_count += 1
                parts = line.split()
                if parts:
                    details.append(
                        CheckDetail(
                            file_path=parts[-1] if parts else "",
                            line=0,
                            column=0,
                            severity="error",
                            message="File needs reformatting",
                            rule_id="format",
                        )
                    )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return CheckResult(
            check_name=self.name,
            passed=passed,
            output=output,
            error_count=error_count,
            warning_count=0,
            details=details,
            duration_ms=duration_ms,
            timestamp=datetime.utcnow(),
            has_critical_failure=False,
        )


class MypyRunner(BaseCheck):
    name = "typecheck"
    timeout_seconds = 60

    def __init__(self, target_path: str = "src/", extra_args: list[str] | None = None):
        self.target_path = target_path
        self.extra_args = extra_args or ["--no-error-summary"]

    async def execute(self, sandbox_id: str | None = None, cwd: str | None = None) -> CheckResult:
        start_time = datetime.utcnow()

        command = ["mypy", self.target_path, *self.extra_args]

        returncode, stdout, stderr = self._run_command(command, cwd=cwd, timeout=self.timeout_seconds)

        output = f"{stdout}\n{stderr}".strip()
        passed = returncode == 0

        error_count, warning_count, details = self._parse_output(output)

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return CheckResult(
            check_name=self.name,
            passed=passed,
            output=output,
            error_count=error_count,
            warning_count=warning_count,
            details=details,
            duration_ms=duration_ms,
            timestamp=datetime.utcnow(),
            has_critical_failure=False,
        )

    def _parse_output(self, output: str) -> tuple[int, int, list[CheckDetail]]:
        details: list[CheckDetail] = []
        error_count = 0
        warning_count = 0

        for line in output.split("\n"):
            if ": error:" in line:
                error_count += 1
                details.append(self._parse_line(line, "error"))
            elif ": warning:" in line:
                warning_count += 1
                details.append(self._parse_line(line, "warning"))
            elif ": note:" in line:
                pass

        return error_count, warning_count, details

    def _parse_line(self, line: str, severity: str) -> CheckDetail:
        parts = line.split(":", 3)
        file_path = parts[0] if len(parts) > 0 else ""
        line_num = int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else 0
        message = parts[3].strip() if len(parts) > 3 else line

        if "[" in message and "]" in message:
            bracket_start = message.rfind("[")
            bracket_end = message.rfind("]")
            rule_id = message[bracket_start + 1 : bracket_end]
        else:
            rule_id = "mypy"

        return CheckDetail(
            file_path=file_path,
            line=line_num,
            column=0,
            severity=severity,
            message=message,
            rule_id=rule_id,
        )


class SemgrepRunner(BaseCheck):
    name = "security"
    timeout_seconds = 60

    SEVERITY_MAP = {"ERROR": "error", "WARNING": "warning", "INFO": "info"}

    def __init__(self, target_path: str = "src/", config: str = "auto"):
        self.target_path = target_path
        self.config = config

    async def execute(self, sandbox_id: str | None = None, cwd: str | None = None) -> CheckResult:
        start_time = datetime.utcnow()

        command = [
            "semgrep",
            "--config",
            self.config,
            "--json",
            "--no-git-ignore",
            self.target_path,
        ]

        returncode, stdout, stderr = self._run_command(command, cwd=cwd, timeout=self.timeout_seconds)

        output = f"{stdout}\n{stderr}".strip()
        error_count, warning_count, details, has_critical = self._parse_output(stdout)

        passed = not has_critical

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return CheckResult(
            check_name=self.name,
            passed=passed,
            output=output,
            error_count=error_count,
            warning_count=warning_count,
            details=details,
            duration_ms=duration_ms,
            timestamp=datetime.utcnow(),
            has_critical_failure=has_critical,
        )

    def _parse_output(self, output: str) -> tuple[int, int, list[CheckDetail], bool]:
        import json

        details: list[CheckDetail] = []
        error_count = 0
        warning_count = 0
        has_critical = False

        try:
            data = json.loads(output) if output.strip() else {}
            results = data.get("results", [])

            for result in results:
                severity = result.get("extra", {}).get("severity", "INFO")
                mapped_severity = self.SEVERITY_MAP.get(severity, "info")

                if mapped_severity == "error":
                    error_count += 1
                    has_critical = True
                elif mapped_severity == "warning":
                    warning_count += 1

                details.append(
                    CheckDetail(
                        file_path=result.get("path", ""),
                        line=result.get("start", {}).get("line", 0),
                        column=result.get("start", {}).get("col", 0),
                        severity=mapped_severity,
                        message=result.get("extra", {}).get("message", ""),
                        rule_id=result.get("check_id", "").split(".")[-1] if result.get("check_id") else "semgrep",
                    )
                )
        except json.JSONDecodeError:
            pass

        return error_count, warning_count, details, has_critical
