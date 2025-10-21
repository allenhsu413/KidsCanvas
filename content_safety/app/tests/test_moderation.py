"""Tests for the moderation engine."""

from app.policies.moderation import ModerationEngine


def test_moderation_engine_flags_banned_keywords() -> None:
    """Ensure banned keywords trigger a block."""
    engine = ModerationEngine()
    result = engine.evaluate_text("A scary dragon with blood")

    assert not result.passed
    assert "scary" in result.reasons
    assert "blood" in result.reasons


def test_moderation_engine_allows_clean_labels() -> None:
    """Labels without banned keywords should pass."""
    engine = ModerationEngine()
    result = engine.evaluate_labels(["happy", "cloud"])

    assert result.passed
    assert result.reasons == []
