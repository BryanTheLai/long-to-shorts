# PAPER_BREAKDOWN.md — HIVE (ByteDance, 2507.02790v1)

Full, first-principles breakdown. No filler. No hedging.

Source: https://arxiv.org/html/2507.02790v1
Title: *From Long Videos to Engaging Clips: A Human-Inspired Video Editing Framework with Multimodal Narrative Understanding*
Authors: ByteDance + USTC (Wang et al., 2025).
Dataset: DramaAD — 831 short-drama episodes + 522 professionally edited ad clips.

---

## 0. The paper in one sentence

End-to-end "give an LLM a transcript, ask for timestamps" editing is bad. What works: rebuild the video as structured narrative data first, then decompose editing into three constrained sub-tasks (highlight, opening/ending, pruning) and run each as its own LLM call.

---

## 1. The problem, from first principles

A long video is not text. It is three synchronized streams:

1. **Pixels** (frames)
2. **Audio** (dialogue, music, ambient)
3. **Time** (fixed monotonic clock that binds 1 and 2)

A "good short clip" has three properties that are invisible if you only read the transcript:

- **Narrative continuity.** A cut inside a sentence, an argument, or a thought breaks the viewer.
- **Hook + payoff structure.** Openings must grab, endings must leave suspense or closure.
- **Density.** Dead air, filler, and transitions must be pruned, or retention collapses.

Prior art fails because it ignores one of the three streams or flattens them into one:

- **Feature-ranker methods** (Pardo 2021, Podlesnyy 2020, Hu 2023): train a model to pick shots. No narrative understanding. No interpretability. Model capacity is the ceiling.
- **ASR-only LLM methods** (FunClip, AI-YouTube-Shorts-Generator): transcribe, feed the LLM a text wall, ask for timestamps. No visual context → misses facial reactions, gestures, screen text. End-to-end one-shot prompt → abrupt transitions.

HIVE's core claim: **you cannot one-shot this. You must both (a) re-encode the video as a structured narrative and (b) decompose the editing decision into sub-tasks.**

---

## 2. The architecture, as a system diagram

```
                 ┌─────────────────────────────────────────────────────────┐
                 │  Module A: Multimodal Narrative Understanding           │
                 │                                                         │
  Long video ──▶ │  Character extraction  ──▶  face detect → cluster →     │
                 │                              MLLM → name + identity     │
                 │  Dialogue analysis     ──▶  ASR + OCR subtitles →       │
                 │                              LLM reconciliation         │
                 │  Character↔dialogue    ──▶  diarization + MLLM fusion   │
                 │  Scene segmentation    ──▶  3-stage:                    │
                 │      visual shot → local fuse → global MLLM refine      │
                 │  Comprehensive caption ──▶  MLLM over all of the above  │
                 │  Memory module         ──▶  character db + scene db     │
                 └────────────────────────┬────────────────────────────────┘
                                          │
                                          ▼
                    Scenes S = (S₁, …, Sₙ), each with full narrative text
                                          │
                 ┌────────────────────────┴────────────────────────────────┐
                 │  Module B: Human-Inspired Editing (Algorithm 1)         │
                 │                                                         │
                 │  (1) Highlight detection                                │
                 │      L(Rₕ, V)  → score every scene against rule set →   │
                 │      merge adjacent non-zero into highlight clips hᵢ    │
                 │                                                         │
                 │  (2) Opening/ending selection                           │
                 │      For each top-k hᵢ:                                 │
                 │        O = L(Rₒ, hᵢ, V) over scenes before hᵢ           │
                 │        E = L(Rₑ, hᵢ, V) over scenes after  hᵢ           │
                 │        B ← B ∪ (O × E)   (Cartesian product)            │
                 │                                                         │
                 │  (3) Content pruning                                    │
                 │      For each (o, e) ∈ B:                               │
                 │        P = L(Rₚ, V[o:e])                                │
                 │        V' ← V' ∪ CutAndSplice(V[o:e] \ P)               │
                 │                                                         │
                 │  Return V' (set of edited videos)                       │
                 └─────────────────────────────────────────────────────────┘
```

Every arrow is a strict, schema-validated JSON hop. Nothing is free-form.

---

## 3. Module A in detail — why each sub-module exists

### 3.1 Character extraction
**Why:** "Who is on screen" is a prerequisite for every downstream prompt ("why does this scene matter for character X's arc?").
**How:** face detection (RetinaFace-style) → facial embeddings → clustering into identities → MLLM enriches clusters with names/roles scraped from drama metadata.
**Result:** A `character_db` that persists across episodes via the memory module.

### 3.2 Dialogue analysis
**Why:** ASR alone is noisy. Music, overlaps, name homophones, accents — all poison transcripts. Dialogue errors cascade through every downstream decision.
**How:** ASR (Whisper/Paraformer) + OCR on burned-in subtitles + LLM reconciliation. OCR is the ground-truth anchor; ASR provides word timestamps; the LLM merges them.
**Result:** High-accuracy time-aligned dialogue that an LLM can reason about.

### 3.3 Character–dialogue matching
**Why:** "Character A says X" is a different narrative fact than "X was said." Speaker diarization alone can't handle off-screen dialogue, overlapping speech, or dubbing. Naive "visible face = speaker" fails constantly.
**How:** diarization → multi-LLM fusion (visual + audio + semantic) → accept only above confidence threshold.

### 3.4 Video scene segmentation
**Why:** Cut points matter. Traditional *shot* detection gives fragments (a single conversation is 20 shots). Editing at shot boundaries slices dialogues in half.
**How:** three stages.
1. **Visual shot segmentation** (TransNetV2 / AutoShot) → raw shot boundaries.
2. **Local shot fusion** → trained classifier merges adjacent shots of the same scene.
3. **Global semantic refinement** → MLLM merges visually dissimilar but semantically continuous shots (close-up ↔ wide shot of same conversation).
**Result:** Semantically coherent scenes, where cuts don't bisect a beat.

### 3.5 Comprehensive caption
**Why:** The editor LLM in Module B needs text it can reason over. One detailed narrative paragraph per scene is that substrate.
**How:** Gemini 1.5 Pro consumes characters, dialogue, scene boundaries, *and previous-episode summaries from the memory module*, then emits one rich caption per scene.

### 3.6 Memory module
**Why:** A 30-episode drama can't fit in context. State must be externalized.
**What it holds:**
- Character axis: visual features, relationships, dialogue history, narrative arcs across episodes.
- Narrative axis: scene segmentation results, overall storyline progression.
**How it's used:** read/written by every other sub-module; supports multi-dimensional retrieval.

---

## 4. Module B in detail — Algorithm 1, line by line

Inputs:
- Video V = (S₁, …, Sₙ) — output of Module A.
- LLM L.
- Rule sets: Rₕ (highlight), Rₒ (opening), Rₑ (ending), Rₚ (pruning).
- k — number of top highlights to keep.

Steps:

```
H  = L(Rₕ, V)                           # score every scene
H' = sort(H descending)                 # keep top k
B  = {}                                 # editing boundary set
for h' in H'[1:k]:
    O = L(Rₒ, h', V)   # opening candidates (general scenes before h' + first scene of any highlight)
    E = L(Rₑ, h', V)   # ending  candidates (general scenes after  h' + last  scene of any highlight)
    B = B ∪ (O × E)
V' = {}
for (o, e) in B:
    P  = L(Rₚ, V[o:e])                  # scenes to prune inside the window
    V' = V' ∪ CutAndSplice(V[o:e] \ P)
return V'
```

Three properties fall out of this design:

- **Interpretability.** Every scene has an explicit role (highlight / opening / ending / pruned). You can audit and override.
- **Diversity.** The Cartesian O × E is how one raw video becomes many distinct edited outputs. That is why Diversity is a first-class metric.
- **Safety.** Internal scenes of a highlight are never picked as boundaries — the narrative spine of the highlight is preserved.

### 4.1 Highlight detection — the rules Rₕ
Each scene is matched against an authored rule set (see appendix A.3, audience-gender-dependent). Each match adds points. Zero-match scenes become "general scenes" with score 0. Adjacent non-zero-scored scenes merge into a single "highlight clip" with summed score.

**Why this works:** the LLM is not asked "is this scene a highlight?" (vague). It's asked "does this scene match rule Rᵢ: does it contain a kiss, a reveal, a confrontation, a twist?" Each rule is a binary, gradable question. LLMs are much better at those.

### 4.2 Opening/ending selection — rules Rₒ, Rₑ
Opening must:
- Grab attention immediately.
- Not depend on earlier context (don't start mid-event).
- Introduce characters, setting, or premise.

Ending must:
- Stay on-topic with the highlight (don't drift into a new arc).
- Ideally leave suspense OR complete a mini arc.

Only scenes *outside* the highlight are openings/endings. This preserves the highlight's internal integrity.

### 4.3 Content pruning — rule Rₚ
Inside the `[o, e]` window, general scenes are candidates for removal. Highlight scenes are never removed. First and last scenes of the window are never removed (they set the viewing experience).

The LLM returns `{scene_id, delete: bool, thought: str}` for each candidate, wrapped in `<output>…</output>` tags.

---

## 5. Dataset — DramaAD

| Property           | Value                                              |
|--------------------|----------------------------------------------------|
| Raw videos         | 831 short-drama episodes (first 30% of 30 series)  |
| Reference edits    | 522 professional advertisement clips               |
| Resolution         | 720p–1080p                                         |
| Aspect ratio       | 9:16 (mobile-native)                               |
| Total duration     | 22 h                                               |
| Key novelty        | First drama dataset shipping *reference ad edits*  |

Why this matters: the reference edits are the gold-standard. They let every metric be grounded against "what a professional actually made," not against a fuzzy quality judgement.

---

## 6. Evaluation — what the numbers mean

Six metrics over two scenarios.

### General scenarios
- **Diversity.** 1 − average IoU across outputs given the same source. High = many different good cuts.
- **Smoothness.** Transition quality between consecutive cuts (judged 1–7).
- **Engagement.** Fraction of clips judged "engaging" by reviewers.
- **VEI** (Video Editing Index). Composite of the above.

### Advertising scenarios
- **Hook Rate.** Fraction of edited clips whose opening succeeds as a hook.
- **Suspense Rate.** Fraction whose ending holds suspense or satisfying closure.

Results (Table 2):

| Method                | Diversity | Smoothness | Engagement | VEI  | Hook | Suspense |
|-----------------------|----------:|-----------:|-----------:|-----:|-----:|---------:|
| Human (golden)        | 0.74      | 6.84       | 0.93       | 6.35 | 0.87 | 0.91     |
| End2End (ASR-only)    | 0.75      | 0.65       | 0.82       | 0.54 | 0.64 | 0.47     |
| End2End (Narration)   | 0.48      | 1.28       | 0.88       | 1.14 | 0.62 | 0.52     |
| **HIVE (full)**       | **0.66**  | **4.48**   | **0.89**   | **4.01** | **0.71** | **0.73** |
| HIVE w/o highlight    | 0.78      | 4.42       | 0.62       | 2.74 | 0.65 | 0.69     |
| HIVE w/o boundary     | 0.54      | 4.17       | 0.81       | 3.38 | 0.28 | 0.30     |
| HIVE w/o pruning      | 0.66      | 5.10       | 0.69       | 3.51 | 0.69 | 0.68     |

Read the deltas.

- **Smoothness: 0.65 → 4.48.** Nearly 7× vs the best end-to-end. This is the headline — decomposition gets you smooth cuts.
- **VEI: 1.14 → 4.01.** 3.5× the composite quality.
- **Hook/Suspense.** 0.71/0.73 vs human 0.87/0.91. Still below human, but much closer than baselines.
- **Ablations confirm every module pulls weight:**
  - Remove highlight → Engagement collapses (0.89 → 0.62).
  - Remove boundary → Hook (0.71 → 0.28) and Suspense (0.73 → 0.30) collapse.
  - Remove pruning → Engagement (0.89 → 0.69) collapses.

Translation: each sub-task is load-bearing. You can't drop any.

---

## 7. Why this is a better template than "throw it at one LLM"

Four reasons, from first principles:

1. **LLMs fail softly on big open questions, sharply on narrow ones.** "Edit this video" is open. "Does scene 7 contain a confrontation?" is narrow. HIVE rewrites the problem as a stack of narrow questions.
2. **Grounding beats hallucination.** Module A turns synchronized multimodal data into strict text. The editor LLM never sees "the video" — it sees a provably consistent narrative representation.
3. **Decomposition gives auditability.** When a bad cut ships, you can point at exactly which sub-task failed: highlight, boundary, or pruning.
4. **Decomposition gives diversity.** The Cartesian O × E multiplies valid outputs without any extra model calls per output.

---

## 8. Where HIVE still loses to humans

- Hook Rate 0.71 vs 0.87. The LLM's "attention-grabbing opening" is conservative — it trusts introduction scenes. Humans aggressively open on mid-scene tension.
- Suspense Rate 0.73 vs 0.91. Same cause — rule-driven endings are safer than intuitive ones.
- Diversity 0.66 vs 0.74. The Cartesian product is combinatorially large, but many combinations are near-duplicates after pruning.

These are prompt-engineering ceilings, not architectural ones.

---

## 9. Mapping HIVE to this repository

HIVE = **Module A (understanding) + Module B (editing)**. This repo implements the practical 9:16-podcast-to-shorts slice of both:

| HIVE concept                         | This repo                                                            |
|--------------------------------------|----------------------------------------------------------------------|
| Scene segmentation                   | `humeo_core.primitives.ingest` (PySceneDetect + keyframe export)      |
| Character extraction (faces)         | `humeo_core.primitives.face_detect` (MediaPipe, pluggable)            |
| Dialogue / ASR                       | `humeo.ingest.transcribe_whisperx` + `TranscriptWord` schema         |
| Comprehensive caption (per scene)    | `humeo_core.primitives.vision` (vision-LLM + OCR bbox primitive)      |
| Highlight detection                  | `humeo_core.primitives.select_clips` (density heuristic; LLM pluggable in `humeo.clip_selector`) |
| Opening/ending selection             | Covered inside `clip_selector` (the LLM picks clip boundaries)       |
| Content pruning                      | Future work — see `SOLUTIONS.md §6` for design                       |
| Memory module                        | Future work — artefacts on disk already support this                 |
| Strict JSON at every hop             | `humeo_core.schemas` (Pydantic, validated, single source of truth)    |
| Decomposed editing via tools         | `humeo_core.server` (each primitive is its own MCP tool)              |

The big architectural lesson we copied: **every intermediate artefact is strict JSON, every primitive is one file, every boundary is schema-validated.** That's HIVE §7 ("what to learn from the paper") applied directly.

---

## 10. Anti-patterns the paper flags (and we inherit)

- **Don't** dump raw video into one LLM prompt.
- **Don't** skip scene segmentation.
- **Don't** emit free-form text from LLMs — always force JSON via schema.
- **Don't** re-run expensive extraction on retries — cache scene timestamps, transcripts, keyframes.
- **Don't** optimize a single opaque objective — decompose and audit.

---

## 11. Bottom line

Video editing is not a generation problem. It is a **staged reasoning problem with a fixed rendering backend**. HIVE's contribution is the shape of the reasoning stack, the proof that decomposition measurably beats end-to-end, and the first dataset that can verify both.

For builders: don't train a model, orchestrate a pipeline. Keep the primitives narrow. Keep the schemas strict. Keep the LLM out of anything deterministic.
