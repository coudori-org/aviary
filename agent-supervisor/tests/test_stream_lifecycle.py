"""Focused tests for _StreamLifecycle state transitions + metric bumps."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app import metrics
from app.services.stream_service import _StreamLifecycle


def _metric_value(labeled, **labels) -> float:
    return labeled.labels(**labels)._value.get()


@pytest.mark.asyncio
async def test_begin_sets_status_keys_and_increments_active():
    lc = _StreamLifecycle("s1", "stream-1")
    before = metrics.active_streams._value.get()
    with (
        patch("app.redis_client.set_stream_status", new_callable=AsyncMock) as stream_status,
        patch("app.redis_client.set_session_status", new_callable=AsyncMock) as session_status,
        patch("app.redis_client.set_session_latest_stream", new_callable=AsyncMock) as latest,
    ):
        await lc.begin()

    stream_status.assert_awaited_once_with("stream-1", "streaming")
    session_status.assert_awaited_once_with("s1", "streaming")
    latest.assert_awaited_once_with("s1", "stream-1")
    assert metrics.active_streams._value.get() == before + 1


@pytest.mark.asyncio
async def test_end_decrements_active_and_flips_session_idle():
    lc = _StreamLifecycle("s2", "stream-2")
    metrics.active_streams.inc()
    before = metrics.active_streams._value.get()
    with patch("app.redis_client.set_session_status", new_callable=AsyncMock) as session_status:
        await lc.end()

    session_status.assert_awaited_once_with("s2", "idle")
    assert metrics.active_streams._value.get() == before - 1


@pytest.mark.asyncio
async def test_mark_complete_writes_status_and_bumps_counter():
    lc = _StreamLifecycle("s3", "stream-3")
    before = _metric_value(metrics.publish_requests_total, status="complete")
    with patch("app.redis_client.set_stream_status", new_callable=AsyncMock) as stream_status:
        await lc.mark_complete()

    stream_status.assert_awaited_once_with("stream-3", "complete")
    assert _metric_value(metrics.publish_requests_total, status="complete") == before + 1


@pytest.mark.asyncio
async def test_mark_error_writes_status_and_bumps_counter():
    lc = _StreamLifecycle("s4", "stream-4")
    before = _metric_value(metrics.publish_requests_total, status="error")
    with patch("app.redis_client.set_stream_status", new_callable=AsyncMock) as stream_status:
        await lc.mark_error()

    stream_status.assert_awaited_once_with("stream-4", "error")
    assert _metric_value(metrics.publish_requests_total, status="error") == before + 1


@pytest.mark.asyncio
async def test_mark_aborted_writes_status_and_bumps_counter():
    lc = _StreamLifecycle("s5", "stream-5")
    before = _metric_value(metrics.publish_requests_total, status="aborted")
    with patch("app.redis_client.set_stream_status", new_callable=AsyncMock) as stream_status:
        await lc.mark_aborted()

    stream_status.assert_awaited_once_with("stream-5", "aborted")
    assert _metric_value(metrics.publish_requests_total, status="aborted") == before + 1
