import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry import metrics as otel_metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View

from app import redis_client
from app.auth.oidc import dev_user_sub, idp_enabled, init_oidc
from app.config import settings
from app.routers import agents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Pinned via OTel Views so boundaries reach the backend regardless of SDK default.
_TURN_BUCKETS = [0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600]
_TTFB_BUCKETS = [0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30]
_EXT_DEP_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5]

_BUCKET_VIEWS = [
    ("aviary_supervisor_publish_duration_seconds", _TURN_BUCKETS),
    ("aviary_supervisor_a2a_duration_seconds", _TURN_BUCKETS),
    ("aviary_supervisor_time_to_query_started_seconds", _TTFB_BUCKETS),
    ("aviary_supervisor_vault_fetch_duration_seconds", _EXT_DEP_BUCKETS),
]


def _init_otel_metrics() -> MeterProvider | None:
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        logger.info("OTel metrics disabled (OTEL_EXPORTER_OTLP_ENDPOINT unset)")
        return None

    views = [
        View(
            instrument_name=name,
            aggregation=ExplicitBucketHistogramAggregation(boundaries=buckets),
        )
        for name, buckets in _BUCKET_VIEWS
    ]
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(),
        export_interval_millis=settings.otel_metric_export_interval_ms,
    )
    provider = MeterProvider(metric_readers=[reader], views=views)
    otel_metrics.set_meter_provider(provider)
    return provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    meter_provider = _init_otel_metrics()
    await redis_client.init_redis()
    await init_oidc()
    if not idp_enabled():
        logger.warning(
            "OIDC disabled — INSECURE dev mode. Every caller is treated as "
            "sub=%r. DO NOT deploy this configuration to production; set "
            "OIDC_ISSUER to enable JWT validation.",
            dev_user_sub(),
        )
    agents.start_abort_listener()
    try:
        yield
    finally:
        await agents.stop_abort_listener()
        await redis_client.close_redis()
        if meter_provider:
            meter_provider.shutdown()


app = FastAPI(title="Aviary Agent Supervisor", version="0.4.0", lifespan=lifespan)
app.include_router(agents.router, prefix="/v1", tags=["sessions"])


@app.get("/v1/health")
async def health():
    return {"status": "ok"}
