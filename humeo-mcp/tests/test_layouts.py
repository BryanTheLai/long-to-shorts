import pytest

from humeo_mcp.primitives.layouts import (
    DEFAULT_SRC_H,
    DEFAULT_SRC_W,
    _center_crop_to_9x16,
    _crop_box,
    plan_layout,
)
from humeo_mcp.schemas import LayoutInstruction, LayoutKind


def test_crop_box_aspect_exact():
    cw, ch, x, y = _crop_box(1920, 1080, 9 / 16, 1.0, 0.5, 0.5)
    # 9:16 inside 1920x1080 -> height-limited: ch=1080, cw ~= 608
    assert ch == 1080
    assert abs(cw / ch - 9 / 16) < 0.01
    assert 0 <= x <= 1920 - cw
    assert y == 0


def test_crop_box_clamps_inside_frame():
    cw, ch, x, y = _crop_box(1920, 1080, 9 / 16, 2.0, 0.99, 0.5)
    assert x + cw <= 1920
    assert y + ch <= 1080


def test_crop_box_zoom_tightens():
    cw_small, ch_small, _, _ = _center_crop_to_9x16(1920, 1080, 2.0, 0.5)
    cw_large, ch_large, _, _ = _center_crop_to_9x16(1920, 1080, 1.0, 0.5)
    assert cw_small < cw_large
    assert ch_small < ch_large


def test_even_dimensions():
    cw, ch, x, y = _crop_box(1921, 1081, 9 / 16, 1.3, 0.4, 0.5)
    assert cw % 2 == 0 and ch % 2 == 0
    assert x % 2 == 0 and y % 2 == 0


def _contains(s: str, *subs: str) -> bool:
    return all(sub in s for sub in subs)


def test_zoom_call_layout_filtergraph_shape():
    instr = LayoutInstruction(
        clip_id="c", layout=LayoutKind.ZOOM_CALL_CENTER, zoom=1.5, person_x_norm=0.5
    )
    plan = plan_layout(instr, out_w=1080, out_h=1920)
    fg = plan.filtergraph
    assert _contains(fg, "[0:v]crop=", "scale=1080:1920", "[vout]")


def test_sit_center_layout_filtergraph_shape():
    instr = LayoutInstruction(clip_id="c", layout=LayoutKind.SIT_CENTER)
    plan = plan_layout(instr, out_w=1080, out_h=1920)
    assert "[vout]" in plan.filtergraph
    assert plan.out_label == "vout"


def test_split_layout_contains_vstack():
    instr = LayoutInstruction(
        clip_id="c",
        layout=LayoutKind.SPLIT_CHART_PERSON,
        person_x_norm=0.83,
        chart_x_norm=0.0,
    )
    plan = plan_layout(instr, out_w=1080, out_h=1920)
    fg = plan.filtergraph
    assert _contains(fg, "split=2", "vstack=inputs=2", "[vout]")
    assert "[top]" in fg and "[bot]" in fg


def test_split_layout_person_clamped():
    instr = LayoutInstruction(
        clip_id="c", layout=LayoutKind.SPLIT_CHART_PERSON, person_x_norm=1.0
    )
    plan = plan_layout(instr, out_w=1080, out_h=1920)
    assert "crop=" in plan.filtergraph  # no OOB math crash


def test_plan_layout_dispatch_covers_all_kinds():
    for k in LayoutKind:
        instr = LayoutInstruction(clip_id="c", layout=k)
        plan = plan_layout(instr)
        assert plan.out_label == "vout"
        assert plan.filtergraph.endswith("[vout]")


def test_zoom_tighter_means_smaller_crop_window():
    from humeo_mcp.primitives.layouts import plan_zoom_call_center

    wide = plan_zoom_call_center(
        LayoutInstruction(clip_id="c", layout=LayoutKind.ZOOM_CALL_CENTER, zoom=1.0),
        out_w=1080,
        out_h=1920,
    )
    tight = plan_zoom_call_center(
        LayoutInstruction(clip_id="c", layout=LayoutKind.ZOOM_CALL_CENTER, zoom=2.0),
        out_w=1080,
        out_h=1920,
    )
    # Parse crop=CW:CH:X:Y out of each filtergraph.
    import re

    def crop(fg: str) -> tuple[int, int]:
        m = re.search(r"crop=(\d+):(\d+):", fg)
        assert m is not None
        return int(m.group(1)), int(m.group(2))

    wcw, wch = crop(wide.filtergraph)
    tcw, tch = crop(tight.filtergraph)
    assert tcw < wcw and tch < wch
