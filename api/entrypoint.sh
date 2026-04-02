#!/usr/bin/env bash
set -e

echo "Running database migrations..."
uv run --frozen --no-dev --package aviary-api alembic upgrade head

echo "Starting API server..."
exec uv run --frozen --no-dev --package aviary-api uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
