"""API endpoints for streaming backend events to the realtime gateway."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from ...core.redis import RedisWrapper, get_redis_wrapper
from ...services.strokes import OBJECT_EVENT_STREAM, WS_EVENT_STREAM


router = APIRouter(tags=["events"])


async def _select_stream(redis: RedisWrapper) -> dict[str, object] | None:
    """Return the next event across object and general streams."""

    async def _peek(key: str) -> tuple[str, dict[str, object]] | None:
        events = await redis.list_events(key)
        if not events:
            return None
        return key, events[0]

    options: list[tuple[str, dict[str, object]]] = []
    for key in (OBJECT_EVENT_STREAM, WS_EVENT_STREAM):
        peeked = await _peek(key)
        if peeked is not None:
            options.append(peeked)

    if not options:
        return None

    def _sort_key(item: tuple[str, dict[str, object]]) -> tuple[str, str]:
        payload = item[1]
        timestamp = str(payload.get("timestamp", ""))
        return timestamp, item[0]

    selected = min(options, key=_sort_key)
    key = selected[0]
    return await redis.pop_event(key)


@router.get("/internal/events/next", response_model=None)
async def get_next_event(redis: RedisWrapper = Depends(get_redis_wrapper)) -> Response | dict[str, object]:
    """Return the next backend event for realtime delivery."""

    event = await _select_stream(redis)
    if event is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return event
