# Phase 12: Boundary Lines + Text Annotations — Pattern Map

**Mapped:** 2026-05-25
**Files analyzed:** 5 to modify, 1 to create, 1 read-only (verification target)
**Analogs found:** 11 / 11 distinct sub-patterns — 100% in-tree analog coverage (no external citations needed; every Phase 12 sub-pattern has a Phase 8/9/10/11 precedent)

## File Classification

| File to Create / Modify | Role | Data Flow | Closest Analog | Match Quality |
|-------------------------|------|-----------|----------------|---------------|
| `planner/static/planner/js/signal_flow_editor.js` (Region A — shape registration ~line 761) | JS shape registration | n/a (declarative class defs) | itself — 7 existing shape classes at signal_flow_editor.js:622–761 (Console template at 622–639) | exact (self-extend) |
| `planner/static/planner/js/signal_flow_editor.js` (Region B — vertex tool ~line 597) | JS draw lifecycle (elementTools.Control subclass) | DOM drag → `cell.prop('vertices')` mutation → `change:vertices` event → autosave | itself — Phase 11 `CornerResize` at signal_flow_editor.js:537–597 | exact (template clone, swap corner→vertexIndex, size()→prop('vertices')) |
| `planner/static/planner/js/signal_flow_editor.js` (Region C — toolbar wiring + pen-tool state machine) | JS toolbar wiring + JS draw lifecycle | DOM click → mode flag flip → `paper.on('blank:pointerdown')` → vertex push → `commitOrCancelBoundary` → `graph.addCell` → autosave | Phase 8 rubber-band-rect at signal_flow_editor.js:1500–1544 (multi-listener `blank:pointerdown` + live SVG preview pattern) | exact (pattern clone — same paper-event surface, same SVG preview append-to-viewport) |
| `planner/static/planner/js/signal_flow_editor.js` (Region D — inspector mode panels) | JS inspector mode panel | DOM swatch click → `cell.prop()` mutation → `applyBoundaryRender` → `scheduleAutosave` | Phase 9 `buildNodeModeBlock` at signal_flow_editor.js:1980–2056 + `setInspectorMode('node')` branch at signal_flow_editor.js:2213–2235 | exact (template clone — same lazy-build / show-hide / `style.setProperty(.., 'important')` discipline) |
| `planner/static/planner/js/signal_flow_editor.js` (Region E — text inline-edit lifecycle) | JS edit lifecycle (HTML overlay) | DOM click → `<input>` overlay → blur/Enter → `cell.attr('label/text')` → autosave; Esc → cancel/auto-delete | Phase 10 `selectAcRow` synthetic-input pattern at signal_flow_editor.js:1908–1915 (selection writes value + dispatches event) | role-match (HTML overlay is novel but the focus/commit/cancel discipline matches the autocomplete) |
| `planner/static/planner/js/signal_flow_editor.js` (Region F — selection-change + autosave wiring) | JS selection wiring | JointJS selection event → `setInspectorMode('boundary'\|'text')` → `attachBoundaryVertexTools` | Phase 9 `onSelectionChanged` at signal_flow_editor.js:1862 + Phase 11 `attachResizeTools` invocation pattern | exact |
| `planner/templates/planner/signal_flow/editor.html` (toolbar insertion lines 58–60) | HTML toolbar | static markup | existing `<div class="sfd-btn-group" data-group="…">` blocks at editor.html:45–67 (5 existing groups) | exact (clone existing group structure + 2 dividers) |
| `planner/static/planner/css/signal_flow.css` (append Sections 17 + 18 after line 875) | CSS new sections | n/a (static) | Phase 11 Sections 14/15/16 (line 711+, 824+, 847+) — append-at-end convention | exact |
| `planner/views.py` IDOR allowlist (~line 7693) | Python view validation | request-response | **READ-ONLY this phase** — verified pass-through; no edits | n/a (regression-locked by test) |
| `planner/tests/test_signal_flow_phase12.py` (NEW) | Python tests | request-response (Django TestCase POST) | `planner/tests/test_signal_flow_phase9.py` (`_Phase9Base` setUp pattern) | exact (file structure clone) |
| `.planning/REQUIREMENTS.md` traceability table (lines 110–136) | spec / documentation | n/a (static text) | itself — existing DRAW + TXT row entries | exact (mark-as-done edit) |

---

## Pattern Assignments

### Region A — JS shape registration (`planner/static/planner/js/signal_flow_editor.js`, after line 761)

**Role:** JointJS element class definitions — one for `BoundaryLine`, one for `TextLabel`. Module-level constant palettes + style tables.

**Closest analog:** Console reference template at signal_flow_editor.js:622–639. All 7 existing shape classes follow this exact markup → defaults → deepSupplement structure.

**Reference template — Console (signal_flow_editor.js:622–639):**

```javascript
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

**FONT_STACK reference (signal_flow_editor.js:94):**
```javascript
var FONT_STACK = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
```

**Planner change directive:**
1. Insert AFTER the Amp class (signal_flow_editor.js:761) and BEFORE `new joint.dia.Graph(...)` at signal_flow_editor.js:770 (cell-class registration MUST precede graph instantiation — verified at signal_flow_editor.js:88 comment).
2. **BoundaryLine** — 2-child markup (`linePrimary` + `lineSecondary` polylines inside a `lineGroup`); no `ports:` key (decorative — no magnets per R-05); custom props `vertices`, `color`, `lineStyle`, `strokeWidth`. Verbatim class body in RESEARCH §R-01 lines 138–179.
3. **TextLabel** — 2-child markup (`hitArea` rect + `label` text); no `ports:` key; custom props `fontSize`, `color`. Verbatim class body in RESEARCH §R-02 lines 233–263.
4. **Module-level constants** — emit a single literal block AFTER the new classes:
   ```javascript
   var BOUNDARY_PALETTE   = ['#000000','#666666','#dc2626','#ea580c','#eab308','#16a34a','#2563eb','#9333ea']; // D-09
   var TEXT_PALETTE       = BOUNDARY_PALETTE.concat(['#ffffff']);                                              // D-19 +white
   var BOUNDARY_LINE_STYLES = {
     solid:  { dasharray: 'none',  doubleVisible: false },
     dashed: { dasharray: '6 4',   doubleVisible: false },
     dotted: { dasharray: '1 3',   doubleVisible: false },
     double: { dasharray: 'none',  doubleVisible: true  },
   };
   var TEXT_FONT_SIZES    = { small: 12, medium: 16, large: 24 };                                              // D-19
   ```
5. **`applyBoundaryRender(cell)` helper** — append in the same module-level scope (BoundaryLine has no native `change:vertices`→render path; this helper is the one true render path). Verbatim body in RESEARCH §R-01 lines 192–216.

---

### Region B — JS draw lifecycle: vertex-edit tool (`planner/static/planner/js/signal_flow_editor.js`, after line 597)

**Role:** `joint.elementTools.Control` subclass per vertex. ShowStack's second-ever `elementTools.*` subclass (Phase 11 introduced the first).

**Closest analog:** Phase 11 `CornerResize` at signal_flow_editor.js:537–597. Phase 12 is a template clone: swap `corner` → `vertexIndex`; swap `view.model.size()` → `view.model.prop('vertices')[idx]`; swap `model.resize(w,h)` → `model.prop('vertices', verts)`.

**Reference template — `CornerResize` (signal_flow_editor.js:537–597):**

```javascript
var CornerResize = joint.elementTools.Control.extend({
  children: [{
    tagName: 'rect',
    selector: 'handle',
    attributes: {
      width: 10, height: 10, x: -5, y: -5,
      fill: '#0d9488', stroke: '#fff', 'stroke-width': 1,
      cursor: 'nwse-resize',
    }
  }],

  getPosition: function (view) {
    var s = view.model.size();
    var c = this.options.corner;
    if (c === 'tl') return { x: 0,        y: 0 };
    if (c === 'tr') return { x: s.width,  y: 0 };
    if (c === 'bl') return { x: 0,        y: s.height };
    return { x: s.width, y: s.height };
  },

  setPosition: function (view, coordinates) {
    // ...snap-to-grid, clamp, model.resize() ...
  }
});
```

**Planner change directive:** Insert `BoundaryVertex` subclass + `attachBoundaryVertexTools(cell)` helper immediately after `CornerResize.setPosition` closes (~line 597). Verbatim body in RESEARCH §R-03 lines 352–412.

**Critical:**
- Visible handle is a **circle r=6** in teal `#0d9488` (D-06 — engineers learn one selection-handle language across resize + vertex-edit per Phase 11 user-MEMORY rule).
- Hit-area is a **second transparent circle r=12** as a sibling child (matches Phase 11 CornerResize's 10px-visible / SVG-rect-bounds hit-target pattern).
- `setPosition` snaps via `window.__sfd.viewport.snapEnabled` — same snap-toggle source-of-truth as Phase 11 D-05 corner resize.
- `setPosition` writes via `model.prop('vertices', verts)` — **must use `.slice()` to copy the array first** (prop() returns the live reference; mutating it bypasses change:vertices).
- A `graph.on('change:vertices', ...)` listener (Region C) re-renders + calls `view.updateTools()` + `scheduleAutosave()`.

---

### Region C — JS toolbar wiring + pen-tool state machine (`planner/static/planner/js/signal_flow_editor.js`)

**Role:** Mode-button click handlers + closure-scoped `drawState` state machine + `paper.on('blank:pointerdown' | 'blank:pointermove' | 'blank:pointerdblclick')` listeners + Esc keydown branch.

**Closest analog:** Phase 8 rubber-band rect at signal_flow_editor.js:1500–1544. Same multi-listener `blank:pointerdown` strategy, same SVG live-preview appended to `paper.viewport`, same document-level mousemove/mouseup discipline.

**Reference template — rubber-band rect (signal_flow_editor.js:1500–1544):**

```javascript
paper.on('blank:pointerdown', function (evt, x, y) {
  if (panState.spaceDown || evt.button !== 0) return;
  var startLocal = { x: x, y: y };
  var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('fill', 'rgba(13, 148, 136, 0.08)');   // accent at 8% opacity
  rect.setAttribute('stroke', '#0d9488');
  rect.setAttribute('stroke-width', '1');
  rect.setAttribute('stroke-dasharray', '4 3');
  rect.setAttribute('pointer-events', 'none');
  rect.setAttribute('x', String(x));
  rect.setAttribute('y', String(y));
  rect.setAttribute('width', '0');
  rect.setAttribute('height', '0');
  var vp = paper.viewport || paper.svg;
  if (vp && vp.appendChild) vp.appendChild(rect);

  function onMove(evt2) { /* ... grow rect to cursor ... */ }
  function onUp(evt2)   { /* ... select hits in rect, removeChild rect ... */ }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
});
```

**Multi-listener confirmation (signal_flow_editor.js:1717–1720):**

```javascript
// NOTE: plan 05 already registers a `blank:pointerdown` listener for rubber-band selection.
// JointJS event emitter supports multiple listeners on the same event; the rubber-band
// listener and this one (removeTools on blank click) coexist.
paper.on('blank:pointerdown', function () { paper.removeTools(); });
```

**Existing `is-active` toolbar button styling (signal_flow.css:84–87):**

```css
#sfd-toolbar button.is-active {
  background-color: #0d9488 !important;
  color: #fff !important;
}
```

**Snap toggle as the mode-active reference (editor.html:53):**

```html
<button type="button" id="sfd-snap-toggle" class="is-active"
        aria-label="Snap to grid: on" aria-pressed="true">&#x229E;</button>
```

**Planner change directive:**
1. **Add `drawState` closure-scoped object** + `enterBoundaryMode` / `exitBoundaryMode` / `enterTextMode` / `exitTextMode` functions. Verbatim bodies in RESEARCH §R-06 lines 513–625.
2. **Mode-button visual feedback (D-07)** — on entry: `toolBoundaryBtn.classList.add('is-active'); toolBoundaryBtn.setAttribute('aria-pressed', 'true'); paperEl.style.setProperty('cursor', 'crosshair', 'important');`. On exit: reverse + `paperEl.style.setProperty('cursor', '', 'important')`. **`!important` is mandatory** per CLAUDE.md admin-CSS override rule.
3. **`paper.on('blank:pointerdown', ...)` for vertex placement** — gated on `drawState.active`. Snap via `currentViewport.snapEnabled` (same source-of-truth as the rubber-band handler doesn't reference, but the Phase 11 CornerResize `setPosition` uses `window.__sfd.viewport.snapEnabled`).
4. **`paper.on('blank:pointermove', ...)` for live "to cursor" segment** — sets `x1/y1/x2/y2` on a transient `<line>` SVG, same direct-DOM approach as the rubber-band rect.
5. **`paper.on('blank:pointerdblclick', ...)` to commit** — calls `commitOrCancelBoundary()` (R-06).
6. **Esc keydown branch** — extend the existing handler at signal_flow_editor.js:1549. Order: (a) text-edit mode active → cancel/auto-delete first; (b) boundary draw active → `commitOrCancelBoundary()` then `exitBoundaryMode()`; (c) fall through to existing selection-clear + picker-close behavior. **`evt.preventDefault()` MUST be called inside (a) and (b)** so the existing selection-clear at signal_flow_editor.js:1397+ does not fire.
7. **Existing rubber-band guard (Risk #1 — most-likely-forgotten edit):** add `if (drawState.active) return;` at the **top** of the rubber-band handler at signal_flow_editor.js:1500–1501, right after the existing `if (panState.spaceDown || evt.button !== 0) return;`.

---

### Region D — JS inspector mode panels (`planner/static/planner/js/signal_flow_editor.js`)

**Role:** Right-side inspector — `setInspectorMode('boundary' | 'text')` branches + lazy-built `buildBoundaryModeBlock` / `buildTextModeBlock` + `refreshBoundaryModeBlock(cell)` / `refreshTextModeBlock(cell)`.

**Closest analog:** Phase 9 `buildNodeModeBlock` + `setInspectorMode('node')` branch at signal_flow_editor.js:1980–2056 + 2213–2235. EXACT template clone with two new mode branches.

**Reference template — `setInspectorMode('node')` (signal_flow_editor.js:2213–2235):**

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
  if (!portAuthorBlock) buildPortAuthorBlock();
  portAuthorBlock.style.setProperty('display', 'block', 'important');
  refreshPortAuthorBlock(cell);
}
```

**Existing `.sfd-segmented` HTML pattern (editor.html:134–140 — connector signal-type picker):**

```html
<div class="sfd-field">
  <label>Direction</label>
  <div class="sfd-segmented" role="group" aria-label="Connector direction">
    <button type="button" id="sfd-dir-forward" data-active="true">Source &rarr; Target</button>
    <button type="button" id="sfd-dir-bidir">Bidirectional</button>
  </div>
</div>
```

**Existing `.sfd-segmented` CSS (signal_flow.css:281–301):**

```css
.sfd-segmented {
  display: inline-flex !important;
  border: 1px solid #444 !important;
  border-radius: 4px !important;
  overflow: hidden !important;
}
.sfd-segmented button {
  background-color: #1a1a2a !important;
  color: #eee !important;
  border: none !important;
  padding: 6px 10px !important;
  font-size: 11px !important;
  cursor: pointer !important;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif !important;
}
.sfd-segmented button[data-active="true"] {
  background-color: #0d9488 !important;
  color: #fff !important;
}
```

**Planner change directive:**
1. Extend `setInspectorMode` switch at signal_flow_editor.js:2199 with two new `else if` branches (`'boundary'` and `'text'`). Verbatim bodies in RESEARCH §R-08 lines 728–754. Both branches MUST hide ALL existing mode blocks (`nodeModeBlock`, `portAuthorBlock`, `connectorFieldRows`) via `style.setProperty('display','none','important')` before showing the new block.
2. `buildBoundaryModeBlock` — lazy-built ONCE per page. 2 fields: `Color` (4×2 swatch grid, 8 colors), `Line style` (4-button segmented with inline SVG `<line>` previews). Verbatim body in RESEARCH §R-08 lines 670–717.
3. `buildTextModeBlock` — parallel: 2 fields: `Color` (3×3 swatch grid, 9 colors including white), `Font size` (3-button S/M/L segmented). No line-style block.
4. **`refreshBoundary/TextModeBlock(cell)`** — called on every entry; syncs `data-active="true"` on the swatch matching `cell.prop('color')` and on the segmented button matching `cell.prop('lineStyle')` / `cell.prop('fontSize')`.
5. **`onSelectionChanged` extension** at signal_flow_editor.js:1862 — add two new branches BEFORE the existing `isElement` branch: `cell.get('type') === 'showstack.BoundaryLine'` → `setInspectorMode('boundary', cell)` + `attachBoundaryVertexTools(cell)`; `cell.get('type') === 'showstack.TextLabel'` → `setInspectorMode('text', cell)`. Verbatim in RESEARCH §R-03 lines 428–443.

---

### Region E — JS edit lifecycle: text inline-edit overlay (`planner/static/planner/js/signal_flow_editor.js`)

**Role:** `enterTextEditMode(cell)` creates a transient HTML `<input>` overlay positioned absolutely over the cell's screen bbox; commit / cancel writes back to `cell.attr('label/text')` and triggers autosave; empty body auto-deletes the cell (D-18).

**Closest analog:** No direct in-tree analog for HTML-overlay-on-SVG (Phase 10's autocomplete is the closest discipline — focus/commit/cancel pattern, synthetic-event dispatch). The class of pattern is novel but the focus-and-commit flow mirrors `selectAcRow` at signal_flow_editor.js:1908–1915.

**Reference — Phase 10 synthetic-event commit pattern (signal_flow_editor.js:1908–1915):**

```javascript
function selectAcRow(rowEl, label) {
  var chosen = label || (rowEl.querySelector('span') && rowEl.querySelector('span').textContent) || '';
  circuitLabelInput.value = chosen;
  closeAcListbox();
  // D-14: dispatch synthetic input event so existing Phase 9 inspector listener fires.
  circuitLabelInput.dispatchEvent(new Event('input', { bubbles: true }));
}
```

**Reference — `paper.localToPaperRect` use (JointJS API; new to ShowStack but documented):**

```javascript
var screenBbox = paper.localToPaperRect(cell.getBBox());
input.style.left   = screenBbox.x + 'px';
input.style.top    = screenBbox.y + 'px';
input.style.width  = screenBbox.width  + 'px';
input.style.height = screenBbox.height + 'px';
```

**Planner change directive:**
1. **`<input type="text">`** — NOT `contenteditable` (D-18 single-line). Append to `paperEl.parentNode` (HTML overlay must be HTML, not SVG child).
2. **Position absolutely** via `paper.localToPaperRect(cell.getBBox())`. Font-size + color set inline via `setProperty('important')` matching cell's `fontSize` + `color` props.
3. **Hide SVG glyph during edit** — `cell.attr('label/display', 'none')`. Restore on commit/cancel.
4. **Commit triggers:** `blur` event + `keydown` where `evt.key === 'Enter'`. On commit: if `input.value.trim() === ''` → `cell.remove()`; else → `cell.attr('label/text', value)` + auto-fit width via Canvas-2D `measureText` (RESEARCH §R-02 step 4).
5. **Cancel triggers:** `keydown` where `evt.key === 'Escape'`. If newly placed (no prior text) → `cell.remove()`; else → discard input value, restore SVG.
6. **Re-entry from D-17** — `paper.on('element:pointerdblclick', ...)` checking `cell.get('type') === 'showstack.TextLabel'` → `enterTextEditMode(cell)`.
7. **Risk #5 mitigation** — force-commit (call `commit()`) on any zoom or pan event during active edit (Phase 7 zoom/pan handlers; gate via `inTextEdit` flag).

---

### Region F — JS selection + autosave wiring (`planner/static/planner/js/signal_flow_editor.js`)

**Role:** Wire selection events to inspector + vertex tools; wire mutations to `scheduleAutosave`.

**Closest analog:** Phase 11 `change:size` listener at signal_flow_editor.js:2411 + Phase 9 graph-events line at signal_flow_editor.js:2403.

**Reference — Phase 11 graph-event registration (signal_flow_editor.js:2401–2411):**

```javascript
// Phase 11 — change:size added so programmatic resizes (Plan 11-06 auto-expand)
// trigger autosave even when the engineer didn't release a pointer.
graph.on('add remove change:source change:target change:size', scheduleAutosave);

paper.on('element:pointerup', scheduleAutosave);

graph.on('change:size', function (cell) {
  // ...
});
```

**Planner change directive:**
1. **DO NOT add `change:vertices` to the comma-separated event string at line 2403** — Risk #6 warns naïve listening produces an infinite loop with auto-render. Instead, add a STANDALONE listener that re-renders + refreshes tools + calls `scheduleAutosave()` explicitly (RESEARCH §R-03 lines 416–422):
   ```javascript
   graph.on('change:vertices', function (cell) {
     if (cell.get('type') !== 'showstack.BoundaryLine') return;
     applyBoundaryRender(cell);
     var view = cell.findView(paper);
     if (view) view.updateTools();
     scheduleAutosave();
   });
   ```
2. **Session-sticky defaults (R-09)** — declare 4 closure-scoped vars at signal_flow_editor.js:2258 area:
   ```javascript
   var lastBoundaryColor = '#000000';      // D-09 initial
   var lastBoundaryStyle = 'solid';        // D-12 initial
   var lastTextSize      = 16;             // D-19 medium default
   var lastTextColor     = '#000000';      // D-19 black default
   ```
   Every inspector swatch/segmented click writes BOTH to the cell AND to the `last*` var (mutate-sticky-defaults BEFORE schedulering autosave — Pattern Violation #1 below).
3. **Z-order (R-10)** — after `graph.addCell(boundaryCell)`: `cell.toBack()`. After `graph.addCell(textCell)`: `cell.toFront()`. Both write to `cell.attributes.z` which survives `graph.toJSON()` round-trip with no other code change.

---

### HTML toolbar insertion (`planner/templates/planner/signal_flow/editor.html`, between lines 58 and 60)

**Role:** Insert a new `.sfd-btn-group[data-group="create"]` between the history group and the right-aligned spacer.

**Closest analog:** The 5 existing toolbar groups at editor.html:45–67. The history group at editor.html:56–58 is the structural neighbor.

**Reference — existing history group (editor.html:55–59):**

```html
<span class="sfd-toolbar-divider"></span>
<div class="sfd-btn-group" data-group="history">
  <button type="button" id="sfd-undo" aria-label="Undo (Ctrl/Cmd+Z)" disabled>&#x21B6;</button>
  <button type="button" id="sfd-redo" aria-label="Redo (Ctrl/Cmd+Shift+Z)" disabled>&#x21B7;</button>
</div>
<span class="sfd-toolbar-spacer"></span>      <!-- right-align everything after this -->
```

**Reference — `is-active` + `aria-pressed` mode-button pattern (editor.html:53):**

```html
<button type="button" id="sfd-snap-toggle" class="is-active"
        aria-label="Snap to grid: on" aria-pressed="true">&#x229E;</button>
```

**Planner change directive — insert AFTER line 59 (`</div>` of history group) and BEFORE line 60 (`<span class="sfd-toolbar-spacer">`):**

```html
<span class="sfd-toolbar-divider"></span>
<div class="sfd-btn-group" data-group="create">
  <button type="button" id="sfd-tool-boundary" aria-label="Draw boundary" aria-pressed="false">&#x29C8;</button>
  <button type="button" id="sfd-tool-text"     aria-label="Place text"     aria-pressed="false">T</button>
</div>
```

**Critical:**
- `aria-pressed="false"` initial state — flipped to `"true"` by `enterBoundaryMode` / `enterTextMode` (Region C).
- `class="is-active"` is added/removed by JS, NOT set in the template (matches `#sfd-snap-toggle` initial-active being a snap-specific case where snap is on by default).
- Glyphs picked from Unicode (boundary ⧈ U+29C8 or similar polyline glyph; text "T" or "𝐓"); planner picks final glyph.

---

### CSS Sections 17 + 18 (`planner/static/planner/css/signal_flow.css`, append after line 875)

**Role:** Toolbar mode-button styling (mostly inherited from Section 1), inspector color-swatch grid, line-style segmented previews, font-size segmented, inline-edit overlay.

**Closest analog:** Phase 11 Sections 14/15/16 — append-at-end convention. Section 4 `.sfd-segmented` (lines 281–301) is the reused base; Sections 17/18 only ADD new classes (no overrides of existing segmented rules).

**Reference — existing toolbar `.is-active` rule that the new buttons inherit (signal_flow.css:84–87):**

```css
#sfd-toolbar button.is-active {
  background-color: #0d9488 !important;
  color: #fff !important;
}
```

**Reference — Section header convention (verbatim format from Section 13 at signal_flow.css:677–681):**

```css
/* =========================================================================
   SECTION 13 — Export button group (Phase 10 EXP-01)
   Right-aligned toolbar group containing the PNG export button. Group
   scaffolded for future PDF / SVG buttons (v2.4+).
   ========================================================================= */
```

**Planner change directive:**
1. **Update section-list comment** at signal_flow.css:21–37 — add entries 17 and 18 + the Section-7 amend note. Verbatim block in RESEARCH §R-12 lines 858–878.
2. **Append Section 17 after line 875** — Verbatim block in RESEARCH §R-12 lines 883–930. Includes `.sfd-color-swatches` (4×2 grid), `.sfd-color-swatch`, `.sfd-color-swatch[data-active="true"]` (teal inset ring), inline SVG line-style preview rules. **Every `color:` and `background-color:` declaration MUST use the dark-navy palette (`#eee` text, `#aaa` muted) per user MEMORY Phase 11 GAP-11.7 rule** — Pattern Violation #4 below.
3. **Append Section 18 after Section 17** — Verbatim block in RESEARCH §R-12 lines 938–959. Includes `.sfd-text-edit-overlay` (positioned absolute, teal border), `.sfd-text-fontsize-segmented` button[data-size] sizes, `.sfd-color-swatches--text` 3×3 grid override.
4. **DO NOT edit Section 7 port hover-reveal** — Phase 11's amendment at signal_flow.css:489+ stays as-is.

---

### `planner/views.py` (READ-ONLY this phase — verified pass-through at line 7693)

**Role:** Phase 12 confirms — does NOT modify — the existing IDOR allowlist branch.

**Closest analog:** n/a — this is the read-only target that the test file locks in.

**Verbatim code at `planner/views.py:7686–7693` (R-04 evidence):**

```python
cells = canvas_state.get('cells') or []
for cell in cells:
    prop = cell.get('showstack') if isinstance(cell, dict) else None
    if not isinstance(prop, dict):
        continue                                 # ← cells without `showstack` dict bypass
    ct_id = prop.get('contentTypeId')
    obj_id = prop.get('objectId')
    if not ct_id or not obj_id:
        continue                                 # ← cells without GFK bypass (THIS is the branch)
    # ... allowlist check only runs when ct_id AND obj_id are present ...
```

**Planner change directive:** **NO edits.** Plan MUST contain an explicit "do not modify" task for this file. The pass-through behavior is regression-locked by the new test file (Region G).

---

### `planner/tests/test_signal_flow_phase12.py` (NEW)

**Role:** Backend regression tests for the IDOR-pass-through behavior + the canvas_state round-trip for BoundaryLine + TextLabel cells.

**Closest analog:** `planner/tests/test_signal_flow_phase9.py` `_Phase9Base` class. Phase 10 followed the same pattern.

**Reference — existing test base pattern (`_Phase9Base` setUp signature):**

```python
class _Phase9Base(TestCase):
    """Common setUp: user, project, project membership, login, session-current-project."""
    def setUp(self):
        # ... User.objects.create_user, Project.objects.create,
        # ProjectMember.objects.create(role='editor'),
        # self.client.force_login(self.user),
        # session = self.client.session; session['current_project_id'] = ...; session.save()
        ...

    def _post_autosave(self, payload, if_match='1'):
        return self.client.post(
            reverse('planner:signal_flow_autosave', args=[self.diagram.id]),
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_IF_MATCH=if_match,
        )
```

**Planner change directive — create file with 4 tests (RESEARCH §R-13 lines 982–1024):**

1. `test_boundary_only_canvas_state_round_trips` — POST a canvas_state with only a BoundaryLine cell (no equipment GFK); assert HTTP 200, `data['ok'] is True`, `data['version'] == 2`.
2. `test_text_only_canvas_state_round_trips` — POST a canvas_state with only a TextLabel cell; assert HTTP 200.
3. `test_mixed_boundary_text_equipment_round_trip` — POST a canvas_state with BoundaryLine + TextLabel + Console (with valid `contentTypeId`/`objectId` scoped to `current_project`); assert HTTP 200 (proves allowlist walk skips decorative cells AND runs IDOR on the Console).
4. `test_boundary_with_invalid_color_still_saves` — POST with `color: 'not-a-real-hex'`; assert HTTP 200 (locks in "server is opaque to canvas_state JSON").

---

### `.planning/REQUIREMENTS.md` Traceability table (lines 110–136)

**Role:** Mark DRAW-01..04 + TXT-01..03 as `Phase 12 → Done` after phase completion.

**Closest analog:** Phase 11's amendment that marked PORT-01..06 + SHP-RESIZE-01..03 as done in the same table.

**Planner change directive:** Edit the 7 row entries in the traceability table — flip "Planned" → "Done" with phase number `12`. Make this edit in the FIRST plan that touches REQUIREMENTS.md so downstream plans, the verifier, and audit see the corrected status.

---

## Shared Patterns

### Admin-DOM `!important` style writes (CLAUDE.md mandate)

**Source:** CLAUDE.md "Overriding Django admin CSS from JavaScript" + 28+ occurrences in `signal_flow_editor.js` + Phase 11 GAP-11.7 user MEMORY rule.

**Apply to:** EVERY style write Phase 12 makes on inspector HTML elements (`#sfd-tool-boundary`, `#sfd-tool-text`, `.sfd-color-swatch`, segmented buttons, `.sfd-text-edit-overlay`) AND the `#sfd-paper` cursor change (D-07).

**Reference call sites (signal_flow_editor.js:1468, 1474–1478, 2218 etc.):**

```javascript
nodeModeBlock.style.setProperty('display', 'none', 'important');
nodeRelinkBtn.style.setProperty('display', 'block', 'important');
nodeRelinkBtn.style.setProperty('cursor', 'pointer', 'important');
paperEl.style.setProperty('cursor', 'crosshair', 'important');     // Phase 12 D-07 mode-on
```

**Rule:** Never use `el.style.display = '…'` shorthand on `.sfd-*` HTML elements inside the inspector or `#sfd-paper`. Always `el.style.setProperty(prop, value, 'important')`. JointJS SVG inside `#sfd-paper` (polyline strokes, vertex-handle circles, text glyphs) is NOT in the admin namespace and does NOT need `!important` — but Sections 17 and 18 use `!important` defensively per file-header convention.

---

### Autosave + debounce + If-Match wiring

**Source:** `planner/static/planner/js/signal_flow_editor.js:2401–2411` (Phase 11 extended Phase 9 listener line).

**Apply to:** EVERY Phase 12 mutation:
- Mode entry/exit (no autosave needed — UI only).
- `commitOrCancelBoundary()` → `graph.addCell()` → fires `graph 'add'` → autosave fires from existing listener (line 2403).
- Vertex drag → `model.prop('vertices', verts)` → fires `change:vertices` → Phase 12 standalone listener calls `scheduleAutosave()` explicitly (NOT added to the line-2403 comma-list — Risk #6).
- Inspector color/style swatch click → mutate `cell.prop(...)` → call `scheduleAutosave()` explicitly.
- Text edit commit → `cell.attr('label/text', value)` → fires `change:attrs` → existing autosave catches via toJSON.
- Text inline-edit Esc-cancel → `cell.remove()` → fires `graph 'remove'` → autosave fires from existing listener.

**Reference (signal_flow_editor.js:2403):**

```javascript
graph.on('add remove change:source change:target change:size', scheduleAutosave);
paper.on('element:pointerup', scheduleAutosave);
```

**Rule:** Do NOT extend the comma-separated event list with `change:vertices` (Risk #6 — naïve listening causes infinite loop with `applyBoundaryRender` write-back). Phase 12 mutations that aren't covered by the line-2403 events MUST call `scheduleAutosave()` explicitly in their handler.

---

### Beginning/ending undo batch on multi-step mutations

**Source:** Phase 9 `nodeDeleteBtn` click handler at signal_flow_editor.js:1502–1517 + `window.__sfd.undo.beginBatch / endBatch` at signal_flow_editor.js:1759–1763.

**Apply to:** Phase 12 mutations that touch multiple cells in one gesture (text inline-edit cancel-of-just-placed cell is a 1-op delete = no batch needed; `commitOrCancelBoundary` is a 1-op addCell = no batch needed). **For v2.3 scope, no Phase 12 mutation needs a batch.** This pattern is documented here for the verifier's reference only.

**Reference (signal_flow_editor.js:1502–1517):**

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
  ...
});
```

---

### Lazy-build with null-guard

**Source:** Phase 9 `buildNodeModeBlock` at signal_flow_editor.js:1980 + Phase 11 `buildPortAuthorBlock`.

**Apply to:** `buildBoundaryModeBlock` and `buildTextModeBlock`.

**Reference (signal_flow_editor.js:1463–1464):**

```javascript
function buildNodeModeBlock() {
  if (!inspectorEl) return;       // ← null-guard
  ...
}
```

**Rule:** every Phase 12 DOM-touching helper opens with `if (!inspectorEl) return;`. Cache the built block (`if (!boundaryModeBlock) buildBoundaryModeBlock();`) — never rebuild on every show.

---

### XSS-safe textContent over innerHTML

**Source:** Phase 10 autocomplete row render at signal_flow_editor.js:1873–1888 + Phase 11 PATTERNS.md security rule.

**Apply to:** ALL Phase 12 inspector rendering — `<label>` text, swatch `aria-label`, font-size button letter ("S"/"M"/"L"). Even though Phase 12 has no user-input strings in the inspector (palettes are fixed literals), maintaining the discipline prevents a future copy-paste regression.

**Reference (signal_flow_editor.js:1873–1888 paraphrase):**

```javascript
var labelSpan = document.createElement('span');
labelSpan.textContent = rec.label || '';     // XSS-safe
```

**Exception:** `renderLineStylePreviewSVG(s)` (line-style segmented button content) IS a string of SVG markup. Use `innerHTML` ONLY for the fixed-literal `<svg>` snippets generated by Phase 12 itself — never with any user input. Document the exception with an inline comment on the call.

---

### Cell-class registration order

**Source:** Phase 8 inline comment at signal_flow_editor.js:88 (PITFALLS §1) + verified by reading lines 622–770.

**Apply to:** `BoundaryLine` + `TextLabel` class definitions.

**Rule:** Register BoundaryLine + TextLabel BEFORE `new joint.dia.Graph(...)` at signal_flow_editor.js:770. All 7 existing classes are registered between lines 622–761; Phase 12 appends the 2 new classes in the same block (after Amp at line 761, before the graph instantiation).

---

## CSS Append-at-End Pattern

**Source:** `planner/static/planner/css/signal_flow.css:1–37` file header + current Sections 1–16.

**Reference — file-header `!important` mandate (signal_flow.css:1–17):**

```css
/*
 * signal_flow.css — Phase 8 chrome for the Signal Flow Diagrammer editor.
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

**Reference — Section header format (signal_flow.css:677–681):**

```css
/* =========================================================================
   SECTION 13 — Export button group (Phase 10 EXP-01)
   ...
   ========================================================================= */
```

**Planner change directive:**
1. Update file-header section-list at lines 21–37 to enumerate Sections 17 + 18 (+ the Section-7 amend cross-reference).
2. Append Section 17 (boundary lines) AFTER line 875 — the current end of file post-Phase-11. Section 17 contains: toolbar `.is-active` inheritance (no new selector needed — line 84 covers it), `.sfd-color-swatches` 4×2 grid, `.sfd-color-swatch[data-active="true"]` teal-inset ring, `.sfd-segmented button[data-style]` inline SVG sizing.
3. Append Section 18 (text annotations) AFTER Section 17. Section 18 contains: `.sfd-text-edit-overlay` (position: absolute, teal border, transparent bg), `.sfd-text-fontsize-segmented` per-button font-size letter scaling, `.sfd-color-swatches--text` 3×3 grid override.

---

## No Analog Found

| File / Need | Why no in-tree analog | Recommended source |
|-------------|----------------------|--------------------|
| HTML `<input>` overlay positioned over a JointJS SVG cell bbox | ShowStack has zero HTML-overlay-on-SVG patterns. Phase 10's `<input>` is positioned by CSS in a static `.sfd-field` slot, not over a paper cell. | RESEARCH §R-02 lines 280–296 + §R-07. `paper.localToPaperRect(cell.getBBox())` is documented JointJS API; the overlay discipline (focus → blur/Enter commit → Esc cancel → auto-delete empty) is well-trodden in Figma/Lucidchart references. |
| Closure-scoped pen-tool state machine over `paper.on('blank:pointerdown' \| 'blank:pointermove' \| 'blank:pointerdblclick')` | No existing multi-click-with-live-preview interaction. Rubber-band rect is single-drag; no other tool accumulates multi-vertex state. | Pattern-clone of rubber-band rect at signal_flow_editor.js:1500–1544 (SVG live preview, document-level `mousemove`/`mouseup`). Verbatim state machine in RESEARCH §R-06. |
| Per-segment unit-normal math for double-line rendering | Phase 12 ships the (0,+3)-y-offset cheat per Risk #3. | Marked as v2.3 ship-it. If UAT reveals the cheat looks wrong on vertical/diagonal boundaries, per-segment normal math lands as a follow-up `applyBoundaryRender` change with no public-API impact. |

---

## Pattern Violation Guardrails

These are the 1–2 lines per pattern that, if the executor gets wrong, will cause silent bugs. Each is a verbatim restatement of a Risk in RESEARCH.md or a user MEMORY rule.

### Violation 1 — Sticky-default mutation timing

**Where:** Inspector swatch + segmented click handlers in Region D.

**Rule:** **Mutate `lastBoundaryColor` / `lastBoundaryStyle` / `lastTextSize` / `lastTextColor` BEFORE schedulering autosave** — otherwise the next-drawn boundary inherits the prior value (the new value is in the cell but not yet in the sticky-default var when `commitOrCancelBoundary` reads it).

**Correct order:**
```javascript
lastBoundaryColor = newHex;            // 1. sticky default FIRST
cell.prop('color', newHex);            // 2. cell mutation
applyBoundaryRender(cell);             // 3. SVG render
scheduleAutosave();                    // 4. autosave LAST
```

### Violation 2 — Rubber-band guard

**Where:** Existing `paper.on('blank:pointerdown', ...)` rubber-band handler at signal_flow_editor.js:1500.

**Rule:** **Add `if (drawState.active) return;` to the existing rubber-band-selection handler — JointJS has no stopPropagation analog.** Both the Phase 12 pen-tool listener and the existing rubber-band listener fire on the same `blank:pointerdown` event, and the guard must live inside the rubber-band handler itself.

**Correct edit (insert as line 2 of the rubber-band handler, BEFORE the existing `if (panState.spaceDown ...)`):**
```javascript
paper.on('blank:pointerdown', function (evt, x, y) {
  if (drawState.active) return;                              // <-- Phase 12 ADD
  if (panState.spaceDown || evt.button !== 0) return;        // existing
  ...
});
```

### Violation 3 — Paper cursor `!important`

**Where:** `enterBoundaryMode` / `enterTextMode` / `exitBoundaryMode` / `exitTextMode` in Region C.

**Rule:** **Set `paperEl.style.setProperty('cursor', 'crosshair', 'important')` for the `#sfd-paper` cursor change — admin CSS overrides need `!important` from JS per CLAUDE.md.** The shorthand `paperEl.style.cursor = 'crosshair'` will be silently overridden by django-admin-interface.

**Correct call:**
```javascript
paperEl.style.setProperty('cursor', 'crosshair', 'important');   // enter
paperEl.style.setProperty('cursor', '', 'important');            // exit (empty string clears)
```

### Violation 4 — Dark-navy inspector palette audit

**Where:** Sections 17 + 18 in `signal_flow.css`.

**Rule:** **Audit every CSS `color:` and `background-color:` declaration against the dark-navy inspector palette per user MEMORY Phase 11 GAP-11.7 rule** — `#eee` primary text, `#aaa` muted labels/help, NOT Django-admin light-bg defaults. The inspector lives on a dark surface; any light-bg default leaks contrast bugs that the Phase 11 UAT caught twice.

**Correct pattern (Section 17 swatch label example):**
```css
.sfd-field--boundary label {
  color: #aaa !important;       /* muted label — dark-navy palette */
  font-size: 11px !important;
}
```

### Violation 5 — `change:vertices` listener placement

**Where:** Graph-event listener for vertex drags in Region F.

**Rule:** **Do NOT add `change:vertices` to the comma-separated event string at signal_flow_editor.js:2403** — naïve listening causes an infinite loop because `applyBoundaryRender` writes back to `cell.attr(...)` which can re-fire mutations. The Phase 12 listener MUST be a standalone `graph.on('change:vertices', function(cell) { ... })` that explicitly calls `scheduleAutosave()` at the end.

**Correct registration:**
```javascript
// CORRECT — standalone listener that re-renders + calls scheduleAutosave explicitly:
graph.on('change:vertices', function (cell) {
  if (cell.get('type') !== 'showstack.BoundaryLine') return;
  applyBoundaryRender(cell);
  var view = cell.findView(paper);
  if (view) view.updateTools();
  scheduleAutosave();
});

// WRONG — do NOT extend the existing listener:
// graph.on('add remove change:source change:target change:size change:vertices', scheduleAutosave);
```

### Violation 6 — Cell-class registration order

**Where:** Region A — BoundaryLine + TextLabel registration.

**Rule:** **Register BoundaryLine + TextLabel BEFORE `new joint.dia.Graph(...)` at signal_flow_editor.js:770** — JointJS requires shape classes registered before the cell appears in `graph.fromJSON()` (PITFALLS §1 inline comment at signal_flow_editor.js:88). Saved diagrams with BoundaryLine cells will fail to load if the class isn't registered in time.

### Violation 7 — Vertex array mutation

**Where:** `BoundaryVertex.setPosition` in Region B.

**Rule:** **`cell.prop('vertices')` returns the LIVE array reference, not a copy.** Mutating it in place bypasses `change:vertices` and breaks autosave + tool refresh.

**Correct slice-then-mutate:**
```javascript
setPosition: function (view, coordinates) {
  var model = view.model;
  var verts = (model.prop('vertices') || []).slice();   // <-- .slice() COPY
  verts[this.options.vertexIndex] = { x: newX, y: newY };
  model.prop('vertices', verts);                          // setter fires change:vertices
}
```

### Violation 8 — Esc keydown handler ordering

**Where:** Esc keydown branch in Region C (extends signal_flow_editor.js:1549).

**Rule:** **Order the new Esc branches to fire BEFORE the existing selection-clear logic — early-exit with `evt.preventDefault()` when draw/text mode is active.** Three Esc-handlers compete (existing picker-modal close, existing selection-clear, new draw/text exit); the new branches must claim the event before the others see it.

**Correct branch ordering:**
```javascript
document.addEventListener('keydown', function (evt) {
  if (/INPUT|TEXTAREA|SELECT/.test(evt.target.tagName)) {
    // EXCEPTION: the text-edit overlay <input> IS the active element
    // during text edit; Esc inside it MUST cancel-edit, not be filtered out.
    if (evt.key === 'Escape' && inTextEdit) { cancelTextEdit(); evt.preventDefault(); return; }
    return;
  }
  if (evt.key === 'Escape' && drawState.active) {
    commitOrCancelBoundary();
    exitBoundaryMode();
    evt.preventDefault();
    return;                                  // pre-empts selection-clear
  }
  // ... existing picker-close + selection-clear logic ...
});
```

---

## Pattern Coverage Summary

| Phase 12 sub-pattern | Closest analog | Match quality |
|----------------------|----------------|---------------|
| `BoundaryLine` cell class | Phase 8 Console template at signal_flow_editor.js:622–639 | exact (markup→defaults→deepSupplement clone) |
| `TextLabel` cell class | Phase 8 Console template | exact |
| `applyBoundaryRender` helper | n/a — novel for Phase 12 | RESEARCH §R-01 verbatim |
| `BoundaryVertex` elementTools.Control subclass | Phase 11 `CornerResize` at signal_flow_editor.js:537–597 | exact (swap corner→vertexIndex, size→prop('vertices')) |
| `attachBoundaryVertexTools` | Phase 11 `attachResizeTools` | exact |
| Pen-tool draw-mode state machine | Phase 8 rubber-band rect at signal_flow_editor.js:1500–1544 | exact (SVG live preview pattern) |
| `enterBoundaryMode` / `enterTextMode` toolbar wiring | Phase 8 `#sfd-snap-toggle` `is-active` + `aria-pressed` pattern | exact |
| `setInspectorMode('boundary' \| 'text')` branches | Phase 9 `setInspectorMode('node')` at signal_flow_editor.js:2213–2235 | exact (template clone) |
| `buildBoundaryModeBlock` / `buildTextModeBlock` | Phase 9 `buildNodeModeBlock` at signal_flow_editor.js:1980–2056 | exact |
| Color-swatch + segmented `data-active="true"` visual | Phase 8 `.sfd-segmented button[data-active="true"]` at signal_flow.css:298 | exact |
| Inline-edit overlay `<input>` lifecycle | n/a — novel; closest is Phase 10 `selectAcRow` synthetic event | role-match |
| `paper.on('element:pointerdblclick', ...)` for re-entry | Phase 9 paper-event use at signal_flow_editor.js:1473 | exact |
| `change:vertices` standalone listener | Phase 11 `change:size` listener at signal_flow_editor.js:2411 | exact |
| Session-sticky default closure vars | Phase 9 `conflicted` / `diagramDirty` / `currentVersion` closure state at signal_flow_editor.js:2258 | exact |
| `cell.toBack()` / `cell.toFront()` z-order | n/a — first use in editor | JointJS 4.2.4 documented API |
| Section 17 + 18 CSS append | Phase 11 Sections 14/15/16 append convention | exact |
| Toolbar `.sfd-btn-group` insertion | Phase 8/9/10 toolbar groups at editor.html:45–67 | exact |
| `test_signal_flow_phase12.py` file structure | `test_signal_flow_phase9.py` `_Phase9Base` | exact |

---

## Metadata

**Analog search scope:**
- `planner/static/planner/js/signal_flow_editor.js` (read of regions 80–124, 537–770, 1495–1544, 1862–1894, 1980–2056, 2199–2235, 2401–2411)
- `planner/static/planner/css/signal_flow.css` (read of regions 1–117, 281–301, 677–875 — full section header survey)
- `planner/templates/planner/signal_flow/editor.html` (read of toolbar region 40–74)
- `planner/views.py:7686–7726` (verified at RESEARCH §R-04 read; pass-through confirmed)
- `planner/tests/test_signal_flow_phase9.py` (file-structure analog for the new test file)
- `.planning/phases/12-boundaries-and-text/12-CONTEXT.md`
- `.planning/phases/12-boundaries-and-text/12-RESEARCH.md`
- `.planning/phases/11-ports-and-resize/11-PATTERNS.md` (template for this document)

**Files scanned:** 6 source files + 3 planning docs.
**External analog citations:** 0 — every Phase 12 sub-pattern has an in-tree Phase 8/9/10/11 precedent.
**Pattern extraction date:** 2026-05-25.
