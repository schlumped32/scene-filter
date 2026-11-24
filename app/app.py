"""Scene Filter: a local app that finds nudity in a movie file you own and makes a filtered copy.

Run:  python app.py      (opens http://127.0.0.1:7860 in your browser; nothing leaves your computer)
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import gradio as gr
import pandas as pd

from scene_filter import core

APP_DIR = Path(__file__).resolve().parent
try:
    APP_VERSION = (APP_DIR / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    APP_VERSION = "?"
OUTPUT_DIR = Path(os.environ.get("SCENE_FILTER_OUTPUT", APP_DIR / "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_TYPES = ["video", ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts"]
MODE_LABELS = {
    "Timestamps only (no filter)": "none",
    "Cut the scenes out": "cut",
    "Blur the whole screen": "blur",
    "Black screen": "black",
}
CLASS_CHOICES = [(label, key) for key, label in core.ALL_CLASSES.items()]
TABLE_COLS = ["Filter?", "Scene", "Start", "End", "Length", "Detected", "Confidence"]


IS_MAC = sys.platform == "darwin"
IS_WINDOWS = os.name == "nt"
CAN_PICK = IS_MAC or IS_WINDOWS
MOVIE_PATTERNS = ";".join(f"*{t}" for t in VIDEO_TYPES if t.startswith("."))

# Windows file picker: a standard Open dialog shown by PowerShell (built into Windows), kept on top of the browser.
WIN_PICKER = (
    "Add-Type -AssemblyName System.Windows.Forms;"
    "$o = New-Object System.Windows.Forms.Form -Property @{TopMost=$true; ShowInTaskbar=$false};"
    "$d = New-Object System.Windows.Forms.OpenFileDialog;"
    "$d.Title = 'Pick a movie for Scene Filter';"
    f"$d.Filter = 'Movies|{MOVIE_PATTERNS}|All files|*.*';"
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;"
    "if ($d.ShowDialog($o) -eq 'OK') {{ $d.FileName }}"
).replace("{{", "{").replace("}}", "}")


def pick_movie(current):  # returns (path, cleared drop zone)
    """Open the computer's own file picker so big movies aren't copied through the browser."""
    if IS_WINDOWS:
        out = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", WIN_PICKER], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", creationflags=0x08000000)
    else:
        script = ('tell me to activate\n'
                  'POSIX path of (choose file with prompt "Pick a movie for Scene Filter" of type {"public.movie", "mkv", "webm"})')
        out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    path = out.stdout.strip()
    return (path, None) if path else (current, gr.update())


def show_output(state):
    folder = state["run_dir"] if state else str(OUTPUT_DIR)
    if IS_MAC:
        subprocess.run(["open", folder])
    elif os.name == "nt":
        os.startfile(folder)  # type: ignore[attr-defined]
    return f"Output folder: `{folder}`"


def _movie_path(upload, typed: str) -> str:
    path = (typed or "").strip().strip('"').strip("'")
    if not path and upload:
        path = upload if isinstance(upload, str) else getattr(upload, "name", "")
    if not path:
        raise gr.Error("Pick a movie file, or paste the full path to one.")
    if not Path(path).is_file():
        raise gr.Error(f"Can't find a file at: {path}")
    return path


def _table(scenes):
    return pd.DataFrame(
        [[s.include, s.index, core.fmt_ts(s.start), core.fmt_ts(s.end, round_up=True), f"{s.duration:.1f}s",
          s.label_text(), f"{s.peak_score:.0%}"] for s in scenes],
        columns=TABLE_COLS,
    )


def _apply_table(scenes, table):
    """Copy the Filter? checkboxes from the on-screen table back onto the scenes."""
    if table is None or len(scenes) == 0:
        return scenes
    df = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table, columns=TABLE_COLS)
    picks = {}
    for _, row in df.iterrows():
        try:
            picks[int(row["Scene"])] = str(row["Filter?"]).lower() in ("true", "1", "yes")
        except (ValueError, TypeError):
            continue
    for s in scenes:
        s.include = picks.get(s.index, s.include)
    return scenes


def do_scan(upload, typed, animated, sensitivity, classes, sample_fps, padding, merge_gap, min_hits, clear_previews,
            double_check, progress=gr.Progress()):
    path = _movie_path(upload, typed)
    if not classes:
        raise gr.Error("Tick at least one thing to look for.")
    run_dir = OUTPUT_DIR / f"{Path(path).stem}_{time.strftime('%Y%m%d-%H%M%S')}"
    threshold = core.threshold_for(int(sensitivity), animated)
    if animated:
        min_hits = max(int(min_hits), core.ANIMATED_MIN_HITS)
    t0 = time.time()
    report = core.scan(
        path, run_dir, double_check=double_check, sample_fps=sample_fps, threshold=threshold, classes=classes, padding=padding,
        merge_gap=merge_gap, min_hits=int(min_hits), blur_thumbnails=not clear_previews,
        strong_single=core.ANIMATED_STRONG_SINGLE if animated else core.STRONG_SINGLE,
        progress=lambda f, msg: progress(f, desc=msg),
    )
    scenes, duration = report.scenes, report.duration
    files = core.export_lists(scenes, path, run_dir)
    total = sum(s.duration for s in scenes)
    if not double_check:
        checked = ""
    elif report.accurate_model:
        checked = f" {report.suspicious} suspicious moment(s) were double-checked with the accurate detector."
    else:
        checked = (f" {report.suspicious} suspicious moment(s) were double-checked, but the accurate detector "
                   "couldn't be downloaded, so the quick one was used. Check your internet and scan again.")
    summary = (
        f"**{len(scenes)} scene(s) flagged** in {core.fmt_ts(duration)} of video, "
        f"{core.fmt_ts(total)} in total. Scanned in {time.time() - t0:.0f}s.{checked}\n\n"
        "Untick any scene you don't want filtered, then pick a filter option below. "
        "Times include the padding before and after each scene."
        if scenes else
        f"**No scenes flagged** in {core.fmt_ts(duration)} of video.{checked} "
        "If you expected some, raise the sensitivity and scan again"
        + (" (or untick \"Animated movie\")." if animated else ".")
    )
    gallery = [(s.thumbnail, f"Scene {s.index}: {core.fmt_ts(s.start)} to {core.fmt_ts(s.end, round_up=True)}")
               for s in scenes if s.thumbnail]
    state = {"path": path, "run_dir": str(run_dir), "scenes": scenes}
    return state, summary, _table(scenes), gallery, list(files.values())


def do_export(state, table, mode_label, mute, progress=gr.Progress()):
    if not state:
        raise gr.Error("Scan a movie first.")
    scenes = _apply_table(state["scenes"], table)
    files = core.export_lists(scenes, state["path"], state["run_dir"])
    mode = MODE_LABELS[mode_label]
    chosen = [s for s in scenes if s.include]
    if mode == "none":
        return list(files.values()), (
            f"Saved the timestamp list for {len(chosen)} scene(s). No video was changed.\n\n"
            f"Files are in `{state['run_dir']}`. Tip: put the `.edl` file next to the movie with the "
            "same name and Kodi will skip those scenes during playback.")
    if not chosen:
        raise gr.Error("No scenes are ticked, so there is nothing to filter.")
    dst = core.default_output_name(state["path"], mode, state["run_dir"])
    core.render(state["path"], dst, scenes, mode=mode, mute=mute,
                progress=lambda f, msg: progress(f, desc=msg))
    # The movie itself isn't handed to the browser: copying a multi-GB file there is slow. It's on disk.
    return list(files.values()), (
        f"Done. {len(chosen)} scene(s) filtered ({mode_label.lower()}).\n\nSaved to `{dst}`")


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Scene Filter") as ui:
        state = gr.State(None)
        gr.Markdown(
            f"# Scene Filter <small style='font-size:0.45em;opacity:0.6'>version {APP_VERSION}</small>\n"
            "Load a movie file you own. It finds scenes with nudity, shows you exactly when "
            "they are, and can make a filtered copy. Everything runs on this computer."
        )
        upload = gr.File(label="Drag and drop a movie here (or click to browse)", file_types=VIDEO_TYPES,
                         type="filepath", height=200)
        with gr.Row(equal_height=True):
            typed = gr.Textbox(label="...or choose a movie without copying it (best for big files)" if CAN_PICK
                               else "...or paste the movie's full path (best for big files)",
                               placeholder="/Users/you/Movies/movie.mp4  or  C:\\Movies\\movie.mkv", scale=4)
            pick_btn = gr.Button("Choose movie...", visible=CAN_PICK, scale=1)
        animated = gr.Checkbox(False, label="Animated movie (cartoons fool the detector: this only flags confident, repeated matches)")
        with gr.Accordion("Detection settings", open=False):
            sensitivity = gr.Slider(1, 10, value=5, step=1, label="Sensitivity (higher flags more, with more false alarms)")
            classes = gr.CheckboxGroup(CLASS_CHOICES, value=core.DEFAULT_CLASSES, label="Look for")
            with gr.Row():
                sample_fps = gr.Slider(0.5, 5, value=2, step=0.5, label="Frames checked per second")
                padding = gr.Slider(0, 5, value=1.5, step=0.5, label="Padding before/after each scene (s)")
                merge_gap = gr.Slider(0, 10, value=3, step=0.5, label="Join hits closer than (s)")
                min_hits = gr.Slider(1, 5, value=2, step=1, label="Min. flagged frames per scene")
            double_check = gr.Checkbox(True, label="Double-check suspicious moments closely with the accurate "
                                                   "detector (recommended; a little slower)")
            clear_previews = gr.Checkbox(False, label="Show unblurred preview images")
        scan_btn = gr.Button("Scan movie", variant="primary")

        summary = gr.Markdown()
        table = gr.Dataframe(headers=TABLE_COLS, datatype=["bool", "number", "str", "str", "str", "str", "str"],
                             interactive=True, label="Flagged scenes (untick to leave a scene alone)", wrap=True)
        gallery = gr.Gallery(label="Previews (blurred)", columns=6, height="auto")

        gr.Markdown("### Filter option")
        with gr.Row():
            mode = gr.Radio(list(MODE_LABELS), value="Cut the scenes out", label="What to do with ticked scenes")
            mute = gr.Checkbox(False, label="Also mute audio (blur / black screen only)")
        with gr.Row():
            export_btn = gr.Button("Save", variant="primary")
            folder_btn = gr.Button("Open output folder", visible=IS_MAC or os.name == "nt")
        result = gr.Markdown()
        files = gr.File(label="Timestamp lists (CSV, JSON, text, Kodi skip file)", file_count="multiple")

        scan_btn.click(do_scan, [upload, typed, animated, sensitivity, classes, sample_fps, padding, merge_gap, min_hits,
                                 clear_previews, double_check], [state, summary, table, gallery, files])
        pick_btn.click(pick_movie, [typed], [typed, upload])
        upload.upload(lambda: "", None, typed)  # a dropped movie replaces a chosen one
        folder_btn.click(show_output, [state], [result])
        export_btn.click(do_export, [state, table, mode, mute], [files, result])
    return ui


if __name__ == "__main__":
    os.chdir(OUTPUT_DIR)  # a stable working folder, whatever folder the app was started from
    ui = build_ui().queue()
    _, url, _ = ui.launch(server_name="127.0.0.1", inbrowser=True, allowed_paths=[str(OUTPUT_DIR)],
                          prevent_thread_lock=True)
    url_file = os.environ.get("SCENE_FILTER_URL_FILE")  # set by the Mac app so it can reopen the page
    if url_file:
        Path(url_file).write_text(url)
    ui.block_thread()
