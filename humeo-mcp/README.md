# humeo-mcp

**Reusable-rocket MCP server for long-video → 9:16 shorts.**

First-principles design, from the HIVE paper + Bryan's rocket analogy:
we don't build doors and windows (general subject-tracker UI, retraining
models). We build the **container** (schemas), **landing gear** (deterministic
local extraction), and **three thrusters that point in three directions**
(the three 9:16 layouts this video format actually uses). Everything else
is pluggable.

## The rocket, in one picture

```
            ┌──────────────────────────────────────────┐
            │         Control panel  (MCP tools)       │   <- any MCP client
            └───────────────────┬──────────────────────┘
                                │ strict JSON
   ┌────────────────┬───────────┼────────────────┬─────────────────┐
   ▼                ▼           ▼                ▼                 ▼
 ingest       classify_scenes  select_clips   plan_layout       render_clip
(scenes +     (3-way layout   (clip picker,   (3 thrusters,    (ffmpeg compile,
 keyframes +   classifier)     heuristic +     pure filter      dry-run safe)
 transcript)                   LLM-ready)      math)
                                                 │
                                                 ▼
                                       ┌────────────────────┐
                                       │   LayoutKind       │
                                       │  ────────────────  │
                                       │  zoom_call_center  │
                                       │  sit_center        │
                                       │  split_chart_person│
                                       └────────────────────┘
```

Only the classifier and clip-selector have optional LLM hooks; everything
else is deterministic, local, and cheap.

## Why three layouts?

The source video this tool was designed for has exactly **three** on-screen
geometries:

1. **`zoom_call_center`** — one person on a zoom call, subject in the middle,
   tight crop (the default zoom is `1.25`).
2. **`sit_center`** — one person sitting in frame, subject in the middle,
   wider framing (zoom `1.0`).
3. **`split_chart_person`** — explainer scene where a chart occupies the
   left ~2/3 of the source and a person occupies the right ~1/3. In the
   9:16 output these are stacked: chart 60% top, person 40% bottom.

Because the geometry is bounded, we do NOT need a general subject-tracker
ML model or a drag-to-highlight UI. We need three small, correct pieces of
crop/compose math. That is exactly what `src/humeo_mcp/primitives/layouts.py`
is.

## Install

```bash
pip install -e .
# optional: word-level transcription
pip install 'humeo-mcp[transcribe]'
```

External requirements: `ffmpeg` and `ffprobe` on PATH.

`scenedetect` requires OpenCV. Install `opencv-python-headless` or
`opencv-python` alongside `scenedetect`.

## Use it as an MCP server

```bash
humeo-mcp         # stdio transport
```

Example Cursor/Claude Desktop config:

```json
{
  "mcpServers": {
    "humeo": { "command": "humeo-mcp" }
  }
}
```

Tools exposed:

| Tool                   | Purpose                                                          |
| ---------------------- | ---------------------------------------------------------------- |
| `list_layouts`         | Enumerate the 3 supported layouts.                               |
| `ingest`               | Scene detection + keyframe extraction (+ optional transcript).   |
| `classify_scenes`      | Heuristic per-scene layout classification.                       |
| `select_clips`         | Heuristic clip picker over a word-level transcript.              |
| `plan_layout`          | Return the exact `ffmpeg -filter_complex` for a layout.          |
| `build_render_cmd`     | Build the ffmpeg command (no execution) — review before spend.   |
| `render_clip`          | Build + run ffmpeg to produce a 9:16 MP4.                        |

Resource: `humeo://layouts` (JSON listing of the 3 layouts).

## Use it as a CLI

```bash
humeo layouts
humeo plan-layout zoom_call_center --zoom 1.3
humeo ingest /path/to/long.mp4 ./work --with-transcript
humeo pipeline /path/to/long.mp4 ./out --clips 3 --min-sec 30 --max-sec 60
```

## JSON contracts (non-negotiable)

All tools take and return Pydantic-validated JSON. The contracts live in
[`src/humeo_mcp/schemas.py`](src/humeo_mcp/schemas.py):

- `Scene`                     `{scene_id, start_time, end_time, keyframe_path?}`
- `TranscriptWord`            `{word, start_time, end_time}`
- `IngestResult`              `{source_path, duration_sec, scenes[], transcript_words[], keyframes_dir?}`
- `SceneClassification`       `{scene_id, layout, confidence, reason}`
- `Clip`                      `{clip_id, topic, start_time_sec, end_time_sec, viral_hook, virality_score, transcript, suggested_overlay_title, layout?}`
- `ClipPlan`                  `{source_path, clips[]}`
- `LayoutInstruction`         `{clip_id, layout, zoom, person_x_norm, chart_x_norm}`
- `RenderRequest` / `RenderResult`

## First-principles decisions (what we intentionally did NOT build)

- **No giant subject-tracker ML.** The video format has 3 fixed layouts;
  pixel-level tracking is not needed.
- **No drag-and-highlight UI.** An MCP tool is a better "UI" for an
  agent-first workflow. If a human wants to override, they pass a
  `LayoutInstruction` with their own `person_x_norm` / `chart_x_norm` /
  `zoom`.
- **No end-to-end video→video model.** The HIVE paper's core insight is
  that decomposed orchestration beats monolithic generation. We reify
  that insight as six small composable tools.

## Extending the pilot

- Plug a real multimodal model into `classify_scenes_with_llm(vision_fn)`.
- Plug a real reasoning model into `select_clips_with_llm(text_fn)`.
- Both enforce strict JSON outputs, so bad model output can't corrupt
  downstream stages.

## Testing

```bash
python -m pytest
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for deeper rationale.

## License

MIT
