# HIVE Paper — Blunt, High-Signal Guide

**Pairing doc:** Full paper walk-through, metrics, and repo mapping live in [`PAPER_BREAKDOWN.md`](PAPER_BREAKDOWN.md). This file is the **one-pager** plus paper lessons—not a second copy of the long breakdown.

---

## 1) Paper in One Sentence

Short-video editing fails when you use **transcript-only** cutting; better results come from **multimodal narrative understanding** plus **scene-level editing** steps that mimic human editors.

---

## 2) First-Principles Breakdown

- Input is **not** text alone: frames + audio + time stay synchronized.
- You cannot **one-shot** a long video into a good short; you need **decomposed** sub-tasks with constraints.

---

## 3) What HIVE Does (Two Pillars)

**Pillar A — Multimodal narrative:** characters, dialogue, captions, memory across episodes.

**Pillar B — Scene-level editing:** highlights → opening/ending around them → prune filler.

**Results / dataset:** See [`PAPER_BREAKDOWN.md`](PAPER_BREAKDOWN.md) §5–§6 (DramaAD, metrics, Table 2).

---

## 4) How This Repo Maps (Shipped Product)

**Canonical runtime:** [`docs/PIPELINE.md`](../PIPELINE.md) — `ingest → clip selection → hook detection → content pruning → layout vision → render`.

The paper’s ideal **narrative_context.json before clip select** is **not** the shipped path yet; see [`docs/TODO.md`](../TODO.md) §0–§2 for that north star.

---

## 5) Paper Lessons You Should Actually Steal

- **Orchestrate**, don’t train a giant model first.
- **Strict JSON** at every hop (this repo: `humeo_core.schemas` + provider-side `response_schema` validation).
- **Deterministic** media steps local; **LLM** for decisions only.
- **Cache** transcripts and intermediates so retries re-run model calls only.

**Anti-patterns:** Raw video into one LLM prompt; skipping segmentation; free-form LLM output; re-running expensive extraction every retry. (Expanded in [`PAPER_BREAKDOWN.md`](PAPER_BREAKDOWN.md) §10–§11.)

---

## 6) Local vs Cloud (80/20)

- **Local:** download, ffmpeg, ASR, scene/keyframe extraction where used.
- **Cloud/API:** provider-swappable clip + hook + prune + layout vision (`gemini`, `openai`, `azure`).
- **Local again:** final ffmpeg compile.

---

## 7) Bottom Line

Treat editing as **staged reasoning + a fixed render backend**—that is the portable insight from HIVE, whether the payload is drama or podcast.
