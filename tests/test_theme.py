import theme


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
