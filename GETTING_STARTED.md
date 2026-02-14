# Getting Started Guide

This guide walks you through setting up and running the Agentic AI Code Reviewer.

## Prerequisites

Before starting, ensure you have the following installed:

### 1. Python 3.11+

```bash
python --version  # Should be 3.11 or higher
```

If you need to install Python:
- **macOS**: `brew install python@3.11`
- **Linux**: `sudo apt install python3.11 python3.11-venv`
- **Windows**: Download from [python.org](https://www.python.org/downloads/)

### 2. Docker Desktop

Required for PostgreSQL database and sandbox execution.

```bash
docker --version
docker-compose --version
```

Install from: https://www.docker.com/products/docker-desktop

### 3. OpenAI API Key

- Get one at https://platform.openai.com/api-keys
- Ensure you have credits/quota available
- The app uses GPT-4o for code generation and text-embedding-3-small for retrieval

---

## Step-by-Step Setup

### Step 1: Create Virtual Environment

Isolate the project dependencies from your system Python:

```bash
cd /Users/tomersheier/Documents/AIProjects/AgenticAICodeReviewer

python -m venv venv
source venv/bin/activate
```

On Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

You should see `(venv)` in your terminal prompt.

### Step 2: Install Dependencies

Install the project and all its dependencies:

```bash
pip install -e ".[dev]"
```

This installs:
- Core dependencies (FastAPI, LangGraph, SQLAlchemy, etc.)
- Development tools (pytest, ruff, mypy)
- The `kilo` CLI command

### Step 3: Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:

```env
OPENAI_API_KEY=sk-your-actual-key-here
```

**Required settings:**
- `OPENAI_API_KEY` - Your OpenAI API key (required)

**Optional settings** (defaults should work for local development):
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `LLM_MODEL` - Model for code generation (default: gpt-4o)
- `EMBEDDING_MODEL` - Model for embeddings (default: text-embedding-3-small)

### Step 4: Start Database Services

Start PostgreSQL and Redis using Docker:

```bash
docker-compose up -d db redis
```

Wait about 10-15 seconds for PostgreSQL to fully initialize.

Verify services are running:
```bash
docker-compose ps
```

You should see both `db` and `redis` with status "running".

### Step 5: Run Database Migrations

Create the database tables:

```bash
alembic upgrade head
```

You should see output like:
```
INFO  [alembic.runtime.migration] Running upgrade -> 001_initial
```

### Step 6: Build Sandbox Image (Optional)

The sandbox image is used for isolated code execution. This is optional for basic usage but required for full functionality:

```bash
docker build -f docker/sandbox/Dockerfile.sandbox -t code-reviewer-sandbox:latest docker/sandbox/
```

---

## Quick Test

### Test the CLI

Run a validation check on the current project:

```bash
kilo check . --no-tests
```

This runs linting, type checking, and security scans on the codebase.

### Test the API

Start the API server:

```bash
uvicorn src.main:app --reload
```

In another terminal, test the health endpoint:

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy"}
```

Visit the API documentation: http://localhost:8000/docs

---

## Running Your First Code Review

### Using the CLI

```bash
kilo review /path/to/your/repo --task "Add error handling to the main function"
```

### Using the API

```bash
curl -X POST http://localhost:8000/api/runs/ \
  -H "Content-Type: application/json" \
  -d '{
    "repo_path": "/path/to/your/repo",
    "task_description": "Refactor the user service to use dependency injection",
    "task_type": "refactor"
  }'
```

---

## Summary of Commands

| Step | Command |
|------|---------|
| Create venv | `python -m venv venv && source venv/bin/activate` |
| Install dependencies | `pip install -e ".[dev]"` |
| Configure | `cp .env.example .env` (then edit with your API key) |
| Start database | `docker-compose up -d db redis` |
| Run migrations | `alembic upgrade head` |
| Build sandbox | `docker build -f docker/sandbox/Dockerfile.sandbox -t code-reviewer-sandbox:latest docker/sandbox/` |
| Test CLI | `kilo check . --no-tests` |
| Start API | `uvicorn src.main:app --reload` |
| Run review | `kilo review ./some-repo --task "Your task"` |

---

## What Each Step Does

| Step | Purpose |
|------|---------|
| Virtual environment | Isolates project dependencies from system Python |
| pip install | Installs all required packages and the `kilo` CLI |
| .env file | Configures API keys and database connection strings |
| docker-compose | Starts PostgreSQL with pgvector extension and Redis |
| alembic migrate | Creates database tables for runs, patches, audit logs |
| sandbox image | Docker container for isolated code validation |

---

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

### Port Already in Use

If port 8000 is in use:
```bash
uvicorn src.main:app --reload --port 8001
```

If PostgreSQL port 5432 is in use, edit `docker-compose.yml` to use a different port.

### OpenAI API Errors

- Verify `OPENAI_API_KEY` is set correctly in `.env`
- Check API quota and billing at https://platform.openai.com/
- Ensure the key has access to GPT-4 and embedding models

---

## Next Steps

After completing setup:

1. **Index a repository** for faster retrieval:
   ```bash
   kilo index /path/to/repo
   ```

2. **Run validation checks** on your code:
   ```bash
   kilo check /path/to/repo
   ```

3. **Review the API docs** at http://localhost:8000/docs

4. **Read the full README** for detailed usage and architecture information
