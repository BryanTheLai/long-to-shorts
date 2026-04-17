"""Subtitle helpers for the product pipeline."""

import logging
from pathlib import Path

from humeo_mcp.schemas import Clip

logger = logging.getLogger(__name__)


def generate_srt(clip: Clip, output_dir: Path) -> Path:
    """
    Generate an SRT subtitle file from the clip's transcript.

    For MVP, creates a single subtitle block for the entire clip.
    WhisperX word-level timestamps can be used later for karaoke-style subs.
    """
    srt_path = output_dir / f"clip_{clip.clip_id}.srt"

    # Split transcript into chunks of ~10 words for readable subtitles
    words = clip.transcript.split()
    chunks = []
    chunk_size = 8  # words per subtitle line
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i : i + chunk_size]))

    # Distribute chunks evenly across the clip duration
    chunk_duration = clip.duration_sec / max(len(chunks), 1)

    lines = []
    for idx, chunk in enumerate(chunks):
        start_sec = idx * chunk_duration
        end_sec = min((idx + 1) * chunk_duration, clip.duration_sec)
        lines.append(str(idx + 1))
        lines.append(f"{_format_srt_time(start_sec)} --> {_format_srt_time(end_sec)}")
        lines.append(chunk)
        lines.append("")  # blank line separator

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Generated SRT: %s (%d subtitle blocks)", srt_path, len(chunks))
    return srt_path


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


