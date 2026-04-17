"""Compiler: assemble a final 9:16 clip from source + clip + layout instruction.

Builds the ffmpeg invocation, optionally runs it. Keeping ``dry_run`` as a
first-class mode means the MCP server can return the exact command without
executing — ideal for an agent that wants to review before spending CPU.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..schemas import RenderRequest, RenderResult
from .layouts import plan_layout


def _ensure_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH")
    return exe


def _escape_drawtext(text: str) -> str:
    # ffmpeg drawtext quoting: single quotes and colons need escaping.
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def build_ffmpeg_cmd(req: RenderRequest, *, src_w: int = 1920, src_h: int = 1080) -> list[str]:
    exe = _ensure_ffmpeg() if req.mode != "dry_run" else "ffmpeg"

    plan = plan_layout(
        req.layout, out_w=req.width, out_h=req.height, src_w=src_w, src_h=src_h
    )
    fg = plan.filtergraph

    if req.title_text:
        title_esc = _escape_drawtext(req.title_text)
        fg = (
            fg.replace(
                "[vout]",
                "[v_prepad];"
                f"[v_prepad]drawtext=text='{title_esc}':"
                "fontcolor=white:fontsize=72:borderw=4:bordercolor=black:"
                "x=(w-text_w)/2:y=80[vout]",
            )
        )

    start = req.clip.start_time_sec
    dur = max(0.1, req.clip.duration_sec)

    Path(Path(req.output_path).parent).mkdir(parents=True, exist_ok=True)

    return [
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
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        req.output_path,
    ]


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
    cmd = build_ffmpeg_cmd(req, src_w=src_w, src_h=src_h)

    if req.mode == "dry_run":
        return RenderResult(
            clip_id=req.clip.clip_id,
            output_path=req.output_path,
            ffmpeg_cmd=cmd,
            success=True,
        )
    try:
        subprocess.run(cmd, check=True, capture_output=True)
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
