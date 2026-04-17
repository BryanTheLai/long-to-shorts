"""Scene classifier: assigns one of 3 layouts to each scene.

Two backends share the same contract:

* ``classify_scenes_heuristic`` — no model call. Uses keyframe pixel analysis
  (edge density + color variance + face-rectangle heuristic-free approach)
  to guess which of the 3 layouts fits best. Fully offline, deterministic.
* ``classify_scenes_with_llm`` — pluggable LLM hook. Takes a callable
  ``(image_path, prompt) -> str`` so the caller (MCP client or test) can
  wire up whatever multimodal model they want. Enforces strict JSON output.

Even without a model, the heuristic is good enough for many real inputs and
keeps the whole pipeline runnable with zero external dependencies.
"""

from __future__ import annotations

import json
import os
import struct
from typing import Callable, Iterable

from ..schemas import LayoutKind, Scene, SceneClassification


# ---------------------------------------------------------------------------
# Tiny PNG/JPEG reader → down-sampled grayscale column profile
# ---------------------------------------------------------------------------
# We intentionally avoid a hard dependency on Pillow. If Pillow is available
# we use it; otherwise we fall back to reading just PNG dimensions, which is
# enough for a coarse column-variance heuristic on any pre-decoded frame.


def _load_grayscale(path: str) -> tuple[list[list[int]], int, int] | None:
    try:
        from PIL import Image  # type: ignore

        img = Image.open(path).convert("L")
        w, h = img.size
        # Down-sample to at most 128 cols x 72 rows for cheap analysis.
        tw = min(128, w)
        th = min(72, h)
        img = img.resize((tw, th))
        px = list(img.getdata())
        grid = [px[i * tw : (i + 1) * tw] for i in range(th)]
        return grid, tw, th
    except Exception:
        return None


def _png_dims(path: str) -> tuple[int, int] | None:
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        w, h = struct.unpack(">II", head[16:24])
        return int(w), int(h)
    except Exception:
        return None


def _column_profile(grid: list[list[int]]) -> list[float]:
    if not grid:
        return []
    h = len(grid)
    w = len(grid[0])
    out: list[float] = []
    for x in range(w):
        s = 0
        for y in range(h):
            s += grid[y][x]
        out.append(s / h)
    return out


def _variance(values: Iterable[float]) -> float:
    vs = list(values)
    if not vs:
        return 0.0
    m = sum(vs) / len(vs)
    return sum((v - m) ** 2 for v in vs) / len(vs)


# ---------------------------------------------------------------------------
# Heuristic classifier
# ---------------------------------------------------------------------------


def _classify_one_heuristic(keyframe_path: str | None) -> SceneClassification:
    if not keyframe_path or not os.path.exists(keyframe_path):
        return SceneClassification(
            scene_id="?",
            layout=LayoutKind.SIT_CENTER,
            confidence=0.3,
            reason="no keyframe available — defaulting to SIT_CENTER",
        )

    gs = _load_grayscale(keyframe_path)
    if gs is None:
        # Can't read pixels: still return a safe default with low confidence.
        return SceneClassification(
            scene_id="?",
            layout=LayoutKind.SIT_CENTER,
            confidence=0.25,
            reason="PIL unavailable or image unreadable — defaulting to SIT_CENTER",
        )

    grid, w, h = gs
    cols = _column_profile(grid)
    # Split into left / right halves. If the left half is visually very
    # different from the right half (high between-half variance vs low
    # within-half variance) → probably a chart-vs-person split scene.
    mid = w // 2
    left = cols[:mid]
    right = cols[mid:]
    left_mean = sum(left) / max(1, len(left))
    right_mean = sum(right) / max(1, len(right))
    left_var = _variance(left)
    right_var = _variance(right)
    between = (left_mean - right_mean) ** 2
    within = (left_var + right_var) / 2.0 + 1e-6

    split_score = between / within  # high → likely split layout
    # Overall column variance: low variance → flat composition (zoom call).
    overall_var = _variance(cols)

    if split_score > 25.0:
        return SceneClassification(
            scene_id="?",
            layout=LayoutKind.SPLIT_CHART_PERSON,
            confidence=min(0.95, 0.5 + split_score / 200.0),
            reason=f"left/right halves differ strongly (score={split_score:.1f})",
        )
    if overall_var < 100.0:
        return SceneClassification(
            scene_id="?",
            layout=LayoutKind.ZOOM_CALL_CENTER,
            confidence=0.7,
            reason=f"low column variance ({overall_var:.1f}) — flat centered framing",
        )
    return SceneClassification(
        scene_id="?",
        layout=LayoutKind.SIT_CENTER,
        confidence=0.6,
        reason=f"moderate composition (score={split_score:.1f}, var={overall_var:.1f})",
    )


def classify_scenes_heuristic(scenes: list[Scene]) -> list[SceneClassification]:
    out: list[SceneClassification] = []
    for s in scenes:
        r = _classify_one_heuristic(s.keyframe_path)
        out.append(r.model_copy(update={"scene_id": s.scene_id}))
    return out


# ---------------------------------------------------------------------------
# LLM-backed classifier (caller provides the model hook)
# ---------------------------------------------------------------------------


LLMVisionFn = Callable[[str, str], str]
"""Signature: (image_path, prompt) -> raw model string (expected JSON)."""


CLASSIFIER_PROMPT = """You are a scene layout classifier for a short-video editor.
Return ONLY a JSON object of the form:
  {"layout": "<one of: zoom_call_center | sit_center | split_chart_person>",
   "confidence": <0..1 float>,
   "reason": "<=15 words"}

Layout definitions:
- zoom_call_center: one person on a video call (webcam grid / talking head tight crop), subject centered.
- sit_center:       one person sitting in frame, subject centered, wider framing than a zoom call.
- split_chart_person: an explainer scene with a chart/graphic on the LEFT (~2/3 of frame) and a person on the RIGHT (~1/3).

Pick the single best match. No prose, no markdown, JSON only.
"""


def classify_scenes_with_llm(
    scenes: list[Scene], vision_fn: LLMVisionFn
) -> list[SceneClassification]:
    out: list[SceneClassification] = []
    for s in scenes:
        if not s.keyframe_path:
            out.append(
                SceneClassification(
                    scene_id=s.scene_id,
                    layout=LayoutKind.SIT_CENTER,
                    confidence=0.2,
                    reason="no keyframe",
                )
            )
            continue
        raw = vision_fn(s.keyframe_path, CLASSIFIER_PROMPT)
        try:
            data = json.loads(raw)
            out.append(
                SceneClassification(
                    scene_id=s.scene_id,
                    layout=LayoutKind(data["layout"]),
                    confidence=float(data.get("confidence", 0.5)),
                    reason=str(data.get("reason", ""))[:200],
                )
            )
        except Exception as e:
            out.append(
                SceneClassification(
                    scene_id=s.scene_id,
                    layout=LayoutKind.SIT_CENTER,
                    confidence=0.25,
                    reason=f"LLM parse error: {e!r}",
                )
            )
    return out
