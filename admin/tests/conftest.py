"""Admin test fixtures — PostgreSQL test DB, no auth, test client."""

import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from aviary_shared.db.models import Agent, Base, User
from app.db import get_db

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://aviary:aviary@postgres:5432/aviary_test",
)

engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
test_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def _noop_lifespan(app: FastAPI):
    yield


def _create_test_app() -> FastAPI:
    from app.routers import agents, deployments, policies

    test_app = FastAPI(title="Aviary Admin Test", lifespan=_noop_lifespan)
    test_app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
    test_app.include_router(deployments.router, prefix="/api/agents", tags=["deployments"])
    test_app.include_router(policies.router, prefix="/api/agents", tags=["policies"])

    @test_app.get("/health")
    async def health():
        return {"status": "ok"}

    return test_app


app = _create_test_app()


# ── DB fixtures ───────────────────────────────────────────────

_db_initialized = False


@pytest.fixture(autouse=True)
async def _ensure_test_db():
    global _db_initialized
    if _db_initialized:
        return

    admin_url = TEST_DB_URL.rsplit("/", 1)[0] + "/aviary"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        row = await conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'aviary_test'"))
        if not row.scalar():
            await conn.execute(text("CREATE DATABASE aviary_test"))
    await admin_engine.dispose()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    _db_initialized = True


_TABLES = [
    "messages", "session_participants", "sessions",
    "agent_credentials", "agent_acl", "agents",
    "team_members", "teams", "users",
]


@pytest.fixture(autouse=True)
async def clean_tables():
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} CASCADE"))
    yield


@pytest.fixture(autouse=True)
def _mock_supervisor_client():
    """Stub out supervisor HTTP calls — the ServiceClient is never initialized in tests."""
    targets = [
        "create_namespace",
        "update_network_policy",
        "delete_namespace",
        "ensure_deployment",
        "get_deployment_status",
        "scale_deployment",
        "scale_to_zero",
        "delete_deployment",
        "rolling_restart",
        "get_pod_metrics",
    ]
    patchers = [
        patch(f"app.services.supervisor_client.{name}", new_callable=AsyncMock)
        for name in targets
    ]
    mocks = {name: p.start() for name, p in zip(targets, patchers)}

    # Default: simulate "no deployment exists" for the seeded agent — individual
    # tests that need a live deployment override these via their own patch blocks.
    def _raise_404(*args, **kwargs):
        req = httpx.Request("GET", "http://supervisor/test")
        raise httpx.HTTPStatusError(
            "Not Found", request=req, response=httpx.Response(404, request=req),
        )

    mocks["create_namespace"].return_value = "agent-test"
    mocks["ensure_deployment"].return_value = {"replicas": 1, "min_pods": 1, "max_pods": 3}
    mocks["get_deployment_status"].side_effect = _raise_404
    mocks["update_network_policy"].side_effect = _raise_404
    mocks["get_pod_metrics"].return_value = {"pods": []}
    yield mocks
    for p in patchers:
        p.stop()


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = _override_get_db


# ── Client fixture ────────────────────────────────────────────

@pytest.fixture
def client() -> AsyncClient:
    """Admin console has no auth — just a plain HTTP client."""
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


# ── Seed helpers ──────────────────────────────────────────────

@pytest.fixture
async def seed_agent() -> Agent:
    """Create a test agent directly in DB (bypassing API server)."""
    async with test_session_factory() as db:
        user = User(
            external_id="test-owner-001",
            email="owner@test.com",
            display_name="Test Owner",
        )
        db.add(user)
        await db.flush()

        agent = Agent(
            name="Test Agent",
            slug=f"test-agent-{uuid.uuid4().hex[:8]}",
            description="A test agent",
            owner_id=user.id,
            instruction="Be helpful.",
            model_config_json={"backend": "dummy-backend", "model": "dummy-model"},
            tools=["read_file"],
            mcp_servers=[],
            policy={},
            visibility="public",
        )
        db.add(agent)
        await db.flush()
        await db.commit()

        # Re-fetch to get all defaults populated
        from sqlalchemy import select
        result = await db.execute(select(Agent).where(Agent.id == agent.id))
        return result.scalar_one()
