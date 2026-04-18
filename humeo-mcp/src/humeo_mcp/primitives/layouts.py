"""The 3 thrusters — fixed 9:16 layout math.

First principles: this specific video format only ever has three on-screen
geometries. We do NOT need a general subject-tracker ML model. We do need
three deterministic crop/compose recipes that any MCP client can invoke.

Each layout returns a pure ``ffmpeg -filter_complex`` fragment plus the
output video label. The compiler glues them together with the cut + audio
chain. Keeping this pure makes the whole thing unit-testable without running
ffmpeg (the ``build_filtergraph`` functions are deterministic strings).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import BoundingBox, FocusStackOrder, LayoutInstruction, LayoutKind


# Source geometry assumption. Most podcast sources are 1920x1080; we still
# normalize everything by the actual source size so changing this is safe.
DEFAULT_SRC_W = 1920
DEFAULT_SRC_H = 1080


@dataclass(frozen=True)
class FilterPlan:
    """Result of planning a layout.

    ``filtergraph`` is the body of ``-filter_complex`` and ends with
    ``[vout]`` as the final labelled stream.
    """

    filtergraph: str
    out_label: str = "vout"


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _bbox_to_crop_pixels(
    box: BoundingBox, src_w: int, src_h: int
) -> tuple[int, int, int, int]:
    """Normalized bbox → (cw, ch, x, y) with even dimensions for ffmpeg."""
    x1 = int(round(_clamp01(box.x1) * float(src_w)))
    y1 = int(round(_clamp01(box.y1) * float(src_h)))
    x2 = int(round(_clamp01(box.x2) * float(src_w)))
    y2 = int(round(_clamp01(box.y2) * float(src_h)))
    x1 = max(0, min(src_w - 2, x1))
    y1 = max(0, min(src_h - 2, y1))
    x2 = max(x1 + 2, min(src_w, x2))
    y2 = max(y1 + 2, min(src_h, y2))
    cw = x2 - x1
    ch = y2 - y1
    cw -= cw % 2
    ch -= ch % 2
    x1 -= x1 % 2
    y1 -= y1 % 2
    return max(2, cw), max(2, ch), x1, y1


def _crop_box(
    src_w: int,
    src_h: int,
    target_aspect: float,
    zoom: float,
    center_x_norm: float,
    center_y_norm: float = 0.5,
) -> tuple[int, int, int, int]:
    """Return (cw, ch, x, y) crop values for a centered aspect-ratio crop.

    ``zoom`` > 1 means tighter crop (smaller window around the center).
    The function always keeps the crop window fully inside the source frame.
    """

    zoom = max(1.0, zoom)
    # Start by fitting the widest possible window of the target aspect inside src.
    if src_w / src_h >= target_aspect:
        # Source is wider than target; window is height-limited.
        base_ch = src_h
        base_cw = int(round(base_ch * target_aspect))
    else:
        base_cw = src_w
        base_ch = int(round(base_cw / target_aspect))

    cw = max(2, int(round(base_cw / zoom)))
    ch = max(2, int(round(base_ch / zoom)))
    # ffmpeg 'crop' requires even dimensions for most encoders.
    cw -= cw % 2
    ch -= ch % 2

    cx = int(round(_clamp01(center_x_norm) * src_w))
    cy = int(round(_clamp01(center_y_norm) * src_h))
    x = max(0, min(src_w - cw, cx - cw // 2))
    y = max(0, min(src_h - ch, cy - ch // 2))
    x -= x % 2
    y -= y % 2
    return cw, ch, x, y


def _center_crop_to_9x16(
    src_w: int, src_h: int, zoom: float, person_x_norm: float
) -> tuple[int, int, int, int]:
    return _crop_box(src_w, src_h, 9 / 16, zoom, person_x_norm, 0.5)


# ---------------------------------------------------------------------------
# Layout builders
# ---------------------------------------------------------------------------


def plan_zoom_call_center(
    instruction: LayoutInstruction,
    *,
    out_w: int,
    out_h: int,
    src_w: int = DEFAULT_SRC_W,
    src_h: int = DEFAULT_SRC_H,
) -> FilterPlan:
    """Thruster 1: zoom-call subject centered, tight crop (zoom >= 1.25 default)."""

    zoom = max(instruction.zoom, 1.25)
    cw, ch, x, y = _center_crop_to_9x16(src_w, src_h, zoom, instruction.person_x_norm)
    fg = (
        f"[0:v]crop={cw}:{ch}:{x}:{y},"
        f"scale={out_w}:{out_h}:flags=lanczos,setsar=1[vout]"
    )
    return FilterPlan(filtergraph=fg)


def plan_sit_center(
    instruction: LayoutInstruction,
    *,
    out_w: int,
    out_h: int,
    src_w: int = DEFAULT_SRC_W,
    src_h: int = DEFAULT_SRC_H,
) -> FilterPlan:
    """Thruster 2: 1-person sitting, centered, wider crop (zoom ~1.0).

    Vertical crop center is slightly above mid-frame (0.48) so typical
    lower-third / seated framing keeps faces higher in the 9:16 window.
    """

    zoom = max(instruction.zoom, 1.0)
    cw, ch, x, y = _crop_box(
        src_w, src_h, 9 / 16, zoom, instruction.person_x_norm, 0.48
    )
    fg = (
        f"[0:v]crop={cw}:{ch}:{x}:{y},"
        f"scale={out_w}:{out_h}:flags=lanczos,setsar=1[vout]"
    )
    return FilterPlan(filtergraph=fg)


def plan_split_chart_person(
    instruction: LayoutInstruction,
    *,
    out_w: int,
    out_h: int,
    src_w: int = DEFAULT_SRC_W,
    src_h: int = DEFAULT_SRC_H,
) -> FilterPlan:
    """Thruster 3: explainer scene — chart left 2/3, person right 1/3 in source.

    The 9:16 output stacks them vertically:
      top 60%  -> chart region scaled to full width
      bottom 40% -> person region scaled to full width

    **Important:** When ``split_chart_region`` and ``split_person_region`` are set
    (Gemini vision), those normalized rects define crops. Otherwise the chart and
    person rectangles are **non-overlapping** strips of the source:
    ``x in [0, left_split)`` for the chart and ``x in [left_split, src_w)`` for the person.
    """

    # Top band height (chart) and bottom band height (person).
    top_h = int(round(out_h * 0.6))
    bot_h = out_h - top_h
    top_h -= top_h % 2
    bot_h = out_h - top_h

    if instruction.split_chart_region and instruction.split_person_region:
        chart_w, chart_h, chart_start_x, chart_y = _bbox_to_crop_pixels(
            instruction.split_chart_region, src_w, src_h
        )
        person_w, person_h, person_x, person_y = _bbox_to_crop_pixels(
            instruction.split_person_region, src_w, src_h
        )
        band_chart_top = (
            f"[src1]crop={chart_w}:{chart_h}:{chart_start_x}:{chart_y},"
            f"scale={out_w}:{top_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{top_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[top]"
        )
        band_chart_bot = (
            f"[src1]crop={chart_w}:{chart_h}:{chart_start_x}:{chart_y},"
            f"scale={out_w}:{bot_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{bot_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[cbot]"
        )
        band_person_top = (
            f"[src2]crop={person_w}:{person_h}:{person_x}:{person_y},"
            f"scale={out_w}:{top_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{top_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[ptop]"
        )
        band_person_bot = (
            f"[src2]crop={person_w}:{person_h}:{person_x}:{person_y},"
            f"scale={out_w}:{bot_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{bot_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[bot]"
        )
        if instruction.focus_stack_order == FocusStackOrder.CHART_THEN_PERSON:
            fg = (
                f"[0:v]split=2[src1][src2];"
                f"{band_chart_top};"
                f"{band_person_bot};"
                f"[top][bot]vstack=inputs=2[vout]"
            )
        else:
            fg = (
                f"[0:v]split=2[src1][src2];"
                f"{band_person_top};"
                f"{band_chart_bot};"
                f"[ptop][cbot]vstack=inputs=2[vout]"
            )
        return FilterPlan(filtergraph=fg)

    # Vertical boundary between chart (left 2/3) and person (right 1/3).
    left_split = int(round((2.0 / 3.0) * float(src_w)))
    left_split -= left_split % 2
    left_split = max(2, min(src_w - 2, left_split))

    # Chart: only the left region. ``chart_x_norm`` trims from the left edge [0, left_split).
    chart_start_x = int(round(_clamp01(instruction.chart_x_norm) * float(left_split)))
    chart_start_x -= chart_start_x % 2
    chart_start_x = max(0, min(left_split - 2, chart_start_x))
    chart_w = left_split - chart_start_x
    chart_w -= chart_w % 2
    chart_h = src_h - (src_h % 2)

    # Person: only the right third — never overlaps the chart strip.
    person_x = left_split
    person_x -= person_x % 2
    person_w = src_w - person_x
    person_w -= person_w % 2
    person_h = src_h - (src_h % 2)

    band_chart_top = (
        f"[src1]crop={chart_w}:{chart_h}:{chart_start_x}:0,"
        f"scale={out_w}:{top_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{top_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[top]"
    )
    band_chart_bot = (
        f"[src1]crop={chart_w}:{chart_h}:{chart_start_x}:0,"
        f"scale={out_w}:{bot_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{bot_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[cbot]"
    )
    # Match chart bands: decrease + pad (avoids "zoomed" crop that duplicated chart look).
    band_person_top = (
        f"[src2]crop={person_w}:{person_h}:{person_x}:0,"
        f"scale={out_w}:{top_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{top_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[ptop]"
    )
    band_person_bot = (
        f"[src2]crop={person_w}:{person_h}:{person_x}:0,"
        f"scale={out_w}:{bot_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{bot_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[bot]"
    )

    if instruction.focus_stack_order == FocusStackOrder.CHART_THEN_PERSON:
        fg = (
            f"[0:v]split=2[src1][src2];"
            f"{band_chart_top};"
            f"{band_person_bot};"
            f"[top][bot]vstack=inputs=2[vout]"
        )
    else:
        fg = (
            f"[0:v]split=2[src1][src2];"
            f"{band_person_top};"
            f"{band_chart_bot};"
            f"[ptop][cbot]vstack=inputs=2[vout]"
        )

    return FilterPlan(filtergraph=fg)


_DISPATCH = {
    LayoutKind.ZOOM_CALL_CENTER: plan_zoom_call_center,
    LayoutKind.SIT_CENTER: plan_sit_center,
    LayoutKind.SPLIT_CHART_PERSON: plan_split_chart_person,
}


def plan_layout(
    instruction: LayoutInstruction,
    *,
    out_w: int = 1080,
    out_h: int = 1920,
    src_w: int = DEFAULT_SRC_W,
    src_h: int = DEFAULT_SRC_H,
) -> FilterPlan:
    """Dispatch to one of the 3 thrusters.

    Exhaustive over ``LayoutKind`` — adding a new layout requires adding a
    planner above AND an entry in ``_DISPATCH``.
    """

    fn = _DISPATCH.get(instruction.layout)
    if fn is None:
        # Should be unreachable thanks to Pydantic + Enum, but guard anyway.
        raise ValueError(f"Unknown layout: {instruction.layout!r}")
    return fn(instruction, out_w=out_w, out_h=out_h, src_w=src_w, src_h=src_h)
