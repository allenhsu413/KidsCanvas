"""API endpoints for streaming backend events to the realtime gateway."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.params import Header as HeaderParam

from ...core.config import get_settings
from ...core.redis import RedisWrapper, get_redis_wrapper
from ...core.security import (
    AuthenticatedSubject,
    UserRole,
    bearer_scheme,
    decode_token,
)

router = APIRouter(tags=["events"])


async def _optional_subject(
    credentials=Depends(bearer_scheme),  # type: ignore[annotation-unchecked]
) -> AuthenticatedSubject | None:
    """Return an authenticated subject when a bearer token is supplied."""

    if credentials is None:
        return None
    return decode_token(credentials.credentials)


@router.get("/internal/events/next", response_model=None)
async def get_next_event(
    cursor: str | None = Query(default=None, description="Replay cursor"),
    limit: int = Query(
        default=1, ge=1, le=100, description="Number of events to fetch"
    ),
    redis: RedisWrapper = Depends(get_redis_wrapper),
    subject: AuthenticatedSubject | None = Depends(_optional_subject),
    service_key: str | None = Header(default=None, alias="X-Service-Key"),
) -> Response | dict[str, object]:
    """Return realtime events along with a cursor for replay."""

    settings = get_settings()

    authorised = False
    if isinstance(service_key, HeaderParam):
        service_key = service_key.default

    if subject is not None:
        if subject.role not in {UserRole.MODERATOR, UserRole.PARENT}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_role"
            )
        authorised = True

    if service_key is not None:
        if not secrets.compare_digest(service_key, settings.realtime_service_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_service_key"
            )
        authorised = True

    if not authorised:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_credentials"
        )

    events = await redis.list_timeline_events(cursor=cursor, limit=limit)
    if not events:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    next_cursor = events[-1]["cursor"]
    return {"cursor": next_cursor, "events": events}
