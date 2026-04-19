# TODO — Make the pipeline more dynamic, closer to HIVE, without becoming HIVE

Blunt, first-principles. Three problems were raised. For each: the root cause,
multiple solutions ranked, the chosen path, and concrete edits with no breaking
changes. References back to `docs/hive-paper/hive_paper_blunt_guide.md` and
`docs/hive-paper/PAPER_BREAKDOWN.md`.

Everything below is **additive** to the current schemas. Old callers keep
working. Old cache files keep working (with a one-line meta version bump).

---

## Status snapshot (maintainer log, 2026-04-18)

This section is only “what shipped vs what this file still proposes.” It does
not replace the detailed sections below.

### Already implemented (today’s codebase)

Do **not** duplicate the stage list here — **`docs/PIPELINE.md`** is canonical (`run_pipeline` in `src/humeo/pipeline.py`).

In one line: **ingest → clip selection → hook → inner-clip prune → one keyframe per clip + layout vision → ASS + ffmpeg render**; strict `humeo_core.schemas`; transcript-only at clip-select time, vision after clips exist. Chronology: **`docs/SOLUTIONS.md`** §6.

### Not implemented yet (this TODO’s “north star” extras)

- **`narrative_context.json`** before clip selection (§0 bullet) — **not built.** Clip selection still depends only on transcript (+ hashes for cache), not a visual narrative artefact.
- **Clip selector consuming that artefact** — **not built** (same reason).
- **Many keyframes per clip for layout vision** — **not built.** The product still uses one midpoint keyframe per selected clip; there is no intra-clip key-change detector for color shift, light-intensity change, OCR/text change, layout/person-count change, or model-assisted dedupe.
- **Gemini-facing bbox contract at integer `[0,1000]`** — **not built.** The current prompt/runtime still asks Gemini for normalized `[0,1]` coords end-to-end.
- **“Kill letterboxing” as an explicit milestone closure** — treat as **open** until tracked as a closed issue with before/after samples; layout math exists but this doc’s acceptance criterion was never formally signed off here.
- **§1.3 cross-comments on the two `.gitignore` files** — still **optional**; root and `humeo-core/.gitignore` do not yet have the one-line pointers suggested below.

### Operational note: Gemini `503 UNAVAILABLE` (seen 2026-04-18)

If clip selection fails after three attempts with
`503 UNAVAILABLE` / “high demand” for `gemini-3.1-flash-lite-preview`, that is
**Google’s tier capacity**, not a bug in this repo. Mitigations: wait and
retry, set **`GEMINI_MODEL`** / pass **`--gemini-model`** to a different
generally available model, or use a project/tier with higher quota.

---

## 0. North star for this milestone

> "Not full HIVE. *Feel* closer to HIVE. Ship fast."

Translated:

- Keep the current staged pipeline (`ingest → clip select → hook → prune → layout vision → render`).
- Keep the five fixed 9:16 layouts in `humeo_core.primitives.layouts`.
- Keep the two-package split (`humeo` product, `humeo-core` engine).
- **Add one new cheap multimodal artefact** between ingest and clip selection:
  `narrative_context.json`. This is HIVE §3.1.5 "Comprehensive Caption" in one
  file, one prompt, no memory module.
- **Make the clip selector depend on that artefact** so its output actually
  changes when the visuals/charts change, not only when the transcript hash
  changes.
- **Make the renderer stop letterboxing.** Kill the black bars.

That's the whole milestone. Everything in this TODO is one of those four
moves or a supporting test.

---

## 1. "Why are there two `.gitignore` files? Why a project in a project?"

### 1.1 Root cause (first principles)

There are two Python packages in this repo and they are **both useful on
their own**:

- `humeo-core/` — a reusable MCP server. Anyone (Cursor, Claude Desktop, a
  different CLI) can `pip install humeo-core` and consume the primitives. It
  has its own `pyproject.toml`, its own `README.md`, its own `LICENSE`, its
  own tests. It is intended to be publishable to PyPI independently. See
  `humeo-core/README.md` lines 1-10 and `docs/SOLUTIONS.md §5.3-5.4`
  (explicitly rejected merging the two).
- `src/humeo/` — the product wrapper that glues download + transcript + LLM
  selection + subtitles + ffmpeg together into the `humeo` CLI. It depends
  on `humeo-core` via an editable path source (see root `pyproject.toml`
  `[tool.uv.sources]`).

This is **not a nested git repo**. It's a monorepo with two installable
packages, which is a common and correct Python layout (same pattern as
`langchain` + `langchain-core`, `pytest` + `pytest-*`, etc.).

Each package has its own `.gitignore` because when `humeo-core/` is
extracted/vendored into its own checkout (or published to PyPI from a
subtree), it must still ignore the right things on its own. The root
`.gitignore` is the authoritative repo-wide ignore.

So: **two `.gitignore`s is not a bug**. The duplication is small noise.

### 1.2 Solutions, ranked

| # | Solution | Pros | Cons |
|---|----------|------|------|
| **1 (chosen)** | Keep both. Trim `humeo-core/.gitignore` to the minimum a standalone consumer of that package needs (`__pycache__`, `*.pyc`, `.pytest_cache/`, `build/`, `dist/`, `*.egg-info/`, `.venv/`). Document the invariant in both files. | Zero behavioural change. Sub-package stays standalone-usable. | Two small files to maintain. |
| 2 | Delete `humeo-core/.gitignore`. | One file. | If anyone extracts `humeo-core/` into its own repo (per SOLUTIONS.md §5.4), they have no ignores. Slight land-mine for future contributors. |
| 3 | Convert `humeo-core/` to a git submodule. | "Pure" isolation. | Massive dev-UX regression. Breaks editable installs. Overkill. |
| 4 | Merge `humeo-core/` back into `src/humeo/`. | Simplest tree. | Kills the reusable MCP server, which is the whole point of the package. Explicitly rejected in `docs/SOLUTIONS.md §5.3`. |

### 1.3 Action

- Leave `humeo-core/.gitignore` (already minimal at 9 lines — good).
- Add a 1-line comment at the top of each `.gitignore` pointing at the other,
  so future contributors know which rules go where:
  - Root: `# Repo-wide ignores. Sub-package has its own humeo-core/.gitignore.`
  - humeo-core: `# Standalone-package ignores. Repo-wide rules live in ../.gitignore.`
- Keep as-is otherwise. No code changes.

---

## 2. "The clip selection feels hardcoded / returned too fast"

### 2.1 Root cause (three compounding effects)

Running `src/humeo/clip_selector.py select_clips` **does** call Gemini. The
transcript goes to `google.genai.Client.models.generate_content` with
`response_mime_type="application/json"` and `temperature=0.3`. That is
real inference. What makes it **look** static:

1. **Cache hits are silent, and fast.** `humeo.clip_selection_cache.cache_valid`
   skips the LLM whenever
   `transcript_sha256 + gemini_model` matches. Your latest run was probably a
   cache hit (terminal 8.txt lines 23–31 show clip *ranking*, not an LLM
   round-trip; the Gemini POSTs in terminal 1.txt are the **layout-vision**
   stage, not clip selection). So clip selection took ~0s and the old
   cached clips printed instantly. That is by design (ingest LLM calls are
   expensive), but it *hides* the actual behaviour.
2. **Low temperature + deterministic-shape prompt** = near-identical output
   across retries. `temperature=0.3`, a rigid Jinja schema (see
   `src/humeo/prompts/clip_selection_system.jinja2`), and "return exactly 5
   clips ranked by virality_score" → Gemini produces a neat descending
   sequence like `0.98, 0.95, 0.92, 0.89, 0.85`. That's not hardcoded; it's
   a common LLM artefact when you ask for ordered scores under low-temp.
3. **The selector only sees TEXT.** The prompt is built from
   `transcript["segments"]` as `[start-end] text` lines. No frames, no OCR,
   no scene captions, no character attribution. Result: the selector cannot
   "notice" that a chart appears at 14:15 or that a speaker cut to slides.
   Content-wise, it is forced into transcript-only ranking — exactly the
   anti-pattern HIVE §1 warns against (see `docs/hive-paper/PAPER_BREAKDOWN.md` §1:
   "ASR-only LLM methods … miss facial reactions, gestures, screen text …
   abrupt transitions").

Put differently: **the pipeline is LLM-driven, but the LLM is half-blind.**
Your intuition that it "feels static" is correct — the same half-blind model
fed the same transcript will pick the same five clips.

### 2.2 Solutions, ranked

Each option can be layered. "Chosen" = implement in this milestone.

| # | Solution | Dynamic? | HIVE distance | Cost | Breaking? |
|---|----------|:--------:|:-------------:|:----:|:---------:|
| **A (chosen)** | **Add a multimodal context stage** between ingest and clip-selection. One Gemini call over N scene keyframes (already extracted per clip in stage 3) returns a `NarrativeContext` JSON. Inject that context into the selector prompt. Selector now sees transcript **and** scene captions **and** chart OCR. | Yes | HIVE §3.1.5 "Comprehensive Caption" (minimal). | ~1 extra Gemini call per video. | No (new optional artefact). |
| **B (chosen)** | **Structured rule-scored selection.** Replace the single `virality_score` with a small list of named rules (`hook_strength`, `counterintuitive_claim`, `chart_reference`, `named_entity`, `self_contained`). Each rule gets a 0–1 score and a one-line reason. Total score = weighted sum. | Yes (rule rationale changes per clip) | HIVE §3.2.1 "Highlight Detection rules Rₕ" (minimal). | 0 extra calls. Larger JSON. | No (new optional fields). |
| **C (chosen)** | **Raise clip-selection temperature to 0.7 and over-generate.** Ask Gemini for 8 candidates, then keep top-5 by composite score after rules. | Yes (variance from sampling). | Not HIVE. Just better ML hygiene. | 0 extra calls. | No. |
| D | Swap to full scene segmentation (`scenedetect`) **before** clip selection and feed the segment list into the selector so it can snap boundaries. | Yes | HIVE §3.4 scene segmentation. | ~15 s scene detect on source. | No (optional). |
| E | Character extraction + dialogue attribution (HIVE §3.1–3.3). | Max | Full HIVE Module A. | Big. | Could be. |
| F | Memory module across episodes. | Max | HIVE §3.6. | Big. | Could be. |

### 2.3 Chosen combination — A + B + C (D is optional, later)

This is the minimum change-set that makes the selector genuinely dynamic
(multimodal context + rule rationale + sampling variance) without turning
the repo into full HIVE. It preserves every existing schema as a strict
superset.

### 2.4 JSON contract (additive — **no breaking changes**)

All new fields are optional. Old `clips.json` files still validate.

```json
// work_dir/narrative_context.json  (NEW, produced by new stage 1.5)
{
  "version": 1,
  "source_sha256": "…",
  "gemini_model": "gemini-3.1-pro",
  "global_summary": "Cathie Wood and host discuss prediction markets, debt-to-equity vs debt-to-GDP, and AI-driven productivity.",
  "core_hook": "Prediction markets could explode to $5T notional volume.",
  "characters": [
    {"name": "Cathie Wood", "role": "guest",  "screen_presence": "center_sit"},
    {"name": "Host",        "role": "host",   "screen_presence": "zoom_call"}
  ],
  "scenes": [
    {
      "scene_id": "s001",
      "start_time_sec": 0.0,
      "end_time_sec": 150.2,
      "keyframe_path": ".../keyframes/s001.jpg",
      "caption": "Host introduces ARK x Kalshi partnership. Lower-third graphic only.",
      "ocr_text": "ARK × KALSHI PARTNERSHIP",
      "chart_title": null,
      "dominant_layout_hint": "sit_center"
    }
    // …one entry per scene; O(tens), not thousands
  ]
}
```

```json
// work_dir/clips.json  Clip[] schema — additive fields only
{
  "clip_id": "004",
  "topic": "Government Debt vs Equity",
  "start_time_sec": 694.8,
  "end_time_sec": 745.2,
  "viral_hook": "You should be comparing debt to equity, not debt to GDP.",
  "virality_score": 0.89,                 // kept for back-compat (weighted sum of rule_scores)
  "transcript": "…",
  "suggested_overlay_title": "Stop Using Debt-to-GDP",
  "layout_hint": "split_chart_person",

  // NEW, all optional
  "source_scene_ids": ["s014", "s015"],   // which narrative scenes this clip spans
  "rule_scores": [
    {"rule_id": "hook_strength",         "score": 0.92, "reason": "opens with a counterintuitive claim"},
    {"rule_id": "counterintuitive_claim","score": 0.95, "reason": "debt-to-equity vs debt-to-GDP reframe"},
    {"rule_id": "chart_reference",       "score": 1.00, "reason": "narrative_context scene caption mentions 'black / purple / red' chart"},
    {"rule_id": "self_contained",        "score": 0.80, "reason": "full argument lives inside the clip"},
    {"rule_id": "named_entity",          "score": 0.60, "reason": "Cathie Wood speaks directly"}
  ],
  "selection_reason": "Composite 0.89 = 0.30·hook + 0.30·counterintuitive + 0.20·chart_ref + 0.15·self + 0.05·named"
}
```

```json
// work_dir/clips.meta.json — bump to v3 (non-breaking; cache_valid already
// handles older versions).
{
  "version": 3,
  "transcript_sha256": "…",
  "narrative_sha256":  "…",   // NEW — invalidates clip cache when context changes
  "gemini_model": "gemini-3.1-pro",
  "rule_weights": {"hook_strength": 0.30, "counterintuitive_claim": 0.30, "chart_reference": 0.20, "self_contained": 0.15, "named_entity": 0.05}
}
```

### 2.5 Implementation plan (ordered, each step independently shippable)

Files that change:

1. **`humeo-core/src/humeo_core/schemas.py`** — append optional fields:
   - `Clip`: `source_scene_ids: list[str] = []`, `rule_scores: list[RuleScore] = []`, `selection_reason: str = ""`.
   - New `RuleScore(BaseModel)`: `rule_id: str; score: float (0..1); reason: str`.
   - New `NarrativeCharacter`, `NarrativeScene`, `NarrativeContext` models mirroring §2.4.
   - Export the new names from `humeo_core.__init__`.
   - **No field removals, no rename, no stricter validator on existing fields** → every existing test keeps passing.

2. **`src/humeo/narrative_context.py`** (new file). Mirror the style of
   `humeo/layout_vision.py`:
   - `run_narrative_context_stage(work_dir, scenes, transcript, *, config) -> NarrativeContext`.
   - Hashes `(transcript_sha256, scene_ids, gemini_model)` into
     `narrative_context.meta.json` for caching.
   - Single Gemini call. Uses `response_schema=NarrativeContext` (see
     google-genai docs — validated via Context7: `response_schema`
     accepts a Pydantic model and **guarantees** valid JSON).
   - Logs the summary + per-scene captions.

3. **`src/humeo/prompts/clip_selection_system.jinja2`** — extend the prompt
   to reference `{{ narrative_summary }}`, `{{ scene_index }}` and ask for
   `rule_scores` + `source_scene_ids`. Keep the old field list so responses
   without the new fields still validate.

4. **`src/humeo/clip_selector.py`** —
   - `build_prompt(transcript, narrative_context=None)` adds context when
     available.
   - Switch Gemini call to `response_schema=ClipPlanExtended`
     (a Pydantic model wrapping `list[Clip]`) so malformed JSON becomes a
     3.1 SDK-level error instead of a downstream crash.
   - Bump default `temperature` to **0.7** and ask for 8 candidates; post-
     filter to top 5.
   - Compute `virality_score` from `rule_scores` if the model returned
     them; fall back to model-reported score otherwise.

5. **`src/humeo/clip_selection_cache.py`** —
   - Bump `CURRENT_META_VERSION` to **3**.
   - Add `narrative_sha256` and optional `rule_weights` to the meta.
   - `cache_valid` accepts v2 when narrative absent (back-compat).

6. **`src/humeo/pipeline.py`** — insert the new stage **between** Stage 1
   and Stage 2:
   - `narrative_ctx = run_narrative_context_stage(...)`
   - `clips = select_clips(transcript, narrative_context=narrative_ctx, ...)`
   - Log the summary + scene count.
   - Keep Stage 3 (layout vision) and Stage 4 (render) untouched.

7. **Tests** (all green on CI before ship):
   - `tests/test_narrative_context.py` — prompt shape, schema round-trip,
     caching behaviour.
   - Extend `tests/test_clip_selector.py` with a fixture that injects a
     `NarrativeContext` and asserts the system prompt contains the summary
     and the scene table.
   - Extend `tests/test_clip_selection_cache.py` with v2→v3 migration.
   - Golden-JSON test: a frozen `Clip` with the new optional fields must
     validate against the old v2 `Clip` shape (back-compat guard).

### 2.6 Back-compat sanity check

- Old `clips.json` on disk (v2, no `rule_scores`) loads fine because every
  new field has a default.
- Old `clips.meta.json` (v2) still matches `cache_valid` when the narrative
  artefact is absent — we just skip the context check for legacy caches.
- The prompt change is text-only; Gemini that ignores the new instructions
  still returns a valid `Clip` list.

---

## 3. "Cathie is small. Too much black. The short looks bad."

### 3.1 Root cause (three effects stack on top of each other)

Concrete evidence from the cached run at
`%LOCALAPPDATA%/humeo/videos/PdVv_vLkUgk/layout_vision.json`:

```json
"005": {
  "instruction": { "split_chart_region": null, "split_person_region": null, "...": "..." },
  "raw": {
    "person_bbox": { "x1": 575, "y1": 60, "x2": 990, "y2": 1000 },
    "chart_bbox":  { "x1": 25,  "y1": 30, "x2": 575, "y2":  695 },
    "layout": "split_chart_person"
  }
}
```

That `raw` block is Gemini returning **pixel coordinates, not normalized
[0..1] floats** — exactly what the vision prompt forbids, but the model did
it anyway. Even if the model behaved perfectly, asking Gemini for tiny
normalized decimals may be the wrong boundary contract; the operator wants
the Gemini-facing format to be **integer `[0,1000]`** and the Python side to
normalize that back to `[0,1]`.

Now trace through `src/humeo/layout_vision.py::_parse_bbox`:

```117:123:src/humeo/layout_vision.py
def _parse_bbox(raw: object) -> BoundingBox | None:
    if not raw or not isinstance(raw, dict):
        return None
    try:
        return BoundingBox.model_validate(raw)
    except Exception:
        return None
```

`BoundingBox` has `ge=0.0, le=1.0` on every coord. Pixel values like `990`
**raise**, the bare `except` swallows the exception silently, `None` is
returned, and `split_chart_region`/`split_person_region` end up `null` in
the instruction. Nothing is logged. We never find out the model
misbehaved.

Then `humeo_core.primitives.layouts.plan_split_chart_person` sees null
regions and falls through to its **hard-coded** 2/3 | 1/3 strip math:

```227:244:humeo-core/src/humeo_core/primitives/layouts.py
    left_split = int(round((2.0 / 3.0) * float(src_w)))
    left_split -= left_split % 2
    left_split = max(2, min(src_w - 2, left_split))

    # Chart: only the left region. ``chart_x_norm`` trims from the left edge [0, left_split).
    chart_start_x = int(round(_clamp01(instruction.chart_x_norm) * float(left_split)))
    chart_start_x -= chart_start_x % 2
    chart_start_x = max(0, min(left_split - 2, chart_start_x))
    chart_w = left_split - chart_start_x
    chart_w -= chart_w % 2
    chart_h = src_h - (src_h % 2)

    # Person: only the right third — never overlaps the chart strip.
    person_x = left_split
    person_x -= person_x % 2
    person_w = src_w - person_x
    person_w -= person_w % 2
    person_h = src_h - (src_h % 2)
```

For this particular frame the real speaker is at normalized x ≈ 0.30–0.52
(i.e. **in the left half**). The fallback crops the right-1/3 strip, which
barely overlaps her. What *does* make it into the bottom band is a narrow
640×1080 source region scaled to fit inside a 1080×768 target with
`force_original_aspect_ratio=decrease + pad=black` — see:

```262:266:humeo-core/src/humeo_core/primitives/layouts.py
    band_person_bot = (
        f"[src2]crop={person_w}:{person_h}:{person_x}:0,"
        f"scale={out_w}:{bot_h}:force_original_aspect_ratio=decrease,"
        f"pad={out_w}:{bot_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1[bot]"
    )
```

`force_original_aspect_ratio=decrease` is literally the ffmpeg setting that
says "scale to fit inside and *pad the rest with black*" (confirmed against
`ffmpeg-all.html` §force_original_aspect_ratio, via Context7). Put a
9:16-ish source region into a wider 1080:768 band this way and ffmpeg
inserts ~312px of black on each side. That's the bars in the screenshot.

The chart band does the same thing — 1280×1080 scaled into 1080×1152 fits
to width and leaves ~120 px of black above and below the chart.

So there are **three independent failure modes**:

| # | Failure | Symptom | Fix |
|---|---------|---------|-----|
| F1 | Pixel bboxes accepted-then-silently-dropped | `split_*_region` is `null` when the model is close but wrong unit → fallback layout fires on content it was not designed for. | Enforce Pydantic schema **at the model layer** + defensive normalization. |
| F2 | Fallback layout not content-aware | Hardcoded "chart = left 2/3, person = right 1/3" doesn't match every `split_chart_person` frame. | Fall back to the vision `person_bbox.center_x` even when the split regions are missing; only use the fixed 2/3 split when no person bbox at all is present. |
| F3 | `decrease + pad` letterboxes the split bands | Black bars everywhere. | Switch to `increase + crop` ("fill") so regions fully cover each band; optionally size the bands to the region aspect. |

### 3.2 Solutions, ranked

#### Fix F1 — use a Gemini-friendly bbox contract, then normalize internally

| # | Solution | Guarantee | Cost | Breaking? |
|---|----------|----------|------|-----------|
| **1 (chosen)** | Use `types.GenerateContentConfig(response_schema=GeminiLayoutVisionResponse)` where the **Gemini-specific** bbox model uses integer coords in **`[0,1000]`**, not normalized floats. Normalize to the internal `BoundingBox` (`[0,1]`) only after parse. | Strong at the model boundary. | 0 extra calls. | No — internal layout/render contract stays the same. |
| **2 (chosen, additive to 1)** | Add a defensive adapter in `_parse_bbox` / `_maybe_normalize_bbox` that accepts the preferred `0..1000` format, legacy `0..1` floats, and accidental pixel coords. Log which branch fired. | Strong backup. | 0. | No. |
| 3 | Keep asking for normalized `0..1` and only tighten the schema. | Better than today, but still a brittle model-facing contract. | 0. | No. |
| 4 | Put `additional_properties=false` + `required=[...]` via raw schema dict. | Same structured-output family as 1, but harder to maintain. | 0. | No. |

→ **Ship (1) + (2).** (3) naturally falls out of (2).

#### Fix F2 — fallback that uses whatever signal we do have

| # | Solution | Dynamic? | Cost | Breaking? |
|---|----------|:--------:|:----:|:---------:|
| **1 (chosen)** | When `split_chart_region`/`split_person_region` are absent but `person_x_norm` was derived from `person_bbox.center_x`, compute `left_split = person_bbox.x1` (clamped) instead of the 2/3 constant. This keeps the non-overlap invariant but places the divide where the model actually saw the split. | Yes. | 0. | No — only changes the `null-bbox, non-0.5 person_x` code path. |
| 2 | If both bboxes missing, demote layout from `split_chart_person` to `sit_center`. | Safer but loses the split benefit. | 0. | No. |
| 3 | Keep existing fixed 2/3 split (status quo). | No. | — | — |

→ **Ship (1).** (2) is a sensible secondary guard for the "no regions at
all" degenerate case; add it inline.

#### Fix F3 — stop letterboxing the split bands

| # | Solution | Visual result | Breaking? |
|---|----------|---------------|-----------|
| **1 (chosen)** | Replace `force_original_aspect_ratio=decrease + pad=black` with `force_original_aspect_ratio=increase,crop={out_w}:{band_h}`. Region fills the band, edges cropped. | No black bars. Speaker fills frame. Some edge pixels lost. | Behavioural change (but pure visual improvement; no schema change). Gate behind a new `LayoutInstruction.split_fit: Literal["fit","fill"] = "fill"`. Default to `"fill"` for new instructions; `"fit"` preserves today's look. |
| 2 | Dynamic band heights: `top_h = round(out_h * chart_aspect_weight)`; compute `chart_aspect_weight` from chart_bbox AR so the band matches the region. | Minimizes remaining pad in the `fit` mode. | Non-breaking if `split_fit="fit"`. |
| 3 | Replace the stacked layout with a **picture-in-picture**: chart full-frame behind, person in a bottom-right circle (Twitch style). | Very different look. | Yes — new layout kind. |
| 4 | Keep letterboxing (status quo). | Bars everywhere. | — |

→ **Ship (1). Ship (2) as a small refinement.** Keep a regression test
with `split_fit="fit"` asserting the old filtergraph still compiles
exactly (so legacy callers are unaffected).

### 3.3 JSON contract changes (additive)

```python
# humeo_core/schemas.py  — LayoutInstruction gets ONE new optional field.
class LayoutInstruction(BaseModel):
    # existing fields unchanged …
    split_fit: Literal["fit", "fill"] = "fill"   # NEW — default flips behaviour; safe because
                                                 # every existing *serialized* instruction was
                                                 # implicitly "fit", and we do not persist v1
                                                 # instructions across the cache bump.
```

Cache is invalidated by bumping `layout_vision.meta.json.vision_schema_version` (new field, default `1`). Old caches without that field are rebuilt — equivalent to re-running Gemini vision once after this ships. No user-visible regression; just one extra LLM pass the first time after upgrade.

### 3.4 Implementation plan (small, surgical, all tested)

1. **`humeo-core/src/humeo_core/schemas.py`**:
   - Add `split_fit: Literal["fit", "fill"] = "fill"` to `LayoutInstruction`.
   - Add `GeminiLayoutVisionResponse` (a Pydantic model used as the
     `response_schema` argument) mirroring the JSON the vision prompt asks
     for, but with **Gemini-facing** bbox fields in integer `0..1000`
     coordinates rather than the internal normalized `BoundingBox`.
2. **`humeo-core/src/humeo_core/primitives/layouts.py`**:
   - In `plan_split_chart_person`, branch on `instruction.split_fit`:
     - `"fit"` → current filtergraph.
     - `"fill"` → swap each `scale=...:force_original_aspect_ratio=decrease,pad=...color=black` with `scale=...:force_original_aspect_ratio=increase,crop={out_w}:{band_h}:(iw-ow)/2:(ih-oh)/2`.
   - (Optional refinement) compute `top_h` from chart_bbox AR when
     `split_fit="fit"` so the legacy look has less pad.
3. **`src/humeo/layout_vision.py`**:
   - Switch the vision call to
     `config=types.GenerateContentConfig(response_schema=GeminiLayoutVisionResponse, temperature=0.2, response_mime_type="application/json")`.
   - Add `_maybe_normalize_bbox(raw_dict, src_w, src_h)` that prefers `0..1000` Gemini coords, still accepts legacy `0..1`, and falls back to probed image dims for accidental pixel outputs; log a `warning` when the fallback path fires.
   - Replace the silent `except Exception: return None` with `except Exception as e: logger.warning("dropping malformed bbox: %s", e); return None`.
   - In `_instruction_from_gemini_json`, if the vision layout is
     `split_chart_person` but either bbox is None, demote to
     `sit_center`. If **only** `split_chart_region` / `split_person_region`
     are None but `person_bbox` is present, keep
     `split_chart_person` and derive `left_split = person_bbox.x1` so the
     F2 fallback does the right thing.
4. **Tests**:
   - `humeo-core/tests/test_layouts.py`:
     - `test_split_fill_uses_increase_and_crop` — the new filtergraph
       contains `force_original_aspect_ratio=increase` **and** `crop=1080:`.
     - `test_split_fit_still_letterboxes` — legacy mode unchanged.
   - `humeo-core/tests/test_layout_bbox.py`:
     - `test_split_with_bbox_regions_uses_fill_by_default` — vision-derived
       instructions now render without black bars.
   - `tests/test_layout_vision_unit.py`:
     - `test_thousand_scale_bboxes_get_normalized` — fed a Gemini-style
       `0..1000` bbox, `_instruction_from_gemini_json` returns non-None
       `split_*_region` with `0..1` coords.
     - `test_pixel_bboxes_get_normalized_as_fallback` — accidental
       pixel-scale bbox still survives the adapter path.
     - `test_silent_parse_failure_now_logs_warning` — caplog asserts a
       warning was emitted.

---

## 4. Tying it together — the updated pipeline

After Sections 2 + 3 ship, the runtime path becomes:

```text
YouTube URL
  → Stage 1 : download + transcript                            (deterministic, cached)
  → Stage 1.5 : narrative context                              (NEW, 1 Gemini call, cached)
      • global_summary, core_hook, characters,
      • per-scene caption + ocr_text + layout_hint
      • output: narrative_context.json
  → Stage 2 : clip selection (Gemini + rule scores)            (updated, cached)
      • input: transcript + narrative_context
      • output: clips.json with rule_scores + source_scene_ids
  → Stage 3 : layout vision (Gemini vision w/ response_schema) (updated, cached)
      • output: layout_vision.json with validated bboxes + split_fit
  → Stage 4 : render (split_fit="fill" by default)             (updated)
      • no black bars, content-aware fallbacks
      • output: output/short_XXX.mp4
```

Every JSON artefact at every stage validates against a Pydantic schema.
Every stage's cache key is a SHA-256 of its inputs. Re-runs do the minimum
work. That is HIVE §7 "minimal JSON contracts" + §8 "anti-pattern: re-run
expensive extraction" applied strictly.

---

## 5. Task breakdown (shippable units, dependency-ordered)

Each unit is a standalone PR-sized change with its own tests. Ship in
order.

### Phase 1 — plumbing (no user-visible behaviour change)

- [ ] `schemas.py`: add `RuleScore`, `NarrativeCharacter`, `NarrativeScene`,
      `NarrativeContext`, `GeminiLayoutVisionResponse`; extend `Clip` and
      `LayoutInstruction` with optional fields.
- [ ] Export new symbols from `humeo_core.__init__`.
- [ ] `humeo-core/tests/test_schemas.py`: validate every new model +
      back-compat round-trip on the old `Clip` JSON.

### Phase 2 — rendering fixes (Section 3)

- [ ] Implement `split_fit="fill"` in `layouts.py`.
- [ ] Implement dynamic band height refinement for `"fit"` mode.
- [ ] Re-enable `force_layout_vision=True` default in dev once (flush
      caches), then flip back.
- [ ] Add the `test_split_fill_*` tests.
- [ ] Switch `layout_vision._call_gemini_vision` to
      `response_schema=GeminiLayoutVisionResponse`.
- [ ] Change the Gemini-facing bbox prompt/schema to integer `[0,1000]`.
- [ ] Add `_maybe_normalize_bbox` + warning logs.
- [ ] Add `0..1000` regression tests and pixel-bbox fallback tests.
- [ ] Smoke-render the Cathie Wood clip 005 locally and confirm the black
      bars are gone (visual sign-off).

### Phase 2.5 — keyframe granularity (operator addition)

- [ ] Replace the single midpoint keyframe per clip with multiple candidate
      keyframes per clip.
- [ ] Implement an intra-clip key-change detector; signals are not limited
      to scene boundaries, color / histogram shifts, light-intensity
      changes, OCR/text changes, person-count changes, layout-class changes,
      or a cheap Gemini merge/dedupe pass.
- [ ] Decide whether frame-level layout opinions collapse to one clip-level
      vote or expand `layout_vision.json` into a per-segment timeline.
- [ ] Add tests/fixtures proving one clip can change layout inside the clip
      without relying on a single midpoint frame.

### Phase 3 — narrative context (Section 2, step A)

- [ ] `src/humeo/narrative_context.py` with caching + `response_schema`
      call.
- [ ] `src/humeo/pipeline.py` inserts Stage 1.5 before Stage 2.
- [ ] `tests/test_narrative_context.py` (schema, caching, prompt shape).

### Phase 4 — selector upgrade (Section 2, steps B + C)

- [ ] Extend `clip_selection_system.jinja2` with rule list + context slot.
- [ ] `clip_selector.py`: temperature 0.7, over-generate 8 → keep 5,
      derive `virality_score` from `rule_scores`.
- [ ] Bump `CURRENT_META_VERSION = 3`; support v2 cache gracefully.
- [ ] Tests: `test_clip_selector` with a stubbed context + stubbed
      Gemini returning `rule_scores`; `test_clip_selection_cache` v2→v3.

### Phase 5 — docs + housekeeping (Section 1)

- [ ] Add the one-line header comment to both `.gitignore` files.
- [ ] Update `docs/PIPELINE.md` to document Stage 1.5 + rule scores +
      `split_fit`.
- [ ] Update `README.md` runtime path diagram.
- [ ] Update `docs/SOLUTIONS.md §9 "Known gaps"` — cross off pruning-
      adjacent items that rule-scored selection partially covers.

---

## 6. Non-goals for this milestone

Explicit. So we don't silently scope-creep into HIVE.

- **No character memory across episodes.** HIVE §3.6 memory module is
  valuable for series but adds real complexity.
- **No *scene-level* pruning sub-agent** (HIVE Rₚ deleting whole scenes inside
  a drama window). **Inner-clip** pruning is **already shipped** (`content_pruning.py`).
  Prompt/schema gaps: `docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`.
- **No training data, no custom models.** Everything is prompting +
  schemas.
- ~~**No new layout kinds.** Still exactly three thrusters.~~
  **Updated:** we now ship five thrusters (`zoom_call_center`, `sit_center`,
  `split_chart_person`, `split_two_persons`, `split_two_charts`) — the
  "max 2 items" rule makes the extra two layouts near-free to add.
- **No change to the ingest provider selection** (WhisperX vs OpenAI).
- **No change to `humeo-core`'s MCP server tools.** All modifications are
  schema-additive and behaviour is opt-in via new fields.

---

## 7. What "done" looks like

Concrete acceptance criteria for closing this TODO:

1. `uv run pytest` — all green (old + new tests).
2. `humeo --long-to-shorts "https://www.youtube.com/watch?v=PdVv_vLkUgk"`
   produces `output/short_005.mp4` where Cathie Wood fills the bottom band
   with **no black side-bars**. Visual A/B vs the current render is
   unmistakable.
3. `work_dir/narrative_context.json` exists, validates against
   `NarrativeContext`, and is referenced in `clips.meta.json.narrative_sha256`.
4. `work_dir/clips.json` clips carry non-empty `rule_scores[]` with at
   least 5 distinct `rule_id`s, and the prompt uses the narrative context
   (grep the `clip_selection_raw.json` for the summary string).
5. Re-running with no changes → all three caches hit, no Gemini calls made
   (same behaviour as today, just with more artefacts).
6. Re-running after editing the transcript by one word → narrative cache
   miss → selector cache miss → layout-vision cache still hits (keyframes
   unchanged) → single-file re-render. Exactly the invalidation matrix in
   `docs/PIPELINE.md`, extended by one row for the narrative stage.
7. No existing public function signature changed. No existing schema
   field removed or renamed. Old cache files from before this milestone
   load without errors (they just fail `cache_valid` and get rebuilt).

When all seven hold, this TODO is closed.
