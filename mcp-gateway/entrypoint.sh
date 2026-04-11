#!/usr/bin/env bash
set -e

echo "Starting MCP Gateway..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload --no-access-log
