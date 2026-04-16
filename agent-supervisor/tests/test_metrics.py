from fastapi.testclient import TestClient


def test_metrics_endpoint_returns_prometheus_format():
    from app.main import app
    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    # Metric definitions appear even before any samples.
    assert "aviary_supervisor_publish_requests_total" in body
    assert "aviary_supervisor_sse_events_total" in body
