# Using humeo-mcp from an MCP client

## 1. Add to your client

`claude_desktop_config.json` or `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "humeo": {
      "command": "humeo-mcp"
    }
  }
}
```

## 2. A typical agent plan

```
→ humeo.list_layouts()
    # discover the 3 layouts

→ humeo.ingest(source_path="/abs/long.mp4", work_dir="/abs/work", with_transcript=true)
    # IngestResult: scenes[], keyframes, transcript_words[]

→ humeo.classify_scenes(scenes=<IngestResult.scenes>)
    # SceneClassification[] — one layout per scene

→ humeo.select_clips(
      source_path=..., transcript_words=..., duration_sec=...,
      target_count=5, min_sec=30, max_sec=60
  )
    # ClipPlan — top non-overlapping clips

# For each clip, pick the layout of the scene its midpoint falls in,
# build a LayoutInstruction, and:

→ humeo.build_render_cmd(request={...})
    # dry-run: returns the exact ffmpeg argv, no execution

→ humeo.render_clip(request={..., "mode": "normal"})
    # actually renders the 9:16 MP4
```

## 3. Strict JSON all the way

Every request/response is validated against the schemas in
[`schemas.py`](../src/humeo_mcp/schemas.py). Invalid input is rejected
*before* ffmpeg is touched, so a confused agent can't accidentally
rm-rf your disk or burn GPU hours.

## 4. Override knobs

`LayoutInstruction` accepts `zoom`, `person_x_norm`, `chart_x_norm`.
An agent (or a human via the CLI) can override the defaults per-clip
without touching any code. Example:

```json
{
  "clip_id": "001",
  "layout": "split_chart_person",
  "zoom": 1.0,
  "person_x_norm": 0.83,
  "chart_x_norm": 0.02
}
```

## 5. When to stay in dry-run

- You want to show an approval UI before spending CPU.
- You want to diff the planned ffmpeg commands against a previous run.
- You're building tests.

`mode="dry_run"` is always safe, never writes output, and returns the
exact argv list.
