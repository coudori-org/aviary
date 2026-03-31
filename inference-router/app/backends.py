"""Backend routing — transparent Anthropic Messages API proxy.

The inference router exposes /v1/messages (Anthropic API format).
claude-agent-sdk → Claude Code CLI → Anthropic SDK sends requests here.
The router determines the backend from the model name and proxies accordingly.

Model name → Backend resolution:
  claude-*          → Claude API (api.anthropic.com)
  anthropic.*       → Bedrock (AWS)
  <name>:<tag>      → Ollama (e.g., qwen3.5:35b, llama3.3:70b)
  <org>/<model>     → vLLM (e.g., meta-llama/Llama-3.3-70B-Instruct)

Claude and Ollama both speak the Anthropic Messages API natively,
so requests are proxied as-is. vLLM requires translation to OpenAI format.
"""

import os
import re

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
VLLM_URL = os.environ.get("VLLM_URL", "http://localhost:8001")
CLAUDE_API_URL = os.environ.get("CLAUDE_API_URL", "https://api.anthropic.com")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")

# Default model per backend — resolved when model is "default"
DEFAULT_MODELS: dict[str, str] = {
    "claude": os.environ.get("DEFAULT_MODEL_CLAUDE", "claude-sonnet-4-20250514"),
    "ollama": os.environ.get("DEFAULT_MODEL_OLLAMA", "qwen3:8b"),
    "vllm": os.environ.get("DEFAULT_MODEL_VLLM", "meta-llama/Llama-3.3-70B-Instruct"),
    "bedrock": os.environ.get("DEFAULT_MODEL_BEDROCK", "anthropic.claude-sonnet-4-20250514-v1:0"),
}


def resolve_backend(model: str) -> str:
    """Determine which backend to use based on model name pattern."""
    if model == "default":
        return "claude"
    if model.startswith("claude-"):
        return "claude"
    if model.startswith("anthropic."):
        return "bedrock"
    if ":" in model:
        # Ollama convention: name:tag (e.g., qwen3.5:35b)
        return "ollama"
    if "/" in model:
        # HuggingFace convention: org/model (e.g., meta-llama/...)
        return "vllm"
    # Default to Claude
    return "claude"


def resolve_model(model: str, backend: str) -> str:
    """Resolve 'default' to the configured default model for the backend."""
    if model == "default":
        return DEFAULT_MODELS.get(backend, DEFAULT_MODELS["claude"])
    return model


def get_proxy_url(backend: str) -> str:
    """Return the upstream URL for the Anthropic Messages API proxy."""
    if backend == "claude":
        return CLAUDE_API_URL
    elif backend == "ollama":
        # Ollama's Anthropic-compatible endpoint
        return OLLAMA_URL
    elif backend == "vllm":
        return VLLM_URL
    elif backend == "bedrock":
        return ""  # Bedrock uses AWS SDK, not HTTP proxy
    return CLAUDE_API_URL
