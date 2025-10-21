from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from ..api.routes.events import get_next_event
from ..core.redis import RedisWrapper
from ..core.security import AuthenticatedSubject, UserRole
from ..services.strokes import OBJECT_EVENT_STREAM, WS_EVENT_STREAM


def test_get_next_event_returns_204_when_empty() -> None:
    redis = RedisWrapper()
    response = asyncio.run(
        get_next_event(
            redis=redis,
            limit=1,
            cursor=None,
            subject=AuthenticatedSubject(user_id=uuid4(), role=UserRole.MODERATOR),
        )
    )
    assert hasattr(response, "status_code")
    assert response.status_code == 204


def test_get_next_event_prioritises_oldest() -> None:
    redis = RedisWrapper()
    room_id = str(uuid4())

    newer_event = {
        "topic": "turn",
        "roomId": room_id,
        "timestamp": datetime(2024, 1, 5, tzinfo=timezone.utc).isoformat(),
        "payload": {"turnId": str(uuid4())},
    }
    older_event = {
        "topic": "object",
        "roomId": room_id,
        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
        "payload": {"id": str(uuid4())},
    }

    asyncio.run(redis.enqueue_json(WS_EVENT_STREAM, newer_event))
    asyncio.run(redis.enqueue_json(OBJECT_EVENT_STREAM, older_event))

    moderator = AuthenticatedSubject(user_id=uuid4(), role=UserRole.MODERATOR)
    result = asyncio.run(
        get_next_event(redis=redis, limit=2, cursor=None, subject=moderator)
    )
    assert isinstance(result, dict)
    assert "cursor" in result
    events = result["events"]
    assert len(events) == 2
    assert [event["topic"] for event in events] == ["turn", "object"]


def test_get_next_event_accepts_service_key() -> None:
    redis = RedisWrapper()
    room_id = str(uuid4())

    asyncio.run(
        redis.enqueue_json(
            WS_EVENT_STREAM,
            {
                "topic": "turn",
                "roomId": room_id,
                "timestamp": datetime(2024, 1, 2, tzinfo=timezone.utc).isoformat(),
                "payload": {"turnId": str(uuid4())},
            },
        )
    )

    result = asyncio.run(
        get_next_event(
            redis=redis,
            limit=1,
            cursor=None,
            subject=None,
            service_key="dev-gateway-key",
        )
    )

    assert isinstance(result, dict)
    assert result["events"][0]["topic"] == "turn"


def test_get_next_event_requires_credentials() -> None:
    redis = RedisWrapper()

    try:
        asyncio.run(get_next_event(redis=redis, limit=1, cursor=None, subject=None))
    except HTTPException as exc:  # type: ignore[name-defined]
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
    else:  # pragma: no cover - should not reach
        raise AssertionError("expected HTTPException")
