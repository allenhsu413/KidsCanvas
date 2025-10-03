"""Simple moderation utilities for text and image payloads."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..core.config import get_settings


@dataclass(slots=True)
class SafetyResult:
    """Represents the result of a safety evaluation."""

    category: str
    passed: bool
    reasons: list[str]


class ModerationEngine:
    """Rule-based moderation for prototype purposes."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def evaluate_text(self, text: str) -> SafetyResult:
        """Check text against banned keywords."""
        triggers = [kw for kw in self.settings.banned_keywords if kw in text.lower()]
        return SafetyResult(category="text", passed=not triggers, reasons=triggers)

    def evaluate_labels(self, labels: Iterable[str]) -> SafetyResult:
        """Check model labels for disallowed content."""
        normalized = [label.lower() for label in labels]
        triggers = [kw for kw in self.settings.banned_keywords if kw in normalized]
        return SafetyResult(category="image", passed=not triggers, reasons=triggers)
