"""Command-line version, for scanning without the browser screen.

Examples:
  python cli.py "C:\\Movies\\movie.mkv"                  # timestamps only
  python cli.py movie.mp4 --filter cut                   # scan and cut flagged scenes
  python cli.py movie.mp4 --filter blur --mute --sensitivity 8
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from scene_filter import core


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Find nudity in a movie file and optionally filter it.")
    ap.add_argument("movie")
    ap.add_argument("--filter", choices=core.FILTER_MODES, default="none",
                    help="none = timestamps only (default), cut, blur or black")
    ap.add_argument("--mute", action="store_true", help="mute audio in flagged scenes (blur/black)")
    ap.add_argument("--quick", action="store_true", help="skip the close double-check of suspicious moments")
    ap.add_argument("--animated", action="store_true", help="animated movie: only confident, repeated matches")
    ap.add_argument("--sensitivity", type=int, default=5, choices=range(1, 11), metavar="1-10")
    ap.add_argument("--fps", type=float, default=2.0, help="frames checked per second")
    ap.add_argument("--padding", type=float, default=1.5)
    ap.add_argument("--merge-gap", type=float, default=3.0)
    ap.add_argument("--min-hits", type=int, default=2)
    ap.add_argument("--include", nargs="*", default=core.DEFAULT_CLASSES, choices=list(core.ALL_CLASSES))
    ap.add_argument("--out", default=None, help="output folder (default: output/ next to this script)")
    a = ap.parse_args(argv)

    out = Path(a.out or Path(__file__).resolve().parent / "output") / \
        f"{Path(a.movie).stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    last = [0.0]

    def progress(frac, msg):
        if frac - last[0] >= 0.02 or frac >= 1:
            last[0] = frac
            print(f"\r{frac:5.0%}  {msg}    ", end="", flush=True)

    report = core.scan(a.movie, out, double_check=not a.quick, sample_fps=a.fps, threshold=core.threshold_for(a.sensitivity, a.animated),
                                 classes=a.include, padding=a.padding, merge_gap=a.merge_gap,
                                 min_hits=max(a.min_hits, core.ANIMATED_MIN_HITS) if a.animated else a.min_hits,
                                 strong_single=core.ANIMATED_STRONG_SINGLE if a.animated else core.STRONG_SINGLE,
                                 progress=progress)
    scenes, duration = report.scenes, report.duration
    print()
    files = core.export_lists(scenes, a.movie, out)
    print(f"\n{len(scenes)} scene(s) flagged in {core.fmt_ts(duration)}:")
    for s in scenes:
        print(f"  Scene {s.index}: {core.fmt_ts(s.start)} to {core.fmt_ts(s.end, round_up=True)}  ({s.duration:.1f}s)  {s.label_text()}")
    print("\nLists saved:", *files.values(), sep="\n  ")
    if a.filter != "none" and scenes:
        dst = core.default_output_name(a.movie, a.filter, out)
        core.render(a.movie, dst, scenes, mode=a.filter, mute=a.mute, progress=progress)
        print(f"\n\nFiltered movie: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
