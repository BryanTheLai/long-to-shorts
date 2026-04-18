"""Subtitle helpers for the product pipeline."""

import logging
from pathlib import Path

from humeo_mcp.schemas import Clip

from humeo.transcript_align import clip_subtitle_words, clip_words_to_srt_lines, format_srt

logger = logging.getLogger(__name__)


def generate_srt(clip: Clip, transcript: dict, output_dir: Path) -> Path:
    """
    Build an SRT file from word-level ASR aligned to this clip's timeline.

    ``transcript`` is the persisted ``transcript.json`` (segments with optional
    per-word timestamps). Times are shifted so 0 = clip in-point.
    """
    srt_path = output_dir / f"clip_{clip.clip_id}.srt"
    aligned = clip_subtitle_words(transcript, clip)
    lines = clip_words_to_srt_lines(aligned.words)
    srt_path.write_text(format_srt(lines), encoding="utf-8")
    logger.info("Generated SRT: %s (%d cues)", srt_path, len(lines))
    return srt_path
