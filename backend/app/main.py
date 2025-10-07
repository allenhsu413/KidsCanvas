"""FastAPI application entrypoint."""
from fastapi import FastAPI

from .api.routes.health import router as health_router
from .api.routes.rooms import router as rooms_router
from .core.config import get_settings


def create_app() -> FastAPI:
    """Application factory used by ASGI servers."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.include_router(health_router, prefix=f"{settings.api_prefix}/health", tags=["health"])
    app.include_router(rooms_router, prefix=settings.api_prefix)

    return app


app = create_app()
