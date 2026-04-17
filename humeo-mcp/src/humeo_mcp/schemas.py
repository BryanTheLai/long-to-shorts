"""Strict JSON contracts — the "container" of the rocket.

Every primitive reads and writes these. No primitive takes or returns free-form
strings. This is the non-negotiable interface described in the HIVE paper
guide (section 7): machine-checkable intermediate artifacts at every stage.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Extraction artifacts
# ---------------------------------------------------------------------------


class Scene(BaseModel):
    """A single shot/scene detected in the source video."""

    scene_id: str
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)
    keyframe_path: str | None = None

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, v: float, info) -> float:
        start = info.data.get("start_time", 0.0)
        if v <= start:
            raise ValueError("end_time must be strictly greater than start_time")
        return v

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class TranscriptWord(BaseModel):
    word: str
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)


class IngestResult(BaseModel):
    """Everything Stage 1 (deterministic local extraction) produces."""

    source_path: str
    duration_sec: float
    scenes: list[Scene]
    transcript_words: list[TranscriptWord]
    keyframes_dir: str | None = None


# ---------------------------------------------------------------------------
# Layout system — the 3 "thrusters"
# ---------------------------------------------------------------------------


class LayoutKind(str, Enum):
    """The 3 (and only 3) 9:16 layouts used for this specific video format.

    Mirrors the three on-screen scene types the user identified:

    - ``ZOOM_CALL_CENTER``:   1-person zoom call, subject in the middle, tight crop.
    - ``SIT_CENTER``:         1-person sitting, subject in the middle, wider crop.
    - ``SPLIT_CHART_PERSON``: explainer scene with a chart on the left (~2/3)
                              and a person on the right (~1/3). In the 9:16
                              output these are stacked: chart on top, person below.
    """

    ZOOM_CALL_CENTER = "zoom_call_center"
    SIT_CENTER = "sit_center"
    SPLIT_CHART_PERSON = "split_chart_person"


class LayoutInstruction(BaseModel):
    """Per-clip decision telling the compiler which of the 3 layouts to apply."""

    clip_id: str
    layout: LayoutKind
    # Optional per-layout knobs. Defaults are sane for a 1920x1080 source.
    zoom: float = Field(default=1.0, gt=0, le=4.0)
    person_x_norm: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Normalized x-center of the human subject in source frame (0=left, 1=right).",
    )
    chart_x_norm: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Normalized x-start of the chart region in source frame (only used by split_chart_person).",
    )


class SceneClassification(BaseModel):
    """Result of the classifier: which layout should a given scene use."""

    scene_id: str
    layout: LayoutKind
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


# ---------------------------------------------------------------------------
# Clip planning
# ---------------------------------------------------------------------------


class Clip(BaseModel):
    clip_id: str
    topic: str
    start_time_sec: float = Field(ge=0)
    end_time_sec: float = Field(gt=0)
    viral_hook: str = ""
    virality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    transcript: str = ""
    suggested_overlay_title: str = ""
    layout: LayoutKind | None = None

    @property
    def duration_sec(self) -> float:
        return self.end_time_sec - self.start_time_sec


class ClipPlan(BaseModel):
    """Output of the clip-selection stage — a list of clips + their layouts."""

    source_path: str
    clips: list[Clip]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


class RenderRequest(BaseModel):
    source_path: str
    clip: Clip
    layout: LayoutInstruction
    output_path: str
    width: int = 1080
    height: int = 1920
    burn_subtitles: bool = False
    title_text: str = ""
    mode: Literal["normal", "dry_run"] = "normal"


class RenderResult(BaseModel):
    clip_id: str
    output_path: str
    ffmpeg_cmd: list[str]
    success: bool
    error: str = ""
