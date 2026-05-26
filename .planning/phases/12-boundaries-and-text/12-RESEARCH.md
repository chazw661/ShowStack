# Phase 12 Research: Boundary Lines + Text Annotations

**Researched:** 2026-05-25
**Domain:** JointJS 4.2.4 custom-element authoring inside an established IIFE (signal_flow_editor.js)
**Confidence:** HIGH — all critical findings verified by direct read of the in-tree code and the locked Phase 9/10/11 patterns.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**A. Drawing UX**
- **D-01:** Sticky draw mode. Toolbar button enters draw-boundary mode; exits on Esc, re-click of the same button, or click of another mode button.
- **D-02:** Click-each-vertex pen-tool input. Double-click OR Esc commits. Minimum 2 vertices.
- **D-03:** Vertices snap to 20px grid when the snap toggle is on (Phase 8 D-13 parity).
- **D-04:** New "creation tools" toolbar group between `#sfd-redo` and the right-aligned spacer, containing `#sfd-tool-boundary` and `#sfd-tool-text`, wrapped in `.sfd-toolbar-divider`s.
- **D-05:** Esc mid-polyline commits at current vertex if ≥2 vertices placed; cancels otherwise.
- **D-06:** Vertex-edit handles always visible on a selected boundary; teal `#0d9488` (Phase 11 D-05 parity).
- **D-07:** Visual mode feedback — `.is-active` + `aria-pressed="true"` on toolbar button; `#sfd-paper` cursor → `crosshair` via `setProperty('cursor', 'crosshair', 'important')`.

**B. Color + Line-Style Picker**
- **D-09:** 8-color print-safe palette (Tailwind 600 family): black `#000000`, grey `#666666`, red `#dc2626`, orange `#ea580c`, yellow `#eab308`, green `#16a34a`, blue `#2563eb`, purple `#9333ea`.
- **D-10:** Inspector-only pickers + session-sticky defaults (closure-scoped state in the IIFE).
- **D-11:** "Double" line style = two parallel solid strokes, 3px apart, reshape together on vertex drag.
- **D-12:** Line-style picker = 4 segmented buttons with SVG stroke previews (solid / dashed / dotted / double).

**C. Z-Order / Layering**
- **D-13:** Boundary lines default behind shapes + connectors (low `z`).
- **D-14:** Text annotations default on top of everything (highest `z`).
- **D-15:** No per-element layer overrides in v2.3.

**D. Text Annotation Lifecycle**
- **D-16:** Click → inline edit immediately. Enter / click-outside commits; Esc deletes empty just-placed element.
- **D-17:** Double-click placed text re-enters edit mode. Single-click selects only.
- **D-18:** Single-line only. Enter commits (no newline). Empty commit auto-deletes the cell.
- **D-19:** Font sizes: 12 / 16 / 24 px. Background: transparent. Text palette = D-09 colors + white `#ffffff`.

**E. Carried Decisions (already locked)**
- Canvas state schema — DRAW + TXT cells live inside the existing `SignalFlowDiagram.canvas_state` `cells: []` array. No model migration.
- Autosave — Phase 9 1500ms debounce + If-Match 409 + keepalive flush. No new autosave codepath.
- Snap grid — 20px (Phase 8 D-13).
- Inspector mode switch — Phase 9 `setInspectorMode()`. Phase 12 adds `'boundary'` and `'text'` modes.
- Toolbar group scaffold — Phase 10 D-13 convention.
- CSS section-append rule — append Sections 17 + 18; update the section-list comment.
- System fonts only — `FONT_STACK` constant on signal_flow_editor.js:94.
- Delete / Backspace path — existing handler on signal_flow_editor.js:1549.
- PNG export already covers both (Phase 10 EXP-01).
- IDOR allowlist — boundary/text have no GFK; researcher to verify the existing allowlist passes them through.
- `validateMagnet` / `validateConnection` — boundary declares no magnets; existing rule should auto-reject.

### Claude's Discretion
- JointJS cell-class names — custom showstack classes vs. extending standard.
- Color-swatch layout — 4×2 vs 8×1 vs 9×1.
- Selected-swatch visual — ring, outline, checkmark.
- Stroke-width default — likely 2px.
- Session-sticky storage — closure vs sessionStorage.
- Initial defaults before any sticky value — suggest **boundary: black solid 2px**, **text: medium (16px) black**.
- Vertex-handle hit-target size — visible 6px, hit 12px.
- Clicking outside the canvas mid-sticky-mode = no-op.
- No first-draw toast.
- Text bounding box / drag target — glyph + ~4px padding.

### Deferred Ideas (OUT OF SCOPE)
- Curved boundaries (DRAW-CURVE-01), filled zones (DRAW-FILL-01), rich text, multi-line text, add/delete vertex post-creation, engineer-controlled z-order, toolbar color/style controls, white-pill background, clean-export mode, configurable stroke width, semantic-zone boundaries, right-click context menu.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DRAW-01 | "Draw boundary" toolbar mode → click+each vertex draws polyline; mode exits on Esc or toolbar toggle | R-01 (cell class), R-06 (pen-tool state machine), R-08 (inspector mode panel) |
| DRAW-02 | Each boundary carries editable color (palette of 8) + line-style (solid / dashed / dotted / double) | R-01 (markup), R-08 (inspector controls), R-09 (sticky defaults) |
| DRAW-03 | Select a boundary → edit color + style from right-side inspector (mode-switch from connectors) | R-08 (setInspectorMode('boundary')), R-01 (props live on the cell) |
| DRAW-04 | Drag boundary vertices to reshape; Delete/Backspace deletes | R-03 (vertex-edit handle pattern), Carried Decision: existing Delete handler at signal_flow_editor.js:1549 covers this |
| TXT-01 | Toolbar "Place text" → click → type. Text lives as a JointJS element, not HTML overlay | R-02 (TextLabel cell), R-07 (inline-edit overlay) — overlay is transient input, persisted text is in the SVG cell |
| TXT-02 | Font-size (12 / 16 / 24 px) + text color (D-09 palette + white) | R-02 (cell attrs), R-08 (font-size segmented + color swatches) |
| TXT-03 | Select / drag / edit / delete using same selection + keyboard paths as shapes; edits ride the standard autosave path | R-07 (Enter/Esc/click-out commit), Carried Decision: Delete handler at signal_flow_editor.js:1549; scheduleAutosave hooks at 2403-2404 |
</phase_requirements>

## Summary

Phase 12 ships cleanly on top of the established Phase 8/9/10/11 patterns. The recommended shape is: **two custom `joint.dia.Element` subclasses** (`joint.shapes.showstack.BoundaryLine` and `joint.shapes.showstack.TextLabel`) registered next to the existing seven shape classes; **one new `joint.elementTools.Control` subclass** for per-vertex drag handles, paralleling the Phase 11 `CornerResize` template; and **two new `setInspectorMode()` branches** (`'boundary'` and `'text'`) that build their panels lazily, matching the Phase 9 node-mode lazy-build pattern.

**Critical no-code-change finding:** the existing IDOR allowlist in `planner/views.py:7686-7693` already passes through cells without `showstack.contentTypeId/objectId` via the `continue` on line 7693. **Plan does NOT need to add a new branch** — but the test suite MUST include a round-trip with BoundaryLine + TextLabel cells to lock that behavior in. This is identified as the "most likely silent bug" in CONTEXT.md; the research finding is that the bug does NOT exist today but a future refactor of the allowlist could re-introduce it without a regression test.

**Primary recommendation:** Custom `joint.dia.Element` for both cell types. Authoring two custom shape classes is cheaper than wrestling `joint.shapes.standard.Polyline` to host a sibling double-stroke `<g>` (D-11) and cheaper than coercing `joint.shapes.standard.TextBlock` (which uses an HTML `foreignObject` and would taint the PNG snapshot's font hinting). Custom classes also keep the namespace consistent — every shape in this editor currently lives on `joint.shapes.showstack.*`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Boundary polyline render + vertex drag | Browser (JointJS in `#sfd-paper` SVG) | — | All canvas authoring lives client-side; server is opaque-blob storage. |
| Text annotation render + inline edit | Browser (JointJS SVG + transient `<input>` overlay) | — | Server stores text body only as a `cell.attrs.label.text` field inside `canvas_state` JSON. |
| Color / line-style / font-size editing | Browser (inspector panel writes to `cell.attr` / `cell.prop`) | — | Same locus as Phase 9 connector signal-type picker. |
| Persist DRAW + TXT cells | Browser (graph.toJSON via existing `scheduleAutosave`) → Django (existing `signal_flow_autosave`) | — | Zero new endpoint. Carried Decision: `canvas_state` is opaque JSON to the server. |
| IDOR safety on save | Django (`planner/views.py` allowlist walk) | — | Existing loop skips cells without `showstack.contentTypeId/objectId` (line 7693 `continue`); no new branch needed. |
| Vertex-edit handles | Browser (`joint.elementTools.Control` subclass) | — | Mirrors Phase 11 `CornerResize` at signal_flow_editor.js:537-597. |
| PNG export inclusion | Browser (`html-to-image.toPng(paperEl, …)` at signal_flow_editor.js:2729) | — | Snapshots `#sfd-paper` SVG; new SVG cells flow through with zero code change. |

## Standard Stack

### Core (already vendored — no new installs)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@joint/core` | 4.2.4 (MPL-2.0) | Canvas graph, custom shape classes, elementTools.Control, link tools, paper events | Already the editor's stack — Phases 7–11 all ride this. [VERIFIED: read banner of `planner/static/planner/js/vendor/joint.min.js`] |
| `html-to-image` | 1.11.11 (MIT) | PNG export of `#sfd-paper` SVG | Snapshots include any SVG cell on `#sfd-paper` automatically. [VERIFIED: signal_flow_editor.js:2729-2734] |

**No new Python dependencies.** [VERIFIED: REQUIREMENTS.md line 103]
**No new JS dependencies.** All Phase 12 work is in existing files.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom `joint.dia.Element` for BoundaryLine | Extend `joint.shapes.standard.Polyline` | Polyline expects one `<polyline>` per cell — wedging in D-11's two-parallel-strokes via a sibling element via custom-attrs is uglier than authoring a 2-child markup from the start. [VERIFIED: read of signal_flow_editor.js Polyline-adjacent class patterns lines 622-761] |
| Custom `joint.dia.Element` for TextLabel | Extend `joint.shapes.standard.TextBlock` | TextBlock uses `foreignObject` + HTML — fonts and inline edit are CSS-driven but PNG export via `html-to-image` has known issues with `foreignObject` rendering of webfonts. Plain SVG `<text>` matches Phase 11 port-label rendering exactly. [ASSUMED: html-to-image foreignObject behavior — verified Phase 11 port labels use `<text>`] |

## Critical Implementation Decisions (resolves Claude's Discretion in CONTEXT.md)

### R-01: BoundaryLine cell class — Custom `joint.dia.Element`

**Recommendation: (b) Create a custom `joint.shapes.showstack.BoundaryLine` extending `joint.dia.Element` with two `<polyline>` children inside a `<g>`.**

**Justification:** D-11's double-line style ("two parallel solid strokes, 3px apart, reshape together on vertex drag") needs deterministic control over both polyline children's `points` attribute. With `standard.Polyline`, you'd either (a) post-process the SVG after each render — fragile — or (b) inject a sibling `<polyline>` outside the JointJS markup contract — equally fragile. A 2-child markup authored from the start makes the line-style switch a single `attr` write on the relevant selector(s), and makes the second polyline trivially hide via `display: none` (solid/dashed/dotted) or show (double). This matches the established custom-class pattern at signal_flow_editor.js:622-761 — every other shape in this editor is a custom `joint.dia.Element`.

**Storage of vertices:** custom property `cell.prop('vertices', [{x, y}, {x, y}, ...])`. JointJS `toJSON()` serializes everything under `cell.attributes`, so this survives the canvas_state round-trip (same mechanism as `signalType` / `direction` / `circuitLabel` on SignalLink at signal_flow_editor.js:1607-1611).

**Registration pattern (mirrors signal_flow_editor.js:622-639 Console template):**

```javascript
// signal_flow_editor.js — register AFTER the existing 7 shape classes
// (after Amp at line 761), BEFORE the joint.dia.Graph instantiation at line 770.

// ---- BoundaryLine — decorative polyline, no ports, no magnets (DRAW) ----
// VERTEX STORAGE: cell.prop('vertices') — array of {x, y} in paper-local coords.
// DOUBLE-LINE: `lineSecondary` polyline is `display: none` for solid/dashed/dotted
// and `display: inline` (with same color, no dasharray, 3px y-offset) for 'double'.
joint.shapes.showstack.BoundaryLine = joint.dia.Element.extend({
  markup: [
    { tagName: 'g',        selector: 'lineGroup' },
    { tagName: 'polyline', selector: 'linePrimary' },
    { tagName: 'polyline', selector: 'lineSecondary' },
  ],
  defaults: joint.util.deepSupplement({
    type: 'showstack.BoundaryLine',
    // size + position are NOT meaningful for a polyline; element bbox is computed
    // from the vertices on every render. Set both to 0 so JointJS layout helpers
    // don't accidentally apply (e.g., snapToGrid on cell move). The drag path
    // for the whole boundary moves all vertices in lock-step in JS.
    size: { width: 0, height: 0 },
    attrs: {
      linePrimary: {
        fill: 'none',
        stroke: '#000000',          // D-09 default; sticky default override on creation
        'stroke-width': 2,
        'stroke-dasharray': 'none', // solid initial; updated by applyBoundaryStyle()
        'stroke-linejoin': 'round',
        'stroke-linecap': 'round',
        'pointer-events': 'stroke',  // hit only on the stroke, not the (invisible) inside area
      },
      lineSecondary: {
        fill: 'none',
        stroke: '#000000',
        'stroke-width': 2,
        'stroke-dasharray': 'none',
        'stroke-linejoin': 'round',
        'stroke-linecap': 'round',
        display: 'none',            // hidden unless lineStyle === 'double'
        'pointer-events': 'none',
      },
    },
    // Custom property bag — survives toJSON round-trip (same mechanism as SignalLink props).
    vertices:    [],             // [{x, y}, ...] — paper-local coords
    color:       '#000000',
    lineStyle:   'solid',        // 'solid' | 'dashed' | 'dotted' | 'double'
    strokeWidth: 2,              // fixed at 2 in v2.3; not engineer-configurable
  }, joint.dia.Element.prototype.defaults),
});
```

**Render helper (called on every vertex / style change):**

```javascript
// LINE-STYLE TABLE — drives stroke-dasharray + secondary polyline visibility.
var BOUNDARY_LINE_STYLES = {
  solid:  { dasharray: 'none',  doubleVisible: false },
  dashed: { dasharray: '6 4',   doubleVisible: false },
  dotted: { dasharray: '1 3',   doubleVisible: false },
  double: { dasharray: 'none',  doubleVisible: true  },
};

function applyBoundaryRender(cell) {
  var verts = cell.prop('vertices') || [];
  var primaryPoints = verts.map(function (v) { return v.x + ',' + v.y; }).join(' ');
  // Secondary polyline: same vertex list but offset perpendicular by 3px.
  // For each segment, compute the unit-normal and apply +3px to each endpoint.
  // Cheap approximation for v2.3: shift entire polyline by (0, +3) — visually
  // acceptable for the architectural "double-wall" convention. Per-segment
  // normal math is deferred unless engineers report it looks wrong.
  var secondaryPoints = verts.map(function (v) { return v.x + ',' + (v.y + 3); }).join(' ');
  var style = BOUNDARY_LINE_STYLES[cell.prop('lineStyle') || 'solid'];
  var color = cell.prop('color') || '#000000';

  cell.attr({
    linePrimary: {
      points: primaryPoints,
      stroke: color,
      'stroke-dasharray': style.dasharray,
    },
    lineSecondary: {
      points: secondaryPoints,
      stroke: color,
      display: style.doubleVisible ? 'inline' : 'none',
    },
  });
}
```

**Confidence:** HIGH — matches the established class pattern at signal_flow_editor.js:622-761 verbatim. Markup, defaults, deepSupplement, and the custom-prop bag are all idiomatic JointJS 4.2.4. [VERIFIED: read of in-tree shape definitions]

---

### R-02: TextLabel cell class + inline-edit overlay strategy

**Recommendation: (b) Custom `joint.shapes.showstack.TextLabel` extending `joint.dia.Element` with a single SVG `<text>` child + transient `<input>` overlay for inline edit.**

**Justification:** The persisted text lives in the SVG (TXT-01 requires "lives on the canvas as a JointJS element"). The inline edit (D-16, D-17) is a transient HTML control that appears during the edit gesture and writes its value back to `cell.attr('label/text', value)` on commit. This separates persistence (SVG) from authoring affordance (HTML overlay) cleanly — the engineer sees a blinking caret in an `<input>` overlaid on the cell's screen-coord bbox; everyone else sees the persisted SVG `<text>` only.

**Registration pattern:**

```javascript
// ---- TextLabel — single SVG <text> child + transient HTML <input> for edit (TXT) ----
joint.shapes.showstack.TextLabel = joint.dia.Element.extend({
  markup: [
    { tagName: 'rect', selector: 'hitArea' },   // invisible drag/select target
    { tagName: 'text', selector: 'label' },
  ],
  defaults: joint.util.deepSupplement({
    type: 'showstack.TextLabel',
    size: { width: 60, height: 22 },            // initial — auto-recomputed on text change
    attrs: {
      hitArea: {
        refWidth: '100%', refHeight: '100%',
        fill: 'transparent',
        stroke: 'none',
        // 4px padding around glyph for drag target — D-19 background transparent.
        // Cell size grows around the text via auto-fit (computed on text commit).
      },
      label: {
        refX: '50%', refY: '50%',
        textAnchor: 'middle', textVerticalAnchor: 'middle',
        fontSize: 16,                            // D-19 medium default
        fontFamily: FONT_STACK,                  // system fonts only (PNG-export font-taint)
        fill: '#000000',                         // D-19 black default
        text: '',                                // populated on commit
      },
    },
    // Custom property bag.
    fontSize: 16,
    color:    '#000000',
  }, joint.dia.Element.prototype.defaults),
});
```

**Inline-edit overlay strategy: positioned `<input>` (single-line per D-18), NOT `contenteditable`.**

| Approach | Pros | Cons |
|----------|------|------|
| `<input type="text">` (recommended) | Native Enter / Esc / click-out commit semantics; can be styled to match font size; trivial value read/write; no need for a hidden contenteditable parent | Need to position absolutely + size to the cell's screen bbox |
| `<div contenteditable>` | Inline with the SVG visually; reads font naturally | Multiline by default (D-18 ships single-line) — Enter inserts `<br>`; commit logic must strip newlines; cancel path is messier; tab order is non-trivial |

**Commit / cancel event flow (matches Figma / Lucidchart conventions):**

1. **Enter draw-text mode** → `crosshair` cursor on `#sfd-paper`.
2. **Click on paper** in text-mode →
   - Grid-snap the click coordinates (D-03).
   - Create `TextLabel` cell at snapped position with empty `label.text`. Use `cell.toFront()` (D-14).
   - Apply sticky defaults: `cell.prop('fontSize', lastTextSize); cell.attr('label/fontSize', lastTextSize); cell.prop('color', lastTextColor); cell.attr('label/fill', lastTextColor)`.
   - Immediately call `enterTextEditMode(cell)`.
3. **`enterTextEditMode(cell)`** →
   - Compute the cell's screen-coord bbox via `paper.localToPaperRect(cell.getBBox())`.
   - Create an `<input type="text">`, position absolutely over the bbox, font-size matches the cell's `fontSize` prop, `border: none; background: transparent; outline: none; color: <cell color>`.
   - Append to `paperEl.parentNode` (NOT the SVG — input must be HTML).
   - Set `input.value = cell.attr('label/text') || ''`.
   - `input.focus()`; select all if existing text.
   - Hide the SVG `<text>` during edit (`cell.attr('label/display', 'none')`) so a stale glyph doesn't sit behind the input.
4. **Commit** — `input.addEventListener('blur', commit)` AND `input.addEventListener('keydown', evt => evt.key === 'Enter' && commit())`:
   - If `input.value.trim() === ''` → `cell.remove()` (D-18 auto-delete empty).
   - Else → `cell.attr('label/text', input.value)`; restore display (`cell.attr('label/display', null)`); auto-fit cell width to text via Canvas-2D `measureText` (same pattern as Phase 11 `measureLabelWidth` at signal_flow_editor.js:445-455).
   - Remove the `<input>` from the DOM.
   - `scheduleAutosave()`.
5. **Cancel** — `input.addEventListener('keydown', evt => evt.key === 'Escape' && cancel())`:
   - If the cell was just placed (no prior text) → `cell.remove()`.
   - Else → restore `input.value = previousValue`, but otherwise behave like commit (the input is just torn down without writing).
   - Remove input; restore SVG display.

**Re-entry from selection (D-17):**

```javascript
// Wire to existing paper events — already used by Phase 9 node-mode at signal_flow_editor.js:1473.
paper.on('element:pointerdblclick', function (elementView, evt) {
  var cell = elementView.model;
  if (cell.get('type') === 'showstack.TextLabel') {
    evt.preventDefault();
    enterTextEditMode(cell);
  }
});
```

**Confidence:** HIGH — `<input>` overlay is a well-trodden pattern; the `paper.localToPaperRect` API is documented JointJS surface area. Auto-fit width via measureText is already proven in Phase 11 (signal_flow_editor.js:445-455). [VERIFIED: in-tree measureLabelWidth pattern + paper event use at signal_flow_editor.js:1473]

---

### R-03: Vertex-edit handle implementation — `joint.elementTools.Control` subclass per vertex

**The Phase 11 `CornerResize` class is the exact template.** Phase 12 adds a `BoundaryVertex` `joint.elementTools.Control` subclass that takes a `vertexIndex` option (instead of `corner`) and reads/writes `cell.prop('vertices')[index]` (instead of `cell.size()`).

**Phase 11 CornerResize excerpt (signal_flow_editor.js:537-597) — verbatim:**

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

**Phase 12 BoundaryVertex template (drop next to CornerResize):**

```javascript
// signal_flow_editor.js — add AFTER CornerResize.setPosition() closes at line ~597.

var BoundaryVertex = joint.elementTools.Control.extend({
  children: [{
    tagName: 'circle',
    selector: 'handle',
    attributes: {
      r: 6,                                  // visible radius (D-06 6px)
      fill: '#0d9488',                       // teal — matches Phase 11 D-05
      stroke: '#fff',
      'stroke-width': 1,
      cursor: 'move',
    }
  }, {
    // Transparent hit-area expansion — same approach as Phase 11 CornerResize
    // (handle is 10px visible, hit area is the full SVG rect bounds).
    tagName: 'circle',
    selector: 'hitArea',
    attributes: {
      r: 12,                                  // hit-target 12px (Claude's Discretion)
      fill: 'transparent',
      cursor: 'move',
    }
  }],

  getPosition: function (view) {
    var verts = view.model.prop('vertices') || [];
    var v = verts[this.options.vertexIndex];
    return v ? { x: v.x, y: v.y } : { x: 0, y: 0 };
  },

  setPosition: function (view, coordinates) {
    var model = view.model;
    var idx = this.options.vertexIndex;
    var verts = (model.prop('vertices') || []).slice();   // copy — prop() returns the live array

    var newX = coordinates.x, newY = coordinates.y;
    if (window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled) {
      newX = Math.round(newX / 20) * 20;
      newY = Math.round(newY / 20) * 20;
    }
    verts[idx] = { x: newX, y: newY };
    model.prop('vertices', verts);
    // Re-render both polylines (R-01 applyBoundaryRender) — triggered by
    // the change:vertices listener below; do NOT call here to avoid double-render.
  }
});

// Per-vertex attach/detach — called from onSelectionChanged when selection is
// a single BoundaryLine cell. Mirrors attachResizeTools at signal_flow_editor.js:599-613.
function attachBoundaryVertexTools(cell) {
  if (cell.get('type') !== 'showstack.BoundaryLine') return;
  var view = cell.findView(paper);
  if (!view) return;
  view.removeTools();
  var verts = cell.prop('vertices') || [];
  view.addTools(new joint.dia.ToolsView({
    name: 'sfd-boundary-vertices',
    tools: verts.map(function (_, i) {
      return new BoundaryVertex({ vertexIndex: i });
    }),
  }));
}

// Listener — on vertex change, re-render polylines AND refresh tools so
// the handles follow the new positions in the same frame.
graph.on('change:vertices', function (cell) {
  if (cell.get('type') !== 'showstack.BoundaryLine') return;
  applyBoundaryRender(cell);
  var view = cell.findView(paper);
  if (view) view.updateTools();
  scheduleAutosave();
});
```

**Selection-change wiring (extend signal_flow_editor.js:1862-1894):**

```javascript
// Add a branch in window.__sfd.onSelectionChanged BEFORE the existing isElement branch:
if (cell && cell.get('type') === 'showstack.BoundaryLine') {
  setInspectorMode('boundary', cell);
  showInspector();
  if (_resizeAttachedCell) { detachResizeTools(_resizeAttachedCell); _resizeAttachedCell = null; }
  attachBoundaryVertexTools(cell);
  _vertexAttachedCell = cell;                // new tracker for vertex tools, parallel to _resizeAttachedCell
  return;
}
if (cell && cell.get('type') === 'showstack.TextLabel') {
  setInspectorMode('text', cell);
  showInspector();
  if (_resizeAttachedCell) { detachResizeTools(_resizeAttachedCell); _resizeAttachedCell = null; }
  // Text labels get no special tools — drag handled by JointJS default move behavior on the hitArea rect.
  return;
}
// ... existing isLink / isElement branches unchanged ...
```

**Confidence:** HIGH — `joint.elementTools.Control` is the exact MPL-2.0 base class used by Phase 11; `getPosition/setPosition` semantics are documented and proven in-tree. [VERIFIED: signal_flow_editor.js:537-613 CornerResize implementation]

---

### R-04: IDOR allowlist branch for non-equipment cells — **NO CODE CHANGE NEEDED**

**Verified by direct read of `planner/views.py:7686-7726`:**

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

BoundaryLine and TextLabel cells have no `showstack.contentTypeId` or `showstack.objectId` — they have no equipment link. They will hit the `continue` on line 7693 and proceed to the next cell. The allowlist check never runs for them.

**The plan MUST NOT add a new branch.** Doing so would be redundant defensive code that obscures the intent of the existing pass-through path. The plan MUST add a regression test (R-13) that round-trips a BoundaryLine cell + a TextLabel cell + an equipment-linked Console cell through `signal_flow_autosave` and asserts HTTP 200 — locking in the current behavior against future refactors.

**Confidence:** HIGH — verbatim quote of the active code on `planner/views.py`. [VERIFIED]

---

### R-05: `validateMagnet` / `validateConnection` auto-reject for boundaries — **NO CODE CHANGE NEEDED**

**Verified by direct read of `planner/static/planner/js/signal_flow_editor.js:792-805`:**

```javascript
validateMagnet: function (cellView, magnet) {
  // Allow link drag to START only from non-passive magnets (out-ports).
  // In-ports have magnet="passive" and act as drag TARGETS only.
  return magnet && magnet.getAttribute('magnet') !== 'passive';
},
validateConnection: function (sourceView, sourceMagnet, targetView, targetMagnet) {
  // CON-03 — both ends MUST be magnets (ports). Mid-shape drops have null magnet.
  if (!sourceMagnet || !targetMagnet) return false;
  if (sourceView === targetView) return false;
  return true;
},
```

`validateMagnet` returns `false` when `magnet` is falsy — BoundaryLine has no `<element>` with a `magnet` attribute (the markup defines `linePrimary` / `lineSecondary` only, neither with a `magnet` attr), so any drag attempt that originates on the boundary stroke fails the `magnet && ...` guard.

`validateConnection` returns `false` if `sourceMagnet` OR `targetMagnet` is `null` — a connector dropped onto a BoundaryLine has `targetMagnet === null` (no magnet to snap to) and is rejected.

TextLabel has the same property: no `<element>` with a `magnet` attribute → never a valid endpoint.

**Plan MUST NOT modify these handlers.** A regression test that attempts to drag from a Console out-port to a BoundaryLine would be valuable but is browser-UAT territory, not a backend test.

**Confidence:** HIGH — verbatim quote of the active code. [VERIFIED]

---

### R-06: Pen-tool draw-mode state machine

**Closure-scoped state machine inside the IIFE.** No JointJS built-in "drawing tool" exists in `@joint/core` (the polyline-draw tool is a JointJS+ paid feature, confirmed absent from the vendor bundle by the Phase 11 `joint.elementTools.Resize` lookup). Phase 12 hand-rolls the state machine over `paper.on('blank:pointerdown')` and document-level `keydown` listeners.

**State machine:**

```javascript
// Closure-scoped state for the pen-tool draw mode.
var drawState = {
  active: false,                  // true while in draw-boundary mode (sticky per D-01)
  vertices: [],                   // [{x, y}, ...] accumulated since mode entry
  livePreview: null,              // SVG <polyline> element showing the in-progress line
  liveSegment: null,              // SVG <line> element showing the "to cursor" segment
};

// Mode entry — fires when #sfd-tool-boundary is clicked while NOT already active.
function enterBoundaryMode() {
  drawState.active = true;
  drawState.vertices = [];
  drawState.livePreview = createPreviewPolyline();    // appended to paper.viewport
  drawState.liveSegment = createPreviewSegment();
  // D-07 visual feedback.
  toolBoundaryBtn.classList.add('is-active');
  toolBoundaryBtn.setAttribute('aria-pressed', 'true');
  paperEl.style.setProperty('cursor', 'crosshair', 'important');
  // If text mode was active, exit it (D-01 "click of another mode button").
  if (textModeActive) exitTextMode();
}

function exitBoundaryMode() {
  drawState.active = false;
  drawState.vertices = [];
  if (drawState.livePreview && drawState.livePreview.parentNode) {
    drawState.livePreview.parentNode.removeChild(drawState.livePreview);
  }
  if (drawState.liveSegment && drawState.liveSegment.parentNode) {
    drawState.liveSegment.parentNode.removeChild(drawState.liveSegment);
  }
  drawState.livePreview = null;
  drawState.liveSegment = null;
  toolBoundaryBtn.classList.remove('is-active');
  toolBoundaryBtn.setAttribute('aria-pressed', 'false');
  paperEl.style.setProperty('cursor', '', 'important');   // restore default
}

// Vertex placement — wire to paper.on('blank:pointerdown'), gated on drawState.active.
// Note: signal_flow_editor.js:1500 already has a `blank:pointerdown` for rubber-band selection.
// JointJS emitter supports multiple listeners on the same event (verified at line 1718).
// The Phase 12 listener checks drawState.active and BAILS OUT of the rubber-band path
// when we're drawing; it must be registered AFTER the rubber-band one so it runs second
// — OR we add an early-exit guard in the rubber-band listener itself.
paper.on('blank:pointerdown', function (evt, x, y) {
  if (!drawState.active) return;                      // not in draw mode — rubber-band runs
  // Pre-empt the rubber-band listener: it has no way to know we ran first, so
  // the planner must ALSO add an early-exit `if (drawState.active) return;`
  // at the top of the rubber-band handler at signal_flow_editor.js:1500.
  var pt = { x: x, y: y };
  if (currentViewport.snapEnabled) {                  // D-03 — match Phase 8 D-13 snap
    pt.x = Math.round(pt.x / 20) * 20;
    pt.y = Math.round(pt.y / 20) * 20;
  }
  drawState.vertices.push(pt);
  updatePreviewPolyline();
});

// Live "to cursor" segment — update on every pointermove while in draw mode.
paper.on('blank:pointermove', function (evt, x, y) {
  if (!drawState.active) return;
  if (!drawState.vertices.length) return;
  var last = drawState.vertices[drawState.vertices.length - 1];
  var pt = { x: x, y: y };
  if (currentViewport.snapEnabled) {
    pt.x = Math.round(pt.x / 20) * 20;
    pt.y = Math.round(pt.y / 20) * 20;
  }
  // Set the SVG line from `last` to `pt` — same approach as the rubber-band rect at line 1503.
  drawState.liveSegment.setAttribute('x1', String(last.x));
  drawState.liveSegment.setAttribute('y1', String(last.y));
  drawState.liveSegment.setAttribute('x2', String(pt.x));
  drawState.liveSegment.setAttribute('y2', String(pt.y));
});

// Double-click commits (D-02).
paper.on('blank:pointerdblclick', function (evt, x, y) {
  if (!drawState.active) return;
  commitOrCancelBoundary();
});

// Esc commits if ≥2 vertices, else cancels (D-02 + D-05). Also exits mode.
document.addEventListener('keydown', function (evt) {
  if (/INPUT|TEXTAREA|SELECT/.test(evt.target.tagName)) return;
  if (evt.key !== 'Escape') return;
  if (drawState.active) {
    evt.preventDefault();
    commitOrCancelBoundary();   // commit if ≥2, else just discard
    exitBoundaryMode();
  }
  // ... existing Esc behavior for picker / selection clear remains ...
});

function commitOrCancelBoundary() {
  if (drawState.vertices.length < 2) {
    // D-02 — single-vertex click followed by Esc/dblclick = no polyline.
    drawState.vertices = [];
    return;
  }
  // Create the BoundaryLine cell with the accumulated vertices.
  var cell = new joint.shapes.showstack.BoundaryLine({
    vertices: drawState.vertices.slice(),
    color: lastBoundaryColor || '#000000',          // sticky default
    lineStyle: lastBoundaryStyle || 'solid',
  });
  graph.addCell(cell);
  applyBoundaryRender(cell);
  cell.toBack();                                    // D-13 — behind shapes/connectors
  drawState.vertices = [];
  // Sticky mode stays active per D-01 — engineer can immediately start the next boundary.
  // The graph 'add' event already triggers scheduleAutosave (signal_flow_editor.js:2403).
}
```

**Listener attachment:** mix of `paper.on(...)` (canvas-local pointer events translated to paper-local coords by JointJS) and `document.addEventListener('keydown', ...)` (Esc — exits the IIFE-scoped state machine cleanly).

**Critical gotcha:** the Phase 8 rubber-band-selection handler at signal_flow_editor.js:1500 also listens on `blank:pointerdown`. The plan MUST add an early-exit guard `if (drawState.active) return;` at the top of that handler, otherwise rubber-band drag-select still fires while drawing. JointJS allows multiple listeners on the same event but does NOT have a stopPropagation analog for `blank:pointerdown` — the guard has to live inside the rubber-band handler.

**Confidence:** HIGH — pattern matches the rubber-band-rect implementation at signal_flow_editor.js:1500-1544 verbatim; the multi-listener observation is verified in the existing in-tree comment at signal_flow_editor.js:1717-1719. [VERIFIED]

---

### R-07: Inline text-edit overlay (covered in R-02)

See R-02 for the full event-flow. Summary:

- **Overlay element:** `<input type="text">` — NOT `contenteditable` (single-line is the constraint, native input semantics are simpler).
- **Positioning:** absolute, on top of the cell's screen bbox computed via `paper.localToPaperRect(cell.getBBox())`. Append to `paperEl.parentNode` (HTML overlay, not SVG child).
- **Commit:** Enter / blur → write `cell.attr('label/text', value)`; if empty, `cell.remove()`.
- **Cancel:** Esc → if newly placed (no prior text), remove the cell; remove input either way.
- **Re-entry:** `paper.on('element:pointerdblclick', ...)` on a `showstack.TextLabel` cell.

**Confidence:** HIGH — well-established overlay pattern; positioning math uses documented JointJS API.

---

### R-08: Inspector mode panels (color + line-style + font-size HTML)

**Existing `.sfd-segmented` HTML pattern (editor.html:134-140):**

```html
<div class="sfd-field">
  <label>Direction</label>
  <div class="sfd-segmented" role="group" aria-label="Connector direction">
    <button type="button" id="sfd-dir-forward" data-active="true">Source &rarr; Target</button>
    <button type="button" id="sfd-dir-bidir">Bidirectional</button>
  </div>
</div>
```

CSS (signal_flow.css:281-301): `.sfd-segmented` is a flex inline; buttons set `data-active="true"` for the teal `#0d9488` background.

**Phase 12 inspector — built lazily by `setInspectorMode('boundary')` / `setInspectorMode('text')`.** Phase 9's `buildNodeModeBlock` at signal_flow_editor.js:1980-2056 is the template (build once, cache, show/hide via `display: block | none`).

**Boundary-mode panel HTML structure (built by JS, no template change):**

```javascript
function buildBoundaryModeBlock() {
  boundaryModeBlock = document.createElement('div');
  boundaryModeBlock.setAttribute('data-mode', 'boundary');
  boundaryModeBlock.style.setProperty('display', 'none', 'important');

  // --- Color swatches: 8 swatches, 4×2 grid (recommended) ---
  // 4×2 chosen over 8×1 because the inspector is ~240px wide and an 8-wide row
  // would force each swatch to ~24px which is below the recommended hit-target.
  // 4×2 gives each swatch ~48px hit area with comfortable spacing.
  var colorField = document.createElement('div');
  colorField.className = 'sfd-field';
  colorField.innerHTML = '<label>Color</label>';
  var swatchGrid = document.createElement('div');
  swatchGrid.className = 'sfd-color-swatches';        // new CSS class in Section 17
  BOUNDARY_PALETTE.forEach(function (hex) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'sfd-color-swatch';
    btn.setAttribute('data-color', hex);
    btn.setAttribute('aria-label', 'Color ' + hex);
    btn.style.setProperty('background-color', hex, 'important');
    btn.addEventListener('click', function () { applyBoundaryColor(inspectorCurrentBoundary, hex); });
    swatchGrid.appendChild(btn);
  });
  colorField.appendChild(swatchGrid);

  // --- Line-style segmented: solid / dashed / dotted / double ---
  var styleField = document.createElement('div');
  styleField.className = 'sfd-field';
  styleField.innerHTML = '<label>Line style</label>';
  var styleSeg = document.createElement('div');
  styleSeg.className = 'sfd-segmented';
  styleSeg.setAttribute('role', 'group');
  ['solid', 'dashed', 'dotted', 'double'].forEach(function (s) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('data-style', s);
    // SVG <line> preview inside each button — 24px wide, current stroke color, that style's dasharray.
    btn.innerHTML = renderLineStylePreviewSVG(s);     // returns "<svg>...</svg>" string
    btn.addEventListener('click', function () { applyBoundaryLineStyle(inspectorCurrentBoundary, s); });
    styleSeg.appendChild(btn);
  });
  styleField.appendChild(styleSeg);

  boundaryModeBlock.appendChild(colorField);
  boundaryModeBlock.appendChild(styleField);
  inspectorEl.appendChild(boundaryModeBlock);
}
```

**Text-mode panel** mirrors the boundary panel but with:
- 9-swatch palette (8 colors + white) — also 3×3 grid layout fits the inspector width well.
- Font-size segmented (3 buttons): `S` (12px) / `M` (16px) / `L` (24px), with the letter sized to match the actual font-size for at-a-glance recognition.
- No line-style block.

**`setInspectorMode` extension (signal_flow_editor.js:2199-2236):** add two new branches after the existing `'node'` branch:

```javascript
} else if (mode === 'boundary') {
  if (inspectorHeader) inspectorHeader.textContent = 'Boundary';
  connectorFieldRows.forEach(function (row) {
    row.style.setProperty('display', 'none', 'important');
  });
  if (nodeModeBlock) nodeModeBlock.style.setProperty('display', 'none', 'important');
  if (portAuthorBlock) portAuthorBlock.style.setProperty('display', 'none', 'important');
  if (!boundaryModeBlock) buildBoundaryModeBlock();
  boundaryModeBlock.style.setProperty('display', 'block', 'important');
  inspectorCurrentBoundary = cell;
  inspectorCurrentLink = null;
  inspectorCurrentNode = null;
  refreshBoundaryModeBlock(cell);                     // sync swatch + style active states
} else if (mode === 'text') {
  if (inspectorHeader) inspectorHeader.textContent = 'Text';
  connectorFieldRows.forEach(function (row) {
    row.style.setProperty('display', 'none', 'important');
  });
  if (nodeModeBlock) nodeModeBlock.style.setProperty('display', 'none', 'important');
  if (portAuthorBlock) portAuthorBlock.style.setProperty('display', 'none', 'important');
  if (!textModeBlock) buildTextModeBlock();
  textModeBlock.style.setProperty('display', 'block', 'important');
  inspectorCurrentText = cell;
  inspectorCurrentLink = null;
  inspectorCurrentNode = null;
  refreshTextModeBlock(cell);
}
```

**Swatch active-state visual:** 2px ring in `#0d9488` (teal — matches Phase 11 selection language) applied via `data-active="true"` + a CSS rule with `box-shadow: 0 0 0 2px #0d9488 inset, ...`. Refresh on every selection / color change so the active swatch reflects the cell's current color prop.

**Confidence:** HIGH — pattern matches Phase 9 lazy-build at signal_flow_editor.js:1980-2056 and the existing `.sfd-segmented` HTML at editor.html:134-140. [VERIFIED]

---

### R-09: Session-sticky defaults storage — closure-scoped IIFE state

**Recommendation: closure-scoped variables inside the IIFE.** Matches the existing pattern (`conflicted`, `diagramDirty`, `currentVersion`, `pickerState` are all closure-scoped — see signal_flow_editor.js:2258-2262 + 925-930). `sessionStorage` would persist across page reloads, which is *not* the intent — the engineer drawing 6 red zones in one session is the use case; on next-day reload the defaults reset to factory.

**Location:** add to the autosave / closure-state block at signal_flow_editor.js:2258 area:

```javascript
// Phase 12 — session-sticky defaults for next-created boundary / text cell.
// Reset on page reload (intentional; engineer's session is the window).
var lastBoundaryColor = '#000000';      // D-09 initial — black
var lastBoundaryStyle = 'solid';        // D-12 initial — solid
var lastTextSize     = 16;              // D-19 initial — medium
var lastTextColor    = '#000000';       // D-19 initial — black
```

**Update points:**
- Inspector color swatch click for boundary → `lastBoundaryColor = newColor; cell.prop('color', newColor); applyBoundaryRender(cell); scheduleAutosave();`
- Inspector line-style segmented click → `lastBoundaryStyle = newStyle; cell.prop('lineStyle', newStyle); applyBoundaryRender(cell); scheduleAutosave();`
- Inspector text color swatch click → similar.
- Inspector font-size segmented click → similar.
- Pen-tool `commitOrCancelBoundary` reads `lastBoundaryColor` and `lastBoundaryStyle` (see R-06).
- Click-to-place text reads `lastTextSize` and `lastTextColor` (see R-02 step 2).

**Confidence:** HIGH — closure-scoped state is the established pattern. [VERIFIED]

---

### R-10: Z-order defaults — JointJS `cell.toBack()` / `cell.toFront()`

**JointJS 4.2.4 surface:**
- `cell.toBack(opts)` — sets `z` to one less than the lowest current `z` in the graph.
- `cell.toFront(opts)` — sets `z` to one more than the highest current `z` in the graph.
- Both fire `change:z` (which fires `change` — the existing autosave listener catches it implicitly via `graph.toJSON()` capturing `z`).

**Existing usage:** **None** — none of the 7 existing shape classes nor SignalLink set `z` explicitly. JointJS auto-increments `z` on `addCell`, so cells stack in creation order. This means:

- Boundary cells must be `toBack()` immediately after `graph.addCell(cell)` so they render below existing shapes (D-13).
- Text cells must be `toFront()` immediately after `graph.addCell(cell)` so they render above existing shapes (D-14).

**Implementation:**

```javascript
// In R-06 commitOrCancelBoundary, after addCell:
graph.addCell(cell);
applyBoundaryRender(cell);
cell.toBack();                                       // D-13

// In R-02 click-to-place text, after addCell:
graph.addCell(cell);
cell.toFront();                                      // D-14
enterTextEditMode(cell);
```

**Round-trip:** `cell.toBack()` / `toFront()` write to `cell.attributes.z` which `graph.toJSON()` serializes; on reload, `graph.fromJSON(canvas_state)` restores cells in `z` order. No additional persistence work.

**Caveat:** if a future Phase adds engineer-controlled z-order overrides (D-15 deferred), the bring-forward/back rules will need to span both "boundary always behind" and "user reordering" — but that's a v2.4+ problem.

**Confidence:** HIGH — `toBack`/`toFront` are stable @joint/core API; absence of explicit `z` in existing classes verified by grep. [VERIFIED]

---

### R-11: PNG export verification — **no Phase 12 code change required**

The Phase 10 export path at signal_flow_editor.js:2729-2734 is:

```javascript
htmlToImage.toPng(paperEl, {
  pixelRatio: 2,
  backgroundColor: '#ffffff',
  width: paper.options.width,
  height: paper.options.height,
})
```

`paperEl` is `#sfd-paper`, the SVG root that contains every cell — including new `BoundaryLine` and `TextLabel` cells. `html-to-image` does an offscreen-canvas snapshot of the DOM subtree under `paperEl`. BoundaryLine's two `<polyline>` children and TextLabel's `<text>` child are pure SVG primitives (not `foreignObject`), so they render in the snapshot with no special handling.

**Verification plan (UAT, not backend test):**
1. Draw a 3-vertex boundary in solid red.
2. Draw a 3-vertex boundary in double-style black (verifies the secondary polyline renders).
3. Place a text label in 24px white over the red boundary (verifies the D-19 white-on-color use case).
4. Export PNG.
5. Confirm all three elements appear at the correct colors, line styles, and font sizes.

**Confidence:** HIGH — verified by reading the export code path. No Phase 12 code touches PNG export. [VERIFIED]

---

### R-12: CSS section additions

**Current section list (top of signal_flow.css:21-37):** 16 sections, last is "Section 16 — Inspector port-list rows + trash icon (Phase 11 D-02 / D-04)".

**Note on section ordering:** the section-list comment lists 1–16 in order, but the *physical order in the file* puts Section 16 (line 711) before Sections 14 (line 825) and 15 (line 847). This is a Phase 11 quirk verified by `grep`; Phase 12 simply appends Sections 17 + 18 at the end of the file (lines >875), following the *intent* of the append-at-end convention. The section-list comment update keeps the logical numbering 1–18.

**Section-list update (signal_flow.css:21-37):**

```css
 * Sections:
 *   1. Toolbar button groups + dividers (extends Phase 7 #sfd-toolbar)
 *   2. Canvas container layout (sidebar | paper | inspector)
 *   3. Left sidebar shape picker (#sfd-sidebar + .sfd-tile)
 *   4. Right inspector panel (#sfd-inspector + .sfd-field + .sfd-segmented)
 *   5. Equipment picker modal (.sfd-picker-overlay + .sfd-pick-*)
 *   6. Toast (.sfd-toast)
 *   7. JointJS port hover-reveal (Phase 8; amended Phase 11 — see Section 14)
 *   8. Selection visual (.is-selected + .sfd-multi-bbox)
 *   9. Empty canvas hint (.sfd-empty-hint)
 *  10. 409 Conflict banner (Phase 9 D-07)
 *  11. Orphan ghost render (Phase 9 D-15 + SHP-07)
 *  12. Autocomplete dropdown (Phase 10 LBL-01..03)
 *  13. Export button group (Phase 10 EXP-01)
 *  14. Port-label rendering (Phase 11 D-08 — perpendicular-inside)
 *  15. Resize handles (Phase 11 D-05 — four corners)
 *  16. Inspector port-list rows + trash icon (Phase 11 D-02 / D-04)
 *  17. Boundary lines — DRAW (Phase 12 D-04 toolbar group, D-09 color swatches, D-12 line-style picker)
 *  18. Text annotations — TXT (Phase 12 D-19 font-size segmented, D-19 9-color picker incl. white)
 */
```

**Section 17 skeleton (appended after signal_flow.css:875):**

```css
/* =========================================================================
   SECTION 17 — Boundary lines (Phase 12 DRAW-01..04)
   Toolbar buttons #sfd-tool-boundary / #sfd-tool-text in the .sfd-btn-group
   per D-04; inspector boundary-mode panel with 8-swatch color grid (D-09)
   and 4-button line-style segmented (D-12).
   ========================================================================= */

/* Toolbar boundary + text mode buttons — match Phase 8 #sfd-snap-toggle styling. */
#sfd-tool-boundary,
#sfd-tool-text {
  /* inherits .sfd-btn-group button styles from Section 1 */
}
#sfd-tool-boundary.is-active,
#sfd-tool-text.is-active {
  /* uses same teal active-state as #sfd-snap-toggle.is-active */
}

/* Inspector color swatches — 4×2 grid for boundary, 3×3 grid for text (Section 18). */
.sfd-color-swatches {
  display: grid !important;
  grid-template-columns: repeat(4, 1fr) !important;
  gap: 4px !important;
  margin-top: 4px !important;
}
.sfd-color-swatch {
  width: 100% !important;
  height: 28px !important;
  border: 1px solid #444 !important;
  border-radius: 3px !important;
  cursor: pointer !important;
  padding: 0 !important;
}
.sfd-color-swatch[data-active="true"] {
  box-shadow: 0 0 0 2px #0d9488 inset, 0 0 0 1px #fff inset !important;
}

/* Line-style segmented previews — SVG <line> rendered inside each segmented button. */
.sfd-segmented button[data-style] svg {
  display: block !important;
  width: 28px !important;
  height: 12px !important;
}

/* GAP-11.7 PARALLEL: All inspector text in boundary/text panels uses the
   dark-navy inspector light-on-dark palette per the user MEMORY rule
   (#eee primary text, #aaa muted label/help). Default Django-admin
   light-bg colors must NOT leak into the new panels. */

/* =========================================================================
   SECTION 18 — Text annotations (Phase 12 TXT-01..03)
   Inline-edit overlay <input> styling (D-16, D-17), font-size segmented
   (D-19 S/M/L), 9-color picker including white (D-19).
   ========================================================================= */

/* Inline-edit overlay <input> — positioned over the cell bbox during edit. */
.sfd-text-edit-overlay {
  position: absolute !important;
  border: 1px solid #0d9488 !important;
  background-color: transparent !important;
  outline: none !important;
  padding: 0 !important;
  margin: 0 !important;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif !important;
  /* font-size + color set inline via setProperty(... 'important') matching the cell's props */
}

/* Font-size segmented S/M/L — letter inside each button scaled to actual font-size hint. */
.sfd-text-fontsize-segmented button[data-size="small"]  { font-size: 11px !important; }
.sfd-text-fontsize-segmented button[data-size="medium"] { font-size: 13px !important; }
.sfd-text-fontsize-segmented button[data-size="large"]  { font-size: 16px !important; }

/* Text-mode 9-color picker — 3×3 grid (includes white per D-19). */
.sfd-color-swatches--text {
  grid-template-columns: repeat(3, 1fr) !important;
}
```

**Confidence:** HIGH — append convention is the established pattern; Phase 11 added Sections 14/15/16 the same way. [VERIFIED]

---

### R-13: Test file naming + backend test surface

**Filename:** `planner/tests/test_signal_flow_phase12.py` — matches the Phase 9 / Phase 10 convention.

**Test pattern:** extend `_Phase9Base` (or copy its setUp pattern) — `force_login` + `session['current_project_id']` for CurrentProjectMiddleware. The Phase 10 test file uses the same approach.

**Minimum backend test surface:**

```python
class SignalFlowPhase12AutosaveTests(_Phase12Base):
    """Phase 12 — BoundaryLine + TextLabel cells autosave round-trip.

    Locks in the R-04 finding that cells WITHOUT a `showstack.contentTypeId`
    bypass the IDOR allowlist via the `continue` at planner/views.py:7693.
    Regression test against a future refactor that re-introduces the bug.
    """

    def test_boundary_only_canvas_state_round_trips(self):
        """Canvas with only BoundaryLine cells — no equipment GFK — autosaves OK."""
        payload = {
            'canvas_state': {
                'cells': [
                    {
                        'id': 'b1',
                        'type': 'showstack.BoundaryLine',
                        'vertices': [{'x': 100, 'y': 100}, {'x': 200, 'y': 100}, {'x': 200, 'y': 200}],
                        'color': '#dc2626',
                        'lineStyle': 'dashed',
                    },
                ],
            },
            'viewport': {'x': 0, 'y': 0, 'scale': 1.0, 'snapEnabled': True},
        }
        resp = self._post_autosave(payload, if_match='1')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['version'], 2)

    def test_text_only_canvas_state_round_trips(self):
        """Canvas with only TextLabel cells — no equipment GFK — autosaves OK."""
        # ... mirror of above with TextLabel cell ...

    def test_mixed_boundary_text_equipment_round_trip(self):
        """Mixed canvas — BoundaryLine + TextLabel + Console (with project-scoped GFK) — autosaves OK.

        Covers the realistic save: decorative cells alongside real equipment-linked shapes.
        The allowlist walk skips the decorative cells (no `showstack.contentTypeId`)
        and runs the IDOR check only on the Console.
        """
        # ... include a Console cell with valid contentTypeId/objectId scoped to current_project ...

    def test_boundary_with_invalid_color_still_saves(self):
        """Phase 12 cells are opaque to the server — palette validation is client-side only.

        The server does not parse `cell.color` or `cell.lineStyle`; it just stores the
        canvas_state JSON blob. A garbage color value still round-trips.
        """
        # ... assert HTTP 200 with color: 'not-a-real-hex' ...
```

**Out of scope for backend test (covered by UAT):**
- Pen-tool input gestures (mouse events).
- Inline-edit overlay positioning + commit/cancel.
- Vertex-drag handle attach/detach on selection.
- Z-order rendering correctness.
- PNG export visual fidelity.

**Confidence:** HIGH — test file pattern verified against test_signal_flow_phase9.py and test_signal_flow_phase10.py headers. [VERIFIED]

---

### R-14: `canvas_state` JSON shape for DRAW + TXT cells

**Verified by direct read of signal_flow_editor.js:829-832 + 2299-2307:**

```javascript
// Load (line 829-832):
var canvasState = state.canvas_state || {};
if (canvasState && Array.isArray(canvasState.cells)) {
  graph.fromJSON(canvasState, { undoable: false });
}

// Save (line 2299-2307):
var payloadObj = {
  canvas_state: graph.toJSON(),                       // <-- JointJS native serialize
  viewport: { ... },
};
```

`graph.toJSON()` returns `{ cells: [...] }` — a single top-level `cells` array containing every cell (elements + links) in the graph. BoundaryLine and TextLabel cells are JointJS elements just like Console / Device / etc., so they appear in the same array.

**Per-cell JSON shape (illustrative — actual values driven by JointJS toJSON):**

```json
{
  "cells": [
    {
      "type": "showstack.Console",
      "id": "...",
      "position": {"x": 100, "y": 100},
      "size": {"width": 180, "height": 60},
      "attrs": {"label": {"text": "FOH Console"}},
      "showstack": {"contentTypeId": 7, "objectId": 42}
    },
    {
      "type": "showstack.BoundaryLine",
      "id": "...",
      "position": {"x": 0, "y": 0},
      "size": {"width": 0, "height": 0},
      "attrs": {"linePrimary": {...}, "lineSecondary": {...}},
      "vertices": [{"x": 100, "y": 100}, {"x": 200, "y": 100}],
      "color": "#dc2626",
      "lineStyle": "dashed",
      "z": 0
    },
    {
      "type": "showstack.TextLabel",
      "id": "...",
      "position": {"x": 240, "y": 80},
      "size": {"width": 60, "height": 22},
      "attrs": {"label": {"text": "FOH", "fontSize": 24, "fill": "#000000"}},
      "fontSize": 24,
      "color": "#000000",
      "z": 999
    }
  ]
}
```

**Key:** DRAW + TXT cells live in the **same top-level `cells: []` array** as shapes and connectors. There are NO new top-level keys like `boundaries: []` or `text: []`. The `type` field discriminates them.

This is the simplest possible shape — JointJS's `graph.toJSON()` and `graph.fromJSON()` handle round-tripping with zero extra code. Server (`signal_flow_autosave`) treats the entire blob as opaque JSON. The IDOR walk iterates `cells` and skips entries without `showstack.contentTypeId` (R-04).

**Confidence:** HIGH — verbatim from in-tree code. [VERIFIED]

## Files Modified (estimated)

### JS shape registration — `planner/static/planner/js/signal_flow_editor.js`
- **After line 761 (after Amp class):** add `joint.shapes.showstack.BoundaryLine` class (~30 lines).
- **After BoundaryLine:** add `joint.shapes.showstack.TextLabel` class (~25 lines).
- **After ~line 597 (after CornerResize):** add `BoundaryVertex` elementTools.Control subclass + `attachBoundaryVertexTools` / `detachBoundaryVertexTools` helpers (~60 lines).
- **Module-level constants:** `BOUNDARY_PALETTE`, `TEXT_PALETTE`, `BOUNDARY_LINE_STYLES`, `TEXT_FONT_SIZES` (~10 lines).

### JS toolbar / event-handlers — `planner/static/planner/js/signal_flow_editor.js`
- **Mode-button wiring:** click handlers on `#sfd-tool-boundary` and `#sfd-tool-text` calling `enterBoundaryMode` / `exitBoundaryMode` / `enterTextMode` / `exitTextMode` (~30 lines).
- **Pen-tool state machine:** `drawState` closure + `paper.on('blank:pointerdown' | 'blank:pointermove' | 'blank:pointerdblclick')` listeners + `commitOrCancelBoundary` (~80 lines from R-06).
- **Esc keydown branch:** extend the existing `document.addEventListener('keydown', ...)` at signal_flow_editor.js:1549 to commit/cancel mid-polyline OR cancel text-edit (~15 lines).
- **Existing rubber-band guard:** add early-exit `if (drawState.active) return;` at signal_flow_editor.js:1500-1501.

### JS inspector mode panels — `planner/static/planner/js/signal_flow_editor.js`
- **`buildBoundaryModeBlock` + `refreshBoundaryModeBlock`:** lazy build at first `setInspectorMode('boundary')` call (~60 lines).
- **`buildTextModeBlock` + `refreshTextModeBlock`:** parallel for text mode (~55 lines).
- **`setInspectorMode` extension:** two new branches (`'boundary'`, `'text'`) at signal_flow_editor.js:2199 (~25 lines).
- **`onSelectionChanged` extension:** two new branches at signal_flow_editor.js:1862 (~20 lines).
- **Closure state:** `lastBoundaryColor` / `lastBoundaryStyle` / `lastTextSize` / `lastTextColor` (~5 lines).

### JS draw / edit lifecycle — `planner/static/planner/js/signal_flow_editor.js`
- **`enterTextEditMode(cell)` + `commitTextEdit` / `cancelTextEdit`:** inline-edit overlay lifecycle (~60 lines from R-02).
- **`paper.on('element:pointerdblclick')` handler:** TextLabel re-entry (~10 lines).
- **`applyBoundaryRender(cell)` helper:** render both polylines on every vertex / style change (~25 lines from R-01).
- **`graph.on('change:vertices')` listener:** re-render + tool-refresh + autosave (~10 lines).

### HTML toolbar insertion — `planner/templates/planner/signal_flow/editor.html`
- **Between lines 58 and 60** (after `</div>` of history group, before `<span class="sfd-toolbar-spacer">`): insert `<span class="sfd-toolbar-divider"></span>` + `<div class="sfd-btn-group" data-group="create"><button id="sfd-tool-boundary">...</button><button id="sfd-tool-text">...</button></div>` (~6 lines).

### CSS Section 17 + 18 — `planner/static/planner/css/signal_flow.css`
- **Update section-list comment** at top (lines 21-37): add Sections 17 + 18 entries.
- **Append Section 17** (after line 875): toolbar mode-button styling, color-swatch grid, line-style segmented preview styling (~40 lines).
- **Append Section 18** (after Section 17): inline-edit overlay styling, font-size segmented S/M/L styling, 3×3 text color picker grid override (~30 lines).

### views.py — NO CHANGES (per R-04)
The IDOR allowlist already passes through cells without `showstack.contentTypeId/objectId` via the `continue` on line 7693. The plan MUST NOT touch this file beyond verifying the behavior with the new test file.

### Test — `planner/tests/test_signal_flow_phase12.py` (NEW)
- `_Phase12Base` class — copies `_Phase9Base` setUp pattern (~50 lines).
- `SignalFlowPhase12AutosaveTests` with 4 tests per R-13 (~120 lines).

### Documentation — `.planning/REQUIREMENTS.md`
- Update Traceability table (lines 110-136): mark DRAW-01..04 + TXT-01..03 as "12" / "Done" after phase completion.

## Risks / Gotchas

| # | Risk | Plan guard |
|---|------|------------|
| 1 | **Rubber-band selection fires alongside the pen-tool's `blank:pointerdown`** — both listeners are registered on the same event, JointJS has no stopPropagation analog. | Plan MUST add an early-exit `if (drawState.active) return;` at the **top** of the existing rubber-band handler at signal_flow_editor.js:1500. This guard is a one-line edit and is the most-likely-forgotten step. |
| 2 | **IDOR allowlist regression risk** — current code skips cells without GFK via `continue` (line 7693); a future refactor that promotes the allowlist to a `match`/strict-enum could silently reject Phase 12 cells. | Plan MUST add the `test_boundary_only_canvas_state_round_trips` + `test_text_only_canvas_state_round_trips` tests in test_signal_flow_phase12.py. These tests lock in the current behavior. |
| 3 | **Double-line per-segment normal math is non-trivial** — the R-01 implementation shifts the second polyline by `(0, +3)`, which is fine for mostly-horizontal lines but visually wrong for a vertical or 45-degree boundary. | Plan documents the simplification as a v2.3 ship-it (architecture-drawing double-walls are dominantly horizontal). If UAT reveals the cheat is unacceptable, the per-segment unit-normal math can land as a Phase 12 follow-up without changing the public API. |
| 4 | **Esc keydown branch interleaving** — three Esc-handlers compete: existing picker-modal close (signal_flow_editor.js:1069+), existing selection-clear (signal_flow_editor.js:1397+), and new draw/text mode exit. | Plan MUST order the new Esc branches to fire BEFORE the existing selection-clear logic — early-exit with `evt.preventDefault()` when draw/text mode is active. |
| 5 | **Inline-edit overlay positioning on zoom/pan** — the `<input>` is HTML-positioned in CSS pixels; if the engineer pans or zooms during an active edit, the overlay drifts off the cell. | Plan MUST disable pan/zoom during text edit (set a `inTextEdit` flag and gate the existing pan handler) OR force-commit on any zoom/pan event. Force-commit is the safer UX. |
| 6 | **`change:vertices` not in the existing autosave graph-event list** at signal_flow_editor.js:2403 — the listener is `'add remove change:source change:target change:size'`. Vertex drags will not trigger autosave unless explicitly handled. | Plan's `graph.on('change:vertices', ...)` listener for BoundaryLine MUST explicitly call `scheduleAutosave()` (already in R-03 code). Same pattern as Phase 11 `graph.on('change:size', ...)` at signal_flow_editor.js:2411. |
| 7 | **Inspector dark-navy palette** — per user MEMORY rule, new `#sfd-inspector` CSS must use `#eee` primary text and `#aaa` muted labels, not Django-admin light-bg defaults. GAP-11.7 in Phase 11 lost 2 contrast bugs to this. | Plan tasks for Sections 17 + 18 CSS MUST audit every `color:` declaration against the dark-navy inspector palette. Mention the MEMORY rule in the plan task description. |
| 8 | **Cell-class registration order** — JointJS requires shape classes registered BEFORE the cell appears in `graph.fromJSON()` (PITFALLS §1 in the codebase comment at signal_flow_editor.js:88). | Plan MUST register BoundaryLine + TextLabel BEFORE `new joint.dia.Graph(...)` at signal_flow_editor.js:770. Currently the existing classes are registered before that line; new classes go in the same block. |

## Out of Scope (mirror CONTEXT.md)

- Curved boundary lines (DRAW-CURVE-01, v2.4+).
- Filled translucent zone shapes (DRAW-FILL-01, v2.4+).
- Rich text formatting (bold / italic / multi-line — v2.4+).
- Multi-line text via Shift+Enter — single-line in v2.3.
- Add / delete vertex post-creation — drag-existing-vertices only in v2.3.
- Engineer-controlled z-order overrides (bring-forward / send-back — v2.4+).
- Toolbar color / style controls — inspector-only per D-10.
- Configurable boundary stroke width — fixed 2px in v2.3.
- Boundaries as semantic zones — decorative only per REQUIREMENTS line 95.
- Right-click context menu on canvas.

## Environment Availability

> All Phase 12 work is code-only inside the existing `planner` app and existing vendored JS bundles. No external runtime dependencies, no new package installs.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `@joint/core` | All Phase 12 shapes + tools | Yes | 4.2.4 (MPL-2.0) | — |
| `html-to-image` | PNG export (no Phase 12 change) | Yes | 1.11.11 | — |
| Django test client | Backend test suite | Yes | Django 5.x | — |
| Python | Test suite | Yes | (project default) | — |

No missing dependencies. No fallbacks required.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Django TestCase (`django.test.TestCase`) |
| Config file | None — standard Django manage.py test discovery |
| Quick run command | `python manage.py test planner.tests.test_signal_flow_phase12 -v 2` |
| Full suite command | `python manage.py test planner -v 2` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| DRAW-01 | Pen-tool mode entry / vertex click / commit | UI / UAT | n/a (browser-UAT in 12-HUMAN-UAT.md) | ❌ Wave 0 (HUMAN-UAT) |
| DRAW-02 | Color + line-style persist on cell | unit | `python manage.py test planner.tests.test_signal_flow_phase12.SignalFlowPhase12AutosaveTests.test_boundary_with_invalid_color_still_saves` | ❌ Wave 0 |
| DRAW-03 | Inspector color + style edit writes to cell | UI / UAT | n/a (browser-UAT) | ❌ Wave 0 |
| DRAW-04 | Vertex drag updates cell.vertices | UI / UAT | n/a (browser-UAT — vertex drag is mouse-driven) | ❌ Wave 0 |
| TXT-01 | Click → inline edit immediately | UI / UAT | n/a (browser-UAT) | ❌ Wave 0 |
| TXT-02 | Font-size + text color persist | unit | `python manage.py test planner.tests.test_signal_flow_phase12.SignalFlowPhase12AutosaveTests.test_text_only_canvas_state_round_trips` | ❌ Wave 0 |
| TXT-03 | Delete keyboard path inherited from shapes | UI / UAT | n/a (browser-UAT — keyboard handler at signal_flow_editor.js:1549 covers all cells) | ❌ Wave 0 |
| **IDOR pass-through** (R-04) | BoundaryLine + TextLabel cells without GFK skip allowlist | unit | `python manage.py test planner.tests.test_signal_flow_phase12.SignalFlowPhase12AutosaveTests.test_boundary_only_canvas_state_round_trips` | ❌ Wave 0 |
| **Mixed-canvas autosave** | Decorative + equipment-linked cells in one save | unit | `python manage.py test planner.tests.test_signal_flow_phase12.SignalFlowPhase12AutosaveTests.test_mixed_boundary_text_equipment_round_trip` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python manage.py test planner.tests.test_signal_flow_phase12 -v 2` (sub-second once the test file lands)
- **Per wave merge:** `python manage.py test planner.tests.test_signal_flow_phase12 planner.tests.test_signal_flow_phase10 planner.tests.test_signal_flow_phase9 -v 2`
- **Phase gate:** Full `python manage.py test planner` suite green + browser-UAT in 12-HUMAN-UAT.md complete before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `planner/tests/test_signal_flow_phase12.py` — file does not yet exist; covers DRAW-02 + TXT-02 + IDOR pass-through + mixed-canvas.
- [ ] `.planning/phases/12-boundaries-and-text/12-HUMAN-UAT.md` — browser-UAT script for DRAW-01, DRAW-03, DRAW-04, TXT-01, TXT-03, PNG-export visual fidelity. (Phase 11 ships `11-HUMAN-UAT.md` — copy that structure.)

## Sources

### Primary (HIGH confidence)
- **`/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/static/planner/js/signal_flow_editor.js`** — read lines 1-360, 537-761, 1497-1720, 1830-2056, 2199-2410, 2700-2750. Source of truth for every cell-class pattern, tool subclass, inspector mode switch, autosave debounce, paper event registration, and PNG export.
- **`/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/views.py`** — read lines 7530-7760. Source of truth for the IDOR allowlist + `_enrich_nodes` skip behavior (R-04, R-05).
- **`/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/templates/planner/signal_flow/editor.html`** — read lines 1-161. Toolbar HTML, inspector partial, equipment picker modal include.
- **`/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/static/planner/css/signal_flow.css`** — read lines 1-60, 275-301, section grep for 7-16. Section-list comment format, `.sfd-segmented` pattern.
- **`/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/static/planner/js/vendor/joint.min.js`** — banner read. `JointJS v4.2.4 (2026-02-13)` confirmed.
- **`/Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/phases/12-boundaries-and-text/12-CONTEXT.md`** — all locked decisions D-01..D-19 + carried decisions.
- **`/Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/REQUIREMENTS.md`** — DRAW-01..04 + TXT-01..03 acceptance criteria.

### Secondary (MEDIUM confidence)
- **[JointJS Standard Shapes API (v4.2)](https://docs.jointjs.com/api/shapes/standard/)** — confirms `joint.shapes.standard.Polyline` exists with a label sub-element, `joint.shapes.standard.TextBlock` exists with HTML label. Used to justify (b)-over-(a) decision on cell class.
- **[JointJS dia/attributes (v4.2)](https://docs.jointjs.com/api/dia/attributes/)** — confirms `refPoints` attribute behavior for polyline children.

### Tertiary (LOW confidence — flagged for verification at implementation)
- The `(0, +3)` y-offset approximation for double-line rendering is a v2.3 simplification — per-segment unit-normal math is more correct and may be needed if UAT reveals visual unacceptability for vertical / diagonal boundaries. Marked as Risk #3 above.
- `html-to-image` behavior on SVG `<text>` vs `foreignObject` rendering is [ASSUMED] from training knowledge — the implementation should briefly UAT-verify PNG export of a 24px white TextLabel cell over a colored boundary before declaring R-02 done.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `(0, +3)` y-offset is acceptable for double-line rendering in v2.3 boundaries (most boundaries are mostly-horizontal architectural walls). | R-01, Risk #3 | UAT may reveal vertical/diagonal boundaries look wrong; follow-up adds per-segment unit-normal math. Confined to a single function (`applyBoundaryRender`). |
| A2 | `html-to-image` cleanly renders SVG `<text>` children in PNG export (no `foreignObject` font-taint concerns). | R-02, R-11 | If PNG export fails for TextLabel cells, fallback is to rasterize text via Canvas-2D `fillText` into an SVG `<image>` data-URI on commit. Workable but invasive. |
| A3 | The Phase 11 user-MEMORY rule about dark-navy inspector palette (#eee primary, #aaa muted) applies to Sections 17 + 18 the same way. | Risk #7 | Wrong: contrast bugs in inspector text. Confined to CSS — quick GAP-fix turnaround. |
| A4 | `cell.toBack()` / `cell.toFront()` on existing cells write to `cell.attributes.z` and survive `graph.toJSON()` round-trip without additional persistence work. | R-10 | If z-order is not persisted, reload would visually re-stack cells in creation order. Confined to a 2-line test (set z, toJSON, fromJSON, assert z). |
| A5 | Multiple `paper.on('blank:pointerdown')` listeners coexist (the rubber-band one + Phase 12 pen-tool one) — verified by in-tree comment but not by source-code inspection of joint.min.js. | R-06 | If only one listener fires, pen-tool drawing breaks silently. Plan mitigates by adding the early-exit guard in BOTH handlers. |

**Three of five assumptions reduce to "verify during UAT" with confined-fix scope. None block the planner from writing executable plans.**

## Open Questions

None blocking. All technical questions in the CONTEXT.md Claude's Discretion section are answered above.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified versions from in-tree vendor bundle banner.
- Architecture: HIGH — every pattern in R-01 through R-14 is grounded in a verbatim in-tree code excerpt or a verified pattern from Phases 8/9/10/11.
- Pitfalls: HIGH — every risk in the table is observed either in the in-tree code (rubber-band overlap, autosave event list omission, Esc handler ordering) or in the user MEMORY (dark-navy palette).

**Research date:** 2026-05-25
**Valid until:** 2026-06-25 (no expected JointJS / @joint/core / html-to-image churn in 30 days; the vendor bundle is pinned at 4.2.4).

## RESEARCH COMPLETE
