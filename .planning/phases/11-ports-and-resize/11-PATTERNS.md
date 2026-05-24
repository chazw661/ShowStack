# Phase 11: Per-Shape Labeled Ports + Resizable Shapes — Pattern Map

**Mapped:** 2026-05-24
**Files analyzed:** 3 to modify, 1 read-only, 1 external analog
**Analogs found:** 3 / 3 internal files (100% exact-match); 1 external analog (JointJS demo) for resize tool — no in-tree analog exists

## File Classification

| File to Modify | Role | Data Flow | Closest Analog | Match Quality |
|----------------|------|-----------|----------------|---------------|
| `planner/static/planner/js/signal_flow_editor.js` (multi-region) | client controller (UI + graph mutation + persistence orchestrator) | event-driven (DOM events + JointJS graph events → debounced HTTP) | itself — Phase 8/9/10 layers in same IIFE | exact (self-extend) |
| `planner/static/planner/css/signal_flow.css` (Sections 14/15/16) | UI stylesheet | n/a (static) | itself — Sections 1–13 (Phase 8/9/10) | exact (append convention) |
| `.planning/REQUIREMENTS.md` (PORT-01 text amendment) | spec / documentation | n/a (static text) | itself — existing PORT-01..06 + SHP-RESIZE-01..03 blocks | exact |
| `planner/views.py` `_enrich_nodes` | **READ-ONLY this phase** — server enrichment | request-response | n/a (no server changes) | n/a |

**External analog (no in-tree code matches — flagged for citation):**
- `github.com/clientIO/joint-demos/blob/main/resize-control-tool/js/src/main.js` (MPL-2.0) — canonical pattern for the `joint.elementTools.Control`-based corner resize tool. ShowStack has zero existing `joint.elementTools.*` subclasses; this is the first one. RESEARCH §Q1 already cites the demo line-by-line.

---

## Pattern Assignments

### `planner/static/planner/js/signal_flow_editor.js` — Region 1 of 5: Port-model replacement (lines 80–122)

**Role:** module-scoped factory functions that build JointJS port-group definitions and the initial 4-port array for every shape.

**Closest analog:** itself at lines 91–122. The Phase 11 replacement layer (engineer-authored ports) keeps `standardPortGroups()` intact (it's the source-of-truth for the `in`/`out` port-group attrs) but adds new module-level functions next to it.

**What to preserve VERBATIM (Phase 8 / Phase 9 contract):**
```javascript
// signal_flow_editor.js:91-108 — Phase 11 keeps standardPortGroups() unchanged.
// The 'in' / 'out' group magnet semantics ('passive' = inbound target,
// true = outbound source) drive validateMagnet at line 297 and must not change.
function standardPortGroups() {
  return {
    in: {
      position: { name: 'absolute' },
      attrs: { portBody: { magnet: 'passive', r: 4, fill: '#fff', stroke: '#666', 'stroke-width': 1, opacity: 0 } },
      markup: [{ tagName: 'circle', selector: 'portBody' }],
    },
    out: {
      position: { name: 'absolute' },
      attrs: { portBody: { magnet: true, r: 4, fill: '#fff', stroke: '#666', 'stroke-width': 1, opacity: 0 } },
      markup: [{ tagName: 'circle', selector: 'portBody' }],
    },
  };
}
```

**What to preserve as v2.2 back-compat (D-13 "shape has 0 authored ports → use generic"):**
```javascript
// signal_flow_editor.js:114-124 — portsForRect remains the source of the
// generic 4-port back-compat set. Phase 11 calls this UNCHANGED for any
// cell whose .showstack has no `authored: true` ports.
function portsForRect(width, height) {
  return {
    groups: standardPortGroups(),
    items: [
      { group: 'in',  args: { x: 0,         y: height / 2 } },
      { group: 'out', args: { x: width,     y: height / 2 } },
      { group: 'in',  args: { x: width / 2, y: 0 } },
      { group: 'out', args: { x: width / 2, y: height } },
    ],
  };
}
```

**Planner change directive:** ADD (do not replace) new module-level functions immediately AFTER line 124 — `addAuthoredPort(cell, edge, label)`, `removeAuthoredPortWithSurvival(cell, portId)`, `renameAuthoredPort(cell, portId, newLabel)`, `redistributeEdgePorts(cell, edge)`, `convertCellFromGenericToAuthored(cell)`, `cellHasAnyAuthoredPort(cell)`, `getAuthoredPortsByEdge(cell, edge)`, `directionForEdge(edge)`, `edgeMidpointInPaperCoords(cell, edge)`, `portLabelPositionForEdge(edge)`, `portLabelMarkupForEdge()`, `computeMinSize(cell)`, `maybeAutoExpand(cell)`, and `measureLabelWidth(text, fontSize)`. Per RESEARCH §Q8 Option B, all are module-level helpers taking the cell as their first argument — matches the existing `applyOrphanState(cell)` / `applyAttachedOrphanState(link)` pattern at signal_flow_editor.js:1249/1283.

---

### `planner/static/planner/js/signal_flow_editor.js` — Region 2 of 5: 7 shape class definitions (lines 127–266)

**Role:** JointJS element class definitions (one per smart shape type).

**Closest analog:** itself — every one of the 7 classes follows the same structure. Console (lines 127–144) is the reference template.

**Reference template (Console, lines 127–144):**
```javascript
// signal_flow_editor.js:127-144 — Console reference template.
// All 7 shape classes follow this exact shape: markup → defaults → deepSupplement.
joint.shapes.showstack.Console = joint.dia.Element.extend({
  markup: [
    { tagName: 'rect', selector: 'body' },
    { tagName: 'rect', selector: 'band' },
    { tagName: 'text', selector: 'label' },
  ],
  defaults: joint.util.deepSupplement({
    type: 'showstack.Console',
    size: { width: 180, height: 60 },
    attrs: {
      body:  { refWidth: '100%', refHeight: '100%', fill: '#ffffff', stroke: '#333', 'stroke-width': 1.5 },
      band:  { x: 0, y: 0, width: 6, refHeight: '100%', fill: '#0d9488' },
      label: { refX: 16, refY: '50%', textAnchor: 'start', textVerticalAnchor: 'middle',
               fontSize: 13, fontFamily: FONT_STACK, fill: '#111', text: 'Console' },
    },
    ports: portsForRect(180, 60),
  }, joint.dia.Element.prototype.defaults),
});
```

**Phase 11 directive: DO NOT EDIT the 7 `defaults.attrs` blocks.** Per CONTEXT D-08 and RESEARCH §Q8, the per-shape `attrs` (body / band / label `refX`/`refY`/`textAnchor`) are Phase 8/10 LOCKED. Phase 11 adds resize + port-authoring entirely additively via the module-level helpers (Region 1). Auto-generated 4 generic ports via `portsForRect(...)` REMAIN the initial ports array for every shape — they only get removed by `convertCellFromGenericToAuthored(cell)` on first authored-port add (RESEARCH §Q5).

**Absolute floors for SHP-RESIZE-02:** the `defaults.size` values from each class definition (180×60, 140×56, 120×80, 80×100, 140×56, 160×60, 140×60) become the `ABSOLUTE_FLOOR_W` / `ABSOLUTE_FLOOR_H` constants in `computeMinSize`. Researcher already verified at RESEARCH line 411. Planner should derive these from a single literal table, not from runtime introspection (defaults are not safely readable from a registered class after construction).

---

### `planner/static/planner/js/signal_flow_editor.js` — Region 3 of 5: `defaultLink` / `validateMagnet` / `validateConnection` (lines 291–308)

**Role:** Paper-level link-creation policy.

**Closest analog:** itself at lines 291–309. RESEARCH §Q5 explicitly confirms NO functional change is needed here.

**What to preserve UNCHANGED:**
```javascript
// signal_flow_editor.js:291-309 — Phase 11 keeps this block byte-for-byte.
// D-13's whole-shape switch is satisfied elsewhere: at any moment the
// shape has EITHER 4 generic OR N authored ports, never both. The
// "must hit a magnet" rule below is correct for both sets.
defaultLink: function () {
  return new joint.shapes.showstack.SignalLink();
},
validateMagnet: function (cellView, magnet) {
  return magnet && magnet.getAttribute('magnet') !== 'passive';
},
validateConnection: function (sourceView, sourceMagnet, targetView, targetMagnet) {
  if (!sourceMagnet || !targetMagnet) return false;
  if (sourceView === targetView) return false;
  return true;
},
```

**Planner change directive:** NO edits to this block. Per-port snap targeting (PORT-04) emerges automatically from the new `addPort` calls in Region 1. Planner adds an inline comment ("Phase 11 — per-port snap targeting honored automatically; see addAuthoredPort()") to prevent future agents from "fixing" this code.

---

### `planner/static/planner/js/signal_flow_editor.js` — Region 4 of 5: Inspector mode logic (lines 1300–1551)

**Role:** Right-side inspector panel — switches between connector / node modes; builds DOM lazily; wires field handlers.

**Closest analog (best in-tree match for D-04 trash icon + per-row pattern):** the Phase 9 `buildNodeModeBlock` (lines 1463–1518) is the EXACT analog for D-02 "+ Add port" button creation and D-04 trash icon button creation. Same lazy-build / `style.setProperty(..., 'important')` discipline.

**Excerpt — Phase 9 node-mode block as the template for Phase 11 port-author block** (signal_flow_editor.js:1463–1491):
```javascript
function buildNodeModeBlock() {
  if (!inspectorEl) return;
  nodeModeBlock = document.createElement('div');
  nodeModeBlock.className = 'sfd-field sfd-field--node-actions';
  nodeModeBlock.setAttribute('data-mode', 'node');
  nodeModeBlock.style.setProperty('display', 'none', 'important');

  nodeRelinkBtn = document.createElement('button');
  nodeRelinkBtn.type = 'button';
  nodeRelinkBtn.id = 'sfd-node-relink';
  nodeRelinkBtn.textContent = 'Re-link equipment';
  nodeRelinkBtn.style.setProperty('display', 'block', 'important');
  nodeRelinkBtn.style.setProperty('width', '100%', 'important');
  nodeRelinkBtn.style.setProperty('margin-bottom', '8px', 'important');
  nodeRelinkBtn.style.setProperty('padding', '8px 12px', 'important');
  nodeRelinkBtn.style.setProperty('cursor', 'pointer', 'important');

  nodeDeleteBtn = document.createElement('button');
  nodeDeleteBtn.type = 'button';
  nodeDeleteBtn.id = 'sfd-node-delete';
  nodeDeleteBtn.textContent = 'Delete shape';
  nodeDeleteBtn.style.setProperty('display', 'block', 'important');
  nodeDeleteBtn.style.setProperty('width', '100%', 'important');
  nodeDeleteBtn.style.setProperty('padding', '8px 12px', 'important');
  nodeDeleteBtn.style.setProperty('cursor', 'pointer', 'important');

  nodeModeBlock.appendChild(nodeRelinkBtn);
  nodeModeBlock.appendChild(nodeDeleteBtn);
  inspectorEl.appendChild(nodeModeBlock);
  // ... click handlers attach delete (with beginBatch/endBatch wrap) + relink ...
}
```

**Excerpt — Phase 9 delete pattern as the model for Phase 11 "remove port" undo-batching** (signal_flow_editor.js:1502–1517):
```javascript
nodeDeleteBtn.addEventListener('click', function () {
  if (!inspectorCurrentNode) return;
  var cell = inspectorCurrentNode;
  if (window.__sfd.undo && typeof window.__sfd.undo.beginBatch === 'function') {
    window.__sfd.undo.beginBatch();
    cell.remove();
    window.__sfd.undo.endBatch();
  } else {
    cell.remove();
  }
  if (window.__sfd.selection && typeof window.__sfd.selection.clear === 'function') {
    window.__sfd.selection.clear();
  }
  inspectorCurrentNode = null;
  hideInspector();
});
```

**Excerpt — `setInspectorMode('node', cell)` extension point** (signal_flow_editor.js:1533–1550):
```javascript
} else if (mode === 'node') {
  if (inspectorHeader) inspectorHeader.textContent = 'Node';
  connectorFieldRows.forEach(function (row) {
    row.style.setProperty('display', 'none', 'important');
  });
  nodeModeBlock.style.setProperty('display', 'block', 'important');
  inspectorCurrentNode = cell;
  inspectorCurrentLink = null;
  var prop = cell.prop('showstack') || {};
  var hasLink = !!(prop.contentTypeId);
  if (nodeRelinkBtn) {
    nodeRelinkBtn.style.setProperty(
      'display', hasLink ? 'block' : 'none', 'important'
    );
  }
}
```

**Planner change directive:** Phase 11 extends `setInspectorMode('node', cell)` to also call `buildPortAuthorBlock()` lazily on first node-mode entry and `refreshPortAuthorBlock(cell)` every time. Use the EXACT idioms above:
- All DOM style writes via `el.style.setProperty(prop, value, 'important')` (CLAUDE.md mandate, already 28+ occurrences in this file).
- Lazy build flag pattern (`if (!portAuthorBlock) buildPortAuthorBlock();`) identical to `if (!nodeModeBlock) buildNodeModeBlock();` at line 1522.
- Trash-icon click handler wraps `removeAuthoredPortWithSurvival(cell, portId)` in `window.__sfd.undo.beginBatch/endBatch` — same pattern as line 1505–1508 above.
- Render port labels into inspector rows with `textContent`, NEVER `innerHTML` (XSS — RESEARCH §Security; matches Phase 10 pattern at line 1882).

---

### `planner/static/planner/js/signal_flow_editor.js` — Region 5 of 5: Phase 10 combobox widget (lines 1775–1935)

**Role:** ARIA combobox widget — text input + listbox + debounced fetch + keyboard nav. Currently tightly coupled to the single `#sfd-circuit-label` input.

**Closest analog:** itself — IS the widget Phase 11 must reuse (CONTEXT D-03, RESEARCH §Q9).

**Excerpt — current Phase 10 init + listbox creation** (signal_flow_editor.js:1799–1820):
```javascript
function initAutocomplete() {
  if (!circuitLabelInput || !labelAutocompleteUrl) return;

  // Wrap input's parent .sfd-field div — add wrapper class for CSS positioning.
  var fieldDiv = circuitLabelInput.closest('.sfd-field');
  if (!fieldDiv) return;
  fieldDiv.classList.add('sfd-autocomplete-wrapper');

  // Create listbox element.
  acListbox = document.createElement('ul');
  acListbox.id = 'sfd-label-suggestions';
  acListbox.setAttribute('role', 'listbox');
  acListbox.setAttribute('hidden', '');
  fieldDiv.appendChild(acListbox);

  // ARIA: wire combobox role onto the input.
  circuitLabelInput.setAttribute('role', 'combobox');
  circuitLabelInput.setAttribute('aria-autocomplete', 'list');
  circuitLabelInput.setAttribute('aria-expanded', 'false');
  circuitLabelInput.setAttribute('aria-haspopup', 'listbox');
  circuitLabelInput.setAttribute('aria-controls', 'sfd-label-suggestions');
```

**Excerpt — XSS-safe row rendering** (signal_flow_editor.js:1873–1888):
```javascript
results.forEach(function (rec, i) {
  var li = document.createElement('li');
  li.className = 'sfd-ac-row';
  li.setAttribute('role', 'option');
  li.setAttribute('aria-selected', 'false');
  li.id = 'sfd-ac-row-' + i;

  // XSS-safe: textContent only (PATTERNS.md rule).
  var labelSpan = document.createElement('span');
  labelSpan.textContent = rec.label || '';
  var sourceSpan = document.createElement('span');
  sourceSpan.className = 'sfd-ac-source';
  sourceSpan.textContent = rec.source ? ('— ' + rec.source) : '';

  li.appendChild(labelSpan);
  li.appendChild(sourceSpan);
```

**Excerpt — synthetic input event on selection (the autosave-trigger seam Phase 11 needs)** (signal_flow_editor.js:1908–1915):
```javascript
function selectAcRow(rowEl, label) {
  // label may come from the rec or from the row's first span text.
  var chosen = label || (rowEl.querySelector('span') && rowEl.querySelector('span').textContent) || '';
  circuitLabelInput.value = chosen;
  closeAcListbox();
  // D-14: dispatch synthetic input event so existing Phase 9 inspector listener fires.
  circuitLabelInput.dispatchEvent(new Event('input', { bubbles: true }));
}
```

**Planner change directive — REFACTOR (do NOT duplicate):**
Per RESEARCH §Q9, refactor `initAutocomplete()` into `attachAutocompleteToInput(inputEl, url, onSelect)` BEFORE Phase 11 wires per-port-row inputs. Three required generalizations:

1. **Hardcoded element lookup → parameter.** `circuitLabelInput` (referenced 12× in this region) becomes `inputEl` (the function parameter).
2. **Hardcoded listbox id → generated per attachment.** `id="sfd-label-suggestions"` → `id="sfd-label-suggestions-<unique>"` where `<unique>` is `inputEl.id` or a generated counter. Update `aria-controls` and `aria-activedescendant` references in lockstep.
3. **Selection side-effect → callback.** `selectAcRow` currently fires a synthetic `input` event so the Phase 9 inspector listener picks it up. Generalize to also accept an `onSelect(label)` callback so Phase 11 port-rows can call `renameAuthoredPort(cell, portId, label)` directly instead of relying on the global circuit-label listener.

After refactor, the existing circuit-label call site calls `attachAutocompleteToInput(circuitLabelInput, labelAutocompleteUrl, null)` (null → fall back to synthetic-input-event compatibility shim). Each new port-row attaches with `attachAutocompleteToInput(row.querySelector('.sfd-port-label-input'), labelAutocompleteUrl, function(label){ renameAuthoredPort(cell, portId, label); })`. No regression to the Phase 10 circuit-label UAT cases.

---

### Shared pattern: `showToast` API for D-11 ("Shape resized to fit ports")

**Source:** `planner/static/planner/js/signal_flow_editor.js:72-79`

**Apply to:** `maybeAutoExpand(cell)` per RESEARCH §Q7 Example 4.

**Excerpt — exact call signature:**
```javascript
function showToast(message, level) {
  var t = document.createElement('div');
  t.className = 'sfd-toast sfd-toast--' + (level || 'info');
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(function () { t.classList.add('sfd-toast--hide'); }, 3000);
  setTimeout(function () { t.remove(); }, 3500);
}
```

**Phase 11 call site (RESEARCH §Q7 Example 4):**
```javascript
showToast('Shape resized to fit ports.', 'info');
```

Note: `showToast` is **defined as a function-scoped local** inside the IIFE (line 72), NOT exposed on `window.__sfd.helpers.showToast`. The handoff at line 1751 DOES expose it (`window.__sfd.helpers = { ..., showToast: showToast }`) but the in-file caller uses the bare name. Phase 11 helpers added between lines 124 and 268 are in the same IIFE scope and call `showToast(...)` directly — no namespace prefix.

---

### Shared pattern: autosave + If-Match + undo wiring

**Source:** `planner/static/planner/js/signal_flow_editor.js:1597-1717`

**Apply to:** Every Phase 11 mutation — `addAuthoredPort`, `removeAuthoredPortWithSurvival`, `renameAuthoredPort`, `CornerResize.setPosition` (drag-end), `maybeAutoExpand`.

**Excerpt — `scheduleAutosave` debounce (lines 1597–1602):**
```javascript
function scheduleAutosave() {
  if (conflicted) return;
  diagramDirty = true;
  if (autosaveTimer) clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(flushAutosave, 1500);   // D-02
}
```

**Excerpt — graph-event listeners that fire `scheduleAutosave` automatically (lines 1716–1717):**
```javascript
// D-01 — graph events that trigger autosave. Note: change:position is NOT
// listed here. Mid-drag position events are intentionally excluded
// (PITFALLS.md §6 "autosave flooding"); only the element:pointerup
// drag-end below fires the debounce for moves.
graph.on('add remove change:source change:target', scheduleAutosave);
paper.on('element:pointerup', scheduleAutosave);
```

**Phase 11 implications:**
- `cell.resize(w, h)` fires `change:size`. **`change:size` is NOT in the listener list above.** Planner must EITHER add `change:size` to the comma-separated event string at line 1716, OR rely on `paper.on('element:pointerup', scheduleAutosave)` to catch the drag-end. RESEARCH §Q1 (autosave + undo integration) confirms `element:pointerup` does fire when the engineer releases the resize tool handle, so adding `change:size` is OPTIONAL but recommended for the auto-expand path (which does NOT involve a pointer release — it's programmatic).
- `cell.addPort` / `cell.removePort` mutate the cell — they fire `change:ports` (NOT `add` or `remove`, which are graph-level cell add/remove). **`change:ports` is also NOT in the listener list at line 1716.** Phase 11 helpers MUST call `scheduleAutosave()` EXPLICITLY at the end of `addAuthoredPort`, `removeAuthoredPortWithSurvival`, and `renameAuthoredPort` — already shown in RESEARCH §Q4 Example 2 and §Q6 Example 3. Do NOT add `change:ports` to the line 1716 listener — RESEARCH Pitfall 7 calls out that naïve listening can produce an infinite-loop with redistribute.
- All Phase 11 mutations are batched-undoable via `window.__sfd.undo.beginBatch/endBatch` (exposed at line 1759–1763) — same pattern as the Phase 9 delete (lines 1505–1508).

---

### Shared pattern: magnet semantics for engineer-authored ports

**Source:** Phase 8 conventions in `signal_flow_editor.js` — magnet `'passive'` = inbound target; magnet `true` = outbound source.

**Apply to:** every `addAuthoredPort` call (RESEARCH §Q3 — direction inferred from edge).

**Excerpt — Phase 8 magnet declaration in `standardPortGroups`** (lines 96–106):
```javascript
in:  { attrs: { portBody: { magnet: 'passive', r: 4, fill: '#fff', stroke: '#666', 'stroke-width': 1, opacity: 0 } }, ... },
out: { attrs: { portBody: { magnet: true,      r: 4, fill: '#fff', stroke: '#666', 'stroke-width': 1, opacity: 0 } }, ... },
```

**Excerpt — Phase 8 validateMagnet enforcement (line 297–302):**
```javascript
validateMagnet: function (cellView, magnet) {
  // Allow link drag to START only from non-passive magnets (out-ports).
  // In-ports have magnet="passive" and act as drag TARGETS only.
  return magnet && magnet.getAttribute('magnet') !== 'passive';
},
```

**Phase 11 — direction-from-edge map (RESEARCH §Q3 Implementation):**
```javascript
function directionForEdge(edge) {
  // 'top' + 'left'  → inbound (magnet: 'passive')
  // 'bottom' + 'right' → outbound (magnet: true)
  if (edge === 'top' || edge === 'left') return 'in';
  return 'out';
}
```

**Phase 11 — addPort excerpt that honors this mapping** (RESEARCH §Q4 schema + Example 2 — verbatim for the planner):
```javascript
cell.addPort({
  group: directionForEdge(edge),           // 'in' or 'out' — uses existing standardPortGroups
  attrs: {
    portBody: {
      magnet: directionForEdge(edge) === 'in' ? 'passive' : true,
      r: 4, fill: '#fff', stroke: '#666',
      'stroke-width': 1, opacity: 0,        // hover-revealed (Phase 8 CSS Section 7)
    },
    label: { text: label },                  // JointJS reads this for label rendering
  },
  args: { x: 0, y: 0 },                       // overwritten by redistributeEdgePorts
  label: {
    position: portLabelPositionForEdge(edge),  // Q10 — manual layout per edge
    markup: portLabelMarkupForEdge(),
  },
  showstack: { label: label, edge: edge, authored: true },
});
```

---

### Shared pattern: admin-DOM `!important` style writes

**Source:** CLAUDE.md "Overriding Django admin CSS from JavaScript" + 28+ occurrences in `signal_flow_editor.js`.

**Apply to:** EVERY style write Phase 11 makes on `.sfd-port-*` HTML elements (port-row, add-port button, trash icon, edge-section container).

**Reference call sites already in the file** (lines 1468, 1474–1478, 1484–1487, 1527, 1536, 1538, 1546–1548):
```javascript
nodeModeBlock.style.setProperty('display', 'none', 'important');
nodeRelinkBtn.style.setProperty('display', 'block', 'important');
nodeRelinkBtn.style.setProperty('width', '100%', 'important');
nodeRelinkBtn.style.setProperty('margin-bottom', '8px', 'important');
nodeRelinkBtn.style.setProperty('padding', '8px 12px', 'important');
nodeRelinkBtn.style.setProperty('cursor', 'pointer', 'important');
```

**Rule:** Never use `el.style.display = '…'` shorthand on `.sfd-*` HTML elements inside the inspector. Always `el.style.setProperty(prop, value, 'important')`. **JointJS SVG inside `#sfd-paper`** (port circles, port labels, resize-tool `<rect>` handles) is NOT in the admin namespace and does NOT need `!important` — but the CSS Sections 14/15/16 still use `!important` per file-header convention (signal_flow.css lines 12–17).

---

### Shared pattern: graceful no-op when admin elements absent

**Source:** Existing top-of-file early returns + null-guards.

**Apply to:** Phase 11's `buildPortAuthorBlock()` and `refreshPortAuthorBlock(cell)`.

**Excerpt — Phase 9 lazy build with null-guards** (lines 1463–1464):
```javascript
function buildNodeModeBlock() {
  if (!inspectorEl) return;       // ← null-guard
  ...
}
```

**Excerpt — Phase 8 root null-guard** (lines 20–23):
```javascript
var container = document.getElementById('sfd-container');
if (!container) {
  return;  // Either we're not on the editor page or the template was changed unexpectedly.
}
```

Planner: every Phase 11 DOM-touching helper does `if (!inspectorEl) return;` at the top — matches the established discipline.

---

## CSS Append-at-End Pattern

**Source:** `planner/static/planner/css/signal_flow.css:1-30` (file header — enumerates Sections 1–9 originally) and current Sections 1–13.

**Excerpt — file header rule** (lines 1–30, especially 11–17 — the `!important` mandate that Sections 14/15/16 must honor):
```css
/*
 * signal_flow.css — Phase 8 chrome for the Signal Flow Diagrammer editor.
 *
 * Loaded ONLY by `editor.html` ... NEVER loaded by `list.html` ...
 * New rules here use IDs (#sfd-toolbar, #sfd-sidebar, #sfd-inspector) plus
 * distinct class names (.sfd-tile, .sfd-btn-group, .sfd-picker-*, ...).
 *
 * !important is used pervasively because `django-admin-interface` ships
 * `!important` declarations that win specificity battles otherwise. Rule
 * of thumb from CLAUDE.md: every property the admin theme might touch
 * gets `!important`. JointJS-managed SVG inside `#sfd-paper` is in its
 * own namespace and does not need `!important` — but we apply it on the
 * few SVG rules below anyway (port hover-reveal, selection visuals) for
 * defence-in-depth.
 */
```

**Section header convention (verified format from Sections 10–13):**
```css
/* =========================================================================
   SECTION 13 — Export button group (Phase 10 EXP-01)
   Right-aligned toolbar group containing the PNG export button. Group
   scaffolded for future PDF / SVG buttons (v2.4+). Click handler wired
   by Plan 10-03 via html-to-image library (already vendored in Phase 7).
   ========================================================================= */
```

**Reference for the file-header section list update** (current lines 20–30):
```css
 * Sections:
 *   1. Toolbar button groups + dividers (extends Phase 7 #sfd-toolbar)
 *   2. Canvas container layout (sidebar | paper | inspector)
 *   3. Left sidebar shape picker (#sfd-sidebar + .sfd-tile)
 *   4. Right inspector panel (#sfd-inspector + .sfd-field + .sfd-segmented)
 *   5. Equipment picker modal (.sfd-picker-overlay + .sfd-pick-*)
 *   6. Toast (.sfd-toast)
 *   7. JointJS port hover-reveal
 *   8. Selection visual (.is-selected + .sfd-multi-bbox)
 *   9. Empty canvas hint (.sfd-empty-hint)
 */
```

**Planner change directive:**
1. **Append Sections 14/15/16 at end-of-file** (after line 691). Use the same `/* === SECTION N — Title (Phase 11 …) === */` header pattern shown above.
2. **Extend the file-header section list at lines 20–30** to include Sections 10–16 (currently only 1–9 listed — Phase 9/10 already drifted; Phase 11 catches it up).
3. **Section 14 — Port-label rendering (D-08 perpendicular-inside):**
   - The existing Section 7 port hover-reveal at line 482–494 must be AMENDED, not duplicated. Per RESEARCH §Q10:
     ```css
     /* Current (Section 7) — opacity:0 hides the entire .joint-port */
     .joint-paper .joint-element:hover .joint-port circle { opacity: 1 !important; }
     /* Phase 11 amendment — keep labels always visible; only dots hover-reveal */
     .joint-port-label text { opacity: 1 !important; }
     ```
     Planner choice: either (a) edit Section 7 in place and add a Phase 11 cross-reference comment, OR (b) add Section 14 with an overriding `.joint-port-label text` rule that simply wins by source order. RESEARCH recommends (a) for cleanliness.
4. **Section 15 — Resize handles (D-05 four corners):** SVG-namespace rules; `!important` for defence-in-depth per file-header convention. Pattern model is Section 8 selection visual (lines 503–518), which uses `.joint-element.is-selected [joint-selector="body"]` selectors.
5. **Section 16 — Inspector port-list row + trash icon (D-02 / D-04):** admin-DOM rules; `!important` mandatory. Pattern model is Section 4 inspector panel (line 189 onward) for field-row styling. Use class names from RESEARCH §Q9: `.sfd-field--port-author`, `.sfd-port-section-title`, `.sfd-port-edge-section`, `.sfd-port-edge-header`, `.sfd-port-add`, `.sfd-port-list`, `.sfd-port-row`, `.sfd-port-ordinal`, `.sfd-port-label-input`, `.sfd-port-remove`.

---

## REQUIREMENTS.md PORT-01 Amendment (D-01)

**Source:** `.planning/REQUIREMENTS.md:15` (current).

**Current text (verbatim):**
```markdown
- [ ] **PORT-01**: User can add a labeled port to any smart shape via the inspector. Ports anchor to one of three edges per shape: **Top** (horizontal-axis line), **Left** (vertical-axis line), **Right** (vertical-axis line). The bottom edge is reserved for the shape label and is not a port edge in v2.3.
```

**Phase 11 replacement text (per CONTEXT D-01 + RESEARCH header):**
```markdown
- [ ] **PORT-01**: User can add a labeled port to any smart shape via the inspector. Ports anchor to one of four edges per shape: **Top**, **Bottom**, **Left**, **Right**. The bottom edge is structurally free because all 7 shape classes left-anchor their body label inside the colored band (`refX: 16, refY: '50%'` in `signal_flow_editor.js`), so bottom-edge ports do not collide with the shape's own label.
```

**Planner change directive:** make this edit in the FIRST plan that touches REQUIREMENTS.md (likely a setup/scaffolding plan), so downstream plans, the verifier, and future audits all see the corrected text. Mark with a Phase 11 phase reference for traceability.

---

## No Analog Found

| File / Need | Why no in-tree analog | Recommended source |
|-------------|----------------------|--------------------|
| `joint.elementTools.Control` subclass for corner resize | ShowStack has ZERO `elementTools.*` subclasses anywhere in the codebase. Phase 11 is the first. | External MPL-2.0 reference: `github.com/clientIO/joint-demos/blob/main/resize-control-tool/js/src/main.js`. RESEARCH §Q1 cites and adapts it verbatim — Phase 11 adaptation (4 corners + min-size + snap-to-grid + autosave hook) is at RESEARCH lines 215–300. Planner should copy that adapted snippet into the new Region 1 helpers section. |
| Canvas-2D `measureText` text measurement | No existing call site uses `getContext('2d').measureText`. PNG export uses html-to-image which is a different concern. | RESEARCH §Q2 Pixel Measurement section provides the 8-line memoized helper (lines 348–360). |
| Per-port label `position: { name: 'manual', args: {...} }` JointJS markup | Phase 8 ports use `position: { name: 'absolute' }` with no per-port label. Phase 11 introduces per-port labels. | RESEARCH §Q10 Code Examples — `portLabelPositionForEdge(edge)` switch + `portLabelMarkupForEdge()` factory. JointJS docs: `docs.jointjs.com/api/layout/PortLabel/`. |

---

## Pattern Coverage Summary

| Phase 11 helper / feature | Closest analog | Match quality |
|---------------------------|----------------|---------------|
| `addAuthoredPort` | Phase 8 `standardPortGroups` + Phase 9 `applyOrphanState` style (module-level cell-as-arg) | exact |
| `removeAuthoredPortWithSurvival` (re-anchor BEFORE removePort) | none in-tree — RESEARCH §Q6 derived from bundle source inspection of `_processRemovedPort` | external/derived |
| `renameAuthoredPort` | Phase 10 `selectAcRow` + `circuitLabelInput.dispatchEvent(new Event('input'))` pattern | exact |
| `redistributeEdgePorts` | RESEARCH §Q7 redistribution recipe; no in-tree analog (Phase 8 ports are static-positioned) | external/derived |
| `convertCellFromGenericToAuthored` | composition of Phase 8 `cell.removePort` + `cell.addPort` | exact |
| `computeMinSize` / `measureLabelWidth` | none in-tree | RESEARCH §Q2 |
| `maybeAutoExpand` + toast | `showToast` at signal_flow_editor.js:72-79 | exact |
| `CornerResize` element tool | none in-tree — first `joint.elementTools.*` subclass | external MPL-2.0 demo (RESEARCH §Q1) |
| `attachResizeTools` / `detachResizeTools` | Phase 9 `onSelectionChanged` callback wiring at line 1362 | exact |
| Per-edge inspector section (4 sections) | Phase 9 `buildNodeModeBlock` at line 1463 | exact (template clone) |
| Per-port trash icon click handler | Phase 9 `nodeDeleteBtn` click handler + `beginBatch/endBatch` at line 1502–1517 | exact |
| `attachAutocompleteToInput` (combobox refactor) | Phase 10 `initAutocomplete` at line 1799 | exact (refactor) |
| Section 14/15/16 CSS append | Sections 10/11/12/13 (Phase 9 + Phase 10 appends) | exact |

---

## Metadata

**Analog search scope:**
- `planner/static/planner/js/signal_flow_editor.js` (full file — IIFE; ~2150 lines)
- `planner/static/planner/css/signal_flow.css` (full file — 691 lines)
- `planner/views.py:7530-7625` (`_enrich_nodes` + `signal_flow_state`)
- `.planning/REQUIREMENTS.md` (PORT + SHP-RESIZE sections, lines 11–28)
- `.planning/phases/08-canvas-smart-shapes-connectors/08-CONTEXT.md` (via RESEARCH crosswalk)
- `.planning/phases/09-autosave-orphan-rendering/09-CONTEXT.md` (via RESEARCH crosswalk)
- `.planning/phases/10-autocomplete-png-export-new-shapes/10-CONTEXT.md` (via RESEARCH crosswalk)

**Files scanned:** 4 source files + 4 planning docs.
**External analog citations:** 1 (clientIO/joint-demos resize-control-tool — MPL-2.0).
**Pattern extraction date:** 2026-05-24.
