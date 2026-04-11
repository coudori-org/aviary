"""Egress proxy for Aviary agent pods.

All external HTTP/HTTPS traffic from agent pods is routed through this proxy.
Per-agent egress policies (domain wildcards + CIDR) are enforced here.

Agent identification: source pod IP → K8s API lookup → namespace → agent ID.
Policy source: PostgreSQL ``agents.policy`` column (queried on every request).
"""

import asyncio
import contextlib
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import httpx

from app.policy import PolicyChecker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("egress-proxy")

PROXY_PORT = int(os.environ.get("PROXY_PORT", "8080"))
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://aviary:aviary@localhost:5432/aviary")
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8081"))

# ── Caches ──────────────────────────────────────────────────────
_db_pool: asyncpg.Pool | None = None
_ip_to_agent: dict[str, tuple[float, str]] = {}  # pod IP → (timestamp, agent_id)
_IP_CACHE_TTL = 300  # seconds — pod IPs can be reassigned

# K8s in-cluster config
_K8S_HOST = os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
_K8S_PORT = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
_K8S_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
_K8S_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"


# ── DB helpers ─────────────────────────────────────────────────
async def _get_pool() -> asyncpg.Pool:
    global _db_pool
    if _db_pool is None:
        # Strip +asyncpg suffix if present (shared DATABASE_URL format)
        dsn = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        _db_pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    return _db_pool


async def _get_policy(agent_id: str) -> PolicyChecker:
    """Load per-agent policy from DB. Both missing row and empty policy deny by default."""
    pool = await _get_pool()
    row = await pool.fetchrow(
        "SELECT policy FROM agents WHERE id = $1::uuid", agent_id,
    )
    if row is None:
        logger.warning("No agent row for id=%s — denying egress by default", agent_id)
        return PolicyChecker.from_policy({})
    if not row["policy"]:
        logger.warning("Agent %s has no policy configured — denying egress by default", agent_id)
        return PolicyChecker.from_policy({})
    policy = row["policy"] if isinstance(row["policy"], dict) else json.loads(row["policy"])
    return PolicyChecker.from_policy(policy)


# ── K8s pod IP → agent ID resolution ───────────────────────────
async def _resolve_agent_id(source_ip: str) -> str | None:
    """Resolve a pod's IP to an agent ID via K8s API."""
    if source_ip in _ip_to_agent:
        ts, agent_id = _ip_to_agent[source_ip]
        if time.monotonic() - ts < _IP_CACHE_TTL:
            return agent_id

    try:
        token = Path(_K8S_TOKEN_PATH).read_text().strip()
    except (FileNotFoundError, PermissionError):
        logger.warning("K8s token not available — cannot resolve pod IPs")
        return None

    url = f"https://{_K8S_HOST}:{_K8S_PORT}/api/v1/pods?fieldSelector=status.podIP={source_ip}"
    async with httpx.AsyncClient(verify=_K8S_CA_PATH, timeout=5) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            logger.error("K8s API returned %d for pod lookup: %s", resp.status_code, resp.text[:200])
            return None
        items = resp.json().get("items", [])
        if not items:
            return None
        ns = items[0]["metadata"]["namespace"]
        # agent namespace format: agent-{uuid}
        if ns.startswith("agent-"):
            agent_id = ns[len("agent-"):]
            _ip_to_agent[source_ip] = (time.monotonic(), agent_id)
            return agent_id
    return None


# ── HTTP CONNECT tunnel (HTTPS) ────────────────────────────────
async def _handle_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, host: str, port: int):
    """Establish a TCP tunnel for HTTPS CONNECT requests."""
    try:
        remote_reader, remote_writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=10,
        )
    except (OSError, asyncio.TimeoutError) as exc:
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        await writer.drain()
        logger.warning("CONNECT tunnel failed to %s:%d — %s", host, port, exc)
        return

    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await writer.drain()

    async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter):
        try:
            while True:
                data = await src.read(65536)
                if not data:
                    break
                dst.write(data)
                await dst.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        finally:
            dst.close()

    await asyncio.gather(_pipe(reader, remote_writer), _pipe(remote_reader, writer))


# ── HTTP forward proxy ─────────────────────────────────────────
async def _handle_http(writer: asyncio.StreamWriter, method: str, url: str, http_version: str, headers: list[tuple[str, str]], body: bytes):
    """Forward a plain HTTP request."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            req_headers = {k: v for k, v in headers if k.lower() not in ("host", "proxy-connection", "proxy-authorization")}
            resp = await client.request(
                method=method,
                url=url,
                headers=req_headers,
                content=body,
            )
            status_line = f"HTTP/1.1 {resp.status_code} {resp.reason_phrase}\r\n"
            writer.write(status_line.encode())
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding",):
                    writer.write(f"{k}: {v}\r\n".encode())
            writer.write(b"\r\n")
            writer.write(resp.content)
            await writer.drain()
        except httpx.HTTPError as exc:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await writer.drain()
            logger.warning("HTTP forward failed for %s — %s", url, exc)


# ── Main connection handler ─────────────────────────────────────
async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    source_ip = peer[0] if peer else "unknown"

    try:
        # Read request line
        request_line = await asyncio.wait_for(reader.readline(), timeout=10)
        if not request_line:
            return
        request_line = request_line.decode("utf-8", errors="replace").strip()
        parts = request_line.split(" ", 2)
        if len(parts) < 3:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            return

        method, target, http_version = parts

        # Read headers
        headers: list[tuple[str, str]] = []
        content_length = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=10)
            if line in (b"\r\n", b"\n", b""):
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if ":" in decoded:
                k, v = decoded.split(":", 1)
                headers.append((k.strip(), v.strip()))
                if k.strip().lower() == "content-length":
                    content_length = int(v.strip())

        # Extract destination host:port
        if method == "CONNECT":
            # CONNECT host:port
            if ":" in target:
                host, port_str = target.rsplit(":", 1)
                port = int(port_str)
            else:
                host, port = target, 443
        else:
            parsed = urlparse(target)
            host = parsed.hostname or ""
            port = parsed.port or 80

        # Resolve agent and check policy
        agent_id = await _resolve_agent_id(source_ip)
        if agent_id:
            checker = await _get_policy(agent_id)
            if not checker.is_allowed(host, port):
                logger.info("DENIED %s → %s:%d (agent=%s)", method, host, port, agent_id)
                # Close immediately without response — client sees connection
                # reset, which triggers fast failure instead of retry loops.
                writer.close()
                return
        else:
            # Unknown source — deny by default
            logger.warning("DENIED %s → %s:%d (unknown source IP %s)", method, host, port, source_ip)
            writer.close()
            return

        logger.info("ALLOWED %s → %s:%d (agent=%s)", method, host, port, agent_id)

        if method == "CONNECT":
            await _handle_connect(reader, writer, host, port)
        else:
            body = await reader.read(content_length) if content_length else b""
            await _handle_http(writer, method, target, http_version, headers, body)

    except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError):
        pass
    except Exception:
        logger.exception("Unexpected error handling connection from %s", source_ip)
    finally:
        with contextlib.suppress(Exception):
            writer.close()
            await writer.wait_closed()


# ── Health endpoint ───────────────────────────────────────────
from fastapi import FastAPI

health_app = FastAPI(title="Egress Proxy Health")


@health_app.get("/health")
async def health():
    return {"status": "ok"}


# ── Entrypoint ──────────────────────────────────────────────────
async def main():
    # Start proxy server
    proxy_server = await asyncio.start_server(_handle_client, "0.0.0.0", PROXY_PORT)
    logger.info("Egress proxy listening on :%d", PROXY_PORT)

    # Start health endpoint on separate port
    import uvicorn
    health_config = uvicorn.Config(health_app, host="0.0.0.0", port=HEALTH_PORT, log_level="warning")
    health_server = uvicorn.Server(health_config)

    await asyncio.gather(
        proxy_server.serve_forever(),
        health_server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
