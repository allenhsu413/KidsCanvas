import asyncio
import asyncio
from uuid import uuid4

from ..api.routes.rooms import create_room_endpoint
from ..api.routes.strokes import create_stroke_endpoint, list_strokes
from ..core.database import Database
from ..core.redis import RedisWrapper
from ..core.security import AuthenticatedSubject, UserRole
from ..schemas.rooms import RoomCreatePayload
from ..schemas.strokes import PointSchema, StrokeCreatePayload


def test_create_and_list_strokes() -> None:
    asyncio.run(_run_stroke_flow())


async def _run_stroke_flow() -> None:
    db = Database(database_url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    redis = RedisWrapper()

    host_id = uuid4()
    create_payload = RoomCreatePayload(name="Sketch Room", host_id=host_id)
    async with db.transaction() as session:
        room_response = await create_room_endpoint(
            payload=create_payload,
            session=session,
            subject=AuthenticatedSubject(user_id=host_id, role=UserRole.PLAYER),
        )

    room_id = room_response.room.id
    author_id = uuid4()

    stroke_payload = StrokeCreatePayload(
        author_id=author_id,
        color="#ff00ff",
        width=6.0,
        path=[PointSchema(x=0.0, y=0.0), PointSchema(x=10.0, y=5.0)],
    )

    async with db.transaction() as session:
        stroke_response = await create_stroke_endpoint(
            room_id=room_id,
            payload=stroke_payload,
            session=session,
            redis=redis,
            subject=AuthenticatedSubject(user_id=author_id, role=UserRole.PLAYER),
        )

    assert stroke_response.stroke.room_id == room_id
    assert stroke_response.stroke.author_id == author_id
    assert len(stroke_response.stroke.path) == 2

    events = await redis.list_events("ws:events")
    assert len(events) == 1
    assert events[0]["topic"] == "stroke"
    assert events[0]["payload"]["roomId"] == str(room_id)

    async with db.transaction() as session:
        list_response = await list_strokes(
            room_id=room_id,
            session=session,
            subject=AuthenticatedSubject(user_id=author_id, role=UserRole.PLAYER),
        )

    assert len(list_response.strokes) == 1
    assert list_response.strokes[0].color == "#ff00ff"
