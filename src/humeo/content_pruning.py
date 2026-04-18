"""Stage 2.5 - Content pruning inside each selected clip.

This is the HIVE "irrelevant content pruning" sub-task, applied at the
*inner-clip* scale rather than the scene scale. After the clip selector has
chosen 5 x 50-90s windows, we ask Gemini to tighten each window by dropping
weak lead-in (throat-clears, false starts, slow setup) and weak tail content
(trailing ramble, fade-out talk).

Design choices kept deliberately minimal:

- **No schema changes.** The existing ``Clip.trim_start_sec`` /
  ``Clip.trim_end_sec`` fields already feed ``humeo.render_window`` and
  ``humeo_core.primitives.compile`` via ``-ss`` / ``-t``. Writing the pruned
  in / out points into those fields tightens the exported window for free.
- **Contiguous trimming only** (V1). We move the in-point forward and the
  out-point backward; we do not cut in the middle. That keeps subtitles and
  layout vision untouched.
- **Strict clamping** after the LLM returns, so the final duration always
  respects ``MIN_CLIP_DURATION_SEC`` and any declared hook window is
  preserved.
- **Never fatal.** Any failure (API error, malformed JSON, missing clip_id)
  degrades to no-op trims (0.0 / 0.0) for that clip. The pipeline still
  produces output identical to the pre-Stage-2.5 behaviour.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

from humeo_core.schemas import Clip

from humeo.config import (
    GEMINI_MODEL,
    MAX_CLIP_DURATION_SEC,
    MIN_CLIP_DURATION_SEC,
    PipelineConfig,
)
from humeo.env import resolve_gemini_api_key
from humeo.prompt_loader import content_pruning_system_prompt

logger = logging.getLogger(__name__)

T = TypeVar("T")

PRUNE_META_VERSION = 1
PRUNE_META_FILENAME = "prune.meta.json"
PRUNE_RAW_FILENAME = "prune_raw.json"
PRUNE_ARTIFACT_FILENAME = "prune.json"

LLM_MAX_ATTEMPTS = 3
LLM_RETRY_DELAY_SEC = 2.0

PruneLevel = Literal["off", "conservative", "balanced", "aggressive"]

VALID_LEVELS: tuple[PruneLevel, ...] = ("off", "conservative", "balanced", "aggressive")

# Per-level cap on the fraction of the original clip the LLM is allowed to
# trim. Even if the LLM tries to be more eager, we clamp. Final duration is
# additionally clamped to ``MIN_CLIP_DURATION_SEC``.
_MAX_TOTAL_TRIM_PCT: dict[PruneLevel, float] = {
    "off": 0.0,
    "conservative": 0.10,
    "balanced": 0.20,
    "aggressive": 0.35,
}


class _PruneDecision(BaseModel):
    """Per-clip decision returned by Gemini (clip-relative seconds)."""

    clip_id: str
    trim_start_sec: float = Field(default=0.0, ge=0.0)
    trim_end_sec: float = Field(default=0.0, ge=0.0)
    reason: str = ""


class _PruneResponse(BaseModel):
    decisions: list[_PruneDecision] = Field(default_factory=list)


@dataclass
class _ClampStats:
    """Diagnostics for why a returned trim got reshaped."""

    clamped_start: bool = False
    clamped_end: bool = False
    hook_protected: bool = False
    min_duration_protected: bool = False
    max_pct_protected: bool = False


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


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------


def _clamp_decision(
    clip: Clip,
    trim_start: float,
    trim_end: float,
    *,
    level: PruneLevel,
) -> tuple[float, float, _ClampStats]:
    """Clamp a raw (trim_start, trim_end) pair so the resulting clip is legal.

    Guarantees:
    - ``trim_start`` and ``trim_end`` are non-negative.
    - Final duration (``clip.duration_sec - trim_start - trim_end``) is at
      least ``MIN_CLIP_DURATION_SEC`` (or the original duration, whichever is
      smaller - we never *extend* a clip that was already too short).
    - Combined trim does not exceed the level's allowed fraction of the
      original duration.
    - If ``hook_start_sec`` / ``hook_end_sec`` are set on the clip, the hook
      window stays fully inside the result.
    """
    stats = _ClampStats()
    duration = clip.duration_sec

    ts = max(0.0, float(trim_start))
    te = max(0.0, float(trim_end))
    if ts != trim_start:
        stats.clamped_start = True
    if te != trim_end:
        stats.clamped_end = True

    max_pct = _MAX_TOTAL_TRIM_PCT.get(level, 0.0)
    max_total_trim = duration * max_pct
    if ts + te > max_total_trim:
        scale = max_total_trim / max(ts + te, 1e-9)
        ts = ts * scale
        te = te * scale
        stats.max_pct_protected = True

    if clip.hook_start_sec is not None and clip.hook_end_sec is not None:
        hook_lo = clip.hook_start_sec
        hook_hi = clip.hook_end_sec
        if ts > max(0.0, hook_lo - 0.25):
            ts = max(0.0, hook_lo - 0.25)
            stats.hook_protected = True
        if te > max(0.0, duration - hook_hi - 0.25):
            te = max(0.0, duration - hook_hi - 0.25)
            stats.hook_protected = True

    min_final = min(float(MIN_CLIP_DURATION_SEC), duration)
    max_total_by_min = max(0.0, duration - min_final)
    if ts + te > max_total_by_min:
        overflow = ts + te - max_total_by_min
        te_cut = min(te, overflow)
        te -= te_cut
        overflow -= te_cut
        if overflow > 0:
            ts = max(0.0, ts - overflow)
        stats.min_duration_protected = True

    ts = max(0.0, min(ts, duration))
    te = max(0.0, min(te, duration - ts))
    return ts, te, stats


def apply_prune_decisions(
    clips: list[Clip],
    decisions: list[_PruneDecision],
    *,
    level: PruneLevel,
) -> list[Clip]:
    """Return new clips with trim_start / trim_end set from LLM decisions.

    Clips whose ``clip_id`` is missing from ``decisions`` are returned with
    trims of 0 / 0 (no-op). Decisions are always clamped; no exception is
    raised if the model returned invalid numbers.
    """
    by_id = {d.clip_id: d for d in decisions}
    out: list[Clip] = []
    for clip in clips:
        d = by_id.get(clip.clip_id)
        if d is None or level == "off":
            out.append(clip.model_copy(update={"trim_start_sec": 0.0, "trim_end_sec": 0.0}))
            continue
        ts, te, stats = _clamp_decision(
            clip, d.trim_start_sec, d.trim_end_sec, level=level
        )
        if stats.hook_protected or stats.min_duration_protected or stats.max_pct_protected:
            logger.info(
                "Clip %s: prune decision clamped (hook=%s min=%s cap=%s) "
                "requested %.2f/%.2f -> applied %.2f/%.2f",
                clip.clip_id,
                stats.hook_protected,
                stats.min_duration_protected,
                stats.max_pct_protected,
                d.trim_start_sec,
                d.trim_end_sec,
                ts,
                te,
            )
        out.append(clip.model_copy(update={"trim_start_sec": ts, "trim_end_sec": te}))
    return out


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _segments_within_clip(transcript: dict, clip: Clip) -> list[dict]:
    """Return transcript segments that overlap the clip window, with times
    expressed as seconds relative to the clip start.
    """
    s0 = clip.start_time_sec
    s1 = clip.end_time_sec
    lines: list[dict] = []
    for seg in transcript.get("segments", []):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start))
        if end <= s0 or start >= s1:
            continue
        rel_start = max(0.0, start - s0)
        rel_end = min(clip.duration_sec, end - s0)
        if rel_end <= rel_start:
            continue
        lines.append(
            {
                "start": rel_start,
                "end": rel_end,
                "text": (seg.get("text") or "").strip(),
            }
        )
    return lines


def _build_user_message(clips: list[Clip], transcript: dict) -> str:
    """Render a compact textual view of every clip for the LLM user turn."""
    blocks: list[str] = []
    for clip in clips:
        seg_lines = _segments_within_clip(transcript, clip)
        header = (
            f"clip_id: {clip.clip_id}\n"
            f"duration_sec: {clip.duration_sec:.2f}\n"
            f"topic: {clip.topic}"
        )
        if clip.hook_start_sec is not None and clip.hook_end_sec is not None:
            header += (
                f"\nhook_window_sec: [{clip.hook_start_sec:.2f}, {clip.hook_end_sec:.2f}]"
            )
        body = "\n".join(
            f"[{seg['start']:.2f}s - {seg['end']:.2f}s] {seg['text']}" for seg in seg_lines
        )
        if not body:
            body = "(no segments overlap this clip window)"
        blocks.append(f"{header}\n---\n{body}")
    return "\n\n===\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _clips_fingerprint(clips: list[Clip]) -> str:
    """Fingerprint the clip *windows* (not trims, so the cache ignores previous
    prune results when deciding whether to re-ask the LLM).
    """
    payload = json.dumps(
        [
            {
                "id": c.clip_id,
                "s": round(c.start_time_sec, 3),
                "e": round(c.end_time_sec, 3),
                "hs": c.hook_start_sec,
                "he": c.hook_end_sec,
            }
            for c in clips
        ],
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resolved_gemini_model(config: PipelineConfig) -> str:
    return (config.gemini_model or GEMINI_MODEL).strip()


def _prune_meta(
    *,
    transcript_fp: str,
    clips_fp: str,
    config: PipelineConfig,
    level: PruneLevel,
) -> dict[str, Any]:
    return {
        "version": PRUNE_META_VERSION,
        "transcript_sha256": transcript_fp,
        "clips_sha256": clips_fp,
        "gemini_model": _resolved_gemini_model(config),
        "prune_level": level,
    }


def _load_cached_clips(work_dir: Path, clips: list[Clip]) -> list[Clip] | None:
    artifact = work_dir / PRUNE_ARTIFACT_FILENAME
    if not artifact.is_file():
        return None
    try:
        with open(artifact, "r", encoding="utf-8") as f:
            data = json.load(f)
        cached = {item["clip_id"]: item for item in data.get("clips", [])}
    except Exception as e:
        logger.warning("Prune cache artifact unreadable (%s); re-running.", e)
        return None
    out: list[Clip] = []
    for clip in clips:
        cached_c = cached.get(clip.clip_id)
        if cached_c is None:
            return None
        out.append(
            clip.model_copy(
                update={
                    "trim_start_sec": float(cached_c.get("trim_start_sec", 0.0)),
                    "trim_end_sec": float(cached_c.get("trim_end_sec", 0.0)),
                }
            )
        )
    return out


def _write_cache(
    work_dir: Path,
    *,
    pruned: list[Clip],
    meta: dict[str, Any],
    raw_response: str,
) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "clips": [
            {
                "clip_id": c.clip_id,
                "trim_start_sec": c.trim_start_sec,
                "trim_end_sec": c.trim_end_sec,
            }
            for c in pruned
        ]
    }
    (work_dir / PRUNE_ARTIFACT_FILENAME).write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (work_dir / PRUNE_RAW_FILENAME).write_text(raw_response, encoding="utf-8")
    with open(work_dir / PRUNE_META_FILENAME, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    logger.info(
        "Wrote %s, %s and %s",
        PRUNE_META_FILENAME,
        PRUNE_ARTIFACT_FILENAME,
        PRUNE_RAW_FILENAME,
    )


def _prune_cache_valid(
    work_dir: Path,
    *,
    transcript_fp: str,
    clips_fp: str,
    config: PipelineConfig,
    level: PruneLevel,
) -> bool:
    meta_path = work_dir / PRUNE_META_FILENAME
    if not meta_path.is_file():
        return False
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return False
    if meta.get("version") != PRUNE_META_VERSION:
        return False
    if meta.get("transcript_sha256") != transcript_fp:
        return False
    if meta.get("clips_sha256") != clips_fp:
        return False
    if meta.get("gemini_model") != _resolved_gemini_model(config):
        return False
    if meta.get("prune_level") != level:
        return False
    return True


# ---------------------------------------------------------------------------
# Gemini call
# ---------------------------------------------------------------------------


def _parse_decisions(raw_json: str) -> list[_PruneDecision]:
    """Parse a raw JSON response into decisions; bare arrays accepted too."""
    data = json.loads(raw_json)
    if isinstance(data, dict) and "decisions" in data:
        try:
            return _PruneResponse.model_validate(data).decisions
        except ValidationError as e:
            logger.warning("Prune response failed validation: %s", e)
            return []
    if isinstance(data, list):
        decisions: list[_PruneDecision] = []
        for item in data:
            try:
                decisions.append(_PruneDecision.model_validate(item))
            except ValidationError:
                continue
        return decisions
    return []


def request_prune_decisions(
    clips: list[Clip],
    transcript: dict,
    *,
    level: PruneLevel,
    gemini_model: str | None = None,
) -> tuple[list[_PruneDecision], str]:
    """Call Gemini for (potentially) one decision per clip.

    Returns ``(decisions, raw_response)``. ``raw_response`` is the literal
    string Gemini returned (cached to ``prune_raw.json`` for audit). On
    transport or parse failure this raises; callers should catch and treat as
    no-op.
    """
    if level == "off" or not clips:
        return [], "{\"decisions\": []}"

    system = content_pruning_system_prompt(
        min_dur=MIN_CLIP_DURATION_SEC,
        max_dur=MAX_CLIP_DURATION_SEC,
        level=level,
    )
    user_text = _build_user_message(clips, transcript)

    model_name = (gemini_model or GEMINI_MODEL).strip()
    client = genai.Client(api_key=resolve_gemini_api_key())

    def _call() -> str:
        logger.info(
            "Gemini content pruning (model=%s, level=%s, clips=%d)...",
            model_name,
            level,
            len(clips),
        )
        response = client.models.generate_content(
            model=model_name,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned empty response text for content pruning")
        return response.text

    raw = _retry_llm("Gemini content pruning", _call)
    decisions = _parse_decisions(raw)
    return decisions, raw


# ---------------------------------------------------------------------------
# Public stage entrypoint (used by pipeline.run_pipeline)
# ---------------------------------------------------------------------------


def run_content_pruning_stage(
    work_dir: Path,
    clips: list[Clip],
    transcript: dict,
    *,
    transcript_fp: str,
    config: PipelineConfig,
) -> list[Clip]:
    """Apply Stage 2.5 pruning to ``clips`` and return the new list.

    - When ``config.prune_level == "off"``, this is a cheap no-op: returns a
      copy of the clips with trim_start/end zeroed.
    - Otherwise, tries the cache first, then calls Gemini. A failing call
      degrades to no-op (the pipeline is never killed by Stage 2.5).
    """
    level = _validated_level(config.prune_level)
    if level == "off":
        logger.info("Content pruning disabled (prune_level=off); skipping Stage 2.5.")
        return [
            clip.model_copy(update={"trim_start_sec": 0.0, "trim_end_sec": 0.0})
            for clip in clips
        ]

    clips_fp = _clips_fingerprint(clips)

    if not config.force_content_pruning and _prune_cache_valid(
        work_dir,
        transcript_fp=transcript_fp,
        clips_fp=clips_fp,
        config=config,
        level=level,
    ):
        cached = _load_cached_clips(work_dir, clips)
        if cached is not None:
            logger.info(
                "Content pruning cache hit (level=%s, %d clips); skipping LLM.",
                level,
                len(clips),
            )
            return cached

    try:
        decisions, raw = request_prune_decisions(
            clips, transcript, level=level, gemini_model=config.gemini_model
        )
    except Exception as e:
        logger.warning(
            "Content pruning call failed (%s); continuing with un-pruned clips.", e
        )
        return [
            clip.model_copy(update={"trim_start_sec": 0.0, "trim_end_sec": 0.0})
            for clip in clips
        ]

    pruned = apply_prune_decisions(clips, decisions, level=level)
    _log_prune_summary(pruned, clips)

    meta = _prune_meta(
        transcript_fp=transcript_fp,
        clips_fp=clips_fp,
        config=config,
        level=level,
    )
    try:
        _write_cache(work_dir, pruned=pruned, meta=meta, raw_response=raw)
    except Exception as e:
        logger.warning("Failed to write prune cache (%s); continuing.", e)
    return pruned


def _validated_level(level: str | None) -> PruneLevel:
    lvl = (level or "balanced").strip().lower()
    if lvl not in VALID_LEVELS:
        logger.warning("Unknown prune_level=%r; falling back to 'balanced'.", level)
        return "balanced"
    return lvl  # type: ignore[return-value]


def _log_prune_summary(pruned: list[Clip], original: list[Clip]) -> None:
    total_before = sum(c.duration_sec for c in original)
    total_after = sum(
        max(0.0, c.duration_sec - c.trim_start_sec - c.trim_end_sec) for c in pruned
    )
    removed = total_before - total_after
    pct = (removed / total_before * 100.0) if total_before > 0 else 0.0
    logger.info(
        "Content pruning done: removed %.1fs across %d clips (%.1f%% of total).",
        removed,
        len(pruned),
        pct,
    )
    for c in pruned:
        if c.trim_start_sec > 0 or c.trim_end_sec > 0:
            final = c.duration_sec - c.trim_start_sec - c.trim_end_sec
            logger.info(
                "  [%s] trim=%.2fs/%.2fs  %.1fs -> %.1fs",
                c.clip_id,
                c.trim_start_sec,
                c.trim_end_sec,
                c.duration_sec,
                final,
            )
