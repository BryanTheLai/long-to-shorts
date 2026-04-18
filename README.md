# Humeo

Turn a long podcast/interview into vertical shorts.

Bluntly:

- `src/humeo/` is the product wrapper. It downloads a YouTube video, transcribes it, asks an LLM for the best clips, and renders final shorts.
- `humeo-core/` is the reusable engine. It owns the shared schemas, ffmpeg layout math, and MCP server.

If you are confused by the two folders, that is the difference. One is the app. One is the engine.

## One rule, five layouts

A short shows at most **two on-screen items**, where an item is a
`person` or a `chart`. That gives exactly five layouts (the "thrusters"):

| Layout                | Items              |
| --------------------- | ------------------ |
| `zoom_call_center`    | 1 person           |
| `sit_center`          | 1 person           |
| `split_chart_person`  | 1 chart + 1 person |
| `split_two_persons`   | 2 persons          |
| `split_two_charts`    | 2 charts           |

See [`TERMINOLOGY.md`](TERMINOLOGY.md) for the full glossary of every
term used in code and docs (subject, crop, band, seam, bbox, etc.).

## What you actually need

For normal use:

- `humeo` (CLI)
- `humeo-core` (Python package + MCP server command)
- `docs/STUDY_ORDER.md` — **start here** if you have one day to learn the repo
- `docs/PIPELINE.md` — stages, caches, Gemini contracts
- `docs/ENVIRONMENT.md` (API keys, cache dirs, model name)
- `docs/PAPER_BREAKDOWN.md` and `docs/SOLUTIONS.md`
- `docs/TARGET_VIDEO_ANALYSIS.md`

Everything else in `docs/` is supporting context or backlog notes.

## Install

Use `uv`.

```bash
uv venv
uv sync
```

Configuration is documented in **`docs/ENVIRONMENT.md`**. Set **`GOOGLE_API_KEY`** (preferred) or **`GEMINI_API_KEY`** for **Gemini** clip selection (see [Google Gen AI Python SDK](https://github.com/googleapis/python-genai)). By default, ingest for each YouTube id is stored under the platform cache directory (see env doc); use **`--no-video-cache`** or **`--work-dir`** to change that.

Activate the environment, then run:

```bash
humeo --long-to-shorts "https://www.youtube.com/watch?v=PdVv_vLkUgk"
```

## Repo shape

```text
src/humeo/
  cli.py            product CLI
  pipeline.py       end-to-end wrapper
  ingest.py         download + transcript
  clip_selector.py  Gemini clip selection (google-genai SDK)
  env.py                 dotenv + Gemini key + cache root helpers
  video_cache.py         YouTube id → work dir + manifest JSON
  clip_selection_cache.py transcript hash + clips.meta.json / raw LLM output
  render_window.py       trim/hook → single ffmpeg source window
  cutter.py         subtitle generation
  reframe_ffmpeg.py thin adapter into humeo-core
  config.py         product config

humeo-core/
  src/humeo_core/
    schemas.py
    server.py
    primitives/
      ingest.py
      classify.py
      face_detect.py
      vision.py
      select_clips.py
      layouts.py
      compile.py
```

## Runtime path

```text
YouTube URL
  -> download
  -> transcript
  -> clip selection (Gemini text → clips.json)
  -> keyframe per clip + layout vision (Gemini vision → LayoutInstruction)
  -> ASS subtitle generation
  -> humeo-core render primitive (ffmpeg)
  -> final 9:16 MP4s
```

## Docs

- `docs/STUDY_ORDER.md`: recommended reading order (e.g. one-day prep).
- `docs/PIPELINE.md`: exact stage and cache behavior for `run_pipeline`.
- `docs/PAPER_BREAKDOWN.md`: the HIVE paper, explained clearly (see §9 for file mapping).
- `docs/SOLUTIONS.md`: why the repo is shaped this way.
- `docs/TARGET_VIDEO_ANALYSIS.md`: why the Cathie Wood video is the right test case.

## Test

```bash
uv sync --extra dev
uv run pytest
```
