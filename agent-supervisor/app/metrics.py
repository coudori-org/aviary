"""Prometheus metrics for the supervisor.

Exposed at GET /metrics (text format 0.0.4) when METRICS_ENABLED.
"""

from prometheus_client import Counter, Histogram

publish_requests_total = Counter(
    "aviary_supervisor_publish_requests_total",
    "Publish requests handled by the supervisor.",
    ["status"],  # complete | error
)

sse_events_total = Counter(
    "aviary_supervisor_sse_events_total",
    "Runtime SSE events consumed by the supervisor.",
    ["event_type"],
)

redis_errors_total = Counter(
    "aviary_supervisor_redis_errors_total",
    "Redis operations that raised inside the publish path.",
)

publish_duration_seconds = Histogram(
    "aviary_supervisor_publish_duration_seconds",
    "Wall-clock time from publish request start to finish.",
)
