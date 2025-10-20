from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

try:  # pragma: no cover - optional dependency
    from redis.asyncio import Redis as _RedisClient  # type: ignore
except ImportError:  # pragma: no cover - fallback path
    _RedisClient = None  # type: ignore

TIMELINE_STREAM = "ws:timeline"

from .config import get_settings


class InMemoryEventStore:
    """Event store that mimics the Redis interface for tests."""

    def __init__(self) -> None:
        self._queues: defaultdict[str, list[str]] = defaultdict(list)
        self._streams: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        self._sequences: defaultdict[str, int] = defaultdict(int)
        self._timeline: list[dict[str, Any]] = []
        self._timeline_seq = 0

    async def enqueue_stream(self, stream: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._sequences[stream] += 1
        sequence = self._sequences[stream]
        event = {**payload, "sequence": sequence, "stream": stream}
        self._streams[stream].append(event)
        self._timeline_seq += 1
        timeline_cursor = str(self._timeline_seq)
        timeline_event = {**event, "cursor": timeline_cursor}
        self._timeline.append(timeline_event)
        return timeline_event

    async def list_stream(self, stream: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self._streams.get(stream, [])]

    async def enqueue_queue(self, key: str, payload: dict[str, Any]) -> None:
        self._queues[key].append(json.dumps(payload))

    async def list_queue(self, key: str) -> list[dict[str, Any]]:
        return [json.loads(item) for item in self._queues.get(key, [])]

    async def pop_queue(self, key: str) -> dict[str, Any] | None:
        items = self._queues.get(key)
        if not items:
            return None
        raw = items.pop(0)
        return json.loads(raw)

    async def next_timeline_event(self, cursor: str | None = None) -> dict[str, Any] | None:
        if cursor is None:
            return self._timeline[0] if self._timeline else None
        for event in self._timeline:
            if event["cursor"] > cursor:
                return event
        return None

    async def list_timeline(self, cursor: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        events = self._timeline
        if cursor is not None:
            events = [event for event in events if event["cursor"] > cursor]
        if limit is not None:
            events = events[:limit]
        return [dict(event) for event in events]


class RedisEventStore:
    """Wrapper around a real Redis connection."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def enqueue_stream(self, stream: str, payload: dict[str, Any]) -> dict[str, Any]:
        sequence = await self._client.incr(f"seq:{stream}")
        event = {**payload, "sequence": sequence, "stream": stream}
        await self._client.xadd(stream, {"data": json.dumps(event)}, maxlen=5000)
        timeline_event = dict(event)
        entry_id = await self._client.xadd(TIMELINE_STREAM, {"data": json.dumps(timeline_event)}, maxlen=10000)
        timeline_event["cursor"] = entry_id
        return timeline_event

    async def list_stream(self, stream: str) -> list[dict[str, Any]]:
        entries = await self._client.xrange(stream, "-", "+")
        events: list[dict[str, Any]] = []
        for entry_id, fields in entries:
            data = json.loads(fields.get("data", "{}"))
            data["cursor"] = entry_id
            events.append(data)
        return events

    async def enqueue_queue(self, key: str, payload: dict[str, Any]) -> None:
        await self._client.rpush(key, json.dumps(payload))

    async def list_queue(self, key: str) -> list[dict[str, Any]]:
        raw = await self._client.lrange(key, 0, -1)
        events: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, bytes):
                item = item.decode()
            events.append(json.loads(item))
        return events

    async def pop_queue(self, key: str) -> dict[str, Any] | None:
        raw = await self._client.lpop(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    async def next_timeline_event(self, cursor: str | None = None) -> dict[str, Any] | None:
        start = "-" if cursor is None else f"({cursor})"
        entries = await self._client.xrange(TIMELINE_STREAM, min=start, max="+", count=1)
        if not entries:
            return None
        entry_id, fields = entries[0]
        data = json.loads(fields.get("data", "{}"))
        data["cursor"] = entry_id
        return data

    async def list_timeline(self, cursor: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        start = "-" if cursor is None else f"({cursor})"
        entries = await self._client.xrange(TIMELINE_STREAM, min=start, max="+", count=limit)
        events: list[dict[str, Any]] = []
        for entry_id, fields in entries:
            data = json.loads(fields.get("data", "{}"))
            data["cursor"] = entry_id
            events.append(data)
        return events


class RedisWrapper:
    """Abstraction around redis client to simplify testing."""

    def __init__(self, redis_url: str | None = None) -> None:
        if _RedisClient is not None:
            self._client = _RedisClient.from_url(redis_url or "redis://localhost:6379/0", decode_responses=True)
            self._store: InMemoryEventStore | RedisEventStore = RedisEventStore(self._client)
        else:
            self._client = None
            self._store = InMemoryEventStore()

    async def enqueue_json(self, key: str, payload: dict[str, Any]) -> None:
        if key.startswith("turn:"):
            await self._store.enqueue_queue(key, payload)
        else:
            await self._store.enqueue_stream(key, payload)

    async def list_events(self, key: str) -> list[dict[str, Any]]:
        if key.startswith("turn:"):
            return await self._store.list_queue(key)
        return await self._store.list_stream(key)

    async def pop_event(self, key: str) -> dict[str, Any] | None:
        if key.startswith("turn:"):
            return await self._store.pop_queue(key)
        # For streams we pop via timeline replay; default to None.
        events = await self._store.list_stream(key)
        if not events:
            return None
        first = events[0]
        # Remove the event from stream representation for in-memory store
        if isinstance(self._store, InMemoryEventStore):
            stream_events = self._store._streams.get(key, [])  # type: ignore[attr-defined]
            if stream_events:
                stream_events.pop(0)
        return first

    async def enqueue_turn_event(self, key: str, payload: dict[str, Any]) -> None:
        await self.enqueue_json(key, payload)

    async def next_timeline_event(self, cursor: str | None = None) -> dict[str, Any] | None:
        return await self._store.next_timeline_event(cursor)

    async def list_timeline_events(self, cursor: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        return await self._store.list_timeline(cursor, limit)

    async def raw_client(self) -> Any:  # pragma: no cover - used for dependency overrides
        return self._client


_redis_instance: RedisWrapper | None = None


def get_redis_wrapper() -> RedisWrapper:
    global _redis_instance  # noqa: PLW0603
    if _redis_instance is None:
        settings = get_settings()
        _redis_instance = RedisWrapper(redis_url=settings.redis_url)
    return _redis_instance


async def get_redis() -> AsyncIterator[RedisWrapper]:
    yield get_redis_wrapper()
