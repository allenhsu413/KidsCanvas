"""Entrypoint for the AI agent service."""
from fastapi import FastAPI

from .core.config import get_settings
from .pipelines.patch_generation import PatchGenerationPipeline

app = FastAPI(title="InfiniteKidsCanvas AI Agent")


@app.post("/generate", summary="Generate fairytale patch")
def generate_patch(request: dict[str, object]) -> dict[str, object]:
    """Generate a patch response from object metadata."""
    room_id = str(request.get("roomId", "unknown-room"))
    object_id = str(request.get("objectId", "unknown-object"))
    anchor_region = request.get("anchorRegion", {})
    pipeline = PatchGenerationPipeline()
    patch = pipeline.generate(room_id, object_id, anchor_region if isinstance(anchor_region, dict) else {})
    settings = get_settings()
    return {"patch": patch, "cacheDir": settings.cache_dir}
