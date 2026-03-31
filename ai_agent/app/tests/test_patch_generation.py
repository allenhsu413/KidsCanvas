from app.pipelines.patch_generation import PatchGenerationPipeline


def test_patch_generation_includes_safety_score() -> None:
    pipeline = PatchGenerationPipeline()
    patch = pipeline.generate("room-1", "object-1", {})

    assert patch["style"] == "storybook"
    assert patch["safetyScore"] == 0.99
