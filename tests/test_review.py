import review
from scene_filter.core import Scene


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


def test_apply_picks_only_current_scenes():
    scenes = [s(1, 0, 3, ["BUTTOCKS_EXPOSED"], .7), s(2, 9, 12, ["BUTTOCKS_EXPOSED"], .8)]
    review.apply_picks(scenes, [2, 7])   # 7 is a leftover from another movie
    assert [x.include for x in scenes] == [False, True]


def test_scene_rows_for_the_scene_list():
    rows = review.scene_rows([s(1, 3422.0, 3429.4, ["FEMALE_BREAST_EXPOSED", "BUTTOCKS_EXPOSED"], 0.884)])
    assert rows == [{"index": 1, "time": "00:57:02 – 00:57:10", "tag": "Exposed breast, Exposed buttocks",
                     "confidence": 88, "thumb": None, "thumb_light": None}]


def test_file_url_quotes_spaces_and_accents():
    assert review.file_url("/Users/José/Movies/Scene Filter/t/scene_001.jpg") == \
        "/gradio_api/file=/Users/Jos%C3%A9/Movies/Scene%20Filter/t/scene_001.jpg"


def test_scene_rows_with_previews():
    sc = s(1, 10, 14, ["FEMALE_BREAST_EXPOSED"], .9)
    sc.thumbnail, sc.thumbnail_light = "/o/a.jpg", "/o/a_light.jpg"
    row = review.scene_rows([sc])[0]
    assert row["thumb"] == "/gradio_api/file=/o/a.jpg" and row["thumb_light"] == "/gradio_api/file=/o/a_light.jpg"


def test_scene_rows_without_preview():
    row = review.scene_rows([s(1, 10, 14, ["FEMALE_BREAST_EXPOSED"], .9)])[0]
    assert row["thumb"] is None and row["thumb_light"] is None
