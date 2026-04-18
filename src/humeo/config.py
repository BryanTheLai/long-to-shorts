"""Configuration for the product pipeline."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from humeo.env import bootstrap_env

bootstrap_env()

# ---------------------------------------------------------------------------
# Video Output
# ---------------------------------------------------------------------------
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_ASPECT = 9 / 16

# ---------------------------------------------------------------------------
# Clip Selection
# ---------------------------------------------------------------------------
# Clip length bounds for Gemini (also referenced in prompts/clip_selection_system.jinja2).
MIN_CLIP_DURATION_SEC = 50
MAX_CLIP_DURATION_SEC = 90
TARGET_CLIP_COUNT = 5

# Gemini model id (override with GEMINI_MODEL in .env or shell). See docs/ENVIRONMENT.md.
GEMINI_MODEL = (os.environ.get("GEMINI_MODEL") or "gemini-3.1-flash-lite-preview").strip() or "gemini-3.1-flash-lite-preview"
# Per-keyframe layout + bbox (unset = same as effective clip-selection model).
GEMINI_VISION_MODEL = (os.environ.get("GEMINI_VISION_MODEL") or "").strip() or None

# ---------------------------------------------------------------------------
@dataclass
class PipelineConfig:
    """Runtime configuration for a single pipeline run."""

    youtube_url: str
    output_dir: Path = field(default_factory=lambda: Path("output"))
    # None = auto: per-video dir under the cache root (see docs/ENVIRONMENT.md).
    work_dir: Path | None = None
    use_video_cache: bool = True
    # None = default from env (HUMEO_CACHE_ROOT) or platform default.
    cache_root: Path | None = None

    # None = use GEMINI_MODEL from env / module default (Gemini-only clip selection).
    gemini_model: str | None = None
    # None = GEMINI_VISION_MODEL env or same as gemini_model (per-keyframe layout + bbox).
    gemini_vision_model: str | None = None
    # When True, always re-run clip-selection LLM (ignore clips.meta.json match).
    force_clip_selection: bool = False
    # When True, always re-run Gemini vision for layouts (ignore layout_vision.meta.json).
    force_layout_vision: bool = False

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.cache_root is not None:
            self.cache_root = Path(self.cache_root)
        if self.work_dir is not None:
            self.work_dir = Path(self.work_dir)
            self.work_dir.mkdir(parents=True, exist_ok=True)
