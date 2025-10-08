"""Application configuration using Pydantic settings."""
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str):
    """Simple enum-like helper for environment tagging."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="InfiniteKidsCanvas Game Service", description="Service name")
    api_prefix: str = Field(default="/api", description="Base API prefix")
    environment: str = Field(default=Environment.DEVELOPMENT, description="Runtime environment tag")
    database_url: str = Field(
        default="postgresql+asyncpg://canvas:canvas@localhost:5432/canvas",
        description="SQLAlchemy database URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URI"
    )
    ai_agent_url: str = Field(
        default="http://localhost:8100", description="Base URL for the AI agent"
    )
    enable_turn_worker: bool = Field(
        default=True, description="Whether to start the background turn processor"
    )
    turn_worker_poll_interval: float = Field(
        default=0.5, description="Polling interval for the turn worker"
    )


@lru_cache()
def get_settings() -> AppSettings:
    """Return a cached settings instance."""
    return AppSettings()
