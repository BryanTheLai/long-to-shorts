"""Exercise the MCP server tools as plain Python callables.

FastMCP tools are registered on the server instance, but the underlying
functions are ordinary Python functions decorated with ``@mcp.tool()``.
We import the module and invoke those functions directly to verify the
end-to-end wiring (schemas validated, dispatch correct, JSON-serializable).
"""

import humeo_mcp.server as srv
from humeo_mcp.schemas import LayoutKind


def test_list_layouts_lists_all_three():
    result = srv.list_layouts()
    kinds = {layout["kind"] for layout in result["layouts"]}
    assert kinds == {k.value for k in LayoutKind}


def test_plan_layout_tool_returns_filtergraph():
    for k in LayoutKind:
        out = srv.plan_layout(layout=k.value)
        assert out["out_label"] == "vout"
        assert "[vout]" in out["filtergraph"]


def test_build_render_cmd_dry_run():
    req = {
        "source_path": "/tmp/src.mp4",
        "clip": {
            "clip_id": "1",
            "topic": "t",
            "start_time_sec": 0.0,
            "end_time_sec": 30.0,
        },
        "layout": {"clip_id": "1", "layout": LayoutKind.SIT_CENTER.value},
        "output_path": "/tmp/out.mp4",
    }
    out = srv.build_render_cmd(request=req)
    assert out["success"] is True
    assert out["output_path"] == "/tmp/out.mp4"
    assert any("-filter_complex" == part for part in out["ffmpeg_cmd"])


def test_select_clips_tool_happy_path():
    words = [
        {"word": f"w{i}", "start_time": float(i), "end_time": float(i) + 0.5}
        for i in range(120)
    ]
    plan = srv.select_clips(
        source_path="/tmp/x.mp4",
        transcript_words=words,
        duration_sec=120.0,
        target_count=2,
        min_sec=30.0,
        max_sec=60.0,
    )
    assert plan["source_path"] == "/tmp/x.mp4"
    assert 1 <= len(plan["clips"]) <= 2


def test_classify_scenes_tool_no_keyframes():
    scenes = [{"scene_id": "s0", "start_time": 0.0, "end_time": 5.0}]
    out = srv.classify_scenes(scenes=scenes)
    assert out["classifications"][0]["scene_id"] == "s0"
    assert out["classifications"][0]["layout"] in {k.value for k in LayoutKind}
