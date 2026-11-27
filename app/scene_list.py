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
    <div class="sf-item">
      <div class="sf-row">
        <label class="sf-pick">
          <input type="checkbox" value="${r.index}" ${(value || []).map(Number).includes(r.index) ? 'checked' : ''}>
          ${r.thumb ? `<img class="sf-thumb" src="${r.thumb}" alt="">` : ''}
          <span class="sf-row-main">
            <span class="sf-time">${r.time}</span>
            <span class="sf-tag">${r.tag}</span>
          </span>
        </label>
        <span class="sf-conf"><b>${r.confidence}%</b><span class="sf-meter"><i style="width:${r.confidence}%"></i></span></span>
        ${r.thumb_light ? `<button type="button" class="sf-closer" data-closer="${r.index}">Look closer</button>` : ''}
      </div>
      ${r.thumb_light ? `
        <div class="sf-view" data-view="${r.index}" hidden>
          <img src="${r.thumb_light}" alt="Lightly blurred preview of this scene">
          <button type="button" class="sf-closer" data-blur="${r.index}">Blur again</button>
        </div>` : ''}
    </div>`).join('')}
</div>
"""

# Colors come from the --sf-* variables in theme.CSS, so the list follows light and dark mode with the rest.
_CSS = """
.sf-list { display: grid; gap: 6px; }
.sf-list-label { font-size: 14px; color: var(--sf-text); margin: 0 2px 2px; }
.sf-item { display: grid; gap: 6px; }
.sf-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 12px; padding: 8px 12px; border-radius: 11px;
  background: var(--sf-row); }
.sf-row:has(input:checked) { background: var(--sf-badge-bg); }
.sf-pick { display: flex; align-items: center; gap: 12px; flex: 1 1 220px; min-width: 0; cursor: pointer; }
.sf-pick input { width: 18px; height: 18px; margin: 0; flex: none; accent-color: var(--sf-accent); cursor: pointer; }
.sf-thumb { width: 52px; height: 52px; border-radius: 8px; object-fit: cover; flex: none; }
.sf-row-main { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; min-width: 0; }
.sf-time { font-family: var(--sf-mono); font-size: 13px; font-variant-numeric: tabular-nums; color: var(--sf-text); }
.sf-tag { font-size: 12px; font-weight: 700; padding: 2px 9px; border-radius: 99px; background: var(--sf-tag-bg);
  color: var(--sf-tag-fg); }
.sf-conf { display: grid; justify-items: end; gap: 4px; font-size: 12px; color: var(--sf-muted);
  font-variant-numeric: tabular-nums; }
.sf-conf b { font-weight: 700; }
.sf-meter { width: 56px; height: 5px; border-radius: 99px; background: var(--sf-border); overflow: hidden; }
.sf-meter i { display: block; height: 100%; border-radius: 99px; background: var(--sf-accent); }
.sf-closer { font: inherit; font-size: 12.5px; font-weight: 700; padding: 6px 12px; border-radius: 9px; cursor: pointer;
  border: 1px solid var(--sf-border); background: var(--sf-card); color: var(--sf-accent); }
.sf-closer:hover { border-color: var(--sf-accent); }
.sf-closer:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: 2px; }
.sf-view { display: grid; justify-items: start; gap: 8px; padding: 10px 12px 12px; margin-left: 30px;
  border-radius: 11px; background: var(--sf-row); }
.sf-view[hidden] { display: none; }
.sf-view img { width: min(320px, 100%); aspect-ratio: 1; border-radius: 10px; object-fit: cover; }
"""

# One listener on the component itself, so it keeps working each time the rows are redrawn. Ticking a box
# redraws the rows, so the scenes being looked at are remembered and reopened afterwards.
_JS = """
const open = new Set();
const show = (id, on) => {
  const view = element.querySelector(`[data-view="${id}"]`);
  const btn = element.querySelector(`[data-closer="${id}"]`);
  if (view) view.hidden = !on;
  if (btn) btn.hidden = on;
};
element.addEventListener('click', (e) => {
  const closer = e.target.closest('[data-closer]');
  const blur = e.target.closest('[data-blur]');
  if (!closer && !blur) return;
  e.preventDefault();
  const id = (closer || blur).dataset.closer || (closer || blur).dataset.blur;
  if (closer) open.add(id); else open.delete(id);
  show(id, !!closer);
});
element.addEventListener('change', (e) => {
  if (!e.target.matches('input[type="checkbox"]')) return;
  props.value = Array.from(element.querySelectorAll('input[type="checkbox"]:checked')).map(cb => Number(cb.value));
  requestAnimationFrame(() => open.forEach(id => show(id, true)));
});
watch('rows', () => open.clear());
"""


class SceneList(gr.HTML):
    def __init__(self, rows: list[dict] | None = None, *, value: list[int] | None = None, label: str | None = None,
                 **kwargs):
        super().__init__(value=value or [], html_template=_TEMPLATE, css_template=_CSS, js_on_load=_JS,
                         rows=rows or [], label=label, **kwargs)

    def api_info(self):
        return {"items": {"type": "integer"}, "title": "Ticked scenes", "type": "array"}
