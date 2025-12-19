"""Audit log endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ...core.database import DatabaseSession, get_db_session
from ...core.security import AuthenticatedSubject, UserRole, require_roles
from ...schemas.audit import AuditLogResponse

router = APIRouter(prefix="/rooms", tags=["audit"])


@router.get("/{room_id}/audit", response_model=AuditLogResponse)
async def list_audit_logs(
    room_id: UUID,
    since: datetime | None = Query(
        default=None, description="Filter audit logs from this timestamp"
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    session: DatabaseSession = Depends(get_db_session),
    subject: AuthenticatedSubject = Depends(
        require_roles(UserRole.PLAYER, UserRole.MODERATOR, UserRole.PARENT)
    ),
) -> AuditLogResponse:
    """Return audit logs for a room."""

    _ = subject
    logs = await session.list_audit_logs(room_id=room_id)
    if since is not None:
        logs = [log for log in logs if log.ts >= since]
    if limit:
        logs = logs[:limit]
    return AuditLogResponse(room_id=room_id, logs=logs)
