# Humeo MCP — Reusable Rocket Architecture

This document is the first-principles design note that pairs with the
[HIVE paper guide](./hive_paper_blunt_guide.md) and
[podcast-to-shorts pipeline spec](./podcast-to-shorts.md). The working
implementation lives in [`/humeo-mcp`](../humeo-mcp/).

## TL;DR

> We don't build doors or windows. We build a container with landing gear
> and three thrusters that point in three directions. That is exactly what
> this MCP is.

- **Container** — strict JSON contracts (`schemas.py`).
- **Landing gear** — deterministic local extraction (scenes, keyframes,
  optional transcript) in `primitives/ingest.py`.
- **Three thrusters** — the three 9:16 layouts the source video actually
  uses, hard-coded as pure ffmpeg filtergraph math in
  `primitives/layouts.py`.
- **Pilot** — scene classifier + clip selector, both with a heuristic
  default and an LLM-ready callback hook.
- **Control panel** — `FastMCP` server exposing every primitive as a tool.

## Why this is the right shape

### 1. The video format constrains the problem, hard

The source video has exactly three on-screen geometries:

1. Zoom call, one person, subject centered, tight crop.
2. One person sitting, subject centered, wider framing.
3. Explainer scene: chart on the left (~2/3), person on the right (~1/3).

A general subject-tracker ML model is the *wrong* answer here. It is more
expensive, less reliable, harder to test, and overkill. The right answer
is three deterministic crop/compose recipes. Full stop.

### 2. The HIVE paper tells us to decompose

From [`hive_paper_blunt_guide.md`](./hive_paper_blunt_guide.md):

> Build an orchestrated pipeline with strict intermediate artifacts.
> Keep extraction deterministic and local. Use LLMs for reasoning only,
> not for raw media processing. Force structured outputs (JSON schema)
> at every model call.

This MCP literally is that pipeline. Each "sub-task" is a single tool.
Each tool has a Pydantic schema on the way in and on the way out.

### 3. MCP is a better UI than a drag-and-highlight tool

For the podcast-editing-for-coaches ICP described in
[`humeo.md`](./humeo.md), the agent-first workflow is: give the agent a
URL, get shorts back. A drag-and-highlight UI doesn't help that buyer —
they don't want to edit, they want the outcome.

## What got built

In this branch under [`/humeo-mcp`](../humeo-mcp/):

- `pyproject.toml`, installable as `humeo-mcp`.
- `src/humeo_mcp/schemas.py` — the JSON contracts.
- `src/humeo_mcp/primitives/` — ingest, layouts, classify, select_clips, compile.
- `src/humeo_mcp/server.py` — FastMCP server with 7 tools + 1 resource.
- `src/humeo_mcp/cli.py` — `humeo` CLI mirror of the MCP tools.
- `tests/` — 30 unit tests covering schemas, layout math, ffmpeg
  command construction, classifier edge cases, clip-selection scoring,
  and end-to-end tool wiring.
- `docs/ARCHITECTURE.md`, `docs/MCP_USAGE.md` — architecture + usage.
- `examples/render_request.json` — copy-pasteable RenderRequest.

## How this maps to the original spec

| Spec section                                  | Implementation                                                                 |
| --------------------------------------------- | ------------------------------------------------------------------------------ |
| Ingestion + transcription                     | `primitives/ingest.py::ingest()` + optional `transcribe_audio`                 |
| Clip selection → structured JSON              | `primitives/select_clips.py` → `ClipPlan`                                      |
| Segment cutting + vertical formatting         | `primitives/compile.py` + `primitives/layouts.py` (the three thrusters)        |
| Option 1 "UI to drag and highlight subject"   | ❌ **dropped on purpose** — MCP tool is the agent-native UI                    |
| Option 2 "4:3 inside 9:16 black bars"         | Superseded by the three real layouts                                           |
| Option 3 "one-subject-focus with tracker"     | ❌ **dropped on purpose** — not needed, three fixed geometries cover the video |

The intent is not to ship less, it's to ship the **correct** thing. If
the video format grows a fourth layout, adding a thruster is a pure
additive change (new `plan_*` fn + one enum variant + one dispatch entry).
