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
    # When True, use an isolated work dir and force all stages to recompute.
    clean_run: bool = False
    # When True, render stage overwrites existing output files.
    overwrite_outputs: bool = False

    # Stage 2.5 - inner-clip content pruning (HIVE "irrelevant content pruning"
    # applied at clip scale). One of: off | conservative | balanced | aggressive.
    # See ``src/humeo/content_pruning.py`` for the caps and the prompt.
    prune_level: str = "balanced"
    # When True, re-run the pruning LLM even when prune.meta.json matches.
    force_content_pruning: bool = False

    # Subtitle rendering / cue shaping.
    # Values are in **output pixels** for a 1080x1920 short: libass is pinned to
    # the output resolution via ``original_size``, so ``FontSize`` and ``MarginV``
    # mean what they say. 48px font with a 160px bottom margin lands the caption
    # in the lower third with a readable-but-not-shouting size.
    subtitle_font_size: int = 48
    subtitle_margin_v: int = 160
    subtitle_max_words_per_cue: int = 4
    subtitle_max_cue_sec: float = 2.2

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.cache_root is not None:
            self.cache_root = Path(self.cache_root)
        if self.work_dir is not None:
            self.work_dir = Path(self.work_dir)
            self.work_dir.mkdir(parents=True, exist_ok=True)
