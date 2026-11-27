"""Scene Filter's look: "Sage & Forest" in light mode and its deep forest-green twin in dark mode.

Gradio switches between the two by itself, following the computer's light/dark setting. Every color is defined
twice: the `make_theme()` values style Gradio's own widgets, and the CSS variables style the parts Scene Filter
draws itself (header, section cards, summary, scene rows).
"""
from __future__ import annotations

import gradio as gr

LIGHT = {
    "page": "#e7efe8", "card": "#ffffff", "text": "#15281d", "muted": "#5d7366", "border": "#d5e1d8",
    "accent": "#1f5136", "on_accent": "#f2f8f3", "badge_bg": "#dcefe1", "badge_fg": "#1f5c3b",
    "tag_bg": "#f6e6dc", "tag_fg": "#8a4a2c",
}
DARK = {
    "page": "#10241a", "card": "#173226", "text": "#e3efe6", "muted": "#9ab8a4", "border": "#24432f",
    "accent": "#a8d5b5", "on_accent": "#0f2418", "badge_bg": "#1f4331", "badge_fg": "#bfe6cb",
    "tag_bg": "#3a2b24", "tag_fg": "#f0c9b2",
}
# Softer fills used for rows, hovers and inputs (derived from the palettes above, not separate brand colors).
_LIGHT_SOFT = {"row": "#f1f6f2", "hover": "#2a6646", "strong_border": "#a9bfb0"}
_DARK_SOFT = {"row": "#132b20", "hover": "#bfe2c9", "strong_border": "#4a6e57"}

SANS = ['"Plus Jakarta Sans"', "ui-sans-serif", "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"]
MONO = ['"JetBrains Mono"', "ui-monospace", '"SF Mono"', "Menlo", "Consolas", "monospace"]

# Loaded from Google Fonts; with no internet the system fonts in SANS/MONO take over.
# The light/dark switch. Gradio picks light or dark from the computer when the page opens; once someone clicks the
# switch, their choice is kept in the browser (key "sf-theme") and applied on every later visit, and re-applied if
# Gradio sets its own afterwards. Every storage call is guarded: with storage blocked the switch still works for the
# visit, and the app still follows the computer.
THEME_SCRIPT = """<script>
(() => {
  const KEY = "sf-theme";
  const saved = () => { try { return localStorage.getItem(KEY); } catch (e) { return null; } };
  const save = (v) => { try { localStorage.setItem(KEY, v); } catch (e) {} };
  let choice = saved();
  const apply = () => {
    if (!document.body || (choice !== "dark" && choice !== "light")) return;
    const wantDark = choice === "dark";
    if (document.body.classList.contains("dark") !== wantDark) document.body.classList.toggle("dark", wantDark);
  };
  const start = () => {
    apply();
    new MutationObserver(apply).observe(document.body, { attributes: true, attributeFilter: ["class"] });
  };
  document.body ? start() : document.addEventListener("DOMContentLoaded", start);
  document.addEventListener("click", (e) => {
    if (!e.target.closest("[data-sf-theme-toggle]")) return;
    choice = document.body.classList.contains("dark") ? "light" : "dark";
    save(choice);
    apply();
  });
})();
</script>"""

HEAD = THEME_SCRIPT + (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800'
    '&family=JetBrains+Mono:wght@500&display=swap">'
)


def make_theme() -> gr.themes.Base:
    """Gradio's own widgets (buttons, inputs, sliders, tick boxes, drop area) in both palettes."""
    L, D, l, d = LIGHT, DARK, _LIGHT_SOFT, _DARK_SOFT
    pairs = {
        "body_background_fill": (L["page"], D["page"]),
        "body_text_color": (L["text"], D["text"]),
        "body_text_color_subdued": (L["muted"], D["muted"]),
        "background_fill_primary": (L["card"], D["card"]),
        "background_fill_secondary": (l["row"], d["row"]),
        "block_background_fill": (L["card"], D["card"]),
        "block_border_color": (L["border"], D["border"]),
        "block_label_text_color": (L["muted"], D["muted"]),
        "block_title_text_color": (L["text"], D["text"]),
        "block_info_text_color": (L["muted"], D["muted"]),
        "border_color_primary": (L["border"], D["border"]),
        "border_color_accent": (L["accent"], D["accent"]),
        "input_background_fill": (l["row"], d["row"]),
        "input_border_color": (L["border"], D["border"]),
        "input_border_color_focus": (L["accent"], D["accent"]),
        "input_placeholder_color": (L["muted"], D["muted"]),
        "color_accent_soft": (L["badge_bg"], D["badge_bg"]),
        "link_text_color": (L["accent"], D["accent"]),
        "button_primary_background_fill": (L["accent"], D["accent"]),
        "button_primary_background_fill_hover": (l["hover"], d["hover"]),
        "button_primary_text_color": (L["on_accent"], D["on_accent"]),
        "button_primary_border_color": (L["accent"], D["accent"]),
        "button_secondary_background_fill": (l["row"], d["row"]),
        "button_secondary_background_fill_hover": (L["badge_bg"], D["badge_bg"]),
        "button_secondary_text_color": (L["text"], D["text"]),
        "button_secondary_border_color": (L["border"], D["border"]),
        "checkbox_background_color": (L["card"], D["card"]),
        "checkbox_background_color_selected": (L["accent"], D["accent"]),
        "checkbox_border_color": (l["strong_border"], d["strong_border"]),
        "checkbox_border_color_selected": (L["accent"], D["accent"]),
        "checkbox_label_background_fill": (l["row"], d["row"]),
        "checkbox_label_background_fill_selected": (L["badge_bg"], D["badge_bg"]),
        "checkbox_label_text_color": (L["text"], D["text"]),
        "checkbox_label_text_color_selected": (L["text"], D["text"]),
        "slider_color": (L["accent"], D["accent"]),
        "loader_color": (L["accent"], D["accent"]),
        "table_border_color": (L["border"], D["border"]),
        "table_odd_background_fill": (L["card"], D["card"]),
        "table_even_background_fill": (l["row"], d["row"]),
        "table_row_focus": (L["badge_bg"], D["badge_bg"]),
    }
    settings = {}
    for name, (light, dark) in pairs.items():
        settings[name] = light
        settings[name + "_dark"] = dark
    return gr.themes.Base(
        primary_hue=gr.themes.colors.green,
        neutral_hue=gr.themes.colors.gray,
        font=SANS,
        font_mono=MONO,
        radius_size=gr.themes.sizes.radius_lg,
    ).set(
        **settings,
        color_accent=L["accent"],  # Gradio has no dark variant of this one; dark widgets use the settings above
        block_radius="14px",
        button_large_radius="11px",
        button_medium_radius="11px",
        button_small_radius="9px",
        block_shadow="none",
        button_primary_shadow="none",
    )


def _vars(p: dict, soft: dict) -> str:
    return "".join(f"--sf-{k.replace('_', '-')}: {v};" for k, v in {**p, **soft}.items())


CSS = (
    ":root, .gradio-container {" + _vars(LIGHT, _LIGHT_SOFT) + "--sf-sans: " + ", ".join(SANS) + ";"
    "--sf-mono: " + ", ".join(MONO) + ";}"
    ".dark, .dark .gradio-container {" + _vars(DARK, _DARK_SOFT) + "}"
    + """
/* Gradio paints the page from the computer's light/dark setting; follow the theme instead, so the switch
   recolors the whole page. --body-background-fill flips with Gradio's .dark class. */
body { background: var(--body-background-fill) !important; }
.gradio-container { max-width: 760px !important; margin: 0 auto !important; font-family: var(--sf-sans); }
footer { display: none !important; }

/* Header: name, mark and version pill */
.sf-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 2px 2px; }
.sf-brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 22px; letter-spacing: -0.02em;
  color: var(--sf-text); }
.sf-mark { width: 34px; height: 34px; border-radius: 10px; background: var(--sf-accent); display: grid; place-items: center;
  flex: none; }
.sf-mark svg { width: 18px; height: 18px; }
.sf-mark path { stroke: var(--sf-on-accent); }
.sf-pill { font-size: 12px; font-weight: 600; padding: 4px 11px; border-radius: 99px; background: var(--sf-badge-bg);
  color: var(--sf-badge-fg); white-space: nowrap; }
.sf-header-end { display: flex; align-items: center; gap: 8px; }
.sf-theme { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; cursor: pointer;
  border: 1px solid var(--sf-border); background: var(--sf-card); color: var(--sf-text); padding: 0; }
.sf-theme:hover { border-color: var(--sf-accent); }
.sf-theme:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: 2px; }
.sf-theme svg { width: 17px; height: 17px; }
.sf-theme .sf-sun, .dark .sf-theme .sf-moon { display: none; }
.dark .sf-theme .sf-sun { display: block; }
.sf-tagline { color: var(--sf-muted); font-size: 14px; margin: 2px 2px 4px; }

/* The three section cards */
.sf-card { background: var(--sf-card) !important; border: 1px solid var(--sf-border) !important;
  border-radius: 18px !important; padding: 16px !important; gap: 12px !important; }
.sf-step { font-size: 11px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--sf-muted);
  padding: 0 2px; }

/* Inside a card, Gradio's own boxes lose their frames so the card reads as one surface */
.sf-card > .block, .sf-card > .form, .sf-card > .row > .block, .sf-card .form { border: none !important;
  box-shadow: none !important; background: transparent !important; }
.sf-card .sf-drop { border: 1.5px dashed var(--sf-strong-border) !important; border-radius: 14px !important;
  background: var(--sf-row) !important; }
.sf-card .sf-boxed { border: 1px solid var(--sf-border) !important; border-radius: 14px !important;
  background: var(--sf-card) !important; }

.sf-card code { background: var(--sf-row) !important; color: var(--sf-text) !important; border-radius: 6px;
  padding: 1px 5px; overflow-wrap: anywhere; }

/* Review summary */
.sf-summary { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; padding: 2px; }
.sf-count { font-size: 30px; font-weight: 800; letter-spacing: -0.02em; line-height: 1; color: var(--sf-text); }
.sf-count small { font-size: 14px; font-weight: 600; letter-spacing: 0; color: var(--sf-muted); }
.sf-meta { color: var(--sf-muted); font-size: 13px; width: 100%; }
.sf-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; padding: 4px 10px;
  border-radius: 99px; background: var(--sf-badge-bg); color: var(--sf-badge-fg); }
.sf-badge.sf-badge-quick { background: var(--sf-tag-bg); color: var(--sf-tag-fg); }
.sf-empty { font-size: 20px; font-weight: 800; color: var(--sf-text); }

/* Scene rows are styled by scene_list.py */

/* Filter choice as one row of buttons */
.sf-modes .wrap { display: grid !important; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 4px !important;
  padding: 4px; border-radius: 12px; background: var(--sf-row); }
.sf-modes label { justify-content: center; border-radius: 9px !important; font-weight: 600; text-align: center; }
@media (max-width: 520px) { .sf-modes .wrap { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
"""
)
