# Agentic AI Code Reviewer

An AI-powered engineering system that understands codebases, proposes safe refactors, validates changes, and generates auditable diffs before merge.

## Features

- **Repository Indexing** - Parse, chunk, and embed code for semantic retrieval
- **Context-Aware Refactoring** - RAG-based code understanding for targeted changes
- **Automated Validation** - Tests, linting, type checking, and security scanning
- **Quality Scoring** - Deterministic scoring with hard gates and risk heuristics
- **Sandbox Execution** - Docker-isolated environment for safe patch validation
- **Full Audit Trail** - Immutable logging for compliance and traceability

## Requirements

- Python 3.11+
- Docker (for sandbox execution)
- PostgreSQL 16 with pgvector extension
- Redis (optional, for job queuing)
- OpenAI API key

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd agentic-ai-code-reviewer

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e .
```

### 2. Configure Environment

```bash
# Copy example environment
cp .env.example .env

# Edit .env with your settings
# Required: OPENAI_API_KEY
```

Minimum `.env` configuration:

```env
OPENAI_API_KEY=sk-your-api-key-here
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/code_reviewer
DATABASE_SYNC_URL=postgresql://postgres:postgres@localhost:5432/code_reviewer
```

### 3. Start Services

```bash
# Start PostgreSQL and Redis with Docker
docker-compose up -d db redis

# Wait for database to be ready
sleep 5

# Run database migrations
alembic upgrade head
```

### 4. Run a Code Review

```bash
# Review a repository
kilo review ./path/to/repo --task "Add error handling to the user service"

# Or specify a task type
kilo review ./path/to/repo --task "Fix the null pointer bug" --type bugfix
```

## CLI Commands

### `kilo review`

Run an AI-powered code review on a repository.

```bash
kilo review REPO_PATH --task "TASK_DESCRIPTION" [--type TYPE] [--output OUTPUT_FILE]

# Examples:
kilo review ./my-app --task "Refactor authentication to use JWT tokens"
kilo review ./api --task "Fix SQL injection vulnerability" --type bugfix
kilo review ./service --task "Review and optimize database queries" --output changes.diff
```

Options:
- `--task, -t` - Task description (required)
- `--type` - Task type: `refactor`, `bugfix`, or `review` (default: review)
- `--output, -o` - Output file for the generated diff

### `kilo index`

Index a repository for semantic code retrieval.

```bash
kilo index REPO_PATH

# Example:
kilo index ./my-project
```

This parses the codebase, chunks it by functions/classes, generates embeddings, and stores them in pgvector.

### `kilo check`

Run validation checks on a repository.

```bash
kilo check REPO_PATH [--tests] [--lint] [--typecheck] [--security]

# Examples:
kilo check ./my-app                    # Run all checks
kilo check ./my-app --no-security      # Skip security scan
kilo check ./my-app --no-tests --no-lint  # Only typecheck and security
```

Options:
- `--tests/--no-tests` - Run unit tests (default: on)
- `--lint/--no-lint` - Run linting with ruff (default: on)
- `--typecheck/--no-typecheck` - Run type checking with mypy (default: on)
- `--security/--no-security` - Run security scan with semgrep (default: on)

### `kilo runs`

List recent agent runs.

```bash
kilo runs
```

Shows a table of recent runs with status, decision, quality score, and risk score.

## HTTP API

Start the API server:

```bash
# Development
uvicorn src.main:app --reload

# Or with Docker
docker-compose up app
```

API Documentation available at: `http://localhost:8000/docs`

### Endpoints

#### `POST /api/runs/`

Create a new code review run.

```bash
curl -X POST http://localhost:8000/api/runs/ \
  -H "Content-Type: application/json" \
  -d '{
    "repo_path": "/path/to/repo",
    "task_description": "Add input validation to the API endpoints",
    "task_type": "refactor"
  }'
```

Response:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "task_type": "refactor",
  "decision": "needs_review",
  "quality_score": 85.0,
  "risk_score": 0.35,
  "explanation": "Added input validation using Pydantic models...",
  "diff": "--- a/src/api/handlers.py\n+++ b/src/api/handlers.py\n...",
  "errors": []
}
```

#### `GET /api/runs/`

List recent runs.

```bash
curl http://localhost:8000/api/runs/
```

#### `GET /api/runs/{run_id}`

Get details of a specific run.

```bash
curl http://localhost:8000/api/runs/550e8400-e29b-41d4-a716-446655440000
```

#### `GET /api/runs/{run_id}/diff`

Get the diff for a specific run.

```bash
curl http://localhost:8000/api/runs/550e8400-e29b-41d4-a716-446655440000/diff
```

#### `GET /api/runs/{run_id}/audit`

Get the full audit trail for a run.

```bash
curl http://localhost:8000/api/runs/550e8400-e29b-41d4-a716-446655440000/audit
```

#### `GET /health` and `GET /ready`

Health check endpoints for monitoring.

## How It Works

### Agent Workflow

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│ Ingest Repo │────▶│ Retrieve     │────▶│ Plan Change  │
│             │     │ Context      │     │              │
└─────────────┘     └──────────────┘     └──────────────┘
                                               │
┌─────────────┐     ┌──────────────┐     ┌────▼─────────┐
│ Run Checks  │◀────│ Apply Patch  │◀────│ Generate     │
│ (Sandbox)   │     │ (Sandbox)    │     │ Patch        │
└─────────────┘     └──────────────┘     └──────────────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│ Score       │────▶│ Explain Diff │────▶│ Finalize     │
│ Change      │     │              │     │              │
└─────────────┘     └──────────────┘     └──────────────┘
```

### Decision Outcomes

| Decision | Meaning | Action |
|----------|---------|--------|
| `auto_approve` | High quality, low risk | Ready for merge (optional human review) |
| `needs_review` | Moderate risk or quality | Requires human approval |
| `reject` | Failed gates or high risk | Changes not suitable |

### Validation Checks

| Check | Tool | Failure Mode |
|-------|------|--------------|
| Unit Tests | pytest | Any test failure (hard gate) |
| Linting | ruff | Style violations |
| Formatting | ruff format | Unformatted files |
| Type Checking | mypy | Type errors |
| Security | semgrep | High/Critical findings (hard gate) |

### Quality Scoring

Scores are weighted combinations:
- Tests: 40%
- Type checking: 25%
- Security: 15%
- Linting: 15%
- Formatting: 5%

### Risk Heuristics

Risk factors include:
- Diff size (>200 lines = higher risk)
- Sensitive file paths (auth/, security/, payment/)
- Missing test coverage
- Complexity increase
- Dependency file changes

## Project Structure

```
agentic-ai-code-reviewer/
├── src/
│   ├── agent/              # LangGraph workflow
│   │   ├── nodes/          # Individual workflow nodes
│   │   ├── tools/          # LLM, vector search, diff generation
│   │   ├── graph.py        # Workflow definition
│   │   └── state.py        # State schema
│   ├── api/                # FastAPI endpoints
│   ├── cli/                # Typer CLI commands
│   ├── db/                 # SQLAlchemy models & migrations
│   ├── indexing/           # Code parsing & embedding
│   ├── sandbox/            # Docker sandbox execution
│   ├── scoring/            # Quality & risk scoring
│   ├── validation/         # Check runners (pytest, ruff, etc.)
│   ├── config.py           # Settings management
│   └── main.py             # FastAPI app entry point
├── tests/
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests
├── docker/
│   ├── Dockerfile.app      # Main application container
│   └── sandbox/            # Sandbox container for validation
├── config/
│   ├── semgrep_rules/      # Custom security rules
│   └── scoring/            # Scoring rubric configuration
├── scripts/
│   ├── setup_db.sh         # Database initialization
│   └── run_local.sh        # Local development startup
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml
└── .env.example
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | (required) |
| `DATABASE_URL` | Async PostgreSQL URL | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis URL | `redis://localhost:6379/0` |
| `LLM_MODEL` | LLM for generation | `gpt-4o` |
| `EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `MAX_FILES_PER_RUN` | Max files to modify | `10` |
| `MAX_DIFF_LINES` | Max diff size | `500` |

### Scoring Thresholds

Configure in `config/scoring/rubric.yaml`:

```yaml
thresholds:
  quality_approve: 80.0   # Auto-approve if quality >= 80
  quality_review: 60.0    # Needs review if 60 <= quality < 80
  risk_review: 0.3        # Needs review if risk >= 0.3
  risk_reject: 0.7        # Reject if risk >= 0.7
```

### Sensitive Paths

Paths that trigger higher risk scores:

```python
SENSITIVE_PATHS = [
    "auth/",
    "security/",
    "payment/",
    "config/",
    "secrets/",
]
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/unit/test_scoring.py
```

### Code Quality

```bash
# Lint
ruff check src/

# Format
ruff format src/

# Type check
mypy src/
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Troubleshooting

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker-compose ps db

# Check logs
docker-compose logs db

# Restart database
docker-compose restart db
```

### pgvector Extension Missing

```bash
# Connect to database
docker-compose exec db psql -U postgres -d code_reviewer

# Enable extension
CREATE EXTENSION IF NOT EXISTS vector;
```

### Docker Sandbox Issues

```bash
# Build sandbox image
docker build -f docker/sandbox/Dockerfile.sandbox -t code-reviewer-sandbox:latest .

# List running containers
docker ps

# Check container logs
docker logs <container_id>
```

### OpenAI API Errors

- Verify `OPENAI_API_KEY` is set correctly
- Check API quota and billing
- For rate limits, the system will retry with exponential backoff

## Architecture Notes

### Why LangGraph?

LangGraph provides explicit state machines for agent workflows, making the review process:
- Deterministic and reproducible
- Easy to inspect and debug
- Simple to extend with new nodes

### Why pgvector?

Native PostgreSQL extension for vector search:
- No additional database required
- ACID compliance for audit logging
- Familiar SQL interface

### Why Sandbox Execution?

Docker isolation ensures:
- Changes don't affect the host system
- Reproducible validation environment
- Resource limits for safety

## Roadmap

- [ ] GitHub PR integration (webhook receiver, PR creation)
- [ ] WebSocket streaming for real-time progress
- [ ] Multi-language support (TypeScript, Go, Rust)
- [ ] Custom rule configuration via UI
- [ ] Performance regression detection
- [ ] LLM provider abstraction (support for local models)

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and add tests
4. Run quality checks: `ruff check && mypy src && pytest`
5. Submit a pull request
