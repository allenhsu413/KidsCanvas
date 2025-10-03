"""Settings for the AI agent service."""
from functools import lru_cache
from pydantic import BaseSettings, Field


class AgentSettings(BaseSettings):
    model_name: str = Field(default="fairytale-diffusion-mini", description="Primary generation model")
    cache_dir: str = Field(default=".cache", description="Local cache for model assets")

    class Config:
        env_prefix = "AGENT_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> AgentSettings:
    """Return agent settings."""
    return AgentSettings()
