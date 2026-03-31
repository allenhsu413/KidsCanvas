"""Basic metrics endpoint for prototype monitoring."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from ...core.config import get_settings

router = APIRouter(tags=["metrics"])
_STARTED_AT = datetime.now(timezone.utc)


@router.get("/metrics")
def read_metrics() -> dict[str, object]:
    """Return a minimal metrics payload for monitoring dashboards."""

    now = datetime.now(timezone.utc)
    settings = get_settings()
    uptime = (now - _STARTED_AT).total_seconds()
    return {
        "service": settings.app_name,
        "environment": settings.environment,
        "started_at": _STARTED_AT.isoformat(),
        "timestamp": now.isoformat(),
        "uptime_seconds": uptime,
    }
