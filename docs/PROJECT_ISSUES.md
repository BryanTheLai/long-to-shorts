# Project Issues Overview

This is the consolidated issue inventory for this repo as of **2026-04-20**.
It separates:

- **Confirmed runtime gaps**: current code does not do the desired thing.
- **Open backlog**: desired capabilities that are documented but not built.
- **Doc drift**: docs disagree with current code or with each other.

Read this after [`PIPELINE.md`](PIPELINE.md) if you want the blunt picture.

---

## Executive summary

The biggest current product gaps are:

1. **Clip selection is still transcript-only.** Visual context does not influence which clips get selected.
2. **Layout vision still sees one midpoint keyframe per clip.** It cannot react to layout changes inside a clip.
3. **Gemini still gets bbox coordinates in normalized `[0,1]` format.** There is no Gemini-facing `[0,1000]` adapter yet.
4. **Malformed bbox output is silently dropped.** The pipeline degrades safely, but not audibly.
5. **Ranking contract is still incomplete.** The prompt asks for `reasoning` / `score_breakdown`, but runtime ranking ignores them.
6. **Several docs are stale.** The repo now mixes "current truth", "north star", and "already fixed" in a way that is easy to misread.

Your two requested additions are already real open issues in the repo:

- **Many keyframes per clip + key-change detection**: not built.
- **Gemini-facing bbox `[0,1000]` instead of `[0,1]`**: not built.

---

## A. Confirmed runtime gaps

| ID | Issue | Evidence | Why it matters |
|----|-------|----------|----------------|
| R1 | **Clip selection has no visual context.** | [`src/humeo/pipeline.py`](../src/humeo/pipeline.py) runs Stage 2 clip selection before any keyframe extraction or layout vision; [`docs/TODO.md`](TODO.md) says `narrative_context.json` before clip selection is **not built**. | The selector cannot use chart appearances, slide OCR, scene changes, or on-screen structure when choosing clips. |
| R2 | **One midpoint keyframe per clip.** | [`src/humeo/pipeline.py`](../src/humeo/pipeline.py) builds one `Scene` per clip for Stage 3; [`humeo-core/src/humeo_core/primitives/ingest.py`](../humeo-core/src/humeo_core/primitives/ingest.py) `extract_keyframes()` samples exactly one frame at the midpoint. | A 50-90s clip can change layout, chart, speaker count, or lighting inside the clip, but the model only sees one frozen frame. |
| R3 | **No intra-clip key-change detector.** | There is no runtime stage that detects layout changes inside a selected clip; [`docs/TODO.md`](TODO.md) still tracks this as open work. | Even if more frames were sampled, there is no built decision rule yet for where they should come from or how to merge them. |
| R4 | **Gemini-facing bbox contract is still `[0,1]`, not `[0,1000]`.** | [`src/humeo/layout_vision.py`](../src/humeo/layout_vision.py) prompt explicitly requires normalized `0..1` coords; [`humeo-core/src/humeo_core/schemas.py`](../humeo-core/src/humeo_core/schemas.py) `BoundingBox` validates only `0..1`. | This is a brittle model boundary. Your requested Gemini-friendly integer coordinate contract is not implemented yet. |
| R5 | **Malformed bbox output is silently dropped.** | [`src/humeo/layout_vision.py`](../src/humeo/layout_vision.py) `_parse_bbox()` catches `Exception` and returns `None` with no warning. | The pipeline does not crash, but a near-miss model output can be discarded silently and make diagnosis harder. |
| R6 | **Ranking ignores `reasoning` and `score_breakdown`.** | [`src/humeo/prompts/clip_selection_system.jinja2`](../src/humeo/prompts/clip_selection_system.jinja2) asks for both; [`humeo-core/src/humeo_core/schemas.py`](../humeo-core/src/humeo_core/schemas.py) `Clip` has neither; [`src/humeo/clip_selector.py`](../src/humeo/clip_selector.py) ranks only on `virality_score` and `needs_review`. | The prompt implies auditable rule-based ranking, but runtime throws that audit trail away. |
| R7 | **`shorts_title`, `description`, and `hashtags` are persisted but unused.** | [`humeo-core/src/humeo_core/schemas.py`](../humeo-core/src/humeo_core/schemas.py) `Clip` includes them; [`docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`](KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md) documents that runtime does not use them. | Extra model tokens are being spent on metadata that does not affect render or export. |
| R8 | **Hook windows do not change the render in-point.** | [`src/humeo/render_window.py`](../src/humeo/render_window.py) says trim changes export bounds, hook fields do not. | If the intended product behavior is "open at the actual hook", the current code does not do that. |
| R9 | **Layout vision cache over-invalidates.** | [`src/humeo/layout_vision.py`](../src/humeo/layout_vision.py) hashes the entire `clips.json` file, and [`docs/ENVIRONMENT.md`](ENVIRONMENT.md) says any byte change invalidates the layout cache. | Non-layout metadata edits can trigger unnecessary Gemini vision reruns even when keyframes are unchanged. |
| R10 | **Gemini calls use JSON mode, not `response_schema`.** | [`src/humeo/clip_selector.py`](../src/humeo/clip_selector.py) and [`src/humeo/layout_vision.py`](../src/humeo/layout_vision.py) call Gemini with `response_mime_type="application/json"` but no `response_schema`. | Schema enforcement happens after the model call instead of at the provider boundary. |
| R11 | **No end-to-end canonical-video integration test.** | [`docs/SOLUTIONS.md`](SOLUTIONS.md) still lists this as a known gap; current tests are mostly unit and component level. | The repo lacks one high-confidence regression test over the real target workflow. |

---

## B. Open backlog that is documented but not built

These are not hidden bugs. They are openly documented "next capabilities" that are still missing.

| ID | Backlog item | Where documented | What is missing |
|----|--------------|------------------|-----------------|
| B1 | **`narrative_context.json` before clip selection** | [`docs/TODO.md`](TODO.md) | No Stage 1.5 artefact yet; clip selection still depends only on transcript. |
| B2 | **Many keyframes per clip** | [`docs/TODO.md`](TODO.md), [`docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`](KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md) | No multiple candidate frames per clip and no merge/vote/timeline design implemented. |
| B3 | **Key-change detection inside a clip** | [`docs/TODO.md`](TODO.md) | No detector for scene cuts, color/histogram shifts, light-intensity changes, OCR changes, person-count changes, or layout-class changes. |
| B4 | **Gemini-facing bbox `[0,1000]` with internal normalization back to `[0,1]`** | [`docs/TODO.md`](TODO.md), [`docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`](KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md) | No Gemini-specific bbox schema or adapter exists yet. |
| B5 | **Rule-scored clip selection stored in schema** | [`docs/TODO.md`](TODO.md), [`docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`](KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md) | No `rule_scores` / `selection_reason` fields on `Clip`; no composite ranking logic in code. |
| B6 | **Cross-episode memory module** | [`docs/SOLUTIONS.md`](SOLUTIONS.md), [`docs/TODO.md`](TODO.md) | No memory/state layer beyond the current work directory and caches. |

---

## C. Documentation drift and contradictions

These do not always mean code is broken. They mean the repo is harder to reason about than it should be because different docs describe different states.

| ID | Doc issue | Evidence | What should be treated as truth |
|----|-----------|----------|---------------------------------|
| D1 | **Letterboxing is described as still open, but code/tests indicate it is already fixed.** | [`docs/TODO.md`](TODO.md) and [`docs/podcast-to-shorts.md`](podcast-to-shorts.md) still talk about letterboxing as a gap; [`humeo-core/src/humeo_core/primitives/layouts.py`](../humeo-core/src/humeo_core/primitives/layouts.py) uses `force_original_aspect_ratio=increase` + `crop`; [`humeo-core/tests/test_layouts.py`](../humeo-core/tests/test_layouts.py) asserts "no letterbox bars". | Treat current layout code and tests as truth; the roadmap docs need cleanup. |
| D2 | **`TARGET_VIDEO_ANALYSIS.md` still says the product uses the heuristic scene-classification path.** | [`docs/TARGET_VIDEO_ANALYSIS.md`](TARGET_VIDEO_ANALYSIS.md) says that directly; [`src/humeo/pipeline.py`](../src/humeo/pipeline.py) Stage 3 calls Gemini layout vision. | The product path now uses Gemini vision for per-clip layout. |
| D3 | **`TARGET_VIDEO_ANALYSIS.md` still talks about a "three-way ffmpeg filtergraph".** | [`docs/TARGET_VIDEO_ANALYSIS.md`](TARGET_VIDEO_ANALYSIS.md) says that; current layout prompt and schemas support five layouts. | The current product has five layout kinds. |
| D4 | **`SOLUTIONS.md` describes a more HIVE-like ordering than the product currently ships.** | [`docs/SOLUTIONS.md`](SOLUTIONS.md) says "scene segmentation + keyframes first, then LLM reasons over scene narratives"; [`src/humeo/pipeline.py`](../src/humeo/pipeline.py) still does transcript-only clip selection before any visual narrative artefact. | Treat [`PIPELINE.md`](PIPELINE.md) and code as runtime truth; treat `SOLUTIONS.md` partly as design history / intended direction. |
| D5 | **The bbox contract is described inconsistently across docs.** | [`docs/SOLUTIONS.md`](SOLUTIONS.md) invariant says all bboxes are normalized `[0,1]`; [`docs/TODO.md`](TODO.md) and [`docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`](KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md) argue for Gemini-facing `[0,1000]` ints with internal normalization. | The current runtime truth is `[0,1]` end-to-end. The desired future split contract is not implemented yet. |
| D6 | **The repo mixes "current truth" and "north star" without one obvious separator.** | `PIPELINE.md`, `TODO.md`, `SOLUTIONS.md`, `TARGET_VIDEO_ANALYSIS.md`, and `podcast-to-shorts.md` each describe a different level of reality. | Use `PIPELINE.md` for runtime, this file for issues, `TODO.md` for not-built roadmap, `SOLUTIONS.md` for design history. |

---

## D. Clear current-state picture

If you want the shortest accurate description of the project **today**, it is:

1. **What works today**
   - Ingest, transcript, Gemini clip selection, hook detection, content pruning, per-clip Gemini layout vision, subtitles, and ffmpeg render.
   - Split-layout rendering currently uses cover-scale plus crop, not letterbox-fit.
   - There are unit/component tests around ranking, caching, layout planning, bbox parsing, server tools, and rendering primitives.

2. **What is still weak today**
   - Clip selection still does not see visuals before choosing windows.
   - Layout vision still assumes one representative frame per clip.
   - Gemini bbox output handling is still using the older normalized contract and a silent-drop parser.
   - The ranking prompt is richer than the ranking code.
   - Docs still blur the line between "shipped", "desired", and "outdated".

3. **What to fix first if output quality is the priority**
   - Add pre-selection multimodal context.
   - Replace one-keyframe-per-clip with many-keyframes-per-clip plus a key-change detector.
   - Move Gemini bbox IO to `[0,1000]` ints and normalize internally.
   - Add `response_schema` to Gemini calls.
   - Clean stale docs so the repo tells one story.

---

## Recommended reading order from here

1. [`PIPELINE.md`](PIPELINE.md) for current runtime behavior.
2. [`KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`](KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md) for prompt-vs-code mismatches.
3. [`TODO.md`](TODO.md) for planned upgrades.
4. [`SOLUTIONS.md`](SOLUTIONS.md) for design history and rejected alternatives.

