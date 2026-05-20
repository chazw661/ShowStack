# Phase 8 Research — Canvas, Smart Shapes & Connectors

**Researched:** 2026-05-20
**Confidence:** HIGH (JointJS API surface verified against the vendored `joint.min.js` 4.2.4 + JointJS docs); HIGH (Django/IDOR patterns verified against `planner/views.py`); MEDIUM (custom undo-stack pattern is project-specific code we own — verified-by-design, not by external citation)
**Source-of-truth files consulted:**
- `planner/static/planner/js/vendor/joint.min.js` (the actual `@joint/core` 4.2.4 we ship — 465 KB minified UMD; treated as authoritative for symbol-presence checks)
- `.planning/research/STACK.md`, `.planning/research/PITFALLS.md`, `.planning/research/SUMMARY.md`, `.planning/research/ARCHITECTURE.md`
- `.planning/phases/08-canvas-smart-shapes-connectors/08-CONTEXT.md` (16 locked decisions)
- `.planning/phases/07-foundation-crud-editor-shell/07-*-SUMMARY.md` (Phase 7 deliverables)
- `planner/views.py` lines 6320–6360 (`_get_track_for_request` IDOR pattern), `planner/models.py` (`SignalFlowDiagram` model), `planner/templates/planner/signal_flow/editor.html`, `planner/static/planner/js/signal_flow_editor.js`
- `https://docs.jointjs.com/learn/features/undo-redo/` (CommandManager import shows `@joint/plus` only — confirms vendored grep)

---

## Executive Summary

The Phase 8 implementation surface is well-understood and de-risked by Phase 7's foundation work plus the project-level research already on file. The single critical research-flag question — **is `CommandManager` in `@joint/core` 4.2.4?** — has a clean answer: **No.** `CommandManager`, `Clipboard`, `PaperScroller`, and `Selection` are JointJS+ (paid, `@joint/plus`) features and are absent from the vendored `joint.min.js`. CNV-05 (undo/redo) must be built as a custom event-sourced undo stack inside `signal_flow_editor.js`; the pattern is straightforward (~120 lines) and documented below. `linkTools.Vertices` and `linkTools.Segments` (needed for CON-04 midpoint waypoints) **are** in `@joint/core` and work as documented.

Every other Phase 8 requirement maps to a well-supported `@joint/core` API or a small custom layer on top of it. No external dependencies are added; the plan stays inside the locked stack (single JS file extended in place).

## Critical Research Flag Resolution

### `@joint/core` 4.2.4 symbol availability (verified by grep on `planner/static/planner/js/vendor/joint.min.js`)

| Symbol | Present in `@joint/core` 4.2.4? | Source of truth | Implication |
|--------|---------------------------------|-----------------|-------------|
| `dia.CommandManager` | **No** | grep returns 0 matches; docs.jointjs.com import example shows `from '@joint/plus'` only | **CNV-05 must use a custom undo stack** (pattern below) |
| `ui.Clipboard` | **No** | grep returns 0 matches | COPY-01 (v2.3 future) likewise needs custom impl; out of Phase 8 scope |
| `ui.PaperScroller` | **No** | grep returns 0 matches | Non-issue — CONTEXT.md D-14 locks finite paper, no PaperScroller dependency |
| `ui.Selection` | **No** | grep returns 0 matches | CNV-06 multi-select must be hand-rolled (already expected) |
| `elementTools.*` | **Yes** | `ToolsView`, `elementTools` symbols present | Used for connector waypoint / port handles |
| `linkTools.Vertices` | **Yes** | `Vertices`, `Segments`, `Anchor`, `Connect`, `Button`, `Remove`, `SourceAnchor`, `TargetAnchor` symbols all present | CON-04 midpoint waypoints work out of the box |
| `dia.Paper`, `dia.Graph`, `shapes.*` | **Yes** | Core JointJS surface | Foundation works as documented |

**Citation:** `https://docs.jointjs.com/learn/features/undo-redo/` shows the ONLY supported `CommandManager` import as `from '@joint/plus'`. No `@joint/core` import path exists. This is authoritative.

### Custom Undo-Stack Pattern (CNV-05 fallback)

Minimum-viable pattern, ~120 lines inside `signal_flow_editor.js`:

```js
function createUndoStack(graph) {
  var undoStack = [];
  var redoStack = [];
  var capturing = true;   // false while we apply an undo/redo (prevents re-recording)
  var batchDepth = 0;
  var currentBatch = null;

  function record(cmd) {
    if (!capturing) return;
    if (batchDepth > 0) {
      currentBatch.push(cmd);
    } else {
      undoStack.push([cmd]);
      redoStack.length = 0;   // any new action invalidates redo history
    }
  }

  graph.on('add', function (cell) {
    record({ type: 'add', cellId: cell.id, json: cell.toJSON() });
  });
  graph.on('remove', function (cell) {
    record({ type: 'remove', cellId: cell.id, json: cell.toJSON() });
  });
  graph.on('change', function (cell, options) {
    if (options && options.undoable === false) return;
    // Snapshot previous and current attribute values from cell.previousAttributes()
    record({
      type: 'change',
      cellId: cell.id,
      before: cell.previousAttributes(),
      after: cell.toJSON(),
    });
  });

  function applyInverse(cmd) {
    capturing = false;
    try {
      if (cmd.type === 'add') {
        var cell = graph.getCell(cmd.cellId);
        if (cell) cell.remove({ undoable: false });
      } else if (cmd.type === 'remove') {
        graph.addCell(cmd.json, { undoable: false });
      } else if (cmd.type === 'change') {
        var c = graph.getCell(cmd.cellId);
        if (c) c.set(cmd.before, { undoable: false });
      }
    } finally {
      capturing = true;
    }
  }

  function applyForward(cmd) {
    capturing = false;
    try {
      if (cmd.type === 'add') {
        graph.addCell(cmd.json, { undoable: false });
      } else if (cmd.type === 'remove') {
        var cell = graph.getCell(cmd.cellId);
        if (cell) cell.remove({ undoable: false });
      } else if (cmd.type === 'change') {
        var c = graph.getCell(cmd.cellId);
        if (c) c.set(cmd.after, { undoable: false });
      }
    } finally {
      capturing = true;
    }
  }

  return {
    undo: function () {
      var batch = undoStack.pop();
      if (!batch) return;
      // Apply inverse in reverse order
      for (var i = batch.length - 1; i >= 0; i--) applyInverse(batch[i]);
      redoStack.push(batch);
    },
    redo: function () {
      var batch = redoStack.pop();
      if (!batch) return;
      for (var i = 0; i < batch.length; i++) applyForward(batch[i]);
      undoStack.push(batch);
    },
    beginBatch: function () { batchDepth++; if (batchDepth === 1) currentBatch = []; },
    endBatch: function () {
      batchDepth = Math.max(0, batchDepth - 1);
      if (batchDepth === 0 && currentBatch && currentBatch.length) {
        undoStack.push(currentBatch);
        redoStack.length = 0;
        currentBatch = null;
      }
    },
    canUndo: function () { return undoStack.length > 0; },
    canRedo: function () { return redoStack.length > 0; },
  };
}
```

**Critical rule:** The custom stack must be wired **before the first `graph.fromJSON()` call** so that initial-load adds are NOT recorded as undoable actions. Use `graph.fromJSON(state, { undoable: false })` (or set `capturing = false` around the load). The same `{ undoable: false }` option is honored by `addCell`, `remove`, and `set` in the pattern above to prevent recursion.

**Keyboard wiring:** `document.addEventListener('keydown', function (e) { ... })`. Guard against typing in inputs (`if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;`). `Ctrl/Cmd+Z` → undo. `Ctrl/Cmd+Shift+Z` → redo (also accept `Ctrl+Y` as alternate per Windows convention).

**Memory cap:** Bound `undoStack.length` to e.g. 50 (push + `.shift()` to drop oldest). Prevents long sessions from accumulating unbounded history.

---

## Implementation Patterns

### 1. Custom shape class definition (SHP-01..05)

Define five `joint.dia.Element` subclasses under a project namespace `joint.shapes.showstack`. Register namespace on the `Graph` constructor explicitly (mandatory in v4 per PITFALLS.md §1 — silent blank canvas if missed):

```js
joint.shapes.showstack = joint.shapes.showstack || {};

joint.shapes.showstack.Console = joint.dia.Element.extend({
  defaults: joint.util.deepSupplement({
    type: 'showstack.Console',
    size: { width: 180, height: 60 },
    attrs: {
      body: {
        refWidth: '100%', refHeight: '100%',
        fill: '#ffffff', stroke: '#333', strokeWidth: 1.5,
      },
      band: {  // left-edge teal accent
        x: 0, y: 0, width: 6, refHeight: '100%',
        fill: '#0d9488', // teal
      },
      label: {
        refX: 16, refY: '50%', textAnchor: 'start', textVerticalAnchor: 'middle',
        fontSize: 13, fontFamily: 'system-ui, sans-serif', fill: '#111',
        text: 'Console',
      },
    },
    ports: { /* see §4 below */ },
  }, joint.dia.Element.prototype.defaults),
  markup: [
    { tagName: 'rect', selector: 'body' },
    { tagName: 'rect', selector: 'band' },
    { tagName: 'text', selector: 'label' },
  ],
});
```

| Type | `width × height` (px, default) | Geometry SVG | Color band |
|------|--------------------------------|--------------|-----------|
| Console | 180 × 60 | `<rect>` body + left-edge `<rect>` band | teal `#0d9488` |
| Device | 140 × 56 | `<rect>` body + left-edge `<rect>` band | slate `#475569` |
| SpeakerArray | 120 × 80 | `<polygon points="20,0 100,0 120,80 0,80"/>` (trapezoid) | orange `#ea580c` |
| CommBeltPack | 80 × 100 | `<rect rx="40" ry="40">` (pill / rounded-rect) | purple `#7c3aed` |
| Generic | 140 × 56 | `<rect>` body with `stroke-dasharray="4 3"` (dashed border) | grey `#94a3b8` |

For polygon/trapezoid `SpeakerArray`, use `<polygon>` in the `markup` array. `refWidth`/`refHeight` work for `<rect>`; `<polygon>` needs `joint.util.shapePerimeterConnectionPoint` for clean connector docking — confirm via smoke test.

**Equipment-binding payload** stored on each typed shape (SHP-01..04 / SHP-09):

```js
console.prop('showstack/contentTypeId', 47);   // ContentType pk for Console model
console.prop('showstack/objectId', 12);        // Console row pk
console.prop('showstack/savedLabel', 'CL5-FOH'); // Snapshot for Phase 9 ghosting (SHP-07)
```

`toJSON()` serializes everything under `attributes` including custom `prop()` paths. Server `_enrich_nodes()` (Phase 9) reads `contentTypeId + objectId`, fetches live record name, overwrites `attrs/label/text`. Phase 8 only needs to write the payload correctly on equipment pick.

**Registration to namespace passed to `new joint.dia.Graph`:**

```js
var cellNamespace = Object.assign(
  {},
  joint.shapes,
  { showstack: joint.shapes.showstack }
);
var graph = new joint.dia.Graph({}, { cellNamespace: cellNamespace });
var paper = new joint.dia.Paper({
  el: document.getElementById('sfd-paper'),
  model: graph,
  cellViewNamespace: cellNamespace,  // same namespace for views
  width: 4000, height: 3000,
  gridSize: 20,
  drawGrid: { name: 'dot', args: { color: '#dde', thickness: 1 } },
  background: { color: '#ffffff' },
});
```

PITFALLS.md §1 specifies this exact pattern. The `cellViewNamespace` (separate from `cellNamespace`) must also point to the same shapes object for custom views (rarely needed for our case but harmless to set).

### 2. Port definitions on shapes (SHP-08)

Per-side single port (per-channel ports deferred to v2.3). Each shape declares 8 ports (4 sides × {in, out}) using JointJS port groups:

```js
ports: {
  groups: {
    in: {
      position: { name: 'left' },
      attrs: {
        portBody: {
          magnet: 'passive',   // accept incoming connections
          r: 4, fill: '#fff', stroke: '#666', strokeWidth: 1,
          opacity: 0,           // hidden at rest (hover-reveal — CONTEXT.md Claude's Discretion)
        },
      },
      markup: [{ tagName: 'circle', selector: 'portBody' }],
    },
    out: {
      position: { name: 'right' },
      attrs: {
        portBody: { magnet: true, r: 4, fill: '#fff', stroke: '#666', opacity: 0 },
      },
      markup: [{ tagName: 'circle', selector: 'portBody' }],
    },
  },
  items: [
    // 1 in + 1 out per side: top/bottom use position.name override per item
    { group: 'in',  args: { y: '50%' } },         // left side, vertical center
    { group: 'out', args: { y: '50%' } },         // right side, vertical center
    { group: 'in',  args: { x: '50%' }, position: 'top' },
    { group: 'out', args: { x: '50%' }, position: 'bottom' },
  ],
}
```

**Hover reveal:** Use CSS `.joint-paper .joint-element:hover .joint-port circle { opacity: 1 !important; }` (and during link drag — JointJS adds class `is-link-target-magnet` to candidate magnets; style that selector with `opacity: 1`). The `!important` is required per CLAUDE.md because the JointJS-generated SVG sits inside admin DOM and other admin CSS can win specificity wars — but for SVG elements, CSS variables / specificity usually work fine; verify in smoke test.

**Magnet semantics:**
- `magnet: true` — outbound source (drag starts from here)
- `magnet: 'passive'` — inbound target (accept connections but not source new ones)
- This naturally enforces "drag from out → in" while still allowing both directions if the user picks an `out` on each end (acceptable).

### 3. Drag-from-sidebar → drop-on-canvas (CNV-01)

HTML5 drag-drop API with `paper.clientToLocalPoint()` (PITFALLS.md §2):

```html
<div id="sfd-sidebar">
  <button class="sfd-tile" draggable="true" data-shape-type="Console">Console</button>
  <button class="sfd-tile" draggable="true" data-shape-type="Device">Device</button>
  <!-- SpeakerArray, CommBeltPack, Generic -->
</div>
```

```js
document.querySelectorAll('.sfd-tile').forEach(function (tile) {
  tile.addEventListener('dragstart', function (e) {
    e.dataTransfer.setData('application/x-shape-type', tile.dataset.shapeType);
    e.dataTransfer.effectAllowed = 'copy';
  });
});

var paperEl = document.getElementById('sfd-paper');
paperEl.addEventListener('dragover', function (e) { e.preventDefault(); });
paperEl.addEventListener('drop', function (e) {
  e.preventDefault();
  var shapeType = e.dataTransfer.getData('application/x-shape-type');
  if (!shapeType) return;
  var local = paper.clientToLocalPoint({ x: e.clientX, y: e.clientY });
  // Snap to grid (CONTEXT.md D-13)
  if (snapEnabled) {
    local.x = Math.round(local.x / 20) * 20;
    local.y = Math.round(local.y / 20) * 20;
  }
  var ShapeClass = joint.shapes.showstack[shapeType];
  var node = new ShapeClass({ position: local });
  graph.addCell(node);
  if (shapeType !== 'Generic') {
    openEquipmentPicker(shapeType, node);  // CONTEXT.md D-09 (drop-first, modal at drop site)
  }
});
```

### 4. Pan (CNV-02): space+drag and middle-click

```js
var panState = { spaceDown: false, dragging: false, startX: 0, startY: 0, baseTx: 0, baseTy: 0 };

document.addEventListener('keydown', function (e) {
  if (e.code === 'Space' && !/INPUT|TEXTAREA/.test(e.target.tagName)) {
    panState.spaceDown = true;
    paperEl.style.cursor = 'grab';
    e.preventDefault();
  }
});
document.addEventListener('keyup', function (e) {
  if (e.code === 'Space') { panState.spaceDown = false; paperEl.style.cursor = ''; }
});

paperEl.addEventListener('mousedown', function (e) {
  var isMiddle = e.button === 1;
  var isSpaceLeft = e.button === 0 && panState.spaceDown;
  if (!isMiddle && !isSpaceLeft) return;
  panState.dragging = true;
  panState.startX = e.clientX; panState.startY = e.clientY;
  var t = paper.translate();
  panState.baseTx = t.tx; panState.baseTy = t.ty;
  paperEl.style.cursor = 'grabbing';
  e.preventDefault();
});
document.addEventListener('mousemove', function (e) {
  if (!panState.dragging) return;
  paper.translate(panState.baseTx + (e.clientX - panState.startX), panState.baseTy + (e.clientY - panState.startY));
});
document.addEventListener('mouseup', function () {
  if (!panState.dragging) return;
  panState.dragging = false;
  paperEl.style.cursor = panState.spaceDown ? 'grab' : '';
  schedulePersistViewport();
});
```

### 5. Zoom in/out/fit (CNV-03)

```js
var scale = 1.0;
function zoomTo(newScale, cx, cy) {
  newScale = Math.max(0.25, Math.min(2.0, newScale));
  paper.scale(newScale, newScale);
  scale = newScale;
  schedulePersistViewport();
}
function zoomIn()  { zoomTo(scale * 1.2); }
function zoomOut() { zoomTo(scale / 1.2); }
function zoomToFit() {
  var bbox = graph.getBBox();
  if (!bbox || bbox.width === 0) { zoomTo(1.0); paper.translate(0, 0); return; }
  var paperW = paperEl.clientWidth, paperH = paperEl.clientHeight;
  var fitScale = Math.min(paperW / (bbox.width + 80), paperH / (bbox.height + 80), 2.0);
  paper.scale(fitScale, fitScale);
  paper.translate(-bbox.x * fitScale + 40, -bbox.y * fitScale + 40);
  scale = fitScale;
  schedulePersistViewport();
}
```

### 6. Snap-to-grid toggle (CNV-04)

```js
var snapEnabled = true;   // CONTEXT.md D-13 default
function setSnap(on) {
  snapEnabled = on;
  paper.setGrid(on ? 20 : 1);  // gridSize = 1 effectively disables snapping
  paper.drawGrid(on ? { name: 'dot', args: { color: '#dde', thickness: 1 } } : null);
}
```

Element drag honors `paper.setGridSize()` automatically when `paper.options.snapLinks = true` is set or via `model.translate({ snap: true })`. For the sidebar drop (above), apply snap math manually.

### 7. Undo/redo (CNV-05) — see Critical Research Flag Resolution above for the full pattern.

### 8. Multi-select (CNV-06) — shift-click + rubber-band

JointJS `@joint/core` has no built-in selection. Maintain a `selectedSet = new Set()` and a tools view per selected cell:

```js
var selectedSet = new Set();

paper.on('element:pointerclick', function (elementView, evt) {
  var id = elementView.model.id;
  if (evt.shiftKey) {
    if (selectedSet.has(id)) selectedSet.delete(id); else selectedSet.add(id);
  } else {
    selectedSet.clear();
    selectedSet.add(id);
  }
  redrawSelection();
});
paper.on('link:pointerclick', function (linkView, evt) { /* same logic */ });
paper.on('blank:pointerclick', function () { selectedSet.clear(); redrawSelection(); });
```

**Rubber-band on blank drag:**
```js
paper.on('blank:pointerdown', function (evt, x, y) {
  if (panState.spaceDown || evt.button !== 0) return;
  var rect = createSelectionRectOverlay(x, y);
  function onMove(evt2) { updateRect(rect, evt2); }
  function onUp(evt2) {
    var area = rectToArea(rect);
    var hits = paper.findViewsInArea(area);
    selectedSet.clear();
    hits.forEach(function (v) { selectedSet.add(v.model.id); });
    redrawSelection();
    removeRect(rect);
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onUp);
  }
  document.addEventListener('pointermove', onMove);
  document.addEventListener('pointerup', onUp);
});
```

`paper.findViewsInArea({ x, y, width, height })` is a documented `@joint/core` method that returns all element views whose bounding boxes intersect the area.

**Selection style (CONTEXT.md D-08):** add a CSS class `is-selected` to each selected view's SVG group; style with `outline: 2px solid var(--accent)` (or `stroke-width: 2.5` adjustment on the body). Multi-select bbox: render a dashed SVG `<rect>` overlay around `paper.localToClientRect(graph.getCellsBBox(selectedCells))`.

### 9. Keyboard delete (CNV-07)

```js
document.addEventListener('keydown', function (e) {
  if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  if (e.key === 'Delete' || e.key === 'Backspace') {
    var ids = Array.from(selectedSet);
    if (!ids.length) return;
    undoStack.beginBatch();
    ids.forEach(function (id) {
      var cell = graph.getCell(id);
      if (cell) cell.remove();
    });
    undoStack.endBatch();
    selectedSet.clear();
    redrawSelection();
    e.preventDefault();
  }
});
```

### 10. Viewport persistence (CNV-08)

`SignalFlowDiagram.viewport` JSONField (Phase 7 locked). Phase 8 reads on load, writes on debounce. Schema: `{ x: number, y: number, scale: number, snapEnabled: bool }`.

```js
function schedulePersistViewport() {
  clearTimeout(viewportTimer);
  viewportTimer = setTimeout(function () {
    var t = paper.translate();
    var payload = { x: t.tx, y: t.ty, scale: scale, snapEnabled: snapEnabled };
    fetch(viewportUrl, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
      body: JSON.stringify(payload),
    });
  }, 800);  // 800ms debounce; not the full canvas autosave (that's Phase 9)
}
```

The viewport write is independent of the full canvas-state autosave; persisting it on debounce gives CNV-08 without entangling with Phase 9 (which builds the version-checked autosave for `canvas_state`). Use the existing `data-autosave-url` endpoint with a `?viewport_only=1` query param OR a dedicated tiny endpoint — planner can pick. (Plan recommendation: add a tiny `signal_flow_save_viewport` view that updates ONLY the `viewport` field, no version check needed since viewport is per-user-session-ish — last write wins is fine.)

On diagram open: read `data-state-url` (Phase 7-stubbed endpoint that returns `{ canvas_state, viewport, version }`), and restore: `paper.translate(viewport.x, viewport.y); paper.scale(viewport.scale, viewport.scale); setSnap(viewport.snapEnabled);` — fall back to `{ x: 0, y: 0, scale: 1, snapEnabled: true }` (CONTEXT.md D-15).

### 11. Orthogonal connector routing (CON-01)

Define a custom Link class:

```js
joint.shapes.showstack.SignalLink = joint.shapes.standard.Link.extend({
  defaults: joint.util.deepSupplement({
    type: 'showstack.SignalLink',
    router: { name: 'orthogonal' },
    connector: { name: 'rounded', args: { radius: 4 } },
    attrs: {
      line: {
        stroke: '#1a1a1a', strokeWidth: 2, strokeDasharray: 'none',
        targetMarker: { type: 'path', d: 'M 10 -5 0 0 10 5 z', fill: '#1a1a1a', stroke: 'none' },
        sourceMarker: { type: 'none' },
      },
    },
    signalType: 'analog',    // custom attr; default per CONTEXT.md
    direction: 'forward',    // 'forward' | 'bidirectional'
    circuitLabel: '',
  }, joint.shapes.standard.Link.prototype.defaults),
});
```

`router.orthogonal` and `connector.rounded` are documented `@joint/core` defaults. Set `paper.options.defaultLink = function () { return new joint.shapes.showstack.SignalLink(); }` so new links spawned from port drags inherit the type.

### 12. Port snapping / reject mid-shape (CON-03)

```js
paper.options.validateConnection = function (sourceView, sourceMagnet, targetView, targetMagnet, end, linkView) {
  // Reject if no magnets on either end
  if (!sourceMagnet || !targetMagnet) return false;
  // Reject self-connections
  if (sourceView === targetView) return false;
  return true;
};
paper.options.linkPinning = false;   // disallow links with endpoints in empty space
paper.options.snapLinks = { radius: 24 };   // snap to nearest port within 24px
```

`paper.options.snapLinks` is documented in `@joint/core`. Setting `linkPinning = false` is the one-line guard that rejects mid-shape drops.

### 13. Signal-type recipe (CON-02)

```js
var SIGNAL_TYPE_STYLES = {
  analog:   { stroke: '#1a1a1a', strokeWidth: 2,   strokeDasharray: 'none'      },
  AES:      { stroke: '#1565c0', strokeWidth: 2,   strokeDasharray: 'none'      },
  Dante:    { stroke: '#00bcd4', strokeWidth: 2,   strokeDasharray: '6 4'       },
  MADI:     { stroke: '#ef6c00', strokeWidth: 2.5, strokeDasharray: '10 3 3 3'  },
  intercom: { stroke: '#7b1fa2', strokeWidth: 2,   strokeDasharray: '2 4'       },
};
function applySignalType(link, type) {
  var s = SIGNAL_TYPE_STYLES[type];
  link.attr('line/stroke', s.stroke);
  link.attr('line/strokeWidth', s.strokeWidth);
  link.attr('line/strokeDasharray', s.strokeDasharray);
  if (link.attributes.direction !== 'bidirectional') {
    link.attr('line/targetMarker/fill', s.stroke);
  }
  link.prop('signalType', type);
}
```

Per CONTEXT.md D-16 — exact values locked in the table.

### 14. Connector direction (CON-05)

```js
function applyDirection(link, direction) {
  link.prop('direction', direction);
  if (direction === 'bidirectional') {
    link.attr('line/sourceMarker', { type: 'none' });
    link.attr('line/targetMarker', { type: 'none' });
  } else {
    link.attr('line/sourceMarker', { type: 'none' });
    link.attr('line/targetMarker', { type: 'path', d: 'M 10 -5 0 0 10 5 z', fill: link.attr('line/stroke') });
  }
}
```

### 15. Connector midpoint waypoints (CON-04)

Wire `linkTools.Vertices` on link select (confirmed present in `@joint/core` per grep):

```js
paper.on('link:pointerclick', function (linkView) {
  if (linkView.hasTools()) return;  // already attached
  var tools = new joint.dia.ToolsView({
    tools: [
      new joint.linkTools.Vertices(),
      new joint.linkTools.SourceAnchor(),
      new joint.linkTools.TargetAnchor(),
      new joint.linkTools.Remove({ distance: -20 }),
    ],
  });
  linkView.addTools(tools);
});
paper.on('blank:pointerclick link:contextmenu', function () {
  paper.removeTools();
});
```

`Vertices` tool ships drag handles at link midpoints — dragging adds/moves waypoints. Standard JointJS behavior.

### 16. Circuit-label rendering along the line (CON-06)

`@joint/core` `Link.label()` API:

```js
link.labels([{
  position: { distance: 0.5, offset: -10 },  // 50% along the link, 10px above
  attrs: {
    text: {
      text: 'CKT-01',
      fill: '#111',
      fontSize: 11,
      fontFamily: 'system-ui, sans-serif',   // system fonts only per REQUIREMENTS Constraints
    },
    rect: {
      fill: 'rgba(255,255,255,0.85)',
      stroke: '#aaa', strokeWidth: 0.5,
      ref: 'text', refWidth: '110%', refHeight: '110%', refX: '-5%', refY: '-5%',
    },
  },
  markup: [{ tagName: 'rect', selector: 'rect' }, { tagName: 'text', selector: 'text' }],
}]);
```

Inspector input writes to the label on every keystroke (debounce optional).

### 17. Equipment-picker autocomplete view (SHP-09, supports SHP-01..04)

The `planner:signal_flow_autocomplete` URL exists from Phase 7 (stub). Phase 8 must implement the view. Pattern:

```python
@login_required
@require_GET
def signal_flow_autocomplete(request):
    """Return JSON list of project-scoped equipment records for the picker modal.

    Query params: ?type=console&q=foo
    type ∈ {console, device, speakerarray, commbeltpack}
    q is optional substring filter.

    IDOR-safe: every queryset filters on request.current_project.
    Pattern mirrors _get_track_for_request (planner/views.py:6328).
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)

    shape_type = (request.GET.get('type') or '').lower()
    q = request.GET.get('q', '').strip()

    MODEL_MAP = {
        'console':      (Console,      ['name', 'dsp_mixer'], lambda c: f"{c.dsp_mixer or ''} · {c.channel_count or ''} ch"),
        'device':       (Device,       ['name', 'model', 'serial'], lambda d: f"{d.model or ''} · S/N {d.serial or ''}"),
        'speakerarray': (SpeakerArray, ['name'], lambda s: f"{s.cabinet_count or ''} cabinets"),
        'commbeltpack': (CommBeltPack, ['name', 'beltpack_id'], lambda b: f"ID {b.beltpack_id or ''}"),
    }
    if shape_type not in MODEL_MAP:
        return JsonResponse({'error': 'Invalid type'}, status=400)

    Model, search_fields, detail_fn = MODEL_MAP[shape_type]
    qs = Model.objects.filter(project=current_project)
    if q:
        from django.db.models import Q
        cond = Q()
        for f in search_fields:
            cond |= Q(**{f'{f}__icontains': q})
        qs = qs.filter(cond)
    qs = qs.order_by('name')[:50]   # Hard cap; instant-search UX

    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(Model)

    results = [
        {
            'id': obj.pk,
            'contentTypeId': ct.pk,
            'name': obj.name,
            'detail': detail_fn(obj),
        }
        for obj in qs
    ]
    return JsonResponse({'results': results})
```

**Note on `search_fields` per type:** The current model fields shown (e.g. `dsp_mixer`, `channel_count`, `cabinet_count`, `beltpack_id`) are best-guess names from CONTEXT.md D-11; planner should verify against `planner/models.py` and adjust to exact field names. If a field doesn't exist on a model, fall back to `name` only for that type.

**No new URL needed** — `planner:signal_flow_autocomplete` already maps in `planner/urls.py` from Phase 7 (Plan 03 summary confirms). Phase 8 just implements the view body. Same applies to viewport save and full canvas save endpoints (all stub views exist; Phase 8 fills in viewport+manual-save behavior; Phase 9 fills in real autosave).

### 18. Equipment picker modal (CONTEXT.md D-09..12)

Reuse the admin modal pattern from `templates/includes/_help_modal.html`. Phase 8 adds a new modal template `planner/templates/planner/signal_flow/_equipment_picker_modal.html` (included once from `editor.html`), with structure:

```html
<div id="sfd-picker-modal" class="modal-backdrop" hidden>
  <div class="modal-card">
    <h3 class="modal-title">Pick a <span class="sfd-picker-type">Console</span></h3>
    <input type="text" id="sfd-picker-search" placeholder="Search by name, model, serial…" autofocus>
    <ul id="sfd-picker-results" class="sfd-picker-list">
      <!-- populated by autocomplete fetch -->
    </ul>
    <div class="modal-actions">
      <button type="button" id="sfd-picker-cancel">Cancel</button>
    </div>
  </div>
</div>
```

CSS reuses tokens from `custom_admin.css`; only ~80 lines of new CSS to add (modal backdrop, card, list-row hover state). Per CLAUDE.md, any JS-driven inline style writes on these admin-DOM elements must use `setProperty('important')`.

**Picker flow:**
1. `openEquipmentPicker(shapeType, node)` — un-hide modal, focus search input, fetch initial 50 results
2. On keystroke in search input — debounced (200ms) fetch with `?type=X&q=...`
3. On result click — set `node.prop('showstack/contentTypeId', r.contentTypeId); node.prop('showstack/objectId', r.id); node.prop('showstack/savedLabel', r.name); node.attr('label/text', r.name);` and close
4. On Cancel button / Escape key / backdrop click — `node.remove({ undoable: false })` (Phase 8 D-10: no half-built nodes) and close

### 19. Manual save trigger for Phase 8 (deferred-real-autosave)

A "Save" button on the toolbar that POSTs the full `graph.toJSON()` to `data-autosave-url`. The stub view from Phase 7 needs minimal real behavior:

```python
@login_required
@require_POST
def signal_flow_autosave(request, diagram_id):
    viewer_block = _signal_flow_viewer_block(request)   # new helper, mirrors _multitrack_viewer_block
    if viewer_block: return viewer_block
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)
    diagram = SignalFlowDiagram.objects.filter(id=diagram_id, project=current_project).first()
    if not diagram:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Bad JSON'}, status=400)

    # Walk canvas JSON, validate equipment refs (PITFALLS.md §4)
    canvas_state = payload.get('canvas_state', {})
    cells = canvas_state.get('cells', [])
    for cell in cells:
        prop = cell.get('showstack') or {}
        ct_id = prop.get('contentTypeId')
        obj_id = prop.get('objectId')
        if ct_id and obj_id:
            ct = ContentType.objects.filter(id=ct_id).first()
            if not ct:
                return JsonResponse({'error': f'Unknown content type {ct_id}'}, status=422)
            Model = ct.model_class()
            if not hasattr(Model, 'project'):
                return JsonResponse({'error': f'Type {ct.model} has no project scope'}, status=422)
            if not Model.objects.filter(id=obj_id, project=current_project).exists():
                return JsonResponse({'error': 'Equipment reference out of project'}, status=422)

    diagram.canvas_state = canvas_state
    diagram.viewport = payload.get('viewport', diagram.viewport)
    diagram.version = (diagram.version or 1) + 1   # bump, even without conflict check yet
    diagram.save(update_fields=['canvas_state', 'viewport', 'version', 'updated_at'])
    return JsonResponse({'ok': True, 'version': diagram.version})
```

**Phase 9 will add:** `version` conflict check, debounce on JS side, `keepalive` fetch on unload, HTTP 409 banner. Phase 8 ships the IDOR + equipment-ref validation now (mandatory baseline per PITFALLS.md §4). The simplified version bump (no conflict check) is acceptable for Phase 8 — single-tab manual save flow can't race itself.

### 20. CSRF + role check helpers

`_signal_flow_viewer_block(request)` — new helper paralleling `_multitrack_viewer_block` (planner/views.py near line 6320). Both autocomplete and save endpoints call it. Viewers (read-only) get 403 on autosave but can still GET state (separate endpoint, no helper).

CSRF token read via existing `getCsrfToken()` pattern from `templates/planner/mic_tracker.html:1212-1215` — copy that helper into `signal_flow_editor.js` (already there in stub? confirm). Read fresh on every fetch (PITFALLS.md §5).

---

## Per-Requirement Coverage Map

| REQ-ID | Approach summary | Risk | Notes |
|--------|------------------|------|-------|
| CNV-01 | HTML5 drag-drop + `paper.clientToLocalPoint()`; snap math applied if `snapEnabled`. Open equipment picker for typed shapes; place Generic directly. | low | PITFALLS.md §2 enforced via `clientToLocalPoint` |
| CNV-02 | Space-bar state + middle-click `mousedown`/`mousemove` listeners; `paper.translate()` updates. | low | Standard pattern |
| CNV-03 | Toolbar buttons call `zoomIn/Out/ToFit`; `paper.scale()` + bounded 0.25–2.0; fit uses `graph.getBBox()`. | low | `getBBox()` is `@joint/core` |
| CNV-04 | Toolbar toggle calls `setSnap(bool)`; `paper.setGrid()` switches between 20px and 1px (effectively off). | low | |
| CNV-05 | Custom undo stack (no CommandManager in `@joint/core`); subscribes to `add`/`remove`/`change` events; supports `beginBatch`/`endBatch`. Wired before `fromJSON()`. | **medium** | The custom stack is ~120 lines of project code; plan should include a smoke test that covers undo of add/remove/move/connect/disconnect. |
| CNV-06 | Shift-click toggles `selectedSet`; rubber-band via `blank:pointerdown` + `paper.findViewsInArea()` on `mouseup`. | low | `findViewsInArea` is `@joint/core` |
| CNV-07 | Document-level keydown for Delete/Backspace; guard against typing-in-input; batched remove via undo stack. | low | |
| CNV-08 | Debounced POST of `{ x, y, scale, snapEnabled }` to viewport endpoint on pan/zoom; restore on diagram open. | low | Use a tiny dedicated view (no version check needed for per-user viewport) |
| SHP-01..04 | `joint.shapes.showstack.{Console,Device,SpeakerArray,CommBeltPack}` shape classes with type-specific geometry + color band; drop-first equipment picker modal binds `(contentTypeId, objectId, savedLabel)`. | low | PITFALLS.md §1 (cellNamespace) enforced |
| SHP-05 | `joint.shapes.showstack.Generic` shape with dashed border + grey band; skips picker on drop; label is freeform via inspector (or double-click-to-edit). | low | |
| SHP-08 | Per-side single-port (in left, out right, in top, out bottom — 4-side variant for flexibility, or strictly in-left/out-right if simpler). Magnet types: out=true (source), in='passive' (target). | low | Hover reveal via CSS |
| SHP-09 | Autocomplete view filters every queryset on `request.current_project`. IDOR pattern from `planner/views.py:6328`. | low | PITFALLS.md §4 |
| CON-01 | `paper.options.defaultLink` returns SignalLink with `router: 'orthogonal'` and `connector: 'rounded'`. Drag from port magnet to port magnet. | low | |
| CON-02 | Inspector dropdown writes `link.prop('signalType', type)`; `applySignalType()` sets stroke + dashes from D-16 table. | low | |
| CON-03 | `paper.options.linkPinning = false` + `validateConnection()` returns false for missing magnets / self-loops. | low | |
| CON-04 | `linkTools.Vertices` (confirmed in `@joint/core` 4.2.4) attached on `link:pointerclick`. | low | |
| CON-05 | Inspector toggle writes `link.prop('direction', d)`; `applyDirection()` strips or adds target marker. | low | |
| CON-06 | Inspector text input writes `link.labels([{ ... text: { text } }])`; renders along the line via JointJS native label positioning. | low | System font only (REQUIREMENTS Constraints) |

---

## Open Risks for Planner

1. **Custom undo stack edge cases.** Multi-cell drag (when JointJS emits a flurry of `change:position` events) must be batched into a single undo entry — wrap drag-start/drag-end with `undoStack.beginBatch()/endBatch()`. Plan should include a smoke test for "drag 3 selected nodes 100px and undo once → all 3 return to original positions."

2. **Trapezoid (SpeakerArray) connector docking.** SVG `<polygon>` paths don't honor `refWidth`/`refHeight` cleanly. May need `joint.util.shapePerimeterConnectionPoint` in the shape's `connection-point` strategy to ensure connectors meet the polygon edge rather than the bounding-box edge. Verify in smoke test; if problematic, fall back to a rect+chamfer SVG instead of polygon.

3. **Equipment model field names.** The autocomplete `MODEL_MAP` above guesses at field names (`dsp_mixer`, `channel_count`, `serial`, `cabinet_count`, `beltpack_id`). Planner must verify against `planner/models.py` for each model and adjust. Fall back to `name` only if a guessed field doesn't exist.

4. **Selection visual on JointJS SVG elements.** Adding a CSS class like `is-selected` requires JointJS to expose a way to add classes to a cell view — the `joint.dia.ElementView` and `joint.dia.LinkView` both support `cellView.el.classList.add(...)`. Verify in smoke test that the class persists across re-renders (it may not — JointJS sometimes re-creates the SVG on attribute changes). Fallback: write `selected: true` as an attribute and target via CSS attribute selector.

5. **Manual save button is not a Phase 9 substitute.** The Phase 8 manual Save is enough to verify the round-trip (write → reload → restore canvas state). Phase 9's debounced autosave + version conflict + keepalive on unload remain Phase 9 scope. Plan should NOT add debounced autosave in Phase 8 — that's scope creep and conflicts with PITFALLS.md §3's design (which requires version conflict in the same patch).

6. **Connector inspector + selection layer must coexist.** Inspector auto-show triggers on `link:pointerclick`. Selection toggle also triggers on `link:pointerclick`. Order matters — the selection handler should run first, then if the new selection is a single connector, show the inspector. Plan should sequence the two handlers explicitly.

7. **Keyboard shortcut conflicts.** Browser Ctrl+Z is also browser-level undo for inputs. The keydown handler must `e.preventDefault()` once it has decided to handle the event. Plan should cover this in the keyboard-handler task acceptance criteria.

---

## Pre-Existing Patterns to Reuse

| Pattern | Citation | What to copy |
|---------|----------|--------------|
| IDOR-safe model lookup | `planner/views.py:6328` `_get_track_for_request` | `Model.objects.filter(id=X, project=current_project).first()` shape |
| Viewer-role read-only guard | `planner/views.py:6300-6310` `_multitrack_viewer_block` | Replicate as `_signal_flow_viewer_block(request)` |
| CSRF token reader | `templates/planner/mic_tracker.html:1212-1215` `getCsrfToken()` | Copy into `signal_flow_editor.js` |
| `@admin.register(M, site=showstack_admin_site)` | `planner/admin.py` (SignalFlowDiagramAdmin already done in Phase 7) | No-op for Phase 8 |
| Vendor JS layout | `planner/static/planner/js/vendor/joint.min.js` (locked) | Phase 8 adds no new vendor files |
| Modal pattern | `templates/includes/_help_modal.html` | Reuse backdrop + card structure, extend CSS in `custom_admin.css` (or scoped `signal_flow.css` if isolation is preferred) |
| `setProperty(...'important')` rule | `CLAUDE.md §Overriding Django admin CSS from JavaScript` | Apply to ALL toolbar / sidebar / inspector / modal element style writes |
| Equipment changelist links | `showstack_admin_site` URLs for Console, Device, SpeakerArray, CommBeltPack | Used in the picker modal's empty-state "Add equipment in Admin" link |

---

## RESEARCH COMPLETE
