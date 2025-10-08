"""Turn management helpers for the in-memory database."""
from __future__ import annotations

from uuid import UUID

from ..core.database import DatabaseSession
from ..core.redis import RedisWrapper
from ..models import Room, Turn, TurnActor, TurnStatus
from .audit import record_audit_event

TURN_QUEUE_KEY = "turn:events"


async def create_turn_for_object(
    session: DatabaseSession,
    redis: RedisWrapper,
    *,
    room: Room,
    object_id: UUID,
    user_id: UUID,
) -> Turn:
    room.turn_seq += 1
    turn = Turn(
        room_id=room.id,
        sequence=room.turn_seq,
        status=TurnStatus.WAITING_FOR_AI,
        current_actor=TurnActor.AI,
        source_object_id=object_id,
    )
    session.save_turn(turn)

    await record_audit_event(
        session,
        room_id=room.id,
        user_id=user_id,
        turn_id=turn.id,
        event_type="turn.created",
        payload={
            "sequence": turn.sequence,
            "status": turn.status,
            "current_actor": turn.current_actor,
            "source_object_id": str(object_id),
        },
    )

    await redis.enqueue_turn_event(
        TURN_QUEUE_KEY,
        {
            "event": "turn.waiting_for_ai",
            "turn_id": str(turn.id),
            "room_id": str(room.id),
            "object_id": str(object_id),
            "sequence": turn.sequence,
        },
    )

    return turn
