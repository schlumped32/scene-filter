from pathlib import Path

import cv2
import numpy as np

from scene_filter import core


def _img(path):
    return cv2.imread(str(path)).astype(np.float64)


def _frame():
    """A test picture: big shapes (what kind of scene it is) on the left, fine checkerboard (detail) on the right."""
    f = np.full((320, 320, 3), 40, np.uint8)
    cv2.rectangle(f, (20, 40), (140, 160), (230, 230, 230), -1)
    cv2.circle(f, (80, 240), 50, (120, 200, 90), -1)
    fine = (np.indices((320, 160)).sum(axis=0) % 4 < 2).astype(np.uint8) * 255
    f[:, 160:] = fine[..., None]
    return f


def _scene_and_hits():
    hits = [core.Hit(10.0, 0.9, ["FEMALE_BREAST_EXPOSED"])]
    return core.merge_hits(hits, 60), hits


def test_two_blur_levels_and_no_clear_file(tmp_path):
    scenes, hits = _scene_and_hits()
    core.save_thumbnails(scenes, {10.0: _frame()}, hits, tmp_path / "t")
    s = scenes[0]
    assert sorted(p.name for p in (tmp_path / "t").iterdir()) == ["scene_001.jpg", "scene_001_light.jpg"]
    assert s.thumbnail.endswith("scene_001.jpg") and s.thumbnail_light.endswith("scene_001_light.jpg")
    original = _frame().astype(np.float64)
    heavy, light = _img(s.thumbnail), _img(s.thumbnail_light)
    # The light preview keeps more of the overall picture than the heavy one. Compared at 40px (shapes, not
    # pixels), since pixel-by-pixel comparison penalises smooth blurs for softening edges that blocks keep sharp.
    def shapes(x):
        return cv2.resize(x, (40, 40), interpolation=cv2.INTER_AREA)[:, :20]
    assert np.abs(shapes(light) - shapes(original)).mean() < np.abs(shapes(heavy) - shapes(original)).mean()
    # ...and both wipe out fine detail: the checkerboard half comes out nearly flat.
    for blurred in (heavy, light):
        assert blurred[:, 170:310].std() < original[:, 170:310].std() / 5


def test_scene_without_frame_gets_no_previews(tmp_path):
    scenes, hits = _scene_and_hits()
    core.save_thumbnails(scenes, {}, hits, tmp_path / "t")
    assert scenes[0].thumbnail is None and scenes[0].thumbnail_light is None


def test_export_json_leaves_out_preview_paths(tmp_path):
    scenes, _ = _scene_and_hits()
    scenes[0].thumbnail, scenes[0].thumbnail_light = "a.jpg", "b.jpg"
    text = Path(core.export_lists(scenes, "movie.mp4", tmp_path)["json"]).read_text()
    assert "a.jpg" not in text and "b.jpg" not in text


def _closeup():
    """A close-up-style picture: dark shapes 16-30px across (like features in a frame-filling shot)."""
    f = np.full((320, 320, 3), 200, np.uint8)
    rng = np.random.default_rng(7)
    for _ in range(40):
        x, y = rng.integers(20, 300, 2)
        cv2.circle(f, (int(x), int(y)), int(rng.integers(8, 15)), (40, 40, 40), -1)
    return f


def _sharpest_edge(img):
    g = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float64)
    return np.hypot(cv2.Sobel(g, cv2.CV_64F, 1, 0), cv2.Sobel(g, cv2.CV_64F, 0, 1)).max()


def test_light_preview_softens_outlines_on_closeups(tmp_path):
    """The owner chose the softer light blur (option B): on a close-up, no outline keeps more than a fifth of its
    sharpness. (The first light blur kept 24%, the chosen one about 15%.)"""
    hits = [core.Hit(10.0, 0.9, ["FEMALE_BREAST_EXPOSED"])]
    scenes = core.merge_hits(hits, 60)
    core.save_thumbnails(scenes, {10.0: _closeup()}, hits, tmp_path / "t")
    assert _sharpest_edge(_img(scenes[0].thumbnail_light)) < 0.2 * _sharpest_edge(_closeup())
