"""Per-clip layout + bbox via Gemini vision (no pixel heuristics in the product pipeline)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from humeo_mcp.schemas import (
    BoundingBox,
    LayoutInstruction,
    LayoutKind,
    Scene,
    SceneClassification,
    SceneRegions,
)
from humeo_mcp.primitives.vision import layout_instruction_from_regions

from humeo.config import GEMINI_MODEL, GEMINI_VISION_MODEL, PipelineConfig
from humeo.env import resolve_gemini_api_key

logger = logging.getLogger(__name__)

LAYOUT_VISION_META = "layout_vision.meta.json"
LAYOUT_VISION_JSON = "layout_vision.json"

GEMINI_LAYOUT_VISION_PROMPT = """You are framing a vertical short (9:16) from a 16:9 video frame.

Return ONLY a JSON object with this exact shape:
{
  "layout": "sit_center" | "zoom_call_center" | "split_chart_person",
  "person_bbox": {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0} | null,
  "chart_bbox": {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0} | null,
  "reason": "short rationale"
}

Rules:
- All bbox coordinates are normalized 0..1 (left/top = 0, right/bottom = 1). Require x2 > x1 and y2 > y1 when a bbox is non-null.
- person_bbox: tight box around the main speaker's head/upper body if visible; null if not visible.
- chart_bbox: slide, chart, graph, or large on-screen graphic; null if none.
- layout:
  - split_chart_person: chart/slide beside or overlapping a visible speaker (webinar / explainer). Prefer this when BOTH person_bbox and chart_bbox are non-null and they occupy distinct regions.
  - zoom_call_center: single tight webcam / video-call headshot filling much of the frame.
  - sit_center: single subject, interview framing, or when unsure.
- No markdown. JSON only."""


def _clips_fingerprint(clips_path: Path) -> str:
    if not clips_path.is_file():
        return ""
    return hashlib.sha256(clips_path.read_bytes()).hexdigest()


def layout_cache_valid(
    work_dir: Path,
    *,
    transcript_fp: str,
    clips_fp: str,
    vision_model: str,
) -> bool:
    meta_path = work_dir / LAYOUT_VISION_META
    data_path = work_dir / LAYOUT_VISION_JSON
    if not meta_path.is_file() or not data_path.is_file():
        return False
    try:
        meta: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (
        meta.get("transcript_sha256") == transcript_fp
        and meta.get("clips_sha256") == clips_fp
        and meta.get("gemini_vision_model") == vision_model
    )


def load_layout_cache(work_dir: Path) -> dict[str, dict[str, Any]] | None:
    p = work_dir / LAYOUT_VISION_JSON
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    clips = data.get("clips")
    return clips if isinstance(clips, dict) else None


def write_layout_cache(
    work_dir: Path,
    *,
    transcript_fp: str,
    clips_fp: str,
    vision_model: str,
    clips_payload: dict[str, dict[str, Any]],
) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "transcript_sha256": transcript_fp,
        "clips_sha256": clips_fp,
        "gemini_vision_model": vision_model,
    }
    (work_dir / LAYOUT_VISION_META).write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    (work_dir / LAYOUT_VISION_JSON).write_text(
        json.dumps({"clips": clips_payload}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Wrote %s and %s", LAYOUT_VISION_META, LAYOUT_VISION_JSON)


def _parse_bbox(raw: object) -> BoundingBox | None:
    if not raw or not isinstance(raw, dict):
        return None
    try:
        return BoundingBox.model_validate(raw)
    except Exception:
        return None


def _instruction_from_gemini_json(
    scene_id: str, data: dict[str, Any]
) -> LayoutInstruction:
    layout_str = str(data.get("layout", "sit_center")).strip()
    try:
        kind = LayoutKind(layout_str)
    except ValueError:
        kind = LayoutKind.SIT_CENTER
    pb = _parse_bbox(data.get("person_bbox"))
    cb = _parse_bbox(data.get("chart_bbox"))
    reason = str(data.get("reason", ""))[:400]

    regions = SceneRegions(scene_id=scene_id, person_bbox=pb, chart_bbox=cb, raw_reason=reason)
    classification = SceneClassification(
        scene_id=scene_id, layout=kind, confidence=1.0, reason=reason
    )
    instr = layout_instruction_from_regions(regions, classification, clip_id=scene_id)
    if kind == LayoutKind.SPLIT_CHART_PERSON and pb is not None and cb is not None:
        instr = instr.model_copy(update={"split_chart_region": cb, "split_person_region": pb})
    return instr


def _call_gemini_vision(keyframe_path: str, model_name: str) -> dict[str, Any]:
    path = Path(keyframe_path)
    data = path.read_bytes()
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    client = genai.Client(api_key=resolve_gemini_api_key())
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_text(text=GEMINI_LAYOUT_VISION_PROMPT),
            types.Part.from_bytes(data=data, mime_type=mime),
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    if not response.text:
        raise RuntimeError("Gemini vision returned empty response")
    return json.loads(response.text)


def infer_layout_instructions(
    scenes: list[Scene],
    *,
    gemini_vision_model: str,
) -> tuple[dict[str, LayoutInstruction], dict[str, dict[str, Any]]]:
    """Return ``(clip_id -> LayoutInstruction, clip_id -> raw_gemini_json)``."""

    out: dict[str, LayoutInstruction] = {}
    raw_by_clip: dict[str, dict[str, Any]] = {}
    model_name = gemini_vision_model.strip()

    for s in scenes:
        sid = s.scene_id
        if not s.keyframe_path:
            logger.warning("No keyframe for %s; using sit_center.", sid)
            out[sid] = LayoutInstruction(clip_id=sid, layout=LayoutKind.SIT_CENTER)
            raw_by_clip[sid] = {"error": "no keyframe", "layout": "sit_center"}
            continue
        try:
            data = _call_gemini_vision(s.keyframe_path, model_name)
            raw_by_clip[sid] = data
            out[sid] = _instruction_from_gemini_json(sid, data)
        except Exception as e:
            logger.warning("Gemini vision failed for %s: %s — defaulting sit_center", sid, e)
            out[sid] = LayoutInstruction(clip_id=sid, layout=LayoutKind.SIT_CENTER)
            raw_by_clip[sid] = {"error": str(e), "layout": "sit_center"}

    return out, raw_by_clip


def resolved_vision_model(config: PipelineConfig) -> str:
    if config.gemini_vision_model:
        return config.gemini_vision_model.strip()
    if GEMINI_VISION_MODEL:
        return GEMINI_VISION_MODEL
    return (config.gemini_model or GEMINI_MODEL).strip()


def run_layout_vision_stage(
    work_dir: Path,
    scenes: list[Scene],
    *,
    transcript_fp: str,
    clips_path: Path,
    config: PipelineConfig,
) -> dict[str, LayoutInstruction]:
    """Load cache or call Gemini vision for each keyframe; persist JSON artifacts."""
    clips_fp = _clips_fingerprint(clips_path)
    vm = resolved_vision_model(config)

    if (
        not config.force_layout_vision
        and layout_cache_valid(work_dir, transcript_fp=transcript_fp, clips_fp=clips_fp, vision_model=vm)
    ):
        cached = load_layout_cache(work_dir)
        if cached:
            logger.info("Layout vision cache hit; skipping Gemini vision calls.")
            return {
                k: LayoutInstruction.model_validate(v["instruction"])
                for k, v in cached.items()
                if isinstance(v, dict) and "instruction" in v
            }

    instructions, raw_by_clip = infer_layout_instructions(scenes, gemini_vision_model=vm)

    payload: dict[str, dict[str, Any]] = {}
    for sid, instr in instructions.items():
        payload[sid] = {
            "instruction": json.loads(instr.model_dump_json()),
            "raw": raw_by_clip.get(sid, {}),
        }
    write_layout_cache(
        work_dir,
        transcript_fp=transcript_fp,
        clips_fp=clips_fp,
        vision_model=vm,
        clips_payload=payload,
    )
    return instructions
