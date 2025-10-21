"""Health check endpoints for monitoring."""

from fastapi import APIRouter

from ...core.config import get_settings

router = APIRouter()


@router.get("/", summary="Service health probe")
def read_health() -> dict[str, str]:
    """Return a static payload indicating the service is running."""
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name}
