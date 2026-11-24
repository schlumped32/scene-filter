"""Build a Scene Filter release.

    python tools/build.py --repo OWNER/REPO

Reads the version from app/VERSION and writes to dist/:
  scene-filter-app-<version>.zip   the update package (just the app code) that installed copies download
  latest.json                      tells installed copies the newest version, where it is, and its fingerprint
  Scene_Filter_for_Mac.zip         full download for new Mac users
  Scene_Filter_for_Windows.zip     full download for new Windows users

Then publish a GitHub release tagged v<version> with all four files attached. Installed copies look for
https://github.com/OWNER/REPO/releases/latest/download/latest.json each time they start.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"__pycache__", ".DS_Store"}


def files_under(folder: Path):
    for p in sorted(folder.rglob("*")):
        if p.is_file() and not (set(p.relative_to(folder).parts) & SKIP) and p.suffix != ".pyc":
            yield p


def add(zf: zipfile.ZipFile, src: Path | bytes, arcname: str, executable: bool = False) -> None:
    info = zipfile.ZipInfo(arcname, date_time=(2026, 1, 1, 0, 0, 0))  # fixed date: same input, same zip
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if executable else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.create_system = 3  # Unix, so the Mac launcher keeps its "can run" permission
    zf.writestr(info, src if isinstance(src, bytes) else src.read_bytes())


def add_app(zf: zipfile.ZipFile, prefix: str, config: bytes) -> None:
    """The app code, plus the starter and its update address."""
    for p in files_under(ROOT / "app"):
        add(zf, p, prefix + p.relative_to(ROOT / "app").as_posix())
    add(zf, ROOT / "launcher" / "run.py", prefix + "run.py")
    add(zf, config, prefix + "update_config.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="GitHub OWNER/REPO the releases are published to")
    ap.add_argument("--download-base", help="override where update packages are downloaded from (testing)")
    ap.add_argument("--manifest-url", help="override where installed copies check for updates (testing)")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    a = ap.parse_args()

    version = int((ROOT / "app" / "VERSION").read_text().strip())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = a.download_base or f"https://github.com/{a.repo}/releases/download/v{version}"
    manifest_url = a.manifest_url or f"https://github.com/{a.repo}/releases/latest/download/latest.json"
    config = json.dumps({"manifest_url": manifest_url}, indent=2).encode() + b"\n"

    # 1. update package: app code only, at the zip's top level
    pkg = out / f"scene-filter-app-{version}.zip"
    with zipfile.ZipFile(pkg, "w") as zf:
        for p in files_under(ROOT / "app"):
            add(zf, p, p.relative_to(ROOT / "app").as_posix())
    digest = hashlib.sha256(pkg.read_bytes()).hexdigest()

    # 2. the note installed copies check
    (out / "latest.json").write_text(json.dumps(
        {"version": version, "url": f"{base}/{pkg.name}", "sha256": digest}, indent=2) + "\n")

    # 3. full Mac download
    top = "Scene Filter for Mac/"
    with zipfile.ZipFile(out / "Scene_Filter_for_Mac.zip", "w") as zf:
        bundle = ROOT / "mac" / "Scene Filter.app"
        for p in files_under(bundle):
            rel = p.relative_to(ROOT / "mac").as_posix()
            add(zf, p, top + rel, executable=rel.endswith("MacOS/SceneFilter"))
        add_app(zf, top + "Scene Filter.app/Contents/Resources/app/", config)
        add(zf, ROOT / "mac" / "How to open.txt", top + "How to open.txt")

    # 4. full Windows download
    top = "Scene Filter for Windows/"
    with zipfile.ZipFile(out / "Scene_Filter_for_Windows.zip", "w") as zf:
        add(zf, ROOT / "windows" / "Scene Filter.cmd", top + "Scene Filter.cmd")
        add(zf, ROOT / "windows" / "How to open.txt", top + "How to open.txt")
        add(zf, ROOT / "windows" / "launcher.ps1", top + "app/launcher.ps1")
        add_app(zf, top + "app/", config)

    print(f"Built version {version} in {out}:")
    for p in sorted(out.iterdir()):
        print(f"  {p.name:36s} {p.stat().st_size:>9,} bytes")
    print(f"  update fingerprint (sha256): {digest}")


if __name__ == "__main__":
    main()
