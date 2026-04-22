# SOLUTIONS.md — Full Decision Log

The design record for this repo. What we tried, what broke, what we chose, and why. Blunt.

---

## 1. What this repo does

Takes a long podcast/interview video (YouTube URL or local MP4) and produces multiple 9:16 vertical shorts with burned subtitles and a title card.

Two cooperating Python packages:

- **`humeo-core/`** (import `humeo_core`) — Reusable deterministic primitives + strict JSON schemas, exposed as MCP tools. Treats editing as a composable pipeline of narrow, testable functions. The `humeo-mcp` console script is still registered as an **alias** for existing MCP configs.
- **`src/humeo/`** — Thin end-to-end product wrapper. It handles download, transcript, clip selection, subtitle generation, then delegates final rendering to `humeo-core`.

Design spine: HIVE (ByteDance, 2507.02790v1). See `docs/hive-paper/PAPER_BREAKDOWN.md` for the first-principles write-up.

---

## 2. Problem → solution map

| # | Problem                                                                                  | What we picked                                                                           | Why                                                                                   |
|---|------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| 1 | Transcripts alone produce bad cuts (mid-sentence, abrupt, no visual context).            | Scene segmentation + keyframes first, then LLM reasons over scene narratives.            | HIVE §3.1. Cuts land on semantic boundaries, not word boundaries.                     |
| 2 | Single-LLM "pick 5 shorts from this transcript" gives incoherent output.                 | Decomposed editing: highlight / opening-ending / pruning as separate narrow tool calls.  | HIVE §3.2. LLMs fail softly on vague tasks, sharply on narrow ones.                   |
| 3 | Free-form LLM JSON breaks downstream code.                                               | Pydantic schemas at every hop. Every primitive reads and writes strict types.            | Makes failures loud and early. Tests don't need video fixtures.                       |
| 4 | The repo had two overlapping runtime paths. | Kept one primary render path: `src/humeo` now wraps `humeo-core`'s ffmpeg renderer. | Less code, less duplication, clearer ownership.                                       |
| 5 | How to decide *per-clip* whether to use `zoom_call_center`, `sit_center`, or `split_chart_person`? | Multiple swappable detectors, all emitting the same `SceneRegions` bbox schema.         | Detector is an impl detail. Layout planner and renderer are unchanged.                |
| 6 | Face-tracking in Python per-frame is slow and brittle.                                   | Detect once per scene keyframe, apply one ffmpeg filtergraph per clip.                   | O(scenes) model calls instead of O(frames). Renders deterministic.                   |
| 7 | MCP server didn't even import on installed `mcp 1.1.2`.                                  | Bumped to `mcp[cli]>=1.2.0`; `test_server_tools.py` now runs clean.                      | Pre-existing bug. Fixed while we were here.                                           |
| 8 | `Clip` dataclass existed in two places with subtly different fields.                     | Made Pydantic `Clip` in `humeo_core.schemas` the single source of truth.                  | One type, one validation, one JSON shape.                                             |
| 9 | `__pycache__/`, `egg-info/` were being committed.                                        | Added `.gitignore`, staged clean-up.                                                     | Stops polluting the repo history.                                                    |

---

## 3. The "detect regions → classify → render" pipeline (unified)

Three *interchangeable* region detectors. One output schema. One downstream path.

```
                      ┌────────────────────────┐
                      │    scene keyframes     │
                      └───────────┬────────────┘
                                  │
                 ┌────────────────┼────────────────────────────────┐
                 │                │                                │
                 ▼                ▼                                ▼
      ┌───────────────────┐  ┌────────────────┐     ┌────────────────────────────┐
      │ classify.py       │  │ face_detect.py │     │ vision.py                  │
      │ (pixel heuristic) │  │ (MediaPipe)    │     │ (vision LLM + OCR bboxes)  │
      └─────────┬─────────┘  └───────┬────────┘     └──────────────┬─────────────┘
                │                    │                             │
                └──────────┬─────────┴─────────────────────────────┘
                           │    all emit  SceneRegions
                           ▼
                  ┌─────────────────────────┐
                  │ classify_from_regions   │  → SceneClassification (LayoutKind)
                  └────────────┬────────────┘
                               ▼
                  ┌───────────────────────────────┐
                  │ layout_instruction_from_regions│  → LayoutInstruction
                  └────────────┬──────────────────┘
                               ▼
                  ┌───────────────────────────────┐
                  │ compile.render_clip           │  → one ffmpeg call per clip
                  └───────────────────────────────┘
```

The detector is a knob. The renderer is fixed. That is the single most important property of this design.

---

## 4. Bryan's "big screen change → v3 images → LLM + OCR → bbox" idea

Bryan's exact idea, then the implementation.

> "What if I just detect huge screen changes, then I'll have v3 images, send each to LLM with OCR then get the bbox for them?"

Translated into a clean primitive:

1. **"Huge screen changes" = scene detection.** PySceneDetect already runs at ingest time and emits one keyframe per scene. That is the "v3 image" set, for free, with no pixel code in Python.
2. **"Send each to LLM with OCR"** = one structured multimodal call over the sampled image set, with a prompt/schema that *forces* JSON output containing bounding boxes **and** OCR-like region reasoning.
3. **"Get the bbox for them"** = structured output:
   - model-facing `person_bbox` / `chart_bbox` in the 0..1000 contract
   - internal normalized `[0,1]` boxes after parse
   - `ocr_text`
   - `reason`
4. **Drive the layout:** `person_x_norm` comes from `person_bbox.center_x`. `chart_x_norm` comes from `chart_bbox.x1`. `LayoutKind` is derived from which bboxes are present and how wide they are. The product wrapper now applies the same idea to multi-frame clip sampling in `src/humeo/layout_vision.py`.

This is now implemented in three files:

- `humeo-core/src/humeo_core/schemas.py` — `BoundingBox` + `SceneRegions` Pydantic models.
- `humeo-core/src/humeo_core/primitives/vision.py` — the primitive itself:
  - `REGION_PROMPT` — the exact prompt sent to the LLM, forcing strict JSON.
  - `detect_regions_with_llm(scenes, vision_fn)` — pluggable. Caller supplies the model.
  - `classify_from_regions(regions)` — bbox geometry → `LayoutKind` + confidence.
  - `layout_instruction_from_regions(regions, classification)` — bbox geometry → `LayoutInstruction` with `person_x_norm` / `chart_x_norm` populated.
  - `classify_scenes_with_vision_llm` — one-shot helper.
- `humeo-core/src/humeo_core/server.py` — MCP tools:
  - `humeo.detect_scene_regions` — returns the prompt and per-scene jobs so the agent can run its own vision model.
  - `humeo.classify_scenes_with_vision` — takes the agent's bbox JSON back and returns `SceneClassification` + `LayoutInstruction`.

Validated by 15 tests in `humeo-core/tests/test_vision.py` plus 2 server-tool tests.

### Why this shape (and not "run MediaPipe in a loop")

| Trade-off              | MediaPipe per-frame                              | Scene-change + LLM + OCR                                              |
|------------------------|--------------------------------------------------|-----------------------------------------------------------------------|
| Model calls            | O(frames) ≈ 30 × clip_length                    | **O(scenes)** ≈ 5–30 per clip                                         |
| Catches screen content | No (face only)                                   | **Yes** — OCR reads titles, chart labels, slides                      |
| Catches slides/screenshare | No                                           | **Yes**                                                               |
| Works on still charts  | No (no face → falls through to blurred pad)      | **Yes**                                                               |
| Local CPU cost         | High                                             | ~zero                                                                 |
| Cost per clip          | 0                                                | ~$0.001 (1–5 cents for full podcast) using a cheap vision model       |
| Smoothness             | Native (per-frame)                               | One decision per scene — uses ffmpeg `zoompan` for in-scene motion    |

Bryan's idea is correct and the implementation costs almost nothing compared to per-frame ML.

### Where it fits in HIVE's taxonomy

This is the **Comprehensive Caption** module (§3.1.5) specialized for layout, plus a lightweight **Character Extraction** (§3.1.1) via the `person_bbox`. OCR corresponds to the dialogue-reconciliation role OCR plays in HIVE §3.1.2 — here, used for chart axis text and title overlays.

---

## 5. What we considered and rejected (and why)

### 5.1 "Give the whole transcript to GPT-4, ask for 5 shorts"
**Rejected.** HIVE Table 2 shows VEI 0.54 (ASR end-to-end) vs 4.01 (HIVE full). 7.4× worse. Also reproducibly terrible in our own pilot runs.

### 5.2 "Run MediaPipe on every frame"
**Rejected as the primary product path.** Good for smooth tracking, bad for code simplicity, slow on CPU, and redundant once the engine owned the stable ffmpeg renderer.

### 5.3 "Merge `src/humeo/` into `humeo-core/`"
**Rejected.** Disruptive. The two packages have different surfaces (CLI orchestrator vs MCP server). Clean dependency edge (`humeo` → `humeo-core`) is enough.

### 5.4 "Merge `humeo-core/` into `src/humeo/`"
**Rejected.** `humeo-core` is independently useful for any MCP client (Cursor, Claude Desktop). Burying it inside the podcast pipeline kills that value.

### 5.5 "Hard-code the vision LLM to Gemini (or OpenAI)"
**Rejected.** The vision primitive takes `LLMRegionFn = Callable[[str, str], str]`. Caller supplies the provider. Tests pass stubs. Swap at runtime.

### 5.6 "Train our own scene classifier"
**Rejected.** HIVE §8 explicitly warns against this for the podcast-to-shorts scope. Three-branch rule-based classification (via bboxes) gets us to ship quality with zero training data.

### 5.7 "Use MediaPipe face bbox → `SceneRegions` too"
**Kept.** `humeo-core/src/humeo_core/primitives/face_detect.py` is the local CPU detector that emits the same `SceneRegions` schema as the LLM path. All three detectors (heuristic, MediaPipe, LLM) are interchangeable.

### 5.8 "Run pruning as a fourth sub-task"
**Pending.** HIVE Module B has three sub-tasks (highlight / boundary / pruning). We do highlight and boundary today. Pruning is a one-prompt extension that can sit between Stage 2 (clip select) and Stage 3 (cut).

---

## 6. Technical decision log (chronological)

1. **Staged uncommitted `src/humeo/` noticed.** Ran `git status`, `git log --all --oneline`, `git branch -a`. Confirmed `main`, `origin/cursor/*` all merged; `src/humeo/` was uncommitted parallel work.
2. **Added `.gitignore`.** Python cache, egg-info, `.humeo_work/`, `output/`, IDE files, secrets. Unstaged the committed cache.
3. **Deduplicated `Clip`.** `src/humeo/clip_selector.py` now imports `Clip` / `ClipPlan` from `humeo_core.schemas`. `cutter.py`, `pipeline.py` updated too. `_parse_clips` gracefully strips `duration_sec` (computed property in Pydantic) from LLM JSON before validation.
4. **Added `BoundingBox` + `SceneRegions`.** Pydantic models with validators (`x2 > x1`, `y2 > y1`). Computed properties `center_x`, `center_y`, `width`. Normalized coords keep the schema resolution-independent.
5. **Implemented `primitives/vision.py`.** `LLMRegionFn`, `REGION_PROMPT`, `detect_regions_with_llm`, `classify_from_regions`, `layout_instruction_from_regions`, `classify_scenes_with_vision_llm`. Every parse failure degrades to an empty `SceneRegions` with `raw_reason` — never raises.
6. **Exposed two new MCP tools.** `detect_scene_regions` (returns prompt + jobs) and `classify_scenes_with_vision` (takes bbox JSON back, returns classifications + `LayoutInstruction`s). Deterministic — server never calls an LLM itself, agent does.
7. **Added `primitives/face_detect.py`.** MediaPipe path that emits `SceneRegions`. Uses a pluggable `FaceBBoxFn` so tests don't need MediaPipe installed. Synthesizes a chart bbox when the face is pushed right of `chart_split_threshold` (matches the original `reframe.py` heuristic).
8. **Wrote 21 new tests.** `test_vision.py` (15), `test_face_detect.py` (6), plus 2 new server-tool tests. All pass.
9. **Fixed pre-existing MCP import bug.** `from mcp.server.fastmcp import FastMCP` didn't exist in `mcp 1.1.2`. Bumped to `mcp[cli]>=1.2.0`; upgraded installed copy; `test_server_tools.py` now collects and runs.
10. **Made `src/humeo/reframe_ffmpeg.py` the only product render path.** It is now a thin adapter that builds a `LayoutInstruction` from the shared `Clip` schema and calls `humeo_core.primitives.compile.render_clip`.
11. **Collapsed the root pipeline.** Removed the extra cut/reframe/finish pass. The product pipeline now matches **`docs/PIPELINE.md`**: ingest → clip selection → hook detection → content pruning → layout vision → ASS captions → final render.
12. **Wired top-level pytest.** Root `pyproject.toml` now has `testpaths = ["tests", "humeo-core/tests"]`. `tests/test_reframe_ffmpeg.py` covers the adapter.
13. **Ran ruff --fix.** Removed dead imports and kept the suite green.
14. **Renamed package folder `humeo-mcp/` → `humeo-core/`** and Python package `humeo_mcp` → `humeo_core`. PyPI/local project name is `humeo-core`. Console entry points: **`humeo-core`** (primary) and **`humeo-mcp`** (same `main()`, for backward-compatible MCP client configs).

---

## 7. Architecture as it stands today

**Layout:** `src/humeo/` (CLI + pipeline) depends on `humeo-core/` (schemas, primitives, MCP server). Product stages are **`docs/PIPELINE.md`**; this section is not a second pipeline spec.

**Directory tree:** Use the repo as checked out on disk (`tree` / IDE). **Markdown index:** [`docs/README.md`](README.md).

---

## 8. Tests

Run from repo root:

```bash
uv run pytest
```

Per-package discovery (counts change as tests are added):

```bash
uv run pytest humeo-core/tests --collect-only -q
uv run pytest tests --collect-only -q
```

Do not treat a frozen row-count table in git as the source of truth—**pytest is**.

---

## 9. Known gaps (pending work, sized)

**Update (2026-04-19):** Inner-clip **content pruning** (HIVE-style Rₚ at clip scale) and **hook detection** ship in `src/humeo/pipeline.py` — see **`docs/PIPELINE.md`**. The row below on pruning was written before that landed; it is kept struck-through for history.

Prompt-vs-code gaps (e.g. `score_breakdown` not ranked, unused `shorts_title` / `hashtags`) live in **`docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`**.

| Gap                                                             | Effort | Impact |
|-----------------------------------------------------------------|--------|--------|
| ~~`Content Pruning` sub-task (HIVE §3.2.3) not yet implemented.~~ **Shipped** (`content_pruning.py`, Stage 2.5). | — | — |
| Memory module (HIVE §3.1.6) for multi-episode state.            | ~2 day | Required if we extend to full drama series.                               |
| ~~Vision-LLM provider wiring (Gemini/OpenAI client).~~ **Shipped** via `src/humeo/llm_provider.py`. | — | Product stages 2 / 2.25 / 2.5 / 3 now share the same provider-swappable transport (`gemini`, `openai`, `azure`). |
| End-to-end integration test on the target Cathie Wood video.    | ~1 hr  | Manual regression run exists; an automated committed test is still missing. See `TARGET_VIDEO_ANALYSIS.md` for why that video is the canonical test case. |
| Pruning + Memory are what close the remaining HIVE gap to human.| —      | See `docs/hive-paper/PAPER_BREAKDOWN.md` §8.                                              |

---

## 10. Invariants to preserve

Anyone editing this repo in the future: don't violate these.

1. **Every LLM call must return JSON that validates against a Pydantic model.** No free-form text in the pipeline.
2. **Every primitive is one file, one job.** No god-modules.
3. **Internal/runtime bbox coordinates are normalized [0, 1].** Stage 3 may accept model-facing 0..1000 boxes, but nothing downstream of the parser should depend on pixels.
4. **Detectors are swappable; renderer is fixed.** If you add a fourth detector, it must emit `SceneRegions`.
5. **Keep the product wrapper thin.** New reusable media logic belongs in `humeo-core`, not in `src/humeo`.
6. **Cache aggressively.** Work dir layout and env vars: **`docs/ENVIRONMENT.md`**. Retries should re-run model calls only, not deterministic extraction.
7. **Schemas live in `humeo_core.schemas`. One source of truth.**

---

## 11. Bottom line

The repo now embodies HIVE's architecture: staged reasoning, strict schemas, narrow primitives, decomposed editing, one-file-per-job. Bryan's scene-change + LLM-OCR-bbox idea is implemented as a first-class primitive that plugs into exactly the same downstream pipeline as the heuristic and MediaPipe detectors. Tests prove it. Documentation explains it. No workarounds, no dangling threads.
