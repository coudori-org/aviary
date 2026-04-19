#!/usr/bin/env bash
set -e

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --no-access-log
