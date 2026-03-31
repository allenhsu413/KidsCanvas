"""Schemas for replay API responses."""

from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel


class ReplayResponse(BaseModel):
    cursor: str | None = None
    events: List[dict[str, Any]]
