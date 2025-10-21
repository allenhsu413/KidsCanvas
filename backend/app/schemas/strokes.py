"""Pydantic schemas for stroke APIs."""

from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from pydantic.config import ConfigDict


class PointSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    x: float
    y: float


class StrokeCreatePayload(BaseModel):
    author_id: UUID = Field(description="User creating the stroke")
    color: str = Field(default="#000000", max_length=16)
    width: float = Field(gt=0, description="Stroke width in pixels")
    path: List[PointSchema]

    @field_validator("path")
    @classmethod
    def ensure_points(cls, value: List[PointSchema]) -> List[PointSchema]:
        if not value:
            raise ValueError("path must contain at least one point")
        return value


class StrokeSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    room_id: UUID
    author_id: UUID
    color: str
    width: float
    ts: datetime
    path: List[PointSchema]
    object_id: UUID | None


class StrokeCreateResponse(BaseModel):
    stroke: StrokeSchema


class StrokeBatchResponse(BaseModel):
    strokes: List[StrokeSchema]
