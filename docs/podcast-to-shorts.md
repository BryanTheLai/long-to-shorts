---
title: Podcast-to-Shorts Pipeline
type: mvp-spec
status: draft
---

# Podcast to shorts (product blurb)

**Goal:** Turn a long YouTube podcast or interview into several **9:16** MP4 shorts with burned subtitles and a title overlay.

**CLI:** `uv run humeo --long-to-shorts "<youtube_url>"` (see repo root `README.md` for install and flags).

**How it works (one sentence):** Download + transcript -> structured clip selection -> hook detection -> inner-clip pruning -> multi-frame layout vision -> ffmpeg render.

**Canonical detail (do not duplicate here):** [`docs/PIPELINE.md`](PIPELINE.md) - stages, durations, caches, artifacts.

**Terminology:** [`TERMINOLOGY.md`](../TERMINOLOGY.md) - time window vs crop/layout.

**Gaps / roadmap:** [`docs/TODO.md`](TODO.md) for the historical design plan and [`docs/PROJECT_ISSUES.md`](PROJECT_ISSUES.md) for the current issue list. Prompt-vs-code quirks live in [`docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`](KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md).

**Layout subject (zoom vs split chart):** Product uses provider-swappable multimodal Stage 3 plus `humeo-core` layouts. The main open product question is no longer split math; it is whether one merged layout per clip should evolve into a layout timeline for clips that genuinely change structure mid-run.
