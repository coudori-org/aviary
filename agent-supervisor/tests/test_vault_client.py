"""Vault client honors Vault when configured, falls back to config.yaml otherwise."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services import vault_client


@pytest.fixture(autouse=True)
def _reset_caches():
    vault_client._client = None
    vault_client._config_secrets.cache_clear()
    yield
    vault_client._client = None
    vault_client._config_secrets.cache_clear()


@pytest.mark.asyncio
async def test_fetch_uses_vault_when_addr_set(monkeypatch):
    monkeypatch.setattr(settings, "vault_addr", "http://vault.test:8200")
    monkeypatch.setattr(settings, "vault_token", "token")

    fake = AsyncMock(return_value="ghp_from_vault")
    with patch("aviary_shared.vault.VaultClient.read_user_credential", fake):
        creds = await vault_client.fetch_user_credentials("dev-user")

    assert creds == {"github_token": "ghp_from_vault"}
    fake.assert_awaited_once_with("dev-user", "aviary", "github-token")


@pytest.mark.asyncio
async def test_fetch_falls_back_to_config_when_vault_disabled(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "secrets:\n"
        "  dev-user:\n"
        "    aviary:\n"
        "      github-token: ghp_from_config\n"
    )
    monkeypatch.setattr(settings, "vault_addr", "")
    monkeypatch.setattr(settings, "vault_token", "")
    monkeypatch.setattr(settings, "llm_backends_config_path", str(cfg))

    creds = await vault_client.fetch_user_credentials("dev-user")
    assert creds == {"github_token": "ghp_from_config"}


@pytest.mark.asyncio
async def test_fetch_returns_empty_when_neither_source_has_creds(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "secrets:\n"
        "  other-user:\n"
        "    aviary:\n"
        "      github-token: ghp_x\n"
    )
    monkeypatch.setattr(settings, "vault_addr", "")
    monkeypatch.setattr(settings, "vault_token", "")
    monkeypatch.setattr(settings, "llm_backends_config_path", str(cfg))

    creds = await vault_client.fetch_user_credentials("dev-user")
    assert creds == {}
