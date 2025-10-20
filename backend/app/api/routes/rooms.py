"""Room and object related API routes."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.database import DatabaseSession, get_db_session
from ...core.redis import RedisWrapper, get_redis
from ...core.security import AuthenticatedSubject, UserRole, require_roles
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
    subject: AuthenticatedSubject = Depends(
        require_roles(UserRole.PLAYER, UserRole.MODERATOR, UserRole.PARENT)
    ),
) -> RoomSnapshotResponse:
    if subject.role == UserRole.PLAYER and payload.host_id != subject.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cannot_create_for_other_user"
        )
    snapshot = await create_room(session, name=payload.name, host_id=payload.host_id)
    return _snapshot_response(snapshot)


@router.post("/{room_id}/join", response_model=RoomSnapshotResponse)
async def join_room_endpoint(
    room_id: UUID,
    payload: RoomJoinPayload,
    session: DatabaseSession = Depends(get_db_session),
    subject: AuthenticatedSubject = Depends(
        require_roles(UserRole.PLAYER, UserRole.MODERATOR, UserRole.PARENT)
    ),
) -> RoomSnapshotResponse:
    if subject.role == UserRole.PLAYER and payload.user_id != subject.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cannot_join_for_other_user"
        )
    snapshot = await join_room(session, room_id=room_id, user_id=payload.user_id)
    return _snapshot_response(snapshot)


@router.post("/{room_id}/objects", status_code=201, response_model=ObjectCreateResponse)
async def commit_object(
    room_id: UUID,
    payload: ObjectCreatePayload,
    session: DatabaseSession = Depends(get_db_session),
    redis: RedisWrapper = Depends(get_redis),
    subject: AuthenticatedSubject = Depends(
        require_roles(UserRole.PLAYER, UserRole.MODERATOR, UserRole.PARENT)
    ),
) -> ObjectCreateResponse:
    if subject.role == UserRole.PLAYER and payload.owner_id != subject.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cannot_commit_for_other_user"
        )
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
