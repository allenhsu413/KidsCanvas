"""Schemas for room creation and join flows."""
from __future__ import annotations

from datetime import datetime
from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from .objects import ObjectSchema, TurnSchema
from .strokes import StrokeSchema


class RoomCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    host_id: UUID = Field(description="User identifier for the room host")


class RoomJoinPayload(BaseModel):
    user_id: UUID = Field(description="User joining the room")


class RoomSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    turn_seq: int
    created_at: datetime


class RoomMemberSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    room_id: UUID
    user_id: UUID
    role: str
    joined_at: datetime


class RoomSnapshotResponse(BaseModel):
    room: RoomSchema
    member: RoomMemberSchema
    members: List[RoomMemberSchema]
    strokes: List[StrokeSchema]
    objects: List[ObjectSchema]
    turns: List[TurnSchema]
