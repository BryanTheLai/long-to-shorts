"""Environment bootstrap (``.env``) and cache path helpers."""

from __future__ import annotations

import os
from pathlib import Path

_BOOTSTRAPPED = False


def bootstrap_env() -> None:
    """Load ``.env`` from the process cwd (non-fatal if missing). Safe to call twice."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    _BOOTSTRAPPED = True


def default_humeo_cache_root() -> Path:
    """Default cache root: ``~/.cache/humeo`` on Unix; ``%LOCALAPPDATA%/humeo`` on Windows."""
    override = (os.environ.get("HUMEO_CACHE_ROOT") or "").strip()
    if override:
        return Path(override)
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "humeo"
    return Path.home() / ".cache" / "humeo"


def resolve_gemini_api_key() -> str:
    """Return an API key for Gemini, or raise if none is configured.

    Prefer ``GOOGLE_API_KEY``; fall back to ``GEMINI_API_KEY``. Values are read from
    the environment after ``bootstrap_env()`` (``.env`` in cwd).

    We require an explicit key so we do not fall back to Application Default
    Credentials (e.g. ``gcloud auth application-default login``), which often
    lack the Generative Language API scope and produce
    ``403 ACCESS_TOKEN_SCOPE_INSUFFICIENT``.
    """
    bootstrap_env()
    for env_name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        val = (os.environ.get(env_name) or "").strip()
        if val:
            return val
    raise ValueError(
        "Set GOOGLE_API_KEY or GEMINI_API_KEY for Gemini clip selection. "
        "See docs/ENVIRONMENT.md. Without an API key the client may use ADC and fail "
        "with insufficient scopes (403)."
    )
