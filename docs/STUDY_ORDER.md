# One-day study order (interview prep)

Blunt: read in this order so you always know **what runs** before **why it is shaped** and **where the code is**.

Full index of every `docs/*.md` file: **`docs/README.md`**.

## Block 1 — Morning (2–3 hours): product truth

1. **`docs/PIPELINE.md`** — The actual `run_pipeline` stages, caches, when Gemini runs, and what files land on disk. This is the spine.
2. **`TERMINOLOGY.md`** — So you never confuse a temporal **clip window** with a spatial **crop/layout**.
3. **`README.md` (repo root)** — Two packages: `src/humeo` (product) vs `humeo-core/` (engine + MCP).

## Block 2 — Late morning (1–2 hours): decisions you can defend

4. **`docs/SOLUTIONS.md`** — What you rejected, what you kept, and the three-detector diagram (heuristic / MediaPipe / vision LLM → same `SceneRegions`).
5. **`docs/hive-paper/PAPER_BREAKDOWN.md`** — Read §0–§2 for the HIVE story, then **§9 (mapping table)** to tie paper rows to modules (`humeo_core.*`).

## Block 3 — Afternoon (2 hours): paper shortcut + engine surface

6. **`docs/hive-paper/hive_paper_blunt_guide.md`** — Fast recap; cross-check you understood §9 of the long breakdown.
7. **`humeo-core/docs/ARCHITECTURE.md`** — Rocket metaphor mapped to files.
8. **`humeo-core/docs/MCP_USAGE.md`** — How to point an MCP client at the server (`humeo-core` command; `humeo-mcp` remains an install alias).

## Block 4 — Afternoon (2 hours): code you can point to in a screen share

Skim in this order (do not deep-read every line unless you have time):

| Order | File | Why |
|------:|------|-----|
| 1 | `src/humeo/pipeline.py` | Stages 1, 2, 2.25, 2.5, 3, 4 wired together |
| 2 | `src/humeo/clip_selector.py` | Gemini clip JSON → `Clip` |
| 3 | `src/humeo/render_window.py` | Trim → ffmpeg source window |
| 4 | `humeo-core/src/humeo_core/primitives/compile.py` | `-ss` / `-t` + filtergraph + subtitles last |
| 5 | `humeo-core/src/humeo_core/schemas.py` | `Clip`, `LayoutInstruction`, `RenderRequest` |

## Block 5 — Evening (1 hour): ops + demo narrative

9. **`docs/ENVIRONMENT.md`** — Keys, cache dirs, model env vars.
10. **`docs/TARGET_VIDEO_ANALYSIS.md`** — The “why this video” story for quality discussion.
11. **`docs/mcp_architecture.md`** — Where MCP sits relative to the CLI (short).

## Optional / if time

- **`docs/KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`** — Where prompts diverge from code (e.g. `score_breakdown` not ranked; hook vs export window; unused `clips.json` fields).
- **`docs/SHARING.md`** — Raw GitHub links, Pages, why MP4s are not in the repo.
- **`docs/podcast-to-shorts.md`**, **`docs/humeo.md`** — Product wording (short; defers to `PIPELINE.md`).
- **`docs/TODO.md`** — Historical design doc plus still-open north-star milestones (for example `narrative_context.json` and layout timelines).
- **`docs/bryans_ideas.md`** — Brainstorm context; shipped bbox idea is spelled in `SOLUTIONS.md` §4.

## Same-day verification (15 minutes)

```bash
uv sync --extra dev
uv run pytest
```

If you only remember **four** artifacts after one day, remember: **`PIPELINE.md`**, **`SOLUTIONS.md`**, **`hive-paper/PAPER_BREAKDOWN.md` §9**, and **`KNOWN_LIMITATIONS_AND_PROMPT_CONTRACT_GAP.md`** when the model output does not match runtime behavior.
