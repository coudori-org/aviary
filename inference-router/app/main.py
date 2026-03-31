"""Inference Router — Anthropic Messages API compatible proxy.

Exposes /v1/messages so that claude-agent-sdk (via ANTHROPIC_BASE_URL) can
send requests here transparently. The router determines the backend from the
model name and proxies the request, preserving the full Anthropic API format
including tools, tool_use, streaming, etc.

Architecture:
  claude-agent-sdk → Claude Code CLI → Anthropic SDK
    → POST http://inference-router:8080/v1/messages
    → Router inspects model name → routes to correct backend
    → Response streamed back in Anthropic SSE format
"""

import json
import logging
import os

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from app.backends import (
    ANTHROPIC_API_KEY,
    CLAUDE_API_URL,
    OLLAMA_URL,
    VLLM_URL,
    get_proxy_url,
    resolve_backend,
    resolve_model,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Aviary Inference Router", version="0.1.0")


@app.post("/v1/messages")
async def proxy_messages(request: Request):
    """Transparent proxy for Anthropic Messages API.

    Reads the model name from the request body, determines the backend,
    and proxies the entire request (including tools, system, etc.) as-is.
    """
    body_bytes = await request.body()
    body = json.loads(body_bytes)
    model = body.get("model", "default")
    backend = resolve_backend(model)
    model = resolve_model(model, backend)
    body["model"] = model
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
        "max_tokens": body.get("max_tokens", 8192),
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
            {"id": "claude-opus-4-20250514", "name": "claude-opus-4-20250514"},
            {"id": "claude-sonnet-4-20250514", "name": "claude-sonnet-4-20250514"},
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
