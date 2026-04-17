# Humeo

Turn a long podcast/interview into vertical shorts.

Bluntly:

- `src/humeo/` is the product wrapper. It downloads a YouTube video, transcribes it, asks an LLM for the best clips, and renders final shorts.
- `humeo-mcp/` is the reusable engine. It owns the shared schemas, ffmpeg layout math, and MCP server.

If you are confused by the two folders, that is the difference. One is the app. One is the engine.

## What you actually need

For normal use:

- `humeo`
- `humeo-mcp`
- `docs/PAPER_BREAKDOWN.md`
- `docs/SOLUTIONS.md`
- `docs/TARGET_VIDEO_ANALYSIS.md`

Everything else in `docs/` is supporting context or older notes.

## Install

Use `uv`.

```bash
uv venv
uv sync
```

Activate the environment, then run:

```bash
humeo --long-to-shorts "https://www.youtube.com/watch?v=PdVv_vLkUgk"
```

Use OpenAI instead of Gemini:

```bash
humeo --long-to-shorts "https://www.youtube.com/watch?v=PdVv_vLkUgk" --provider openai
```

## Repo shape

```text
src/humeo/
  cli.py            product CLI
  pipeline.py       end-to-end wrapper
  ingest.py         download + transcript
  clip_selector.py  choose clips with LLM
  cutter.py         subtitle generation
  reframe_ffmpeg.py thin adapter into humeo-mcp
  config.py         product config

humeo-mcp/
  src/humeo_mcp/
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
  -> clip selection
  -> midpoint keyframe per chosen clip
  -> heuristic layout classification
  -> subtitle generation
  -> humeo-mcp render primitive
  -> final 9:16 MP4s
```

## Docs

- `docs/PAPER_BREAKDOWN.md`: the HIVE paper, explained clearly.
- `docs/SOLUTIONS.md`: why the repo is shaped this way.
- `docs/TARGET_VIDEO_ANALYSIS.md`: why the Cathie Wood video is the right test case.

## Test

```bash
pytest
```
