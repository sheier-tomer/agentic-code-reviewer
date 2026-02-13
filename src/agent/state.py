from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import uuid


class TaskType(str, Enum):
    REFACTOR = "refactor"
    BUGFIX = "bugfix"
    REVIEW = "review"


class Decision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    NEEDS_REVIEW = "needs_review"
    REJECT = "reject"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CodeChunk:
    id: str
    file_path: str
    chunk_type: str
    symbol_name: str | None
    start_line: int
    end_line: int
    content: str
    language: str
    similarity: float = 0.0
    embedding: list[float] | None = None
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    docstring: str | None = None
    complexity_score: int | None = None


@dataclass
class ChangePlan:
    description: str
    files_to_modify: list[str]
    changes: list["PlannedChange"]
    rationale: str
    confidence: float
    estimated_impact: str


@dataclass
class PlannedChange:
    file_path: str
    change_type: str
    description: str
    affected_symbols: list[str]


@dataclass
class CheckDetail:
    file_path: str
    line: int
    column: int
    severity: str
    message: str
    rule_id: str


@dataclass
class CheckResult:
    check_name: str
    passed: bool
    output: str
    error_count: int
    warning_count: int
    details: list[CheckDetail]
    duration_ms: int
    timestamp: datetime
    has_critical_failure: bool = False


@dataclass
class TestResult:
    total_tests: int
    passed: int
    failed: int
    skipped: int
    output: str
    duration_ms: int
    test_files: list[str]


@dataclass
class LintResult:
    total_issues: int
    errors: int
    warnings: int
    output: str
    details: list[CheckDetail]


@dataclass
class TypeCheckResult:
    errors: int
    warnings: int
    output: str
    details: list[CheckDetail]


@dataclass
class SecurityResult:
    critical: int
    high: int
    medium: int
    low: int
    output: str
    details: list[CheckDetail]


@dataclass
class PatchResult:
    success: bool
    sandbox_id: str | None = None
    error: str | None = None
    files_modified: list[str] = field(default_factory=list)


@dataclass
class Scores:
    quality_score: float
    risk_score: float
    test_score: float
    lint_score: float
    typecheck_score: float
    security_score: float
    has_hard_gate_failure: bool


@dataclass
class RiskAssessment:
    combined_score: float
    diff_size_risk: float
    sensitive_path_risk: float
    test_coverage_risk: float
    complexity_risk: float
    dependency_risk: float
    new_code_risk: float
    flags: list[str]


@dataclass
class AgentState:
    run_id: str
    repo_path: str
    task_type: TaskType
    task_description: str

    repo_id: str | None = None
    commit_sha: str | None = None
    branch: str | None = None

    file_index: list[dict[str, Any]] = field(default_factory=list)
    repo_metadata: dict[str, Any] = field(default_factory=dict)

    retrieved_chunks: list[CodeChunk] = field(default_factory=list)
    related_docs: list[dict[str, Any]] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)

    change_plan: ChangePlan | None = None
    plan_confidence: float = 0.0

    generated_diff: str | None = None
    patch_applied: bool = False
    sandbox_id: str | None = None
    patch_result: PatchResult | None = None

    check_results: dict[str, CheckResult] = field(default_factory=dict)
    test_results: TestResult | None = None
    lint_results: LintResult | None = None
    typecheck_results: TypeCheckResult | None = None
    security_results: SecurityResult | None = None

    scores: Scores | None = None
    quality_score: float = 0.0
    risk_score: float = 0.0
    decision: Decision | None = None

    explanation: str | None = None
    final_diff: str | None = None

    errors: list[str] = field(default_factory=list)
    requires_escalation: bool = False
    retry_count: int = 0

    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def create(cls, repo_path: str, task_type: TaskType, task_description: str) -> "AgentState":
        return cls(
            run_id=str(uuid.uuid4()),
            repo_path=repo_path,
            task_type=task_type,
            task_description=task_description,
            status=RunStatus.PENDING,
        )
