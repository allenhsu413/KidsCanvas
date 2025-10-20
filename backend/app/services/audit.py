"""Audit log utilities built on top of the in-memory database."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from ..core.database import DatabaseSession
from ..models import AuditLog


async def record_audit_event(
    session: DatabaseSession,
    *,
    room_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    user_id: UUID | None = None,
    turn_id: UUID | None = None,
) -> AuditLog:
    log = AuditLog(
        room_id=room_id,
        user_id=user_id,
        turn_id=turn_id,
        event_type=event_type,
        payload=payload,
    )
    await session.append_audit_log(log)
    return log
