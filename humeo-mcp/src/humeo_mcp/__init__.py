"""humeo-mcp: reusable-rocket MCP primitives for long-video-to-shorts editing.

First-principles design (rocket analogy):
    Container  -> schemas.py        (strict JSON contracts)
    Landing gear -> primitives/ingest.py, primitives/compile.py  (deterministic local)
    Thrusters    -> primitives/layouts.py                         (3 fixed 9:16 layouts)
    Pilot        -> primitives/classify.py, primitives/select_clips.py (heuristic, LLM-ready)
    Control panel -> server.py      (FastMCP tools that expose all primitives)
"""

from .schemas import (
    BoundingBox,
    Clip,
    ClipPlan,
    IngestResult,
    LayoutInstruction,
    LayoutKind,
    RenderRequest,
    RenderResult,
    Scene,
    SceneClassification,
    SceneRegions,
    TranscriptWord,
)

__all__ = [
    "BoundingBox",
    "Clip",
    "ClipPlan",
    "IngestResult",
    "LayoutInstruction",
    "LayoutKind",
    "RenderRequest",
    "RenderResult",
    "Scene",
    "SceneClassification",
    "SceneRegions",
    "TranscriptWord",
]

__version__ = "0.1.0"
