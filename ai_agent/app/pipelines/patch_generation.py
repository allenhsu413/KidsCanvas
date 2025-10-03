"""Placeholder pipeline that mocks fairytale patch generation."""
from typing import Any

from ..core.config import get_settings


class PatchGenerationPipeline:
    """Generate storybook-style patches for committed objects."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def generate(self, room_id: str, object_id: str, anchor_region: dict[str, Any]) -> dict[str, Any]:
        """Return a mocked patch payload for downstream services."""
        return {
            "roomId": room_id,
            "objectId": object_id,
            "style": "storybook",
            "model": self.settings.model_name,
            "anchor": anchor_region,
            "instructions": "Blend soft pastel colors with rounded shapes to extend the drawing.",
        }
