"""Redis helper with an in-memory fallback for offline testing."""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

try:  # pragma: no cover - optional dependency
    from redis.asyncio import Redis as _RedisClient  # type: ignore
except ImportError:  # pragma: no cover - fallback path
    _RedisClient = None  # type: ignore


class InMemoryRedis:
    """Minimal Redis clone supporting the operations we require."""

    def __init__(self) -> None:
        self._lists: defaultdict[str, list[str]] = defaultdict(list)

    async def rpush(self, key: str, value: str) -> None:
        self._lists[key].append(value)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self._lists.get(key, [])
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    async def lpop(self, key: str) -> str | None:
        items = self._lists.get(key)
        if not items:
            return None
        return items.pop(0)

    async def publish(self, channel: str, message: str) -> None:  # pragma: no cover - not used yet
        self._lists[channel].append(message)

    async def close(self) -> None:
        self._lists.clear()


class RedisWrapper:
    """Abstraction around redis client to simplify testing."""

    def __init__(self) -> None:
        if _RedisClient is not None:
            self._client = _RedisClient.from_url("redis://localhost:6379/0", decode_responses=True)
        else:
            self._client = InMemoryRedis()

    async def enqueue_json(self, key: str, payload: dict[str, Any]) -> None:
        await self._client.rpush(key, json.dumps(payload))

    async def list_events(self, key: str) -> list[dict[str, Any]]:
        raw = await self._client.lrange(key, 0, -1)
        return [json.loads(item) for item in raw]

    async def pop_event(self, key: str) -> dict[str, Any] | None:
        if hasattr(self._client, "lpop"):
            raw = await self._client.lpop(key)
        else:  # pragma: no cover - redis client fallback
            raw = None
        if raw is None:
            return None
        if isinstance(raw, bytes):  # pragma: no cover - redis client
            raw = raw.decode()
        return json.loads(raw)

    async def enqueue_turn_event(self, key: str, payload: dict[str, Any]) -> None:
        await self.enqueue_json(key, payload)

    async def raw_client(self) -> Any:  # pragma: no cover - used for dependency overrides
        return self._client


_redis_instance: RedisWrapper | None = None


def get_redis_wrapper() -> RedisWrapper:
    global _redis_instance  # noqa: PLW0603
    if _redis_instance is None:
        _redis_instance = RedisWrapper()
    return _redis_instance


async def get_redis() -> AsyncIterator[RedisWrapper]:
    yield get_redis_wrapper()
