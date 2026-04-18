"""
Step 2 - Clip Selection: Gemini-only LLM for viral clip identification.

Uses the unified ``google-genai`` SDK (``from google import genai``). See:
https://github.com/googleapis/python-genai
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable, TypeVar

from google import genai
from google.genai import types

from humeo_core.schemas import Clip, ClipPlan

from humeo.config import (
    GEMINI_MODEL,
    MAX_CLIP_DURATION_SEC,
    MIN_CLIP_DURATION_SEC,
    TARGET_CLIP_COUNT,
)
from humeo.env import resolve_gemini_api_key
from humeo.prompt_loader import clip_selection_prompts

logger = logging.getLogger(__name__)

T = TypeVar("T")

LLM_MAX_ATTEMPTS = 3
LLM_RETRY_DELAY_SEC = 2.0


def _retry_llm(name: str, fn: Callable[[], T], attempts: int = LLM_MAX_ATTEMPTS) -> T:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            if i < attempts - 1:
                logger.warning("%s attempt %d/%d failed: %s", name, i + 1, attempts, e)
                time.sleep(LLM_RETRY_DELAY_SEC * (i + 1))
    assert last is not None
    raise last


def build_prompt(transcript: dict) -> tuple[str, str]:
    """Return ``(system_prompt, user_message)`` for the clip-selector LLM call."""
    lines = []
    for seg in transcript.get("segments", []):
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        lines.append(f"[{start:.1f}s - {end:.1f}s] {text}")

    transcript_text = "\n".join(lines)

    system, user = clip_selection_prompts(
        transcript_text=transcript_text,
        min_dur=MIN_CLIP_DURATION_SEC,
        max_dur=MAX_CLIP_DURATION_SEC,
        count=TARGET_CLIP_COUNT,
    )
    return system, user


def select_clips(transcript: dict, *, gemini_model: str | None = None) -> tuple[list[Clip], str]:
    """
    Call Gemini to select clips. Returns ``(clips, raw_json)`` for caching / debugging.

    Uses ``google.genai.Client`` and ``GenerateContentConfig`` (see Google Gen AI SDK for Python).
    """
    model_name = (gemini_model or GEMINI_MODEL).strip()
    system_prompt, user_text = build_prompt(transcript)

    client = genai.Client(api_key=resolve_gemini_api_key())

    def _call() -> str:
        logger.info("Gemini clip selection (model=%s)...", model_name)
        response = client.models.generate_content(
            model=model_name,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,
                response_mime_type="application/json",
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned empty response text")
        return response.text

    raw = _retry_llm("Gemini clip selection", _call)
    clips = _parse_clips(raw)
    clips = sorted(clips, key=lambda c: c.virality_score, reverse=True)
    return clips, raw


def _parse_clips(raw_json: str) -> list[Clip]:
    """Parse and validate the LLM's JSON response into Clip objects."""
    data = json.loads(raw_json)
    clips_data = data.get("clips", data) if isinstance(data, dict) else data

    clips: list[Clip] = []
    for item in clips_data:
        payload = dict(item)
        payload.pop("duration_sec", None)
        clip = Clip.model_validate(payload)

        actual_dur = clip.end_time_sec - clip.start_time_sec
        stated_dur = item.get("duration_sec")
        if stated_dur is not None and abs(actual_dur - float(stated_dur)) > 1.0:
            logger.warning(
                "Clip %s: stated duration %.1fs doesn't match (%.1f-%.1f = %.1f).",
                clip.clip_id, float(stated_dur),
                clip.start_time_sec, clip.end_time_sec, actual_dur,
            )
        clips.append(clip)

    logger.info("Parsed %d clips from LLM response", len(clips))
    return clips


def save_clips(clips: list[Clip], output_path: Path) -> Path:
    """Persist clips to a JSON file using the shared Pydantic schema."""
    plan = ClipPlan(source_path="", clips=list(clips))
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(plan.model_dump_json(indent=2))
    logger.info("Saved %d clips to %s", len(clips), output_path)
    return output_path


def load_clips(clips_path: Path) -> list[Clip]:
    """Load clips from a previously saved JSON file."""
    with open(clips_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "clips" in data:
        return [Clip.model_validate(c) for c in data["clips"]]
    return [Clip.model_validate(c) for c in data]
