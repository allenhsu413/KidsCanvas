"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes.events import router as events_router
from .api.routes.health import router as health_router
from .api.routes.rooms import router as rooms_router
from .api.routes.strokes import router as strokes_router
from .core.config import get_settings
from .core.redis import get_redis_wrapper
from .services.turn_processor import TurnProcessor


def create_app() -> FastAPI:
    """Application factory used by ASGI servers."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001 - FastAPI lifespan signature
        processor: TurnProcessor | None = None
        if settings.enable_turn_worker:
            redis = get_redis_wrapper()
            processor = TurnProcessor(
                redis,
                agent_url=settings.ai_agent_url,
                poll_interval=settings.turn_worker_poll_interval,
            )
            await processor.start()
        try:
            yield
        finally:
            if processor is not None:
                await processor.stop()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.include_router(health_router, prefix=f"{settings.api_prefix}/health", tags=["health"])
    app.include_router(rooms_router, prefix=settings.api_prefix)
    app.include_router(strokes_router, prefix=settings.api_prefix)
    app.include_router(events_router, prefix=settings.api_prefix)

    return app


app = create_app()
