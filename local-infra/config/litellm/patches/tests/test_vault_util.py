"""Unit tests for aviary_vault_util.fetch_credential."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

import aviary_vault_util


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=None, response=None,  # type: ignore[arg-type]
            )


class _FakeClient:
    def __init__(self, resp: _FakeResponse):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, *_, **__) -> _FakeResponse:
        return self._resp


@pytest.mark.asyncio
async def test_fetch_credential_returns_value_on_hit():
    resp = _FakeResponse(200, {"data": {"data": {"value": "secret-abc"}}})
    with patch("aviary_vault_util.httpx.AsyncClient", return_value=_FakeClient(resp)):
        value = await aviary_vault_util.fetch_credential("user-1", "github-token")
    assert value == "secret-abc"


@pytest.mark.asyncio
async def test_fetch_credential_returns_none_on_404(caplog):
    resp = _FakeResponse(404)
    caplog.set_level("DEBUG", logger="aviary_vault_util")
    with patch("aviary_vault_util.httpx.AsyncClient", return_value=_FakeClient(resp)):
        value = await aviary_vault_util.fetch_credential("user-1", "missing-key")
    assert value is None
    # Debug log should record the miss with user_sub + key for operator triage.
    assert any("Vault miss" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_fetch_credential_raises_on_transport_error():
    class _BoomClient(_FakeClient):
        async def get(self, *_, **__):
            raise httpx.ConnectError("no route")

    with patch(
        "aviary_vault_util.httpx.AsyncClient",
        return_value=_BoomClient(_FakeResponse(0)),
    ):
        with pytest.raises(Exception, match="Vault error"):
            await aviary_vault_util.fetch_credential("user-1", "some-key")


@pytest.mark.asyncio
async def test_fetch_credential_rejects_missing_config(monkeypatch):
    monkeypatch.setattr(aviary_vault_util, "VAULT_ADDR", "")
    with pytest.raises(Exception, match="Vault not configured"):
        await aviary_vault_util.fetch_credential("user-1", "any")


@pytest.mark.asyncio
async def test_fetch_credential_logs_warning_on_slow_fetch(monkeypatch, caplog):
    monkeypatch.setattr(aviary_vault_util, "_SLOW_FETCH_SECONDS", 0.0)
    resp = _FakeResponse(200, {"data": {"data": {"value": "ok"}}})
    caplog.set_level("WARNING", logger="aviary_vault_util")
    with patch("aviary_vault_util.httpx.AsyncClient", return_value=_FakeClient(resp)):
        await aviary_vault_util.fetch_credential("user-1", "slow-key")
    assert any("Vault fetch slow" in r.message for r in caplog.records)
