"""Tests for Stage 2.5 content pruning.

No network. The Gemini client is always mocked. These tests cover:

- clamping (max-pct cap, min-duration floor, hook protection)
- decision -> clip mapping (``apply_prune_decisions``)
- prompt construction (clip-relative segments, hook window line)
- ``request_prune_decisions`` ships the right args to the Gemini SDK and
  parses the JSON response
- ``run_content_pruning_stage`` happy path, cache hit, cache invalidation on
  level change, and graceful failure when the LLM blows up
- ``off`` level short-circuits (no call, all trims zero)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from humeo.config import MIN_CLIP_DURATION_SEC, PipelineConfig
from humeo.content_pruning import (
    PRUNE_ARTIFACT_FILENAME,
    PRUNE_META_FILENAME,
    PRUNE_RAW_FILENAME,
    _build_user_message,
    _clamp_decision,
    _clips_fingerprint,
    _parse_decisions,
    _PruneDecision,
    _segments_within_clip,
    apply_prune_decisions,
    request_prune_decisions,
    run_content_pruning_stage,
)
from humeo_core.schemas import Clip


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _clip(
    clip_id: str = "001",
    *,
    start: float = 100.0,
    end: float = 190.0,
    hook_start: float | None = None,
    hook_end: float | None = None,
    topic: str = "topic",
) -> Clip:
    return Clip.model_validate(
        {
            "clip_id": clip_id,
            "topic": topic,
            "start_time_sec": start,
            "end_time_sec": end,
            "hook_start_sec": hook_start,
            "hook_end_sec": hook_end,
        }
    )


def _transcript_for(start: float, end: float, *, step: float = 5.0) -> dict:
    segs = []
    t = start - 3.0
    while t < end + 3.0:
        segs.append({"start": t, "end": t + step, "text": f"text {t:.0f}"})
        t += step
    return {"segments": segs}


@pytest.fixture
def cfg(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        youtube_url="https://youtu.be/abc",
        work_dir=tmp_path,
        gemini_model="gemini-test",
        prune_level="balanced",
    )


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------


def test_clamp_respects_max_pct_balanced():
    clip = _clip(end=200.0)  # duration = 100s
    ts, te, stats = _clamp_decision(clip, 40.0, 10.0, level="balanced")
    assert ts + te == pytest.approx(20.0)  # 20% cap on 100s
    assert stats.max_pct_protected is True


def test_clamp_keeps_minimum_duration():
    clip = _clip(end=160.0)  # duration = 60s; balanced pct cap = 12s
    ts, te, stats = _clamp_decision(clip, 30.0, 30.0, level="aggressive")
    final = clip.duration_sec - ts - te
    assert final >= MIN_CLIP_DURATION_SEC - 1e-6
    assert stats.min_duration_protected is True


def test_clamp_preserves_hook_start_and_end():
    clip = _clip(end=200.0, hook_start=2.0, hook_end=8.0)  # duration 100s
    ts, te, _ = _clamp_decision(clip, 50.0, 50.0, level="aggressive")
    assert ts <= max(0.0, clip.hook_start_sec - 0.24)
    assert te <= max(0.0, clip.duration_sec - clip.hook_end_sec - 0.24)
    final = clip.duration_sec - ts - te
    assert final >= MIN_CLIP_DURATION_SEC - 1e-6


def test_clamp_level_off_nulls_trim():
    clip = _clip(end=200.0)
    ts, te, _ = _clamp_decision(clip, 10.0, 5.0, level="off")
    assert ts == 0.0 and te == 0.0


def test_clamp_negatives_become_zero():
    clip = _clip(end=200.0)
    ts, te, stats = _clamp_decision(clip, -5.0, -2.0, level="balanced")
    assert ts == 0.0 and te == 0.0
    assert stats.clamped_start is True
    assert stats.clamped_end is True


# ---------------------------------------------------------------------------
# apply_prune_decisions
# ---------------------------------------------------------------------------


def test_apply_decisions_maps_by_clip_id():
    a = _clip("001", end=200.0)
    b = _clip("002", start=300.0, end=400.0)
    decisions = [
        _PruneDecision(clip_id="001", trim_start_sec=3.0, trim_end_sec=2.0),
        _PruneDecision(clip_id="002", trim_start_sec=1.0, trim_end_sec=1.0),
    ]
    out = apply_prune_decisions([a, b], decisions, level="balanced")
    assert out[0].trim_start_sec == pytest.approx(3.0)
    assert out[0].trim_end_sec == pytest.approx(2.0)
    assert out[1].trim_start_sec == pytest.approx(1.0)
    assert out[1].trim_end_sec == pytest.approx(1.0)


def test_apply_decisions_missing_id_is_no_op():
    a = _clip("001", end=200.0)
    out = apply_prune_decisions([a], decisions=[], level="balanced")
    assert out[0].trim_start_sec == 0.0
    assert out[0].trim_end_sec == 0.0


def test_apply_decisions_off_level_zeroes_everything():
    a = _clip("001", end=200.0)
    decisions = [_PruneDecision(clip_id="001", trim_start_sec=3.0, trim_end_sec=3.0)]
    out = apply_prune_decisions([a], decisions, level="off")
    assert out[0].trim_start_sec == 0.0
    assert out[0].trim_end_sec == 0.0


# ---------------------------------------------------------------------------
# Prompt / user-message construction
# ---------------------------------------------------------------------------


def test_segments_are_clip_relative():
    clip = _clip(start=100.0, end=190.0)
    transcript = {
        "segments": [
            {"start": 80.0, "end": 95.0, "text": "before"},
            {"start": 100.0, "end": 110.0, "text": "hello"},
            {"start": 150.0, "end": 160.0, "text": "middle"},
            {"start": 190.0, "end": 200.0, "text": "after"},
        ]
    }
    segs = _segments_within_clip(transcript, clip)
    texts = [s["text"] for s in segs]
    assert texts == ["hello", "middle"]
    assert segs[0]["start"] == pytest.approx(0.0)
    assert segs[0]["end"] == pytest.approx(10.0)
    assert segs[1]["start"] == pytest.approx(50.0)
    assert segs[1]["end"] == pytest.approx(60.0)


def test_build_user_message_includes_hook_when_set():
    clip = _clip(start=100.0, end=190.0, hook_start=0.0, hook_end=3.0)
    transcript = _transcript_for(100.0, 190.0)
    msg = _build_user_message([clip], transcript)
    assert "clip_id: 001" in msg
    assert "hook_window_sec" in msg
    assert "[0.00, 3.00]" in msg
    assert "duration_sec: 90.00" in msg


def test_build_user_message_separates_clips():
    clips = [
        _clip("001", start=100.0, end=160.0),
        _clip("002", start=300.0, end=380.0),
    ]
    transcript = _transcript_for(100.0, 380.0)
    msg = _build_user_message(clips, transcript)
    assert "clip_id: 001" in msg
    assert "clip_id: 002" in msg
    assert "===" in msg  # block separator


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def test_parse_decisions_object_form():
    raw = json.dumps(
        {
            "decisions": [
                {"clip_id": "001", "trim_start_sec": 1.2, "trim_end_sec": 0.8, "reason": "ok"}
            ]
        }
    )
    decisions = _parse_decisions(raw)
    assert len(decisions) == 1
    assert decisions[0].clip_id == "001"
    assert decisions[0].trim_start_sec == pytest.approx(1.2)


def test_parse_decisions_array_form():
    raw = json.dumps(
        [{"clip_id": "001", "trim_start_sec": 1.0, "trim_end_sec": 0.0, "reason": "x"}]
    )
    decisions = _parse_decisions(raw)
    assert len(decisions) == 1


def test_parse_decisions_skips_malformed_items_in_array():
    raw = json.dumps(
        [
            {"clip_id": "001", "trim_start_sec": 1.0, "trim_end_sec": 0.0},
            {"not a decision": True},
        ]
    )
    decisions = _parse_decisions(raw)
    assert len(decisions) == 1
    assert decisions[0].clip_id == "001"


# ---------------------------------------------------------------------------
# Gemini call plumbing
# ---------------------------------------------------------------------------


@patch("humeo.content_pruning.genai.Client")
def test_request_prune_decisions_calls_gemini(mock_client_cls, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    mock_inst = MagicMock()
    mock_client_cls.return_value = mock_inst
    mock_inst.models.generate_content.return_value = MagicMock(
        text=json.dumps(
            {
                "decisions": [
                    {"clip_id": "001", "trim_start_sec": 2.0, "trim_end_sec": 1.0, "reason": "r"}
                ]
            }
        )
    )

    clip = _clip("001", end=200.0)
    transcript = _transcript_for(100.0, 200.0)

    decisions, raw = request_prune_decisions(
        [clip], transcript, level="balanced", gemini_model="gemini-x"
    )

    mock_client_cls.assert_called_once_with(api_key="test-key")
    mock_inst.models.generate_content.assert_called_once()
    call_kwargs = mock_inst.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-x"
    assert "clip_id: 001" in call_kwargs["contents"]

    assert len(decisions) == 1
    assert decisions[0].trim_start_sec == pytest.approx(2.0)
    assert json.loads(raw)["decisions"][0]["clip_id"] == "001"


def test_request_prune_decisions_off_level_is_no_op(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    with patch("humeo.content_pruning.genai.Client") as mock_client_cls:
        decisions, raw = request_prune_decisions(
            [_clip()], transcript={"segments": []}, level="off"
        )
        assert decisions == []
        assert json.loads(raw)["decisions"] == []
        mock_client_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Stage entrypoint + cache
# ---------------------------------------------------------------------------


def _mock_gemini_ok(mock_client_cls, *, ts: float = 3.0, te: float = 2.0):
    mock_inst = MagicMock()
    mock_client_cls.return_value = mock_inst
    mock_inst.models.generate_content.return_value = MagicMock(
        text=json.dumps(
            {
                "decisions": [
                    {"clip_id": "001", "trim_start_sec": ts, "trim_end_sec": te, "reason": "ok"}
                ]
            }
        )
    )
    return mock_inst


@patch("humeo.content_pruning.genai.Client")
def test_run_stage_writes_artifacts_and_applies_trims(mock_client_cls, cfg, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    _mock_gemini_ok(mock_client_cls, ts=3.0, te=2.0)

    clip = _clip("001", end=200.0)
    transcript = _transcript_for(100.0, 200.0)

    out = run_content_pruning_stage(
        cfg.work_dir,
        [clip],
        transcript,
        transcript_fp="fp-1",
        config=cfg,
    )

    assert len(out) == 1
    assert out[0].trim_start_sec == pytest.approx(3.0)
    assert out[0].trim_end_sec == pytest.approx(2.0)

    assert (cfg.work_dir / PRUNE_META_FILENAME).is_file()
    assert (cfg.work_dir / PRUNE_ARTIFACT_FILENAME).is_file()
    assert (cfg.work_dir / PRUNE_RAW_FILENAME).is_file()
    meta = json.loads((cfg.work_dir / PRUNE_META_FILENAME).read_text())
    assert meta["prune_level"] == "balanced"
    assert meta["transcript_sha256"] == "fp-1"


@patch("humeo.content_pruning.genai.Client")
def test_run_stage_is_cached_on_second_call(mock_client_cls, cfg, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    mock_inst = _mock_gemini_ok(mock_client_cls, ts=3.0, te=2.0)

    clip = _clip("001", end=200.0)
    transcript = _transcript_for(100.0, 200.0)

    run_content_pruning_stage(cfg.work_dir, [clip], transcript, transcript_fp="fp", config=cfg)
    assert mock_inst.models.generate_content.call_count == 1

    out2 = run_content_pruning_stage(
        cfg.work_dir, [clip], transcript, transcript_fp="fp", config=cfg
    )
    assert mock_inst.models.generate_content.call_count == 1  # still 1 -> cache hit
    assert out2[0].trim_start_sec == pytest.approx(3.0)


@patch("humeo.content_pruning.genai.Client")
def test_run_stage_cache_invalidates_on_level_change(mock_client_cls, cfg, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    mock_inst = _mock_gemini_ok(mock_client_cls, ts=3.0, te=2.0)

    clip = _clip("001", end=200.0)
    transcript = _transcript_for(100.0, 200.0)

    run_content_pruning_stage(cfg.work_dir, [clip], transcript, transcript_fp="fp", config=cfg)
    assert mock_inst.models.generate_content.call_count == 1

    cfg2 = PipelineConfig(
        youtube_url=cfg.youtube_url,
        work_dir=cfg.work_dir,
        gemini_model=cfg.gemini_model,
        prune_level="aggressive",
    )
    run_content_pruning_stage(
        cfg2.work_dir, [clip], transcript, transcript_fp="fp", config=cfg2
    )
    assert mock_inst.models.generate_content.call_count == 2


@patch("humeo.content_pruning.genai.Client")
def test_run_stage_off_level_short_circuits(mock_client_cls, tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    cfg = PipelineConfig(
        youtube_url="https://youtu.be/abc",
        work_dir=tmp_path,
        gemini_model="gemini-test",
        prune_level="off",
    )
    clip = _clip("001", end=200.0)
    out = run_content_pruning_stage(
        cfg.work_dir, [clip], _transcript_for(100.0, 200.0), transcript_fp="fp", config=cfg
    )
    assert out[0].trim_start_sec == 0.0
    assert out[0].trim_end_sec == 0.0
    mock_client_cls.assert_not_called()
    assert not (cfg.work_dir / PRUNE_META_FILENAME).exists()


@patch("humeo.content_pruning.genai.Client")
def test_run_stage_swallows_llm_errors(mock_client_cls, cfg, monkeypatch, caplog):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    mock_inst = MagicMock()
    mock_client_cls.return_value = mock_inst
    mock_inst.models.generate_content.side_effect = RuntimeError("boom")

    clip = _clip("001", end=200.0)
    transcript = _transcript_for(100.0, 200.0)

    with caplog.at_level("WARNING", logger="humeo.content_pruning"):
        out = run_content_pruning_stage(
            cfg.work_dir, [clip], transcript, transcript_fp="fp", config=cfg
        )
    assert out[0].trim_start_sec == 0.0
    assert out[0].trim_end_sec == 0.0
    assert any("Content pruning call failed" in r.message for r in caplog.records)


@patch("humeo.content_pruning.genai.Client")
def test_run_stage_force_bypasses_cache(mock_client_cls, cfg, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    mock_inst = _mock_gemini_ok(mock_client_cls, ts=3.0, te=2.0)
    clip = _clip("001", end=200.0)
    transcript = _transcript_for(100.0, 200.0)

    run_content_pruning_stage(cfg.work_dir, [clip], transcript, transcript_fp="fp", config=cfg)
    assert mock_inst.models.generate_content.call_count == 1

    cfg_force = PipelineConfig(
        youtube_url=cfg.youtube_url,
        work_dir=cfg.work_dir,
        gemini_model=cfg.gemini_model,
        prune_level=cfg.prune_level,
        force_content_pruning=True,
    )
    run_content_pruning_stage(
        cfg_force.work_dir, [clip], transcript, transcript_fp="fp", config=cfg_force
    )
    assert mock_inst.models.generate_content.call_count == 2


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


def test_clips_fingerprint_is_trim_independent():
    a = _clip("001", end=200.0)
    b = a.model_copy(update={"trim_start_sec": 5.0, "trim_end_sec": 3.0})
    assert _clips_fingerprint([a]) == _clips_fingerprint([b])


def test_clips_fingerprint_changes_on_window_change():
    a = _clip("001", end=200.0)
    b = _clip("001", end=201.0)
    assert _clips_fingerprint([a]) != _clips_fingerprint([b])
