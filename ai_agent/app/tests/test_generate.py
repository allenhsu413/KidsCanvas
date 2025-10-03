"""Tests for the AI agent generation endpoint."""
from fastapi.testclient import TestClient

from app.main import app


def test_generate_returns_storybook_patch() -> None:
    """The endpoint should respond with a storybook patch payload."""
    client = TestClient(app)

    payload = {
        "roomId": "room-123",
        "objectId": "object-456",
        "anchorRegion": {"type": "ring", "radius": 128},
    }

    response = client.post("/generate", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["patch"]["style"] == "storybook"
    assert data["patch"]["roomId"] == payload["roomId"]
