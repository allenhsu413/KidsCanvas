"""Replay endpoints for timeline events."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from ...core.redis import RedisWrapper, get_redis_wrapper
from ...core.security import AuthenticatedSubject, UserRole, require_roles
from ...schemas.replay import ReplayResponse

router = APIRouter(prefix="/rooms", tags=["replay"])


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@router.get("/{room_id}/replay", response_model=None)
async def replay_events(
    room_id: UUID,
    cursor: str | None = Query(default=None, description="Replay cursor"),
    limit: int = Query(default=100, ge=1, le=500),
    since: str | None = Query(default=None, description="Filter from timestamp"),
    redis: RedisWrapper = Depends(get_redis_wrapper),
    subject: AuthenticatedSubject = Depends(
        require_roles(UserRole.PLAYER, UserRole.MODERATOR, UserRole.PARENT)
    ),
) -> Response | ReplayResponse:
    """Return timeline events for replay or scrubber usage."""

    _ = subject
    events = await redis.list_timeline_events(cursor=cursor, limit=limit)
    if not events:
        return Response(status_code=204)

    next_cursor = events[-1]["cursor"]
    since_dt = _parse_timestamp(since)
    filtered: list[dict[str, object]] = []
    for event in events:
        if event.get("roomId") != str(room_id):
            continue
        if since_dt is not None:
            event_ts = _parse_timestamp(event.get("timestamp"))
            if event_ts is None or event_ts < since_dt:
                continue
        filtered.append(event)

    return ReplayResponse(cursor=next_cursor, events=filtered)
