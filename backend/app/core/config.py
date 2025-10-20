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
    auth_secret_key: str = Field(
        default="dev-secret", description="HMAC secret for signing access tokens"
    )
    auth_algorithm: str = Field(
        default="HS256", description="JWT signing algorithm"
    )
    access_token_expire_minutes: int = Field(
        default=60, description="Access token lifetime in minutes"
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
    state_file: str | None = Field(
        default="data/state.json",
        description="Path to JSON file used for prototype persistence (set to empty to disable)",
    )


@lru_cache()
def get_settings() -> AppSettings:
    """Return a cached settings instance."""
    return AppSettings()
