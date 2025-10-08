"""Stroke endpoints for the drawing canvas."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ...core.database import DatabaseSession, get_db_session
from ...core.redis import RedisWrapper, get_redis
from ...schemas.strokes import StrokeBatchResponse, StrokeCreatePayload, StrokeCreateResponse
from ...services.strokes import create_stroke, list_strokes as list_strokes_service

router = APIRouter(prefix="/rooms/{room_id}/strokes", tags=["strokes"])


@router.post("", status_code=201, response_model=StrokeCreateResponse)
async def create_stroke_endpoint(
    room_id: UUID,
    payload: StrokeCreatePayload,
    session: DatabaseSession = Depends(get_db_session),
    redis: RedisWrapper = Depends(get_redis),
) -> StrokeCreateResponse:
    stroke = await create_stroke(
        session,
        redis,
        room_id=room_id,
        author_id=payload.author_id,
        path=[point.model_dump() for point in payload.path],
        color=payload.color,
        width=payload.width,
    )
    return StrokeCreateResponse(stroke=stroke)


@router.get("", response_model=StrokeBatchResponse)
async def list_strokes(
    room_id: UUID,
    session: DatabaseSession = Depends(get_db_session),
) -> StrokeBatchResponse:
    strokes = list_strokes_service(session, room_id=room_id)
    return StrokeBatchResponse(strokes=list(strokes))
