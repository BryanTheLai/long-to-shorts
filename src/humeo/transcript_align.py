"""Map source-timeline ASR words to per-clip subtitle timings (t=0 at clip in-point)."""

from __future__ import annotations

from humeo_mcp.schemas import Clip, ClipSubtitleWords, TranscriptWord

# Whisper / WhisperX / OpenAI-normalized segment shapes
_MAX_WORDS_PER_CUE = 8
_MAX_CUE_SEC = 4.0


def _iter_words_from_segments(transcript: dict) -> list[TranscriptWord]:
    out: list[TranscriptWord] = []
    for seg in transcript.get("segments", []) or []:
        words = seg.get("words") or []
        if words:
            for raw in words:
                w = str(raw.get("word", "")).strip()
                if not w:
                    continue
                out.append(
                    TranscriptWord(
                        word=w,
                        start_time=float(raw["start"]),
                        end_time=float(raw["end"]),
                    )
                )
            continue
        # Segment-level only (no word list): treat whole segment as one token
        text = str(seg.get("text", "")).strip()
        if text:
            out.append(
                TranscriptWord(
                    word=text,
                    start_time=float(seg.get("start", 0.0)),
                    end_time=float(seg.get("end", 0.0)),
                )
            )
    return out


def clip_subtitle_words(transcript: dict, clip: Clip) -> ClipSubtitleWords:
    """Words overlapping ``clip`` with times shifted to start at 0 (clip-local)."""
    clip_start = clip.start_time_sec
    clip_end = clip.end_time_sec
    words = _iter_words_from_segments(transcript)
    local: list[TranscriptWord] = []
    for w in words:
        if w.end_time <= clip_start or w.start_time >= clip_end:
            continue
        t0 = max(w.start_time, clip_start) - clip_start
        t1 = min(w.end_time, clip_end) - clip_start
        if t1 <= t0:
            continue
        local.append(TranscriptWord(word=w.word, start_time=t0, end_time=t1))

    if local:
        return ClipSubtitleWords(words=local)

    return ClipSubtitleWords(words=_fallback_even_words(clip))


def _fallback_even_words(clip: Clip) -> list[TranscriptWord]:
    """Even split over clip duration when no word timestamps exist."""
    text = (clip.transcript or "").strip()
    if not text:
        return []
    parts = text.split()
    if not parts:
        return []
    d = clip.duration_sec
    step = d / len(parts)
    out: list[TranscriptWord] = []
    for i, p in enumerate(parts):
        out.append(
            TranscriptWord(
                word=p,
                start_time=i * step,
                end_time=(i + 1) * step if i < len(parts) - 1 else d,
            )
        )
    return out


def clip_words_to_srt_lines(words: list[TranscriptWord]) -> list[tuple[float, float, str]]:
    """Group words into SRT cues: max N words and max duration per cue."""
    if not words:
        return []
    lines: list[tuple[float, float, str]] = []
    i = 0
    n = len(words)
    while i < n:
        chunk: list[TranscriptWord] = [words[i]]
        t0 = words[i].start_time
        end_t = words[i].end_time
        j = i + 1
        while j < n:
            w = words[j]
            if len(chunk) >= _MAX_WORDS_PER_CUE:
                break
            if w.start_time - t0 > _MAX_CUE_SEC:
                break
            chunk.append(w)
            end_t = w.end_time
            j += 1
        text = " ".join(w.word for w in chunk)
        lines.append((t0, end_t, text))
        i = j
    return lines


def format_srt(lines: list[tuple[float, float, str]]) -> str:
    blocks: list[str] = []
    for idx, (start, end, text) in enumerate(lines, start=1):
        blocks.append(
            f"{idx}\n{_fmt_time(start)} --> {_fmt_time(end)}\n{text}\n"
        )
    return "\n".join(blocks)


def _fmt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
