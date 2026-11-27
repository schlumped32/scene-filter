# Sage & Forest Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Scene Filter screen into the agreed Sage & Forest look (light and dark) with a Movie → Review → Save layout, and ship it as version 8.

**Architecture:** Colors, fonts and CSS move into a new `app/theme.py` (a Gradio theme with light and `*_dark` values plus one CSS string). The text shown in the Review section moves into a new `app/review.py` of pure functions (no Gradio), so it can be unit-tested. `app/app.py` keeps its scan/save handlers and is regrouped into three sections that use both. The scene table becomes a tick-box list with one row per scene.

**Tech Stack:** Python 3.12, Gradio 6 (already a dependency), pytest for tests (dev only, not added to `app/requirements.txt`), Playwright (preinstalled, Node) for one screen smoke test.

**Spec:** `docs/superpowers/specs/2026-11-27-sage-forest-redesign-design.md`

## Global Constraints

- Only files under `app/` ship; installed copies get them by auto-update. Raise `app/VERSION` to `8`.
- No new runtime packages: `app/requirements.txt` stays as it is.
- Fonts: Plus Jakarta Sans (everything), JetBrains Mono (timestamps), from Google Fonts, always with system fallbacks so the app looks right offline.
- Light/dark follows the computer's setting (Gradio's own `.dark` switching); no in-app toggle.
- Palette values are exactly the spec's table (copied into Task 1's test).
- Scanning, filtering, saving, the starter and auto-update behavior do not change.
- Labels get plainer, never more technical. Filter choices read: `Cut out`, `Blur`, `Black screen`, `Times only`.

## Review Focus

1. **Gradio's own widgets in dark mode** (file drop area, accordion, sliders, progress bar, gallery): must be readable on the dark green, not left white-on-white or black-on-green. Covered by the Task 4 screenshots in both color schemes.
2. **Rescanning a second movie**: tick boxes from the first movie must not carry over to the second. Task 3 resets the ticks on every scan; Task 2's `apply_picks` test pins that only current scene numbers count.
3. **A scan that flags nothing**: the Review section needs a clear "No scenes flagged" state, not an empty card. Task 2 test `test_summary_no_scenes`.
4. **Narrow windows and long movie names**: rows wrap instead of running off the side. Covered by the Task 4 phone-width screenshot.
5. **Accurate detector unavailable**: the badge must say the quick detector was used, not claim the accurate one. Task 2 test `test_summary_quick_fallback`.

---

### Task 1: Theme and styles (`app/theme.py`)

**Files:**
- Create: `app/theme.py`
- Test: `tests/test_theme.py`

**Interfaces:**
- Produces: `LIGHT: dict[str, str]`, `DARK: dict[str, str]` (keys: `page`, `card`, `text`, `muted`, `border`, `accent`, `on_accent`, `badge_bg`, `badge_fg`, `tag_bg`, `tag_fg`); `make_theme() -> gr.themes.Base`; `CSS: str`; `HEAD: str` (the Google Fonts `<link>` tags).

- [ ] **Step 1: Write the failing tests**

```python
from app import theme  # tests run from the repo root with app/ on sys.path; see conftest in Step 3

def test_palettes_match_spec():
    assert theme.LIGHT == {"page": "#e7efe8", "card": "#ffffff", "text": "#15281d", "muted": "#5d7366",
        "border": "#d5e1d8", "accent": "#1f5136", "on_accent": "#f2f8f3", "badge_bg": "#dcefe1",
        "badge_fg": "#1f5c3b", "tag_bg": "#f6e6dc", "tag_fg": "#8a4a2c"}
    assert theme.DARK == {"page": "#10241a", "card": "#173226", "text": "#e3efe6", "muted": "#9ab8a4",
        "border": "#24432f", "accent": "#a8d5b5", "on_accent": "#0f2418", "badge_bg": "#1f4331",
        "badge_fg": "#bfe6cb", "tag_bg": "#3a2b24", "tag_fg": "#f0c9b2"}

def test_theme_sets_light_and_dark_backgrounds():
    t = theme.make_theme()
    assert t.body_background_fill == "#e7efe8" and t.body_background_fill_dark == "#10241a"
    assert t.button_primary_background_fill == "#1f5136" and t.button_primary_background_fill_dark == "#a8d5b5"

def test_css_has_both_modes_and_fallback_fonts():
    assert ".dark" in theme.CSS and "#10241a" in theme.CSS
    assert "Plus Jakarta Sans" in theme.CSS and "system-ui" in theme.CSS
```

- [ ] **Step 2: Run to see them fail**

Run: `$PY -m pytest tests/test_theme.py -q` (`$PY` = a Python with `app/requirements.txt` and pytest installed)
Expected: FAIL, `ModuleNotFoundError: theme`

- [ ] **Step 3: Implement `app/theme.py` and `tests/conftest.py`**

`conftest.py` puts the repo root on `sys.path`. `make_theme()` builds on `gr.themes.Base` and sets body, block, input, border, primary-button and slider fills from `LIGHT`, with every matching `*_dark` from `DARK`; radius around 14px for cards, 11px for buttons. `CSS` styles the three section cards, the header (name + version pill), the scene rows (Task 3's tick-box list), the "Double-checked" badge and timestamps in JetBrains Mono, using CSS variables set once on `:root`/`.gradio-container` and again under `.dark`.

- [ ] **Step 4: Run the tests**

Run: `$PY -m pytest tests/test_theme.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/theme.py tests/conftest.py tests/test_theme.py
git commit -m "Add the Sage & Forest theme with light and dark palettes"
```

### Task 2: Review text (`app/review.py`)

**Files:**
- Create: `app/review.py`
- Test: `tests/test_review.py`

**Interfaces:**
- Consumes: `scene_filter.core.Scene`, `scene_filter.core.fmt_ts`
- Produces:
  - `summary_html(n_scenes: int, total_s: float, duration_s: float, seconds: float, suspicious: int, accurate: bool, double_check: bool, animated: bool) -> str`
  - `scene_choices(scenes: list[Scene]) -> list[tuple[str, int]]`: one `(label, scene.index)` per scene
  - `apply_picks(scenes: list[Scene], picked: list[int]) -> list[Scene]`: sets `include = index in picked`, returns the list

- [ ] **Step 1: Write the failing tests**

```python
from app.scene_filter.core import Scene
from app import review

def s(i, a, b, labels, peak):
    return Scene(index=i, start=a, end=b, first_seen=a, last_seen=b, peak_score=peak, hits=3, labels=labels)

def test_summary_counts_and_accurate_badge():
    h = review.summary_html(2, 12.0, 5534, 61, 7, accurate=True, double_check=True, animated=False)
    assert "2" in h and "scenes flagged" in h and "accurate detector" in h

def test_summary_no_scenes():
    h = review.summary_html(0, 0, 5534, 61, 0, accurate=True, double_check=True, animated=True)
    assert "No scenes flagged" in h and "Animated movie" in h  # hint mentions unticking it

def test_summary_quick_fallback():
    h = review.summary_html(1, 4.0, 5534, 61, 3, accurate=False, double_check=True, animated=False)
    assert "quick detector" in h and "accurate detector couldn" in h

def test_scene_choices_label():
    [(label, idx)] = review.scene_choices([s(1, 3422.0, 3429.4, ["FEMALE_BREAST_EXPOSED"], 0.88)])
    assert idx == 1 and label == "00:57:02 – 00:57:10 · Exposed breast · 88%"

def test_apply_picks_only_current_scenes():
    scenes = [s(1, 0, 3, ["BUTTOCKS_EXPOSED"], .7), s(2, 9, 12, ["BUTTOCKS_EXPOSED"], .8)]
    review.apply_picks(scenes, [2, 7])   # 7 is a leftover from another movie
    assert [x.include for x in scenes] == [False, True]
```

- [ ] **Step 2: Run to see them fail**

Run: `$PY -m pytest tests/test_review.py -q`
Expected: FAIL, `cannot import name 'review'`

- [ ] **Step 3: Implement `app/review.py`**

Label: `f"{fmt_ts(start)} – {fmt_ts(end, round_up=True)} · {scene.label_text()} · {peak:.0%}"`. `summary_html` returns small HTML using the CSS classes from Task 1 (big count, muted "… of video, scanned in Ns", and the badge: accurate / quick-fallback / none when `double_check` is false). With no scenes: "No scenes flagged" plus the existing hint (raise sensitivity, or untick Animated movie when `animated`).

- [ ] **Step 4: Run the tests**

Run: `$PY -m pytest tests/ -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add app/review.py tests/test_review.py
git commit -m "Add the Review section's summary and scene labels"
```

### Task 3: Regroup the screen (`app/app.py`)

**Files:**
- Modify: `app/app.py` (`MODE_LABELS`, `_table`, `_apply_table`, `do_scan`, `do_export`, `build_ui`, `__main__`)

**Interfaces:**
- Consumes: Task 1 `make_theme()`, `CSS`, `HEAD`; Task 2 `summary_html`, `scene_choices`, `apply_picks`
- Produces: nothing new for other tasks.

- [ ] **Step 1: Make the change**

- `MODE_LABELS` keys become `Cut out`, `Blur`, `Black screen`, `Times only` (same values `cut`/`blur`/`black`/`none`); default `Cut out`.
- Replace `TABLE_COLS`, `_table` and `_apply_table` with Task 2's functions. The scene list is a `gr.CheckboxGroup(choices=scene_choices(scenes), value=[all indices])`, and `do_scan` returns a fresh one each scan (Review Focus 2). `do_export` calls `apply_picks(state["scenes"], picked)`.
- Header: `gr.HTML` with the name and a `Version {APP_VERSION}` pill.
- Three `gr.Group` sections with elem_classes `sf-card`, each opening with a small uppercase step label:
  - **Movie:** drop area, path box + "Choose movie...", Animated switch, `Detection settings` accordion (closed; contents unchanged), **Scan movie**.
  - **Review:** `gr.HTML` summary, the tick-box list, the gallery (label "Previews").
  - **Save:** filter choice as a horizontal `gr.Radio`, mute box, **Save filtered movie**, "Open output folder", result text and files.
- Pass `theme=make_theme(), css=CSS, head=HEAD` wherever Gradio 6 accepts them (`gr.Blocks` or `launch`).

- [ ] **Step 2: Check it still imports and starts**

Run: `$PY -c "import sys; sys.path.insert(0,'app'); import app; app.build_ui()"`
Expected: no error

- [ ] **Step 3: Run the unit tests**

Run: `$PY -m pytest tests/ -q`
Expected: 8 passed

- [ ] **Step 4: Commit**

```bash
git add app/app.py
git commit -m "Regroup the screen into Movie, Review and Save"
```

### Task 4: Screen check in both modes, then version 8

**Files:**
- Create: `tests/ui/fake_app.py` (starts `app.py` with the detector replaced so a scan flags 2 scenes in a few seconds; same idea as the session's earlier test harness), `tests/ui/smoke.cjs` (Playwright)
- Modify: `app/VERSION` → `8`; create `release-notes/v8.md`

**Interfaces:**
- Consumes: the running app from Task 3.

- [ ] **Step 1: Write the smoke test**

`smoke.cjs` opens the app twice, with `colorScheme: 'light'` and `'dark'`, at 1280px and 400px wide. It fills the path box with a generated test video, clicks **Scan movie**, waits for "2 scenes flagged", unticks the second scene, picks **Black screen**, clicks **Save filtered movie**, waits for "Done. 1 scene(s) filtered", and saves a screenshot for each mode and width. It fails on any page error.

- [ ] **Step 2: Run it**

Run: `$PY tests/ui/fake_app.py & node tests/ui/smoke.cjs`
Expected: `PASS light`, `PASS dark`, four screenshots written. Look at them against the mockup and the Review Focus list (dark-mode widgets readable, narrow width wraps).

- [ ] **Step 3: Version and notes**

`app/VERSION` = `8`. `release-notes/v8.md`: "A fresh look: Sage & Forest in light mode, deep forest green in dark mode, and a simpler Movie → Review → Save screen. Nothing about scanning or saving changed."

- [ ] **Step 4: Run everything once more**

Run: `$PY -m pytest tests/ -q` then the smoke test again.
Expected: 8 passed; `PASS light`, `PASS dark`

- [ ] **Step 5: Commit and push**

```bash
git add tests/ui app/VERSION release-notes/v8.md
git commit -m "Version 8: Sage & Forest look"
git push origin main
```

Then the owner clicks **Actions → Release → Run workflow** to publish.
