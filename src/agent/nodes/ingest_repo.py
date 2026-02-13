import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agent.state import AgentState, RunStatus
from src.indexing.filters import FileFilter, filter_files


async def ingest_repo(state: AgentState) -> AgentState:
    state.status = RunStatus.RUNNING
    state.started_at = datetime.utcnow()

    repo_path = Path(state.repo_path)

    if not repo_path.exists():
        state.errors.append(f"Repository path does not exist: {repo_path}")
        state.status = RunStatus.FAILED
        return state

    try:
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if commit_result.returncode == 0:
            state.commit_sha = commit_result.stdout.strip()

        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
        )
        if branch_result.returncode == 0:
            state.branch = branch_result.stdout.strip()
    except Exception:
        pass

    file_filter = FileFilter(repo_path)
    state.file_index = filter_files(repo_path, file_filter)

    state.repo_metadata = {
        "path": str(repo_path),
        "commit_sha": state.commit_sha,
        "branch": state.branch,
        "file_count": len(state.file_index),
        "total_size": sum(f.get("size", 0) for f in state.file_index),
    }

    return state
