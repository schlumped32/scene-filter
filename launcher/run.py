"""Scene Filter starter: keeps the app up to date, then runs it.

This file ships inside the Mac app and the Windows folder and is meant to change rarely. The app itself
(app.py, scene_filter/, ...) is what gets updated. On every launch this:

  1. checks the update address for a newer version (gives up after a few seconds if offline),
  2. downloads it, checks its fingerprint (SHA-256), and unpacks it next to the older versions,
  3. installs any new packages that version needs,
  4. starts the newest version that isn't marked bad,
  5. if a new version fails to start, marks it bad and starts the previous one instead.

Only the Python standard library is used here, so this file works even if an update breaks a package.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import signal
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent              # the version that shipped with the download
SUPPORT = Path(os.environ.get("SCENE_FILTER_SUPPORT") or Path.home() / ".scene-filter")
VERSIONS = SUPPORT / "app-versions"                  # downloaded versions, one folder each
STATE_FILE = SUPPORT / "app-state.json"              # which versions started fine, which didn't
URL_FILE = Path(os.environ.get("SCENE_FILTER_URL_FILE") or SUPPORT / "url")
KEEP = 3                                             # downloaded versions kept for falling back
CHECK_TIMEOUT = 6                                    # seconds to wait for the update check
START_TIMEOUT = 180                                  # seconds a version gets to open its page
IS_MAC = sys.platform == "darwin"
IS_WINDOWS = os.name == "nt"
NO_WINDOW = {"creationflags": 0x08000000} if IS_WINDOWS else {}


def log(msg: str) -> None:
    print(f"[starter] {msg}", flush=True)


def notify(msg: str) -> None:
    """Tell the person something is happening (a Mac notification; on Windows the console shows it)."""
    log(msg)
    if IS_MAC:
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Scene Filter"'],
                       capture_output=True)


# ------------------------------------------------------------------ state

def load_state() -> dict:
    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {"good": list(s.get("good", [])), "bad": list(s.get("bad", []))}
    except (OSError, ValueError):
        return {"good": [], "bad": []}


def save_state(state: dict) -> None:
    SUPPORT.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(STATE_FILE)


def mark(state: dict, version: int, verdict: str) -> None:
    other = "bad" if verdict == "good" else "good"
    if version not in state[verdict]:
        state[verdict].append(version)
    if version in state[other]:
        state[other].remove(version)
    save_state(state)


def read_version(folder: Path) -> int | None:
    try:
        return int((folder / "VERSION").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def available(state: dict) -> list[tuple[int, Path]]:
    """Every runnable version, newest first, leaving out ones marked bad."""
    found = {}
    v = read_version(HERE)
    if v is not None and (HERE / "app.py").is_file():
        found[v] = HERE
    if VERSIONS.is_dir():
        for d in VERSIONS.iterdir():
            v = read_version(d)
            if v is not None and d.name == str(v) and (d / "app.py").is_file():
                found.setdefault(v, d)
    return sorted(((v, d) for v, d in found.items() if v not in state["bad"]), reverse=True)


# ------------------------------------------------------------------ updates

def manifest_url() -> str | None:
    url = os.environ.get("SCENE_FILTER_UPDATE_URL")
    if not url:
        try:
            url = json.loads((HERE / "update_config.json").read_text(encoding="utf-8")).get("manifest_url")
        except (OSError, ValueError):
            return None
    if not url or "OWNER/REPO" in url:  # not set up yet
        return None
    return url


def _contexts():
    try:
        import certifi  # present once the app's packages are installed; the system's list is tried too

        yield ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    yield ssl.create_default_context()


def fetch(url: str, timeout: float) -> bytes:
    last = None
    for ctx in _contexts():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SceneFilter-updater"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read()
        except urllib.error.URLError as e:
            last = e
            if not isinstance(e.reason, ssl.SSLError):
                break
    raise last


def safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    root = dest.resolve()
    for m in zf.infolist():
        target = (dest / m.filename).resolve()
        if root != target and root not in target.parents:
            raise ValueError(f"unsafe path in update: {m.filename}")
    zf.extractall(dest)


def check_for_update(state: dict, current: int) -> None:
    url = manifest_url()
    if not url:
        return
    try:
        manifest = json.loads(fetch(url, CHECK_TIMEOUT))
        new = int(manifest["version"])
    except Exception as e:  # offline, or no release yet: just carry on with what we have
        log(f"update check skipped: {e}")
        return
    if new in state["bad"]:
        log(f"skipping version {new}: it didn't start last time (staying on {current})")
        return
    if new <= current or (VERSIONS / str(new)).is_dir():
        log(f"up to date (version {current})")
        return
    notify(f"Updating Scene Filter to version {new}...")
    try:
        data = fetch(manifest["url"], 120)
        if hashlib.sha256(data).hexdigest() != manifest["sha256"].lower():
            raise ValueError("download didn't match its fingerprint")
        VERSIONS.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".{new}-", dir=VERSIONS))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            safe_extract(zf, tmp)
        if read_version(tmp) != new or not (tmp / "app.py").is_file():
            shutil.rmtree(tmp, ignore_errors=True)
            raise ValueError("update package is incomplete")
        tmp.rename(VERSIONS / str(new))
        log(f"version {new} downloaded")
    except Exception as e:
        log(f"update to {new} failed, keeping version {current}: {e}")


def prune(state: dict, in_use: int) -> None:
    """Delete downloaded versions we no longer need: keep the one in use and the newest few that started fine."""
    if not VERSIONS.is_dir():
        return
    good = sorted((v for v in state["good"] if v != in_use), reverse=True)[:KEEP - 1]
    keep = {str(in_use), *map(str, good)}
    for d in VERSIONS.iterdir():
        if d.is_dir() and d.name not in keep:
            shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ packages

def ensure_packages(folder: Path) -> bool:
    """Install this version's packages if they differ from what's installed. False if that failed."""
    req = folder / "requirements.txt"
    if not req.is_file():
        return True
    digest = hashlib.sha256(req.read_bytes()).hexdigest()[:16]
    env_root = Path(sys.prefix)
    marker = env_root / f".packages-{digest}"
    if marker.exists():
        return True
    uv = os.environ.get("SCENE_FILTER_UV")
    if not uv or not Path(uv).exists():
        log("no package installer available; trying this version as-is")
        return True
    notify("Making sure Scene Filter has everything it needs. After an update this can take a few minutes...")
    r = subprocess.run([uv, "pip", "install", "--python", sys.executable, "-r", str(req)], **NO_WINDOW)
    if r.returncode != 0:
        return False
    for old in env_root.glob(".packages-*"):
        old.unlink(missing_ok=True)
    marker.touch()
    return True


# ------------------------------------------------------------------ running

_child: subprocess.Popen | None = None


def _forward(signum, _frame):
    if _child and _child.poll() is None:
        _child.terminate()
    sys.exit(0)


def run_version(folder: Path, on_start) -> tuple[bool, int]:
    """Run app.py from folder; on_start() is called as soon as its page opens.
    Returns (opened its page, exit code)."""
    global _child
    URL_FILE.unlink(missing_ok=True)
    env = {**os.environ, "SCENE_FILTER_URL_FILE": str(URL_FILE)}
    _child = subprocess.Popen([sys.executable, str(folder / "app.py")], cwd=str(folder), env=env)
    deadline = time.time() + START_TIMEOUT
    while _child.poll() is None and time.time() < deadline:
        if URL_FILE.is_file() and URL_FILE.stat().st_size > 0:
            on_start()
            return True, _child.wait()
        time.sleep(0.5)
    if _child.poll() is None:  # never opened its page in time: treat as a failed start
        _child.terminate()
        _child.wait()
        return False, 1
    started = URL_FILE.is_file() and URL_FILE.stat().st_size > 0
    if started:
        on_start()
    return started, _child.returncode


def main() -> int:
    signal.signal(signal.SIGTERM, _forward)
    SUPPORT.mkdir(parents=True, exist_ok=True)
    URL_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = load_state()
    versions = available(state)
    if not versions:
        log("no runnable version of Scene Filter found")
        return 1
    check_for_update(state, versions[0][0])
    tried = set()
    while True:
        versions = [(v, d) for v, d in available(state) if v not in tried]
        if not versions:
            log("no version of Scene Filter would start")
            return 1
        v, folder = versions[0]
        tried.add(v)
        log(f"starting version {v} from {folder}")
        if not ensure_packages(folder):
            if folder != HERE:
                log(f"version {v}'s packages wouldn't install; going back to the previous version")
                mark(state, v, "bad")
                continue
            return 1
        def on_start(v=v):
            mark(state, v, "good")
            prune(state, v)

        started, code = run_version(folder, on_start)
        if started:
            return code
        if folder == HERE or v in state["good"]:
            # The shipped version, or one that has worked before: not the update's fault. Don't fall back.
            log(f"version {v} stopped before opening (exit {code})")
            return code or 1
        log(f"version {v} failed to start (exit {code}); marking it bad and going back to the previous version")
        mark(state, v, "bad")
        notify("The latest update didn't start, so Scene Filter went back to the previous version.")


if __name__ == "__main__":
    sys.exit(main())
