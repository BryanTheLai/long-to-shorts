# TARGET_VIDEO_ANALYSIS.md — *ITK with Cathie Wood: Is AI Winning The War On Inflation?*

Source: https://www.youtube.com/watch?v=PdVv_vLkUgk
Length: 46:23 · Channel: ARK Invest · Published: 2026-04-09

## Why this is a near-perfect test case

This repo exists to turn long-form chart-heavy interviews into 9:16 shorts. This video is that *exact* format.

1. **Host + guest (`zoom_call_center` / `sit_center`).** Cathie Wood in a solo seated frame through most of the talk.
2. **Screen-shared charts (`split_chart_person`).** Chapters "PPI vs CPI divergence", "Dollar Strength Catches Markets Off Guard", "Productivity Boom" are guaranteed to cut to slides with labeled axes.
3. **Chapter markers already segment the narrative** — free high-confidence highlight boundaries:

| Ch. | Time       | Topic                                             | Expected layout(s)          |
|-----|------------|---------------------------------------------------|-----------------------------|
| 0   | 00:00      | ARK × Kalshi Partnership                          | `sit_center`                |
| 1   | 02:30      | A New Era For Active Investing                    | `sit_center`                |
| 2   | 04:30      | A Multi-Trillion-Dollar Opportunity               | `sit_center`                |
| 3   | 06:30      | War Disrupts Deficit Progress                     | `split_chart_person`        |
| 4   | 14:15      | Dollar Strength Catches Markets Off Guard         | `split_chart_person`        |
| 5   | 23:30      | Productivity Boom Is Closer Than Expected         | `split_chart_person`        |
| 6   | 30:00      | Inflation Pressures Continue To Crack             | `split_chart_person`        |
| 7   | 42:30      | Credit Markets Show No Signs Of Stress            | `sit_center`                |
| 8   | 43:30      | Innovation Could Power The Next Bull Market       | `sit_center`                |

## Why Bryan's scene-change + vision-LLM + OCR path matters here

The MediaPipe-only backend would do badly on this video:

- **Chart scenes have no face**, so MediaPipe falls through to blurred pad — the chart content itself is not emphasized.
- **The speaker shares screen**, so the face bbox is pushed far right. The heuristic handles this, but it can't read the chart title or the axis labels — it just knows "face on right → assume chart left."

The vision-LLM + OCR primitive (`humeo_core.primitives.vision`) solves this directly:

- Reads the chart title ("PPI vs CPI divergence").
- Returns both `person_bbox` and `chart_bbox` with accurate geometry.
- Surfaces the chart's OCR text so a render/title layer can echo the on-screen label.

For this exact video, the bbox primitive is the *right* backend.

## Suggested product run

```bash
humeo --long-to-shorts "https://www.youtube.com/watch?v=PdVv_vLkUgk"
```

Today the product wrapper uses the stable heuristic scene-classification path.
The richer LLM+OCR bbox path lives in `humeo-core` and remains the right next
upgrade for this exact video.

## What we expect in the final shorts

| Clip type     | Source scenes (ch.)      | Expected count | Expected layout         |
|---------------|--------------------------|---------------:|-------------------------|
| Hook/opener   | ch 0, 2                  | 1              | `sit_center`            |
| Chart reveals | ch 3, 4, 5, 6            | 2–3            | `split_chart_person`    |
| Payoff/close  | ch 8                     | 1              | `sit_center`            |

Target: 4–5 shorts, 30–60 s each, burned subtitles, AUTO-derived overlay title from the OCR'd chart headings where applicable.

## Bottom line

This video is the canonical use case. Every primitive in this repo — scene detection, bbox-driven layout, three-way ffmpeg filtergraph, burn-in subs — was designed for exactly this shape of content.
