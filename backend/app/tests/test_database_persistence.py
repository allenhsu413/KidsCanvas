import asyncio
from uuid import uuid4

from ..core.database import Database
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


def test_database_persistence_roundtrip(tmp_path) -> None:
    path = tmp_path / "state.json"
    asyncio.run(_exercise_database(path))


async def _exercise_database(path) -> None:
    db = Database(storage_path=path)
    room_id = uuid4()
    user_id = uuid4()

    room = Room(id=room_id, name="Persistent Room", turn_seq=2)
    member = RoomMember(room_id=room_id, user_id=user_id, role=RoomRole.HOST)

    inner_bbox = BBox(x=0.0, y=0.0, width=10.0, height=6.0)
    outer_bbox = BBox(x=-2.0, y=-2.0, width=14.0, height=10.0)
    anchor = AnchorRing(inner=inner_bbox, outer=outer_bbox)

    canvas_object = CanvasObject(
        room_id=room_id,
        owner_id=user_id,
        bbox=inner_bbox,
        anchor_ring=anchor,
        status=ObjectStatus.COMMITTED,
        label="castle",
    )

    stroke = Stroke(
        room_id=room_id,
        author_id=user_id,
        path=[Point(0.0, 0.0), Point(5.0, 5.0)],
        color="#ffffff",
        width=2.0,
        object_id=canvas_object.id,
    )

    turn = Turn(
        room_id=room_id,
        sequence=1,
        status=TurnStatus.AI_COMPLETED,
        current_actor=TurnActor.PLAYER,
        source_object_id=canvas_object.id,
        ai_patch_uri="/cache/mock.png",
        safety_status="passed",
    )

    audit_log = AuditLog(
        room_id=room_id,
        event_type="test.persisted",
        payload={"ok": True},
        user_id=user_id,
        turn_id=turn.id,
    )

    async with db.transaction() as session:
        session.save_room(room)
        session.save_room_member(member)
        session.save_object(canvas_object)
        session.save_stroke(stroke)
        session.save_turn(turn)
        session.append_audit_log(audit_log)

    assert path.exists()

    db_reloaded = Database(storage_path=path)
    async with db_reloaded.transaction() as session:
        loaded_room = session.get_room(room_id)
        assert loaded_room.name == "Persistent Room"
        strokes = session.list_strokes(room_id)
        assert len(strokes) == 1
        assert strokes[0].object_id == canvas_object.id
        loaded_object = session.get_object(canvas_object.id)
        assert loaded_object.anchor_ring.outer.width == outer_bbox.width
        loaded_turn = session.get_turn(turn.id)
        assert loaded_turn.ai_patch_uri == "/cache/mock.png"
        assert loaded_turn.safety_status == "passed"
        logs = session.list_audit_logs(room_id)
        assert logs and logs[0].payload["ok"] is True
