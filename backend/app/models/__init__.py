"""Domain models for the KidsCanvas game service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, List, Sequence
from uuid import UUID, uuid4


class ObjectStatus(StrEnum):
    DRAFT = "draft"
    COMMITTED = "committed"


class TurnStatus(StrEnum):
    WAITING_FOR_AI = "waiting_for_ai"
    AI_COMPLETED = "ai_completed"
    BLOCKED = "blocked"


class TurnActor(StrEnum):
    PLAYER = "player"
    AI = "ai"


@dataclass
class Point:
    x: float
    y: float


@dataclass
class BBox:
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class AnchorRing:
    inner: BBox
    outer: BBox

    def to_dict(self) -> dict[str, dict[str, float]]:
        return {"inner": self.inner.to_dict(), "outer": self.outer.to_dict()}


@dataclass
class Room:
    name: str
    id: UUID = field(default_factory=uuid4)
    turn_seq: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Stroke:
    room_id: UUID
    author_id: UUID
    path: List[Point]
    color: str
    width: float
    id: UUID = field(default_factory=uuid4)
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    object_id: UUID | None = None


@dataclass
class CanvasObject:
    room_id: UUID
    owner_id: UUID
    bbox: BBox
    anchor_ring: AnchorRing
    status: ObjectStatus
    label: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Turn:
    room_id: UUID
    sequence: int
    status: TurnStatus
    current_actor: TurnActor
    source_object_id: UUID
    id: UUID = field(default_factory=uuid4)
    ai_patch_uri: str | None = None
    safety_status: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AuditLog:
    room_id: UUID
    event_type: str
    payload: dict[str, Any]
    user_id: UUID | None = None
    turn_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


MODEL_REGISTRY: Sequence[type] = (
    Room,
    Stroke,
    CanvasObject,
    Turn,
    AuditLog,
)
