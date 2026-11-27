"""What the Review section says: the scan summary, one label per flagged scene, and which scenes stay ticked.

Plain functions with no Gradio in them, so they can be tested on their own. The HTML uses the classes styled in
theme.CSS.
"""
from __future__ import annotations

from scene_filter.core import Scene, fmt_ts


def _badge(suspicious: int, accurate: bool, double_check: bool) -> str:
    if not double_check:
        return ""
    if accurate:
        return '<span class="sf-badge">&#10003; Double-checked with the accurate detector</span>'
    return ('<span class="sf-badge sf-badge-quick">Double-checked with the quick detector: the accurate detector '
            "couldn't be downloaded. Check your internet and scan again.</span>")


def summary_html(n_scenes: int, total_s: float, duration_s: float, seconds: float, suspicious: int,
                 accurate: bool, double_check: bool, animated: bool) -> str:
    badge = _badge(suspicious, accurate, double_check)
    scanned = f"Scanned in {seconds:.0f}s."
    if n_scenes == 0:
        hint = "If you expected some, raise the sensitivity and scan again"
        hint += ', or untick "Animated movie".' if animated else "."
        return (f'<div class="sf-summary"><span class="sf-empty">No scenes flagged</span>{badge}'
                f'<span class="sf-meta">in {fmt_ts(duration_s)} of video. {scanned} {hint}</span></div>')
    noun = "scene flagged" if n_scenes == 1 else "scenes flagged"
    return (f'<div class="sf-summary"><span class="sf-count">{n_scenes} <small>{noun}</small></span>{badge}'
            f'<span class="sf-meta">{fmt_ts(total_s)} in total, out of {fmt_ts(duration_s)} of video. {scanned} '
            f"Untick any scene you want left alone. Times include a little padding before and after.</span></div>")


def scene_choices(scenes: list[Scene]) -> list[tuple[str, int]]:
    """One tick-box row per scene: its time range, what was detected, and how sure the detector was."""
    return [(f"{fmt_ts(s.start)} – {fmt_ts(s.end, round_up=True)} · {s.label_text()} · {s.peak_score:.0%}", s.index)
            for s in scenes]


def apply_picks(scenes: list[Scene], picked: list[int]) -> list[Scene]:
    """Keep the ticked scenes. Numbers that aren't one of these scenes (left over from another movie) are ignored."""
    chosen = {int(p) for p in picked or []}
    for s in scenes:
        s.include = s.index in chosen
    return scenes
