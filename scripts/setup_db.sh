#!/bin/bash
set -e

echo "Setting up database..."

if command -v psql &> /dev/null; then
    psql -c "CREATE DATABASE code_reviewer;" 2>/dev/null || true
    psql -d code_reviewer -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || true
fi

echo "Running migrations..."
alembic upgrade head

echo "Database setup complete!"
