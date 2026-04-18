"""Strict JSON contracts — the "container" of the rocket.

Every primitive reads and writes these. No primitive takes or returns free-form
strings. This is the non-negotiable interface described in the HIVE paper
guide (section 7): machine-checkable intermediate artifacts at every stage.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    """One ASR token with times in **seconds on the source video** timeline."""

    word: str
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)


class ClipSubtitleWords(BaseModel):
    """Words for one clip with times in **seconds relative to clip start** (t=0 at cut in-point)."""

    words: list[TranscriptWord] = Field(default_factory=list)


class FocusStackOrder(str, Enum):
    """Vertical order for ``SPLIT_CHART_PERSON``: who occupies the top 60% / bottom 40% bands."""

    CHART_THEN_PERSON = "chart_then_person"
    PERSON_THEN_CHART = "person_then_chart"


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
        description=(
            "split_chart_person only: left-edge trim of the chart strip, as a fraction of the "
            "left 2/3 pane (0 = use full chart area)."
        ),
    )
    focus_stack_order: FocusStackOrder = Field(
        default=FocusStackOrder.CHART_THEN_PERSON,
        description="For split_chart_person only: chart-on-top vs person-on-top in the 9:16 stack.",
    )
    split_chart_region: BoundingBox | None = Field(
        default=None,
        description=(
            "Optional normalized rect for the chart/slide crop (Gemini vision). "
            "When set with split_person_region, the split layout uses these boxes instead of fixed 2/3|1/3."
        ),
    )
    split_person_region: BoundingBox | None = Field(
        default=None,
        description="Optional normalized rect for the speaker crop (Gemini vision).",
    )


class SceneClassification(BaseModel):
    """Result of the classifier: which layout should a given scene use."""

    scene_id: str
    layout: LayoutKind
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


# ---------------------------------------------------------------------------
# Vision bounding boxes — the LLM+OCR path (alt to pixel heuristics)
# ---------------------------------------------------------------------------


class BoundingBox(BaseModel):
    """Normalized [0..1] bounding box in the source frame coordinate space.

    Normalized coords keep these outputs portable across source resolutions
    and stop the model hallucinating pixel values. ``x2 > x1`` and
    ``y2 > y1`` are enforced.
    """

    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)
    label: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("x2")
    @classmethod
    def _x2_after_x1(cls, v: float, info) -> float:
        x1 = info.data.get("x1", 0.0)
        if v <= x1:
            raise ValueError("x2 must be > x1")
        return v

    @field_validator("y2")
    @classmethod
    def _y2_after_y1(cls, v: float, info) -> float:
        y1 = info.data.get("y1", 0.0)
        if v <= y1:
            raise ValueError("y2 must be > y1")
        return v

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def width(self) -> float:
        return self.x2 - self.x1


class SceneRegions(BaseModel):
    """Vision-LLM output for a single scene keyframe.

    Flow: detect a scene change locally (cheap) -> extract one keyframe per
    scene -> send that keyframe to a vision LLM with an OCR hint -> get
    normalized bounding boxes for the on-screen roles (``person``,
    ``chart``). Those boxes drive ``person_x_norm`` / ``chart_x_norm`` on a
    ``LayoutInstruction`` without any pixel code running in Python.
    """

    scene_id: str
    person_bbox: BoundingBox | None = None
    chart_bbox: BoundingBox | None = None
    ocr_text: str = ""
    raw_reason: str = ""


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

    # Optional LLM metadata (source timeline is start_time_sec / end_time_sec).
    hook_start_sec: float | None = Field(
        default=None,
        description="Seconds from clip in-point where the viral hook begins (0 = clip start).",
    )
    hook_end_sec: float | None = Field(
        default=None,
        description="Seconds from clip in-point where the hook ends (exclusive upper bound).",
    )
    trim_start_sec: float = Field(
        default=0.0,
        ge=0,
        description="Seconds to remove from the start of this segment when exporting.",
    )
    trim_end_sec: float = Field(
        default=0.0,
        ge=0,
        description="Seconds to remove from the end of this segment when exporting.",
    )
    shorts_title: str = ""
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    layout_hint: LayoutKind | None = None
    needs_review: bool = False
    review_reason: str = ""

    @model_validator(mode="after")
    def _timing_consistency(self) -> "Clip":
        if self.end_time_sec <= self.start_time_sec:
            raise ValueError("end_time_sec must be greater than start_time_sec")
        dur = self.end_time_sec - self.start_time_sec
        hs, he = self.hook_start_sec, self.hook_end_sec
        if (hs is None) ^ (he is None):
            raise ValueError("hook_start_sec and hook_end_sec must both be set or both omitted")
        if hs is not None and he is not None:
            if not (0 <= hs < he <= dur):
                raise ValueError(
                    "hook window must satisfy 0 <= hook_start_sec < hook_end_sec <= clip duration"
                )
        if self.trim_start_sec + self.trim_end_sec > dur:
            raise ValueError("trim_start_sec + trim_end_sec must not exceed clip duration")
        return self

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
    subtitle_path: str | None = None
    title_text: str = ""
    mode: Literal["normal", "dry_run"] = "normal"


class RenderResult(BaseModel):
    clip_id: str
    output_path: str
    ffmpeg_cmd: list[str]
    success: bool
    error: str = ""
