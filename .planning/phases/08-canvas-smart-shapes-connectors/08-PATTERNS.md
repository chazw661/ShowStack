# Phase 8: Canvas, Smart Shapes & Connectors — Pattern Map

**Mapped:** 2026-05-20
**Files analyzed:** 6 to be modified + 2 to be created (~8 total deliverables)
**Analogs found:** 8 / 8 (100% coverage — multitrack module is a near-perfect role-match across the board)

---

## File Classification

| New/Modified File | New/Mod | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|---------|------|-----------|----------------|---------------|
| `planner/static/planner/js/signal_flow_editor.js` | **MODIFY** (extend the IIFE) | static JS controller | event-driven (canvas events + drag-drop + fetch) | `planner/static/planner/js/multitrack_editor.js` | exact (modal + drag + JSON POST + admin-DOM `!important` rules) |
| `planner/static/planner/css/signal_flow.css` | **NEW** | static CSS | n/a (rendering) | `planner/static/planner/css/multitrack.css` | exact (modal overlay + tabs + filter + list + toast; same dark-admin theme) |
| `planner/templates/planner/signal_flow/editor.html` | **MODIFY** (toolbar children, sidebar, inspector, modal include) | template (HTML shell) | request-response (rendered once; JS hydrates) | `planner/templates/planner/multitrack/editor.html` (the multitrack track editor page; sibling of `_picker_modal.html`) + `planner/templates/planner/signal_flow/list.html` (existing CSRF + cookie pattern) | role-match (multitrack editor has the same role; current SFD list.html ships the `getCsrfToken` cookie helper we copy in) |
| `planner/templates/planner/signal_flow/_equipment_picker_modal.html` | **NEW** | template partial (HTML) | request-response | `planner/templates/planner/multitrack/_picker_modal.html` | exact (modal partial with tab nav, filter, scrollable list, footer; included once from the editor template) |
| `planner/views.py` — fill `signal_flow_autocomplete` view body | **MODIFY** (replace stub) | view (Django HTTP) | request-response (GET → JSON) | `planner/views.py` lines 6329–6343 (`_get_track_for_request` IDOR helper) + `planner/views.py` lines 6652–6727 (`multitrack_add_tracks` for the JSON-POST IDOR + per-source-type model dispatch pattern) | exact (IDOR pattern + multi-model dispatch table both already in `multitrack_add_tracks`) |
| `planner/views.py` — fill `signal_flow_autosave` view body | **MODIFY** (replace stub) | view (Django HTTP) | request-response (POST → JSON) | `planner/views.py` lines 6346–6500 (`multitrack_reorder`) + lines 6675–6740 (`multitrack_add_tracks` validation block) | exact (viewer-block + project-scoped IDOR + JSON body parse + structured 4xx/5xx errors) |
| `planner/urls.py` | **NO CHANGE** (URLs already exist from Phase 7) | route | request-response | `planner/urls.py` lines 335–343 | n/a (URLs already in place; Phase 8 only fills the view bodies) |
| `planner/models.py` | **NO CHANGE** (no new migrations) | model | n/a | n/a | n/a (`SignalFlowDiagram` already has `canvas_state` / `viewport` / `version` JSONField + IntegerField from Phase 7 migration `0158`) |

**Key insight:** the multitrack module is a near-perfect analog for everything except the JointJS-specific canvas code. There is no in-repo analog for the JointJS layer itself — that work cites the project's own RESEARCH.md §1–20 patterns instead (flagged in *No Analog Found* below).

---

## Pattern Assignments

### `planner/static/planner/js/signal_flow_editor.js` (static JS controller, event-driven)

**Analog:** `planner/static/planner/js/multitrack_editor.js`

**Stub state to preserve** (current file at `planner/static/planner/js/signal_flow_editor.js`):
- IIFE wrapper `(function () { 'use strict'; … })()` — Phase 8 extends this IIFE; no new file
- `var container = document.getElementById('sfd-container');` early-return guard
- `dataset.diagramId / stateUrl / autosaveUrl` reads
- `joint` global check
- `console.log('[SFD] JointJS ready — version ...')` — keep or remove, planner's call

**IIFE wrapper + helpers pattern** (lines 23–62 of `multitrack_editor.js`):
```javascript
(function () {
  'use strict';

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function csrfToken() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      credentials: 'same-origin',
      body: JSON.stringify(body || {}),
    }).then(function (r) {
      return r.json().then(function (data) { return { status: r.status, data: data }; });
    });
  }

  function getJSON(url) {
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); });
  }

  // Toast — minimal passive notification.
  function showToast(message, level) {
    const t = document.createElement('div');
    t.className = 'mts-toast mts-toast--' + (level || 'info');
    t.textContent = message;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add('mts-toast--hide'); }, 3000);
    setTimeout(function () { t.remove(); }, 3500);
  }
```
Copy verbatim — adapt `mts-toast` → `sfd-toast` to match the new CSS namespace. The `csrfToken()` form (reading hidden `<input name=csrfmiddlewaretoken>`) is preferred over the cookie-parse form because `editor.html` already renders `{% csrf_token %}` inside a hidden form (Phase 7-locked line 43).

**Alternative CSRF helper** (already in `planner/templates/planner/signal_flow/list.html` lines 74–78):
```javascript
function getCsrfToken() {
  return document.cookie.split('; ')
    .find(function (row) { return row.startsWith('csrftoken='); })
    .split('=')[1];
}
```
Use this only if planner decides to drop the hidden form. The hidden-input form is safer (no cookie parsing edge cases).

**Modal open/close pattern with `!important` style writes** (lines 204–221):
```javascript
window.mtsOpenPicker = function (tab) {
  renderPickerLists();
  window.mtsSwitchTab(tab || 'inputs');
  const overlay = $('#mts-picker-overlay');
  if (overlay) overlay.style.setProperty('display', 'flex', 'important');
  setTimeout(function () { const f = $('.mts-filter-input'); if (f) f.focus(); }, 100);
};

window.mtsClosePicker = function () {
  const overlay = $('#mts-picker-overlay');
  if (overlay) overlay.style.setProperty('display', 'none', 'important');
  // Reset selection state on close
  pickerSelections = { inputs: new Set(), aux: new Set(), matrix: new Set(), stereo: new Set() };
  pickerManualQueue = [];
  …
};
```
**Critical:** every DOM style write uses `el.style.setProperty(prop, value, 'important')`. This is CLAUDE.md's hard rule for admin-template DOM. JointJS-managed SVG inside `#sfd-paper` is exempt (its own SVG namespace).

**Search filter / typeahead pattern** (lines 235–246):
```javascript
window.mtsFilterPicker = function (query) {
  const q = (query || '').toLowerCase().trim();
  if (pickerActiveTab === 'manual') return;
  const list = $('[data-pick-list="' + pickerActiveTab + '"]');
  if (!list) return;
  $$('.mts-pick-row', list).forEach(function (row) {
    const num = (row.querySelector('.mts-pick-num') || {}).textContent || '';
    const name = (row.querySelector('.mts-pick-name') || {}).textContent || '';
    const haystack = (num + ' ' + name).toLowerCase();
    row.style.setProperty('display', (q === '' || haystack.indexOf(q) >= 0) ? 'flex' : 'none', 'important');
  });
};
```
For Phase 8: change to a debounced server-side fetch (per RESEARCH.md §17/18 — 200ms debounce, `?type=X&q=…`) because equipment lists can be larger than what multitrack tabs hold. Same row-rendering shape — `<row>` containing `<num>`/`<name>` spans, `textContent` (never `innerHTML`) for XSS-safety.

**XSS-safe row build** (lines 148–176) — use `document.createElement` + `textContent`, never `innerHTML`:
```javascript
channels.forEach(function (ch) {
  const row = document.createElement('label');
  row.className = 'mts-pick-row';
  row.dataset.sourceType = tab.replace(/s$/, '');
  row.dataset.sourceId = ch.id;

  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'mts-pick-checkbox';
  cb.checked = pickerSelections[tab].has(ch.id);
  cb.addEventListener('change', function () { /* … */ });

  const num = document.createElement('span');
  num.className = 'mts-pick-num';
  num.textContent = ch.channel_number || '';

  const lbl = document.createElement('span');
  lbl.className = 'mts-pick-name';
  lbl.textContent = ch.label;   // textContent — XSS-safe

  row.appendChild(cb);
  row.appendChild(num);
  row.appendChild(lbl);
  list.appendChild(row);
});
```
Phase 8: drop the checkbox (single-pick), keep primary text + secondary detail line shape.

**POST round-trip with status-code branching** (lines 86–100):
```javascript
postJSON('/audiopatch/multitrack/' + sessionId + '/reorder/', { ordered_ids: ids })
  .then(function (resp) {
    if (resp.status !== 200 || !resp.data.ok) {
      showToast("Couldn't save track order. Check your connection and reload the page.", 'error');
      return;
    }
    // Optimistic UI: renumber #1..#N client-side
    $$('.mts-track-num', list).forEach(function (el, idx) {
      el.textContent = '#' + (idx + 1);
    });
  })
  .catch(function () {
    showToast("Couldn't save track order. Check your connection and reload the page.", 'error');
  });
```
For Phase 8 manual Save: identical shape — POST `graph.toJSON()` + `viewport` to `data-autosave-url`, branch on `resp.status`, update save-status text, show toast on failure (`UI-SPEC § Toast / Inline Messages`).

**Init pattern at bottom of IIFE** — `multitrack_editor.js` ends with explicit init calls (search the file for `initSortable();` / `init...()` lines). For Phase 8, init order matters (RESEARCH.md §1, CRITICAL): register `joint.shapes.showstack.*` first → instantiate Graph with `cellNamespace` → instantiate Paper with `cellViewNamespace` → THEN call `graph.fromJSON(state, { undoable: false })`.

**Critical Phase 8-specific call-outs that have NO multitrack analog** (cite RESEARCH.md):
- Custom undo stack (~120 lines, RESEARCH.md §"Custom Undo-Stack Pattern", lines 41–137 of RESEARCH.md) — must wire BEFORE `fromJSON()`
- JointJS shape definitions (RESEARCH.md §1) — 5 classes in `joint.shapes.showstack` namespace
- Paper init with `cellNamespace` + `cellViewNamespace` + finite 4000×3000 bounds (RESEARCH.md §1 closing block)
- `paper.clientToLocalPoint()` for drag-drop coordinate translation (PITFALLS.md §2 + RESEARCH.md §3)
- `linkTools.Vertices` attach on `link:pointerclick` (RESEARCH.md §15)
- Custom rubber-band selection using `paper.findViewsInArea()` (RESEARCH.md §8)

---

### `planner/static/planner/css/signal_flow.css` (NEW static CSS)

**Analog:** `planner/static/planner/css/multitrack.css` (lines 568–795 for picker modal; lines 1081–1111 for toast)

**Picker modal CSS** (multitrack.css lines 568–757) — copy verbatim with namespace swap (`mts-*` → `sfd-*`):
```css
.sfd-picker-overlay {
  position: fixed !important;
  inset: 0 !important;
  background-color: rgba(0, 0, 0, 0.6) !important;
  z-index: 99999 !important;
  align-items: center !important;
  justify-content: center !important;
  padding: 16px !important;
}

.sfd-picker-panel {
  width: 480px !important;       /* UI-SPEC § Equipment Picker Modal max-width 480px */
  max-width: 95vw !important;
  max-height: 85vh !important;
  background-color: #1a1a1a !important;
  border: 1px solid #333 !important;
  border-radius: 10px !important;
  display: flex !important;
  flex-direction: column !important;
  overflow: hidden !important;
}

.sfd-picker-header { /* … 590–596 */ }
.sfd-picker-title  { /* … 598–605 */ }
.sfd-picker-close  { /* … 607–621 */ }
.sfd-picker-filter { /* … 651–671 */ }
.sfd-filter-input  { /* … 656–671 */ }
.sfd-pick-list     { /* … 704–708 */ }
.sfd-pick-row      { /* … 710–727 */ }
.sfd-pick-num      { /* … 737–744 */ }
.sfd-pick-name     { /* … 746–750 */ }
.sfd-pick-empty    { /* … 752–757 */ }
```

**Toast CSS** (multitrack.css lines 1081–1111) — copy verbatim:
```css
.sfd-toast {
  position: fixed !important;
  bottom: 24px !important;
  right: 24px !important;
  padding: 12px 16px !important;
  background-color: #1e1e3a !important;
  border: 1px solid #2a2a4a !important;
  border-radius: 8px !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4) !important;
  color: #e0e0e0 !important;
  font-size: 14px !important;
  z-index: 100000 !important;
  transition: opacity 300ms !important;
  max-width: 480px !important;
}

.sfd-toast--success { border-left: 3px solid #00ff88 !important; }
.sfd-toast--error   { border-left: 3px solid #dc3545 !important; }
.sfd-toast--info    { border-left: 3px solid #4a9eff !important; }
.sfd-toast--hide    { opacity: 0 !important; }
```

**Phase 8-specific CSS that has NO multitrack analog** (build from UI-SPEC § Component Specs):
- `#sfd-sidebar` (left, 64px fixed, 5 stacked tiles)
- `#sfd-inspector` (right, 280px, auto-show, slide-in transition)
- Sidebar tile `.sfd-tile` + hover state + `draggable` cursor (`grab` → `grabbing`)
- Toolbar button groups + dividers + save-status text
- JointJS port hover-reveal (`.joint-paper .joint-element:hover .joint-port circle { opacity: 1 !important; }` — see RESEARCH.md §2)
- Snap-toggle active state (`#0d9488` background)

**Critical:** every selector must use `!important` if the rule writes a value that conflicts with `django-admin-interface` defaults. JointJS SVG inside `#sfd-paper` is in its own namespace — JointJS-set inline styles win there without `!important`.

**Load:** add a `<link rel="stylesheet" href="{% static 'planner/css/signal_flow.css' %}">` to `editor.html`'s `{% block extrahead %}` (after the inline `<style>` block currently there, OR move the inline block into the new file).

---

### `planner/templates/planner/signal_flow/editor.html` (MODIFY template, request-response)

**Analog:** `planner/templates/planner/multitrack/editor.html` (for the editor-shell-plus-modal pattern) + `planner/templates/planner/signal_flow/list.html` (for the in-repo SFD CSRF helper + AJAX-button pattern)

**Phase 7-locked elements** (line numbers from current `editor.html`):
```django
{# Phase 7 lock — DO NOT remove or rename: #}
- Line 1: {% extends "admin/base_site.html" %}
- Line 2: {% load static %}
- Line 4: {% block title %} (keep)
- Line 22-28: <div id="sfd-container" data-diagram-id=... data-state-url=... data-autosave-url=... data-autocomplete-url=... data-export-png-url=...>
- Line 30: <div id="sfd-toolbar">
- Line 31: <a class="sfd-back-link" href="{% url 'planner:signal_flow_list' %}">&larr; Diagrams</a>
- Line 32: <h1>{{ diagram.name }}</h1>
- Line 36: <div id="sfd-canvas-container">
- Line 38: <div id="sfd-paper"></div>   ← JointJS Paper mounts here
- Line 43: <form style="display:none">{% csrf_token %}</form>
- Lines 47-49: vendor JS load order (joint → html-to-image → signal_flow_editor.js deferred)
```

**Phase 8 additions (sibling pattern from `signal_flow/list.html` block extra-head + content):**

1. **Replace the placeholder span** (line 33: `(Phase 8 will wire the canvas; this is the shell.)`) with the actual toolbar button groups per `UI-SPEC § #sfd-toolbar`:
```django
{# Phase 8: toolbar button groups #}
<div class="sfd-toolbar-spacer"></div>
<div class="sfd-btn-group" data-group="zoom">
  <button type="button" id="sfd-zoom-out" aria-label="Zoom out (−)">−</button>
  <span id="sfd-zoom-level">100%</span>
  <button type="button" id="sfd-zoom-in" aria-label="Zoom in (+)">+</button>
  <button type="button" id="sfd-zoom-fit" aria-label="Zoom to fit">⊡</button>
</div>
<span class="sfd-toolbar-divider"></span>
<div class="sfd-btn-group" data-group="mode">
  <button type="button" id="sfd-snap-toggle" aria-label="Snap to grid: on">⊞</button>
</div>
<span class="sfd-toolbar-divider"></span>
<div class="sfd-btn-group" data-group="history">
  <button type="button" id="sfd-undo" aria-label="Undo (⌘Z)" disabled>↶</button>
  <button type="button" id="sfd-redo" aria-label="Redo (⌘⇧Z)" disabled>↷</button>
</div>
<div class="sfd-toolbar-spacer"></div>
<button type="button" id="sfd-save" aria-label="Save diagram">Save</button>
<span id="sfd-save-status">All changes saved.</span>
```

2. **Add sidebar + inspector siblings to `#sfd-paper` inside `#sfd-canvas-container`:**
```django
<div id="sfd-canvas-container">
  <aside id="sfd-sidebar">
    <button class="sfd-tile" draggable="true" data-shape-type="Console">
      {# inline SVG mixer icon, 20×20 #}
      <span class="sfd-tile-label">Console</span>
    </button>
    <button class="sfd-tile" draggable="true" data-shape-type="Device">…</button>
    <button class="sfd-tile" draggable="true" data-shape-type="SpeakerArray">…</button>
    <button class="sfd-tile" draggable="true" data-shape-type="CommBeltPack">…</button>
    <button class="sfd-tile" draggable="true" data-shape-type="Generic">…</button>
  </aside>
  <div id="sfd-paper"></div>
  <aside id="sfd-inspector" hidden>
    <header class="sfd-inspector-header">
      <h3>Connector</h3>
      <button type="button" id="sfd-inspector-close" aria-label="Close inspector">×</button>
    </header>
    <div class="sfd-field">
      <label for="sfd-signal-type">Signal type</label>
      <select id="sfd-signal-type">
        <option value="analog">Analog</option>
        <option value="AES">AES</option>
        <option value="Dante">Dante</option>
        <option value="MADI">MADI</option>
        <option value="intercom">Intercom</option>
      </select>
    </div>
    <div class="sfd-field">
      <label>Direction</label>
      <div class="sfd-segmented">
        <button type="button" id="sfd-dir-forward" data-active="true">Source → Target</button>
        <button type="button" id="sfd-dir-bidir">Bidirectional</button>
      </div>
    </div>
    <div class="sfd-field">
      <label for="sfd-circuit-label">Circuit label</label>
      <input type="text" id="sfd-circuit-label" placeholder="e.g. CKT-01">
      <p class="sfd-field-help">Renders along the connector line.</p>
    </div>
  </aside>
</div>
```

3. **Include the equipment picker modal partial** (after `<form>{% csrf_token %}</form>`):
```django
{% include "planner/signal_flow/_equipment_picker_modal.html" %}
```

4. **Add the new CSS link** (in `{% block extrahead %}` after the inline `<style>` block, or move all CSS to the new file):
```django
<link rel="stylesheet" href="{% static 'planner/css/signal_flow.css' %}">
```

**JS loading order (Phase 7-locked — do NOT change):**
- Line 47: `<script src="{% static 'planner/js/vendor/joint.min.js' %}"></script>` (NOT deferred)
- Line 48: `<script src="{% static 'planner/js/vendor/html-to-image.min.js' %}"></script>` (Phase 10 uses this)
- Line 49: `<script src="{% static 'planner/js/signal_flow_editor.js' %}" defer></script>`

---

### `planner/templates/planner/signal_flow/_equipment_picker_modal.html` (NEW template partial)

**Analog:** `planner/templates/planner/multitrack/_picker_modal.html` (lines 1–80)

**Modal shell pattern** (lines 1–7 of `_picker_modal.html`):
```django
<div id="sfd-picker-overlay" class="sfd-picker-overlay" style="display:none">
  <div class="sfd-picker-panel" role="dialog" aria-labelledby="sfd-picker-title">
    <header class="sfd-picker-header">
      <h2 id="sfd-picker-title" class="sfd-picker-title">Pick a <span id="sfd-picker-type">Console</span></h2>
      <button type="button" class="sfd-picker-close" aria-label="Cancel"
              onclick="sfdClosePicker()">&#x2715;</button>
    </header>

    <div class="sfd-picker-filter">
      <input type="text" id="sfd-picker-search" class="sfd-filter-input"
             placeholder="Search by name, model, serial…"
             oninput="sfdFilterPicker(this.value)"
             aria-label="Search equipment" autofocus>
    </div>

    <div class="sfd-tab-panel">
      <ul id="sfd-picker-results" class="sfd-pick-list" role="listbox">
        {# rendered by JS from the autocomplete fetch #}
      </ul>
      <p id="sfd-picker-empty" class="sfd-pick-empty" hidden>
        No <span id="sfd-picker-empty-type">Console</span> records in this project.
      </p>
    </div>

    <footer class="sfd-picker-footer">
      <button type="button" id="sfd-picker-cancel" onclick="sfdClosePicker()">Cancel</button>
    </footer>
  </div>
</div>
```

**Critical UI-SPEC § Copywriting differences from multitrack:**
- Title: `"Pick a {Type}"` — `{Type}` is filled by JS: "Console" / "Device" / "Speaker Array" / "Beltpack"
- Single-select (click result row to assign), NOT checkboxes — drop the `.mts-pick-checkbox`
- Empty state copy: `"No {Type} records in this project — add equipment in Admin"` with admin URL (UI-SPEC § Equipment Picker Modal)
- Cancel removes the placeholder shape (`node.remove({ undoable: false })`) per CONTEXT.md D-10

---

### `planner/views.py` — fill `signal_flow_autocomplete` body (MODIFY view, request-response)

**Analog 1 — IDOR-safe lookup helper** (`planner/views.py` lines 6329–6343):
```python
def _get_track_for_request(request, track_id):
    """Return the MultitrackTrack iff its session.project == request.current_project.

    IDOR-safe lookup. Returns None when the track doesn't exist or belongs to
    a different project.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return None
    return (
        MultitrackTrack.objects
        .filter(id=track_id, session__project=current_project)
        .select_related('session')
        .first()
    )
```
Already adapted as `_get_diagram_for_request` (`planner/views.py` lines 7373–7386) — Phase 8 doesn't need a new helper; reuse this one when needed.

**Analog 2 — Multi-model dispatch pattern with project-scoped querysets** (`planner/views.py` lines 6711–6726, inside `multitrack_add_tracks`):
```python
valid_input_ids = set(
    ConsoleInput.objects.filter(console=console)
    .values_list('id', flat=True)
) & set(selections.get('inputs', []) or [])
valid_aux_ids = set(
    ConsoleAuxOutput.objects.filter(console=console)
    .values_list('id', flat=True)
) & set(selections.get('aux', []) or [])
valid_matrix_ids = set( ... )
valid_stereo_ids = set( ... )
```
Phase 8 adapts this into a `MODEL_MAP` dispatch table per shape type — see RESEARCH.md §17 for the full skeleton:
```python
MODEL_MAP = {
    'console':      (Console,      [<search fields>], lambda c: f"…secondary detail…"),
    'device':       (Device,       [<search fields>], lambda d: f"…"),
    'speakerarray': (SpeakerArray, [<search fields>], lambda s: f"…"),
    'commbeltpack': (CommBeltPack, [<search fields>], lambda b: f"…"),
}
```

**Verified equipment-model field constraints** (from `planner/models.py` reads — RESEARCH.md §17 explicitly flags these need verification before lock-in):

| Model | `project` FK? | Verified searchable fields | Notes |
|-------|---------------|----------------------------|-------|
| `Console` (line 871) | `models.ForeignKey('Project', …, null=True, blank=True)` — yes but nullable | `name` (always). Secondary candidates: NONE of `dsp_mixer` / `channel_count` exist on the model. Console only has `name`, `is_template`, `primary_ip_address`, `secondary_ip_address`. **The RESEARCH.md §17 / CONTEXT D-11 secondary-field guesses were wrong for Console.** | Planner: fall back to `name` only for Console, or render secondary from `is_template` + IP. |
| `Device` (line 1493) | `models.ForeignKey('Project', on_delete=models.CASCADE)` — yes | `name` always. Secondary candidates: `input_count`, `output_count`. **No `model` field, no `serial` field** on the current Device model. | Planner: secondary detail = `"{input_count} in × {output_count} out"` or fall back to `name` only. |
| `SpeakerArray` (line 3722) | **NO direct `project` FK.** Connected via `prediction = ForeignKey(SoundvisionPrediction, …)` — must filter `SpeakerArray.objects.filter(prediction__project=current_project)`. | `source_name`, `array_base_name`. NO `name` field. NO `cabinet_count` field directly (but `prediction.cabinet_count` may exist; verify). | **IDOR query is different for SpeakerArray** — use `prediction__project=...`, not `project=...`. This is the #1 thing the planner must catch. |
| `CommBeltPack` (line 2646) | `models.ForeignKey('Project', on_delete=models.CASCADE)` — yes | `bp_number` (IntegerField), `manufacturer`, `system_type`. NO `name` CharField (`name` is a ForeignKey to `CommCrewName`). NO `beltpack_id` field. | Planner: search on `bp_number` + `manufacturer__icontains`. Display label = `f"BP #{bp.bp_number} — {bp.get_manufacturer_display()}"`. |

**This nuance MUST be reflected in the autocomplete view implementation.** The naive `Model.objects.filter(project=current_project)` works for Console / Device / CommBeltPack, FAILS for SpeakerArray.

**Logger pattern** (`planner/views.py` line 7359):
```python
_signal_flow_logger = logging.getLogger(__name__)
```
Already in place — reuse for any caught exceptions in the autocomplete view body.

**`@staff_member_required` decorator** is already on the stub (line 7558) — keep it for the GET autocomplete. Mutations use `@login_required + @require_POST` (mirrors `signal_flow_create` lines 7404–7405).

**ContentType lookup pattern** (RESEARCH.md §17 lines 642–655):
```python
from django.contrib.contenttypes.models import ContentType
ct = ContentType.objects.get_for_model(Model)
results = [{
    'id': obj.pk,
    'contentTypeId': ct.pk,
    'name': obj.name,
    'detail': detail_fn(obj),
} for obj in qs]
return JsonResponse({'results': results})
```

**CRITICAL DESIGN CONFLICT TO FLAG TO PLANNER:**
The Phase 7 stub view at `planner/views.py` line 7558-7564 is currently named **`signal_flow_autocomplete`** and the docstring says *"GET stub for circuit-label autocomplete (Phase 10 fills)"*. But RESEARCH.md §17 and `editor.html`'s `data-autocomplete-url` are using this same URL for the Phase 8 **equipment picker autocomplete**. These are two different features (Phase 8 = equipment list per shape type; Phase 10 = circuit-label string completion). Planner decides:
- **Option A:** Repurpose the existing URL `signal_flow_autocomplete` for the equipment picker now (Phase 8); add a separate URL `signal_flow_label_autocomplete` in Phase 10. Cleanest semantically.
- **Option B:** Branch on `?kind=equipment` vs `?kind=label` inside the existing view. Keeps URL count down but couples two unrelated features.
- **Option C:** Add a new URL `signal_flow_equipment_pick` in Phase 8 alongside the existing `signal_flow_autocomplete` (which stays a stub for Phase 10). Requires a `urls.py` edit (Phase 8 scope creep).

RESEARCH.md §17 closing note ("No new URL needed") implicitly chose Option A or B without flagging the docstring conflict. **Plan should pick explicitly.** Recommended: Option A — repurpose `signal_flow_autocomplete` for the equipment picker (Phase 8), rename Phase 10's label autocomplete to a new URL.

---

### `planner/views.py` — fill `signal_flow_autosave` body (MODIFY view, request-response)

**Analog 1 — Mutation endpoint with viewer block + IDOR + JSON body parse + structured errors** (`planner/views.py` lines 6346–6500, `multitrack_reorder`):
```python
@login_required
@require_POST
def multitrack_reorder(request, session_id):
    """POST: reassign dense track_number 1..N from a posted ordered list (TRK-05)."""
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        session = MultitrackSession.objects.filter(
            id=session_id, project=current_project
        ).first()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        data = json.loads(request.body or '{}')
        # ... validation ...
        # ... mutation ...
        return JsonResponse({'ok': True, ...})
    except Exception:
        _multitrack_logger.exception('multitrack_reorder failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```
Copy verbatim into `signal_flow_autosave` — swap `multitrack_*` → `_signal_flow_*` for helpers and logger.

**Phase 8 simplified autosave body** (per RESEARCH.md §19):
```python
@login_required
@require_POST
def signal_flow_autosave(request, diagram_id):
    """POST: save canvas_state + viewport. Phase 8 simplified — no optimistic locking yet."""
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        diagram = _get_diagram_for_request(request, diagram_id)
        if not diagram:
            return JsonResponse({'error': 'Not found'}, status=404)

        payload = json.loads(request.body or '{}')
        canvas_state = payload.get('canvas_state', {})

        # Walk canvas JSON, validate equipment refs (PITFALLS.md §4 — mandatory IDOR baseline)
        for cell in canvas_state.get('cells', []):
            prop = cell.get('showstack') or {}
            ct_id = prop.get('contentTypeId')
            obj_id = prop.get('objectId')
            if ct_id and obj_id:
                ct = ContentType.objects.filter(id=ct_id).first()
                if not ct:
                    return JsonResponse({'error': f'Unknown content type {ct_id}'}, status=422)
                Model = ct.model_class()
                # IDOR check — special-case SpeakerArray (no direct project FK)
                if Model.__name__ == 'SpeakerArray':
                    exists = Model.objects.filter(id=obj_id, prediction__project=request.current_project).exists()
                elif hasattr(Model, 'project'):
                    exists = Model.objects.filter(id=obj_id, project=request.current_project).exists()
                else:
                    return JsonResponse({'error': f'Type {ct.model} has no project scope'}, status=422)
                if not exists:
                    return JsonResponse({'error': 'Equipment reference out of project'}, status=422)

        diagram.canvas_state = canvas_state
        diagram.viewport = payload.get('viewport', diagram.viewport)
        diagram.version = (diagram.version or 1) + 1
        diagram.save(update_fields=['canvas_state', 'viewport', 'version', 'updated_at'])
        return JsonResponse({'ok': True, 'version': diagram.version})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Bad JSON'}, status=400)
    except Exception:
        _signal_flow_logger.exception('signal_flow_autosave failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

**No version-conflict check in Phase 8** — Phase 9 adds the `If-Match`-style check (RESEARCH.md "Open Risks for Planner" §5). Phase 8's single-tab manual-save flow can't race itself.

**Optional: separate tiny `signal_flow_save_viewport` view for viewport-only debounced writes (RESEARCH.md §10).** RESEARCH says "planner can pick — add a tiny endpoint or use `?viewport_only=1`." Plan recommendation: branch on `request.GET.get('viewport_only')` inside `signal_flow_autosave` to keep URL count stable (no `urls.py` edit). When `viewport_only=1`: skip the `canvas_state` validation, only update `viewport`, no version bump.

---

## Shared Patterns

### IDOR-Safe Equipment Lookup (used in autocomplete + autosave)

**Source:** `planner/views.py` lines 6329–6343 (`_get_track_for_request`) + lines 7373–7386 (`_get_diagram_for_request`).

**Apply to:** Every `Model.objects.filter(...)` call inside `signal_flow_autocomplete` and `signal_flow_autosave`.

```python
# Standard case
qs = Model.objects.filter(project=request.current_project)

# SpeakerArray-only case (no direct project FK)
qs = SpeakerArray.objects.filter(prediction__project=request.current_project)
```

Project lookup: `current_project = getattr(request, 'current_project', None)` then early `return JsonResponse({'error': 'No active project'}, status=400)` if `None`. Phase 7 already establishes this in every signal_flow view (`signal_flow_create` line 7416, `signal_flow_editor` line 7447).

### Viewer-Role Guard

**Source:** `planner/views.py` lines 7362–7370 (`_signal_flow_viewer_block`).

**Apply to:** Every mutating view in this phase — `signal_flow_autosave`. NOT applied to `signal_flow_autocomplete` (GET, read-only).

```python
viewer_block = _signal_flow_viewer_block(request)
if viewer_block is not None:
    return viewer_block
```

### CSRF Token in JS

**Source 1 (hidden input — preferred):** `planner/static/planner/js/multitrack_editor.js` lines 33–47:
```javascript
function csrfToken() {
  const el = document.querySelector('[name=csrfmiddlewaretoken]');
  return el ? el.value : '';
}
```

**Source 2 (cookie — fallback):** `planner/templates/planner/signal_flow/list.html` lines 74–78. Use only if the hidden form is removed from `editor.html`.

**Apply to:** All `fetch(url, { method: 'POST' })` calls inside `signal_flow_editor.js`.

`editor.html` already renders `<form style="display:none">{% csrf_token %}</form>` at line 43 (Phase 7 locked).

### Django Admin `!important` Style Override

**Source:** `CLAUDE.md § Overriding Django admin CSS from JavaScript` + every `style.setProperty(prop, value, 'important')` call in `multitrack_editor.js` (lines 200, 208, 214, 229, 244, etc.)

**Apply to:** Every DOM style write inside `signal_flow_editor.js` that targets toolbar / sidebar / inspector / modal elements (anything inside the `admin/base_site.html` extending template).

```javascript
// ❌ Does NOT work — admin !important wins
el.style.display = 'none';

// ✅ Correct
el.style.setProperty('display', 'none', 'important');
```

**Exception:** JointJS-managed SVG inside `#sfd-paper` is in its own SVG element namespace. JointJS sets inline attributes (`stroke`, `fill`, `transform`) directly — these are not affected by admin CSS, and you do NOT need `!important` for shape attributes set via `cell.attr(...)` or `paper.scale(...)`. The rule applies to HTML DOM nodes (toolbar buttons, modal `<div>`s, sidebar tiles), not to SVG inside the paper.

### Error Handling — try/except with module logger

**Source:** `planner/views.py` lines 7415–7436 (`signal_flow_create`):
```python
try:
    # ... view body ...
    return JsonResponse({'ok': True, ...})
except Exception:
    _signal_flow_logger.exception('signal_flow_<verb> failed')
    return JsonResponse({'error': 'Server error.'}, status=500)
```
The module logger `_signal_flow_logger` is already defined at line 7359. Use `.exception()` (captures stack trace) for all caught exceptions; user gets a generic message, dev gets the trace.

### `@staff_member_required` vs `@login_required + @require_POST`

**Source:** Phase 7 PATTERNS.md "Authentication" section + actual decorator usage in `planner/views.py`:

| View | Decorator |
|------|-----------|
| `signal_flow_state` (GET, read state) | `@staff_member_required` |
| `signal_flow_autocomplete` (GET, read equipment) | `@staff_member_required` |
| `signal_flow_autosave` (POST, mutate) | `@login_required` + `@require_POST` |
| `signal_flow_export_png` (GET, Phase 10) | `@staff_member_required` |

`@login_required` is what mutating signal_flow views (create/rename/delete) already use. Pattern locked in Phase 7.

---

## Vendor JS Notes (no work in Phase 8)

| File | Status |
|------|--------|
| `planner/static/planner/js/vendor/joint.min.js` (4.2.4, MPL-2.0) | Phase 7-locked. DO NOT modify. File-level MPL-2.0 weak copyleft. |
| `planner/static/planner/js/vendor/html-to-image.min.js` (1.11.11, MIT) | Phase 7-locked. Phase 8 doesn't use it. Phase 10 will. |
| `planner/static/planner/js/vendor/Sortable.min.js` | Used by multitrack; not needed in Phase 8. |
| `THIRD_PARTY_LICENSES.txt` | Phase 7-locked at project root. No changes needed. |

---

## No Analog Found

The JointJS-specific surface area has no in-repo analog. Planner should reference RESEARCH.md sections (not the multitrack module) for these:

| Task | Reason | Cite Instead |
|------|--------|--------------|
| Custom shape class definitions (5 classes in `joint.shapes.showstack`) | No prior JointJS use in repo (Phase 7 only vendored the JS, didn't use it) | RESEARCH.md §1 ("Custom shape class definition") + PITFALLS.md §1 (cellNamespace) |
| Paper/Graph init with `cellNamespace` + `cellViewNamespace` | Same — first use in repo | RESEARCH.md §1 closing block |
| Port definitions (in / out groups, magnet types, hover reveal) | Same | RESEARCH.md §2 |
| `paper.clientToLocalPoint()` for drag-drop coords | Same | RESEARCH.md §3 + PITFALLS.md §2 |
| Pan / zoom / fit / snap-toggle | Same | RESEARCH.md §4 / §5 / §6 |
| Custom undo stack (~120 lines, because `@joint/core` has no `CommandManager`) | Same — and this is the single biggest Phase 8 risk per RESEARCH.md Critical Research Flag Resolution | RESEARCH.md §"Custom Undo-Stack Pattern" (lines 41–137) + Open Risk #1 |
| Multi-select via `paper.findViewsInArea()` + rubber-band overlay | Same | RESEARCH.md §8 |
| Keyboard handler (Delete/Backspace/Ctrl+Z/Ctrl+Shift+Z) with input-guard | Same | RESEARCH.md §7 + §9 + Open Risk #7 |
| Viewport persistence (debounced POST of `{ x, y, scale, snapEnabled }`) | Same | RESEARCH.md §10 |
| Custom Link class with orthogonal router + signal-type styling | Same | RESEARCH.md §11 + §13 |
| `validateConnection` + `linkPinning = false` + `snapLinks` | Same | RESEARCH.md §12 |
| Connector direction (markers on/off) | Same | RESEARCH.md §14 |
| `linkTools.Vertices` for midpoint waypoints | Same | RESEARCH.md §15 |
| Circuit-label rendering via `link.labels([{ … }])` | Same | RESEARCH.md §16 |
| Trapezoid SpeakerArray connector docking (`shapePerimeterConnectionPoint`) | Same | RESEARCH.md Open Risk #2 |
| Selection visual via SVG class toggling | Same | RESEARCH.md Open Risk #4 |
| Inspector show/hide on `link:pointerclick` sequencing with selection | Same | RESEARCH.md Open Risk #6 |

**Total:** ~16 JointJS-specific implementation chunks. All have research-grounded patterns in RESEARCH.md with line-level code examples — planner can reference RESEARCH.md sections directly in plan task lists.

---

## Open Risks to Carry into PLAN.md

1. **CRITICAL DESIGN CONFLICT — `signal_flow_autocomplete` URL usage.** Phase 7 stub docstring says "circuit-label autocomplete (Phase 10 fills)". Phase 8 RESEARCH.md §17 says use this same URL for the equipment picker. Plan must pick: repurpose for equipment picker now and rename label autocomplete for Phase 10 (recommended), OR branch on a `?kind=` query param.

2. **CRITICAL FIELD-NAME MISMATCH — equipment model search fields.** RESEARCH.md §17 / CONTEXT.md D-11 list secondary search fields (`dsp_mixer`, `channel_count`, `model`, `serial`, `cabinet_count`, `beltpack_id`) that **do not exist on the current models per `planner/models.py` read**. Verified field names:
   - `Console`: only `name`, `is_template`, `primary_ip_address`, `secondary_ip_address`
   - `Device`: only `name`, `input_count`, `output_count`, IP fields
   - `SpeakerArray`: `source_name`, `array_base_name` (NO `name` field!), via `prediction` (NO direct `project` FK!)
   - `CommBeltPack`: `bp_number`, `manufacturer`, `system_type` (NO `name` CharField — `name` is a FK to `CommCrewName`)

3. **SpeakerArray IDOR query is different.** Uses `prediction__project=current_project`, not `project=current_project`. Plan must explicitly handle this — naive code will silently leak across projects or return empty results.

4. **JointJS shape namespace registration order.** Per PITFALLS.md §1 + RESEARCH.md §1: register `joint.shapes.showstack` before `new joint.dia.Graph({}, { cellNamespace })`. Custom undo stack must wire BEFORE the first `graph.fromJSON()` call (RESEARCH.md §"Critical rule" line 139). Plan should sequence these in the JS init phase explicitly.

5. **Trapezoid SpeakerArray polygon docking.** RESEARCH.md Open Risk #2 flags that `<polygon>` doesn't honor `refWidth`/`refHeight` cleanly. Planner should include a smoke test; if docking is ugly, fall back to a rect+chamfer SVG (visual fidelity vs. correctness trade-off; CONTEXT.md doesn't lock this).

6. **Phase 8 simplified version bump (no conflict check).** `diagram.version = (version or 1) + 1` on every save is acceptable for Phase 8 single-tab manual saves (RESEARCH.md §19 + Open Risk #5). Phase 9 adds the optimistic-lock check.

7. **CSS namespace conflict if `signal_flow.css` is loaded on `list.html` too.** `list.html` already defines its own `.sfd-*` classes inline. New `signal_flow.css` must scope to selectors that don't collide, or only load on `editor.html`. Recommended: load `signal_flow.css` only on the editor template (it's the only page that needs the canvas / modal / inspector styles).

---

## Metadata

**Analog search scope:**
- `planner/views.py` (multitrack + signal_flow modules)
- `planner/static/planner/js/multitrack_editor.js` (798 lines — analog for JS controller)
- `planner/static/planner/css/multitrack.css` (1100+ lines — analog for modal/toast CSS)
- `planner/templates/planner/multitrack/_picker_modal.html` (analog for modal partial)
- `planner/templates/planner/signal_flow/editor.html` (Phase 7-locked shell)
- `planner/templates/planner/signal_flow/list.html` (sibling SFD template with established conventions)
- `planner/models.py` (Console, Device, SpeakerArray, CommBeltPack field verification)
- `templates/includes/_help_modal.html` (alternate modal pattern — older, less polished than multitrack)
- `.planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md` (Phase 7 PATTERNS for established conventions reference)

**Files scanned:** ~12 files read; ~25 grep operations across `planner/`.

**Pattern extraction date:** 2026-05-20
