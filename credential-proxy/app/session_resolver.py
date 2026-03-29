"""Resolve session ID to agent credentials via database lookup."""

import os

import asyncpg

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://aviary:aviary@postgres:5432/aviary",
)

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def get_credentials_for_session(session_id: str) -> list[dict]:
    """Look up all credentials for the agent associated with a session.

    Returns list of {"name": "GITHUB_TOKEN", "vault_path": "aviary/agents/.../credentials/GITHUB_TOKEN"}
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ac.name, ac.vault_path
            FROM agent_credentials ac
            JOIN sessions s ON s.agent_id = ac.agent_id
            WHERE s.id = $1::uuid
            """,
            session_id,
        )
        return [{"name": row["name"], "vault_path": row["vault_path"]} for row in rows]
