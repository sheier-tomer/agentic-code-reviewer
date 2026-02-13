from src.scoring.engine import ScoringEngine, ScoringWeights, ScoringThresholds
from src.agent.state import CheckResult, CheckDetail, Decision
from datetime import datetime


def make_check_result(name: str, passed: bool, errors: int = 0, warnings: int = 0) -> CheckResult:
    return CheckResult(
        check_name=name,
        passed=passed,
        output="",
        error_count=errors,
        warning_count=warnings,
        details=[],
        duration_ms=100,
        timestamp=datetime.utcnow(),
    )


def test_scoring_engine_all_passed():
    engine = ScoringEngine()
    
    check_results = {
        "tests": make_check_result("tests", True),
        "lint": make_check_result("lint", True),
        "typecheck": make_check_result("typecheck", True),
        "security": make_check_result("security", True),
    }
    
    result = engine.compute_scores(check_results)
    
    assert result.quality_score == 100.0
    assert result.decision == Decision.AUTO_APPROVE


def test_scoring_engine_tests_failed():
    engine = ScoringEngine()
    
    check_results = {
        "tests": make_check_result("tests", False, errors=2),
        "lint": make_check_result("lint", True),
        "typecheck": make_check_result("typecheck", True),
        "security": make_check_result("security", True),
    }
    
    result = engine.compute_scores(check_results)
    
    assert result.decision == Decision.REJECT
    assert "Tests failed" in result.gate_failures


def test_scoring_engine_lint_warnings():
    engine = ScoringEngine()
    
    check_results = {
        "tests": make_check_result("tests", True),
        "lint": make_check_result("lint", True, warnings=5),
        "typecheck": make_check_result("typecheck", True),
        "security": make_check_result("security", True),
    }
    
    result = engine.compute_scores(check_results)
    
    assert result.quality_score < 100.0
    assert result.scores.lint_score < 100.0


def test_scoring_engine_security_critical():
    engine = ScoringEngine()
    
    check_results = {
        "tests": make_check_result("tests", True),
        "lint": make_check_result("lint", True),
        "typecheck": make_check_result("typecheck", True),
        "security": make_check_result("security", False, errors=1),
    }
    
    check_results["security"].has_critical_failure = True
    
    result = engine.compute_scores(check_results)
    
    assert result.decision == Decision.REJECT


def test_scoring_engine_quality_thresholds():
    engine = ScoringEngine(
        thresholds=ScoringThresholds(
            quality_approve=80.0,
            quality_review=60.0,
        )
    )
    
    check_results = {
        "tests": make_check_result("tests", True),
        "lint": make_check_result("lint", True, warnings=10),
        "typecheck": make_check_result("typecheck", True, errors=3),
        "security": make_check_result("security", True),
    }
    
    result = engine.compute_scores(check_results)
    
    assert result.quality_score < 80.0
    assert result.decision in [Decision.NEEDS_REVIEW, Decision.REJECT]
