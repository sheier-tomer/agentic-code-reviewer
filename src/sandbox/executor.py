import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import unidiff

from src.agent.state import PatchResult
from src.sandbox.docker_manager import DockerSandboxManager, LocalExecutor


@dataclass
class PatchValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    hunks_total: int
    hunks_applied: int
    files_affected: list[str]
    lines_added: int
    lines_removed: int


class PatchApplier:
    MAX_DIFF_LINES = 500
    FORBIDDEN_PATTERNS = [
        "__pycache__",
        ".pyc",
        ".env",
        "credentials",
        "secrets",
        ".git/",
    ]

    def __init__(self, sandbox_manager: DockerSandboxManager | None = None):
        self.sandbox_manager = sandbox_manager

    def validate_diff(self, diff_content: str) -> PatchValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        try:
            patch_set = unidiff.PatchSet(diff_content)
        except Exception as e:
            return PatchValidationResult(
                valid=False,
                errors=[f"Invalid diff format: {e}"],
                warnings=[],
                hunks_total=0,
                hunks_applied=0,
                files_affected=[],
                lines_added=0,
                lines_removed=0,
            )

        hunks_total = 0
        lines_added = 0
        lines_removed = 0
        files_affected: list[str] = []

        for patched_file in patch_set:
            file_path = patched_file.path
            if file_path.startswith("a/"):
                file_path = file_path[2:]
            files_affected.append(file_path)

            for pattern in self.FORBIDDEN_PATTERNS:
                if pattern in file_path:
                    errors.append(f"Forbidden path pattern: {pattern} in {file_path}")

            for hunk in patched_file:
                hunks_total += 1
                for line in hunk:
                    if line.is_added:
                        lines_added += 1
                        if self._contains_secret(line.value):
                            errors.append(f"Potential secret in added line: {file_path}:{hunk.target_start}")
                    elif line.is_removed:
                        lines_removed += 1

        total_lines = lines_added + lines_removed
        if total_lines > self.MAX_DIFF_LINES:
            errors.append(f"Diff too large: {total_lines} lines (max {self.MAX_DIFF_LINES})")

        if len(files_affected) > 10:
            warnings.append(f"Many files affected: {len(files_affected)}")

        for patched_file in patch_set:
            if patched_file.target_file == "/dev/null":
                errors.append(f"File deletion not allowed: {patched_file.source_file}")

        return PatchValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            hunks_total=hunks_total,
            hunks_applied=0,
            files_affected=files_affected,
            lines_added=lines_added,
            lines_removed=lines_removed,
        )

    def _contains_secret(self, line: str) -> bool:
        secret_patterns = [
            "api_key",
            "apikey",
            "secret_key",
            "secretkey",
            "password",
            "passwd",
            "token",
            "bearer",
            "auth",
            "credential",
        ]

        line_lower = line.lower()
        for pattern in secret_patterns:
            if pattern in line_lower and "=" in line:
                return True

        import re

        patterns = [
            r"sk-[a-zA-Z0-9]{20,}",
            r"AKIA[0-9A-Z]{16}",
            r"ghp_[a-zA-Z0-9]{36}",
            r"[a-zA-Z0-9]{32,}",
        ]

        for pattern in patterns:
            if re.search(pattern, line):
                return True

        return False

    def apply_patch(
        self,
        repo_path: Path,
        diff_content: str,
        sandbox_id: str | None = None,
    ) -> PatchResult:
        validation = self.validate_diff(diff_content)

        if not validation.valid:
            return PatchResult(
                success=False,
                error="; ".join(validation.errors),
                files_modified=[],
            )

        if sandbox_id and self.sandbox_manager:
            return self._apply_in_sandbox(repo_path, diff_content, sandbox_id)
        else:
            return self._apply_local(repo_path, diff_content)

    def _apply_local(self, repo_path: Path, diff_content: str) -> PatchResult:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".diff", delete=False) as f:
            f.write(diff_content)
            diff_path = f.name

        try:
            result = subprocess.run(
                ["git", "apply", "--check", diff_path],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return PatchResult(
                    success=False,
                    error=f"Patch would not apply cleanly: {result.stderr}",
                    files_modified=[],
                )

            result = subprocess.run(
                ["git", "apply", diff_path],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                return PatchResult(
                    success=False,
                    error=f"Failed to apply patch: {result.stderr}",
                    files_modified=[],
                )

            validation = self.validate_diff(diff_content)
            return PatchResult(
                success=True,
                files_modified=validation.files_affected,
            )

        except Exception as e:
            return PatchResult(
                success=False,
                error=str(e),
                files_modified=[],
            )
        finally:
            Path(diff_path).unlink(missing_ok=True)

    def _apply_in_sandbox(self, repo_path: Path, diff_content: str, sandbox_id: str) -> PatchResult:
        if not self.sandbox_manager:
            return PatchResult(success=False, error="No sandbox manager available", files_modified=[])

        with tempfile.NamedTemporaryFile(mode="w", suffix=".diff", delete=False) as f:
            f.write(diff_content)
            diff_path = Path(f.name)

        try:
            success = self.sandbox_manager.copy_files_to_sandbox(sandbox_id, diff_path, "/tmp/patch.diff")
            if not success:
                return PatchResult(
                    success=False,
                    error="Failed to copy patch to sandbox",
                    files_modified=[],
                )

            result = self.sandbox_manager.execute_in_sandbox(
                sandbox_id,
                ["git", "apply", "--check", "/tmp/patch.diff"],
            )

            if not result.success:
                return PatchResult(
                    success=False,
                    error=f"Patch would not apply cleanly: {result.stderr}",
                    sandbox_id=sandbox_id,
                    files_modified=[],
                )

            result = self.sandbox_manager.execute_in_sandbox(
                sandbox_id,
                ["git", "apply", "/tmp/patch.diff"],
            )

            if not result.success:
                return PatchResult(
                    success=False,
                    error=f"Failed to apply patch: {result.stderr}",
                    sandbox_id=sandbox_id,
                    files_modified=[],
                )

            validation = self.validate_diff(diff_content)
            return PatchResult(
                success=True,
                sandbox_id=sandbox_id,
                files_modified=validation.files_affected,
            )

        except Exception as e:
            return PatchResult(
                success=False,
                error=str(e),
                files_modified=[],
            )
        finally:
            diff_path.unlink(missing_ok=True)

    def revert_patch(self, repo_path: Path, sandbox_id: str | None = None) -> bool:
        if sandbox_id and self.sandbox_manager:
            result = self.sandbox_manager.execute_in_sandbox(
                sandbox_id,
                ["git", "checkout", "."],
            )
            return result.success
        else:
            result = subprocess.run(
                ["git", "checkout", "."],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
