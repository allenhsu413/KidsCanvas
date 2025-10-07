"""Pydantic schemas for room objects."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from pydantic.config import ConfigDict

from ..models import ObjectStatus, TurnActor, TurnStatus


class BBoxSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    x: float
    y: float
    width: float
    height: float


class AnchorRingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inner: BBoxSchema
    outer: BBoxSchema


class ObjectCreatePayload(BaseModel):
    owner_id: UUID = Field(description="User committing the object")
    stroke_ids: list[UUID] = Field(description="Stroke identifiers to group")
    label: str | None = Field(default=None, max_length=128)

    @field_validator("stroke_ids")
    @classmethod
    def ensure_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("stroke_ids must be unique")
        return value


class ObjectSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    room_id: UUID
    owner_id: UUID
    label: str | None
    status: ObjectStatus
    bbox: BBoxSchema
    anchor_ring: AnchorRingSchema
    created_at: datetime


class TurnSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    room_id: UUID
    sequence: int
    status: TurnStatus
    current_actor: TurnActor
    source_object_id: UUID
    created_at: datetime
    updated_at: datetime


class ObjectCreateResponse(BaseModel):
    object: ObjectSchema
    turn: TurnSchema
    room: dict[str, Any]
