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

import review
import theme
from scene_list import SceneList
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
    "Cut out": "cut",
    "Blur": "blur",
    "Black screen": "black",
    "Times only": "none",
}
CLASS_CHOICES = [(label, key) for key, label in core.ALL_CLASSES.items()]


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
        merge_gap=merge_gap, min_hits=int(min_hits),
        strong_single=core.ANIMATED_STRONG_SINGLE if animated else core.STRONG_SINGLE,
        progress=lambda f, msg: progress(f, desc=msg),
    )
    scenes, duration = report.scenes, report.duration
    files = core.export_lists(scenes, path, run_dir)
    summary = review.summary_html(len(scenes), sum(s.duration for s in scenes), duration, time.time() - t0,
                                  report.suspicious, report.accurate_model, double_check, animated)
    # A fresh list every scan, all ticked, so ticks from a previous movie never carry over.
    picks = SceneList(review.scene_rows(scenes), value=[s.index for s in scenes], label=SCENES_LABEL,
                      visible=bool(scenes), elem_classes="sf-scenes", padding=False)
    gallery = [(s.thumbnail, f"Scene {s.index}: {core.fmt_ts(s.start)} to {core.fmt_ts(s.end, round_up=True)}")
               for s in scenes if s.thumbnail]
    state = {"path": path, "run_dir": str(run_dir), "scenes": scenes}
    # The result line is cleared so the last save message can't be mistaken for this movie's.
    return state, summary, picks, gr.Gallery(value=gallery, visible=bool(gallery)), list(files.values()), ""


def do_export(state, picked, mode_label, mute, progress=gr.Progress()):
    if not state:
        raise gr.Error("Scan a movie first.")
    scenes = review.apply_picks(state["scenes"], picked)
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


SCENES_LABEL = "Flagged scenes: ticked ones get filtered"

HEADER = f"""<div class="sf-header">
  <div class="sf-brand"><span class="sf-mark"><svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M3 4h10M3 8h10M3 12h6" stroke-width="2" stroke-linecap="round"/></svg></span>Scene Filter</div>
  <span class="sf-pill">Version {APP_VERSION}</span>
</div>
<p class="sf-tagline">Finds nudity in a movie you own, shows you exactly when it happens, and can make a filtered
copy. Everything stays on this computer.</p>"""


def _step(text: str) -> None:
    gr.HTML(f'<div class="sf-step">{text}</div>', padding=False)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Scene Filter") as ui:
        state = gr.State(None)
        gr.HTML(HEADER, padding=False)

        with gr.Column(elem_classes="sf-card"):
            _step("Movie")
            upload = gr.File(label="Drop a movie here, or click to browse", file_types=VIDEO_TYPES,
                             type="filepath", height=150, elem_classes="sf-drop")
            with gr.Row(equal_height=True):
                typed = gr.Textbox(label="...or choose one without copying it (best for big files)" if CAN_PICK
                                   else "...or paste the movie's full path (best for big files)",
                                   placeholder="/Users/you/Movies/movie.mp4  or  C:\\Movies\\movie.mkv", scale=4)
                pick_btn = gr.Button("Choose movie...", visible=CAN_PICK, scale=1)
            animated = gr.Checkbox(False, label="Animated movie",
                                   info="Cartoons can fool the detector. This only flags confident, repeated matches.")
            with gr.Accordion("Detection settings", open=False):
                sensitivity = gr.Slider(1, 10, value=5, step=1, label="Sensitivity",
                                        info="Higher flags more, with more false alarms.")
                classes = gr.CheckboxGroup(CLASS_CHOICES, value=core.DEFAULT_CLASSES, label="Look for")
                with gr.Row():
                    sample_fps = gr.Slider(0.5, 5, value=2, step=0.5, label="Frames checked per second")
                    padding = gr.Slider(0, 5, value=1.5, step=0.5, label="Extra seconds before and after each scene")
                    merge_gap = gr.Slider(0, 10, value=3, step=0.5, label="Join scenes closer than (seconds)")
                    min_hits = gr.Slider(1, 5, value=2, step=1, label="Frames a scene needs to count")
                double_check = gr.Checkbox(True, label="Double-check suspicious moments with the accurate detector",
                                           info="Recommended. A little slower.")
                clear_previews = gr.Checkbox(False, label="Show unblurred preview images")
            scan_btn = gr.Button("Scan movie", variant="primary", size="lg")

        with gr.Column(elem_classes="sf-card"):
            _step("Review")
            summary = gr.HTML('<div class="sf-summary"><span class="sf-meta">Scan a movie to see what it '
                              "finds here.</span></div>", padding=False)
            picks = SceneList(label=SCENES_LABEL, visible=False, elem_classes="sf-scenes", padding=False)
            gallery = gr.Gallery(label="Previews", columns=4, height=210, object_fit="cover", visible=False,
                                 elem_classes="sf-boxed")

        with gr.Column(elem_classes="sf-card"):
            _step("Save")
            mode = gr.Radio(list(MODE_LABELS), value="Cut out", label="What to do with ticked scenes",
                            elem_classes="sf-modes")
            mute = gr.Checkbox(False, label="Also mute the sound (Blur and Black screen only)")
            with gr.Row():
                export_btn = gr.Button("Save filtered movie", variant="primary", size="lg", scale=3)
                folder_btn = gr.Button("Open output folder", visible=IS_MAC or os.name == "nt", scale=2)
            result = gr.Markdown()
            files = gr.File(label="Timestamp lists (CSV, JSON, text, Kodi skip file)", file_count="multiple",
                            elem_classes="sf-boxed")

        scan_btn.click(do_scan, [upload, typed, animated, sensitivity, classes, sample_fps, padding, merge_gap, min_hits,
                                 clear_previews, double_check], [state, summary, picks, gallery, files, result])
        pick_btn.click(pick_movie, [typed], [typed, upload])
        upload.upload(lambda: "", None, typed)  # a dropped movie replaces a chosen one
        folder_btn.click(show_output, [state], [result])
        export_btn.click(do_export, [state, picks, mode, mute], [files, result])
    return ui


# Gradio 6 takes the look at launch time.
STYLE = {"theme": theme.make_theme(), "css": theme.CSS, "head": theme.HEAD}


if __name__ == "__main__":
    os.chdir(OUTPUT_DIR)  # a stable working folder, whatever folder the app was started from
    ui = build_ui().queue()
    _, url, _ = ui.launch(server_name="127.0.0.1", inbrowser=True, allowed_paths=[str(OUTPUT_DIR)],
                          prevent_thread_lock=True, **STYLE)
    url_file = os.environ.get("SCENE_FILTER_URL_FILE")  # set by the Mac app so it can reopen the page
    if url_file:
        Path(url_file).write_text(url)
    ui.block_thread()
