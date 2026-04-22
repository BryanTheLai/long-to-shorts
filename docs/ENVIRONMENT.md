# Environment variables

This is the single reference for how Humeo reads configuration from the environment and from a project `.env` file.

## Loading order

1. On import, `humeo.config` runs `humeo.env.bootstrap_env()`, which calls `python-dotenv`’s `load_dotenv()` for the **current working directory** (typically your repo root).
2. Values already set in the process environment **win** over `.env` (dotenv default).

Practical rule: run the product from the repo venv with `uv run humeo ...` so the active dependencies and the current `.env` resolve from the same place.

Copy `.env.example` to `.env` and fill in secrets. `.env` is gitignored.

## Stage LLMs (stages 2 / 2.25 / 2.5 / 3)

These stages are provider-swappable through `src/humeo/llm_provider.py`.

| Variable | Default | Meaning |
|----------|---------|---------|
| **`HUMEO_LLM_PROVIDER`** | `gemini` | One of `gemini`, `openai`, or `azure`. |
| **`HUMEO_LLM_MODEL`** | *(unset)* | Text-stage model or deployment id for clip selection, hook detection, and content pruning. |
| **`HUMEO_LLM_VISION_MODEL`** | *(unset)* | Optional separate model or deployment id for stage 3 layout vision. Falls back to `HUMEO_LLM_MODEL`. |

## Gemini (legacy envs still supported)

Clip selection uses the **Google Gen AI SDK for Python** (`google-genai` package): `from google import genai`. Upstream docs: [python-genai](https://github.com/googleapis/python-genai) (Gemini Developer API and Vertex AI). The older `google-generativeai` package is not used.

| Variable | Used for |
|----------|----------|
| **`GOOGLE_API_KEY`** | **Preferred** API key for Gemini. Get a key from [Google AI Studio](https://aistudio.google.com/apikey). The SDK also recognizes **`GEMINI_API_KEY`** in the environment when using `genai.Client()` without an explicit key. |
| **`GEMINI_API_KEY`** | Fallback only if `GOOGLE_API_KEY` is unset (same kind of key as AI Studio). |

Gemini **must** use an explicit API key for the stage LLMs. Without it, clients may fall back to Application Default Credentials and return `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT`.

| Variable | Default | Meaning |
|----------|---------|---------|
| **`GEMINI_MODEL`** | `gemini-3.1-flash-lite-preview` | Legacy Gemini text-model env. Used when `HUMEO_LLM_PROVIDER=gemini` and `HUMEO_LLM_MODEL` is unset. |
| **`GEMINI_VISION_MODEL`** | *(unset)* | Legacy Gemini vision-model env. Used when `HUMEO_LLM_PROVIDER=gemini` and `HUMEO_LLM_VISION_MODEL` is unset. |

## OpenAI / Azure OpenAI

| Variable | Used for |
|----------|----------|
| **`OPENAI_API_KEY`** | Required when `HUMEO_LLM_PROVIDER=openai`. |
| **`OPENAI_BASE_URL`** | Optional OpenAI-compatible gateway URL when `HUMEO_LLM_PROVIDER=openai`. |
| **`AZURE_OPENAI_API_KEY`** | Required when `HUMEO_LLM_PROVIDER=azure`. |
| **`AZURE_OPENAI_BASE_URL`** / **`AZURE_BASE_URL`** | Preferred Azure OpenAI-compatible base URL. If this is set, Humeo uses the plain OpenAI client against that base URL and ignores endpoint-style Azure settings. |
| **`AZURE_OPENAI_ENDPOINT`** / **`AZURE_ENDPOINT`** | Endpoint-style Azure resource URL. Used only when no Azure base URL is set. |
| **`AZURE_OPENAI_DEPLOYMENT`** / **`AZURE_DEPLOYMENT`** | Optional Azure deployment name for endpoint-style Azure resources. If `HUMEO_LLM_MODEL` is unset, this value is used as the model fallback. |
| **`AZURE_OPENAI_API_VERSION`** / **`OPENAI_API_VERSION`** | Required only for endpoint-style Azure resources. Not required when `AZURE_OPENAI_BASE_URL` / `AZURE_BASE_URL` is used. |

## Clip selection prompts (Jinja2)

Templates live under `src/humeo/prompts/` in the repo (`clip_selection_system.jinja2`, `clip_selection_user.jinja2`) and are shipped with the package.

| Variable | Used for |
|----------|----------|
| **`HUMEO_PROMPTS_DIR`** | If set to a directory path, Humeo loads those `.jinja2` files instead of the built-ins (custom prompts without editing the package). |

Clip duration bounds for the clip-selection stage match `MIN_CLIP_DURATION_SEC` / `MAX_CLIP_DURATION_SEC` in `humeo.config` (defaults **50–90** seconds). Edit `config.py` or your forked templates to change what the model is asked for.

### Per-clip layout (product pipeline)

After clip selection, the pipeline samples multiple frames per clip and calls the configured multimodal model with a fixed JSON schema (`layout`, `person_bbox`, `chart_bbox`, `reason`). That produces a full **`LayoutInstruction`** per clip (including optional normalized split regions). Cached artifacts: **`layout_vision.meta.json`** and **`layout_vision.json`** under the work directory. Use **`--force-layout-vision`** to ignore that cache. Full detail: **`docs/PIPELINE.md`**.

## OpenAI (transcription only)

| Variable | Used for |
|----------|----------|
| **`OPENAI_API_KEY`** | OpenAI **Whisper** HTTP API when you choose it (see below) or when WhisperX is not installed. Not used for clip selection. |
| **`HUMEO_TRANSCRIBE_PROVIDER`** | `auto` (default), `openai`, or `whisperx`. With `uv sync --extra whisper`, WhisperX wins unless you set **`openai`** — then **`OPENAI_API_KEY`** is used and you avoid local WhisperX/torch stack noise on Windows. Same video directory still reuses **`transcript.json`** after the first successful run. |

Transcription output is always normalized to **`transcript.json`** in the work directory. Re-running the pipeline on the same cached video **skips** ASR when that file already exists (same as skipping re-download of **`source.mp4`**).

## Clip selection cache (LLM skip)

When **`clips.json`** and **`clips.meta.json`** exist under the work directory and the stored **LLM identity** still matches the current provider/model transport, the pipeline **skips** the clip-selection call and reuses **`clips.json`**.

| Artifact | Role |
|----------|------|
| **`clips.meta.json`** | Version (v4 = provider-aware), transcript hash, `llm`, ranking policy fingerprint |
| **`clip_selection_raw.json`** | Exact raw JSON string returned by the LLM (debug / audit) |

Use **`--force-clip-selection`** to always re-run. Legacy v1 meta files that used OpenAI for clip selection are treated as **cache miss**.

## Layout vision cache (multimodal LLM)

When **`layout_vision.json`** and **`layout_vision.meta.json`** exist and the cached **LLM identity** still matches the current run, the pipeline **skips** layout vision calls.

Stage 3 samples multiple frames per clip with `cv2` (uniform coverage plus frame-diff peaks), sends them to the configured multimodal provider, and merges those frame opinions into one render-safe `LayoutInstruction`. `opencv-python` is part of the default app install for this reason.

| Artifact | Role |
|----------|------|
| **`layout_vision.meta.json`** | Transcript hash, `clip_windows_sha256`, `llm`, layout policy version |
| **`layout_vision.json`** | Per-clip `instruction` (serialized `LayoutInstruction`) + `raw` (model JSON or error) |

Use **`--force-layout-vision`** to always re-run. Changing the rendered clip windows (start/end, trims, keep ranges) invalidates the layout cache; editing unrelated clip metadata does not.

## Video cache

Repeat runs for the same YouTube video id reuse **`source.mp4`** and **`transcript.json`** when they already exist in the resolved work directory.

| Variable | Meaning |
|----------|---------|
| **`HUMEO_CACHE_ROOT`** | Root directory for the cache layout and the manifest file. Default: `~/.cache/humeo` on Unix, `%LOCALAPPDATA%/humeo` on Windows. |

### Layout

- **Default work directory** (no `--work-dir`): `<cache_root>/videos/<11-char-video-id>/`
- **Global manifest** (index of ids → paths and metadata): `<cache_root>/video_cache_manifest.json`
- **`--no-video-cache`**: use `./.humeo_work` unless you pass `--work-dir`
- **`--work-dir PATH`**: use that folder for all intermediates (disables the default per-id path)

After a successful download, yt-dlp writes **`source.info.json`** next to **`source.mp4`**. The pipeline merges that metadata into the manifest.

## CLI cross-reference

| Flag | Env equivalent / notes |
|------|-------------------------|
| `--llm-provider` | `HUMEO_LLM_PROVIDER` |
| `--llm-model` | `HUMEO_LLM_MODEL` (`--gemini-model` still works as a legacy alias) |
| `--llm-vision-model` | `HUMEO_LLM_VISION_MODEL` (`--gemini-vision-model` still works as a legacy alias) |
| `--work-dir` | Explicit intermediate-artifact directory |
| `--cache-root` | `HUMEO_CACHE_ROOT` |
| `--no-video-cache` | Disables per-video cache dirs |
| `--force-clip-selection` | Ignores clip-selection cache |
| `--force-hook-detection` | Ignores hook-detection cache |
| `--force-content-pruning` | Ignores pruning cache |
| `--force-layout-vision` | Ignores layout vision cache |
| `--no-hook-detection` | Skips Stage 2.25 entirely |
| `--start-at`, `--stop-after` | Resume / stop at a named stage using cached artifacts |
| `--inspect-stage`, `--clip-id` | Dump stable stage-inspection JSON from an existing work dir |
| `--clean-run` | Forces a fresh work dir and bypasses cache reuse |

## See also

- **[`docs/README.md`](README.md)** — Index of all documentation under `docs/`.
- **[`docs/PIPELINE.md`](PIPELINE.md)** — Stages and cache invalidation (overlaps CLI flags above only by cross-reference; no duplicate tables maintained here).
- **[`docs/SHARING.md`](SHARING.md)** — Public repo vs raw file URLs vs GitHub Pages; why large media is not committed.
