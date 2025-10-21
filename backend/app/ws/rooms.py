"""WebSocket endpoints for room streaming with authentication."""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ..core.database import get_database
from ..core.redis import get_redis_wrapper
from ..core.security import AuthenticatedSubject, UserRole, decode_token

router = APIRouter()


async def _authenticate(websocket: WebSocket) -> AuthenticatedSubject:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketDisconnect()
    try:
        return decode_token(token)
    except Exception:  # pragma: no cover - validation already covered in security tests
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise WebSocketDisconnect() from None


@router.websocket("/ws/rooms/{room_id}")
async def room_events(websocket: WebSocket, room_id: UUID) -> None:
    subject = await _authenticate(websocket)
    await websocket.accept()

    database = get_database()
    async with database.transaction() as session:
        try:
            await session.get_room(room_id)
        except LookupError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        try:
            await session.get_room_member(room_id, subject.user_id)
        except LookupError:
            if subject.role == UserRole.PLAYER:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

    redis = get_redis_wrapper()
    cursor = websocket.query_params.get("cursor")

    try:
        backlog = await redis.list_timeline_events(cursor=cursor, limit=50)
        for event in backlog:
            if event.get("roomId") != str(room_id):
                continue
            cursor = event["cursor"]
            await websocket.send_json(event)

        while True:
            event = await redis.next_timeline_event(cursor)
            if event is None:
                await asyncio.sleep(0.5)
                continue
            cursor = event["cursor"]
            if event.get("roomId") != str(room_id):
                continue
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
