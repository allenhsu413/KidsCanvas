"""Configuration for the content safety service."""
from functools import lru_cache
from pydantic import BaseSettings, Field


class SafetySettings(BaseSettings):
    banned_keywords: list[str] = Field(
        default_factory=lambda: [
            "violence",
            "blood",
            "weapon",
            "scary",
            "alcohol",
        ]
    )

    class Config:
        env_prefix = "SAFETY_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> SafetySettings:
    """Return service settings."""
    return SafetySettings()
