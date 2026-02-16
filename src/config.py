from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_base_url: str | None = None

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/code_reviewer"
    database_sync_url: str = "postgresql://postgres:postgres@localhost:5432/code_reviewer"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    redis_url: str = "redis://localhost:6379/0"

    docker_sandbox_image: str = "code-reviewer-sandbox:latest"
    docker_timeout_seconds: int = 300
    docker_memory_limit: str = "2g"
    docker_cpu_limit: str = "2"

    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096

    max_files_per_run: int = 10
    max_diff_lines: int = 500
    max_context_tokens: int = 50000
    min_similarity_threshold: float = 0.1
    max_retries: int = 2

    scoring_quality_threshold_approve: float = 80.0
    scoring_quality_threshold_review: float = 60.0
    scoring_risk_threshold_review: float = 0.3
    scoring_risk_threshold_reject: float = 0.7

    sensitive_paths: list[str] = [
        "auth/",
        "security/",
        "payment/",
        "config/",
        "settings/",
        "secrets/",
        "credentials/",
    ]

    ignore_patterns: list[str] = [
        ".git/",
        "__pycache__/",
        "*.pyc",
        ".env*",
        "node_modules/",
        "*.min.js",
        "*.lock",
        "dist/",
        "build/",
        ".venv/",
        "venv/",
        "*.egg-info/",
        ".mypy_cache/",
        ".pytest_cache/",
        ".ruff_cache/",
    ]

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1

    log_level: str = "INFO"
    log_format: str = "json"


settings = Settings()
