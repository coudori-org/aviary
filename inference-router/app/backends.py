"""Backend routing — transparent Anthropic Messages API proxy.

The inference router exposes /v1/messages (Anthropic API format).
claude-agent-sdk → Claude Code CLI → Anthropic SDK sends requests here.

Backend is determined by the X-Backend header (required), set via
ANTHROPIC_CUSTOM_HEADERS in the runtime Pod environment.
Supported backends: claude, ollama, vllm, bedrock.

Claude, Ollama, and vLLM (gemma4 image) all speak the Anthropic Messages API
natively, so requests are proxied as-is.
"""

import os

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
VLLM_URL = os.environ.get("VLLM_URL", "http://localhost:8191")
CLAUDE_API_URL = os.environ.get("CLAUDE_API_URL", "https://api.anthropic.com")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-2")

VALID_BACKENDS = {"claude", "ollama", "vllm", "bedrock"}

# Default model per backend — resolved when model is "default"
DEFAULT_MODELS: dict[str, str] = {
    "claude": os.environ.get("DEFAULT_MODEL_CLAUDE", "claude-sonnet-4-6"),
    "ollama": os.environ.get("DEFAULT_MODEL_OLLAMA", "gemma4:26b"),
    "vllm": os.environ.get("DEFAULT_MODEL_VLLM", "cyankiwi/gemma-4-31B-it-AWQ-4bit"),
    "bedrock": os.environ.get("DEFAULT_MODEL_BEDROCK", "anthropic.claude-sonnet-4-5-20250929-v1:0"),
}


# In-memory cache for default model sampling parameters.
# Populated at startup by fetch_default_model_params().
# Keys: backend name, Values: dict of sampling params (temperature, top_p, top_k, num_ctx).
DEFAULT_MODEL_PARAMS: dict[str, dict] = {}


async def fetch_default_model_params():
    """Fetch and cache sampling parameters for each backend's default model.

    Called once at startup. For Ollama, queries /api/show to read Modelfile defaults.
    """
    import httpx

    # Ollama
    ollama_model = DEFAULT_MODELS.get("ollama", "")
    if ollama_model:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/show", json={"name": ollama_model})
                resp.raise_for_status()
                data = resp.json()
            params: dict[str, float] = {}
            for line in (data.get("parameters") or "").strip().splitlines():
                parts = line.split()
                if len(parts) == 2:
                    try:
                        params[parts[0]] = float(parts[1])
                    except ValueError:
                        pass
            # Extract max context length from model_info
            max_ctx = 0
            for k, v in (data.get("model_info") or {}).items():
                if k.endswith(".context_length") and isinstance(v, (int, float)):
                    max_ctx = max(max_ctx, int(v))

            DEFAULT_MODEL_PARAMS["ollama"] = {
                k: v for k, v in {
                    "temperature": params.get("temperature"),
                    "top_p": params.get("top_p"),
                    "top_k": int(params["top_k"]) if "top_k" in params else None,
                    "num_ctx": max_ctx or (int(params["num_ctx"]) if "num_ctx" in params else None),
                }.items() if v is not None
            }
        except Exception:
            pass  # Ollama may not be running at startup

    # vLLM
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{VLLM_URL}/v1/models")
            resp.raise_for_status()
            models = resp.json().get("data", [])
            if models:
                model_id = models[0]["id"]
                # Query max_model_len from /v1/models detail
                max_len = models[0].get("max_model_len")
                DEFAULT_MODEL_PARAMS["vllm"] = {
                    k: v for k, v in {
                        "max_model_len": max_len,
                    }.items() if v is not None
                }
    except Exception:
        pass  # vLLM may not be running at startup


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
