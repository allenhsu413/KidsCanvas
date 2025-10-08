from uuid import uuid4

import asyncio
import math
from uuid import uuid4

from ..api.routes.rooms import commit_object
from ..core.database import Database
from ..core.redis import RedisWrapper
from ..models import ObjectStatus, Point, Room, Stroke, TurnActor, TurnStatus
from ..schemas.objects import ObjectCreatePayload


def test_commit_object_creates_turn_and_audit() -> None:
    asyncio.run(_run_commit_object_flow())


async def _run_commit_object_flow() -> None:
    db = Database()
    redis = RedisWrapper()

    room_id = uuid4()
    user_id = uuid4()
    stroke_id = uuid4()

    room = Room(id=room_id, name="Story Room")
    stroke = Stroke(
        id=stroke_id,
        room_id=room_id,
        author_id=user_id,
        path=[Point(10.0, 15.0), Point(30.0, 45.0)],
        color="#000000",
        width=4.0,
    )

    db.insert_room(room)
    db.insert_stroke(stroke)

    payload = ObjectCreatePayload(owner_id=user_id, stroke_ids=[stroke_id], label="castle")

    async with db.transaction() as session:
        response = await commit_object(
            room_id=room_id,
            payload=payload,
            session=session,
            redis=redis,
        )

    obj_payload = response.object
    assert obj_payload.room_id == room_id
    assert obj_payload.owner_id == user_id
    assert obj_payload.status == ObjectStatus.COMMITTED
    assert obj_payload.bbox.model_dump() == {
        "x": 10.0,
        "y": 15.0,
        "width": 20.0,
        "height": 30.0,
    }

    expected_padding = max(20.0, 30.0) * 0.4
    assert math.isclose(
        obj_payload.anchor_ring.outer.width,
        20.0 + expected_padding * 2,
        rel_tol=1e-6,
    )

    turn_payload = response.turn
    assert turn_payload.room_id == room_id
    assert turn_payload.sequence == 1
    assert turn_payload.status == TurnStatus.WAITING_FOR_AI
    assert turn_payload.current_actor == TurnActor.AI

    async with db.transaction() as session:
        stored_object = session.get_object(obj_payload.id)
        assert stored_object.status == ObjectStatus.COMMITTED

        stored_turn = session.get_turn(turn_payload.id)
        assert stored_turn.sequence == 1

        updated_stroke = session.get_stroke(stroke_id)
        assert updated_stroke.object_id == stored_object.id

        updated_room = session.get_room(room_id)
        assert updated_room.turn_seq == 1

        audit_logs = session.list_audit_logs(room_id)
        assert len(audit_logs) == 2
        assert {log.event_type for log in audit_logs} == {"object.committed", "turn.created"}

    queue_items = await redis.list_events("turn:events")
    assert len(queue_items) == 1
    queued_event = queue_items[0]
    assert queued_event["event"] == "turn.waiting_for_ai"
    assert queued_event["room_id"] == str(room_id)
    assert queued_event["object_id"] == str(obj_payload.id)
