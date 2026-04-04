#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="aviary-vllm"

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping and removing '${CONTAINER_NAME}'..."
    docker rm -f "$CONTAINER_NAME"
    echo "Done."
else
    echo "No container '${CONTAINER_NAME}' found."
fi
