# Known limitations, prompt–code contract gaps, and fix map

This document is the **single trail** for issues that keep recurring in design review and chat: what the **prompts and raw JSON** imply vs what **Python actually ranks, stores, and renders**. It follows the **evidence-before-assertion** bar from the operator prompt ([`startup/PROMPT.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/startup/PROMPT.md) §2, §4): every claim below points at **file + line** or a **repro command**.

**Last verified against repo:** 2026-04-20 (code-path inspection for keyframe/layout contracts; the `Clip.model_validate` repro in §1 remains valid unless the schema changes).

---

## 1. Ranking: `score_breakdown` and `reasoning` are **not** used

### Verdict

**Clips are ranked only by `virality_score` (with a `needs_review` penalty).** The LLM may emit `score_breakdown` and `reasoning` per the clip-selection prompt, but those keys are **not** on the `Clip` schema and are **silently dropped** at parse time. They remain visible only in **`clip_selection_raw.json`** (verbatim LLM string), not in typed `Clip` objects or ranking logic.

### Evidence

**Ranker uses `virality_score` only:**

```102:137:c:\Users\wbrya\OneDrive\Documents\GitHub\humeo-bring-home-work-v1\src\humeo\clip_selector.py
def rank_and_filter_clips(
    clips: list[Clip],
    ...
) -> list[Clip]:
    """Rank ``clips`` by ``virality_score`` and apply the threshold+floor+cap.
    ...
    1. Sort descending by ``virality_score``.
    ...
    """
    ...
    def _priority(c: Clip) -> tuple[float, float]:
        review_penalty = 0.5 if c.needs_review else 0.0
        return (c.virality_score - review_penalty, c.virality_score)

    ordered = sorted(clips, key=_priority, reverse=True)

    strong = [c for c in ordered if c.virality_score >= threshold and not c.needs_review]
```

**Parse path validates `Clip` only** (no merge of `score_breakdown` into any field):

```258:267:c:\Users\wbrya\OneDrive\Documents\GitHub\humeo-bring-home-work-v1\src\humeo\clip_selector.py
def _parse_clips(raw_json: str) -> list[Clip]:
    ...
    for item in clips_data:
        payload = dict(item)
        payload.pop("duration_sec", None)
        clip = Clip.model_validate(payload)
```

**`Clip` model** ([`humeo-core/src/humeo_core/schemas.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/humeo-core/src/humeo_core/schemas.py)) has **no** `score_breakdown` or `reasoning` fields (see class `Clip` ~L271–306).

**Prompt still asks for them** (contract drift):

[`src/humeo/prompts/clip_selection_system.jinja2`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/prompts/clip_selection_system.jinja2) documents `reasoning` and `score_breakdown` and says `virality_score` must be consistent with them — but the runtime ranker **never reads** those keys.

**Repro (extra keys stripped):**

```bash
cd humeo-bring-home-work-v1
uv run python -c "from humeo_core.schemas import Clip; c=Clip.model_validate({'clip_id':'001','topic':'t','start_time_sec':0,'end_time_sec':60,'virality_score':0.9,'score_breakdown':{'a':1},'reasoning':'x'}); print(list(c.model_dump().keys()))"
```

Output does **not** include `score_breakdown` or `reasoning`.

### Prompt–schema drift (same issue)

The clip-selection prompt asks the model to keep `virality_score` **consistent** with `reasoning` / `score_breakdown`, but those keys **never survive** into `clips.json` because they are **not** on `Clip`. Auditing that consistency after parse requires **`clip_selection_raw.json`**, not typed clips alone.

### What to change if you want rule-based ranking (HIVE-style R_h)

| Area | File | What to do |
|------|------|------------|
| Schema | [`humeo-core/src/humeo_core/schemas.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/humeo-core/src/humeo_core/schemas.py) | Add optional `rule_scores: list[RuleScore]` or `score_breakdown: dict[str, int]` + optional `selection_reason: str` on `Clip` (see existing plan in [`docs/TODO.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/TODO.md) §2.4–2.5). |
| Parse | [`src/humeo/clip_selector.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/clip_selector.py) `_parse_clips` | No change if fields are on `Clip`; validation will retain them. |
| Rank | [`src/humeo/clip_selector.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/clip_selector.py) `rank_and_filter_clips` ~L102–175 | Extend `_priority()` or add a derived scalar: e.g. `composite = f(rule_scores)` with fallback to `virality_score`. |
| Cache | [`src/humeo/clip_selection_cache.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/clip_selection_cache.py) | Bump meta version if clip JSON shape or ranking inputs change (see `TODO.md` v3 plan). |
| Tests | [`tests/test_clip_ranking.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/tests/test_clip_ranking.py), [`tests/test_clip_selector.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/tests/test_clip_selector.py) | Assert order when `virality_score` ties but `score_breakdown` differs. |
| Docs | [`docs/PIPELINE.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/PIPELINE.md) Stage 2 | Document the actual rank key after implementation. |

**External reference:** HIVE highlight rules (conceptual ancestor) — [`docs/hive-paper/PAPER_BREAKDOWN.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/hive-paper/PAPER_BREAKDOWN.md) §4.1.

---

## 2. Hook window vs export start (mental model bug)

### Verdict

`hook_start_sec` / `hook_end_sec` are **clip-relative** and used for **pruning clamps** and **hook-detection prompts**, **not** to shift the ffmpeg `-ss` in-point. The exported slice is **`[start_time_sec, end_time_sec]`** narrowed only by **`trim_start_sec` / `trim_end_sec`**.

### Evidence

[`src/humeo/render_window.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/render_window.py) `effective_export_bounds` — L12–17: trim narrows window; **hook fields do not change the export window**. `clip_for_render` clears hook fields on the copy used for render (L32–43).

Hook used in pruning: [`src/humeo/content_pruning.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/content_pruning.py) `_clamp_decision` — preserves hook inside trimmed window (~L165–198).

### Fix map (only if product should “open at hook”)

| File | Change |
|------|--------|
| [`src/humeo/render_window.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/render_window.py) | New policy: e.g. export start = `start + trim_start + hook_start` (would need spec for audio/subtitle sync). |
| [`humeo-core/.../compile.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/humeo-core/src/humeo_core/primitives/compile.py) | Possibly two-pass or leader if you want frozen-frame open; currently single `-ss`/`-t`. |
| [`docs/PIPELINE.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/PIPELINE.md), [`TERMINOLOGY.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/TERMINOLOGY.md) (repo root) | Document the chosen semantics. |

---

## 3. Clip JSON fields persisted but **unused** in the render pipeline

### Verdict

These exist on **`Clip`** and appear in **`clips.json`**, but **no code in `src/humeo` reads them** for ffmpeg, subtitles, or uploads:

- `shorts_title`
- `description`
- `hashtags`

**Evidence:** `rg "shorts_title|description|hashtags" src/humeo --glob "*.py"` returns **no** matches outside prompts / this doc (verified 2026-04-19).

**Used fields (non-exhaustive):** `clip_id`, `topic`, `start_time_sec`, `end_time_sec`, `viral_hook`, `virality_score`, `transcript`, `suggested_overlay_title`, `layout_hint` (fallback), `hook_*`, `trim_*`, `layout` (set from vision), `needs_review` (ranking penalty only).

### Fix map

| Goal | File |
|------|------|
| Emit upload sidecar JSON | New module e.g. `src/humeo/upload_metadata.py` + CLI flag; read from `Clip` |
| Burn `shorts_title` instead of overlay title | [`src/humeo/pipeline.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/pipeline.py) ~L245 `title_text=` |
| Drop fields from prompt to save tokens | [`src/humeo/prompts/clip_selection_system.jinja2`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/prompts/clip_selection_system.jinja2) |

---

## 4. Scene detection vs product keyframes

### Verdict

**PySceneDetect `ContentDetector`** exists in **`humeo-core`** for **shot/scene boundaries** on a file ([`humeo-core/src/humeo_core/primitives/ingest.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/humeo-core/src/humeo_core/primitives/ingest.py) `detect_scenes` ~L60–93).

The **product pipeline** ([`src/humeo/pipeline.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/pipeline.py) Stage 3) does **not** call `detect_scenes` on the long source for clip layout. It builds **one `Scene` per selected clip** and extracts **one keyframe at the clip window midpoint** (`extract_keyframes` ~L96–125 in same `ingest.py`).

**Implication:** If layout changes **inside** a 50–90s clip, a **single** midpoint frame can misrepresent the whole clip for Gemini vision.

**Missing capability:** The repo has **no intra-clip key-change detector** today. If the product should move from "one keyframe per clip" to "many keyframes per clip", it also needs a way to decide **where** the additional frames come from. Candidate triggers are not limited to:

- scene / shot boundaries from `detect_scenes`
- dominant-color or histogram deltas
- brightness / light-intensity changes
- OCR text appearance / disappearance
- person-count or layout-class changes (person-only → chart+person, two-persons → one-person, etc.)
- a cheap Gemini verification pass that merges near-duplicate candidate frames

**Second implication:** Even if extra frames are sampled, the current cache/artifact shape still stores **one `LayoutInstruction` per clip** in `layout_vision.json` (`src/humeo/layout_vision.py` writes `clip_id -> instruction`). That means a real many-keyframe design likely needs either:

- a **vote/merge** step that collapses N frame-level opinions into one clip-level layout, or
- a **layout timeline** / per-segment instruction list instead of a single instruction.

### Fix map

| Approach | Files |
|----------|--------|
| Multi-keyframe per clip | [`src/humeo/pipeline.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/pipeline.py), [`src/humeo/layout_vision.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/layout_vision.py), schemas for N frames |
| Add an intra-clip key-change detector | [`humeo-core/src/humeo_core/primitives/ingest.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/humeo-core/src/humeo_core/primitives/ingest.py), [`src/humeo/pipeline.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/pipeline.py) — candidate triggers not limited to shot boundaries, color / light deltas, OCR changes, person-count changes, or a model pass |
| Replace single per-clip layout output with a vote or timeline | [`src/humeo/layout_vision.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/layout_vision.py), [`humeo-core/src/humeo_core/schemas.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/humeo-core/src/humeo_core/schemas.py), [`docs/PIPELINE.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/PIPELINE.md) |
| Run `detect_scenes` on source, feed segment list into selector | [`src/humeo/pipeline.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/pipeline.py), [`src/humeo/clip_selector.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/clip_selector.py) — aligns with [`docs/TODO.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/TODO.md) optional row D |

**External:** [PySceneDetect](https://www.scenedetect.com/) — `ContentDetector` thresholding. Neural alternatives (HIVE mentions): TransNet V2, AutoShot (research / separate deps).

---

## 5. Gemini-facing bbox contract is likely the wrong shape today

### Verdict

The **internal** render/layout contract is normalized `[0, 1]` bboxes, and that part is fine. The likely problem is that the **model-facing** Gemini prompt also asks for `[0, 1]` floats directly. Per operator direction, that boundary should likely become **integer `[0, 1000]` coordinates** for Gemini, then normalize back to `[0, 1]` in Python before building `BoundingBox`.

This is **not implemented today**. Right now the code and docs ask Gemini for normalized floats end-to-end.

### Evidence

The Gemini vision prompt in [`src/humeo/layout_vision.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/layout_vision.py) explicitly says:

- `person_bbox`, `face_bbox`, `chart_bbox`, etc. use `{"x1": 0.0, ... "x2": 1.0, ...}`
- `All bbox coordinates are normalized 0..1`

The terminology doc repeats the same contract:

- [`TERMINOLOGY.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/TERMINOLOGY.md) says all bboxes use normalized `[0, 1]` coordinates.

The parser also validates straight into normalized runtime boxes with no dedicated Gemini-boundary adapter:

- [`src/humeo/layout_vision.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/layout_vision.py) `_parse_bbox`
- [`humeo-core/src/humeo_core/schemas.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/humeo-core/src/humeo_core/schemas.py) `BoundingBox`

### Why it matters

- Asking Gemini for **small decimals** is a stricter model-output contract than the renderer actually needs.
- Integer `[0, 1000]` coordinates are easier to describe, easier to inspect in raw JSON, and easier to clamp robustly before normalization.
- Keeping `[0, 1]` **internally** still preserves resolution-independence for the renderer and schema.

### Fix map

| Area | File | What to do |
|------|------|------------|
| Prompt boundary | [`src/humeo/layout_vision.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/layout_vision.py) | Change the Gemini prompt/examples from normalized `[0, 1]` floats to integer `[0, 1000]` coords. |
| Response schema | [`src/humeo/layout_vision.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/layout_vision.py), [`humeo-core/src/humeo_core/schemas.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/humeo-core/src/humeo_core/schemas.py) | Add a Gemini-specific bbox schema/model for `0..1000` ints; do **not** replace the internal normalized `BoundingBox`. |
| Adapter layer | [`src/humeo/layout_vision.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/src/humeo/layout_vision.py) | Normalize `0..1000` ints to `0..1` floats before constructing `LayoutInstruction`; keep a fallback for legacy `0..1` and accidental pixel outputs. |
| Tests | [`tests/test_layout_vision_unit.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/tests/test_layout_vision_unit.py), [`humeo-core/tests/test_layout_bbox.py`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/humeo-core/tests/test_layout_bbox.py) | Add fixtures proving `0..1000` raw model boxes normalize correctly and still drive the existing renderer. |
| Docs | [`TERMINOLOGY.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/TERMINOLOGY.md), [`docs/PIPELINE.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/PIPELINE.md) | Keep `[0, 1]` as the internal/runtime contract, but explicitly document `[0, 1000]` as the Gemini-facing contract if adopted. |

---

## 6. `startup/PROMPT.md` — not wired into this repo

[`startup/PROMPT.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/startup/PROMPT.md) is a **portable operator/agent system prompt** (different repo path on this machine: `GitHub/startup/`). It is **not** imported by `humeo` at runtime. Use it for **human and agent process** (evidence, ship bar, gears); use **this file + `PIPELINE.md`** for **product truth**.

---

## 7. Quick cross-index

| Topic | Canonical doc |
|--------|----------------|
| Stages, caches | [`docs/PIPELINE.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/PIPELINE.md) |
| Backlog / narrative context / layout fixes | [`docs/TODO.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/TODO.md) |
| Design history | [`docs/SOLUTIONS.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/SOLUTIONS.md) |
| Temporal vs spatial | [`TERMINOLOGY.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/TERMINOLOGY.md) or `PIPELINE.md` + this doc §2 |
| Reading order | [`docs/STUDY_ORDER.md`](file:///c:/Users/wbrya/OneDrive/Documents/GitHub/humeo-bring-home-work-v1/docs/STUDY_ORDER.md) |

---

## 8. Verification command (Operator OS §2 / §4)

After any schema or ranker change:

```bash
cd humeo-bring-home-work-v1
uv run pytest tests/test_clip_ranking.py tests/test_clip_selector.py tests/test_clip_selection_cache.py humeo-core/tests/test_schemas.py
```

Ship only when green, with output captured for the trail.
