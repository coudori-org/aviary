"""Override parent conftest autouse fixtures for pure unit tests (no DB needed)."""

import pytest


@pytest.fixture(autouse=True)
async def _ensure_test_db():
    """No-op override — unit tests don't need a database."""
    yield


@pytest.fixture(autouse=True)
async def clean_tables():
    """No-op override — unit tests don't need table cleanup."""
    yield
