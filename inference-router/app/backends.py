"""Backend routing — transparent Anthropic Messages API proxy.

The inference router exposes /v1/messages (Anthropic API format).
claude-agent-sdk → Claude Code CLI → Anthropic SDK sends requests here.

Backend is determined by the X-Backend header (required), set via
ANTHROPIC_CUSTOM_HEADERS in the runtime Pod environment.
Supported backends: claude, ollama, vllm, bedrock.

Claude and Ollama both speak the Anthropic Messages API natively,
so requests are proxied as-is. vLLM requires translation to OpenAI format.
"""

import os

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
VLLM_URL = os.environ.get("VLLM_URL", "http://localhost:8001")
CLAUDE_API_URL = os.environ.get("CLAUDE_API_URL", "https://api.anthropic.com")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-2")

VALID_BACKENDS = {"claude", "ollama", "vllm", "bedrock"}

# Default model per backend — resolved when model is "default"
DEFAULT_MODELS: dict[str, str] = {
    "claude": os.environ.get("DEFAULT_MODEL_CLAUDE", "claude-sonnet-4-6"),
    "ollama": os.environ.get("DEFAULT_MODEL_OLLAMA", "qwen3.5:35b"),
    "vllm": os.environ.get("DEFAULT_MODEL_VLLM", "meta-llama/Llama-3.3-70B-Instruct"),
    "bedrock": os.environ.get("DEFAULT_MODEL_BEDROCK", "anthropic.claude-sonnet-4-5-20250929-v1:0"),
}


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
