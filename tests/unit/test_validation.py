import pytest
from pathlib import Path
from src.validation.pipeline import ValidationPipeline, ValidationConfig


def test_validation_config_defaults():
    config = ValidationConfig()
    
    assert config.run_tests is True
    assert config.run_lint is True
    assert config.run_typecheck is True
    assert config.run_security is True


def test_validation_config_disabled():
    config = ValidationConfig(
        run_tests=False,
        run_security=False,
    )
    
    pipeline = ValidationPipeline(config)
    check_names = [name for name, _ in pipeline._checks]
    
    assert "tests" not in check_names
    assert "security" not in check_names
    assert "lint" in check_names


@pytest.mark.asyncio
async def test_pipeline_summary():
    from src.agent.state import CheckResult
    from datetime import datetime
    
    pipeline = ValidationPipeline()
    
    results = {
        "tests": CheckResult(
            check_name="tests",
            passed=True,
            output="",
            error_count=0,
            warning_count=0,
            details=[],
            duration_ms=100,
            timestamp=datetime.utcnow(),
        ),
        "lint": CheckResult(
            check_name="lint",
            passed=True,
            output="",
            error_count=0,
            warning_count=2,
            details=[],
            duration_ms=50,
            timestamp=datetime.utcnow(),
        ),
    }
    
    summary = pipeline.get_summary(results)
    
    assert summary["total_checks"] == 2
    assert summary["passed"] == 2
    assert summary["total_warnings"] == 2
    assert summary["all_passed"] is True
