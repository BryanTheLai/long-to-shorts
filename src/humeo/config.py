"""Configuration for the product pipeline."""

from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Video Output
# ---------------------------------------------------------------------------
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_ASPECT = 9 / 16

# ---------------------------------------------------------------------------
# Clip Selection
# ---------------------------------------------------------------------------
MIN_CLIP_DURATION_SEC = 20
MAX_CLIP_DURATION_SEC = 90
TARGET_CLIP_COUNT = 5

# ---------------------------------------------------------------------------
@dataclass
class PipelineConfig:
    """Runtime configuration for a single pipeline run."""

    youtube_url: str
    output_dir: Path = field(default_factory=lambda: Path("output"))
    work_dir: Path = field(default_factory=lambda: Path(".humeo_work"))

    # LLM provider for clip selection: "gemini" or "openai"
    llm_provider: str = "gemini"

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.work_dir = Path(self.work_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
