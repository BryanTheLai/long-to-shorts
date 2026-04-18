"""Load Jinja2 prompt templates (editable; override dir via HUMEO_PROMPTS_DIR)."""

from __future__ import annotations

import os
from pathlib import Path

import jinja2


def _prompt_loader() -> jinja2.BaseLoader:
    override = (os.environ.get("HUMEO_PROMPTS_DIR") or "").strip()
    if override:
        return jinja2.FileSystemLoader(str(Path(override).expanduser()))
    return jinja2.PackageLoader("humeo", "prompts")


def clip_selection_prompts(
    *,
    transcript_text: str,
    min_dur: float,
    max_dur: float,
    count: int,
) -> tuple[str, str]:
    """Return ``(system_instruction, user_message)`` for Gemini clip selection."""
    env = jinja2.Environment(loader=_prompt_loader(), autoescape=False, trim_blocks=True)
    ctx = {
        "min_dur": min_dur,
        "max_dur": max_dur,
        "count": count,
        "transcript_text": transcript_text,
    }
    system = env.get_template("clip_selection_system.jinja2").render(**ctx)
    user = env.get_template("clip_selection_user.jinja2").render(**ctx)
    return system, user
