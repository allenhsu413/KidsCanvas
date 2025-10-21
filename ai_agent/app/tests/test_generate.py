"""Tests for the AI agent generation endpoint."""

import pytest
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
    patch = data["patch"]
    assert patch["style"] == "storybook"
    assert patch["roomId"] == payload["roomId"]
    assert "labels" in patch and isinstance(patch["labels"], list)
    assert patch["confidence"] == pytest.approx(0.92, rel=1e-6)
