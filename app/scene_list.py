"""The flagged-scene list in the Review section: one row per scene with a tick box, its time range, a pastel tag
naming what was detected, and a confidence bar.

Built on Gradio 6's HTML component, because a normal tick-box group can only show plain text. Its value is the
list of ticked scene numbers, exactly what a gr.CheckboxGroup of scene numbers would give, so review.apply_picks
reads it unchanged.
"""
from __future__ import annotations

import gradio as gr

_TEMPLATE = """
<div class="sf-list">
  ${label ? `<div class="sf-list-label">${label}</div>` : ''}
  ${(rows || []).map(r => `
    <label class="sf-row">
      <input type="checkbox" value="${r.index}" ${(value || []).map(Number).includes(r.index) ? 'checked' : ''}>
      <span class="sf-row-main">
        <span class="sf-time">${r.time}</span>
        <span class="sf-tag">${r.tag}</span>
      </span>
      <span class="sf-conf"><b>${r.confidence}%</b><span class="sf-meter"><i style="width:${r.confidence}%"></i></span></span>
    </label>`).join('')}
</div>
"""

# Colors come from the --sf-* variables in theme.CSS, so the list follows light and dark mode with the rest.
_CSS = """
.sf-list { display: grid; gap: 6px; }
.sf-list-label { font-size: 14px; color: var(--sf-text); margin: 0 2px 2px; }
.sf-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 12px;
  padding: 10px 12px; border-radius: 11px; background: var(--sf-row); cursor: pointer; }
.sf-row:has(input:checked) { background: var(--sf-badge-bg); }
.sf-row input { width: 18px; height: 18px; margin: 0; accent-color: var(--sf-accent); cursor: pointer; }
.sf-row-main { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; min-width: 0; }
.sf-time { font-family: var(--sf-mono); font-size: 13px; font-variant-numeric: tabular-nums; color: var(--sf-text); }
.sf-tag { font-size: 12px; font-weight: 700; padding: 2px 9px; border-radius: 99px; background: var(--sf-tag-bg);
  color: var(--sf-tag-fg); }
.sf-conf { display: grid; justify-items: end; gap: 4px; font-size: 12px; color: var(--sf-muted);
  font-variant-numeric: tabular-nums; }
.sf-conf b { font-weight: 700; }
.sf-meter { width: 56px; height: 5px; border-radius: 99px; background: var(--sf-border); overflow: hidden; }
.sf-meter i { display: block; height: 100%; border-radius: 99px; background: var(--sf-accent); }
"""

# One listener on the component itself, so it keeps working each time the rows are redrawn.
_JS = """
element.addEventListener('change', (e) => {
  if (!e.target.matches('input[type="checkbox"]')) return;
  props.value = Array.from(element.querySelectorAll('input[type="checkbox"]:checked')).map(cb => Number(cb.value));
});
"""


class SceneList(gr.HTML):
    def __init__(self, rows: list[dict] | None = None, *, value: list[int] | None = None, label: str | None = None,
                 **kwargs):
        super().__init__(value=value or [], html_template=_TEMPLATE, css_template=_CSS, js_on_load=_JS,
                         rows=rows or [], label=label, **kwargs)

    def api_info(self):
        return {"items": {"type": "integer"}, "title": "Ticked scenes", "type": "array"}
