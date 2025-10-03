"""Application configuration using Pydantic settings."""
from functools import lru_cache
from pydantic import BaseSettings, Field


class AppSettings(BaseSettings):
    app_name: str = Field(default="InfiniteKidsCanvas Game Service", description="Service name")
    api_prefix: str = Field(default="/api", description="Base API prefix")
    environment: str = Field(default="development", description="Runtime environment tag")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> AppSettings:
    """Return a cached settings instance."""
    return AppSettings()
