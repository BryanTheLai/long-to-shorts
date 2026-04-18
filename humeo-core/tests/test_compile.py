from humeo_core.primitives.compile import build_ffmpeg_cmd
from humeo_core.schemas import Clip, LayoutInstruction, LayoutKind, RenderRequest


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


def test_map_vout_and_primary_audio():
    cmd = build_ffmpeg_cmd(_req())
    assert "[vout]" in cmd
    assert "0:a:0" in cmd


def test_subtitle_style_uses_requested_font_and_margin():
    cmd = build_ffmpeg_cmd(
        _req(subtitle_path="/tmp/clip.srt", subtitle_font_size=18, subtitle_margin_v=64)
    )
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "subtitles='" in fg
    assert "FontSize=18" in fg
    assert "MarginV=64" in fg
    # Smart word wrap so long captions break into multiple readable lines.
    assert "WrapStyle=0" in fg


def test_subtitle_original_size_pins_libass_to_output_resolution():
    """Without original_size=W x H, libass uses PlayResY=288 and blows up fonts/margins.

    This is the root cause of the "subtitles floating in the middle of the
    frame / blocked" bug the user reported.
    """
    cmd = build_ffmpeg_cmd(_req(subtitle_path="/tmp/clip.srt"))
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "original_size=1080x1920" in fg


def test_subtitles_applied_after_crop_and_title():
    """Order: crop/compose -> drawtext title -> subtitles.

    The pipeline must crop **first**, then draw text on the finished frame.
    """
    cmd = build_ffmpeg_cmd(
        _req(title_text="Hook", subtitle_path="/tmp/clip.srt")
    )
    fg = cmd[cmd.index("-filter_complex") + 1]
    crop_pos = fg.index("[0:v]crop=")
    drawtext_pos = fg.index("drawtext")
    subs_pos = fg.index("subtitles=")
    assert crop_pos < drawtext_pos < subs_pos


def test_build_is_layout_specific():
    c = Clip(clip_id="1", topic="t", start_time_sec=0, end_time_sec=10)
    split_req = _req(
        clip=c,
        layout=LayoutInstruction(clip_id="1", layout=LayoutKind.SPLIT_CHART_PERSON),
    )
    cmd = build_ffmpeg_cmd(split_req)
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "vstack" in fg


def test_title_is_suppressed_on_split_layouts():
    """Split layouts already contain a slide/chart with its own title.

    Overlaying an additional drawtext title just obscures content -- that's
    what was happening in the Cathy Wood "chart overlaps subject" report.
    """
    for kind in (
        LayoutKind.SPLIT_CHART_PERSON,
        LayoutKind.SPLIT_TWO_PERSONS,
        LayoutKind.SPLIT_TWO_CHARTS,
    ):
        cmd = build_ffmpeg_cmd(
            _req(
                layout=LayoutInstruction(clip_id="1", layout=kind),
                title_text="This should not render",
            )
        )
        fg = cmd[cmd.index("-filter_complex") + 1]
        assert "drawtext" not in fg, f"title leaked into split layout {kind}"


def test_title_is_drawn_on_single_subject_layouts():
    """Titles are still rendered on ZOOM_CALL_CENTER and SIT_CENTER."""
    for kind in (LayoutKind.ZOOM_CALL_CENTER, LayoutKind.SIT_CENTER):
        cmd = build_ffmpeg_cmd(
            _req(
                layout=LayoutInstruction(clip_id="1", layout=kind),
                title_text="Hook title",
            )
        )
        fg = cmd[cmd.index("-filter_complex") + 1]
        assert "drawtext=text='Hook title'" in fg
