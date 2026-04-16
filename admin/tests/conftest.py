"""Admin test fixtures — PostgreSQL test DB, no auth, test client."""

import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

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
    from app.routers import agents

    test_app = FastAPI(title="Aviary Admin Test", lifespan=_noop_lifespan)
    test_app.include_router(agents.router, prefix="/api/agents", tags=["agents"])

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


_TABLES = ["messages", "sessions", "agents", "users"]


@pytest.fixture(autouse=True)
async def clean_tables():
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_TABLES)} CASCADE"))
    yield


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
def client() -> AsyncClient:
    """Admin console has no auth — just a plain HTTP client."""
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.fixture
async def seed_agent() -> Agent:
    """Create a test agent directly in DB (bypassing API server)."""
    from sqlalchemy import select
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
        )
        db.add(agent)
        await db.flush()
        await db.commit()

        result = await db.execute(select(Agent).where(Agent.id == agent.id))
        return result.scalar_one()
