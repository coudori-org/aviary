"""Inference Router — Anthropic Messages API compatible proxy.

Exposes /v1/messages so that claude-agent-sdk (via ANTHROPIC_BASE_URL) can
send requests here transparently. The backend is determined by the required
X-Backend header, injected by the runtime Pod via ANTHROPIC_CUSTOM_HEADERS.

Architecture:
  claude-agent-sdk → Claude Code CLI → Anthropic SDK
    → POST http://inference-router:8080/v1/messages
    → Router reads X-Backend header → routes to correct backend
    → Response streamed back in Anthropic SSE format
"""

import json
import logging
import os

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.backends import (
    ANTHROPIC_API_KEY,
    CLAUDE_API_URL,
    OLLAMA_URL,
    VALID_BACKENDS,
    VLLM_URL,
    get_proxy_url,
    resolve_model,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Aviary Inference Router", version="0.1.0")


@app.post("/v1/messages")
async def proxy_messages(request: Request):
    """Transparent proxy for Anthropic Messages API.

    Reads the model name from the request body, determines the backend,
    and proxies the entire request (including tools, system, etc.) as-is.
    """
    backend = request.headers.get("x-backend")
    if not backend or backend not in VALID_BACKENDS:
        raise HTTPException(
            status_code=400,
            detail=f"Missing or invalid X-Backend header. Must be one of: {', '.join(sorted(VALID_BACKENDS))}",
        )

    body_bytes = await request.body()
    body = json.loads(body_bytes)
    model = body.get("model", "default")
    model = resolve_model(model, backend)
    body["model"] = model

    # Inject sampling parameters from custom headers (set by runtime Pod)
    _SAMPLING_HEADERS = {
        "x-sampling-temperature": ("temperature", float),
        "x-sampling-top-p": ("top_p", float),
        "x-sampling-top-k": ("top_k", int),
        "x-sampling-num-ctx": ("num_ctx", int),
    }
    for header, (body_key, cast) in _SAMPLING_HEADERS.items():
        val = request.headers.get(header)
        if val is not None:
            try:
                body.setdefault(body_key, cast(val))
            except (ValueError, TypeError):
                pass

    body_bytes = json.dumps(body).encode()
    is_stream = body.get("stream", False)

    logger.info("Routing model=%s → backend=%s stream=%s", model, backend, is_stream)

    if backend == "vllm":
        return await _proxy_vllm(body, request.headers)

    if backend == "bedrock":
        return await _proxy_bedrock(body, request.headers)

    # Claude and Ollama both speak Anthropic Messages API — transparent proxy
    upstream_url = get_proxy_url(backend)
    target_url = f"{upstream_url}/v1/messages"

    # Build upstream headers
    upstream_headers = {
        "content-type": "application/json",
        "anthropic-version": request.headers.get("anthropic-version", "2023-06-01"),
    }

    # API key: use the one from request, or fall back to env
    api_key = request.headers.get("x-api-key", "")
    if backend == "claude":
        upstream_headers["x-api-key"] = api_key or ANTHROPIC_API_KEY
    elif backend == "ollama":
        upstream_headers["x-api-key"] = "ollama"

    # Forward any anthropic-beta header (for extended thinking, etc.)
    beta = request.headers.get("anthropic-beta")
    if beta:
        upstream_headers["anthropic-beta"] = beta

    if is_stream:
        return StreamingResponse(
            _stream_proxy(target_url, upstream_headers, body_bytes),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(target_url, headers=upstream_headers, content=body_bytes)
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
            )


async def _stream_proxy(url: str, headers: dict, body: bytes):
    """Stream an upstream SSE response, yielding each line as-is."""
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", url, headers=headers, content=body) as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk


async def _proxy_vllm(body: dict, req_headers):
    """Translate Anthropic Messages API → OpenAI Chat Completions API for vLLM,
    then translate the response back to Anthropic format."""
    # Convert Anthropic messages to OpenAI format
    oai_messages = []
    system = body.get("system")
    if system:
        if isinstance(system, str):
            oai_messages.append({"role": "system", "content": system})
        elif isinstance(system, list):
            text = " ".join(b.get("text", "") for b in system if b.get("type") == "text")
            oai_messages.append({"role": "system", "content": text})

    for msg in body.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, list):
            # Extract text blocks
            text = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
            content = text
        oai_messages.append({"role": msg["role"], "content": content})

    oai_body = {
        "model": body["model"],
        "messages": oai_messages,
        "temperature": body.get("temperature", 0.7),
        "stream": body.get("stream", False),
    }

    if body.get("stream"):
        return StreamingResponse(
            _vllm_stream_to_anthropic(oai_body),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    else:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{VLLM_URL}/v1/chat/completions", json=oai_body)
            oai_resp = resp.json()
            # Convert to Anthropic format
            anthropic_resp = {
                "id": oai_resp.get("id", ""),
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": oai_resp["choices"][0]["message"]["content"]}],
                "model": body["model"],
                "stop_reason": "end_turn",
            }
            return Response(content=json.dumps(anthropic_resp), media_type="application/json")


async def _vllm_stream_to_anthropic(oai_body: dict):
    """Stream vLLM OpenAI response, converting to Anthropic SSE format."""
    # Emit Anthropic-format event stream
    yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': 'msg_router', 'type': 'message', 'role': 'assistant', 'content': [], 'model': oai_body['model']}})}\n\n"
    yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}})}\n\n"

    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("POST", f"{VLLM_URL}/v1/chat/completions", json=oai_body) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                chunk = json.loads(data_str)
                text = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if text:
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': text}})}\n\n"

    yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0})}\n\n"
    yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}})}\n\n"
    yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'})}\n\n"


async def _proxy_bedrock(body: dict, req_headers):
    """Route to AWS Bedrock via boto3."""
    try:
        import boto3
    except ImportError:
        return Response(
            content=json.dumps({"error": {"message": "boto3 not installed"}}),
            status_code=502,
        )

    # TODO: Implement Bedrock streaming proxy
    return Response(
        content=json.dumps({"error": {"message": "Bedrock proxy not yet implemented"}}),
        status_code=501,
    )


# ── Management endpoints ──────────────────────────────────────

@app.get("/v1/backends")
async def list_backends():
    return {"backends": ["claude", "ollama", "vllm", "bedrock"]}


@app.get("/v1/backends/{backend}/models")
async def list_models(backend: str):
    # TODO: Add RBAC filtering based on user claims (forwarded via headers)
    # once key management and tier-based access control are implemented.
    if backend == "claude":
        # TODO: Fetch dynamically from Anthropic API (GET /v1/models)
        # once API key management (platform key / per-tenant key from Vault) is in place.
        return {"models": [
            {"id": "claude-sonnet-4-6", "name": "claude-sonnet-4-6"},
            {"id": "claude-opus-4-6", "name": "claude-opus-4-6"},
        ]}
    elif backend == "ollama":
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{OLLAMA_URL}/api/tags")
                resp.raise_for_status()
                models = [
                    {"id": m["name"], "name": m["name"], "size": m.get("size")}
                    for m in resp.json().get("models", [])
                ]
                return {"models": models}
        except Exception as e:
            logger.warning("Ollama not reachable: %s", e)
            return {"models": [], "error": "Ollama not reachable"}
    elif backend == "vllm":
        # TODO: Fetch from vLLM API (GET /v1/models) when a serving engine is available.
        return {"models": [
            {"id": "meta-llama/Llama-3.3-70B-Instruct", "name": "meta-llama/Llama-3.3-70B-Instruct"},
        ]}
    return {"models": []}


@app.get("/v1/backends/{backend}/model-info")
async def get_model_info(backend: str, model: str):
    """Return default sampling parameters, context limits, and capabilities for a model."""
    if backend == "ollama":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/show", json={"name": model})
                resp.raise_for_status()
                data = resp.json()

            # Parse "key value" pairs from parameters text
            params: dict[str, float] = {}
            for line in (data.get("parameters") or "").strip().splitlines():
                parts = line.split()
                if len(parts) == 2:
                    try:
                        params[parts[0]] = float(parts[1])
                    except ValueError:
                        pass

            # Extract max context length from model_info
            model_info = data.get("model_info", {})
            max_ctx = 0
            for k, v in model_info.items():
                if k.endswith(".context_length") and isinstance(v, (int, float)):
                    max_ctx = max(max_ctx, int(v))

            # Capabilities from Ollama (v0.5+)
            caps = data.get("capabilities", [])

            return {
                "model": model,
                "backend": backend,
                "defaults": {
                    "temperature": params.get("temperature"),
                    "top_p": params.get("top_p"),
                    "top_k": int(params["top_k"]) if "top_k" in params else None,
                    "num_ctx": int(params["num_ctx"]) if "num_ctx" in params else None,
                },
                "limits": {
                    "max_context_length": max_ctx or None,
                },
                "capabilities": {
                    "vision": "vision" in caps,
                    "audio": "audio" in caps,
                    "tools": "tools" in caps,
                },
            }
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=f"Ollama error: {e.response.text}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Ollama not reachable: {e}")

    elif backend == "claude":
        return {
            "model": model,
            "backend": backend,
            "defaults": {"temperature": 1.0, "top_p": None, "top_k": None, "num_ctx": None},
            "limits": {"max_context_length": 200000},
            "capabilities": {"vision": True, "audio": False, "tools": True},
        }
    elif backend == "vllm":
        return {
            "model": model,
            "backend": backend,
            "defaults": {"temperature": 0.7, "top_p": None, "top_k": None, "num_ctx": None},
            "limits": {"max_context_length": None},
            "capabilities": {"vision": False, "audio": False, "tools": False},
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown backend: {backend}")


@app.get("/v1/backends/{backend}/health")
async def backend_health(backend: str):
    url_map = {"claude": CLAUDE_API_URL, "ollama": OLLAMA_URL, "vllm": VLLM_URL}
    url = url_map.get(backend)
    if not url:
        return {"status": "unknown"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(url)
            return {"status": "ok", "url": url}
    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


@app.get("/health")
async def health():
    return {"status": "ok"}
