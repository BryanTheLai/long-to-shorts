"""Minimal CLI that exposes the same primitives as the MCP server.

Keeps the rocket dual-use: ``humeo-mcp`` for agentic clients,
``humeo`` for terminal-driven runs.

Subcommands:
    humeo ingest <src> <work_dir> [--with-transcript]
    humeo classify <ingest_result.json>
    humeo plan-layout <layout> [--zoom 1.2] [...]
    humeo render <render_request.json>
    humeo layouts
    humeo pipeline <src> <out_dir>        # full end-to-end (heuristics only)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .primitives import classify as classify_mod
from .primitives import compile as compile_mod
from .primitives import ingest as ingest_mod
from .primitives import layouts as layouts_mod
from .primitives import select_clips as select_mod
from .schemas import (
    Clip,
    IngestResult,
    LayoutInstruction,
    LayoutKind,
    RenderRequest,
    Scene,
)


def _write_json(path: str, obj: Any) -> None:
    Path(Path(path).parent).mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def cmd_layouts(_: argparse.Namespace) -> int:
    for kind in LayoutKind:
        print(kind.value)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    result = ingest_mod.ingest(
        args.source,
        args.work_dir,
        with_transcript=args.with_transcript,
        whisper_model=args.whisper_model,
    )
    out_path = args.out or os.path.join(args.work_dir, "ingest.json")
    _write_json(out_path, result.model_dump())
    print(out_path)
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    with open(args.ingest_json) as f:
        data = json.load(f)
    scenes = [Scene.model_validate(s) for s in data["scenes"]]
    results = classify_mod.classify_scenes_heuristic(scenes)
    out = {"classifications": [r.model_dump() for r in results]}
    if args.out:
        _write_json(args.out, out)
        print(args.out)
    else:
        print(json.dumps(out, indent=2))
    return 0


def cmd_plan_layout(args: argparse.Namespace) -> int:
    instr = LayoutInstruction(
        clip_id="cli",
        layout=LayoutKind(args.layout),
        zoom=args.zoom,
        person_x_norm=args.person_x,
        chart_x_norm=args.chart_x,
    )
    fp = layouts_mod.plan_layout(
        instr, out_w=args.out_w, out_h=args.out_h, src_w=args.src_w, src_h=args.src_h
    )
    print(fp.filtergraph)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    with open(args.request_json) as f:
        data = json.load(f)
    req = RenderRequest.model_validate(data)
    result = compile_mod.render_clip(req)
    print(json.dumps(result.model_dump(), indent=2))
    return 0 if result.success else 1


def cmd_pipeline(args: argparse.Namespace) -> int:
    """End-to-end: ingest -> classify -> select clips -> render, all heuristic."""

    out_dir = args.out_dir
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    ingest_res = ingest_mod.ingest(
        args.source, out_dir, with_transcript=args.with_transcript
    )
    _write_json(os.path.join(out_dir, "ingest.json"), ingest_res.model_dump())

    classifications = classify_mod.classify_scenes_heuristic(ingest_res.scenes)
    layout_by_scene = {c.scene_id: c.layout for c in classifications}

    plan = select_mod.select_clips_heuristic(
        ingest_res.source_path,
        ingest_res.transcript_words,
        ingest_res.duration_sec,
        target_count=args.clips,
        min_sec=args.min_sec,
        max_sec=args.max_sec,
    )
    # Attach a layout to each clip by picking the layout of the scene its
    # midpoint falls in; fall back to SIT_CENTER.
    def _layout_for_clip(c: Clip) -> LayoutKind:
        mid = (c.start_time_sec + c.end_time_sec) / 2.0
        for s in ingest_res.scenes:
            if s.start_time <= mid < s.end_time:
                return layout_by_scene.get(s.scene_id, LayoutKind.SIT_CENTER)
        return LayoutKind.SIT_CENTER

    _write_json(os.path.join(out_dir, "plan.json"), plan.model_dump())

    results = []
    for c in plan.clips:
        layout_kind = _layout_for_clip(c)
        instr = LayoutInstruction(clip_id=c.clip_id, layout=layout_kind)
        out_path = os.path.join(out_dir, f"clip_{c.clip_id}.mp4")
        req = RenderRequest(
            source_path=ingest_res.source_path,
            clip=c,
            layout=instr,
            output_path=out_path,
            title_text=c.suggested_overlay_title,
            mode="dry_run" if args.dry_run else "normal",
        )
        r = compile_mod.render_clip(req)
        results.append(r.model_dump())
        print(f"[{c.clip_id}] layout={layout_kind.value} success={r.success} -> {out_path}")

    _write_json(os.path.join(out_dir, "renders.json"), results)
    return 0 if all(r["success"] for r in results) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="humeo")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("layouts", help="List the 3 supported layouts").set_defaults(func=cmd_layouts)

    pi = sub.add_parser("ingest", help="Run scene detection + keyframes (+ optional transcript)")
    pi.add_argument("source")
    pi.add_argument("work_dir")
    pi.add_argument("--with-transcript", action="store_true")
    pi.add_argument("--whisper-model", default="base")
    pi.add_argument("--out", default=None)
    pi.set_defaults(func=cmd_ingest)

    pc = sub.add_parser("classify", help="Heuristically classify scenes into layouts")
    pc.add_argument("ingest_json")
    pc.add_argument("--out", default=None)
    pc.set_defaults(func=cmd_classify)

    pl = sub.add_parser("plan-layout", help="Print the ffmpeg filter_complex for a layout")
    pl.add_argument("layout", choices=[k.value for k in LayoutKind])
    pl.add_argument("--zoom", type=float, default=1.0)
    pl.add_argument("--person-x", dest="person_x", type=float, default=0.5)
    pl.add_argument("--chart-x", dest="chart_x", type=float, default=0.0)
    pl.add_argument("--out-w", dest="out_w", type=int, default=1080)
    pl.add_argument("--out-h", dest="out_h", type=int, default=1920)
    pl.add_argument("--src-w", dest="src_w", type=int, default=1920)
    pl.add_argument("--src-h", dest="src_h", type=int, default=1080)
    pl.set_defaults(func=cmd_plan_layout)

    pr = sub.add_parser("render", help="Render a clip from a RenderRequest JSON file")
    pr.add_argument("request_json")
    pr.set_defaults(func=cmd_render)

    pp = sub.add_parser("pipeline", help="End-to-end long-to-shorts run (heuristic-only)")
    pp.add_argument("source")
    pp.add_argument("out_dir")
    pp.add_argument("--clips", type=int, default=3)
    pp.add_argument("--min-sec", type=float, default=30.0)
    pp.add_argument("--max-sec", type=float, default=60.0)
    pp.add_argument("--with-transcript", action="store_true")
    pp.add_argument("--dry-run", action="store_true")
    pp.set_defaults(func=cmd_pipeline)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
