"""Shared test fixtures — PostgreSQL test DB, mock auth, test client.

Uses the same PostgreSQL instance with a separate 'aviary_test' database.
The test app has no lifespan (no background tasks, no OIDC init, no Redis).
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.oidc import TokenClaims
from app.db.models import Base, User
from app.db.session import get_db

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://aviary:aviary@postgres:5432/aviary_test",
)

from sqlalchemy.pool import NullPool

engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
test_session_factory = async_sessionmaker(engine, expire_on_commit=False)


# ── Build a test-only FastAPI app (no lifespan side effects) ──

@asynccontextmanager
async def _noop_lifespan(app: FastAPI):
    yield


def _create_test_app() -> FastAPI:
    """Create a FastAPI instance with the same routes but no lifespan."""
    from app.config import settings
    from app.routers import agents, auth, catalog, inference, sessions
    from fastapi.middleware.cors import CORSMiddleware

    test_app = FastAPI(title="Aviary API Test", lifespan=_noop_lifespan)
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    test_app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    test_app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
    test_app.include_router(catalog.router, prefix="/api/catalog", tags=["catalog"])
    test_app.include_router(inference.router, prefix="/api/inference", tags=["inference"])
    test_app.include_router(sessions.router, prefix="/api", tags=["sessions"])

    @test_app.get("/api/health")
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


@pytest.fixture(autouse=True)
def _mock_agent_supervisor():
    """Stub out supervisor HTTP calls — the ServiceClient is never initialized in tests."""
    targets = [
        "post_message",
        "abort_stream",
        "cleanup_session",
        "health_check",
    ]
    patchers = [
        patch(f"app.services.agent_supervisor.{name}", new_callable=AsyncMock)
        for name in targets
    ]
    for p in patchers:
        p.start()
    yield
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


# ── Auth fixtures ─────────────────────────────────────────────

@pytest.fixture
def user1_claims() -> TokenClaims:
    return TokenClaims(
        sub="user1-sub-001", email="user1@test.com",
        display_name="User One", roles=[], groups=["engineering"],
    )


@pytest.fixture
def user2_claims() -> TokenClaims:
    return TokenClaims(
        sub="user2-sub-002", email="user2@test.com",
        display_name="User Two", roles=[], groups=["engineering", "product"],
    )


@pytest.fixture
def user3_claims() -> TokenClaims:
    return TokenClaims(
        sub="user3-sub-003", email="user3@test.com",
        display_name="User Three", roles=[], groups=["data-science"],
    )


# Map fake tokens to claims for multi-user tests
_TOKEN_CLAIMS: dict[str, TokenClaims] = {}


def _setup_auth_override():
    """Install a single get_current_user override that dispatches by Bearer token."""
    from app.auth.dependencies import get_current_user, _upsert_user
    from fastapi import Depends
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from sqlalchemy import select

    security = HTTPBearer()

    async def _mock_get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ):
        token = credentials.credentials
        claims = _TOKEN_CLAIMS.get(token)
        if not claims:
            raise Exception(f"Unknown test token: {token}")
        async with test_session_factory() as session:
            user = await _upsert_user(session, claims)
            await session.commit()
            result = await session.execute(select(User).where(User.id == user.id))
            return result.scalar_one()

    app.dependency_overrides[get_current_user] = _mock_get_current_user


_setup_auth_override()


def _make_client(claims: TokenClaims, token: str) -> AsyncClient:
    _TOKEN_CLAIMS[token] = claims
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.fixture
def user1_client(user1_claims) -> AsyncClient:
    return _make_client(user1_claims, "test-token-user1")


@pytest.fixture
def user2_client(user2_claims) -> AsyncClient:
    return _make_client(user2_claims, "test-token-user2")


@pytest.fixture
def user3_client(user3_claims) -> AsyncClient:
    return _make_client(user3_claims, "test-token-user3")
