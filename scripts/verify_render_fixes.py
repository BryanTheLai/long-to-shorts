"""Re-render the cached clips with the new render primitive and snap a
preview PNG from each output so Bryan can eyeball the fix.

Usage:
    python scripts/verify_render_fixes.py
        [--work-dir .humeo_work_clean_01]
        [--output output_verify]
        [--keep-existing]

Reads ``<work-dir>/clips.json``, ``<work-dir>/layout_vision.json``, and the
per-clip subtitles; does **not** call any LLMs or scene-detectors. Emits a
fresh 1080x1920 MP4 for every cached clip plus a single-frame
``*_preview.png`` grabbed at the clip's 1s mark so split layouts are
visible.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from pathlib import Path

from humeo.cutter import generate_ass
from humeo.reframe_ffmpeg import reframe_clip_ffmpeg
from humeo.render_window import clip_for_render
from humeo_core.schemas import Clip, LayoutInstruction


def _snap_preview(video: Path, png: Path, at_sec: float = 1.0) -> None:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not on PATH")
    png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            exe,
            "-y",
            "-ss",
            f"{at_sec:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(png),
        ],
        check=True,
        capture_output=True,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", type=Path, default=Path(".humeo_work_clean_01"))
    ap.add_argument("--output", type=Path, default=Path("output_verify"))
    ap.add_argument(
        "--keep-existing",
        action="store_true",
        help="Skip clips whose output MP4 already exists.",
    )
    args = ap.parse_args()

    work_dir = args.work_dir
    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    source = work_dir / "source.mp4"
    clips_path = work_dir / "clips.json"
    layout_path = work_dir / "layout_vision.json"
    transcript_path = work_dir / "transcript.json"
    subtitles_dir = work_dir / "subtitles"
    subtitles_dir.mkdir(parents=True, exist_ok=True)

    for p in (source, clips_path, layout_path, transcript_path):
        if not p.exists():
            raise FileNotFoundError(p)

    clips_payload = json.loads(clips_path.read_text(encoding="utf-8"))["clips"]
    layout_payload = json.loads(layout_path.read_text(encoding="utf-8"))["clips"]
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

    for cdata in clips_payload:
        clip = Clip.model_validate(cdata)
        instr_payload = layout_payload.get(clip.clip_id, {}).get("instruction")
        if instr_payload is None:
            logging.warning("No layout instruction for %s; skipping.", clip.clip_id)
            continue
        instr = LayoutInstruction.model_validate(instr_payload)
        clip.layout = instr.layout

        rclip = clip_for_render(clip)
        subtitle_path = generate_ass(
            rclip,
            transcript,
            subtitles_dir,
            max_words_per_cue=4,
            max_cue_sec=2.2,
            play_res_x=1080,
            play_res_y=1920,
            font_size=48,
            margin_v=160,
        )

        out_mp4 = out_dir / f"short_{clip.clip_id}.mp4"
        out_png = out_dir / f"short_{clip.clip_id}_preview.png"

        if args.keep_existing and out_mp4.exists():
            logging.info("Skipping %s (already exists).", out_mp4)
        else:
            logging.info(
                "Rendering %s [%s] -> %s", clip.clip_id, instr.layout.value, out_mp4
            )
            reframe_clip_ffmpeg(
                input_path=source,
                output_path=out_mp4,
                clip=rclip,
                layout_instruction=instr,
                subtitle_path=subtitle_path,
                subtitle_font_size=48,
                subtitle_margin_v=160,
                title_text=clip.suggested_overlay_title,
            )

        _snap_preview(out_mp4, out_png)
        logging.info("  preview -> %s", out_png)


if __name__ == "__main__":
    main()
