"""Stroke management helpers for drawing synchronisation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence
from uuid import UUID

from fastapi import HTTPException, status

from ..core.database import DatabaseSession
from ..core.redis import RedisWrapper
from ..models import Point, Room, Stroke
from .audit import record_audit_event

WS_EVENT_STREAM = "ws:events"


def _ensure_room(session: DatabaseSession, room_id: UUID) -> Room:
    try:
        return session.get_room(room_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found") from None


def _serialise_stroke(stroke: Stroke) -> dict[str, object]:
    return {
        "id": str(stroke.id),
        "roomId": str(stroke.room_id),
        "authorId": str(stroke.author_id),
        "color": stroke.color,
        "width": stroke.width,
        "ts": stroke.ts.isoformat(),
        "path": [{"x": point.x, "y": point.y} for point in stroke.path],
        "objectId": str(stroke.object_id) if stroke.object_id else None,
    }


async def create_stroke(
    session: DatabaseSession,
    redis: RedisWrapper,
    *,
    room_id: UUID,
    author_id: UUID,
    path: Sequence[dict[str, float]],
    color: str,
    width: float,
) -> Stroke:
    if not path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path must contain at least one point")

    room = _ensure_room(session, room_id)

    points = [Point(float(point["x"]), float(point["y"])) for point in path]

    stroke = Stroke(
        room_id=room.id,
        author_id=author_id,
        path=points,
        color=color,
        width=width,
    )
    session.save_stroke(stroke)

    await record_audit_event(
        session,
        room_id=room.id,
        user_id=author_id,
        event_type="stroke.created",
        payload={
            "stroke_id": str(stroke.id),
            "color": color,
            "width": width,
            "points": len(points),
        },
    )

    await redis.enqueue_json(
        WS_EVENT_STREAM,
        {
            "topic": "stroke",
            "roomId": str(room.id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": _serialise_stroke(stroke),
        },
    )

    return stroke


def list_strokes(session: DatabaseSession, *, room_id: UUID) -> Iterable[Stroke]:
    _ensure_room(session, room_id)
    return session.list_strokes(room_id)


async def broadcast_object_event(
    redis: RedisWrapper,
    *,
    room_id: UUID,
    payload: dict[str, object],
) -> None:
    await redis.enqueue_json(
        WS_EVENT_STREAM,
        {
            "topic": "object",
            "roomId": str(room_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        },
    )
