"""Room lifecycle helpers for the prototype backend."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from fastapi import HTTPException, status

from ..core.database import DatabaseSession
from ..models import CanvasObject, Room, RoomMember, RoomRole, Stroke, Turn
from .audit import record_audit_event


@dataclass(frozen=True)
class RoomSnapshot:
    room: Room
    member: RoomMember
    members: Sequence[RoomMember]
    strokes: Sequence[Stroke]
    objects: Sequence[CanvasObject]
    turns: Sequence[Turn]


async def create_room(
    session: DatabaseSession,
    *,
    name: str,
    host_id: UUID,
) -> RoomSnapshot:
    room = Room(name=name)
    member = RoomMember(room_id=room.id, user_id=host_id, role=RoomRole.HOST)

    session.save_room(room)
    session.save_room_member(member)

    await record_audit_event(
        session,
        room_id=room.id,
        user_id=host_id,
        event_type="room.created",
        payload={"room_id": str(room.id), "name": room.name},
    )

    members = [member]
    strokes: list[Stroke] = []
    objects: list[CanvasObject] = []
    turns: list[Turn] = []

    return RoomSnapshot(
        room=room,
        member=member,
        members=members,
        strokes=strokes,
        objects=objects,
        turns=turns,
    )


async def join_room(
    session: DatabaseSession,
    *,
    room_id: UUID,
    user_id: UUID,
) -> RoomSnapshot:
    try:
        room = session.get_room(room_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found") from None

    try:
        member = session.get_room_member(room_id, user_id)
        is_new_member = False
    except LookupError:
        member = RoomMember(room_id=room.id, user_id=user_id, role=RoomRole.PARTICIPANT)
        session.save_room_member(member)
        is_new_member = True

    members = session.list_room_members(room.id)
    strokes = session.list_strokes(room.id)
    objects = session.list_objects(room.id)
    turns = session.get_turns_for_room(room.id)

    if is_new_member:
        await record_audit_event(
            session,
            room_id=room.id,
            user_id=user_id,
            event_type="room.joined",
            payload={"room_id": str(room.id), "role": member.role},
        )

    return RoomSnapshot(
        room=room,
        member=member,
        members=members,
        strokes=strokes,
        objects=objects,
        turns=turns,
    )
