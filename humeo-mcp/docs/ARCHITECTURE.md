# Architecture — Reusable Rocket

> *"We don't need to build the door or windows — just a container with landing
> gear and thrusters that move in different directions."*
> — Bryan

That analogy maps exactly onto this MCP:

| Rocket part     | Codebase                                                         | Purpose                                                                 |
| --------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Container       | `src/humeo_mcp/schemas.py`                                       | Strict JSON contracts every stage reads/writes.                         |
| Landing gear    | `src/humeo_mcp/primitives/ingest.py`                             | Deterministic local extraction (scenes, keyframes, transcript).         |
| Thrusters (×3)  | `src/humeo_mcp/primitives/layouts.py`                            | Three fixed 9:16 crop/compose recipes.                                  |
| Pilot           | `primitives/classify.py` + `primitives/select_clips.py`          | Heuristic + LLM-ready decision makers.                                  |
| Compiler        | `src/humeo_mcp/primitives/compile.py`                            | Deterministic ffmpeg assembly.                                          |
| Control panel   | `src/humeo_mcp/server.py`                                        | MCP tools exposing every primitive.                                     |
| Manual controls | `src/humeo_mcp/cli.py`                                           | CLI mirror of the MCP tools for terminal use.                           |

## First-principles reasoning

The HIVE paper's core insight is that good short-video editing requires
**staged reasoning with strict intermediate artifacts**, not a single
giant model call. Three consequences flow from that:

1. **Extraction must be local and deterministic.** No model call should
   ever touch raw video bytes. `ingest.py` runs ffprobe + PySceneDetect
   + ffmpeg + (optional) faster-whisper. Everything it emits is JSON or
   a file path.

2. **Reasoning must be decomposed into narrow sub-tasks.** Classifying a
   scene's layout is a completely different task from selecting a viral
   clip. Each has its own schema, its own prompt, its own validation.
   This is why `primitives/` is five files instead of one.

3. **Every model call must emit schema-validated JSON.** Free-form model
   output is not allowed to enter the pipeline. `classify_scenes_with_llm`
   and `select_clips_with_llm` both `model_validate(...)` the raw output
   before returning; parse failures degrade gracefully to `SIT_CENTER` +
   low confidence, not crashes.

## Why only three layouts?

The video format this MCP was designed for has exactly three on-screen
geometries (the user's observation from the source video):

- zoom call, one person, center, tight.
- one person sitting, center, wider.
- explainer: chart left (~2/3) + person right (~1/3).

A general subject-tracker ML model is orders of magnitude more expensive
and less reliable than three hand-written crop recipes. The recipes live
in `plan_zoom_call_center`, `plan_sit_center`, `plan_split_chart_person`
and are pure functions from `LayoutInstruction` to an ffmpeg filtergraph
string. They are fully unit-tested.

If a new geometry shows up in future source videos, adding a fourth
"thruster" is strictly additive: write a new `plan_*` function, add it
to `_DISPATCH`, add an enum variant. No existing code has to change.

## 9:16 layout math

Source is assumed 16:9 (1920×1080 by default, but probed per-clip).
Target is 1080×1920. For each layout:

### `zoom_call_center` and `sit_center`

Standard centered aspect-ratio crop to 9:16, then scale to 1080×1920:

```
crop=cw:ch:x:y,scale=1080:1920:flags=lanczos,setsar=1[vout]
```

`cw`, `ch` are the largest 9:16 window that fits in the source, divided
by `zoom`. `x`, `y` center the window on `person_x_norm` / 0.5.
Dimensions are rounded to even values so libx264 is happy. The window is
clamped inside the source so a high `person_x_norm` never crops outside.

### `split_chart_person`

The source is split into two independent branches via `split=2`:

- **Top band (60% of output height):** crop the left 2/3 of the source
  (chart region), fit with `force_original_aspect_ratio=decrease`, and
  pad to fill the top band. Padding preserves chart readability.
- **Bottom band (40% of output height):** crop a 1/3-wide window
  centered on the person (`person_x_norm`), then fill with
  `force_original_aspect_ratio=increase` + a final crop so the person is
  cleanly cropped without letterboxing.

The two branches are `vstack`-ed into the 1080×1920 output.

## Extensibility story

- **Smarter classifier:** implement `LLMVisionFn` with any multimodal
  model and pass it to `classify_scenes_with_llm`. The fallback heuristic
  stays available for offline runs and tests.
- **Smarter clip selector:** same pattern, `LLMTextFn` → `select_clips_with_llm`.
- **New layout:** add a `plan_*` planner, register in `_DISPATCH`, add a
  `LayoutKind` variant. Tests in `test_layouts.py` automatically iterate
  over all `LayoutKind`s, so the dispatch coverage test will catch a
  missing registration immediately.

## What we intentionally did NOT build

- Drag-and-highlight subject-selector UI.
- A general ML subject-tracker.
- A monolithic video-in-video-out model.
- Any network calls in the core library. The MCP server is stdio-only;
  the CLI runs fully offline.

This keeps the rocket **reusable**: the same primitives power the MCP
server, the CLI, a Python library, and (soon) a web UI if that's ever
warranted.
