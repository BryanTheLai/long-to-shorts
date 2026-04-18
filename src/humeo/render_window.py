"""Map LLM clip timing (segment + trim + hook) to one ffmpeg source window.

``humeo_mcp.primitives.compile`` already cuts with ``-ss`` / ``-t`` from ``Clip``;
this module is the single place that turns trim/hook fields into concrete bounds.
"""

from __future__ import annotations

from humeo_mcp.schemas import Clip


def effective_export_bounds(clip: Clip) -> tuple[float, float]:
    """Return ``(start_sec, end_sec)`` on the source timeline for the exported short.

    1. **Trim** narrows ``[start_time_sec, end_time_sec]``.
    2. **Hook** (optional) intersects ``[start + hook_start, start + hook_end]`` with
       the trimmed range. Empty intersection falls back to trim-only, then full segment.
    """
    s0 = clip.start_time_sec
    s1 = clip.end_time_sec

    t_lo = s0 + clip.trim_start_sec
    t_hi = s1 - clip.trim_end_sec
    if t_hi <= t_lo:
        t_lo, t_hi = s0, s1

    if clip.hook_start_sec is not None and clip.hook_end_sec is not None:
        h_lo = s0 + clip.hook_start_sec
        h_hi = s0 + clip.hook_end_sec
        n_lo = max(t_lo, h_lo)
        n_hi = min(t_hi, h_hi)
        if n_hi > n_lo:
            t_lo, t_hi = n_lo, n_hi
        else:
            t_lo = s0 + clip.trim_start_sec
            t_hi = s1 - clip.trim_end_sec
            if t_hi <= t_lo:
                t_lo, t_hi = s0, s1

    if t_hi <= t_lo:
        t_lo, t_hi = s0, s1

    return t_lo, t_hi


def clip_for_render(clip: Clip) -> Clip:
    """Copy with ``start``/``end`` set to the actual cut; trim/hook cleared."""
    t0, t1 = effective_export_bounds(clip)
    return clip.model_copy(
        update={
            "start_time_sec": t0,
            "end_time_sec": t1,
            "trim_start_sec": 0.0,
            "trim_end_sec": 0.0,
            "hook_start_sec": None,
            "hook_end_sec": None,
        }
    )
