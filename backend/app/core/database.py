"""Simplified in-memory database layer with an async-friendly API."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Iterable
from uuid import UUID

from ..models import AuditLog, CanvasObject, Room, RoomMember, Stroke, Turn


class Database:
    """A lightweight transactional store that mimics PostgreSQL semantics."""

    def __init__(self) -> None:
        self._rooms: dict[UUID, Room] = {}
        self._strokes: dict[UUID, Stroke] = {}
        self._objects: dict[UUID, CanvasObject] = {}
        self._turns: dict[UUID, Turn] = {}
        self._audit_logs: dict[UUID, AuditLog] = {}
        self._members: dict[tuple[UUID, UUID], RoomMember] = {}
        self._room_member_index: defaultdict[UUID, list[UUID]] = defaultdict(list)
        self._room_turn_index: defaultdict[UUID, list[UUID]] = defaultdict(list)
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["DatabaseSession"]:
        async with self._lock:
            session = DatabaseSession(self)
            yield session
            session.commit()

    # Convenience helpers used by tests to bootstrap data -----------------

    def insert_room(self, room: Room) -> None:
        self._rooms[room.id] = room

    def insert_stroke(self, stroke: Stroke) -> None:
        self._strokes[stroke.id] = stroke

    # Internal helpers -----------------------------------------------------

    def _save_object(self, obj: CanvasObject) -> None:
        self._objects[obj.id] = obj

    def _save_turn(self, turn: Turn) -> None:
        self._turns[turn.id] = turn
        self._room_turn_index[turn.room_id].append(turn.id)

    def _save_audit_log(self, log: AuditLog) -> None:
        self._audit_logs[log.id] = log

    def _save_room(self, room: Room) -> None:
        self._rooms[room.id] = room

    def _save_stroke(self, stroke: Stroke) -> None:
        self._strokes[stroke.id] = stroke

    def _save_member(self, member: RoomMember) -> None:
        key = (member.room_id, member.user_id)
        if key not in self._members:
            self._room_member_index[member.room_id].append(member.user_id)
        self._members[key] = member


class DatabaseSession:
    """Single transaction facade used by services."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._pending_audit_logs: list[AuditLog] = []
        self._pending_turns: list[Turn] = []
        self._pending_objects: list[CanvasObject] = []
        self._pending_rooms: list[Room] = []
        self._pending_strokes: list[Stroke] = []
        self._pending_members: list[RoomMember] = []
        self._updated_strokes: list[Stroke] = []

    # Lookup helpers -------------------------------------------------------

    def get_room(self, room_id: UUID) -> Room:
        room = self._db._rooms.get(room_id)
        if room is None:
            raise LookupError("room_not_found")
        return room

    def get_strokes(self, room_id: UUID, stroke_ids: Iterable[UUID]) -> list[Stroke]:
        found: list[Stroke] = []
        for stroke_id in stroke_ids:
            stroke = self._db._strokes.get(stroke_id)
            if stroke is None or stroke.room_id != room_id:
                raise LookupError("stroke_not_found")
            found.append(stroke)
        return found

    def get_turns_for_room(self, room_id: UUID) -> list[Turn]:
        return [self._db._turns[turn_id] for turn_id in self._db._room_turn_index.get(room_id, [])]

    def get_object(self, object_id: UUID) -> CanvasObject:
        obj = self._db._objects.get(object_id)
        if obj is None:
            raise LookupError("object_not_found")
        return obj

    def list_objects(self, room_id: UUID) -> list[CanvasObject]:
        return [obj for obj in self._db._objects.values() if obj.room_id == room_id]

    def get_turn(self, turn_id: UUID) -> Turn:
        turn = self._db._turns.get(turn_id)
        if turn is None:
            raise LookupError("turn_not_found")
        return turn

    def get_stroke(self, stroke_id: UUID) -> Stroke:
        stroke = self._db._strokes.get(stroke_id)
        if stroke is None:
            raise LookupError("stroke_not_found")
        return stroke

    def list_strokes(self, room_id: UUID) -> list[Stroke]:
        strokes = [stroke for stroke in self._db._strokes.values() if stroke.room_id == room_id]
        return sorted(strokes, key=lambda stroke: stroke.ts)

    def get_room_member(self, room_id: UUID, user_id: UUID) -> RoomMember:
        member = self._db._members.get((room_id, user_id))
        if member is None:
            raise LookupError("member_not_found")
        return member

    def list_room_members(self, room_id: UUID) -> list[RoomMember]:
        members = [self._db._members[(room_id, user_id)] for user_id in self._db._room_member_index.get(room_id, [])]
        for member in self._pending_members:
            if member.room_id == room_id and member not in members:
                members.append(member)
        return members

    def list_audit_logs(self, room_id: UUID | None = None) -> list[AuditLog]:
        logs = list(self._db._audit_logs.values())
        if room_id is not None:
            logs = [log for log in logs if log.room_id == room_id]
        return logs

    # Mutation helpers -----------------------------------------------------

    def save_object(self, obj: CanvasObject) -> None:
        self._pending_objects.append(obj)

    def save_room(self, room: Room) -> None:
        self._pending_rooms.append(room)

    def save_stroke(self, stroke: Stroke) -> None:
        self._pending_strokes.append(stroke)

    def save_room_member(self, member: RoomMember) -> None:
        self._pending_members.append(member)

    def update_stroke(self, stroke: Stroke, *, object_id: UUID) -> None:
        updated = replace(stroke, object_id=object_id)
        self._updated_strokes.append(updated)

    def save_turn(self, turn: Turn) -> None:
        self._pending_turns.append(turn)

    def append_audit_log(self, log: AuditLog) -> None:
        self._pending_audit_logs.append(log)

    def commit(self) -> None:
        for room in self._pending_rooms:
            self._db._save_room(room)
        for stroke in self._pending_strokes:
            self._db._save_stroke(stroke)
        for member in self._pending_members:
            self._db._save_member(member)
        for obj in self._pending_objects:
            self._db._save_object(obj)
        for stroke in self._updated_strokes:
            self._db._strokes[stroke.id] = stroke
        for turn in self._pending_turns:
            self._db._save_turn(turn)
        for log in self._pending_audit_logs:
            self._db._save_audit_log(log)
        self._pending_rooms.clear()
        self._pending_strokes.clear()
        self._pending_members.clear()
        self._pending_objects.clear()
        self._updated_strokes.clear()
        self._pending_turns.clear()
        self._pending_audit_logs.clear()


_db_instance: Database | None = None


def get_database() -> Database:
    global _db_instance  # noqa: PLW0603
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


async def get_db_session() -> AsyncIterator[DatabaseSession]:
    db = get_database()
    async with db.transaction() as session:
        yield session
