from humeo_mcp.primitives.compile import build_ffmpeg_cmd
from humeo_mcp.schemas import Clip, LayoutInstruction, LayoutKind, RenderRequest


def _req(**overrides):
    c = Clip(clip_id="1", topic="t", start_time_sec=10.0, end_time_sec=40.0)
    li = LayoutInstruction(clip_id="1", layout=LayoutKind.SIT_CENTER)
    data = dict(
        source_path="/tmp/src.mp4",
        clip=c,
        layout=li,
        output_path="/tmp/out.mp4",
        mode="dry_run",
    )
    data.update(overrides)
    return RenderRequest(**data)


def test_ffmpeg_cmd_has_ss_duration_filtergraph_output():
    cmd = build_ffmpeg_cmd(_req())
    assert "-ss" in cmd
    assert "-t" in cmd
    assert "-filter_complex" in cmd
    # duration = 30.0
    t_idx = cmd.index("-t")
    assert float(cmd[t_idx + 1]) == 30.0
    ss_idx = cmd.index("-ss")
    assert float(cmd[ss_idx + 1]) == 10.0
    assert cmd[-1] == "/tmp/out.mp4"


def test_title_text_injects_drawtext():
    cmd = build_ffmpeg_cmd(_req(title_text="Hello: world's"))
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "drawtext" in fg
    # colon should be escaped
    assert "Hello\\:" in fg
    assert "worlds" in fg
    assert "world's" not in fg
    assert "expansion=none" in fg


def test_map_vout_and_optional_audio():
    cmd = build_ffmpeg_cmd(_req())
    assert "[vout]" in cmd
    assert "0:a?" in cmd


def test_build_is_layout_specific():
    c = Clip(clip_id="1", topic="t", start_time_sec=0, end_time_sec=10)
    split_req = _req(
        clip=c,
        layout=LayoutInstruction(clip_id="1", layout=LayoutKind.SPLIT_CHART_PERSON),
    )
    cmd = build_ffmpeg_cmd(split_req)
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "vstack" in fg
