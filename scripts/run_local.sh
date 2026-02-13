#!/bin/bash
set -e

echo "Starting Agentic AI Code Reviewer..."

docker-compose up -d db redis

sleep 5

alembic upgrade head

echo "Services started!"
echo "API: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
