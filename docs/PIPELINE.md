# Product pipeline: stages, caches, and JSON contracts

This document describes **`humeo.pipeline.run_pipeline`**: what runs when, what is cached, what each structured LLM stage returns, and how data flows into ffmpeg.

**Other docs:** index at [`README.md`](README.md) in this folder. Prompt-vs-code gaps (e.g. ranking): [`KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`](KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md).

Visual map (HIVE-inspired, static HTML): [hive_architecture_visualization.html](hive_architecture_visualization.html) — also hosted via GitHub Pages if your fork enables it (see [SHARING.md](SHARING.md)).

## High-level flow

```
YouTube URL
    → Stage 1:    Ingest (download, transcript)
    → Stage 2:    Clip selection (structured LLM JSON → over-generate pool → rank → clips.json)
    → Stage 2.25: Hook detection (structured LLM JSON → hooks.json, overwrites clip.hook_start/end)
    → Stage 2.5:  Content pruning (structured LLM JSON → prune.json, writes clip.trim_start/end)
    → Stage 3:    Keyframes + layout vision (structured multimodal JSON → LayoutInstruction per clip)
    → Stage 4:    Render (ffmpeg per clip → output/short_<id>.mp4)
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

## Stage 2: Clip selection (provider-swappable structured LLM, text-only)

**Goal:** `clips.json` - ranked viral segments with timings and metadata.

**Cache / reuse model**

Clip selection has two reuse layers:

1. **Full cache hit** - if `clips.meta.json` says the transcript fingerprint, provider/model transport, and ranking policy all still match, the pipeline loads `clips.json` and makes no LLM call.
2. **Re-rank hit** - if the transcript and provider/model still match but the ranking policy changed, the pipeline reuses `clip_selection_raw.json`, re-parses the candidate pool, and re-ranks locally without paying for another model call.

The full cache is bypassed when `force_clip_selection` is true.

**Artifacts**

| File | Contents |
|------|----------|
| `clips.meta.json` | `version` (4), `transcript_sha256`, `llm`, `ranking_policy_sha256`, `ranking_policy` |
| `clip_selection_raw.json` | Verbatim raw candidate-pool JSON returned by the LLM |
| `clips.json` | Parsed and ranked list of shared `Clip` models |

**Structured LLM call** (`humeo.clip_selector.select_clips`)

- Provider/model resolution flows through `humeo.llm_provider`.
- **System:** Jinja template `clip_selection_system.jinja2` (package: `src/humeo/prompts/`).
- **User:** transcript lines built from `transcript["segments"]` as `[start-end] text` (`build_prompt`).
- **Schema:** `response_schema=ClipSelectionResponse`.
- **Temperature:** `0.7` by default so the model returns a wider candidate pool instead of the same obvious five windows every run.
- Retries: `LLM_MAX_ATTEMPTS = 3`, `LLM_RETRY_DELAY_SEC = 2.0` with backoff.

**Expected JSON shape (clip selection)**

Top-level object with `"clips": [ ... ]` (or a bare array - parser accepts both). Each item first validates as `_ClipSelectionCandidate`, then is converted into the shared `humeo_core.schemas.Clip`.

Important fields beyond the old v1 contract:

- `selection_reason`
- `rule_scores` with the five downstream-consumed rule ids
- `layout_hint`
- `hook_*` and `trim_*` placeholders for later stages

**Constants (from `humeo.config`)**

- `MIN_CLIP_DURATION_SEC` = **50**
- `MAX_CLIP_DURATION_SEC` = **90**
- `TARGET_CLIP_COUNT` = **5** (used as the ranker's default `min_kept`)
- Default Gemini fallback model = **`gemini-3.1-flash-lite-preview`** if the provider is Gemini and no explicit model is supplied

**Over-generate + rank (default policy)**

Rather than asking the model for exactly 5 clips every run, the selector asks for a candidate **pool** and keeps the best ones with a threshold + floor + cap:

| Setting | Default | `PipelineConfig` field |
|---------|---------|------------------------|
| Candidate pool size | 12 | `clip_selection_candidate_count` |
| Sampling temperature | 0.7 | (hard-coded in `select_clips`) |
| Quality threshold (score) | 0.70 | `clip_selection_quality_threshold` |
| Minimum clips to ship | 5 | `clip_selection_min_kept` |
| Maximum clips to ship | 8 | `clip_selection_max_kept` |

Policy (implemented in `humeo.clip_selector.rank_and_filter_clips`):

1. Sort by `virality_score` desc; clips with `needs_review=True` take a
   priority penalty so they fall behind same-score non-reviewed clips.
2. Keep every clip with `virality_score ≥ threshold` that isn't reviewed.
3. If fewer than `min_kept` cleared the threshold, backfill from the next
   best candidates so the pipeline never ships zero shorts on a weak
   transcript.
4. Cap the final list at `max_kept`. Exceptionally rich transcripts ship
   more than 5 shorts instead of being artificially capped.
5. Renumber `clip_id` to `001..NNN` in rank order so downstream artifacts
   (keyframes, subtitles, filenames) stay dense and ordered.

**Rank signal:** the ranker still sorts on `virality_score`, but `virality_score` is now derived from the weighted composite of `rule_scores` when those structured rule outcomes are present. `needs_review=True` still pushes a candidate behind same-score non-reviewed clips.

The raw LLM response is cached verbatim (`clip_selection_raw.json`), so you can re-rank a cached pool without another LLM call by editing the ranking thresholds or weights.

---

## Stage 2.25: Hook detection (provider-swappable structured LLM, text-only)

**Goal:** Overwrite each clip's `hook_start_sec` / `hook_end_sec` with a
real, localised hook sentence window. The clip-selection LLM almost always
echoes the `[0.0, 3.0]` placeholder from the prompt, which (pre-P1) silently
disabled every start-trim in Stage 2.5 — the clamp refused to trim past a
hook_start of 0.0.

**How it's wired in** — `humeo.hook_detector.run_hook_detection_stage`:

- Runs **after** clip selection and **before** content pruning.
- Single batched structured LLM call: takes every clip's clip-relative segments
  plus the selector's guessed hook text, returns one hook window per clip.
- Validates each window against:
  - `0 ≤ hook_start < hook_end ≤ clip.duration_sec` (±0.5s rounding grace).
  - `1.0s ≤ hook_end − hook_start ≤ 10.0s`.
  - **Not** the `[0.0, 3.0]` fingerprint — the whole point of this stage.
- Rejected / missing decisions leave the clip untouched; Stage 2.5's
  fingerprint guard treats any remaining `[0.0, 3.0]` as "no hook" so
  pruning still runs.
- Any LLM failure is logged and treated as a no-op (pipeline keeps going).

**When the LLM is skipped (cache hit)**

- `hooks.meta.json` + `hooks.json` exist **and**
- `transcript_sha256` matches **and**
- `clips_sha256` matches (hash of clip **windows**, hook-independent) **and**
- `llm` identity matches **and**
- `force_hook_detection` is false

**Artifacts**

| File | Contents |
|------|----------|
| `hooks.meta.json` | `version` (2), `transcript_sha256`, `clips_sha256`, `llm` |
| `hooks_raw.json` | Raw string returned by the stage LLM (audit) |
| `hooks.json` | `{ "hooks": [{clip_id, hook_start_sec, hook_end_sec, hook_text, reason}, ...] }` |

**Kill switch**

- `--no-hook-detection` sets `detect_hooks=False`. The selector's hook
  (possibly a placeholder) is carried through unchanged; Stage 2.5 still
  works correctly because of the placeholder fingerprint guard in
  `content_pruning._looks_like_default_hook`.

---

## Stage 2.5: Content pruning (provider-swappable structured LLM, text-only)

**Goal:** Tighten each selected clip by trimming weak lead-in / trailing
content. This is HIVE's "irrelevant content pruning" sub-task applied at the
**inner-clip** scale (not scene scale) — the cleanest win for watchability on
50-90s talk-heavy shorts.

**How it's wired in** — `humeo.content_pruning.run_content_pruning_stage`:

- Runs **after** clip selection (`clips.json` is finalized) and **before**
  keyframe extraction, because keyframes are sampled from
  `clip_for_render(clip)` which already honours `trim_start_sec` /
  `trim_end_sec`.
- Writes per-clip trims into the existing `Clip.trim_start_sec` /
  `Clip.trim_end_sec` fields. **No schema changes.** The existing
  `humeo.render_window` + `humeo_core.primitives.compile` path cuts with
  `-ss` / `-t` from those fields, so the tightened window renders for free.

**Aggressiveness** — `config.prune_level` ∈ {`off`, `conservative`, `balanced`, `aggressive`}:

| Level | Max total trim per clip | Intent |
|-------|------------------------|--------|
| `off` | 0% | Skip Stage 2.5 entirely |
| `conservative` | ≤10% | Dead-air, throat-clears, stutters, false starts |
| `balanced` (default) | ≤20% | +slow setup, self-correction, minor tangents |
| `aggressive` | ≤35% | +anything not advancing the hook or payoff |

**Hard guarantees** (clamped in Python after the LLM returns):

- Final duration ≥ `MIN_CLIP_DURATION_SEC` (50s).
- If `hook_start_sec` / `hook_end_sec` are set on the clip **and** the
  window is a real, localised hook (not the `[0.0, 3.0]` placeholder from
  the clip-selection prompt — see `_looks_like_default_hook`), the hook
  stays fully inside the tightened window (with a 0.25s safety margin on
  each side). Stage 2.25 is responsible for producing real windows; the
  placeholder fingerprint check here is the belt-and-suspenders guard for
  when hook detection is disabled or fails.
- Total trim ≤ per-level cap above.
- **Segment-boundary snapping.** After clamping, `trim_start_sec` and
  `trim_end_sec` are snapped to the nearest WhisperX segment edge within a
  3s tolerance (see `_snap_trims_to_segment_boundaries`). Preference is
  "finish the sentence" — for `trim_end`, land on the next segment end
  at-or-after the LLM's requested out-point so the clip never stops at
  "this could be…" mid-sentence. The snap is self-gated: any candidate
  that would violate min-duration, the level's max-pct cap, or a real
  hook window is reverted.
- Any LLM / transport failure is logged and degrades to no-op (0.0 / 0.0
  trims), so the pipeline never dies in Stage 2.5.
- Every non-trivial clamp (hook-protected, min-duration-protected,
  max-pct-protected, or any requested-vs-applied delta > 0.05s) is logged
  at INFO level so silent no-op stages become audible. Segment-boundary
  snaps are logged separately with a `prune boundaries snapped to segment
  edges` line so the post-clamp refinement is auditable.

**When the LLM is skipped (cache hit)**

- `prune.meta.json` + `prune.json` exist **and**
- `transcript_sha256` matches **and**
- `clips_sha256` matches (hash of clip windows, trim-independent) **and**
- `llm` identity matches **and**
- `prune_level` matches **and**
- `force_content_pruning` is false

**Artifacts**

| File | Contents |
|------|----------|
| `prune.meta.json` | `version` (3), `transcript_sha256`, `clips_sha256`, `llm`, `prune_level` |
| `prune_raw.json` | Raw string returned by the stage LLM (audit) |
| `prune.json` | `{"clips": [{clip_id, trim_start_sec, trim_end_sec}, ...]}` |

**Structured LLM call** (`humeo.content_pruning.request_prune_decisions`)

- Single batched call for all 5 clips.
- System prompt: `src/humeo/prompts/content_pruning_system.jinja2`.
- User message: per-clip block with `clip_id`, `duration_sec`, `topic`,
  optional `hook_window_sec`, and clip-relative segment lines
  (`[REL_START - REL_END] text`).
- `response_schema` validates the pruning response at the provider boundary.
- Retries: same as clip selection (3 attempts, exponential backoff).

**Expected JSON shape**

```json
{
  "decisions": [
    {
      "clip_id": "001",
      "trim_start_sec": 4.2,
      "trim_end_sec": 1.8,
      "reason": "Throat-clear and false start at the open; trailing tangent at the close."
    }
  ]
}
```

Bare-array form (`[{...}, {...}]`) is also accepted.

---

## Stage 3: Keyframes + layout vision (provider-swappable structured multimodal LLM)

**Goal:** Multiple sampled frames per clip under `work_dir/keyframes/`, then one merged **`LayoutInstruction`** per `clip_id` for render.

### 3a - Frame sampling

`humeo.layout_vision._sample_clip_frames` samples directly from the render window:

- Start from `clip_for_render(clip)` and `source_keep_ranges(...)`.
- Take **uniform coverage** timestamps across the kept ranges.
- Add **frame-diff peak** timestamps so obvious visual changes have a chance to influence the decision.
- Cap the total at **6 sampled frames per clip**.
- Write JPEGs under **`work_dir/keyframes/<clip_id>/`** and keep per-frame metadata (`frame_id`, `timestamp_sec`, `path`, `width`, `height`).

This stage imports `cv2`, which is why `opencv-python` is part of the default app dependency set.

### 3b - Layout vision

**When vision is skipped (cache hit)**

- `layout_vision.meta.json` + `layout_vision.json` exist **and**
- `transcript_sha256` matches **and**
- `clip_windows_sha256` matches **and**
- `llm` identity matches the resolved provider/model transport **and**
- `layout_policy_version` matches **and**
- `force_layout_vision` is **false**

-> reload `LayoutInstruction` objects from cache (`humeo.layout_vision.run_layout_vision_stage`).

**Resolved vision model**

`resolved_vision_model(config)` prefers, in order:

1. `config.llm_vision_model`
2. legacy `config.gemini_vision_model`
3. `HUMEO_LLM_VISION_MODEL`
4. `GEMINI_VISION_MODEL`
5. the resolved text-stage model

**Structured multimodal call** (`_call_gemini_vision`)

- Provider/model resolution still flows through `humeo.llm_provider`.
- The request sends every sampled frame as a labeled image (`FRAME {idx}: timestamp_sec=...`).
- `response_schema=_GeminiMultiFrameResponse`.
- Raw model output is kept alongside the parsed result for audit.

**Model JSON shape (layout vision)**

The exact contract lives in `GEMINI_LAYOUT_VISION_PROMPT` in `humeo.layout_vision`. It is now a **multi-frame** response:

```json
{
  "frames": [
    {
      "frame_index": 0,
      "timestamp_sec": 12.34,
      "layout": "zoom_call_center" | "sit_center" | "split_chart_person" | "split_two_persons" | "split_two_charts",
      "person_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
      "face_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
      "chart_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
      "second_person_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
      "second_face_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
      "second_chart_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
      "reason": "short rationale"
    }
  ],
  "merged": {
    "layout": "zoom_call_center" | "sit_center" | "split_chart_person" | "split_two_persons" | "split_two_charts",
    "person_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
    "face_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
    "chart_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
    "second_person_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
    "second_face_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
    "second_chart_bbox": {"x1": 0, "y1": 0, "x2": 1000, "y2": 1000} | null,
    "reason": "one merged rationale"
  }
}
```

**Mapping to `LayoutInstruction`** (`_instruction_from_gemini_json`)

- `layout` -> `LayoutKind` (invalid strings downgrade to `sit_center` with a warning).
- Bboxes accept:
  - the preferred **0..1000** model-facing coordinate scale
  - legacy normalized **[0,1]**
  - accidental pixel coords if the sampled frame size is known
- Parsed boxes are normalized back to the internal shared `BoundingBox` schema.
- For split layouts, the parser populates render-safe bbox fields such as:
  - `split_chart_region` / `split_person_region`
  - `split_second_person_region`
  - `split_second_chart_region`
- `face_bbox` is used to derive a tighter person crop for split-person layouts so the speaker's head is not cut off by a torso-heavy box.

**Failures and fallbacks**

- If **no sampled frames** are produced, Stage 3 now falls back to `clip.layout_hint` (or the clip's current `layout`) instead of blindly collapsing to `sit_center`.
- If the multimodal call fails after some frame instructions were produced, the stage chooses the dominant frame-level layout or falls back to `layout_hint`.
- Parser warnings and raw errors are written into the cache artifact so failures are visible after the run.

**Artifacts**

| File | Contents |
|------|----------|
| `layout_vision.meta.json` | `version`, `transcript_sha256`, `clip_windows_sha256`, `llm`, `layout_policy_version` |
| `layout_vision.json` | `{ "clips": { "<clip_id>": { "instruction": ..., "sampled_frames": [...], "frame_results": [...], "raw": ..., "warnings": [...] } } }` |

**Note:** `humeo_core.primitives.vision.classify_from_regions` still exists for MCP / other callers. The product pipeline now trusts the structured multimodal response plus the bbox adapter and merge logic above.

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

## Stage 4 title overlays (word-wrap + auto-shrink)

`humeo_core.primitives.compile.plan_title_drawtext` decides how to render
the clip's `suggested_overlay_title` before it hits ffmpeg's `drawtext`
filter (which does not wrap text on its own):

- Short titles that fit at **72px** render as a single `drawtext` call at
  `y=80` — byte-identical to the pre-P2 form (golden tests enforce this).
- Long titles are split at the **best word boundary** (most balanced
  halves) into two lines, shrunk to 60 / 52 / 44px until both lines fit
  within `width - 2 × 60px` of margin, and rendered as two stacked
  `drawtext` filters.
- Single-word titles that still overflow shrink the single line instead.
- The hard floor is 44px; if nothing fits even then, the title is
  truncated with an ellipsis.

This is what fixed the "Prediction Markets vs Derivatives" clipped-title
bug on the Cathy Wood run.

The title font is pinned to **Arial** via a `font=Arial` directive in the
`drawtext` filter (resolved through ffmpeg's fontconfig build), matching
the `Fontname=Arial` used by the ASS subtitle force-style below. Without
this directive, drawtext fell back to fontconfig's "Sans" alias, which on
default Windows installs resolves to Times New Roman — the "ugly serif
title on the finance shorts" bug that shipped in v1.

Titles are still suppressed on split layouts (`SPLIT_CHART_PERSON`,
`SPLIT_TWO_PERSONS`, `SPLIT_TWO_CHARTS`) because those already have a
baked-in title on the chart/slide.

---

## Quick reference: what invalidates which cache

| Change | Clip selection | Hook detection | Content pruning | Layout vision |
|--------|---------------|---------------|-----------------|---------------|
| Edit `transcript.json` (content) | Miss (hash) | Miss (hash) | Miss (hash) | Miss (hash) |
| Change clip windows / trims / keep ranges | N/A | Miss (`clips_sha256`) | Miss (`clips_sha256`) | Miss (`clip_windows_sha256`) |
| Change `--llm-model` | Miss | Miss | Miss | May still hit vision if the resolved vision model is unchanged |
| Change `--prune-level` | No effect | No effect | Miss | No effect |
| Change vision model (env/flag) | No effect | No effect | No effect | Miss |
| `--force-clip-selection` | Always run LLM | — | — | — |
| `--force-hook-detection` | — | Always run LLM | — | — |
| `--force-content-pruning` | — | — | Always run LLM | — |
| `--force-layout-vision` | — | — | — | Always run vision |

Note that changing only the hook on a clip does **not** invalidate the
pruning cache: `prune.meta.json`'s `clips_sha256` hashes only the clip
windows, so you can re-run hook detection without also re-running pruning.

---

## CLI flags (pipeline-related)

| Flag | Maps to |
|------|---------|
| `--llm-provider` | `PipelineConfig.llm_provider` |
| `--llm-model` | `PipelineConfig.llm_model` (`--gemini-model` is a legacy alias) |
| `--llm-vision-model` | `PipelineConfig.llm_vision_model` (`--gemini-vision-model` is a legacy alias) |
| `--force-clip-selection` | `force_clip_selection` |
| `--force-layout-vision` | `force_layout_vision` |
| `--no-hook-detection` | `detect_hooks = False` (Stage 2.25 skipped) |
| `--force-hook-detection` | `force_hook_detection` |
| `--prune-level` | `prune_level` (Stage 2.5 aggressiveness) |
| `--force-content-pruning` | `force_content_pruning` |
| `--work-dir`, `--cache-root`, `--no-video-cache` | work dir / cache |
| `--start-at`, `--stop-after` | Pipeline stage resume / stop controls |
| `--inspect-stage`, `--clip-id` | Stable stage-inspection output |

See `humeo.cli` for the full parser.
