"""Prometheus metrics for the supervisor.

Exposed at GET /metrics (text format 0.0.4) when METRICS_ENABLED.

Designed for the RED method (Rate / Errors / Duration) plus a few gauges
that let ops see in-flight load at a glance. Label sets are kept small to
avoid cardinality blow-up: no session_id, agent_id, or stream_id labels.
"""

from prometheus_client import Counter, Gauge, Histogram

# Agent turn durations range from a second to many minutes (long-horizon
# tool-using turns). These buckets give enough resolution to spot SLO
# violations across that entire range.
_TURN_DURATION_BUCKETS = (0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, float("inf"))
# TTFB: runtime should emit `query_started` very quickly once it accepts.
_TTFB_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, float("inf"))
# External dependency (Vault/Redis) — sub-second p99 expected.
_EXT_DEP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, float("inf"))


# ── Counters ────────────────────────────────────────────────────────────────

publish_requests_total = Counter(
    "aviary_supervisor_publish_requests_total",
    "Publish requests handled by the supervisor.",
    ["status"],  # complete | error | aborted | disconnected
)

a2a_requests_total = Counter(
    "aviary_supervisor_a2a_requests_total",
    "A2A sub-agent stream requests handled by the supervisor.",
    ["status"],  # complete | error
)

sse_events_total = Counter(
    "aviary_supervisor_sse_events_total",
    "Runtime SSE events consumed by the supervisor.",
    ["event_type"],
)

runtime_http_errors_total = Counter(
    "aviary_supervisor_runtime_http_errors_total",
    "Non-2xx HTTP responses from the runtime pool.",
    ["status_code"],
)

abort_requests_total = Counter(
    "aviary_supervisor_abort_requests_total",
    "Abort requests received on /v1/streams/{id}/abort.",
    ["via"],  # local | broadcast
)

redis_errors_total = Counter(
    "aviary_supervisor_redis_errors_total",
    "Redis operation failures.",
    ["operation"],
)


# ── Gauges ──────────────────────────────────────────────────────────────────

active_streams = Gauge(
    "aviary_supervisor_active_streams",
    "Currently in-flight /message streams on this replica.",
)

active_a2a_streams = Gauge(
    "aviary_supervisor_active_a2a_streams",
    "Currently in-flight /a2a sub-agent streams on this replica.",
)


# ── Histograms ──────────────────────────────────────────────────────────────

publish_duration_seconds = Histogram(
    "aviary_supervisor_publish_duration_seconds",
    "Wall-clock time from publish request start to finish.",
    buckets=_TURN_DURATION_BUCKETS,
)

a2a_duration_seconds = Histogram(
    "aviary_supervisor_a2a_duration_seconds",
    "Wall-clock time for /a2a sub-agent streams.",
    buckets=_TURN_DURATION_BUCKETS,
)

time_to_query_started_seconds = Histogram(
    "aviary_supervisor_time_to_query_started_seconds",
    "Time from publish start to the runtime's first `query_started` event (TTFB).",
    buckets=_TTFB_BUCKETS,
)

vault_fetch_duration_seconds = Histogram(
    "aviary_supervisor_vault_fetch_duration_seconds",
    "Time spent fetching user credentials from Vault.",
    buckets=_EXT_DEP_BUCKETS,
)
