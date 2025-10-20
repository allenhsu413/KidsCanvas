"""API endpoints for streaming backend events to the realtime gateway."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status

from ...core.redis import RedisWrapper, get_redis_wrapper
from ...core.security import AuthenticatedSubject, UserRole, require_roles


router = APIRouter(tags=["events"])


@router.get("/internal/events/next", response_model=None)
async def get_next_event(
    cursor: str | None = Query(default=None, description="Replay cursor"),
    limit: int = Query(default=1, ge=1, le=100, description="Number of events to fetch"),
    redis: RedisWrapper = Depends(get_redis_wrapper),
    _: AuthenticatedSubject = Depends(
        require_roles(UserRole.MODERATOR, UserRole.PARENT)
    ),
) -> Response | dict[str, object]:
    """Return realtime events along with a cursor for replay."""

    events = await redis.list_timeline_events(cursor=cursor, limit=limit)
    if not events:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    next_cursor = events[-1]["cursor"]
    return {"cursor": next_cursor, "events": events}
