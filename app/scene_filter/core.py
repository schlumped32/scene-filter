"""Core engine: scan a video for nudity, merge hits into scenes, export lists, render a filtered copy.

Works only on video files you already have on disk. It does not read discs or remove copy protection.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np

# Labels the NudeNet model can output that mean actual exposure.
EXPLICIT_CLASSES = {
    "FEMALE_BREAST_EXPOSED": "Exposed breast",
    "FEMALE_GENITALIA_EXPOSED": "Exposed genitals (F)",
    "MALE_GENITALIA_EXPOSED": "Exposed genitals (M)",
    "BUTTOCKS_EXPOSED": "Exposed buttocks",
}
# Optional, off by default: shirtless men trip this constantly.
OPTIONAL_CLASSES = {
    "MALE_BREAST_EXPOSED": "Shirtless male chest",
    "BELLY_EXPOSED": "Exposed belly",
}
ALL_CLASSES = {**EXPLICIT_CLASSES, **OPTIONAL_CLASSES}
DEFAULT_CLASSES = list(EXPLICIT_CLASSES)

# Animated films fool the detector (it was trained on photos): Toy Story 2 scored up to 71% with no nudity.
# Animated mode only accepts confident, repeated matches.
ANIMATED_MIN_THRESHOLD = 0.75
ANIMATED_MIN_HITS = 2
# A scene normally needs min_hits flagged frames, but one frame this confident counts on its own,
# so a brief flash isn't missed. Animated mode raises it.
STRONG_SINGLE = 0.75
ANIMATED_STRONG_SINGLE = 0.90


def threshold_for(sensitivity: int, animated: bool = False) -> float:
    """Sensitivity 1..10 -> detector confidence cut-off 0.75 .. 0.30 (higher = flags more)."""
    t = round(0.80 - sensitivity * 0.05, 2)
    return max(t, ANIMATED_MIN_THRESHOLD) if animated else t


FRAME_BOX = 320  # frames are letterboxed into a 320x320 square: the detector's own input size

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = os.name == "nt"
# On Windows, stop every ffmpeg call from flashing up its own console window.
NO_WINDOW = {"creationflags": 0x08000000} if IS_WINDOWS else {}  # CREATE_NO_WINDOW
# Read ffmpeg's text output as UTF-8 everywhere (Windows would otherwise guess an older encoding and
# choke on accented file names).
TEXT = {"text": True, "encoding": "utf-8", "errors": "replace"}
# Use the Mac's video hardware to decode. ffmpeg quietly falls back to software if it can't.
HW_DECODE = ["-hwaccel", "videotoolbox"] if IS_MAC else []

FILTER_MODES = ("none", "cut", "blur", "black")

ProgressFn = Callable[[float, str], None]


# ---------------------------------------------------------------- utilities

def find_tool(name: str) -> Optional[str]:
    """Find ffmpeg/ffprobe on PATH; for ffmpeg, fall back to the copy bundled with imageio-ffmpeg.
    Returns None for ffprobe when it isn't installed (probe() then reads ffmpeg's own output)."""
    path = shutil.which(name)
    if path:
        return path
    if name == "ffmpeg":
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
        raise RuntimeError("ffmpeg was not found. Install ffmpeg (see README) and make sure it is on your PATH.")
    return None


def fmt_ts(seconds: float, millis: bool = False, round_up: bool = False) -> str:
    """Seconds -> HH:MM:SS (or HH:MM:SS.mmm). round_up=True rounds whole seconds up (used for scene ends,
    so the HH:MM:SS range shown always covers the whole filtered range)."""
    import math

    seconds = max(0.0, seconds)
    if round_up and not millis:
        seconds = math.ceil(seconds - 1e-6)
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}" if millis else f"{h:02d}:{m:02d}:{s:02d}"


def probe(path: str) -> dict:
    """Duration (s), fps and whether the file has audio."""
    ffprobe = find_tool("ffprobe")
    if ffprobe is None:
        return _probe_with_ffmpeg(path)
    out = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, **TEXT, **NO_WINDOW,
    )
    if out.returncode != 0:
        raise RuntimeError(f"Could not read the video: {out.stderr.strip()[:300]}")
    info = json.loads(out.stdout)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise RuntimeError("That file has no video stream.")
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    num, _, den = (video.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {
        "duration": duration,
        "fps": fps,
        "has_audio": audio is not None,
        "audio_codec": (audio or {}).get("codec_name", ""),
        "bitrate_kbps": int(info.get("format", {}).get("bit_rate") or 0) // 1000,
    }


def _probe_with_ffmpeg(path: str) -> dict:
    """Same as probe(), by reading the stream summary ffmpeg prints (used when ffprobe isn't available)."""
    import re

    if not Path(path).is_file():
        raise RuntimeError(f"Could not read the video: no file at {path}")
    err = subprocess.run([find_tool("ffmpeg"), "-hide_banner", "-i", path], capture_output=True,
                         **TEXT, **NO_WINDOW).stderr
    video = re.search(r"Stream #\S+.*?: Video: .*", err)
    if not video:
        raise RuntimeError(f"Could not read the video: {err.strip()[-300:]}")
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0
    f = re.search(r"([\d.]+) fps", video[0])
    audio = re.search(r"Stream #\S+.*?: Audio: (\w+)", err)
    b = re.search(r"Duration:.*?bitrate: (\d+) kb/s", err)
    return {"duration": duration, "fps": float(f[1]) if f else 0.0, "has_audio": audio is not None,
            "audio_codec": audio[1] if audio else "", "bitrate_kbps": int(b[1]) if b else 0}


# ---------------------------------------------------------------- scanning

@dataclass
class Hit:
    t: float
    score: float
    labels: list[str]


@dataclass
class Scene:
    index: int
    start: float          # filtered range start (includes padding)
    end: float            # filtered range end (includes padding)
    first_seen: float     # first sampled frame with a detection
    last_seen: float      # last sampled frame with a detection
    peak_score: float
    hits: int
    labels: list[str] = field(default_factory=list)
    thumbnail: Optional[str] = None
    include: bool = True

    @property
    def duration(self) -> float:
        return self.end - self.start

    def label_text(self) -> str:
        return ", ".join(ALL_CLASSES.get(l, l) for l in self.labels)


def make_detector(threads: int = 0, model_path: Optional[Path] = None, resolution: int = 320):
    """A NudeNet detector. threads=0 lets it use every core; scans run several 1-2 thread detectors side by side,
    which is faster than one detector using all cores (the model is small). model_path/resolution pick the
    accurate model (640m.onnx at 640) instead of the built-in quick one."""
    from nudenet import NudeDetector  # imported lazily: loading the model takes a second

    d = NudeDetector(model_path=str(model_path) if model_path else None, inference_resolution=resolution)
    if threads:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        d.onnx_session = ort.InferenceSession(d.onnx_session._model_path, opts, providers=["CPUExecutionProvider"])
    return d


_detector = None


def get_detector():
    global _detector
    if _detector is None:
        _detector = make_detector()
    return _detector


def scan_workers() -> tuple[int, int]:
    """(parallel workers, detector threads per worker) for this computer."""
    cores = os.cpu_count() or 2
    workers = max(1, min(6, cores // 2))
    return workers, max(1, cores // workers - 1)


def iter_frames(path: str, sample_fps: float, start: float = 0.0, length: Optional[float] = None,
                box: int = FRAME_BOX):
    """Yield (timestamp_seconds, bgr_frame) sampled at sample_fps, letterboxed to a box x box square.
    start/length scan just part of the movie (start should be a multiple of 1/sample_fps)."""
    vf = (
        f"fps={sample_fps},"
        f"scale={box}:{box}:force_original_aspect_ratio=decrease,"
        f"pad={box}:{box}:(ow-iw)/2:(oh-ih)/2"
    )
    seek = (["-ss", f"{start:.3f}"] if start else []) + (["-t", f"{length:.3f}"] if length else [])
    cmd = [find_tool("ffmpeg"), "-v", "error", *HW_DECODE, *seek, "-i", path, "-map", "0:v:0", "-an", "-sn",
           "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
    frame_bytes = box * box * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **NO_WINDOW)
    try:
        i = 0
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            frame = np.frombuffer(buf, np.uint8).reshape(box, box, 3)
            yield start + i / sample_fps, frame
            i += 1
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def detect_hits(
    path: str,
    sample_fps: float = 2.0,
    threshold: float = 0.45,
    classes: Optional[Iterable[str]] = None,
    progress: Optional[ProgressFn] = None,
    keep_frames_for: Optional[dict] = None,
    workers: Optional[int] = None,
) -> list[Hit]:
    """Run the detector over sampled frames and return the frames that matched.
    The movie is split into equal parts that are decoded and checked side by side."""
    classes = set(classes or DEFAULT_CLASSES)
    duration = probe(path)["duration"]
    expected = max(1, int(duration * sample_fps))
    n_workers, threads = scan_workers()
    if workers:
        n_workers = workers
    if duration <= 0:
        n_workers = 1  # unknown length: can't split it, scan it start to finish
    # Each part starts on the sampling grid so the timestamps match a single straight scan.
    step = 1.0 / sample_fps
    part = max(step, round(duration / n_workers / step) * step) if duration > 0 else None
    parts = [(i * part, part if i < n_workers - 1 else None) for i in range(n_workers)] if part else [(0.0, None)]

    hits: list[Hit] = []
    lock = threading.Lock()
    done = [0]
    errors: list[BaseException] = []

    def run(start, length):
        try:
            det = make_detector(threads) if n_workers > 1 else get_detector()
            for t, frame in iter_frames(path, sample_fps, start, length):
                if errors:
                    return
                found = [d for d in det.detect(frame) if d["class"] in classes and d["score"] >= threshold]
                with lock:
                    done[0] += 1
                    if found:
                        hits.append(Hit(t=t, score=max(d["score"] for d in found),
                                        labels=sorted({d["class"] for d in found})))
                        if keep_frames_for is not None:
                            keep_frames_for[t] = frame.copy()
        except BaseException as e:  # surfaced below, after the other parts stop
            errors.append(e)

    with ThreadPoolExecutor(len(parts)) as ex:
        futures = [ex.submit(run, a, b) for a, b in parts]
        while not all(f.done() for f in futures):
            time.sleep(0.5)
            if progress:
                progress(min(0.99, done[0] / expected),
                         f"Scanning: {fmt_ts(min(duration, done[0] / sample_fps))} of {fmt_ts(duration)} checked")
    if errors:
        raise errors[0]
    if progress:
        progress(1.0, "Scan finished")
    hits.sort(key=lambda h: h.t)
    return hits


# ---------------------------------------------------------------- accurate re-check (stage 2)

# NudeNet's larger, more accurate model. Downloaded once, on the first scan that needs it.
MODELS_DIR = Path(os.environ.get("SCENE_FILTER_MODELS") or Path.home() / ".scene-filter" / "models")
ACCURATE_MODEL = MODELS_DIR / "640m.onnx"
ACCURATE_URL = "https://github.com/notAI-tech/NudeNet/releases/download/v3.4-weights/640m.onnx"
ACCURATE_RESOLUTION = 640
REFINE_FPS = 6.0        # frames per second checked around each suspicious moment
REFINE_MARGIN = 1.0     # seconds checked before and after it
_download_failed = False
STAGE1_SLACK = 0.15     # the quick pass flags anything within this much of the threshold, so little slips past


def _model_loads(path: Path) -> bool:
    try:
        import onnxruntime as ort

        ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        return True
    except Exception:
        return False


def ensure_accurate_model(progress: Optional[ProgressFn] = None) -> Optional[Path]:
    """Return the accurate model's path, downloading it the first time. None if it can't be had
    (no internet, say); the re-check then uses the quick model instead."""
    global _download_failed
    if ACCURATE_MODEL.is_file():
        return ACCURATE_MODEL
    if _download_failed:
        return None  # already failed this session (offline?): don't make every scan wait on it again
    import ssl
    import urllib.error
    import urllib.request

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    part = ACCURATE_MODEL.with_suffix(".part")
    try:
        # Try the bundled certificate list first (the bundled Python can't always see the system's, on macOS
        # especially), then the computer's own (needed behind some company or school networks).
        contexts = []
        try:
            import certifi

            contexts.append(ssl.create_default_context(cafile=certifi.where()))
        except ImportError:
            pass
        contexts.append(ssl.create_default_context())
        for i, ctx in enumerate(contexts):
            try:
                r = urllib.request.urlopen(ACCURATE_URL, timeout=30, context=ctx)
                break
            except urllib.error.URLError as e:
                if i == len(contexts) - 1 or not isinstance(e.reason, ssl.SSLError):
                    raise
        with r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                got += len(chunk)
                if progress and total:
                    progress(got / total * 0.99, f"Downloading the accurate detector (one time): "
                                                 f"{got >> 20} of {total >> 20} MB")
        if not _model_loads(part):
            raise RuntimeError("downloaded model file is damaged")
        part.replace(ACCURATE_MODEL)
        return ACCURATE_MODEL
    except Exception as e:
        _download_failed = True
        print(f"Accurate detector unavailable, using the quick one for the re-check: {e}", flush=True)
        part.unlink(missing_ok=True)
        return None


def suspicious_windows(hits: list[Hit], duration: float, margin: float = REFINE_MARGIN) -> list[tuple[float, float]]:
    """Time ranges around the quick pass's hits (joined when they nearly touch) to look at closely."""
    out: list[list[float]] = []
    for h in sorted(hits, key=lambda h: h.t):
        a, b = max(0.0, h.t - margin), h.t + margin
        if duration:
            b = min(duration, b)
        if out and a <= out[-1][1] + 0.5:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out if b > a]


def refine_hits(
    path: str,
    windows: list[tuple[float, float]],
    threshold: float,
    classes: Optional[Iterable[str]] = None,
    model_path: Optional[Path] = None,
    refine_fps: float = REFINE_FPS,
    progress: Optional[ProgressFn] = None,
    keep_frames_for: Optional[dict] = None,
) -> list[Hit]:
    """Stage 2: look at each window closely (refine_fps frames a second) with the accurate model if we have it,
    otherwise the quick one. Only these hits decide the final scenes."""
    classes = set(classes or DEFAULT_CLASSES)
    box = ACCURATE_RESOLUTION if model_path else FRAME_BOX
    expected = max(1, int(sum(b - a for a, b in windows) * refine_fps))
    n_workers, threads = scan_workers()
    n_workers = max(1, min(n_workers, len(windows)))
    todo = list(windows)
    hits: list[Hit] = []
    lock = threading.Lock()
    done = [0]
    errors: list[BaseException] = []

    def run():
        try:
            det = make_detector(threads, model_path, box)
            while True:
                with lock:
                    if not todo or errors:
                        return
                    a, b = todo.pop(0)
                for t, frame in iter_frames(path, refine_fps, a, b - a, box=box):
                    found = [d for d in det.detect(frame) if d["class"] in classes and d["score"] >= threshold]
                    with lock:
                        done[0] += 1
                        if found:
                            hits.append(Hit(t=t, score=max(d["score"] for d in found),
                                            labels=sorted({d["class"] for d in found})))
                            if keep_frames_for is not None:
                                import cv2

                                keep_frames_for[t] = cv2.resize(frame, (FRAME_BOX, FRAME_BOX),
                                                                interpolation=cv2.INTER_AREA)
        except BaseException as e:
            errors.append(e)

    if windows:
        with ThreadPoolExecutor(n_workers) as ex:
            futures = [ex.submit(run) for _ in range(n_workers)]
            while not all(f.done() for f in futures):
                time.sleep(0.5)
                if progress:
                    progress(min(0.99, done[0] / expected),
                             f"Double-checking {len(windows)} suspicious moment(s)"
                             + (" with the accurate detector" if model_path else ""))
    if errors:
        raise errors[0]
    if progress:
        progress(1.0, "Double-check finished")
    hits.sort(key=lambda h: h.t)
    return hits


def merge_hits(
    hits: list[Hit],
    duration: float,
    padding: float = 1.5,
    merge_gap: float = 3.0,
    min_hits: int = 1,
    strong_single: float = STRONG_SINGLE,
) -> list[Scene]:
    """Group hits closer than merge_gap into scenes, pad both ends. A group is kept if it has at least
    min_hits frames, or any one frame scored strong_single or higher."""
    groups: list[list[Hit]] = []
    for h in sorted(hits, key=lambda h: h.t):
        if groups and h.t - groups[-1][-1].t <= merge_gap:
            groups[-1].append(h)
        else:
            groups.append([h])
    groups = [g for g in groups if len(g) >= min_hits or max(h.score for h in g) >= strong_single]

    scenes: list[Scene] = []
    for g in groups:
        start = max(0.0, g[0].t - padding)
        end = min(duration, g[-1].t + padding) if duration else g[-1].t + padding
        labels = sorted({l for h in g for l in h.labels})
        peak = max(h.score for h in g)
        if scenes and start - scenes[-1].end < 1.0:  # under a second of clean video between them: join
            s = scenes[-1]
            s.end = max(s.end, end)
            s.last_seen = g[-1].t
            s.peak_score = max(s.peak_score, peak)
            s.hits += len(g)
            s.labels = sorted(set(s.labels) | set(labels))
        else:
            scenes.append(Scene(index=0, start=start, end=end, first_seen=g[0].t, last_seen=g[-1].t,
                                peak_score=peak, hits=len(g), labels=labels))
    for i, s in enumerate(scenes, 1):
        s.index = i
    return scenes


def save_thumbnails(scenes: list[Scene], frames: dict, hits: list[Hit], out_dir: Path, blur: bool = True):
    """Save one thumbnail per scene (the strongest frame), blurred unless blur=False."""
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    for s in scenes:
        inside = [h for h in hits if s.start <= h.t <= s.end and h.t in frames]
        if not inside:
            continue
        best = max(inside, key=lambda h: h.score)
        img = frames[best.t]
        if blur:
            small = cv2.resize(img, (16, 16), interpolation=cv2.INTER_AREA)
            img = cv2.resize(small, (320, 320), interpolation=cv2.INTER_NEAREST)
        path = out_dir / f"scene_{s.index:03d}.jpg"
        # imencode + write_bytes instead of imwrite: imwrite fails on Windows if the folder name has
        # non-English letters in it (for example a user name like "José").
        ok, jpg = cv2.imencode(".jpg", cv2.resize(img, (320, 320)))
        if ok:
            path.write_bytes(jpg.tobytes())
        s.thumbnail = str(path)


@dataclass
class ScanReport:
    scenes: list[Scene]
    duration: float
    suspicious: int = 0          # moments the quick pass sent for a closer look
    accurate_model: bool = False  # True if the closer look used the accurate model


def scan(
    path: str,
    out_dir: str | Path,
    sample_fps: float = 2.0,
    threshold: float = 0.45,
    classes: Optional[Iterable[str]] = None,
    padding: float = 1.5,
    merge_gap: float = 3.0,
    min_hits: int = 1,
    strong_single: float = STRONG_SINGLE,
    thumbnails: bool = True,
    blur_thumbnails: bool = True,
    progress: Optional[ProgressFn] = None,
    double_check: bool = True,
) -> ScanReport:
    """Full scan. With double_check (the default) it runs in two stages:
      1. a quick pass over the whole movie, loose enough that little slips past;
      2. a close look (6 frames a second, accurate model) at just the suspicious moments, which decides.
    Without double_check it is the single quick pass."""
    info = probe(path)
    duration = info["duration"]
    frames: dict = {} if thumbnails else None

    def part(lo, hi):  # map a stage's 0..1 progress onto lo..hi of the whole bar
        return (lambda f, m: progress(lo + (hi - lo) * f, m)) if progress else None

    if not double_check:
        hits = detect_hits(path, sample_fps, threshold, classes, progress, frames)
        scenes = merge_hits(hits, duration, padding, merge_gap, min_hits, strong_single)
        report = ScanReport(scenes, duration)
    else:
        model = ensure_accurate_model(part(0.0, 0.05))
        quick = detect_hits(path, sample_fps, max(0.25, threshold - STAGE1_SLACK), classes, part(0.05, 0.75))
        windows = suspicious_windows(quick, duration)
        hits = refine_hits(path, windows, threshold, classes, model, REFINE_FPS, part(0.75, 1.0), frames)
        # min_hits counts frames at the normal sampling rate; scale it to the closer look's rate,
        # so "2 frames" still means "about a second of footage".
        needed = max(1, round(min_hits * REFINE_FPS / sample_fps))
        scenes = merge_hits(hits, duration, padding, merge_gap, needed, strong_single)
        report = ScanReport(scenes, duration, len(windows), model is not None)
    if thumbnails:
        save_thumbnails(scenes, frames, hits, Path(out_dir) / "thumbnails", blur_thumbnails)
    return report


# ---------------------------------------------------------------- exports

def export_lists(scenes: list[Scene], movie_path: str, out_dir: str | Path) -> dict[str, str]:
    """Write CSV, JSON, a plain-text list and a Kodi .edl skip file. Only scenes with include=True."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(movie_path).stem
    kept = [s for s in scenes if s.include]
    files = {}

    p = out_dir / f"{stem}_scenes.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scene", "start", "end", "duration_s", "first_detected", "last_detected",
                    "start_seconds", "end_seconds", "detected", "peak_confidence"])
        for s in kept:
            w.writerow([s.index, fmt_ts(s.start, True), fmt_ts(s.end, True), round(s.duration, 1),
                        fmt_ts(s.first_seen, True), fmt_ts(s.last_seen, True),
                        round(s.start, 3), round(s.end, 3), s.label_text(), round(s.peak_score, 2)])
    files["csv"] = str(p)

    p = out_dir / f"{stem}_scenes.json"
    data = [{**{k: v for k, v in asdict(s).items() if k != "thumbnail"},
             "start_ts": fmt_ts(s.start, True), "end_ts": fmt_ts(s.end, True)} for s in kept]
    p.write_text(json.dumps({"movie": Path(movie_path).name, "scenes": data}, indent=2), encoding="utf-8")
    files["json"] = str(p)

    p = out_dir / f"{stem}_scenes.txt"
    lines = [f"Flagged scenes in {Path(movie_path).name}", ""]
    lines += [f"Scene {s.index}: {fmt_ts(s.start)} to {fmt_ts(s.end, round_up=True)} ({s.duration:.1f}s) - {s.label_text()}"
              for s in kept] or ["No scenes flagged."]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    files["txt"] = str(p)

    # Kodi skip file: put it next to the movie with the same name and Kodi skips these ranges on playback.
    p = out_dir / f"{stem}.edl"
    p.write_text("".join(f"{s.start:.3f}\t{s.end:.3f}\t0\n" for s in kept), encoding="utf-8")
    files["edl"] = str(p)
    return files


# ---------------------------------------------------------------- rendering

def _expr(ranges: list[tuple[float, float]]) -> str:
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in ranges)


# Audio formats an .mp4 can hold as-is, so they can be copied instead of re-encoded.
MP4_AUDIO = {"aac", "ac3", "eac3", "mp3", "alac"}
# Video encoders to try in order. The Mac's hardware encoder is several times faster than libx264.
# Windows: NVIDIA, Intel and AMD hardware encoders; a PC without that hardware fails in under a second
# and moves on, ending with libx264, which works everywhere.
if IS_MAC:
    ENCODERS = ["h264_videotoolbox", "libx264"]
elif IS_WINDOWS:
    ENCODERS = ["h264_nvenc", "h264_qsv", "h264_amf", "libx264"]
else:
    ENCODERS = ["libx264"]


def _video_codec_args(encoder: str, info: dict) -> list[str]:
    # Hardware encoders: match the source's bitrate (within sensible limits) to keep quality.
    kbps = min(max(info.get("bitrate_kbps") or 8000, 5000), 30000)
    rate = ["-b:v", f"{kbps}k", "-maxrate", f"{kbps * 2}k", "-bufsize", f"{kbps * 2}k"]
    if encoder == "h264_videotoolbox":
        return ["-c:v", encoder, *rate, "-allow_sw", "1", "-pix_fmt", "yuv420p"]
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p5", "-rc", "vbr", *rate, "-pix_fmt", "yuv420p"]
    if encoder == "h264_qsv":
        return ["-c:v", encoder, "-preset", "medium", *rate, "-pix_fmt", "nv12"]
    if encoder == "h264_amf":
        return ["-c:v", encoder, "-quality", "balanced", *rate, "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


def build_ffmpeg_cmd(src: str, dst: str, ranges: list[tuple[float, float]], mode: str,
                     mute: bool, info: dict, encoder: str = "libx264") -> list[str]:
    if mode not in ("cut", "blur", "black"):
        raise ValueError(f"Unknown filter mode: {mode}")
    has_audio = info["has_audio"]
    e = _expr(ranges)
    if mode == "cut":
        # Shift each kept frame back by the total length cut before it. Works for variable frame rate
        # video too (N/FRAME_RATE assumes a constant rate and desyncs audio on phone/web recordings).
        shift = "+".join(f"gte(T,{b:.3f})*{b - a:.3f}" for a, b in ranges)
        vf = f"select='not({e})',setpts='PTS-({shift})/TB'"
        af = f"aselect='not({e})',asetpts='PTS-({shift})/TB'"
    else:
        # Blur strength scales with the picture size, so a 4K movie is blurred as heavily as a 720p one.
        vf = (f"boxblur=luma_radius='min(w,h)/12':luma_power=3:"
              f"chroma_radius='min(cw,ch)/12':chroma_power=3:enable='{e}'" if mode == "blur"
              else f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='{e}'")
        af = f"volume=0:enable='{e}'" if mute else None
    hw = HW_DECODE if encoder == "h264_videotoolbox" else []
    cmd = [find_tool("ffmpeg"), "-y", "-v", "error", "-progress", "pipe:1", "-nostats", *hw,
           "-i", src, "-map", "0:v:0"]
    if has_audio:
        cmd += ["-map", "0:a:0"]
    cmd += ["-vf", vf, *_video_codec_args(encoder, info)]
    if has_audio:
        if af:
            cmd += ["-af", af, "-c:a", "aac", "-b:a", "192k"]
        elif info.get("audio_codec") in MP4_AUDIO:
            cmd += ["-c:a", "copy"]  # audio untouched: copy it (faster, and no quality loss)
        else:
            cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += ["-movflags", "+faststart", dst]
    return cmd


def _run_ffmpeg(cmd: list[str], total: float, progress: Optional[ProgressFn], label: str) -> tuple[int, str]:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **TEXT, **NO_WINDOW)
    err_lines: list[str] = []
    t = threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True)
    t.start()  # read errors alongside progress so a chatty ffmpeg can't stall
    for line in proc.stdout:
        if line.startswith("out_time_us=") and progress and total > 0:
            try:
                done = int(line.split("=", 1)[1]) / 1e6
                progress(min(0.99, done / total), f"{label} {fmt_ts(done)} of {fmt_ts(total)}")
            except ValueError:
                pass
    code = proc.wait()
    t.join()
    return code, "".join(err_lines)


def render(src: str, dst: str, scenes: list[Scene], mode: str = "cut", mute: bool = False,
           progress: Optional[ProgressFn] = None, encoders: Optional[list[str]] = None) -> str:
    """Write a filtered copy. mode: cut | blur | black. Returns dst.
    Tries the fastest encoder first and falls back to the next one if it fails."""
    ranges = [(s.start, s.end) for s in scenes if s.include]
    info = probe(src)
    if not ranges:
        raise ValueError("No scenes are selected, so there is nothing to filter.")
    total = info["duration"]
    if mode == "cut":
        total -= sum(b - a for a, b in ranges)
    err = ""
    for i, encoder in enumerate(encoders or ENCODERS):
        cmd = build_ffmpeg_cmd(src, dst, ranges, mode, mute, info, encoder)
        label = "Writing (slower method)" if encoder == "libx264" and i > 0 else "Writing"
        code, err = _run_ffmpeg(cmd, total, progress, label)
        if code == 0:
            if progress:
                progress(1.0, "Done")
            return dst
        print(f"ffmpeg with {encoder} failed, trying the next option: {err.strip()[-300:]}", flush=True)
    raise RuntimeError(f"ffmpeg failed: {err.strip()[-500:]}")


def default_output_name(src: str, mode: str, out_dir: str | Path) -> str:
    return str(Path(out_dir) / f"{Path(src).stem}_filtered_{mode}.mp4")
