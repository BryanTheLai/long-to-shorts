# HIVE Paper — Blunt, High-Signal Guide

## 1) Paper in One Sentence
The paper says short-video editing fails when you use transcript-only cutting; better results come from multimodal narrative understanding plus scene-level editing steps that mimic human editors.

## 2) First-Principles Breakdown

### Real Problem
- Input is not "text". Input is synchronized multimodal data: frames + audio + timing.
- Good edits require story continuity, not just keyword matching.
- Transcript-only methods miss visual context, so cuts feel incoherent.

### Core Claim
- You cannot "one-shot prompt" a long video into a good short.
- You must:
  1. Understand narrative from both visuals and speech.
  2. Decompose editing into constrained sub-tasks.

## 3) What the Framework (HIVE) Actually Does

## Pillar A: Multimodal Narrative Understanding
- Character extraction: who is on screen.
- Dialogue analysis: what is said and why it matters.
- Narrative summarization: combine visual + text to infer plot and intent.

## Pillar B: Scene-Level Task Decomposition
- Segment by scene first.
- Then run three editing tasks:
  1. Highlight detection.
  2. Opening/ending selection (hook + close).
  3. Irrelevant content pruning (dead air/filler/transitions).

## 4) Why This Beats End-to-End Methods
- End-to-end approaches optimize a single black-box objective and miss local structure.
- HIVE adds explicit constraints at each stage.
- This reduces abrupt cuts and improves narrative coherence.
- The paper reports stronger performance on their benchmark dataset (DramaAD).

## 5) Dataset / Evaluation Signal in Your Notes
- DramaAD benchmark is used to validate the approach.
- Composition in your notes:
  - 800 short dramas.
  - 500 professional ads.
- Main result direction: stepwise human-inspired editing > transcript-only end-to-end baselines.

## 6) Direct Translation to Your CLI Tool

## Stage 1: Ingestion (Local, deterministic)
Inputs: `long_video.mp4`
- Scene detection (`PySceneDetect`) -> `scene_timestamps.json`
- Audio extraction (`ffmpeg`) + ASR (`faster-whisper`) -> `transcript_words.json`
- Keyframe extraction (`ffmpeg`) -> `keyframes/`

## Stage 2: Context Agent (Multimodal)
Input: keyframes + transcript.
Output: `narrative_context.json` with:
- `global_summary`
- `characters`
- `core_conflict_or_value`

## Stage 3: Editor Agents (Decomposed reasoning)
Use shared `narrative_context.json` for all agents.

1) **Structure Agent**
- Find strongest 3–5s hook and 5–10s ending.
- Output precise timestamps.

2) **Highlight Agent**
- Score scenes by relevance to `core_conflict_or_value`.
- Select best segments to fill target duration.

3) **Micro-Pruning Agent**
- Remove silence > threshold, filler words, dead air.
- Output micro-cut timestamp ranges.

## Stage 4: Compiler
- Assemble timeline: `[Hook] + [Highlights after micro-cuts] + [Outro]`
- Render with `ffmpeg` / `ffmpeg-python`.
- Output: `short_video.mp4`

## 7) Minimal JSON Contracts (Non-negotiable)
Use strict schemas so every stage is machine-checkable.

- `Scene`: `scene_id`, `start_time`, `end_time`, `keyframe_path`
- `TranscriptWord`: `word`, `start_time`, `end_time`
- `NarrativeContext`: `global_summary`, `characters[]`, `core_hook`
- `VideoStructure`: `hook_scene_ids[]`, `highlight_scene_ids[]`, `outro_scene_ids[]`
- `MicroCut`: `start_time`, `end_time`, `reason`

## 8) What to Learn from the Paper (Actionable)
- Do not train a giant model first.
- Build an orchestrated pipeline with strict intermediate artifacts.
- Keep extraction deterministic and local.
- Use LLMs for reasoning only, not for raw media processing.
- Force structured outputs (JSON schema) at every model call.

## 9) Local vs Cloud Compute (Your Practical Decision)

### Best 80/20 Architecture
- **Local**: scene detection, audio extraction, ASR, keyframe extraction.
- **Cloud/API**: multimodal narrative reasoning + structured edit decisions.
- **Local**: final FFmpeg compile.

This keeps cost low, latency acceptable, and quality high.

### Scaling Rule
- If GPU is weak and videos are long, reduce frame sampling density first.
- Cache all extraction artifacts (`scene_timestamps`, transcript, keyframes) so retries only re-run model calls.
- Batch model requests by scene windows, not full-video every time.

## 10) Build Order (Fastest Path to Working Product)
1. Implement deterministic extraction pipeline.
2. Add one context model call with strict schema validation.
3. Add structure + highlight agents.
4. Add micro-pruning.
5. Add FFmpeg compiler.
6. Add CLI wrapper (`humeo --long-to-shorts <url_or_path>`).
7. Add metrics: duration hit-rate, coherence rating, and manual retention proxy.

## 11) Anti-Patterns (Do Not Do)
- Do not send full raw video directly to an LLM and expect robust edits.
- Do not skip scene segmentation.
- Do not let agents output free-form text without schema validation.
- Do not re-run expensive extraction every retry.

## 12) Bottom Line
The paper’s core insight: treat video editing as a staged reasoning system, not a monolithic generation problem. For your CLI, this is high-ROI because you can ship strong quality with orchestration, not model training.
