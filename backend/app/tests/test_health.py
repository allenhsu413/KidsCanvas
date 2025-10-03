"""Unit tests for health endpoint."""
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_returns_ok() -> None:
    """Health endpoint should respond with service status."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
