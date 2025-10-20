"""Database layer supporting both SQLAlchemy and in-memory fallbacks."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
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

try:  # pragma: no cover - optional dependency
    from sqlalchemy import Select, select, update
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from .db.models import AuditLogORM, Base, ObjectORM, RoomMemberORM, RoomORM, StrokeORM, TurnORM

    SQLALCHEMY_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - when dependencies missing
    SQLALCHEMY_AVAILABLE = False


if SQLALCHEMY_AVAILABLE:  # pragma: no cover - exercised via integration tests

    class Database:
        """Async database facade that exposes high-level helpers used by services."""

        def __init__(self, *, database_url: str | None = None, echo: bool = False) -> None:
            settings = get_settings()
            self._database_url = database_url or settings.database_url
            engine_kwargs: dict[str, Any] = {"echo": echo, "future": True}
            if self._database_url.startswith("sqlite+aiosqlite"):
                engine_kwargs["connect_args"] = {"check_same_thread": False}
                engine_kwargs["poolclass"] = StaticPool
            self._engine: AsyncEngine = create_async_engine(self._database_url, **engine_kwargs)
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

        async def create_all(self) -> None:
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        async def dispose(self) -> None:
            await self._engine.dispose()

        @asynccontextmanager
        async def transaction(self) -> AsyncIterator["DatabaseSession"]:
            async with self._session_factory() as session:
                async with session.begin():
                    yield DatabaseSession(session)


    class DatabaseSession:
        """Wrap an AsyncSession with domain-specific helpers."""

        def __init__(self, session: AsyncSession) -> None:
            self._session = session

        async def save_room(self, room: Room) -> None:
            self._session.add(RoomORM.from_domain(room))

        async def update_room(self, room: Room) -> None:
            await self._session.execute(
                update(RoomORM)
                .where(RoomORM.id == room.id)
                .values(name=room.name, turn_seq=room.turn_seq, created_at=room.created_at)
            )

        async def get_room(self, room_id: UUID) -> Room:
            room = await self._session.get(RoomORM, room_id)
            if room is None:
                raise LookupError("room_not_found")
            return room.to_domain()

        async def list_room_members(self, room_id: UUID) -> list[RoomMember]:
            stmt: Select[tuple[RoomMemberORM]] = (
                select(RoomMemberORM).where(RoomMemberORM.room_id == room_id).order_by(RoomMemberORM.joined_at)
            )
            result = await self._session.execute(stmt)
            return [row[0].to_domain() for row in result.all()]

        async def save_room_member(self, member: RoomMember) -> None:
            self._session.add(RoomMemberORM.from_domain(member))

        async def get_room_member(self, room_id: UUID, user_id: UUID) -> RoomMember:
            member = await self._session.get(RoomMemberORM, (room_id, user_id))
            if member is None:
                raise LookupError("member_not_found")
            return member.to_domain()

        async def save_stroke(self, stroke: Stroke) -> None:
            self._session.add(StrokeORM.from_domain(stroke))

        async def list_strokes(self, room_id: UUID) -> list[Stroke]:
            stmt: Select[tuple[StrokeORM]] = (
                select(StrokeORM).where(StrokeORM.room_id == room_id).order_by(StrokeORM.ts)
            )
            result = await self._session.execute(stmt)
            return [row[0].to_domain() for row in result.all()]

        async def get_stroke(self, stroke_id: UUID) -> Stroke:
            stroke = await self._session.get(StrokeORM, stroke_id)
            if stroke is None:
                raise LookupError("stroke_not_found")
            return stroke.to_domain()

        async def get_strokes(self, room_id: UUID, stroke_ids: Iterable[UUID]) -> list[Stroke]:
            ids = list(stroke_ids)
            if not ids:
                return []
            stmt: Select[tuple[StrokeORM]] = select(StrokeORM).where(StrokeORM.id.in_(ids))
            result = await self._session.execute(stmt)
            strokes = {row[0].id: row[0].to_domain() for row in result.all()}
            missing = [stroke_id for stroke_id in ids if stroke_id not in strokes]
            if missing:
                raise LookupError("stroke_not_found")
            ordered: list[Stroke] = []
            for stroke_id in ids:
                stroke = strokes[stroke_id]
                if stroke.room_id != room_id:
                    raise LookupError("stroke_not_found")
                ordered.append(stroke)
            return ordered

        async def update_stroke(self, stroke: Stroke, *, object_id: UUID) -> None:
            await self._session.execute(
                update(StrokeORM).where(StrokeORM.id == stroke.id).values(object_id=object_id)
            )

        async def save_object(self, obj: CanvasObject) -> None:
            self._session.add(ObjectORM.from_domain(obj))

        async def get_object(self, object_id: UUID) -> CanvasObject:
            obj = await self._session.get(ObjectORM, object_id)
            if obj is None:
                raise LookupError("object_not_found")
            return obj.to_domain()

        async def list_objects(self, room_id: UUID) -> list[CanvasObject]:
            stmt: Select[tuple[ObjectORM]] = (
                select(ObjectORM).where(ObjectORM.room_id == room_id).order_by(ObjectORM.created_at)
            )
            result = await self._session.execute(stmt)
            return [row[0].to_domain() for row in result.all()]

        async def save_turn(self, turn: Turn) -> None:
            self._session.add(TurnORM.from_domain(turn))

        async def update_turn(self, turn: Turn) -> None:
            await self._session.execute(
                update(TurnORM)
                .where(TurnORM.id == turn.id)
                .values(
                    status=str(turn.status),
                    current_actor=str(turn.current_actor),
                    ai_patch_uri=turn.ai_patch_uri,
                    safety_status=turn.safety_status,
                    updated_at=turn.updated_at,
                )
            )

        async def get_turn(self, turn_id: UUID) -> Turn:
            turn = await self._session.get(TurnORM, turn_id)
            if turn is None:
                raise LookupError("turn_not_found")
            return turn.to_domain()

        async def get_turns_for_room(self, room_id: UUID) -> list[Turn]:
            stmt: Select[tuple[TurnORM]] = (
                select(TurnORM).where(TurnORM.room_id == room_id).order_by(TurnORM.sequence)
            )
            result = await self._session.execute(stmt)
            return [row[0].to_domain() for row in result.all()]

        async def append_audit_log(self, log: AuditLog) -> None:
            self._session.add(AuditLogORM.from_domain(log))

        async def list_audit_logs(self, room_id: UUID | None = None) -> list[AuditLog]:
            stmt: Select[tuple[AuditLogORM]] = select(AuditLogORM)
            if room_id is not None:
                stmt = stmt.where(AuditLogORM.room_id == room_id)
            stmt = stmt.order_by(AuditLogORM.ts)
            result = await self._session.execute(stmt)
            return [row[0].to_domain() for row in result.all()]


else:  # pragma: no cover - exercised in CI when SQLAlchemy unavailable

    class Database:
        """In-memory database fallback used when SQLAlchemy is unavailable."""

        def __init__(self, *, database_url: str | None = None, storage_path: str | Path | None = None) -> None:
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

        async def create_all(self) -> None:  # pragma: no cover - no-op for fallback
            return None

        async def dispose(self) -> None:  # pragma: no cover - no resources to release
            return None

        @asynccontextmanager
        async def transaction(self) -> AsyncIterator["DatabaseSession"]:
            async with self._lock:
                session = DatabaseSession(self)
                yield session
                if await session.commit():
                    self._persist()

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
        def _serialise_point(point: "Point") -> dict[str, float]:
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
            from ..models import Point

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
        def _serialise_bbox(bbox: "BBox") -> dict[str, float]:
            return bbox.to_dict()

        @staticmethod
        def _deserialise_bbox(data: dict[str, object]) -> "BBox":
            from ..models import BBox

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
                "bbox": cls._serialise_bbox(obj.bbox),
                "anchor_ring": {
                    "inner": cls._serialise_bbox(obj.anchor_ring.inner),
                    "outer": cls._serialise_bbox(obj.anchor_ring.outer),
                },
                "status": str(obj.status),
                "label": obj.label,
                "created_at": obj.created_at.isoformat(),
            }

        @classmethod
        def _deserialise_object(cls, data: dict[str, object]) -> CanvasObject:
            anchor = AnchorRing(
                inner=cls._deserialise_bbox(data["anchor_ring"]["inner"]),  # type: ignore[index]
                outer=cls._deserialise_bbox(data["anchor_ring"]["outer"]),  # type: ignore[index]
            )
            return CanvasObject(
                id=UUID(str(data["id"])),
                room_id=UUID(str(data["room_id"])),
                owner_id=UUID(str(data["owner_id"])),
                bbox=cls._deserialise_bbox(data["bbox"]),
                anchor_ring=anchor,
                status=ObjectStatus(str(data["status"])),
                label=data.get("label"),
                created_at=datetime.fromisoformat(str(data["created_at"])),
            )

        @staticmethod
        def _serialise_turn(turn: Turn) -> dict[str, object]:
            return {
                "id": str(turn.id),
                "room_id": str(turn.room_id),
                "sequence": turn.sequence,
                "status": str(turn.status),
                "current_actor": str(turn.current_actor),
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
                ai_patch_uri=data.get("ai_patch_uri"),
                safety_status=data.get("safety_status"),
                created_at=datetime.fromisoformat(str(data["created_at"])),
                updated_at=datetime.fromisoformat(str(data["updated_at"])),
            )

        @staticmethod
        def _serialise_audit(log: AuditLog) -> dict[str, object]:
            return {
                "id": str(log.id),
                "room_id": str(log.room_id),
                "user_id": str(log.user_id) if log.user_id else None,
                "turn_id": str(log.turn_id) if log.turn_id else None,
                "event_type": log.event_type,
                "payload": log.payload,
                "ts": log.ts.isoformat(),
            }

        @staticmethod
        def _deserialise_audit(data: dict[str, object]) -> AuditLog:
            user_id = data.get("user_id")
            turn_id = data.get("turn_id")
            return AuditLog(
                id=UUID(str(data["id"])),
                room_id=UUID(str(data["room_id"])),
                user_id=UUID(str(user_id)) if user_id else None,
                turn_id=UUID(str(turn_id)) if turn_id else None,
                event_type=str(data["event_type"]),
                payload=data["payload"],  # type: ignore[arg-type]
                ts=datetime.fromisoformat(str(data["ts"])),
            )

        @staticmethod
        def _serialise_member(member: RoomMember) -> dict[str, object]:
            return {
                "room_id": str(member.room_id),
                "user_id": str(member.user_id),
                "role": str(member.role),
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
        def __init__(self, db: Database) -> None:
            self._db = db
            self._pending_audit_logs: list[AuditLog] = []
            self._pending_turns: list[Turn] = []
            self._pending_objects: list[CanvasObject] = []
            self._pending_rooms: list[Room] = []
            self._pending_strokes: list[Stroke] = []
            self._pending_members: list[RoomMember] = []
            self._updated_strokes: list[Stroke] = []

        async def save_room(self, room: Room) -> None:
            self._pending_rooms.append(room)

        async def update_room(self, room: Room) -> None:
            self._pending_rooms.append(room)

        async def get_room(self, room_id: UUID) -> Room:
            room = self._db._rooms.get(room_id)
            if room is None:
                raise LookupError("room_not_found")
            return room

        async def list_room_members(self, room_id: UUID) -> list[RoomMember]:
            members = [self._db._members[(room_id, user_id)] for user_id in self._db._room_member_index.get(room_id, [])]
            for member in self._pending_members:
                if member.room_id == room_id and member not in members:
                    members.append(member)
            return members

        async def save_room_member(self, member: RoomMember) -> None:
            self._pending_members.append(member)

        async def get_room_member(self, room_id: UUID, user_id: UUID) -> RoomMember:
            member = self._db._members.get((room_id, user_id))
            if member is None:
                raise LookupError("member_not_found")
            return member

        async def save_stroke(self, stroke: Stroke) -> None:
            self._pending_strokes.append(stroke)

        async def list_strokes(self, room_id: UUID) -> list[Stroke]:
            strokes = [stroke for stroke in self._db._strokes.values() if stroke.room_id == room_id]
            strokes.extend(stroke for stroke in self._pending_strokes if stroke.room_id == room_id)
            return sorted(strokes, key=lambda stroke: stroke.ts)

        async def get_stroke(self, stroke_id: UUID) -> Stroke:
            stroke = self._db._strokes.get(stroke_id)
            if stroke is None:
                raise LookupError("stroke_not_found")
            return stroke

        async def get_strokes(self, room_id: UUID, stroke_ids: Iterable[UUID]) -> list[Stroke]:
            found: list[Stroke] = []
            for stroke_id in stroke_ids:
                stroke = self._db._strokes.get(stroke_id)
                if stroke is None or stroke.room_id != room_id:
                    raise LookupError("stroke_not_found")
                found.append(stroke)
            return found

        async def update_stroke(self, stroke: Stroke, *, object_id: UUID) -> None:
            updated = replace(stroke, object_id=object_id)
            self._updated_strokes.append(updated)

        async def save_object(self, obj: CanvasObject) -> None:
            self._pending_objects.append(obj)

        async def get_object(self, object_id: UUID) -> CanvasObject:
            obj = self._db._objects.get(object_id)
            if obj is None:
                raise LookupError("object_not_found")
            return obj

        async def list_objects(self, room_id: UUID) -> list[CanvasObject]:
            return [obj for obj in self._db._objects.values() if obj.room_id == room_id]

        async def save_turn(self, turn: Turn) -> None:
            self._pending_turns.append(turn)

        async def update_turn(self, turn: Turn) -> None:
            self._pending_turns.append(turn)

        async def get_turn(self, turn_id: UUID) -> Turn:
            turn = self._db._turns.get(turn_id)
            if turn is None:
                raise LookupError("turn_not_found")
            return turn

        async def get_turns_for_room(self, room_id: UUID) -> list[Turn]:
            return [self._db._turns[turn_id] for turn_id in self._db._room_turn_index.get(room_id, [])]

        async def append_audit_log(self, log: AuditLog) -> None:
            self._pending_audit_logs.append(log)

        async def list_audit_logs(self, room_id: UUID | None = None) -> list[AuditLog]:
            logs = list(self._db._audit_logs.values())
            if room_id is not None:
                logs = [log for log in logs if log.room_id == room_id]
            return logs

        async def commit(self) -> bool:
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
                self._db._rooms[room.id] = room
            for stroke in self._pending_strokes:
                self._db._strokes[stroke.id] = stroke
            for member in self._pending_members:
                key = (member.room_id, member.user_id)
                if key not in self._db._members:
                    self._db._room_member_index[member.room_id].append(member.user_id)
                self._db._members[key] = member
            for obj in self._pending_objects:
                self._db._objects[obj.id] = obj
            for stroke in self._updated_strokes:
                self._db._strokes[stroke.id] = stroke
            for turn in self._pending_turns:
                self._db._turns[turn.id] = turn
                if turn.id not in self._db._room_turn_index[turn.room_id]:
                    self._db._room_turn_index[turn.room_id].append(turn.id)
            for log in self._pending_audit_logs:
                self._db._audit_logs[log.id] = log

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
        if SQLALCHEMY_AVAILABLE:
            _db_instance = Database()
        else:
            _db_instance = Database(storage_path=getattr(settings, "state_file", None) or None)
    return _db_instance


async def get_db_session() -> AsyncIterator[DatabaseSession]:
    db = get_database()
    async with db.transaction() as session:
        yield session
