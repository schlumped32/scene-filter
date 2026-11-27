"""Runs Scene Filter with a stand-in detector, for the screen test in smoke.cjs.

    python tests/ui/fake_app.py

Every scan "finds" two scenes in a generated 60-second test video, in a few seconds, so the test can click
through scanning, unticking and saving without a real movie. Scan settings, saving and everything on screen are
the real app. Writes the test video's path and the app's address to <temp>/scene-filter-ui/.
"""
import os
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
WORK = Path(tempfile.gettempdir()) / "scene-filter-ui"
WORK.mkdir(exist_ok=True)
os.environ.setdefault("SCENE_FILTER_OUTPUT", str(WORK / "out"))
os.environ["SCENE_FILTER_URL_FILE"] = str(WORK / "url")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
(WORK / "url").unlink(missing_ok=True)

sys.path.insert(0, str(APP))
from scene_filter import core  # noqa: E402

video = WORK / "test.mp4"
if not video.exists():
    subprocess.run([core.find_tool("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=1280x720:rate=24:duration=60", "-f", "lavfi", "-i", "sine=d=60",
                    "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video)], check=True)
(WORK / "video").write_text(str(video))


def _hits():
    return ([core.Hit(t, 0.9, ["FEMALE_BREAST_EXPOSED"]) for t in (10, 11, 12)]
            + [core.Hit(t, 0.8, ["BUTTOCKS_EXPOSED"]) for t in (30, 31)])


def fake_detect(path, fps, threshold, classes, progress=None, keep=None, workers=None):
    if progress:
        progress(1.0, "Quick pass finished")
    return _hits()


def fake_refine(path, windows, threshold, classes=None, model_path=None, refine_fps=6.0, progress=None,
                keep_frames_for=None):
    hits = [h for h in _hits() if h.score >= threshold]
    if keep_frames_for is not None:
        for h in hits:
            keep_frames_for[h.t] = np.full((320, 320, 3), 128, np.uint8)
    return hits


core.detect_hits = fake_detect
core.refine_hits = fake_refine
core.ensure_accurate_model = lambda progress=None: Path("stand-in-accurate-model")

sys.argv = [str(APP / "app.py")]
runpy.run_path(str(APP / "app.py"), run_name="__main__")
