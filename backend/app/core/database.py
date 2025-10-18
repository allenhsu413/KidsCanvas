"""Simplified database layer with optional disk persistence."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Iterable
from uuid import UUID

from ..models import (
    AnchorRing,
    AuditLog,
    BBox,
    CanvasObject,
    ObjectStatus,
    Point,
    Room,
    RoomMember,
    RoomRole,
    Stroke,
    Turn,
    TurnActor,
    TurnStatus,
)
from .config import get_settings


class Database:
    """A lightweight transactional store that mimics PostgreSQL semantics."""

    def __init__(self, *, storage_path: str | Path | None = None) -> None:
        self._rooms: dict[UUID, Room] = {}
        self._strokes: dict[UUID, Stroke] = {}
        self._objects: dict[UUID, CanvasObject] = {}
        self._turns: dict[UUID, Turn] = {}
        self._audit_logs: dict[UUID, AuditLog] = {}
        self._members: dict[tuple[UUID, UUID], RoomMember] = {}
        self._room_member_index: defaultdict[UUID, list[UUID]] = defaultdict(list)
        self._room_turn_index: defaultdict[UUID, list[UUID]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._storage_path = Path(storage_path).expanduser() if storage_path else None
        if self._storage_path:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["DatabaseSession"]:
        async with self._lock:
            session = DatabaseSession(self)
            yield session
            if session.commit():
                self._persist()

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
        self._room_member_index[member.room_id] = list(dict.fromkeys(self._room_member_index[member.room_id]))

    # Persistence helpers -------------------------------------------------

    def _persist(self) -> None:
        if self._storage_path is None:
            return
        payload = {
            "rooms": [self._serialise_room(room) for room in self._rooms.values()],
            "strokes": [self._serialise_stroke(stroke) for stroke in self._strokes.values()],
            "objects": [self._serialise_object(obj) for obj in self._objects.values()],
            "turns": [self._serialise_turn(turn) for turn in self._turns.values()],
            "audit_logs": [self._serialise_audit(log) for log in self._audit_logs.values()],
            "members": [self._serialise_member(member) for member in self._members.values()],
        }
        tmp_path = self._storage_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        tmp_path.replace(self._storage_path)

    def _load_from_disk(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        with self._storage_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        self._rooms = {UUID(item["id"]): self._deserialise_room(item) for item in data.get("rooms", [])}
        self._strokes = {
            UUID(item["id"]): self._deserialise_stroke(item) for item in data.get("strokes", [])
        }
        self._objects = {
            UUID(item["id"]): self._deserialise_object(item) for item in data.get("objects", [])
        }
        self._turns = {UUID(item["id"]): self._deserialise_turn(item) for item in data.get("turns", [])}
        self._audit_logs = {
            UUID(item["id"]): self._deserialise_audit(item) for item in data.get("audit_logs", [])
        }
        self._members = {
            (UUID(item["room_id"]), UUID(item["user_id"])): self._deserialise_member(item)
            for item in data.get("members", [])
        }

        self._room_member_index.clear()
        for member in self._members.values():
            self._room_member_index[member.room_id].append(member.user_id)

        self._room_turn_index.clear()
        for turn in self._turns.values():
            self._room_turn_index[turn.room_id].append(turn.id)

    @staticmethod
    def _serialise_room(room: Room) -> dict[str, object]:
        return {
            "id": str(room.id),
            "name": room.name,
            "turn_seq": room.turn_seq,
            "created_at": room.created_at.isoformat(),
        }

    @staticmethod
    def _deserialise_room(data: dict[str, object]) -> Room:
        return Room(
            id=UUID(str(data["id"])),
            name=str(data["name"]),
            turn_seq=int(data.get("turn_seq", 0)),
            created_at=datetime.fromisoformat(str(data["created_at"])),
        )

    @staticmethod
    def _serialise_point(point: Point) -> dict[str, float]:
        return {"x": point.x, "y": point.y}

    @staticmethod
    def _deserialise_point(data: dict[str, object]) -> Point:
        return Point(float(data["x"]), float(data["y"]))

    @classmethod
    def _serialise_stroke(cls, stroke: Stroke) -> dict[str, object]:
        return {
            "id": str(stroke.id),
            "room_id": str(stroke.room_id),
            "author_id": str(stroke.author_id),
            "color": stroke.color,
            "width": stroke.width,
            "ts": stroke.ts.isoformat(),
            "path": [cls._serialise_point(point) for point in stroke.path],
            "object_id": str(stroke.object_id) if stroke.object_id else None,
        }

    @classmethod
    def _deserialise_stroke(cls, data: dict[str, object]) -> Stroke:
        path = [cls._deserialise_point(point) for point in data.get("path", [])]  # type: ignore[arg-type]
        object_id = data.get("object_id")
        return Stroke(
            id=UUID(str(data["id"])),
            room_id=UUID(str(data["room_id"])),
            author_id=UUID(str(data["author_id"])),
            path=path,
            color=str(data["color"]),
            width=float(data["width"]),
            ts=datetime.fromisoformat(str(data["ts"])),
            object_id=UUID(object_id) if object_id else None,
        )

    @staticmethod
    def _serialise_bbox(bbox: BBox) -> dict[str, float]:
        return bbox.to_dict()

    @staticmethod
    def _deserialise_bbox(data: dict[str, object]) -> BBox:
        return BBox(
            x=float(data["x"]),
            y=float(data["y"]),
            width=float(data["width"]),
            height=float(data["height"]),
        )

    @classmethod
    def _serialise_object(cls, obj: CanvasObject) -> dict[str, object]:
        return {
            "id": str(obj.id),
            "room_id": str(obj.room_id),
            "owner_id": str(obj.owner_id),
            "label": obj.label,
            "status": obj.status.value,
            "bbox": cls._serialise_bbox(obj.bbox),
            "anchor_ring": {
                "inner": cls._serialise_bbox(obj.anchor_ring.inner),
                "outer": cls._serialise_bbox(obj.anchor_ring.outer),
            },
            "created_at": obj.created_at.isoformat(),
        }

    @classmethod
    def _deserialise_object(cls, data: dict[str, object]) -> CanvasObject:
        anchor = data.get("anchor_ring", {})
        inner = cls._deserialise_bbox(anchor.get("inner", {}))  # type: ignore[arg-type]
        outer = cls._deserialise_bbox(anchor.get("outer", {}))  # type: ignore[arg-type]
        return CanvasObject(
            id=UUID(str(data["id"])),
            room_id=UUID(str(data["room_id"])),
            owner_id=UUID(str(data["owner_id"])),
            label=data.get("label") if data.get("label") is not None else None,
            status=ObjectStatus(str(data["status"])),
            bbox=cls._deserialise_bbox(data["bbox"]),  # type: ignore[arg-type]
            anchor_ring=AnchorRing(inner=inner, outer=outer),
            created_at=datetime.fromisoformat(str(data["created_at"])),
        )

    @staticmethod
    def _serialise_turn(turn: Turn) -> dict[str, object]:
        return {
            "id": str(turn.id),
            "room_id": str(turn.room_id),
            "sequence": turn.sequence,
            "status": turn.status.value,
            "current_actor": turn.current_actor.value,
            "source_object_id": str(turn.source_object_id),
            "ai_patch_uri": turn.ai_patch_uri,
            "safety_status": turn.safety_status,
            "created_at": turn.created_at.isoformat(),
            "updated_at": turn.updated_at.isoformat(),
        }

    @staticmethod
    def _deserialise_turn(data: dict[str, object]) -> Turn:
        return Turn(
            id=UUID(str(data["id"])),
            room_id=UUID(str(data["room_id"])),
            sequence=int(data["sequence"]),
            status=TurnStatus(str(data["status"])),
            current_actor=TurnActor(str(data["current_actor"])),
            source_object_id=UUID(str(data["source_object_id"])),
            ai_patch_uri=data.get("ai_patch_uri") if data.get("ai_patch_uri") is not None else None,
            safety_status=data.get("safety_status"),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
        )

    @staticmethod
    def _serialise_audit(log: AuditLog) -> dict[str, object]:
        return {
            "id": str(log.id),
            "room_id": str(log.room_id),
            "event_type": log.event_type,
            "payload": log.payload,
            "user_id": str(log.user_id) if log.user_id else None,
            "turn_id": str(log.turn_id) if log.turn_id else None,
            "ts": log.ts.isoformat(),
        }

    @staticmethod
    def _deserialise_audit(data: dict[str, object]) -> AuditLog:
        turn_id = data.get("turn_id")
        user_id = data.get("user_id")
        return AuditLog(
            id=UUID(str(data["id"])),
            room_id=UUID(str(data["room_id"])),
            event_type=str(data["event_type"]),
            payload=data.get("payload", {}),
            user_id=UUID(user_id) if user_id else None,
            turn_id=UUID(turn_id) if turn_id else None,
            ts=datetime.fromisoformat(str(data["ts"])),
        )

    @staticmethod
    def _serialise_member(member: RoomMember) -> dict[str, object]:
        return {
            "room_id": str(member.room_id),
            "user_id": str(member.user_id),
            "role": member.role.value,
            "joined_at": member.joined_at.isoformat(),
        }

    @staticmethod
    def _deserialise_member(data: dict[str, object]) -> RoomMember:
        return RoomMember(
            room_id=UUID(str(data["room_id"])),
            user_id=UUID(str(data["user_id"])),
            role=RoomRole(str(data["role"])),
            joined_at=datetime.fromisoformat(str(data["joined_at"])),
        )


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

    def commit(self) -> bool:
        changed = any(
            collection
            for collection in (
                self._pending_rooms,
                self._pending_strokes,
                self._pending_members,
                self._pending_objects,
                self._updated_strokes,
                self._pending_turns,
                self._pending_audit_logs,
            )
        )

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
        return changed


_db_instance: Database | None = None


def get_database() -> Database:
    global _db_instance  # noqa: PLW0603
    if _db_instance is None:
        settings = get_settings()
        storage = getattr(settings, "state_file", None) or None
        _db_instance = Database(storage_path=storage)
    return _db_instance


async def get_db_session() -> AsyncIterator[DatabaseSession]:
    db = get_database()
    async with db.transaction() as session:
        yield session
