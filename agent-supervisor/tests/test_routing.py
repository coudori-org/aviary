from app.routing import resolve_runtime_base


def test_resolve_uses_override():
    assert resolve_runtime_base("http://custom:3000") == "http://custom:3000"


def test_resolve_uses_default_when_null():
    from app.config import settings
    assert resolve_runtime_base(None) == settings.supervisor_default_runtime_endpoint


def test_resolve_uses_default_when_empty():
    from app.config import settings
    # Empty string is falsy → falls back to default.
    assert resolve_runtime_base("") == settings.supervisor_default_runtime_endpoint
