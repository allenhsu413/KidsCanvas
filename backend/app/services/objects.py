"""Business logic for player-created objects using the in-memory database."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence
from uuid import UUID

from fastapi import HTTPException, status

from ..core.database import DatabaseSession
from ..core.redis import RedisWrapper
from ..models import AnchorRing, BBox, CanvasObject, ObjectStatus, Room, Stroke, Turn
from .audit import record_audit_event
from .strokes import broadcast_object_event
from .turns import create_turn_for_object

try:
    from content_safety.app.policies.moderation import ModerationEngine
except Exception:  # pragma: no cover - fallback when safety package unavailable

    class ModerationEngine:  # type: ignore[redefinition]
        def __init__(self) -> None:
            self._banned = ["violence", "blood", "weapon", "scary", "alcohol"]

        def evaluate_text(self, text: str):
            lowered = text.lower()
            triggers = [kw for kw in self._banned if kw in lowered]

            class _Result:  # pragma: no cover - simple container
                def __init__(self, passed: bool, reasons: list[str]) -> None:
                    self.category = "text"
                    self.passed = passed
                    self.reasons = reasons

            return _Result(not triggers, triggers)


@dataclass(frozen=True)
class BBoxResult:
    x: float
    y: float
    width: float
    height: float

    def to_bbox(self) -> BBox:
        return BBox(x=self.x, y=self.y, width=self.width, height=self.height)


def _compute_bbox(strokes: Iterable[Stroke]) -> BBoxResult:
    xs: list[float] = []
    ys: list[float] = []
    for stroke in strokes:
        for point in stroke.path:
            xs.append(point.x)
            ys.append(point.y)
    if not xs or not ys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strokes must contain at least one point",
        )
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(max_x - min_x, 1e-6)
    height = max(max_y - min_y, 1e-6)
    return BBoxResult(x=min_x, y=min_y, width=width, height=height)


def _compute_anchor_ring(bbox: BBoxResult) -> AnchorRing:
    padding = max(bbox.width, bbox.height) * 0.4
    outer = BBox(
        x=bbox.x - padding,
        y=bbox.y - padding,
        width=bbox.width + padding * 2,
        height=bbox.height + padding * 2,
    )
    inner = bbox.to_bbox()
    return AnchorRing(inner=inner, outer=outer)


async def create_object(
    session: DatabaseSession,
    redis: RedisWrapper,
    *,
    room_id: UUID,
    owner_id: UUID,
    stroke_ids: Sequence[UUID],
    label: str | None = None,
) -> tuple[CanvasObject, Turn, Room]:
    moderation_engine = ModerationEngine()
    if not stroke_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one stroke must be provided",
        )

    try:
        room = await session.get_room(room_id)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        ) from None

    try:
        strokes = await session.get_strokes(room_id, stroke_ids)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more strokes do not belong to the room",
        ) from None

    assigned = [stroke.id for stroke in strokes if stroke.object_id is not None]
    if assigned:
        assigned_list = ", ".join(str(sid) for sid in assigned)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Strokes already assigned: {assigned_list}",
        )

    bbox = _compute_bbox(strokes)
    anchor_ring = _compute_anchor_ring(bbox)

    if label:
        safety = moderation_engine.evaluate_text(label)
        if not safety.passed:
            await record_audit_event(
                session,
                room_id=room.id,
                user_id=owner_id,
                event_type="object.blocked",
                payload={
                    "label": label,
                    "reasons": list(safety.reasons),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error": "label_blocked", "reasons": list(safety.reasons)},
            )

    canvas_object = CanvasObject(
        room_id=room.id,
        owner_id=owner_id,
        label=label,
        status=ObjectStatus.COMMITTED,
        bbox=bbox.to_bbox(),
        anchor_ring=anchor_ring,
    )
    await session.save_object(canvas_object)

    for stroke in strokes:
        await session.update_stroke(stroke, object_id=canvas_object.id)

    await record_audit_event(
        session,
        room_id=room.id,
        user_id=owner_id,
        event_type="object.committed",
        payload={
            "object_id": str(canvas_object.id),
            "stroke_ids": [str(sid) for sid in stroke_ids],
            "bbox": canvas_object.bbox.to_dict(),
            "anchor_ring": canvas_object.anchor_ring.to_dict(),
        },
    )

    turn = await create_turn_for_object(
        session,
        redis,
        room=room,
        object_id=canvas_object.id,
        user_id=owner_id,
    )

    await broadcast_object_event(
        redis,
        room_id=room.id,
        payload={
            "id": str(canvas_object.id),
            "roomId": str(room.id),
            "ownerId": str(owner_id),
            "label": canvas_object.label,
            "status": canvas_object.status,
            "bbox": canvas_object.bbox.to_dict(),
            "anchorRing": canvas_object.anchor_ring.to_dict(),
            "createdAt": canvas_object.created_at.isoformat(),
            "turnId": str(turn.id),
        },
    )

    return canvas_object, turn, room
