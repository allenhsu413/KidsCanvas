"""Room and object related API routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ...core.database import DatabaseSession, get_db_session
from ...core.redis import RedisWrapper, get_redis
from ...schemas.objects import ObjectCreatePayload, ObjectCreateResponse
from ...schemas.rooms import (
    RoomCreatePayload,
    RoomJoinPayload,
    RoomSnapshotResponse,
)
from ...services.objects import create_object
from ...services.rooms import RoomSnapshot, create_room, join_room

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _snapshot_response(snapshot: RoomSnapshot) -> RoomSnapshotResponse:
    return RoomSnapshotResponse(
        room=snapshot.room,
        member=snapshot.member,
        members=list(snapshot.members),
        strokes=list(snapshot.strokes),
        objects=list(snapshot.objects),
        turns=list(snapshot.turns),
    )


@router.post("", status_code=201, response_model=RoomSnapshotResponse)
async def create_room_endpoint(
    payload: RoomCreatePayload,
    session: DatabaseSession = Depends(get_db_session),
) -> RoomSnapshotResponse:
    snapshot = await create_room(session, name=payload.name, host_id=payload.host_id)
    return _snapshot_response(snapshot)


@router.post("/{room_id}/join", response_model=RoomSnapshotResponse)
async def join_room_endpoint(
    room_id: UUID,
    payload: RoomJoinPayload,
    session: DatabaseSession = Depends(get_db_session),
) -> RoomSnapshotResponse:
    snapshot = await join_room(session, room_id=room_id, user_id=payload.user_id)
    return _snapshot_response(snapshot)


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
