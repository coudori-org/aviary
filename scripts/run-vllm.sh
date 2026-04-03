#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="aviary-vllm"

# Load variables from .env if present (without overriding existing env)
ENV_FILE="$(dirname "$0")/../.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$')
    set +a
fi

PORT="${VLLM_PORT:-8191}"
MODEL="${VLLM_MODEL:-cyankiwi/gemma-4-31B-it-AWQ-4bit}"
IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:gemma4}"
GPU_MEM="${VLLM_GPU_MEM:-0.90}"
MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-65536}"
MAX_NUM_SEQS="${VLLM_MAX_NUM_SEQS:-3}"

if [[ -z "${HF_TOKEN:-}" ]]; then
    echo "ERROR: HF_TOKEN not set. Export it or add to .env"
    exit 1
fi

# Remove existing container if stopped
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Removing existing container '${CONTAINER_NAME}'..."
    docker rm -f "$CONTAINER_NAME"
fi

echo "Starting vLLM: model=${MODEL}, port=${PORT}, max_model_len=${MAX_MODEL_LEN}, gpu_memory_utilization=${GPU_MEM}"

docker run -itd \
    --name "$CONTAINER_NAME" \
    --ipc=host \
    --network host \
    --shm-size 16G \
    --gpus all \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -e HF_TOKEN="$HF_TOKEN" \
    "$IMAGE" \
    --model "$MODEL" \
    --tensor-parallel-size 1 \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEM" \
    --max-num-seqs "$MAX_NUM_SEQS" \
    --limit-mm-per-prompt '{"audio": 0}' \
    --async-scheduling \
    --reasoning-parser gemma4 \
    --tool-call-parser gemma4 \
    --enable-auto-tool-choice \
    --kv-cache-dtype fp8 \
    --host 0.0.0.0 \
    --port "$PORT"

echo "Container '${CONTAINER_NAME}' started. Waiting for server..."
echo "Check logs: docker logs -f ${CONTAINER_NAME}"
echo "Test: curl http://localhost:${PORT}/v1/chat/completions -H 'Content-Type: application/json' -d '{\"model\": \"${MODEL}\", \"messages\": [{\"role\": \"user\", \"content\": \"hello\"}], \"max_tokens\": 50}'"
