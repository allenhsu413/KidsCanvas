"""Asynchronous consumer that processes turn events and triggers the AI agent."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

import httpx

try:
    from content_safety.app.policies.moderation import ModerationEngine, SafetyResult
except Exception:  # pragma: no cover - fallback when package unavailable
    from dataclasses import dataclass as _dataclass

    @_dataclass(slots=True)
    class SafetyResult:  # type: ignore[redefinition]
        category: str
        passed: bool
        reasons: list[str]

    class ModerationEngine:  # type: ignore[redefinition]
        def __init__(self) -> None:  # pragma: no cover - minimal fallback
            self._banned = ["violence", "blood", "weapon", "scary", "alcohol"]

        def evaluate_text(self, text: str) -> SafetyResult:
            lowered = text.lower()
            triggers = [kw for kw in self._banned if kw in lowered]
            return SafetyResult(category="text", passed=not triggers, reasons=triggers)

        def evaluate_labels(self, labels: Iterable[str]) -> SafetyResult:
            lowered = [label.lower() for label in labels]
            triggers = [kw for kw in self._banned if kw in lowered]
            return SafetyResult(category="image", passed=not triggers, reasons=triggers)

from ..core.database import Database, get_database
from ..core.redis import RedisWrapper
from ..models import CanvasObject, Turn, TurnActor, TurnStatus
from .audit import record_audit_event
from .strokes import WS_EVENT_STREAM
from .turns import TURN_QUEUE_KEY


@dataclass(slots=True)
class SafetySummary:
    """Aggregate moderation outcomes for a generated patch."""

    results: list[SafetyResult]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_payload(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "results": [
                {
                    "category": result.category,
                    "passed": result.passed,
                    "reasons": result.reasons,
                }
                for result in self.results
            ],
            "reasons": [reason for result in self.results for reason in result.reasons],
        }


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
        moderation_engine: ModerationEngine | None = None,
    ) -> None:
        self._redis = redis
        self._agent_url = agent_url.rstrip("/")
        self._poll_interval = poll_interval
        self._database = database or get_database()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._client: httpx.AsyncClient | None = client
        self._owns_client = client is None
        self._moderation = moderation_engine or ModerationEngine()

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

        safety = self._run_safety_checks(object_snapshot, patch)
        if not safety.passed:
            await self._mark_turn_blocked(
                event,
                reason="policy_violation",
                safety=safety,
            )
            return

        await self._mark_turn_completed(event, turn_snapshot, patch, cache_dir, safety)

    async def _load_turn_context(self, event: TurnEvent) -> tuple[CanvasObject | None, Turn | None]:
        database = self._database
        async with database.transaction() as session:
            try:
                turn = await session.get_turn(event.turn_id)
            except LookupError:
                return None, None
            if turn.status != TurnStatus.WAITING_FOR_AI:
                return None, None
            try:
                canvas_object = await session.get_object(event.object_id)
            except LookupError:
                return None, None
            return canvas_object, turn

    async def _mark_turn_completed(
        self,
        event: TurnEvent,
        turn: Turn,
        patch: dict[str, Any],
        cache_dir: Any,
        safety: "SafetySummary",
    ) -> None:
        database = self._database
        async with database.transaction() as session:
            turn = await session.get_turn(event.turn_id)
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
                    "safety": safety.to_payload(),
                },
            )
            await session.update_turn(turn)

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
                    "safety": safety.to_payload(),
                    "patch": patch,
                },
            },
        )

    async def _mark_turn_blocked(
        self,
        event: TurnEvent,
        *,
        reason: str,
        safety: "SafetySummary" | None = None,
    ) -> None:
        database = self._database
        async with database.transaction() as session:
            try:
                turn = await session.get_turn(event.turn_id)
            except LookupError:  # pragma: no cover - already deleted
                return
            turn.status = TurnStatus.BLOCKED
            if safety is None:
                turn.current_actor = TurnActor.AI
                turn.safety_status = "error"
            else:
                turn.current_actor = TurnActor.PLAYER
                turn.safety_status = "blocked"
            turn.updated_at = datetime.now(timezone.utc)
            await record_audit_event(
                session,
                room_id=turn.room_id,
                turn_id=turn.id,
                event_type="turn.ai.blocked",
                payload={
                    "sequence": turn.sequence,
                    "reason": reason,
                    "safety": safety.to_payload() if safety is not None else None,
                },
            )
            await session.update_turn(turn)

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
                    "safetyStatus": "error" if safety is None else "blocked",
                    "reason": reason,
                    "safety": safety.to_payload() if safety is not None else None,
                },
            },
        )

    def _run_safety_checks(self, canvas_object: CanvasObject, patch: dict[str, Any]) -> "SafetySummary":
        results: list[SafetyResult] = []
        instructions = patch.get("instructions")
        if isinstance(instructions, str) and instructions.strip():
            results.append(self._moderation.evaluate_text(instructions))

        labels: list[str] = []
        patch_labels = patch.get("labels")
        if isinstance(patch_labels, list):
            labels.extend([str(label) for label in patch_labels if isinstance(label, str)])
        if canvas_object.label:
            labels.append(canvas_object.label)
        if labels:
            results.append(self._moderation.evaluate_labels(labels))

        if not results:
            results.append(SafetyResult(category="text", passed=True, reasons=[]))

        return SafetySummary(results)


@asynccontextmanager
async def create_turn_processor(redis: RedisWrapper, *, agent_url: str, poll_interval: float = 0.5):
    processor = TurnProcessor(redis, agent_url=agent_url, poll_interval=poll_interval)
    await processor.start()
    try:
        yield processor
    finally:
        await processor.stop()
