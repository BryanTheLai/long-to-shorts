# Humeo

Long podcast or interview -> vertical 9:16 shorts. Pipeline: download, transcribe, structured LLM stages (clip selection, hook detection, content pruning, layout vision), then ffmpeg render.

The product wrapper supports `gemini`, `openai`, and `azure` for stages 2 / 2.25 / 2.5 / 3 through the same CLI surface.

**Architecture (static HTML, GitHub Pages):**
[https://bryanthelai.github.io/long-to-shorts/hive_architecture_visualization.html](https://bryanthelai.github.io/long-to-shorts/hive_architecture_visualization.html)

## Repo layout

| Path | Role |
|------|------|
| `src/humeo/` | CLI, pipeline, ingest, provider-agnostic prompts, render adapters |
| `humeo-core/` | Schemas, ffmpeg compile, primitives, optional MCP server |

## Pipeline (actual order)

```text
YouTube URL
  -> ingest (source.mp4, transcript.json)
  -> clip selection (structured LLM -> clips.json)
  -> hook detection (structured LLM -> hooks.json)
  -> content pruning (structured LLM -> prune.json)
  -> multi-frame layout vision (structured multimodal LLM -> layout_vision.json)
  -> ASS subtitles + humeo-core ffmpeg render -> short_<id>.mp4
```

Details: **`docs/PIPELINE.md`**.

## Five layouts

A short shows at most two on-screen items (`person` or `chart`). That yields five layout modes (see **`TERMINOLOGY.md`**).

## Requirements

- **Python** >= 3.10
- **`uv`** - install: [astral.sh/uv](https://docs.astral.sh/uv/)
- **`ffmpeg`** - on `PATH` for extract/render
- **API keys / provider env** - see **`docs/ENVIRONMENT.md`**
  - `GOOGLE_API_KEY` or `GEMINI_API_KEY` for Gemini runs
  - `OPENAI_API_KEY` for OpenAI text stages or Whisper API transcription
  - `AZURE_OPENAI_API_KEY` plus Azure endpoint/base-url settings for Azure runs
- **OpenCV** - `opencv-python` is part of the default app install because Stage 3 frame sampling imports `cv2`

Copy **`.env.example`** -> **`.env`** (never commit `.env`).

## Install

```bash
uv venv
uv sync
```

Optional local WhisperX (heavy; Windows often uses OpenAI API instead):

```bash
uv sync --extra whisper
```

## Run

```bash
uv run humeo --long-to-shorts "https://www.youtube.com/watch?v=VIDEO_ID"
```

Use **`--work-dir`** or **`--no-video-cache`** to control where `source.mp4` and intermediates live (see **`docs/ENVIRONMENT.md`**).

## CLI guide

Use `uv run humeo --help` for the live source of truth. Common flags:

### Required

| Flag | Meaning |
|------|---------|
| `--long-to-shorts URL` | YouTube URL to process. Required unless you are inspecting an existing `--work-dir`. |

### Paths and cache behavior

| Flag | Meaning |
|------|---------|
| `--output`, `-o` | Output directory for final `short_*.mp4` files (default: `./output`). |
| `--work-dir PATH` | Directory for intermediate artifacts (`source.mp4`, `transcript.json`, caches). |
| `--no-video-cache` | Disable per-video cache dirs; use `./.humeo_work` unless `--work-dir` is set. |
| `--cache-root PATH` | Override cache root (env equivalent: `HUMEO_CACHE_ROOT`). |
| `--clean-run` | Fresh run: disables per-video cache reuse, forces all LLM stages, and auto-creates a timestamped work dir if `--work-dir` is not provided. |

### LLM provider and model selection

| Flag | Meaning |
|------|---------|
| `--llm-provider {gemini,openai,azure}` | Provider for stages 2 / 2.25 / 2.5 / 3. |
| `--llm-model MODEL_ID` | Text-stage model or deployment id. Legacy alias: `--gemini-model`. |
| `--llm-vision-model MODEL_ID` | Optional separate vision model or deployment id for Stage 3. Legacy alias: `--gemini-vision-model`. |
| `--force-clip-selection` | Re-run Stage 2 even if `clips.meta.json` matches. |
| `--force-hook-detection` | Re-run Stage 2.25 even if `hooks.meta.json` matches. |
| `--force-content-pruning` | Re-run Stage 2.5 even if `prune.meta.json` matches. |
| `--force-layout-vision` | Re-run Stage 3 even if `layout_vision.meta.json` matches. |
| `--no-hook-detection` | Skip Stage 2.25 and leave any hook window already on the clips. |

### Stage control and inspection

| Flag | Meaning |
|------|---------|
| `--start-at STAGE` | Resume from `ingest`, `clip-selection`, `hook-detection`, `content-pruning`, `layout-vision`, or `render`. |
| `--stop-after STAGE` | Stop after a named stage instead of rendering through the end. |
| `--inspect-stage STAGE` | Write a stable inspection JSON payload for a named stage. |
| `--clip-id ID` | Optional clip id filter for `--inspect-stage` (for example `003`). |

### Pruning and subtitles

| Flag | Meaning |
|------|---------|
| `--prune-level {off,conservative,balanced,aggressive}` | Stage 2.5 aggressiveness (default: `balanced`). |
| `--subtitle-font-size INT` | Subtitle font size in output pixels (default: `48`). |
| `--subtitle-margin-v INT` | Bottom subtitle margin in output pixels (default: `160`). |
| `--subtitle-max-words INT` | Max words per subtitle cue (default: `4`). |
| `--subtitle-max-cue-sec FLOAT` | Max subtitle cue duration in seconds (default: `2.2`). |

### Logging

| Flag | Meaning |
|------|---------|
| `--verbose`, `-v` | Enable debug logging. |

### Common command recipes

```bash
# Basic run from the repo venv
uv run humeo --long-to-shorts "https://www.youtube.com/watch?v=VIDEO_ID"

# Full fresh run for debugging / prompt tuning
uv run humeo --long-to-shorts "https://www.youtube.com/watch?v=VIDEO_ID" --clean-run --verbose

# Azure run with explicit stage models
uv run humeo --long-to-shorts "https://www.youtube.com/watch?v=VIDEO_ID" --llm-provider azure --llm-model gpt-5.4 --llm-vision-model gpt-5.4

# Re-run only Stage 3 on an existing cached work dir
uv run humeo --work-dir .humeo_work --start-at layout-vision --force-layout-vision

# Keep intermediates in a fixed local folder
uv run humeo --long-to-shorts "https://www.youtube.com/watch?v=VIDEO_ID" --work-dir .humeo_work
```

## Documentation

| Doc | Purpose |
|-----|---------|
| **`docs/README.md`** | Index of all files under `docs/` |
| **`docs/PIPELINE.md`** | Stages, caches, JSON contracts |
| **`docs/ENVIRONMENT.md`** | Keys, env vars, cache layout |
| **`docs/PROJECT_ISSUES.md`** | Current runtime gaps, backlog, and doc drift |
| **`docs/SHARING.md`** | How to share logs/docs/video without bloating git |
| **`docs/TARGET_VIDEO_ANALYSIS.md`** | Canonical long-form test video rationale |
| **`docs/SOLUTIONS.md`** | Design rationale and invariants |
| **`docs/TODO.md`** | Historical design doc plus current status snapshot |
| **`docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`** | Prompt vs code mismatches and current fix map |
| **`TERMINOLOGY.md`** | Glossary |

## Tests

```bash
uv sync --extra dev
uv run pytest
```

## Sharing outputs

`output/`, `*.mp4`, and `keyframes/` are **gitignored**. Put rendered shorts on **YouTube** or **GitHub Releases**; keep the repo for source and docs. See **`docs/SHARING.md`**.

## License

See **`LICENSE`** (root) and **`humeo-core/LICENSE`**.
