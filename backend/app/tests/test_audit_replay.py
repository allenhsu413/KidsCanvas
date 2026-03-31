import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..api.routes.audit import list_audit_logs
from ..api.routes.replay import replay_events
from ..core.database import Database
from ..core.redis import RedisWrapper
from ..core.security import AuthenticatedSubject, UserRole
from ..services.audit import record_audit_event
from ..services.strokes import WS_EVENT_STREAM


def test_audit_endpoint_filters_by_time() -> None:
    asyncio.run(_run_audit_flow())


async def _run_audit_flow() -> None:
    db = Database(database_url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    room_id = uuid4()
    user_id = uuid4()

    async with db.transaction() as session:
        await record_audit_event(
            session,
            room_id=room_id,
            user_id=user_id,
            event_type="object.committed",
            payload={"label": "sun"},
        )

    async with db.transaction() as session:
        response = await list_audit_logs(
            room_id=room_id,
            since=datetime.now(timezone.utc) - timedelta(minutes=5),
            limit=10,
            session=session,
            subject=AuthenticatedSubject(user_id=user_id, role=UserRole.PLAYER),
        )

    assert response.room_id == room_id
    assert len(response.logs) == 1
    assert response.logs[0].event_type == "object.committed"


def test_replay_endpoint_filters_room() -> None:
    asyncio.run(_run_replay_flow())


async def _run_replay_flow() -> None:
    redis = RedisWrapper()
    room_id = uuid4()
    other_room_id = uuid4()

    await redis.enqueue_json(
        WS_EVENT_STREAM,
        {
            "topic": "stroke",
            "roomId": str(room_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"id": "stroke-1"},
        },
    )
    await redis.enqueue_json(
        WS_EVENT_STREAM,
        {
            "topic": "stroke",
            "roomId": str(other_room_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"id": "stroke-2"},
        },
    )

    response = await replay_events(
        room_id=room_id,
        cursor=None,
        limit=10,
        since=None,
        redis=redis,
        subject=AuthenticatedSubject(user_id=uuid4(), role=UserRole.PLAYER),
    )

    assert response.events
    assert response.events[0]["roomId"] == str(room_id)
