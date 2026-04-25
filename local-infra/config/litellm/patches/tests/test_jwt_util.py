"""Unit tests for aviary_jwt_util.JwtValidator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from aviary_jwt_util import JwtValidator, is_jwt


def test_is_jwt_true_for_three_segment_token():
    assert is_jwt("a.b.c") is True


def test_is_jwt_false_for_virtual_key():
    assert is_jwt("sk-aviary-dev") is False


def test_is_jwt_false_for_empty():
    assert is_jwt("") is False


def test_rewrite_to_internal_rewrites_public_prefix():
    v = JwtValidator()
    v.issuer = "http://localhost:8080/realms/aviary"
    v.internal_issuer = "http://keycloak:8080/realms/aviary"
    assert v.rewrite_to_internal(
        "http://localhost:8080/realms/aviary/.well-known/openid-configuration"
    ) == "http://keycloak:8080/realms/aviary/.well-known/openid-configuration"


def test_rewrite_to_internal_is_noop_when_issuer_matches():
    v = JwtValidator()
    v.issuer = "http://keycloak:8080/realms/aviary"
    v.internal_issuer = "http://keycloak:8080/realms/aviary"
    url = "http://keycloak:8080/realms/aviary/protocol/openid-connect/token"
    assert v.rewrite_to_internal(url) == url


def test_token_cache_key_hashes_whole_token_not_just_signature():
    # Two tokens sharing a signature but with different payloads must produce
    # different cache keys — else a tampered payload with the original
    # signature would hit a stale cached sub.
    a = JwtValidator._token_cache_key("header.payload-A.signature")
    b = JwtValidator._token_cache_key("header.payload-B.signature")
    assert a != b


@pytest.mark.asyncio
async def test_extract_sub_caches_subsequent_calls():
    v = JwtValidator()
    token = "hdr.pl.sig"
    cache_key = JwtValidator._token_cache_key(token)
    v._sub_cache[cache_key] = ("cached-sub", 10_000_000_000)
    # ttl large, so the second call returns cached; no JWKS fetch.
    with patch.object(v, "_get_jwks", new_callable=AsyncMock) as jwks:
        sub = await v.extract_sub(token)
    assert sub == "cached-sub"
    jwks.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_sub_refetches_at_most_once_per_cooldown_on_unknown_kid():
    v = JwtValidator()
    # Bypass the sub cache by clearing it.
    v._sub_cache.clear()

    bad_jwks = {"keys": []}  # No keys — every lookup misses.
    call_count = {"force": 0, "normal": 0}

    async def fake_get_jwks(*, force: bool = False) -> dict:
        if force:
            call_count["force"] += 1
        else:
            call_count["normal"] += 1
        return bad_jwks

    with (
        patch("aviary_jwt_util._pyjwt.get_unverified_header", return_value={"kid": "x"}),
        patch.object(v, "_get_jwks", side_effect=fake_get_jwks),
    ):
        # First call pays a forced refetch; JWKS still misses so it raises.
        with pytest.raises(Exception, match="signing key not found"):
            await v.extract_sub("h.p.s1")
        # Second call within the cooldown window must NOT force-refetch again.
        with pytest.raises(Exception, match="signing key not found"):
            await v.extract_sub("h.p.s2")

    assert call_count["force"] == 1, "cooldown should suppress second force-refetch"
