from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator

from ...models import (
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


class GUID(TypeDecorator):
    """Platform-independent GUID type."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: UUID | None, dialect):  # type: ignore[override]
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return value
        if isinstance(value, UUID):
            return value
        return UUID(str(value))


class Base(DeclarativeBase):
    pass


class RoomORM(Base):
    __tablename__ = "rooms"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    turn_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_domain(self) -> Room:
        return Room(id=self.id, name=self.name, turn_seq=self.turn_seq, created_at=self.created_at)

    @classmethod
    def from_domain(cls, room: Room) -> "RoomORM":
        return cls(id=room.id, name=room.name, turn_seq=room.turn_seq, created_at=room.created_at)


class RoomMemberORM(Base):
    __tablename__ = "room_members"

    room_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(GUID(), primary_key=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_domain(self) -> RoomMember:
        return RoomMember(
            room_id=self.room_id,
            user_id=self.user_id,
            role=RoomRole(self.role),
            joined_at=self.joined_at,
        )

    @classmethod
    def from_domain(cls, member: RoomMember) -> "RoomMemberORM":
        return cls(
            room_id=member.room_id,
            user_id=member.user_id,
            role=str(member.role),
            joined_at=member.joined_at,
        )


class StrokeORM(Base):
    __tablename__ = "strokes"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    room_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[UUID] = mapped_column(GUID(), nullable=False)
    color: Mapped[str] = mapped_column(String(50), nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    path: Mapped[list[dict[str, float]]] = mapped_column(JSON, nullable=False)
    object_id: Mapped[UUID | None] = mapped_column(GUID(), ForeignKey("objects.id", ondelete="SET NULL"))

    def to_domain(self) -> Stroke:
        points = [Point(float(item["x"]), float(item["y"])) for item in self.path]
        return Stroke(
            id=self.id,
            room_id=self.room_id,
            author_id=self.author_id,
            path=points,
            color=self.color,
            width=self.width,
            ts=self.ts,
            object_id=self.object_id,
        )

    @classmethod
    def from_domain(cls, stroke: Stroke) -> "StrokeORM":
        return cls(
            id=stroke.id,
            room_id=stroke.room_id,
            author_id=stroke.author_id,
            color=stroke.color,
            width=stroke.width,
            ts=stroke.ts,
            path=[{"x": point.x, "y": point.y} for point in stroke.path],
            object_id=stroke.object_id,
        )


class ObjectORM(Base):
    __tablename__ = "objects"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    room_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(GUID(), nullable=False)
    bbox: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    anchor_ring: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_domain(self) -> CanvasObject:
        return CanvasObject(
            id=self.id,
            room_id=self.room_id,
            owner_id=self.owner_id,
            bbox=_bbox_from_json(self.bbox),
            anchor_ring=_anchor_from_json(self.anchor_ring),
            status=ObjectStatus(self.status),
            label=self.label,
            created_at=self.created_at,
        )

    @classmethod
    def from_domain(cls, obj: CanvasObject) -> "ObjectORM":
        return cls(
            id=obj.id,
            room_id=obj.room_id,
            owner_id=obj.owner_id,
            bbox=obj.bbox.to_dict(),
            anchor_ring=obj.anchor_ring.to_dict(),
            status=str(obj.status),
            label=obj.label,
            created_at=obj.created_at,
        )


class TurnORM(Base):
    __tablename__ = "turns"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    room_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    current_actor: Mapped[str] = mapped_column(String(30), nullable=False)
    source_object_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("objects.id", ondelete="CASCADE"), nullable=False)
    ai_patch_uri: Mapped[str | None] = mapped_column(String(500))
    safety_status: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_domain(self) -> Turn:
        return Turn(
            id=self.id,
            room_id=self.room_id,
            sequence=self.sequence,
            status=TurnStatus(self.status),
            current_actor=TurnActor(self.current_actor),
            source_object_id=self.source_object_id,
            ai_patch_uri=self.ai_patch_uri,
            safety_status=self.safety_status,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_domain(cls, turn: Turn) -> "TurnORM":
        return cls(
            id=turn.id,
            room_id=turn.room_id,
            sequence=turn.sequence,
            status=str(turn.status),
            current_actor=str(turn.current_actor),
            source_object_id=turn.source_object_id,
            ai_patch_uri=turn.ai_patch_uri,
            safety_status=turn.safety_status,
            created_at=turn.created_at,
            updated_at=turn.updated_at,
        )


class AuditLogORM(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    room_id: Mapped[UUID] = mapped_column(GUID(), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(GUID())
    turn_id: Mapped[UUID | None] = mapped_column(GUID(), ForeignKey("turns.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def to_domain(self) -> AuditLog:
        return AuditLog(
            id=self.id,
            room_id=self.room_id,
            user_id=self.user_id,
            turn_id=self.turn_id,
            event_type=self.event_type,
            payload=self.payload,
            ts=self.ts,
        )

    @classmethod
    def from_domain(cls, log: AuditLog) -> "AuditLogORM":
        return cls(
            id=log.id,
            room_id=log.room_id,
            user_id=log.user_id,
            turn_id=log.turn_id,
            event_type=log.event_type,
            payload=log.payload,
            ts=log.ts,
        )


def _bbox_from_json(data: dict[str, Any]) -> BBox:
    return BBox(
        x=float(data["x"]),
        y=float(data["y"]),
        width=float(data["width"]),
        height=float(data["height"]),
    )


def _anchor_from_json(data: dict[str, Any]) -> AnchorRing:
    inner = _bbox_from_json(data["inner"])
    outer = _bbox_from_json(data["outer"])
    return AnchorRing(inner=inner, outer=outer)
