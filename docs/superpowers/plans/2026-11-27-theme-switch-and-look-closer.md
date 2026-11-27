# Theme Switch and Look Closer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a remembered light/dark switch and a per-scene "Look closer" (lightly blurred, never clear) preview, remove the "Show unblurred preview images" setting, and ship as version 9.

**Architecture:** `core.save_thumbnails` writes two blurred JPEGs per scene (heavy and light) from the in-memory frame and never writes the clear one. `review.scene_rows` adds both preview addresses to each row; `scene_list.SceneList` shows the heavy one as a row thumbnail and swaps in the light one under that row when "Look closer" is clicked (all in the page, no server call). The theme switch is a header button plus a small script in `theme.HEAD` that sets Gradio's `dark` class and remembers the choice in the browser.

**Tech Stack:** Python 3.12, Gradio 6, OpenCV (already installed with NudeNet), pytest, Playwright (Node).

**Spec:** `docs/superpowers/specs/2026-11-27-theme-switch-and-look-closer-design.md`

## Global Constraints

- Never a fully clear preview by any path: the clear frame is used only in memory to make the two blurred versions, and is never saved to disk or sent to the screen.
- Ticking/unticking scenes, detection, filtering and saving behave exactly as in version 8.
- Only `app/` ships; raise `app/VERSION` to `9`. No new runtime packages.
- The theme switch follows the computer until clicked, then remembers the choice in the browser on that computer.
- One lighter step only (heavy → light). Button copy: `Look closer`, `Blur again`.
- `$PY` = the Python with `app/requirements.txt` + pytest; unit tests `$PY -m pytest tests/ -q`; screen test: `$PY tests/ui/fake_app.py &` then `node tests/ui/smoke.cjs`.

## Review Focus

1. **Clicking Look closer or Blur again must not tick or untick the scene.** Smoke test in Task 3 saves after looking closer and still expects "1 scene(s) filtered".
2. **Folder names with spaces or accents** (the default output folder is `Movies/Scene Filter`): preview addresses must still load. Task 2 test `test_file_url_quotes_spaces_and_accents`.
3. **A scene with no saved preview** (no stored frame): its row shows no thumbnail and no Look closer button, not a broken image. Task 2 test `test_scene_rows_without_preview`.
4. **Browser storage blocked** (private window, cleared data): the theme switch still works for the session and the app still starts. Task 4 script wraps every storage call in try/catch; reviewer checks.
5. **Rescanning after looking closer:** the new movie's rows start fully blurred, with nothing left open from the last movie. Smoke test in Task 3 rescans and expects no open light view.

---

### Task 1: Two blurred previews per scene (`core.py`)

**Files:**
- Modify: `app/scene_filter/core.py` (`Scene`, `save_thumbnails`, `scan`, `export_lists`)
- Test: `tests/test_previews.py`

**Interfaces:**
- Produces: `Scene.thumbnail_light: Optional[str] = None`; `save_thumbnails(scenes, frames, hits, out_dir: Path) -> None` (no `blur` parameter) writes `scene_<NNN>.jpg` (heavy) and `scene_<NNN>_light.jpg` (light) and sets `thumbnail` / `thumbnail_light`; `scan(...)` loses `blur_thumbnails`; `HEAVY_BLUR_PX = 16`, `LIGHT_BLUR_PX = 48` (pixel grid the 320px frame is shrunk to before the blur step).

- [ ] **Step 1: Write the failing tests**

```python
import cv2, numpy as np
from pathlib import Path
from scene_filter import core

def _detail(path):  # higher = sharper
    return cv2.Laplacian(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE), cv2.CV_64F).var()

def _frame():  # a detailed test picture: fine checkerboard
    return (np.indices((320, 320)).sum(axis=0) % 8 < 4).astype(np.uint8)[..., None].repeat(3, 2) * 255

def _scene_and_hits():
    hits = [core.Hit(10.0, 0.9, ["FEMALE_BREAST_EXPOSED"])]
    return core.merge_hits(hits, 60), hits

def test_two_blur_levels_and_no_clear_file(tmp_path):
    scenes, hits = _scene_and_hits()
    clear = tmp_path / "clear.png"; cv2.imwrite(str(clear), _frame())
    core.save_thumbnails(scenes, {10.0: _frame()}, hits, tmp_path / "t")
    s = scenes[0]
    assert sorted(p.name for p in (tmp_path / "t").iterdir()) == ["scene_001.jpg", "scene_001_light.jpg"]
    assert s.thumbnail.endswith("scene_001.jpg") and s.thumbnail_light.endswith("scene_001_light.jpg")
    assert _detail(s.thumbnail) < _detail(s.thumbnail_light) < _detail(clear) / 4

def test_scene_without_frame_gets_no_previews(tmp_path):
    scenes, hits = _scene_and_hits()
    core.save_thumbnails(scenes, {}, hits, tmp_path / "t")
    assert scenes[0].thumbnail is None and scenes[0].thumbnail_light is None

def test_export_json_leaves_out_preview_paths(tmp_path):
    scenes, _ = _scene_and_hits()
    scenes[0].thumbnail, scenes[0].thumbnail_light = "a.jpg", "b.jpg"
    text = Path(core.export_lists(scenes, "movie.mp4", tmp_path)["json"]).read_text()
    assert "a.jpg" not in text and "b.jpg" not in text
```

- [ ] **Step 2: Run to see them fail**

Run: `$PY -m pytest tests/test_previews.py -q`
Expected: FAIL (no `_light` file / no `thumbnail_light` attribute)

- [ ] **Step 3: Implement**

Heavy: shrink to `HEAVY_BLUR_PX`² with `INTER_AREA`, enlarge with `INTER_NEAREST` (today's look). Light: shrink to `LIGHT_BLUR_PX`² with `INTER_AREA`, enlarge with `INTER_LINEAR`, then `GaussianBlur((9, 9), 0)`. Write with `cv2.imencode` + `write_bytes` as today. Drop `blur`/`blur_thumbnails`; `export_lists` leaves out both `thumbnail` keys.

- [ ] **Step 4: Run the tests**

Run: `$PY -m pytest tests/ -q`
Expected: all pass (11)

- [ ] **Step 5: Commit** — `git commit -m "Save a heavy and a light blurred preview per scene, never a clear one"`

### Task 2: Preview addresses for the scene rows (`review.py`)

**Files:**
- Modify: `app/review.py` (`scene_rows`, new `file_url`)
- Test: `tests/test_review.py`

**Interfaces:**
- Consumes: Task 1's `Scene.thumbnail`, `Scene.thumbnail_light`
- Produces: `file_url(path: str) -> str` returning `"/gradio_api/file=" + quote(path, safe="/:\\")`; `scene_rows(scenes)` rows gain `"thumb": str | None` and `"thumb_light": str | None` (both `None` unless both previews exist).

- [ ] **Step 1: Write the failing tests** (and update `test_scene_rows_for_the_scene_list` to expect `"thumb": None, "thumb_light": None`)

```python
def test_file_url_quotes_spaces_and_accents():
    assert review.file_url("/Users/José/Movies/Scene Filter/t/scene_001.jpg") == \
        "/gradio_api/file=/Users/Jos%C3%A9/Movies/Scene%20Filter/t/scene_001.jpg"

def test_scene_rows_with_previews():
    sc = s(1, 10, 14, ["FEMALE_BREAST_EXPOSED"], .9); sc.thumbnail, sc.thumbnail_light = "/o/a.jpg", "/o/a_light.jpg"
    row = review.scene_rows([sc])[0]
    assert row["thumb"] == "/gradio_api/file=/o/a.jpg" and row["thumb_light"] == "/gradio_api/file=/o/a_light.jpg"

def test_scene_rows_without_preview():
    row = review.scene_rows([s(1, 10, 14, ["FEMALE_BREAST_EXPOSED"], .9)])[0]
    assert row["thumb"] is None and row["thumb_light"] is None
```

- [ ] **Step 2: Run to see them fail** — `$PY -m pytest tests/test_review.py -q` → FAIL (`file_url` missing)
- [ ] **Step 3: Implement** `file_url` and the two row keys.
- [ ] **Step 4: Run** — `$PY -m pytest tests/ -q` → all pass (14)
- [ ] **Step 5: Commit** — `git commit -m "Give each scene row its preview addresses"`

### Task 3: Look closer in the scene list, previews strip and setting removed

**Files:**
- Modify: `app/scene_list.py` (template, CSS, script), `app/app.py` (remove `clear_previews` and the gallery; `do_scan` outputs), `tests/ui/fake_app.py` (store the checkerboard frame from Task 1's test instead of flat gray), `tests/ui/smoke.cjs`

**Interfaces:**
- Consumes: Task 2's row keys `thumb`, `thumb_light`.

- [ ] **Step 1: Extend the smoke test first.** Before saving: click the first row's `Look closer` button; expect a visible `img` whose `src` contains `_light.jpg` under that row and a `Blur again` button; click `Blur again`; expect no visible `_light.jpg` image. Keep the existing untick-and-save check (must still give "Done. 1 scene(s) filtered"; Review Focus 1). After the rescan: expect zero visible `_light.jpg` images (Review Focus 5). Expect no "Show unblurred preview images" text and no "Previews" gallery anywhere.
- [ ] **Step 2: Run it** — expected `FAIL light: ...Look closer...`
- [ ] **Step 3: Implement.** Row markup becomes a `div.sf-row` holding the `<label>` (tick box, heavy thumbnail 56×56 rounded, time, tag), the confidence bar, and a `Look closer` button outside the label; a hidden panel under the row holds the light image (max 320px wide) and `Blur again`. Rows without `thumb` render no thumbnail and no button. Toggling uses one click listener on `element` matching `[data-closer]`/`[data-blur]`; it calls `preventDefault` and never touches tick boxes. Remove `clear_previews` from `do_scan`'s inputs/signature and the `gr.Gallery` from layout and outputs.
- [ ] **Step 4: Run** — unit tests all pass; smoke `PASS light`, `PASS dark`. Look at the screenshots: thumbnail heavy, open view lightly blurred, both modes.
- [ ] **Step 5: Commit** — `git commit -m "Add Look closer to each scene; remove the previews strip and the unblurred setting"`

### Task 4: Light/dark switch, then version 9

**Files:**
- Modify: `app/theme.py` (`HEAD` gains the script; CSS for the button), `app/app.py` (`HEADER` gains the button), `tests/ui/smoke.cjs`, `app/VERSION` → `9`; create `release-notes/v9.md`

**Interfaces:**
- Produces: header button `<button class="sf-theme" data-sf-theme-toggle aria-label="Switch light or dark">`; browser storage key `sf-theme` with values `light` / `dark`.

- [ ] **Step 1: Extend the smoke test.** In a light-scheme page: click the switch → `document.body.classList.contains('dark')` is true and the body background is `rgb(16, 36, 26)` (#10241a); reload → still dark. Click again → light (#e7efe8) and still light after reload. Clear `sf-theme`, reload with a dark color scheme → dark (follows the computer).
- [ ] **Step 2: Run it** — expected `FAIL ...switch...`
- [ ] **Step 3: Implement.** Script in `HEAD`: on load, if `sf-theme` is stored, add/remove `dark` on `document.body`; a document-level click listener for `[data-sf-theme-toggle]` flips the class and stores the choice. Every `localStorage` access in try/catch (Review Focus 4). Button shows a sun in dark mode and a moon in light mode (CSS on `.dark`).
- [ ] **Step 4: Version and notes.** `app/VERSION` = `9`. `release-notes/v9.md`: light/dark switch; "Look closer" on each flagged scene (lightly blurred, never clear); the "Show unblurred preview images" setting is gone.
- [ ] **Step 5: Run everything** — unit tests all pass; smoke `PASS light`, `PASS dark` (and the switch checks).
- [ ] **Step 6: Commit** — `git commit -m "Version 9: light/dark switch"`
