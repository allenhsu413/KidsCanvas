"""Schemas for audit log responses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List
from uuid import UUID

from pydantic import BaseModel
from pydantic.config import ConfigDict


class AuditLogSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    room_id: UUID
    user_id: UUID | None = None
    turn_id: UUID | None = None
    event_type: str
    payload: dict[str, Any]
    ts: datetime


class AuditLogResponse(BaseModel):
    room_id: UUID
    logs: List[AuditLogSchema]
