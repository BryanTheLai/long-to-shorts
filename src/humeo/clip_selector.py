"""
Step 2 - Clip Selection: Use an LLM to identify viral-worthy segments.

Responsibilities:
  - Send transcript to LLM with a structured prompt.
  - Parse the response into validated ``humeo_mcp.schemas.Clip`` objects
    (single source of truth - shared with the MCP primitives).
  - Output clips.json for downstream consumption.
"""

import json
import logging
from pathlib import Path

from humeo_mcp.schemas import Clip, ClipPlan

from humeo.config import MAX_CLIP_DURATION_SEC, MIN_CLIP_DURATION_SEC, TARGET_CLIP_COUNT

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a viral content editor. You analyze podcast transcripts and identify
the most compelling 30-60 second segments that would perform well as short-form vertical videos
on TikTok, YouTube Shorts, and Instagram Reels.

For each clip you identify, evaluate these factors:
- Strong emotional hook in the first 3 seconds
- Self-contained idea (doesn't require external context)
- Surprising or counterintuitive claim
- Quotable phrasing
- Clear takeaway or "aha moment"

Return your analysis as a JSON object with this exact schema:
{{
  "clips": [
    {{
      "clip_id": "001",
      "topic": "Brief topic label",
      "start_time_sec": 123.0,
      "end_time_sec": 165.5,
      "viral_hook": "The attention-grabbing opening line or idea",
      "virality_score": 0.94,
      "transcript": "Full verbatim text of this segment for subtitle generation",
      "suggested_overlay_title": "Short punchy title for overlay (max 5 words)"
    }}
  ]
}}

Rules:
- Each clip must be between {min_dur} and {max_dur} seconds.
- Return exactly {count} clips, ranked by virality_score (highest first).
- Timestamps must be exact, matching the word-level timestamps provided.
- The transcript field must contain the EXACT text from the source, not paraphrased.
- Return ONLY the JSON object. No markdown, no explanation."""


def build_prompt(transcript: dict) -> tuple[str, str]:
    """Return ``(system_prompt, transcript_text)`` for the clip-selector LLM call."""
    lines = []
    for seg in transcript.get("segments", []):
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        lines.append(f"[{start:.1f}s - {end:.1f}s] {text}")

    transcript_text = "\n".join(lines)

    system = SYSTEM_PROMPT.format(
        min_dur=MIN_CLIP_DURATION_SEC,
        max_dur=MAX_CLIP_DURATION_SEC,
        count=TARGET_CLIP_COUNT,
    )

    return system, transcript_text


def select_clips_gemini(transcript: dict) -> list[Clip]:
    """Use Google Gemini to identify viral clips."""
    import google.generativeai as genai

    system_prompt, transcript_text = build_prompt(transcript)

    model = genai.GenerativeModel(
        "gemini-2.0-flash",
        system_instruction=system_prompt,
    )

    logger.info("Sending transcript to Gemini for clip selection...")
    response = model.generate_content(
        f"Analyze this podcast transcript and identify the top viral clips:\n\n{transcript_text}",
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    return _parse_clips(response.text)


def select_clips_openai(transcript: dict) -> list[Clip]:
    """Use OpenAI GPT to identify viral clips."""
    from openai import OpenAI

    system_prompt, transcript_text = build_prompt(transcript)
    client = OpenAI()

    logger.info("Sending transcript to OpenAI for clip selection...")
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Analyze this podcast transcript and identify the top viral clips:\n\n{transcript_text}",
            },
        ],
        temperature=0.3,
    )

    return _parse_clips(response.choices[0].message.content)


def _parse_clips(raw_json: str) -> list[Clip]:
    """Parse and validate the LLM's JSON response into Clip objects.

    Accepts either ``{"clips": [...]}`` or a bare list. Validation is
    delegated to Pydantic so malformed model output is rejected here,
    not deep in the pipeline.
    """
    data = json.loads(raw_json)
    clips_data = data.get("clips", data) if isinstance(data, dict) else data

    clips: list[Clip] = []
    for item in clips_data:
        payload = dict(item)
        payload.pop("duration_sec", None)
        clip = Clip.model_validate(payload)

        actual_dur = clip.end_time_sec - clip.start_time_sec
        stated_dur = item.get("duration_sec")
        if stated_dur is not None and abs(actual_dur - float(stated_dur)) > 1.0:
            logger.warning(
                "Clip %s: stated duration %.1fs doesn't match (%.1f-%.1f = %.1f).",
                clip.clip_id, float(stated_dur),
                clip.start_time_sec, clip.end_time_sec, actual_dur,
            )
        clips.append(clip)

    logger.info("Parsed %d clips from LLM response", len(clips))
    return clips


def select_clips(transcript: dict, provider: str = "gemini") -> list[Clip]:
    """
    Route to the appropriate LLM provider for clip selection.

    Args:
        transcript: The word-level transcript dict.
        provider: Either "gemini" or "openai".

    Returns:
        List of Clip objects sorted by virality_score descending.
    """
    if provider == "gemini":
        clips = select_clips_gemini(transcript)
    elif provider == "openai":
        clips = select_clips_openai(transcript)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Use 'gemini' or 'openai'.")

    return sorted(clips, key=lambda c: c.virality_score, reverse=True)


def save_clips(clips: list[Clip], output_path: Path) -> Path:
    """Persist clips to a JSON file using the shared Pydantic schema."""
    plan = ClipPlan(source_path="", clips=list(clips))
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(plan.model_dump_json(indent=2))
    logger.info("Saved %d clips to %s", len(clips), output_path)
    return output_path


def load_clips(clips_path: Path) -> list[Clip]:
    """Load clips from a previously saved JSON file."""
    with open(clips_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "clips" in data:
        return [Clip.model_validate(c) for c in data["clips"]]
    return [Clip.model_validate(c) for c in data]
