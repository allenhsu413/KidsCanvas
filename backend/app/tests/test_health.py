"""Unit tests for health endpoint."""
from ..api.routes.health import read_health


def test_health_endpoint_returns_ok() -> None:
    """Health endpoint should respond with service status."""
    payload = read_health()

    assert payload["status"] == "ok"
    assert "service" in payload
