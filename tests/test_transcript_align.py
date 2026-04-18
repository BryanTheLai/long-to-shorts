"""Word-level subtitle alignment for the product pipeline."""

import pytest

from humeo.transcript_align import (
    clip_subtitle_words,
    clip_words_to_srt_lines,
    format_srt,
)
from humeo_mcp.schemas import Clip, TranscriptWord


def test_clip_subtitle_words_shifts_to_clip_local():
    transcript = {
        "segments": [
            {
                "start": 100.0,
                "end": 102.0,
                "text": "one two",
                "words": [
                    {"word": "one", "start": 100.0, "end": 100.5},
                    {"word": "two", "start": 100.6, "end": 101.2},
                ],
            }
        ]
    }
    clip = Clip(
        clip_id="1",
        topic="t",
        start_time_sec=100.0,
        end_time_sec=101.5,
        transcript="one two",
    )
    aligned = clip_subtitle_words(transcript, clip)
    assert len(aligned.words) == 2
    assert aligned.words[0].word == "one"
    assert aligned.words[0].start_time == 0.0
    assert aligned.words[1].start_time == pytest.approx(0.6)


def test_clip_words_to_srt_lines_groups():
    words = [
        TranscriptWord(word=str(i), start_time=i * 0.1, end_time=(i + 1) * 0.1)
        for i in range(10)
    ]
    lines = clip_words_to_srt_lines(words)
    assert len(lines) == 2
    assert lines[0][2].startswith("0 1 2 3 4 5 6 7")


def test_format_srt_roundtrip_single_line():
    s = format_srt([(0.0, 1.0, "hello")])
    assert "00:00:00,000 --> 00:00:01,000" in s
    assert "hello" in s
