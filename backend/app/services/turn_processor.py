"""Asynchronous consumer that processes turn events and triggers the AI agent."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from ..core.database import Database, get_database
from ..core.redis import RedisWrapper
from ..models import CanvasObject, Turn, TurnActor, TurnStatus
from .audit import record_audit_event
from .strokes import WS_EVENT_STREAM
from .turns import TURN_QUEUE_KEY


@dataclass
class TurnEvent:
    turn_id: UUID
    room_id: UUID
    object_id: UUID
    sequence: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TurnEvent":
        return cls(
            turn_id=UUID(payload["turn_id"]),
            room_id=UUID(payload["room_id"]),
            object_id=UUID(payload["object_id"]),
            sequence=int(payload.get("sequence", 0)),
        )


class TurnProcessor:
    """Background worker that consumes turn events and calls the AI agent."""

    def __init__(
        self,
        redis: RedisWrapper,
        *,
        agent_url: str,
        poll_interval: float = 0.5,
        database: Database | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._redis = redis
        self._agent_url = agent_url.rstrip("/")
        self._poll_interval = poll_interval
        self._database = database or get_database()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._client: httpx.AsyncClient | None = client
        self._owns_client = client is None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():  # pragma: no cover - defensive
            return
        self._stop_event.clear()
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._agent_url, timeout=10.0)
            self._owns_client = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
            self._owns_client = False

    async def _run(self) -> None:
        assert self._client is not None  # for type checker
        while not self._stop_event.is_set():
            payload = await self._redis.pop_event(TURN_QUEUE_KEY)
            if not payload:
                await asyncio.sleep(self._poll_interval)
                continue

            try:
                event = TurnEvent.from_payload(payload)
            except Exception as exc:  # pragma: no cover - malformed payload
                print(f"[turn-processor] invalid payload: {payload!r} ({exc})")
                continue

            await self._process_event(event, self._client)

    async def _process_event(self, event: TurnEvent, client: httpx.AsyncClient) -> None:
        object_snapshot, turn_snapshot = await self._load_turn_context(event)
        if turn_snapshot is None or object_snapshot is None:
            return

        request_payload = {
            "roomId": str(event.room_id),
            "objectId": str(event.object_id),
            "anchorRegion": object_snapshot.anchor_ring.to_dict(),
        }

        try:
            response = await client.post("/generate", json=request_payload)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # pragma: no cover - network failure path covered in tests
            await self._mark_turn_blocked(event, reason=str(exc))
            return

        patch = data.get("patch", {})
        cache_dir = data.get("cacheDir")
        await self._mark_turn_completed(event, turn_snapshot, patch, cache_dir)

    async def _load_turn_context(self, event: TurnEvent) -> tuple[CanvasObject | None, Turn | None]:
        database = self._database
        async with database.transaction() as session:
            try:
                turn = session.get_turn(event.turn_id)
            except LookupError:
                return None, None
            if turn.status != TurnStatus.WAITING_FOR_AI:
                return None, None
            try:
                canvas_object = session.get_object(event.object_id)
            except LookupError:
                return None, None
            return canvas_object, turn

    async def _mark_turn_completed(
        self,
        event: TurnEvent,
        turn: Turn,
        patch: dict[str, Any],
        cache_dir: Any,
    ) -> None:
        database = self._database
        async with database.transaction() as session:
            turn = session.get_turn(event.turn_id)
            turn.status = TurnStatus.AI_COMPLETED
            turn.current_actor = TurnActor.PLAYER
            turn.safety_status = "passed"
            turn.updated_at = datetime.now(timezone.utc)
            if isinstance(cache_dir, str):
                turn.ai_patch_uri = cache_dir

            await record_audit_event(
                session,
                room_id=turn.room_id,
                turn_id=turn.id,
                event_type="turn.ai.completed",
                payload={
                    "sequence": turn.sequence,
                    "patch": patch,
                    "cache_dir": cache_dir,
                    "status": turn.status,
                },
            )

        await self._redis.enqueue_json(
            WS_EVENT_STREAM,
            {
                "topic": "turn",
                "roomId": str(event.room_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "turnId": str(event.turn_id),
                    "sequence": event.sequence,
                    "status": TurnStatus.AI_COMPLETED,
                    "safetyStatus": "passed",
                    "patch": patch,
                },
            },
        )

    async def _mark_turn_blocked(self, event: TurnEvent, *, reason: str) -> None:
        database = self._database
        async with database.transaction() as session:
            try:
                turn = session.get_turn(event.turn_id)
            except LookupError:  # pragma: no cover - already deleted
                return
            turn.status = TurnStatus.BLOCKED
            turn.current_actor = TurnActor.AI
            turn.safety_status = "error"
            turn.updated_at = datetime.now(timezone.utc)
            await record_audit_event(
                session,
                room_id=turn.room_id,
                turn_id=turn.id,
                event_type="turn.ai.blocked",
                payload={
                    "sequence": turn.sequence,
                    "reason": reason,
                },
            )

        await self._redis.enqueue_json(
            WS_EVENT_STREAM,
            {
                "topic": "turn",
                "roomId": str(event.room_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "turnId": str(event.turn_id),
                    "sequence": event.sequence,
                    "status": TurnStatus.BLOCKED,
                    "safetyStatus": "error",
                    "reason": reason,
                },
            },
        )


@asynccontextmanager
async def create_turn_processor(redis: RedisWrapper, *, agent_url: str, poll_interval: float = 0.5):
    processor = TurnProcessor(redis, agent_url=agent_url, poll_interval=poll_interval)
    await processor.start()
    try:
        yield processor
    finally:
        await processor.stop()
