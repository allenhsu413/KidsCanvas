import asyncio
from uuid import uuid4

import httpx

from ..api.routes.rooms import commit_object
from ..core.database import Database
from ..core.redis import RedisWrapper
from ..core.security import AuthenticatedSubject, UserRole
from ..models import Point, Room, Stroke, TurnActor, TurnStatus
from ..schemas.objects import ObjectCreatePayload
from ..services.turn_processor import TurnEvent, TurnProcessor


def test_turn_processor_completes_turn() -> None:
    asyncio.run(_run_turn_processor())


async def _run_turn_processor() -> None:
    db = Database(database_url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    redis = RedisWrapper()

    room_id = uuid4()
    user_id = uuid4()
    stroke_id = uuid4()

    room = Room(id=room_id, name="Adventure Room")
    stroke = Stroke(
        id=stroke_id,
        room_id=room_id,
        author_id=user_id,
        path=[Point(0.0, 0.0), Point(5.0, 5.0)],
        color="#000000",
        width=3.0,
    )
    async with db.transaction() as session:
        await session.save_room(room)
        await session.save_stroke(stroke)

    payload = ObjectCreatePayload(owner_id=user_id, stroke_ids=[stroke_id])
    async with db.transaction() as session:
        response = await commit_object(
            room_id=room_id,
            payload=payload,
            session=session,
            redis=redis,
            subject=AuthenticatedSubject(user_id=user_id, role=UserRole.PLAYER),
        )

    object_events = await redis.list_events("ws:object-events")
    assert len(object_events) == 1
    assert object_events[0]["topic"] == "object"
    assert object_events[0]["payload"]["roomId"] == str(room_id)

    queued_payload = await redis.pop_event("turn:events")
    assert queued_payload is not None

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/generate"
        return httpx.Response(
            200, json={"patch": {"mock": True}, "cacheDir": "/tmp/ai"}
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://agent")

    processor = TurnProcessor(
        redis,
        agent_url="http://agent",
        poll_interval=0.01,
        database=db,
        client=client,
    )

    event = TurnEvent.from_payload(queued_payload)
    await processor._process_event(event, client)

    async with db.transaction() as session:
        turn = await session.get_turn(response.turn.id)
        assert turn.status == TurnStatus.AI_COMPLETED
        assert turn.current_actor == TurnActor.PLAYER
        assert turn.safety_status == "passed"

    ws_events = await redis.list_events("ws:events")
    assert len(ws_events) == 1
    assert ws_events[0]["topic"] == "turn"
    payload = ws_events[0]["payload"]
    assert payload["turnId"] == str(response.turn.id)
    assert payload["safetyStatus"] == "passed"
    assert payload["safety"]["passed"] is True

    await client.aclose()


def test_turn_processor_blocks_on_safety() -> None:
    asyncio.run(_run_turn_processor_blocked())


async def _run_turn_processor_blocked() -> None:
    db = Database(database_url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    redis = RedisWrapper()

    room_id = uuid4()
    user_id = uuid4()
    stroke_id = uuid4()

    room = Room(id=room_id, name="Adventure Room")
    stroke = Stroke(
        id=stroke_id,
        room_id=room_id,
        author_id=user_id,
        path=[Point(0.0, 0.0), Point(5.0, 5.0)],
        color="#000000",
        width=3.0,
    )
    async with db.transaction() as session:
        await session.save_room(room)
        await session.save_stroke(stroke)

    payload = ObjectCreatePayload(owner_id=user_id, stroke_ids=[stroke_id])
    async with db.transaction() as session:
        response = await commit_object(
            room_id=room_id,
            payload=payload,
            session=session,
            redis=redis,
            subject=AuthenticatedSubject(user_id=user_id, role=UserRole.PLAYER),
        )

    object_events = await redis.list_events("ws:object-events")
    assert len(object_events) == 1
    assert object_events[0]["topic"] == "object"
    assert object_events[0]["payload"]["roomId"] == str(room_id)

    queued_payload = await redis.pop_event("turn:events")
    assert queued_payload is not None

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/generate"
        return httpx.Response(
            200,
            json={"patch": {"instructions": "add spooky blood everywhere"}},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://agent")

    processor = TurnProcessor(
        redis,
        agent_url="http://agent",
        poll_interval=0.01,
        database=db,
        client=client,
    )

    event = TurnEvent.from_payload(queued_payload)
    await processor._process_event(event, client)

    async with db.transaction() as session:
        turn = await session.get_turn(response.turn.id)
        assert turn.status == TurnStatus.BLOCKED
        assert turn.safety_status == "blocked"

    ws_events = await redis.list_events("ws:events")
    assert len(ws_events) == 1
    payload_event = ws_events[0]["payload"]
    assert payload_event["safetyStatus"] == "blocked"
    assert payload_event["safety"]["passed"] is False
    assert "blood" in payload_event["safety"]["reasons"]

    await client.aclose()
