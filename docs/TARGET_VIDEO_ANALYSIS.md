# TARGET_VIDEO_ANALYSIS.md - *ITK with Cathie Wood: Is AI Winning The War On Inflation?*

Source: https://www.youtube.com/watch?v=PdVv_vLkUgk
Length: 46:23 · Channel: ARK Invest · Published: 2026-04-09

## Why this is a near-perfect test case

This repo exists to turn long-form chart-heavy interviews into 9:16 shorts. This video is that exact format.

1. **Host + guest (`zoom_call_center` / `sit_center`).** Cathie Wood sits in a stable talking-head frame for long stretches.
2. **Chart chapters (`split_chart_person`).** "War Disrupts Deficit Progress", "Dollar Strength Catches Markets Off Guard", "Productivity Boom", and "Inflation Pressures Continue To Crack" all pivot into chart-led material.
3. **Chapter markers already segment the narrative.** They provide high-confidence candidate boundaries for hooks and chart reveals.

| Ch. | Time  | Topic                                     | Expected layout(s)   |
|-----|-------|-------------------------------------------|----------------------|
| 0   | 00:00 | ARK x Kalshi Partnership                  | `sit_center`         |
| 1   | 02:30 | A New Era For Active Investing            | `sit_center`         |
| 2   | 04:30 | A Multi-Trillion-Dollar Opportunity       | `sit_center`         |
| 3   | 06:30 | War Disrupts Deficit Progress             | `split_chart_person` |
| 4   | 14:15 | Dollar Strength Catches Markets Off Guard | `split_chart_person` |
| 5   | 23:30 | Productivity Boom Is Closer Than Expected | `split_chart_person` |
| 6   | 30:00 | Inflation Pressures Continue To Crack     | `split_chart_person` |
| 7   | 42:30 | Credit Markets Show No Signs Of Stress    | `sit_center`         |
| 8   | 43:30 | Innovation Could Power The Next Bull Market | `sit_center`       |

## Why vision + OCR beats face-only here

Chart-heavy chapters need visible slide text and correct split geometry. Face-only paths lose the slide, and transcript-only selection cannot tell when the chart becomes the real subject.

The current product path is the right one for this source:

- Stage 2 remains transcript-only clip selection.
- Stage 3 samples multiple frames per clip, calls the configured multimodal provider (`gemini`, `openai`, or `azure`), and merges those frame opinions into one render-safe `LayoutInstruction`.
- Model-facing boxes use the 0..1000 contract and are normalized back to the internal `[0,1]` render schema.

## Suggested product run

```bash
uv run humeo --long-to-shorts "https://www.youtube.com/watch?v=PdVv_vLkUgk"
```

For a rerender-only geometry check on an existing cached work dir:

```bash
uv run humeo --work-dir .humeo_work --start-at layout-vision --force-layout-vision
```

## What we expect in the final shorts

| Clip type     | Source scenes (ch.) | Expected count | Expected layout      |
|---------------|---------------------|---------------:|----------------------|
| Hook / opener | 0, 2                | 1              | `sit_center`         |
| Chart reveals | 3, 4, 5, 6          | 2-3            | `split_chart_person` |
| Payoff / close | 8                  | 1              | `sit_center`         |

Target: 4-5 shorts, 50-90s each, burned subtitles, and an overlay title derived from the clip topic or visible chart framing.

## Current regression value

This video is also the canonical regression case for the Stage 3 split-layout bug fixed on 2026-04-22. The failing mode was not Azure itself; it was missing `cv2` frame sampling followed by a bad `sit_center` fallback. The fixed rerender restored chart-preserving `split_chart_person` outputs for the chart-led shorts.

## Bottom line

This is the canonical demo and regression source for Humeo. The five-layout renderer, multi-frame layout vision, burned subtitles, and chart/person split logic all show up clearly here.
