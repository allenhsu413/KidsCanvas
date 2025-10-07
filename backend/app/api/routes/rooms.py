"""Room and object related API routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ...core.database import DatabaseSession, get_db_session
from ...core.redis import RedisWrapper, get_redis
from ...schemas.objects import ObjectCreatePayload, ObjectCreateResponse
from ...services.objects import create_object

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.post("/{room_id}/objects", status_code=201, response_model=ObjectCreateResponse)
async def commit_object(
    room_id: UUID,
    payload: ObjectCreatePayload,
    session: DatabaseSession = Depends(get_db_session),
    redis: RedisWrapper = Depends(get_redis),
) -> ObjectCreateResponse:
    try:
        canvas_object, turn, room = await create_object(
            session,
            redis,
            room_id=room_id,
            owner_id=payload.owner_id,
            stroke_ids=payload.stroke_ids,
            label=payload.label,
        )
    except HTTPException:
        raise

    return ObjectCreateResponse(
        object=canvas_object,
        turn=turn,
        room={"id": str(room.id), "turn_seq": room.turn_seq},
    )
