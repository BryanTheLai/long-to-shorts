# Product pipeline: stages, caches, and JSON contracts

This document describes **`humeo.pipeline.run_pipeline`**: what runs when, what is cached, what Gemini returns, and how data flows into ffmpeg.

## High-level flow

```
YouTube URL
    → Stage 1: Ingest (download, transcript)
    → Stage 2: Clip selection (Gemini JSON → clips.json)
    → Stage 3: Keyframes + layout vision (Gemini vision JSON → LayoutInstruction per clip)
    → Stage 4: Render (ffmpeg per clip → output/short_<id>.mp4)
```

Work directory **`work_dir`** defaults to `<HUMEO_CACHE_ROOT>/videos/<video_id>/` unless you pass `--work-dir` or `--no-video-cache` (see `docs/ENVIRONMENT.md`).

---

## Stage 1: Ingest

**Goal:** `source.mp4` + `transcript.json` (+ optional yt-dlp `source.info.json`).

| Step | Function / module | Output |
|------|-------------------|--------|
| Resolve cache dir | `humeo.video_cache.resolve_work_directory` | `config.work_dir` |
| Download | `humeo.ingest.download_video` | `work_dir/source.mp4` |
| Transcript | `humeo.ingest.extract_audio` + `transcribe_whisperx` (or load existing) | `work_dir/transcript.json` |
| Manifest | `upsert_manifest_from_info` | global manifest under cache root |

**Cache behavior**

- If `ingest_complete(work_dir)` is true, the pipeline treats ingest as done and does not re-download (see `humeo.video_cache`).
- If `source.mp4` exists but ingest is not “complete”, download may be skipped; transcript still loads from `transcript.json` if present.

**Transcript fingerprint**

- `transcript_sha256 = SHA256(JSON.dumps(transcript, sort_keys=True, ensure_ascii=False))` — used by clip-selection cache and layout-vision cache (`humeo.clip_selection_cache.transcript_fingerprint`).

---

## Stage 2: Clip selection (Gemini, text-only)

**Goal:** `clips.json` — ranked viral segments with timings and metadata.

**When the LLM runs**

- `clips.json` exists **and**
- `clips.meta.json` exists **and**
- `transcript_sha256` in meta matches current transcript **and**
- `gemini_model` in meta matches **effective** clip model (`config.gemini_model` or `GEMINI_MODEL` from `humeo.config`) **and**
- `force_clip_selection` is **false**

→ **cache hit:** load `clips.json` only (`humeo.clip_selector.load_clips`). No Gemini call.

**When the LLM is skipped (legacy)**

- Meta version &lt; 2 with `llm_provider == "openai"` → cache invalid.

**Artifacts**

| File | Contents |
|------|----------|
| `clips.meta.json` | `version` (2), `transcript_sha256`, `gemini_model` |
| `clip_selection_raw.json` | Raw string returned by Gemini (audit) |
| `clips.json` | Parsed list of `Clip` models (written by `save_clips`) |

**Gemini call** (`humeo.clip_selector.select_clips`)

- SDK: `google.genai` — `Client.models.generate_content`.
- **System:** Jinja template `clip_selection_system.jinja2` (package: `src/humeo/prompts/`).
- **User:** transcript lines built from `transcript["segments"]` as `[start-end] text` (`build_prompt`).
- **Config:** `GenerateContentConfig(system_instruction=..., temperature=0.3, response_mime_type="application/json")`.
- Retries: `LLM_MAX_ATTEMPTS = 3`, `LLM_RETRY_DELAY_SEC = 2.0` with backoff.

**Expected JSON shape (clip selection)**

Top-level object with `"clips": [ ... ]` (or a bare array — parser accepts both). Each item validates as `humeo_core.schemas.Clip`. See `clip_selection_system.jinja2` for the canonical schema (fields include `clip_id`, `start_time_sec`, `end_time_sec`, `virality_score`, `transcript`, `layout_hint`, trim/hook fields, etc.).

**Constants (from `humeo.config`)**

- `MIN_CLIP_DURATION_SEC` = **50**
- `MAX_CLIP_DURATION_SEC` = **90**
- `TARGET_CLIP_COUNT` = **5**
- Default `GEMINI_MODEL` = **`gemini-3.1-flash-lite-preview`** (if env unset)

---

## Stage 3: Keyframes + layout vision (Gemini, multimodal)

**Goal:** One keyframe per clip and a **`LayoutInstruction`** per `clip_id` (layout kind + optional normalized bboxes for split).

### 3a — Keyframes

- Build `Scene` list: `scene_id = clip.clip_id`, `start_time` / `end_time` from `clip_for_render(clip)` window (`humeo.render_window`).
- `humeo_core.primitives.ingest.extract_keyframes(source_video, scenes, keyframes_dir)` writes images under **`work_dir/keyframes/`** and sets `Scene.keyframe_path`.

### 3b — Layout vision (Gemini)

**When vision is skipped (cache hit)**

- `layout_vision.meta.json` + `layout_vision.json` exist **and**
- `transcript_sha256` matches **and**
- `clips_sha256` matches **SHA256 of entire `clips.json` file** **and**
- `gemini_vision_model` matches **resolved** vision model **and**
- `force_layout_vision` is **false**

→ reload `LayoutInstruction` objects from cache (`humeo.layout_vision.run_layout_vision_stage`).

**Resolved vision model** (`resolved_vision_model`)

1. `config.gemini_vision_model` if set  
2. else `GEMINI_VISION_MODEL` env (from `humeo.config`)  
3. else same as clip selection: `config.gemini_model` or `GEMINI_MODEL`

**Gemini call per keyframe** (`_call_gemini_vision`)

- `contents`: `[Part.from_text(GEMINI_LAYOUT_VISION_PROMPT), Part.from_bytes(image)]`
- `GenerateContentConfig(temperature=0.2, response_mime_type="application/json")`
- Parse `response.text` as JSON.

**Gemini JSON schema (layout vision)** — exact contract in `GEMINI_LAYOUT_VISION_PROMPT` in `humeo.layout_vision`:

```json
{
  "layout": "sit_center" | "zoom_call_center" | "split_chart_person",
  "person_bbox": { "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0 } | null,
  "chart_bbox": { "x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0 } | null,
  "reason": "short rationale"
}
```

**Mapping to `LayoutInstruction`** (`_instruction_from_gemini_json`)

- `layout` → `LayoutKind` (invalid string → `sit_center`).
- Bboxes parsed with `BoundingBox.model_validate` (Pydantic).
- `layout_instruction_from_regions` sets `person_x_norm` / `chart_x_norm` from bbox centers/edges (`humeo_core.primitives.vision`).
- If `layout == split_chart_person` **and** both `person_bbox` and `chart_bbox` are non-null, **`split_chart_region`** = chart box and **`split_person_region`** = person box (normalized rects for ffmpeg split planner).

**Failures**

- Missing keyframe → `sit_center`, raw records `error`.
- API/parse failure → `sit_center`, raw records `error` message.

**Artifacts**

| File | Contents |
|------|----------|
| `layout_vision.meta.json` | `transcript_sha256`, `clips_sha256`, `gemini_vision_model` |
| `layout_vision.json` | `{ "clips": { "<clip_id>": { "instruction": <LayoutInstruction JSON>, "raw": <Gemini JSON or error> } } }` |

**Note:** `humeo_core.primitives.vision.classify_from_regions` (bbox heuristics) exists for **MCP / other callers**. The **product pipeline** uses the vision model’s **`layout` field** plus bboxes as above, not pixel heuristics for layout choice.

---

## Stage 4: Render

For each clip:

1. Resolve `LayoutInstruction`: from `layout_instructions[clip_id]`, else `LayoutInstruction(clip_id=..., layout=clip.layout_hint or sit_center)`.
2. Set `clip.layout = instr.layout`.
3. `clip_for_render(clip)` → cut window for ffmpeg.
4. `generate_srt` → subtitles under `work_dir/subtitles/`.
5. If `output_dir/short_<clip_id>.mp4` exists → skip render (log only).
6. Else `reframe_clip_ffmpeg(..., layout_instruction=instr, ...)`.

**Adapter:** `humeo.reframe_ffmpeg` builds `RenderRequest` with full `LayoutInstruction` and calls `humeo_core.primitives.compile.render_clip`.

**Video geometry defaults** (`humeo.config`)

- `TARGET_WIDTH = 1080`, `TARGET_HEIGHT = 1920`, `TARGET_ASPECT = 9/16`

**Layout → ffmpeg**

- `humeo_core.primitives.layouts.plan_layout` dispatches on `LayoutKind`.
- **Split:** If `split_chart_region` and `split_person_region` are set, crops use **`_bbox_to_crop_pixels`** (normalized → even pixel crop). Otherwise split uses fixed **2/3 | 1/3** vertical strip math + `chart_x_norm` trim.
- **Zoom / sit:** Center crops use `person_x_norm` (and vertical center 0.5 vs 0.48 for sit).

---

## Quick reference: what invalidates which cache

| Change | Clip selection cache | Layout vision cache |
|--------|----------------------|---------------------|
| Edit `transcript.json` (content) | Miss (hash) | Miss (hash) |
| Change `clips.json` without meta | N/A | Miss (`clips_sha256`) |
| Change `--gemini-model` | Miss | May still hit vision if vision model unchanged |
| Change vision model (env/flag) | No effect | Miss |
| `--force-clip-selection` | Always run LLM | — |
| `--force-layout-vision` | — | Always run vision |

---

## CLI flags (pipeline-related)

| Flag | Maps to |
|------|---------|
| `--gemini-model` | `PipelineConfig.gemini_model` |
| `--gemini-vision-model` | `PipelineConfig.gemini_vision_model` |
| `--force-clip-selection` | `force_clip_selection` |
| `--force-layout-vision` | `force_layout_vision` |
| `--work-dir`, `--cache-root`, `--no-video-cache` | work dir / cache |

See `humeo.cli` for the full parser.
