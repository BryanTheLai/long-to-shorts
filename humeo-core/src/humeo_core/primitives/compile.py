"""Compiler: assemble a final 9:16 clip from source + clip + layout instruction.

Builds the ffmpeg invocation, optionally runs it. Keeping ``dry_run`` as a
first-class mode means the MCP server can return the exact command without
executing — ideal for an agent that wants to review before spending CPU.

Rendering order is fixed and intentional:

1. **Cut + crop/compose.** ``plan_layout`` produces the base filtergraph
   that takes the source, applies the layout-specific crops, and emits a
   labelled ``[vout]`` at the exact output resolution (e.g. 1080x1920).
2. **Overlay title** (``drawtext``) — skipped for split layouts because
   the source itself already has a slide/chart title and an extra overlay
   just obscures content.
3. **Subtitles.** ``subtitles`` filter runs **last** so text is drawn over
   the finished composition, not the source. ``original_size`` is pinned
   to the output resolution so libass coordinate math (MarginV, FontSize)
   is in *output pixels*, not libass's default PlayResY=288 — which was
   the bug behind the "subtitles blocked / floating in the middle" look.
4. **Mux** with the source audio stream (``0:a:0``).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..schemas import SPLIT_LAYOUTS, RenderRequest, RenderResult
from .layouts import plan_layout


def _ensure_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH")
    return exe


def _escape_drawtext(text: str) -> str:
    # drawtext quoting is brittle across ffmpeg builds. Keep it simple:
    # collapse whitespace, drop apostrophes, and escape the characters
    # that are still significant to the filter parser.
    safe = " ".join(text.split()).replace("'", "")
    return safe.replace("\\", "\\\\").replace(":", "\\:")


def _escape_filter_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _has_audio_stream(media_path: str) -> bool:
    probe = shutil.which("ffprobe")
    if not probe:
        return False
    out = subprocess.run(
        [
            probe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            media_path,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return out.returncode == 0 and "audio" in (out.stdout or "").lower()


def build_ffmpeg_cmd(
    req: RenderRequest,
    *,
    src_w: int = 1920,
    src_h: int = 1080,
    include_audio: bool = True,
) -> list[str]:
    exe = _ensure_ffmpeg() if req.mode != "dry_run" else "ffmpeg"

    plan = plan_layout(
        req.layout, out_w=req.width, out_h=req.height, src_w=src_w, src_h=src_h
    )
    fg = plan.filtergraph

    # Skip the drawtext title overlay on split layouts: the top band already
    # shows a slide/chart with its own baked-in title, so adding an overlay
    # on top of that is pure noise (and was stacking over the chart title
    # in the SPLIT_CHART_PERSON Cathy Wood shorts).
    title_allowed = req.layout.layout not in SPLIT_LAYOUTS
    if req.title_text and title_allowed:
        title_esc = _escape_drawtext(req.title_text)
        fg = fg.replace(
            "[vout]",
            "[v_prepad];"
            f"[v_prepad]drawtext=text='{title_esc}':"
            "expansion=none:"
            "fontcolor=white:fontsize=72:borderw=4:bordercolor=black:"
            "x=(w-text_w)/2:y=80[vout]",
        )

    if req.subtitle_path:
        subtitle_esc = _escape_filter_path(req.subtitle_path)
        # ``original_size`` pins libass's PlayResY to the actual output so
        # ``FontSize`` and ``MarginV`` are interpreted in output pixels. Without
        # this, libass defaults to PlayResY=288 and then upscales to the real
        # canvas (1920) -- blowing font sizes and pushing subtitles to the
        # middle of the frame. ``WrapStyle=0`` enables smart word wrap so long
        # lines break into readable stacks instead of running off-screen.
        fg = fg.replace(
            "[vout]",
            "[v_sub_in];"
            f"[v_sub_in]subtitles='{subtitle_esc}':"
            f"original_size={req.width}x{req.height}:"
            f"force_style='Fontname=Arial,"
            f"FontSize={req.subtitle_font_size},Alignment=2,"
            f"MarginV={req.subtitle_margin_v},MarginL=60,MarginR=60,"
            "WrapStyle=0,BorderStyle=4,"
            "BackColour=&H70000000&,PrimaryColour=&H00FFFFFF&,"
            "Outline=0,Shadow=0,Bold=1'[vout]",
        )

    start = req.clip.start_time_sec
    dur = max(0.1, req.clip.duration_sec)

    Path(Path(req.output_path).parent).mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [
        exe,
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{dur:.3f}",
        "-i",
        req.source_path,
        "-filter_complex",
        fg,
        "-map",
        "[vout]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
    ]

    if include_audio:
        cmd.extend(["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k"])

    cmd.extend(["-movflags", "+faststart", req.output_path])
    return cmd


def probe_source_size(source_path: str) -> tuple[int, int]:
    exe = shutil.which("ffprobe")
    if not exe:
        return 1920, 1080
    out = subprocess.run(
        [
            exe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            source_path,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        w, h = out.stdout.strip().split(",")
        return int(w), int(h)
    except Exception:
        return 1920, 1080


def render_clip(req: RenderRequest) -> RenderResult:
    try:
        src_w, src_h = probe_source_size(req.source_path) if req.mode != "dry_run" else (1920, 1080)
    except Exception:
        src_w, src_h = 1920, 1080

    include_audio = True
    if req.mode != "dry_run":
        include_audio = _has_audio_stream(req.source_path)
        if not include_audio:
            return RenderResult(
                clip_id=req.clip.clip_id,
                output_path=req.output_path,
                ffmpeg_cmd=[],
                success=False,
                error="Source media has no detectable audio stream (a:0).",
            )

    cmd = build_ffmpeg_cmd(req, src_w=src_w, src_h=src_h, include_audio=include_audio)

    if req.mode == "dry_run":
        return RenderResult(
            clip_id=req.clip.clip_id,
            output_path=req.output_path,
            ffmpeg_cmd=cmd,
            success=True,
        )
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if include_audio and not _has_audio_stream(req.output_path):
            return RenderResult(
                clip_id=req.clip.clip_id,
                output_path=req.output_path,
                ffmpeg_cmd=cmd,
                success=False,
                error="Rendered output is missing audio stream (a:0).",
            )
        return RenderResult(
            clip_id=req.clip.clip_id,
            output_path=req.output_path,
            ffmpeg_cmd=cmd,
            success=True,
        )
    except subprocess.CalledProcessError as e:
        return RenderResult(
            clip_id=req.clip.clip_id,
            output_path=req.output_path,
            ffmpeg_cmd=cmd,
            success=False,
            error=e.stderr.decode("utf-8", errors="replace")[-4000:] if e.stderr else str(e),
        )
