import asyncio
import asyncio
from uuid import uuid4

from ..api.routes.rooms import create_room_endpoint, join_room_endpoint
from ..core.database import Database
from ..core.security import AuthenticatedSubject, UserRole
from ..schemas.rooms import RoomCreatePayload, RoomJoinPayload


def test_room_create_and_join_snapshot() -> None:
    asyncio.run(_run_room_flow())


async def _run_room_flow() -> None:
    db = Database(database_url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    host_id = uuid4()

    create_payload = RoomCreatePayload(name="Story Time", host_id=host_id)
    async with db.transaction() as session:
        create_response = await create_room_endpoint(
            payload=create_payload,
            session=session,
            subject=AuthenticatedSubject(user_id=host_id, role=UserRole.PLAYER),
        )

    assert create_response.room.name == "Story Time"
    assert create_response.member.user_id == host_id
    assert str(create_response.member.role) == "host"
    assert create_response.members[0].user_id == host_id
    assert create_response.strokes == []

    participant_id = uuid4()
    join_payload = RoomJoinPayload(user_id=participant_id)
    async with db.transaction() as session:
        join_response = await join_room_endpoint(
            room_id=create_response.room.id,
            payload=join_payload,
            session=session,
            subject=AuthenticatedSubject(user_id=participant_id, role=UserRole.PLAYER),
        )

    assert join_response.room.id == create_response.room.id
    assert join_response.member.user_id == participant_id
    assert str(join_response.member.role) == "participant"
    assert {member.user_id for member in join_response.members} == {host_id, participant_id}
