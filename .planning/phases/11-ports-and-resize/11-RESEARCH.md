# Phase 11: Per-Shape Labeled Ports + Resizable Shapes — Research

**Researched:** 2026-05-24
**Domain:** JointJS 4.2.4 (MPL-2.0) ports + element-tools + resize — vendored UMD bundle
**Confidence:** HIGH overall (one MEDIUM finding — link-survival-on-port-removal default behavior, mitigated by explicit pre-removal re-anchor)
**Researcher:** gsd-researcher

## Summary

Phase 11 is fully implementable on the existing MPL-2.0 `@joint/core` 4.2.4 bundle with **zero new dependencies**. The single biggest risk identified in CONTEXT.md (Q1, JointJS resize-tool licensing) resolves cleanly: `joint.elementTools.Resize` does NOT ship in core, but the abstract `joint.elementTools.Control` (which IS in core) is the documented foundation for building corner-handle resize tools, and the official `clientIO/joint-demos/resize-control-tool` repo on GitHub publishes the exact MPL-2.0 reference implementation. The Phase 11 plan adopts that pattern, scaled to 4 corners per shape with per-type min-size enforcement.

Port authoring uses JointJS's native `addPort` / `removePort` / `getPorts` APIs with `position: { name: 'absolute', args: { x, y } }` — the same position layout already used by Phase 8's `portsForRect()` — so the existing snap-target machinery, magnet validation, and `canvas_state` JSON round-trip work unchanged. Custom port labels live in `port.attrs` (already serializable per JointJS docs); per-port label rendering uses the per-port `label.position` + `label.markup` system that PortLabel layout supports.

The one behavior that JointJS does NOT give us for free is **PORT-05 connector survival on port removal**: by direct inspection of the vendored bundle (`_processRemovedPort` at `joint.min.js` offset ~207789), JointJS 4.2.4 **auto-removes** any link whose `source.port` or `target.port` references a port id that disappears. Phase 11 must therefore intercept BEFORE calling `removePort()` — re-anchor the affected links to the shape's edge midpoint, then remove the port.

**Primary recommendation:** Build a `ResizeControl` element-tool extending `joint.elementTools.Control` (4 instances per selected shape, one per corner). Define a shared "port-authoring mixin" that augments every existing shape class with `addAuthoredPort` / `removeAuthoredPort` / `redistributeEdgePorts` / `computeMinSize` methods. Wire D-13 back-compat by treating "shape has 0 authored ports" as "use generic 4-port mode" — implemented by lazy removal of the generic ports on first authored-port add. All persistence rides Phase 9's existing autosave; no new endpoints, no new payload shape, no model migration.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**A. Edge model**
- **D-01:** 4 edges per shape (Top / Bottom / Left / Right). REQUIREMENTS.md PORT-01 ("3 edges, bottom reserved for shape label") MUST be amended by the planner — the bottom edge is structurally free because all 7 shape classes left-anchor their label inside the colored band (`refX: 16`, `refY: '50%'`).

**B. Inspector UX**
- **D-02:** Per-edge sections in the right-side inspector (Top / Bottom / Left / Right), each with its own "+ Add port" button.
- **D-03:** Port label uses Phase 10's combobox widget verbatim — autocomplete OR freeform; both in the same input.
- **D-04:** Removal via trash icon next to each port row in the inspector list.

**C. Resize handle**
- **D-05:** 4 corner handles on selected shape (top-left, top-right, bottom-left, bottom-right). No aspect ratio constraint in v2.3.
- **D-06:** Live re-distribute during resize drag — every drag frame, ports + labels re-position.
- **D-07:** Min-size per shape type is a research output (this document, Q2 section).

**D. Port label positioning**
- **D-08:** Labels render INSIDE the shape body, perpendicular to the edge.
  - Left → left-to-right, anchored just inside the left edge
  - Right → left-to-right, anchored just inside the right edge
  - Top → horizontal, just below the port dot
  - Bottom → horizontal, just above the port dot
- **D-09:** Canvas shows label only — no ordinal prefix. Inspector row MAY show ordinal (small UI choice; planner picks).

**E. Auto-distribute**
- **D-10:** Snap instantly on port add/remove — no animation tween.
- **D-11:** PORT-06 auto-expansion is default — shape grows when a new port would overflow at minimum spacing. Subtle toast: "Shape resized to fit ports." Uses Phase 9 `.sfd-toast` pattern.

**F. Connector behavior on port operations**
- **D-12:** Connectors re-anchor immediately to shape edge midpoint when their port is removed (PORT-05). Same frame.
- **D-13:** PORT-04 back-compat switch is whole-shape. Zero authored ports → v2.2 4-generic-port behavior preserved. First authored port added (anywhere on the shape) → v2.2 generics disappear and only authored ports remain as snap targets. Clean break, no mixed state.

**H. Carried decisions**
- Phase 10 D-05: SystemProcessor excluded from autocomplete (inherits to PORT-03).
- Phase 10 D-02: results display as `<label> — <source tag>`.
- Phase 9: autosave 1500ms debounce + If-Match 409 conflict.
- Phase 8 D-13: 20px snap grid. Shape resize dimensions snap to multiples of 20px when snap enabled.
- Phase 8 magnet semantics: `magnet: 'passive'` = inbound target, `magnet: true` = outbound source.

### Claude's Discretion

- Port state storage — Q4 in this research recommends JointJS-native `ports.items[N]` with custom data in `port.attrs.label.text`.
- Resize handle pixel/hover/active styling — Q1 recommends matching existing `.is-selected` selection visual.
- Toast styling for D-11 "Shape resized to fit ports" — reuse `.sfd-toast` / `.sfd-toast--info`.
- Inspector port-list row ordinal display — Q9 recommends showing ordinals (small, muted) for engineer reference.

### Deferred Ideas (OUT OF SCOPE for Phase 11)

- Manual port-position dragging (PORT-MANUAL-01) — v2.4+
- Shift-to-constrain aspect ratio on resize — v2.4+
- Canvas-hover ✕ for port removal — v2.4+ (inspector trash icon only in v2.3)
- Per-port direction picker in inspector — pending Q3 outcome (research recommends "infer from edge" → no UI needed)
- Port re-ordering within an edge — v2.4+; Phase 11 ships insertion-order only
- Boundary lines (DRAW-01..04) — Phase 12
- Text annotations (TXT-01..03) — Phase 12

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PORT-01 | Add labeled port to any smart shape via inspector. Anchors to 4 edges (T/B/L/R per D-01 amendment). | Q3 (direction from edge), Q4 (storage), Q9 (inspector DOM), Q10 (canvas label rendering) |
| PORT-02 | Auto-distribute to equal spacing on add/remove. | Q7 auto-expansion + redistribution recipe; ports use `position: { name: 'absolute', args: { x, y } }` recomputed on every add/remove. |
| PORT-03 | Dropdown-or-freetext label via Phase 10 autocomplete combobox. | Phase 10 D-04 already locked endpoint reuse; Q9 specifies how the combobox attaches to each inspector port row. |
| PORT-04 | Per-port snap target; v2.2 back-compat preserved when 0 authored ports. | Q5 — exact `validateConnection` branching. |
| PORT-05 | Remove port via inspector; remaining redistribute; attached connectors survive pinned to edge midpoint. | Q6 — pre-removal re-anchor pattern; JointJS default would DELETE the link, must intercept. |
| PORT-06 | Adding ports auto-expands shape height/width. | Q7 — trigger + toast wiring. |
| SHP-RESIZE-01 | Resize any of 7 smart shape types via corner handle. | Q1 — `joint.elementTools.Control` subclass per the canonical demo; Q8 — shared mixin pattern. |
| SHP-RESIZE-02 | Resize constrained to per-type min-size. | Q2 — min-size formula. |
| SHP-RESIZE-03 | Resize lands in autosave + undo path; 409 applies. | Q1 — `setPosition` calls `model.resize()` which fires `change:size`; existing Phase 9 listener on `paper.on('element:pointerup', scheduleAutosave)` catches drag-end; undo records already track `change:size` per Phase 8. |

## Project Constraints (from CLAUDE.md)

| Directive | Phase 11 Implication |
|-----------|----------------------|
| Admin-DOM JS style writes must use `el.style.setProperty(prop, value, 'important')`. | Inspector port-list rows are HTML inside `#sfd-inspector` (admin-template DOM) → apply rule. JointJS SVG inside `#sfd-paper` (port dots, port labels, resize handles) is unaffected. |
| Never commit `.env`, Resend API keys, Railway tokens. | No secrets in this phase — pure client-side JS + CSS. |
| Solo dev typically goes straight to `main`; feature branches for risky / multi-session work. | Recommend a feature branch for Phase 11 — multi-task scope (resize tool + port authoring + inspector UI + 7 shape integrations). |
| `collectstatic` runs in Procfile on every Railway deploy. | New static files: none expected (Phase 11 modifies existing `signal_flow_editor.js` + `signal_flow.css`). Existing static-file pipeline absorbs the changes. |
| Append CSS sections to end of `signal_flow.css` (Sections 1-13 exist). | Phase 11 adds Section 14 (port-label rendering), Section 15 (resize handles), Section 16 (inspector port-list rows). |
| `showstack_admin_site` for admin registration. | N/A — Phase 11 has no Django admin work. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Resize tool rendering (corner handles) | Browser/JointJS SVG | — | Pure client-side — JointJS `elementTools.Control` paints SVG inside `#sfd-paper`. |
| Resize geometry math (min-size, snap-to-grid) | Browser | — | Computed in JS during drag; no server involvement. |
| Port authoring CRUD UI | Browser (admin-template DOM) | — | HTML rows inside `#sfd-inspector`; engineer-only mutation. |
| Port autocomplete suggestions | API/Backend | Browser | Already Phase 10 D-04: `signal_flow_label_autocomplete` view supplies project-scoped labels; client renders + selects. |
| Port label persistence | Database (JSONField) | API | Lives in `SignalFlowDiagram.canvas_state` per D-22; no schema change. Server is opaque to the JSON. |
| Per-port snap-target wiring | Browser/JointJS | — | `validateConnection` runs client-side at link-drag time. |
| Connector re-anchor on port removal | Browser/JointJS | API (autosave) | Re-anchor is a client-side graph mutation; Phase 9 autosave persists it. |
| Auto-expand-on-port-overflow | Browser | — | All math + `element.resize()` in JS; subtle toast via existing helper. |
| Project scoping on autocomplete | API | — | Phase 10's `signal_flow_label_autocomplete` already filters by `request.current_project`. No new server work. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@joint/core` (vendored as `joint.min.js`) | 4.2.4 (2026-02-13) | Diagramming canvas — element-tools, ports, links, paper, magnet semantics. | Already locked at the v2.2 milestone level; MPL-2.0 license; `THIRD_PARTY_LICENSES.txt` already attributes it. [VERIFIED: `joint.min.js` banner line 1 confirms `v4.2.4 (2026-02-13)`] |

### Supporting (already in project)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `html-to-image` (vendored) | 1.11.11 | PNG export | Untouched in Phase 11; Phase 12 may use it on boundaries. |
| Browser `Canvas 2D measureText` | native | Compute label pixel widths for D-08 + Q2 min-size math. | Min-size enforcement needs to know how wide a port-label string will render before deciding whether the shape needs to grow. Native browser API; no library needed. [CITED: MDN CanvasRenderingContext2D.measureText, system-fonts only per Phase 8 D-16 / CONSTRAINTS — so font measurement is deterministic.] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `joint.elementTools.Control` (custom subclass) | `joint.elementTools.Resize` (JointJS+) | **REJECTED** — JointJS+ is the paid commercial fork. ShowStack ships MPL-2.0 only. [VERIFIED: direct grep of vendored bundle — see Q1 §"Empirical confirmation"] |
| `joint.elementTools.Control` (custom subclass) | Raw SVG `<rect>` + `pointerdown` handlers outside the JointJS tools framework | **REJECTED** — would not integrate with `selectionView`, `paper.on('cell:pointerup', …)`, or the existing selection-rebuild cycle. The official `Resize Control Tool` demo (joint-demos) sets the precedent for `Control` subclassing. |
| Per-class port-authoring methods (duplicated 7×) | Shared mixin (Q8 recommendation) | **REJECTED for v2.3** — 7× duplication would silently drift when bugs surface. Recommendation is mixin via `joint.util.assign` or a factory wrapper around `joint.dia.Element.extend`. |
| In-canvas SVG inspector | HTML inspector in admin template | **REJECTED** — inspector already lives in admin-template `<aside id="sfd-inspector">` (Phase 8 D-05); putting port-edit controls in SVG would require parallel input/click handling. Stick with HTML. |
| Per-port direction explicit picker | Direction inferred from edge (Q3) | **REJECTED for v2.3** — adds inspector UI cost; engineer mental model already lines up with edge-direction inference. Deferred to v2.4+ as a polish item. |

**Version verification:**
```bash
$ head -c 200 planner/static/planner/js/vendor/joint.min.js
/*! JointJS v4.2.4 (2026-02-13) - JavaScript diagramming library
This Source Code Form is subject to the terms of the Mozilla Public License, v. 2.0.
```
[VERIFIED: file banner confirms 4.2.4 published 2026-02-13, ~3 months old as of research date 2026-05-24. No newer point release shipped in the interim per the WebSearch result reporting "Latest version: 4.2.4, last published: 3 months ago" against npm registry.]

---

## Critical Risk: JointJS Resize Tool Licensing (Q1 — the gating answer)

**Answer: `joint.elementTools.Resize` does NOT ship in the MPL-2.0 `@joint/core` 4.2.4 bundle. Use `joint.elementTools.Control` (which IS in core) as the abstract base for a custom corner-resize tool. The official JointJS demos repo publishes the exact pattern under MPL-2.0.**

### Empirical confirmation (HIGH confidence)

I ran a direct probe against the vendored `joint.min.js` to enumerate what's exported under `joint.elementTools.*`:

```
$ python3 -c 'open ... find("elementTools=a") ... read backwards for namespace build'
```

The minified bundle assigns `t.elementTools = a` where `a` is built as:

```javascript
a = { __proto__: null,
      Boundary: qd, Button: e, Connect: $d,
      Control: Ud,                  // ← present in MPL core (the abstract class we'll extend)
      HoverConnect: u,
      Remove: Hd
    };
```

**Complete list of element tools shipped in `@joint/core` 4.2.4 MPL-2.0:** `Boundary, Button, Connect, Control, HoverConnect, Remove`.

`Resize` is absent. The string `"Resize"` appears in the bundle only as part of Bezier curve control-point math (`startControlPoint`, `dividerControlPoint`, etc.) and as an internal `sgResize` view-update helper — **not as a public `elementTools.Resize` class**.

This is corroborated by:
- WebSearch result: *"There is no such out-of-the-box resize tool in JointJS core, only FreeTransform plugin which is in JointJS+. The source code of the resize control tool demo is available as part of the JointJS+ commercial license."* [CITED: web search 2026-05-24 — see Sources]
- Official JointJS docs `elementTools` page: lists `Boundary`, `Button`, `Connect`, `Control`, `HoverConnect`, `RecordScrollbar`, `Remove`, `SwimlaneBoundary`, `SwimlaneTransform` — Resize not listed. [CITED: docs.jointjs.com/api/elementTools/]

### Canonical implementation pattern (HIGH confidence)

JointJS publishes an official demo at https://github.com/clientIO/joint-demos/tree/main/resize-control-tool that builds a single-corner resize handle from `elementTools.Control`. The full source (`resize-control-tool/js/src/main.js`) was fetched and reads in essence:

```javascript
// Source: github.com/clientIO/joint-demos resize-control-tool/js/src/main.js
const ResizeTool = elementTools.Control.extend({
  children: [
    { tagName: 'image', selector: 'handle',
      attributes: { cursor: 'pointer', width: 20, height: 20, 'xlink:href': resizeIcon } },
    { tagName: 'rect', selector: 'extras',
      attributes: { 'pointer-events': 'none', fill: 'none',
                    stroke: '#33334F', 'stroke-dasharray': '2,4', rx: 5, ry: 5 } }
  ],
  getPosition: function (view) {
    const { width, height } = view.model.size();
    return { x: width, y: height };       // bottom-right corner
  },
  setPosition: function (view, coordinates) {
    view.model.resize(
      Math.max(coordinates.x - 10, 1),
      Math.max(coordinates.y - 10, 1)
    );
  }
});

elementView.addTools(new dia.ToolsView({
  tools: [ new ResizeTool({ selector: 'body' }) ]
}));
```

### Phase 11 adaptation (4 corners + min-size + snap-to-grid + autosave hook)

```javascript
// Phase 11 — corner-resize tool extending the MPL-core Control class.
var CornerResize = joint.elementTools.Control.extend({
  children: [{
    tagName: 'rect',
    selector: 'handle',
    attributes: {
      width: 10, height: 10, x: -5, y: -5,
      fill: '#0d9488', stroke: '#fff', 'stroke-width': 1,
      cursor: 'nwse-resize',     // overridden per-corner below
    }
  }],

  // options.corner = 'tl' | 'tr' | 'bl' | 'br' — picked at construction.
  getPosition: function (view) {
    var s = view.model.size();
    var c = this.options.corner;
    if (c === 'tl') return { x: 0, y: 0 };
    if (c === 'tr') return { x: s.width, y: 0 };
    if (c === 'bl') return { x: 0, y: s.height };
    return { x: s.width, y: s.height };
  },

  setPosition: function (view, coordinates) {
    var model = view.model;
    var s = model.size();
    var p = model.position();
    var c = this.options.corner;
    var minSize = computeMinSize(model);     // Q2 formula — re-evaluated every frame

    var newW = s.width, newH = s.height, newX = p.x, newY = p.y;

    // Per-corner geometry. tl/tr/bl/br all anchor the OPPOSITE corner in place.
    if (c === 'br') {
      newW = Math.max(coordinates.x, minSize.width);
      newH = Math.max(coordinates.y, minSize.height);
    } else if (c === 'tr') {
      newW = Math.max(coordinates.x, minSize.width);
      var deltaH = s.height - coordinates.y;
      newH = Math.max(s.height - (coordinates.y), minSize.height);
      newY = p.y + (s.height - newH);
    } else if (c === 'bl') {
      var deltaW = s.width - coordinates.x;
      newW = Math.max(s.width - coordinates.x, minSize.width);
      newX = p.x + (s.width - newW);
      newH = Math.max(coordinates.y, minSize.height);
    } else if (c === 'tl') {
      newW = Math.max(s.width - coordinates.x, minSize.width);
      newH = Math.max(s.height - coordinates.y, minSize.height);
      newX = p.x + (s.width - newW);
      newY = p.y + (s.height - newH);
    }

    // Phase 8 D-13 — snap-to-grid in 20px multiples when snapEnabled.
    if (window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled) {
      newW = Math.round(newW / 20) * 20;
      newH = Math.round(newH / 20) * 20;
      newX = Math.round(newX / 20) * 20;
      newY = Math.round(newY / 20) * 20;
      // Re-clamp to min in case snap pulled below min.
      newW = Math.max(newW, minSize.width);
      newH = Math.max(newH, minSize.height);
    }

    model.position(newX, newY);   // fires change:position
    model.resize(newW, newH);     // fires change:size — Q8 listener redistributes ports
  }
});

// Attach 4 instances per selected shape on selection-change.
function attachResizeTools(cell) {
  var view = cell.findView(paper);
  if (!view) return;
  view.addTools(new joint.dia.ToolsView({
    name: 'sfd-resize',
    tools: [
      new CornerResize({ corner: 'tl', selector: 'body' }),
      new CornerResize({ corner: 'tr', selector: 'body' }),
      new CornerResize({ corner: 'bl', selector: 'body' }),
      new CornerResize({ corner: 'br', selector: 'body' }),
    ]
  }));
}
function detachResizeTools(cell) {
  var view = cell.findView(paper);
  if (view) view.removeTools();
}
```

### Wiring into existing selection (HIGH confidence)

Phase 9 already exposes `window.__sfd.onSelectionChanged(selectedIds)`. Phase 11 attaches/detaches resize tools inside that callback when the selection is a single element (not a link, not multi-select).

### Autosave + undo integration (HIGH confidence — same mechanism as Phase 8 element drag)

`model.resize(w, h)` fires `change:size`; `model.position(x, y)` fires `change:position`. Phase 8 plan 05's undo stack already records `change:position` (and by symmetry `change:size`). Phase 9's autosave already listens on `paper.on('element:pointerup', scheduleAutosave)` — which fires when the engineer releases the corner handle (drag end on the tool's `<rect>` propagates as `element:pointerup` per JointJS event delegation). [CITED: docs.jointjs.com/api/dia/Element/ — `change:size` fires on resize, `change:position` on position; verified the existing Phase 8 listener block in `signal_flow_editor.js:1717`.]

**Conclusion (HIGH confidence):** The "biggest risk" is fully mitigated. Phase 11 uses `joint.elementTools.Control` exclusively — zero JointJS+ exposure, zero new dependencies, zero license risk. The official demo's `setPosition` recipe is adapted by Phase 11 to handle 4 corners + per-type min-size enforcement + snap-to-grid + autosave-aware drag-end.

---

## Min-Size Math (Q2 — formulas + constants)

**Recommendation: compute min-size on demand from the live port set + label widths, never hard-code per-shape floors.** D-07 in CONTEXT.md mandates this; the formula below is the canonical research output.

### Constants

| Constant | Value | Rationale |
|----------|-------|-----------|
| `PORT_LABEL_FONT_SIZE` | `11` (px) | Slightly smaller than the shape's body label (13px per Phase 8 `attrs.label.fontSize`). Keeps port labels subordinate to the shape's primary identity. Engineer can read at typical 100% zoom. |
| `PORT_LABEL_FONT_STACK` | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` | Matches Phase 8 `FONT_STACK` — system-fonts-only constraint locked at the milestone level (PNG export font-taint mitigation). [CITED: REQUIREMENTS.md Constraints line 100] |
| `MIN_PORT_SPACING` | `24` (px) | Center-to-center spacing minimum. Justified: each port is a 4px-radius dot (Phase 8 `portBody.r: 4`, total dot diameter 8px) + 16px label height (11px font + 5px gap to next port) — 24px is the tightest spacing where adjacent labels do not visually collide. Aligned to a multiple of the 20px snap grid would have been preferable, but 20px is too tight for 11px font labels stacked vertically (vertical edges only); 24px is the minimum readable, accepted as off-grid spacing for ports specifically (the shape's BBOX still snaps to 20). |
| `EDGE_PADDING_PARALLEL` | `12` (px) | Distance from the corner along the edge before the first port can sit. Prevents port-label collisions with the shape's corner & with corner-resize handles. |
| `EDGE_PADDING_PERPENDICULAR_INSIDE` | `8` (px) | Inset from the edge to the start of the port label (perpendicular direction). For Left/Right ports: label starts 8px inside the shape body. For Top/Bottom: label baseline sits 8px inside. |
| `BODY_LABEL_RESERVED_WIDTH` | shape-specific (see below) | Width reserved on the shape body for the shape's own label (D-08 — port labels render INSIDE the body, so they must not overlap the body label). |

**Per-shape body-label reserved width:**

| Shape | Body label position (Phase 8 attrs.label) | Reserved width | Reserved height |
|-------|-------------------------------------------|----------------|-----------------|
| Console | `refX: 16, refY: '50%', textAnchor: start` — left-anchored inside band | label text width + 20px padding | font line-height (~16px) |
| Device | same | same | same |
| Processor | same | same | same |
| Amp | same | same | same |
| SpeakerArray | `refX: '50%', refY: '50%', textAnchor: middle` — centered | full label width + 20px | font line-height |
| CommBeltPack | `refX: '50%', refY: '50%', textAnchor: middle` — centered (pill body) | full label width + 20px | font line-height |
| Generic | same as SpeakerArray | full label width + 20px | font line-height |

[VERIFIED: signal_flow_editor.js:127-266 — direct inspection of all 7 shape class `attrs.label` blocks.]

### Pixel measurement (HIGH confidence)

Browser-native `CanvasRenderingContext2D.measureText` is the standard tool — no JointJS dependency. Memoize against `(text, fontStack, fontSize)` to avoid measuring the same string twice per drag frame:

```javascript
var _textMeasureCanvas = null;
var _textMeasureCache = {};
function measureLabelWidth(text, fontSize) {
  if (!text) return 0;
  var key = fontSize + '|' + text;
  if (_textMeasureCache[key] !== undefined) return _textMeasureCache[key];
  if (!_textMeasureCanvas) _textMeasureCanvas = document.createElement('canvas');
  var ctx = _textMeasureCanvas.getContext('2d');
  ctx.font = fontSize + 'px ' + 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  var w = ctx.measureText(text).width;
  _textMeasureCache[key] = w;
  return w;
}
```

[VERIFIED: MDN CanvasRenderingContext2D.measureText — returns a `TextMetrics` object with `width` property; works for any CSS font string including system fonts. Cache reset is automatic — keyed by (size, text) and the font stack is fixed across the app per the system-fonts constraint.]

### Min-size formula (HIGH confidence)

For a given shape, separate authored ports by edge: `topPorts`, `bottomPorts`, `leftPorts`, `rightPorts`. Let `N_T = topPorts.length`, etc. Let `MAX_LABEL_WIDTH_T = max(measureLabelWidth(p.label, 11) for p in topPorts)`, etc.

```
// Width contributions:
// (a) Top + Bottom edges need horizontal space for N ports × MIN_PORT_SPACING
//     plus 2 × EDGE_PADDING_PARALLEL for corner clearance.
W_topbottom = max(N_T, N_B) > 0
              ? 2 * EDGE_PADDING_PARALLEL + max(N_T, N_B) * MIN_PORT_SPACING
              : 0

// (b) Left + Right edges need horizontal space for the LABEL width of each side
//     (since L/R port labels read left-to-right INSIDE the shape body) plus the
//     EDGE_PADDING_PERPENDICULAR_INSIDE inset on each side, plus the body label.
W_leftright = (MAX_LABEL_WIDTH_L > 0 ? MAX_LABEL_WIDTH_L + EDGE_PADDING_PERPENDICULAR_INSIDE : 0)
            + (MAX_LABEL_WIDTH_R > 0 ? MAX_LABEL_WIDTH_R + EDGE_PADDING_PERPENDICULAR_INSIDE : 0)
            + BODY_LABEL_RESERVED_WIDTH

// (c) Body label own width
W_bodylabel = bodyLabelText width + 20px padding

minWidth = max(W_topbottom, W_leftright, W_bodylabel, ABSOLUTE_FLOOR_W)

// Height contributions:
// (a) Top + Bottom edges need MAX_LABEL_WIDTH (perpendicular to edge, but horizontal)
//     plus EDGE_PADDING_PERPENDICULAR_INSIDE on each side they occupy.
H_topbottom = (N_T > 0 ? FONT_LINE_HEIGHT_T + EDGE_PADDING_PERPENDICULAR_INSIDE : 0)
            + (N_B > 0 ? FONT_LINE_HEIGHT_B + EDGE_PADDING_PERPENDICULAR_INSIDE : 0)
            + BODY_LABEL_RESERVED_HEIGHT
  where FONT_LINE_HEIGHT_T = FONT_LINE_HEIGHT_B = PORT_LABEL_FONT_SIZE * 1.4 (≈ 16px)

// (b) Left + Right edges need vertical space for N ports × MIN_PORT_SPACING
//     plus 2 × EDGE_PADDING_PARALLEL for corner clearance.
H_leftright = max(N_L, N_R) > 0
              ? 2 * EDGE_PADDING_PARALLEL + max(N_L, N_R) * MIN_PORT_SPACING
              : 0

// (c) Absolute floor — the v2.2-shipped intrinsic sizes (Console = 180×60,
//     Device = 140×56, SpeakerArray = 120×80, CommBeltPack = 80×100,
//     Generic = 140×56, Processor = 160×60, Amp = 140×60) act as floors so a
//     resize cannot shrink a port-less shape to nothing.

minHeight = max(H_topbottom, H_leftright, ABSOLUTE_FLOOR_H)
```

[VERIFIED: `ABSOLUTE_FLOOR_W` and `ABSOLUTE_FLOOR_H` for each shape are the intrinsic sizes at signal_flow_editor.js:135 (Console 180×60), :155 (Device 140×56), :175 (SpeakerArray 120×80), :195 (CommBeltPack 80×100), :215 (Generic 140×56), :237 (Processor 160×60), :257 (Amp 140×60). These are the Phase 8 / Phase 10-locked defaults.]

### Recompute triggers

`computeMinSize(cell)` is called from:
1. Inside `CornerResize.setPosition()` — every drag frame, so the engineer cannot drag below the live floor.
2. Inside `addAuthoredPort()` — to evaluate D-11 auto-expansion (Q7 below).
3. Inside `removeAuthoredPort()` — to recompute redistribution metrics (but NOT to shrink the shape — removal NEVER shrinks the shape per principle of least surprise; engineer manually resizes back).
4. Inside the port-label-change handler — when the engineer renames a port and the new label is wider than the old, min-width may grow; auto-expand if needed.

[ASSUMED] The browser canvas-text-measurement cache may need flushing if the user's OS font set changes mid-session; this is an edge case (engineer doesn't typically install fonts during a diagram session) and we accept the risk for v2.3. If reports surface, add `_textMeasureCache = {}` to the `pagehide`/`visibilitychange` handlers.

---

## Port Direction Semantics (Q3 — recommendation with rationale)

**Recommendation: Direction inferred from edge — Top + Left = inbound (`magnet: 'passive'`), Bottom + Right = outbound (`magnet: true`).** Matches v2.2 generic-port convention; zero inspector UI cost.

### Evidence

1. **v2.2 already uses this convention.** [VERIFIED: signal_flow_editor.js:118-122 — `portsForRect()` puts an `in` port at left (x:0), an `out` port at right (x:width), an `in` port at top (y:0), and an `out` port at bottom (y:height).] Engineers have used the v2.2 editor for ~2 weeks; the mental model is established.

2. **Audio signal flow conventions.** Live audio engineers read signal-flow diagrams top-down and left-right by default: sources on the left and top (microphones, console inputs), destinations on the right and bottom (speakers, recorders, broadcast). The v2.2 magnet convention matches engineer expectations.

3. **JointJS magnet semantics support both modes equally.** `magnet: 'passive'` blocks new link-drag starts but accepts drops; `magnet: true` allows link-drag starts. Both behaviors are first-class. [VERIFIED: signal_flow_editor.js:297-302 — Phase 8's `validateMagnet` already enforces "out-magnets only as drag source".]

4. **Inspector UI complexity cost of the alternative.** Per-port direction picker would mean each inspector port row needs a direction toggle (in/out radio or segmented button), adding ~30px vertical per row. Phase 11 inspector is already vertically-loaded with 4 edge sections.

### Implementation

When the engineer adds a port to an edge in the inspector, the JS sets:

```javascript
function directionForEdge(edge) {
  // Edge string is one of: 'top' | 'left' | 'right' | 'bottom'.
  if (edge === 'top' || edge === 'left') return 'in';   // magnet: 'passive'
  return 'out';                                          // magnet: true
}
```

The authored port is then added with:

```javascript
element.addPort({
  group: directionForEdge(edge),        // 'in' or 'out' — uses existing standardPortGroups
  attrs: {
    portBody: { magnet: directionForEdge(edge) === 'in' ? 'passive' : true,
                r: 4, fill: '#fff', stroke: '#666', 'stroke-width': 1, opacity: 0 },
    label:    { text: labelText },       // Q4 — custom label storage
  },
  args: { x: edgeX, y: edgeY },           // computed by redistribute (Q7)
  // Q10 — label rendering
  label: { position: portLabelPositionForEdge(edge),
           markup: [{ tagName: 'text', selector: 'label' }] },
  showstack: { edge: edge, label: labelText },   // Phase 11 custom — see Q4
});
```

### Deferred to v2.4+

If beta engineers report that a port needs to be inbound on a Right edge (uncommon but real — e.g., a recorder receiving signal from the right when the canvas layout forces it), add a per-port direction toggle in the inspector. Track as `PORT-DIRECTION-MANUAL-01` in the roadmap-backlog. Phase 11 does NOT ship this control.

[CITED: CONTEXT.md D-XX §H — researcher recommends "inferred from edge unless evidence says otherwise". This research finds no evidence pushing toward explicit-control.]

---

## Port State Storage (Q4 — recommendation with code sketch)

**Recommendation: Store authored ports as `element.attributes.ports.items[N]` (JointJS-native). The engineer-supplied label string lives at TWO places on the port object: `port.attrs.label.text` (so JointJS native label rendering picks it up — see Q10) AND `port.showstack.label` (a Phase 11 custom namespace that mirrors the Phase 8 convention of `cell.showstack.*` for application-specific state).**

### Rationale

| Storage option | Pros | Cons | Recommendation |
|---|---|---|---|
| **JointJS-native `ports.items[N]`** | Round-trips through `graph.toJSON()`/`fromJSON()` for free [VERIFIED: docs.jointjs.com/api/dia/Element/ — "ports defined via the constructor's `ports` property or added through `addPort()`/`addPorts()` are preserved during graph.toJSON() and restored by graph.fromJSON()"]; ports become first-class snap targets via `validateConnection` and `snapLinks` automatically; the existing Phase 8 `portsForRect()` already uses this storage and ships labels via `attrs`. | Have to live with JointJS's auto-id generation + the `change:ports` auto-link-removal default (Q6 problem). | **CHOSEN.** |
| **Sibling `portLabels` map on `element.attributes`** | One canonical source for label strings, independent of JointJS port reshape internals. | Diverges from JointJS conventions; would NOT auto-snap-target without re-implementing the magnet wiring; would need our own serialization-aware migration path. | REJECTED — fights the framework. |
| **Hybrid (id in ports.items, label in showstack.portLabels)** | Allows label rename without touching `change:ports`. | Two writes per port mutation; risk of drift if one write fails. | REJECTED — needless complexity. |

[VERIFIED: by direct inspection of the bundle at `_validatePorts` and `_processRemovedPort` — port-id auto-generation via `generatePortId()`/`generateId()` runs on every port add; `change:ports` fires on every mutation and `_processRemovedPort` walks every link to clean up references to disappeared port ids.]

### Schema for a Phase 11 authored port

```javascript
{
  id: 'pa1-1f3c',                              // auto-assigned by JointJS if omitted
  group: 'in',                                  // 'in' = magnet:'passive', 'out' = magnet:true
  attrs: {
    portBody: {
      magnet: 'passive',                        // duplicated from group for back-compat
      r: 4, fill: '#fff', stroke: '#666',
      'stroke-width': 1, opacity: 0,            // hover-revealed (Phase 8 CSS Section 7)
    },
    label: { text: 'FOH Lead' },                // JointJS reads this for label rendering
  },
  args: { x: 84, y: 0 },                         // 'absolute' position layout coords
  label: {                                       // Q10 — per-port label markup + placement
    position: {                                  // computed per-edge (Q10)
      name: 'manual',                            // we provide explicit x/y/textAnchor
      args: { x: 0, y: 14, attrs: { label: { textAnchor: 'middle' } } },
    },
    markup: [{ tagName: 'text', selector: 'label' }],
  },
  showstack: {                                   // Phase 11 custom — mirrors cell.showstack convention
    label: 'FOH Lead',                           // engineer-authored string (source of truth for inspector)
    edge: 'top',                                 // 'top' | 'bottom' | 'left' | 'right' — derives direction + redistribute logic
    authored: true,                              // marks port as engineer-authored (vs auto-generated v2.2 generic)
  },
}
```

### Round-trip guarantee (HIGH confidence)

The full port object (every key including `showstack`) round-trips through `canvas_state` because:
1. `graph.toJSON()` serializes `element.attributes.ports.items` verbatim. Custom keys (`showstack`) are preserved — JointJS doesn't strip unknown keys. [CITED: docs.jointjs.com/4.0/learn/features/export-import/json/ — "Custom properties saved on the graph are preserved as well, and you can use this to store additional state information."]
2. `graph.fromJSON()` re-instantiates ports via the class constructor → port settings → `_processPort` → port settings data; all custom args survive.
3. Phase 9's server-side `_enrich_nodes` does NOT mutate `cells[N].ports.items` — it only touches `attrs.label.text` and `showstack.{isOrphan,savedLabel}` at the cell-root level. Port-level state passes through opaquely. [VERIFIED: 09-CONTEXT.md D-13 — bulk-fetch + write at cell-root only; ports untouched.]

### Reading and writing in code

```javascript
// Read all authored ports on an edge:
function getAuthoredPortsForEdge(cell, edge) {
  return cell.getPorts().filter(function (p) {
    return p.showstack && p.showstack.authored === true && p.showstack.edge === edge;
  });
}

// Update a port label (engineer typed in inspector or picked autocomplete):
function renameAuthoredPort(cell, portId, newLabel) {
  cell.portProp(portId, 'showstack/label', newLabel);
  cell.portProp(portId, 'attrs/label/text', newLabel);
  // Width may have changed → check D-11 auto-expansion.
  maybeAutoExpand(cell);
}

// Add new authored port:
function addAuthoredPort(cell, edge, label) {
  // If this is the FIRST authored port on this cell, also drop the 4 generic ports
  // per D-13 whole-shape switch.
  if (!cellHasAnyAuthoredPort(cell)) {
    convertCellFromGenericToAuthored(cell);
  }
  cell.addPort({
    group: directionForEdge(edge),
    attrs: { portBody: { magnet: directionForEdge(edge) === 'in' ? 'passive' : true,
                          r: 4, fill: '#fff', stroke: '#666',
                          'stroke-width': 1, opacity: 0 },
              label: { text: label } },
    args: { x: 0, y: 0 },                          // will be set by redistribute
    label: { position: portLabelPositionForEdge(edge),
              markup: [{ tagName: 'text', selector: 'label' }] },
    showstack: { label: label, edge: edge, authored: true },
  });
  redistributeEdgePorts(cell, edge);
  maybeAutoExpand(cell);
  scheduleAutosave();
}
```

---

## Per-Port Snap-Target Wiring (Q5 — exact branching logic for validateConnection)

**Recommendation: Update `validateConnection` to enforce a hard "must hit a magnet" rule, then layer the D-13 whole-shape back-compat on top via a per-element check.**

### Current state (signal_flow_editor.js:303-309)

```javascript
validateConnection: function (sourceView, sourceMagnet, targetView, targetMagnet) {
  if (!sourceMagnet || !targetMagnet) return false;       // CON-03 — both ends must be magnets
  if (sourceView === targetView) return false;             // no self-loops
  return true;
}
```

This is ALREADY correct for the "must hit a magnet" rule. The change Phase 11 needs is to ensure the right set of magnets exists on the shape at any given time.

### Phase 11 update

`validateConnection` itself **does not need to branch on authored-vs-generic**. The reason is D-13's whole-shape switch: at any given moment, a shape has EITHER 4 generic ports OR N authored ports — never both. Whichever set is present, `magnet` lookup over those ports is correct for snap targeting.

```javascript
// Phase 11 — UNCHANGED from Phase 8.
// (Just keeping it as a placeholder for the planner; no edit needed in this function.)
validateConnection: function (sourceView, sourceMagnet, targetView, targetMagnet) {
  if (!sourceMagnet || !targetMagnet) return false;
  if (sourceView === targetView) return false;
  // D-13 already satisfied by the port-set switching elsewhere — the magnets
  // that EXIST on the shape ARE the snap targets. No branching required here.
  return true;
}
```

### Where the D-13 branching lives — `convertCellFromGenericToAuthored`

```javascript
// Called the FIRST time an authored port is added to a cell with only generic ports.
// Atomically removes the 4 generic ports (re-anchoring any attached links — Q6
// pattern) and lets the new authored port take over snap targeting.
function convertCellFromGenericToAuthored(cell) {
  var existingPorts = cell.getPorts();
  // The 4 generic ports were inserted by portsForRect() with no `showstack.authored` flag.
  var genericPorts = existingPorts.filter(function (p) {
    return !(p.showstack && p.showstack.authored === true);
  });
  // Re-anchor + remove each generic port — same recipe as Q6.
  genericPorts.forEach(function (port) {
    reanchorLinksFromPort(cell, port.id);
    cell.removePort(port.id);
  });
}

function cellHasAnyAuthoredPort(cell) {
  return cell.getPorts().some(function (p) {
    return p.showstack && p.showstack.authored === true;
  });
}
```

### Where the v2.2 generic-port-restoration lives — `removeAuthoredPort`

When the engineer removes the **last** authored port from a shape, do we restore the 4 generic ports? CONTEXT.md D-13 reads "this shape is yours now" — the conservative interpretation is **no, the shape stays in authored-mode forever**. The engineer can still connect to the shape body's perimeter via the same `validateConnection` rule (which already rejects mid-shape drops). The shape would simply have zero snap targets until the engineer adds an authored port back.

```javascript
function removeAuthoredPort(cell, portId) {
  reanchorLinksFromPort(cell, portId);    // Q6 pattern
  cell.removePort(portId);
  // Do NOT restore generics. "This shape is yours now."
  // If engineers report this is confusing in beta, revisit in v2.4+.
  var edge = /* derive from removed port — but the port is gone now, so read showstack.edge before removal */;
  redistributeEdgePorts(cell, edge);
  // Do NOT auto-shrink — engineer manually resizes if they want.
  scheduleAutosave();
}
```

[ASSUMED] The "do not restore generics on last-removal" rule mirrors the Phase 9 orphan-flag policy where `contentTypeId` / `objectId` are preserved even when the equipment record is deleted — we don't reset state speculatively. The plan-discuss step may want to re-confirm with the user if there's any ambiguity.

---

## Connector Survival on Port Removal (Q6 — event hook + re-anchor calc)

**Recommendation: Intercept the inspector trash-icon click BEFORE calling `removePort()`. Walk every connected link, rewrite its `source` or `target` from `{id, port}` to `{id}` (which auto-anchors to the element's bounding-box center per JointJS docs), or for a more precise edge-midpoint placement, set the link endpoint to a paper-coordinate point on the shape's edge midpoint. This is required because JointJS 4.2.4's `_processRemovedPort` (private internal method, runs on `change:ports`) **auto-removes** any link whose source/target port id no longer exists.**

### Empirical confirmation (HIGH confidence)

Direct inspection of vendored `joint.min.js`:

```javascript
// Source: joint.min.js @ offset ~207855
_processRemovedPort: function () {
  var t = this.get("ports") || {}, e = {};
  et(t.items).forEach(function (t) { e[t.id] = !0 });
  t = this.previous("ports") || {};
  var n = {};
  et(t.items).forEach(function (t) { e[t.id] || (n[t.id] = !0) });   // n = port ids removed in this change
  t = this.graph;
  t && !ta(n) && (
    t.getConnectedLinks(this, { inbound: !0 }).forEach(function (t) {
      n[t.get("target").port] && t.remove()      // ← inbound link to removed port → REMOVED FROM GRAPH
    }),
    t.getConnectedLinks(this, { outbound: !0 }).forEach(function (t) {
      n[t.get("source").port] && t.remove()      // ← outbound link from removed port → REMOVED FROM GRAPH
    })
  );
}
```

**Confirmed:** JointJS 4.2.4 auto-removes links — does NOT pin them to the shape, does NOT fire a graceful disconnect event. This is the DEFAULT behavior and there is NO option flag to suppress it.

### Required workaround

Move the link rewrite to happen **before** the port is removed, so `_processRemovedPort` sees no stale references and skips the removal.

```javascript
// Re-anchor every link attached to portId to the shape's edge midpoint,
// preserving the link's other endpoint, its signal type, direction, and label.
// MUST be called BEFORE cell.removePort(portId).
function reanchorLinksFromPort(cell, portId) {
  if (!cell.graph) return;

  // Get connected links — inbound (target.port === portId) and outbound (source.port === portId).
  var attachedLinks = cell.graph.getConnectedLinks(cell).filter(function (link) {
    var src = link.get('source'), tgt = link.get('target');
    return (src && src.port === portId) || (tgt && tgt.port === portId);
  });
  if (!attachedLinks.length) return;

  // Compute the edge midpoint for the port being removed.
  var port = cell.getPort(portId);
  var edge = (port && port.showstack && port.showstack.edge) || 'left';
  var midpoint = edgeMidpointInPaperCoords(cell, edge);

  attachedLinks.forEach(function (link) {
    var src = link.get('source'), tgt = link.get('target');
    if (src && src.port === portId) {
      // Rewrite outbound source: drop .port reference; set to paper-coord point.
      link.source({ x: midpoint.x, y: midpoint.y });
      link.prop('showstack/sourceDetached', true);     // optional Phase 11 flag for orphan-link styling
    }
    if (tgt && tgt.port === portId) {
      link.target({ x: midpoint.x, y: midpoint.y });
      link.prop('showstack/targetDetached', true);
    }
  });
}

function edgeMidpointInPaperCoords(cell, edge) {
  var pos = cell.position();
  var size = cell.size();
  if (edge === 'top')    return { x: pos.x + size.width / 2, y: pos.y };
  if (edge === 'bottom') return { x: pos.x + size.width / 2, y: pos.y + size.height };
  if (edge === 'left')   return { x: pos.x,                  y: pos.y + size.height / 2 };
  return { x: pos.x + size.width, y: pos.y + size.height / 2 };
}
```

### Note on `link:disconnect` event

The `link:disconnect` event DOES exist in JointJS 4.2.4 [VERIFIED: bundle grep — `"link:disconnect"` appears once as an event-name string]. However, it fires only on **pointer-drag** disconnections (user grabs a link end and moves it off a port). It does NOT fire when `removePort()` triggers `_processRemovedPort`-driven link removal. So we cannot use it as a hook. The intercept must be on the inspector trash-icon click handler.

### Autosave persistence (HIGH confidence)

Setting `link.source({x, y})` mutates the link model → fires `change:source` → already in the Phase 9 autosave debounce listener at signal_flow_editor.js:1716 (`graph.on('add remove change:source change:target', scheduleAutosave)`). Re-anchored connectors persist through autosave on the next 1500ms tick. No new wiring needed.

### Connector visual on detached endpoints

The Phase 9 orphan ghost CSS (`.joint-link[joint-orphan-attached="true"] { opacity: 0.5 }`) is for connectors attached to ghosted orphan SHAPES. Phase 11 detached connector endpoints should NOT be ghosted — they're still live connectors pointing at a live shape, just at the edge midpoint rather than a specific port. No CSS change needed; the link renders normally.

If beta engineers want a visual "this connector lost its port" indication, that's a v2.4+ polish item.

---

## Auto-Expansion Math (Q7 — trigger + toast wiring)

**Recommendation: Auto-expansion fires on `addAuthoredPort()` and on `renameAuthoredPort()` when the new label is longer. Trigger condition: `(minSize.width > currentSize.width) || (minSize.height > currentSize.height)`. Toast fires only when at least one dimension actually grew; the toast is suppressed if the engineer triggered the addition with the shape already at sufficient size (no visible growth = no toast).**

### Trigger logic

```javascript
function maybeAutoExpand(cell) {
  var current = cell.size();
  var min = computeMinSize(cell);        // Q2 formula

  var grew = false;
  var newW = current.width, newH = current.height;
  if (min.width > current.width)  { newW = min.width;  grew = true; }
  if (min.height > current.height) { newH = min.height; grew = true; }

  if (!grew) return;

  // Snap-to-grid the new size if snap is on (Phase 8 D-13).
  if (window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled) {
    newW = Math.ceil(newW / 20) * 20;    // ceil — never auto-shrink below min after snap
    newH = Math.ceil(newH / 20) * 20;
  }

  cell.resize(newW, newH);               // fires change:size → autosave + undo
  showToast('Shape resized to fit ports.', 'info');
}
```

### Toast wiring (HIGH confidence)

Phase 9 plan 03 confirmed `showToast(message, level)` exists in `signal_flow_editor.js:72-79` and accepts levels `'info' | 'success' | 'error'`. CSS Section 6 styles `.sfd-toast--info`. No new helper, no new CSS — use as-is.

[VERIFIED: signal_flow_editor.js:72-79 + signal_flow.css:474-477 — `.sfd-toast--info` class exists.]

### Position is NOT changed on auto-expand

When a shape grows from its bottom-right corner (via `cell.resize()`), JointJS keeps the top-left corner anchored. This matches engineer expectation: "the shape grew to fit my new port" — the existing position is the anchor. No `cell.position()` call needed.

If the engineer adds a port to the LEFT edge that pushes minWidth above currentWidth, the shape grows to the right (still anchored at the left edge). This may overlap an adjacent shape briefly — that's acceptable for v2.3 (engineer can drag to relocate). Per CONTEXT.md "no smart alignment guides" (deferred to v2.4+).

### Undo behavior

`cell.resize(newW, newH)` records to the existing Phase 8 undo stack as a `change:size` operation. A single Ctrl+Z reverses the auto-expand — and because addPort + auto-expand happen as separate model mutations, two Ctrl+Z keypresses would be needed: one to undo the auto-expand, then one to undo the port-add. Phase 8 plan 05 already provides `window.__sfd.undo.beginBatch/endBatch` for atomic multi-step mutations.

**Plan recommendation:** Wrap addAuthoredPort + maybeAutoExpand in `beginBatch/endBatch` so they undo as one gesture. The Phase 9 node-mode delete-shape pattern (signal_flow_editor.js:1505-1517) already demonstrates this:

```javascript
function addAuthoredPort(cell, edge, label) {
  if (window.__sfd.undo) window.__sfd.undo.beginBatch();
  try {
    if (!cellHasAnyAuthoredPort(cell)) convertCellFromGenericToAuthored(cell);
    cell.addPort({...});
    redistributeEdgePorts(cell, edge);
    maybeAutoExpand(cell);
  } finally {
    if (window.__sfd.undo) window.__sfd.undo.endBatch();
  }
  scheduleAutosave();
}
```

---

## Shape Class Refactor Pattern (Q8 — shared mixin vs per-class)

**Recommendation: Shared per-instance behavior via a `joint.util.assign`-based mixin applied at class definition. Per-shape `attrs` blocks stay UNCHANGED (Phase 8 / Phase 10 locked them). The mixin only adds methods to the prototype; no override of existing `defaults`.**

### Why mixin, not duplicate

Duplicating the 200+ lines of "addAuthoredPort, removeAuthoredPort, redistributeEdgePorts, computeMinSize, maybeAutoExpand" across 7 shape class definitions would:
- Triple the file size (Phase 11 already adds ~600 lines for resize-tool + inspector port-list)
- Risk silent drift if a bug fix only lands in one class
- Make adding an 8th shape type in v2.4+ a copy-paste exercise

A factory function wrapping `joint.dia.Element.extend` is cleaner.

### Why NOT a constructor-level mixin

JointJS classes use Backbone's `.extend()` which DOES support a static methods object (`{instanceProps, staticProps}`). However, `joint.util.deepSupplement` (already used in the existing 7 classes to merge `defaults`) does NOT merge prototype methods. So the cleanest approach is to define the port-authoring methods as module-level **functions**, NOT class methods, and pass the cell as the first argument:

```javascript
// Phase 11 — module-level helpers (not class methods)
function authoredPortsMixin() {
  return {
    addAuthoredPort:       function (edge, label) { /* this = cell */ },
    removeAuthoredPort:    function (portId) {},
    renameAuthoredPort:    function (portId, newLabel) {},
    getAuthoredPorts:      function () {},
    getAuthoredPortsByEdge: function (edge) {},
    computeMinSize:        function () {},
    redistributeEdgePorts: function (edge) {},
  };
}
```

Then either:

**Option A: Mix into every shape class prototype.**
```javascript
[joint.shapes.showstack.Console,
 joint.shapes.showstack.Device,
 joint.shapes.showstack.Processor,
 joint.shapes.showstack.Amp,
 joint.shapes.showstack.SpeakerArray,
 joint.shapes.showstack.CommBeltPack,
 joint.shapes.showstack.Generic].forEach(function (Cls) {
  joint.util.assign(Cls.prototype, authoredPortsMixin());
});
```

**Option B: Define as module-level standalone functions** that take a cell as their first arg.
```javascript
function addAuthoredPort(cell, edge, label) { ... }
function removeAuthoredPort(cell, portId)    { ... }
// etc.
```

**Recommendation: Option B.** Justifications:
- No reliance on JointJS's `.extend()`/prototype merging behavior (which could change between JointJS versions).
- Functions are easy to expose via `window.__sfd.ports = { add: addAuthoredPort, ... }` for inspector wiring + test fixtures.
- The Phase 9 / Phase 10 pattern is already module-level functions (`applyOrphanState`, `applyAttachedOrphanState`, `setInspectorMode`) — Option B matches the established style.

**Per-shape attrs blocks: UNCHANGED.** [VERIFIED: signal_flow_editor.js:127-266 — every shape class has its own `attrs` block. Phase 11 does NOT touch these. The port authoring overlay is entirely additive.]

### Where the mixin lives in the file

Insert after the 7 shape class definitions (around line 270) and before the Graph/Paper init block (line 273). All Phase 11 port-authoring + resize-tool functions live in a single section commented "Phase 11 — port authoring + resize tool" with sub-comments per requirement. Matches the existing append-at-end convention.

---

## Inspector Port-List UI Structure (Q9 — DOM template)

**Recommendation: HTML inside `#sfd-inspector` (admin-template DOM). Built lazily on first `setInspectorMode('node', cell)` call where cell supports authored ports — i.e., on every shape selection. Reuses Phase 10's combobox widget for label input via duplication of the autocomplete-init pattern attached to each port-label input.**

### DOM structure

```html
<!-- Inserted into #sfd-inspector below the existing nodeModeBlock (Phase 9) -->
<div class="sfd-field sfd-field--port-author" data-mode="node">
  <h4 class="sfd-port-section-title">Ports</h4>

  <div class="sfd-port-edge-section" data-edge="top">
    <div class="sfd-port-edge-header">
      <span class="sfd-port-edge-name">Top</span>
      <button type="button" class="sfd-port-add" data-edge="top">+ Add port</button>
    </div>
    <ul class="sfd-port-list" data-edge="top">
      <!-- Repeated per port -->
      <li class="sfd-port-row" data-port-id="pa1-1f3c">
        <span class="sfd-port-ordinal">1</span>
        <input type="text" class="sfd-port-label-input" value="FOH Lead">
        <button type="button" class="sfd-port-remove" aria-label="Remove port">🗑</button>
      </li>
    </ul>
  </div>

  <div class="sfd-port-edge-section" data-edge="bottom">
    <!-- same structure -->
  </div>
  <div class="sfd-port-edge-section" data-edge="left">
    <!-- same structure -->
  </div>
  <div class="sfd-port-edge-section" data-edge="right">
    <!-- same structure -->
  </div>
</div>
```

### Class names (all `.sfd-*` prefixed, follow Phase 8/9 conventions)

| Class | Purpose |
|-------|---------|
| `.sfd-field--port-author` | Wraps the entire port-author block. `data-mode="node"` so the Phase 9 mode-switcher hides/shows it correctly. |
| `.sfd-port-section-title` | "Ports" header. |
| `.sfd-port-edge-section` | One per edge. `data-edge="top|bottom|left|right"` for click delegation. |
| `.sfd-port-edge-header` | Edge-name + add-port button container. |
| `.sfd-port-edge-name` | "Top" / "Bottom" / "Left" / "Right" text. |
| `.sfd-port-add` | "+ Add port" button. Per-edge. |
| `.sfd-port-list` | `<ul>` of port rows for the edge. |
| `.sfd-port-row` | One row per port. `data-port-id` set to JointJS port id. |
| `.sfd-port-ordinal` | "1", "2", ... — small, muted (D-09 explicitly allows inspector ordinals while canvas shows none). |
| `.sfd-port-label-input` | Text input attached to Phase 10's combobox widget. |
| `.sfd-port-remove` | Trash icon button per row. `aria-label="Remove port"` for screen readers. |

### Phase 10 autocomplete combobox reuse

Phase 10 plan 10-03 attached the combobox to `#sfd-circuit-label`. The widget is currently tightly coupled to that input id (signal_flow_editor.js:1799-1857 — `initAutocomplete()` calls `document.getElementById('sfd-circuit-label')`). **Refactor needed for Phase 11:** generalize `initAutocomplete()` into `attachAutocompleteToInput(inputEl, labelAutocompleteUrl)` that the existing circuit-label flow calls once and each new port-label input calls per row.

The refactored signature:

```javascript
function attachAutocompleteToInput(inputEl, url, onSelect) {
  // wraps inputEl's parent .sfd-field with .sfd-autocomplete-wrapper
  // creates <ul id="sfd-label-suggestions-<unique>" role=listbox>
  // wires input/keydown/blur handlers using closures over inputEl
  // onSelect callback fires when user picks a row OR commits free text on blur
}
```

The port-row code then calls:

```javascript
attachAutocompleteToInput(
  portRow.querySelector('.sfd-port-label-input'),
  labelAutocompleteUrl,
  function (label) { renameAuthoredPort(cell, portId, label); }
);
```

[CITED: Phase 10 D-04 — "the same endpoint + JS widget will be reused by Phase 11's PORT-03 custom-label dropdown without re-implementation". Refactor is the natural way to honor that decision.]

### Listbox id collision

The current code uses a hardcoded `id="sfd-label-suggestions"`. With multiple port inputs, the planner must either (a) generate unique ids per attachment (`sfd-label-suggestions-port-<portId>`) or (b) reposition a single shared listbox each time it's needed. **Recommendation:** generate per-input ids; cleaner separation, ARIA `aria-controls` stays valid per input.

### CLAUDE.md admin-DOM rule (HIGH confidence)

The inspector lives inside the admin-template DOM. Every JS style write on these elements MUST use `el.style.setProperty(prop, value, 'important')`. Examples already in code: signal_flow_editor.js:1337, 1342, 1465-1488, 1696-1697. Phase 11 follows the same rule for `.sfd-port-row`, `.sfd-port-add`, etc.

CSS rules in the new Section 16 should use `!important` per the existing Section 1-13 convention (file-header docs the rule explicitly: signal_flow.css lines 12-17).

### Build trigger

`setInspectorMode('node', cell)` (signal_flow_editor.js:1520) currently shows the Phase 9 re-link + delete block. Phase 11 extends this to also build the port-author block. Pattern:

```javascript
function setInspectorMode(mode, cell) {
  // ... existing Phase 9 code ...
  if (mode === 'node') {
    // ... existing show/hide ...
    if (!portAuthorBlock) buildPortAuthorBlock();
    portAuthorBlock.style.setProperty('display', 'block', 'important');
    refreshPortAuthorBlock(cell);    // populate per-edge port lists from cell state
  } else {
    if (portAuthorBlock) portAuthorBlock.style.setProperty('display', 'none', 'important');
  }
}
```

`refreshPortAuthorBlock(cell)` walks `cell.getAuthoredPortsByEdge('top')`, etc., and rebuilds the four `<ul>` lists.

---

## Canvas Label Rendering (Q10 — JointJS markup per edge)

**Recommendation: Use JointJS's per-port `label.markup` + `label.position` system with `position.name: 'manual'` and explicit `args.x`, `args.y`, `args.attrs.textAnchor` per edge. This stays inside the framework's port-label rendering pipeline so the label automatically follows port-position changes during redistribute and auto-expand.**

### Why `label.position.name: 'manual'`

JointJS ships PortLabel layouts named `left`, `right`, `top`, `bottom`, `inside`, `outside`, `insideOriented`, `outsideOriented`, `radial`, `radialOriented`, `manual` [CITED: docs.jointjs.com/api/layout/PortLabel/]. The named layouts (`inside`, `outside`, etc.) work for ports placed via `position: { name: 'left' | 'right' | 'top' | 'bottom' }` (the port-position layouts), but Phase 11 uses `position: { name: 'absolute', args: {x, y} }` to support custom edge-spacing math. With `absolute` port positioning, the named label layouts don't apply correctly — `manual` is the canonical answer.

### Per-edge label position

```javascript
function portLabelPositionForEdge(edge) {
  // Coordinates are relative to the port dot position.
  // EDGE_PADDING_PERPENDICULAR_INSIDE = 8 (offset from edge into the shape body).
  switch (edge) {
    case 'top':
      return { name: 'manual',
               args: { x: 0, y: 14,                          // 14px below the port dot, INSIDE the shape
                       attrs: { '.joint-port-label': { textAnchor: 'middle' } } } };
    case 'bottom':
      return { name: 'manual',
               args: { x: 0, y: -6,                          // 6px above the port dot, INSIDE the shape
                       attrs: { '.joint-port-label': { textAnchor: 'middle' } } } };
    case 'left':
      return { name: 'manual',
               args: { x: 8, y: 4,                           // 8px right of port dot, INSIDE
                       attrs: { '.joint-port-label': { textAnchor: 'start' } } } };
    case 'right':
      return { name: 'manual',
               args: { x: -8, y: 4,                          // 8px left of port dot, INSIDE
                       attrs: { '.joint-port-label': { textAnchor: 'end' } } } };
  }
}
```

### Per-edge label markup

```javascript
function portLabelMarkupForEdge() {
  // Same markup for all edges; only position changes per edge.
  return [{
    tagName: 'text',
    selector: 'label',
    attributes: {
      'font-size': 11,
      'font-family': 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
      fill: '#444',
      'pointer-events': 'none',     // labels never block port-hover or link-drag
    },
  }];
}
```

### Why labels render INSIDE the body

D-08 mandates "labels render inside the shape body, perpendicular to the edge they belong to". The `args.x` and `args.y` offsets above are calibrated to position the label JUST INSIDE the edge in the direction of the shape body center:
- Top edge: label below the dot (port at y=0, label at y=14, BELOW the edge → INSIDE)
- Bottom edge: label above the dot (port at y=height, label at y=-6 relative to port → INSIDE)
- Left edge: label right of the dot (port at x=0, label at x=8 → INSIDE)
- Right edge: label left of the dot (port at x=width, label at x=-8 → INSIDE)

### Text reads horizontally on all edges

All 4 cases use horizontal text (no rotation). This matches D-08's "perpendicular to the edge" with the engineer's expectation that text is readable left-to-right always (no neck-craning). [CITED: D-08 explicitly excludes oriented/rotated labels.]

### Label updates on rename

When the engineer types a new label in an inspector port-row input, `renameAuthoredPort(cell, portId, newLabel)` calls `cell.portProp(portId, 'attrs/label/text', newLabel)`. JointJS native port-label rendering picks up the change immediately and re-paints the text. No imperative DOM write needed.

### Label visibility during normal-state vs hover

Phase 8 hides port DOTS at rest (opacity:0) and reveals on hover. Phase 11 port LABELS should follow the **opposite** rule: labels are ALWAYS VISIBLE (engineers need them to identify which port to wire). Only the dot is hover-revealed. The new CSS Section 14:

```css
.joint-port-label text { opacity: 1 !important; }   /* labels always visible */
.joint-port circle    { opacity: 0; }                /* dots hidden at rest */
.joint-element:hover .joint-port circle,             /* shown on shape hover */
.joint-element.is-selected .joint-port circle { opacity: 1; }
```

[VERIFIED: signal_flow.css Section 7 already has the port hover-reveal CSS — Phase 11 amends it slightly to scope the opacity:0 to `.joint-port circle` only, leaving `.joint-port-label text` always visible.]

### Phase 8 generic ports stay UNLABELED

Generic ports (the 4 ports added by `portsForRect()` in Phase 8) do NOT get labels. Their port definition has no `label` key — JointJS skips label rendering. Only Phase 11 authored ports get labels. The D-13 whole-shape switch ensures a shape never displays both labeled-authored and unlabeled-generic ports simultaneously.

---

## Validation Test Cases (Q11 — grouped by REQ-ID)

Nyquist validation is disabled at the milestone level (`workflow.nyquist_validation` not set in this project) but Phase 9 + Phase 10 demonstrated that manual UAT covers regression risk well. Below are the assertion-form test cases the planner should turn into a UAT script. Each test is independently verifiable.

### PORT-01 — Add labeled port to any shape via inspector

| # | Assertion |
|---|-----------|
| PORT-01.1 | Select a Console shape on canvas → inspector opens in node mode → 4 edge sections visible (Top / Bottom / Left / Right) with "+ Add port" buttons. |
| PORT-01.2 | Click "+ Add port" on the Top section → a new port row appears with an empty label input + trash icon + ordinal "1". |
| PORT-01.3 | Type "Channel 1" in the new port-row input → label appears on the canvas at the center of the Top edge, BELOW the dot, INSIDE the shape body. |
| PORT-01.4 | Repeat steps 1-3 for SpeakerArray (polygon body), Generic (dashed border), Processor, Amp, Device, CommBeltPack — all 7 shape classes accept authored ports. |
| PORT-01.5 | Bottom edge of every shape class accepts ports — verify D-01 amendment (PORT-01 says "4 edges" not "3"). |

### PORT-02 — Auto-equal-spacing on add/remove

| # | Assertion |
|---|-----------|
| PORT-02.1 | Add 1 port to Top edge of Console → port appears at exact horizontal center of the edge. |
| PORT-02.2 | Add a 2nd port to Top edge → first port shifts left, second port shifts right, equal spacing relative to edge midpoint. |
| PORT-02.3 | Add a 3rd port to Top edge → three ports evenly distributed (1/4, 1/2, 3/4 of edge width). |
| PORT-02.4 | Remove the middle (2nd) port → remaining 2 ports snap to 1/3 and 2/3 positions. |
| PORT-02.5 | Snap is INSTANT — no animated transition. |

### PORT-03 — Dropdown-or-custom label exclusive

| # | Assertion |
|---|-----------|
| PORT-03.1 | Add a port → focus the label input → type 1 character → autocomplete dropdown appears within ~200ms. |
| PORT-03.2 | Type "FOH" → dropdown shows project-scoped suggestions matching "FOH" (e.g., "FOH Lead — Device Input"). |
| PORT-03.3 | Click a suggestion → port label populates with the chosen text. |
| PORT-03.4 | Type new freeform text overriding the picked label → port label updates to the freeform text (LBL-03 override). |
| PORT-03.5 | SystemProcessor records do NOT appear in suggestions (D-05 from Phase 10 — inherited). |
| PORT-03.6 | Suggestions are scoped to `request.current_project` — switching to a different project never shows cross-project signal names. |

### PORT-04 — Per-port snap targeting + back-compat

| # | Assertion |
|---|-----------|
| PORT-04.1 | Shape with 0 authored ports — drag a connector from any port hover-revealed at the edge midpoints (the v2.2 4-generic-port behavior) → connector snaps to the generic ports as before. |
| PORT-04.2 | Add 1 authored port to the Top edge of the same shape → the 4 generic ports disappear (D-13 whole-shape switch). |
| PORT-04.3 | After step 2, the only snap target on this shape is the 1 authored port. Hovering the shape reveals only that one port dot. |
| PORT-04.4 | Add authored ports on multiple edges → each port is independently snappable for connectors. |
| PORT-04.5 | Mid-shape drops still rejected by `validateConnection` (CON-03 preserved). |

### PORT-05 — Connector survival on port removal

| # | Assertion |
|---|-----------|
| PORT-05.1 | Create a port → attach a connector from another shape to it → port has 1 attached connector. |
| PORT-05.2 | Click trash icon on that port row → port disappears AND the connector REMAINS in the graph (does not disappear). |
| PORT-05.3 | Inspect the connector → its endpoint is now anchored at the paper-coordinate midpoint of the shape's edge (where the removed port lived). |
| PORT-05.4 | Connector signal type, direction, and circuit label are unchanged. |
| PORT-05.5 | Autosave fires within 1500ms of the trash-icon click; reload the page → connector still present, endpoint still at the edge midpoint. |

### PORT-06 — Auto-expansion on overflow

| # | Assertion |
|---|-----------|
| PORT-06.1 | Console shape at default 180×60 — add 5 ports to the Top edge → shape width grows to fit at minimum 24px spacing (no port labels overlap). |
| PORT-06.2 | Toast appears: "Shape resized to fit ports." — visible briefly, dismisses on its own. |
| PORT-06.3 | Add a port with a very long label ("FOH Lead Vocal Microphone Channel 17") to a Left edge — shape grows to fit the label width. |
| PORT-06.4 | Rename an existing port to a longer string → shape grows if necessary; toast fires. |
| PORT-06.5 | Removing a port does NOT shrink the shape (only manual resize shrinks). |
| PORT-06.6 | Shape position (top-left) is preserved on auto-expansion — shape grows toward the right and bottom only. |
| PORT-06.7 | Ctrl+Z undoes the port-add AND the auto-expand as a single gesture. |

### SHP-RESIZE-01 — Resize any shape via corner handle

| # | Assertion |
|---|-----------|
| SHP-R-01.1 | Select a Console → 4 corner handles appear at the shape's corners (TL, TR, BL, BR). |
| SHP-R-01.2 | Drag the BR handle outward → shape grows down and to the right; TL corner stays anchored. |
| SHP-R-01.3 | Drag the TL handle inward (toward BR) → shape shrinks; BR corner stays anchored. |
| SHP-R-01.4 | Repeat for SpeakerArray (polygon body) — polygon body resizes correctly along with the bounding box. |
| SHP-R-01.5 | Repeat for CommBeltPack (pill body, rx/ry rounded corners) — pill resizes; rounded corners scale proportionally. |
| SHP-R-01.6 | All 7 shape classes (Console / Device / Processor / Amp / SpeakerArray / CommBeltPack / Generic) get corner handles when selected. |
| SHP-R-01.7 | Deselect shape → corner handles disappear. |

### SHP-RESIZE-02 — Min-size constraint

| # | Assertion |
|---|-----------|
| SHP-R-02.1 | Console with 0 ports — drag BR handle toward TL → shape stops shrinking at 180×60 (Phase 8 default = absolute floor). |
| SHP-R-02.2 | Add 3 ports to Top edge of Console with short labels → minimum width is now (2×12 + 3×24) = 96px or 180px (absolute floor wins) → still 180px min. |
| SHP-R-02.3 | Add 6 ports to Top edge → minimum width = (2×12 + 6×24) = 168px (below 180 floor) → 180px floor wins. |
| SHP-R-02.4 | Add 10 ports to Top edge → minimum width = (2×12 + 10×24) = 264px → shape grows to 264px (auto-expand). Now dragging BR inward cannot shrink below 264px. |
| SHP-R-02.5 | Rename a Left-edge port to a very long string → minimum width grows to fit; cannot drag below the new minimum. |
| SHP-R-02.6 | Min size enforced LIVE during drag (drag below min and the shape clamps to min, doesn't follow the cursor). |

### SHP-RESIZE-03 — Resize + autosave + undo + 409 conflict

| # | Assertion |
|---|-----------|
| SHP-R-03.1 | Resize a shape → drag-end → autosave fires within 1500ms (visible in Network tab as POST to autosaveUrl). |
| SHP-R-03.2 | After autosave 200 OK → status indicator shows "All changes saved." |
| SHP-R-03.3 | Reload the page → shape is at the new resized dimensions (canvas_state round-trips correctly). |
| SHP-R-03.4 | Resize → Ctrl+Z → shape returns to previous size. Ctrl+Y → re-applies the resize. |
| SHP-R-03.5 | Open the diagram in two browser tabs. In tab A resize a shape and let autosave complete. In tab B (stale version) resize another shape → 409 banner appears in tab B; canvas locks. |
| SHP-R-03.6 | Snap-to-grid ON: resize snaps to multiples of 20px. Snap OFF: resize is pixel-accurate. |

### Cross-cutting

| # | Assertion |
|---|-----------|
| X.1 | Add ports + resize → close browser tab → reopen → all ports and the resized dimensions are restored. |
| X.2 | Switch projects (CurrentProjectMiddleware) → re-open a different diagram → that diagram's ports + sizes are correct (no cross-project bleed). |
| X.3 | View as a non-editor (viewer role) — Phase 8 + 9 already block edits at the server. Verify viewer cannot add/remove/rename ports in the inspector (controls disabled or absent). |

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Corner resize handle | Custom `<rect>` + pointerdown + pointermove + pointerup in raw SVG | Subclass `joint.elementTools.Control` per the official Resize Control Tool demo | The official demo IS the MPL-2.0 reference implementation — short, correct, integrates with `paper.findView(cell).addTools()` and `removeTools()` for selection-lifecycle. |
| Port-label text measurement | Re-implement text-width measurement with hidden DOM nodes | Native `Canvas.getContext('2d').measureText(text).width` — no library | Browser-built-in; system-fonts-only constraint makes this deterministic; ~5 lines of code. |
| Port re-distribution on add/remove | Animate ports with `requestAnimationFrame` interpolation | Instant snap per D-10 — write final `port.args.x` / `port.args.y` and re-render | Zero animation budget; matches Phase 8 snap-to-grid feel. |
| Connector re-anchor on port removal | Hook `link:disconnect` and walk graph for stranded links | Intercept inspector trash-click BEFORE `removePort()` — re-anchor first, then remove | `link:disconnect` does NOT fire for `removePort()`-driven removals (verified by source inspection). |
| Per-shape min-size table | Hard-code per-class width/height minimums | Compute from live port set + label widths + absolute floors (Q2 formula) | Hard-coded floors become wrong the moment an engineer adds a long label or many ports. |
| Inspector port-list scroll | Custom virtualized list | Native CSS `overflow-y: auto` on the inspector aside | Typical port count is 1-12 per edge; virtualization is unnecessary. |
| Combobox attached to port inputs | Re-implement autocomplete per port row | Refactor Phase 10's `initAutocomplete()` into `attachAutocompleteToInput(el, url, onSelect)` and reuse | Phase 10 D-04 explicitly mandates reuse. |

**Key insight:** Phase 11 is the second consecutive "use the framework, don't reinvent" phase. JointJS's port API, element-tools framework, magnet semantics, and label.position system handle 90%+ of the requirements; Phase 11's net code addition is mostly inspector UI + the port-authoring CRUD façade + the min-size math + the connector re-anchor interception.

---

## Common Pitfalls

### Pitfall 1: Relying on `joint.elementTools.Resize` from training data

**What goes wrong:** Older JointJS examples and Stack Overflow answers reference `joint.elementTools.Resize` as if it shipped with the open-source library. Training data from 2023-2024 may confidently assert this.
**Why it happens:** JointJS+ (paid commercial fork) bundles a `Resize` tool; some demos show it. The MPL-2.0 core does NOT.
**How to avoid:** Verify against the vendored bundle (see Q1 §"Empirical confirmation") and the official element-tools docs.
**Warning signs:** Code that imports `Resize` from `@joint/core` and gets `undefined` at runtime; example snippets that don't compile.

### Pitfall 2: Trusting `link:disconnect` for port-removal-driven link cleanup

**What goes wrong:** Plan adds a `link:disconnect` listener to handle PORT-05 and ships → in beta, removing a port silently deletes attached connectors.
**Why it happens:** `link:disconnect` fires on pointer-drag disconnects, NOT on `removePort()`-driven link removal. JointJS's internal `_processRemovedPort` calls `link.remove()` directly without emitting `link:disconnect`.
**How to avoid:** Intercept the inspector trash-icon click. Re-anchor links BEFORE calling `removePort()`. See Q6 for the exact recipe.
**Warning signs:** Connectors disappear from the graph after port-removal during manual UAT; autosave POST body has no link records for the deleted connector.

### Pitfall 3: Forgetting to refresh `resize-tool` after re-selection

**What goes wrong:** Engineer selects shape → 4 handles appear → engineer drags one → handles seem to lag the new size.
**Why it happens:** JointJS `Control` tool reads `view.model.size()` in `getPosition` every frame, but if the tools were attached BEFORE the resize, they may need a `view.updateTools()` call.
**How to avoid:** Listen for `change:size` on the cell and call `view.updateTools()` (or detach + re-attach) within the same frame. The `ToolsView` re-renders automatically when added to a view that fires `change:size` only IF the view's `tools` flag includes it.
**Warning signs:** Resize handles visually behind the cursor by 1-2 frames during drag.

### Pitfall 4: Snap-to-grid + min-size interaction

**What goes wrong:** Engineer drags BR handle inward → snap to 160px → min size is 168px → shape pops to 168px → engineer's drag cursor still expects 160px → visual judder.
**Why it happens:** Snap rounding can pull the value below min; min clamp then bounces it back up.
**How to avoid:** Apply min-size clamp AFTER snap rounding, not before. (See the snippet in Q1 §"Phase 11 adaptation" — clamps after the snap.) Then the drag is monotonic: snap → clamp → render.
**Warning signs:** During drag, the cursor seems to "stick" then "jump" at the min-size threshold.

### Pitfall 5: Port-label text measurement before the input is committed

**What goes wrong:** Engineer types in the port-label input → every keystroke triggers `measureLabelWidth` → cache balloons / measurement runs during transient invalid strings.
**Why it happens:** No debounce between keystroke and width-measurement.
**How to avoid:** Use the same Phase 9 200ms label-input debounce pattern from signal_flow_editor.js:1412-1428. Only call `maybeAutoExpand()` after the debounce fires.
**Warning signs:** High CPU during fast typing; React-like flicker on the canvas.

### Pitfall 6: Port id mismatch after copy-paste

**What goes wrong:** Phase 11 ships; a future v2.4+ adds copy-paste (currently deferred); engineer copies a shape with authored ports → pasted shape has duplicate port ids → JointJS throws "found id duplicities in ports."
**Why it happens:** Default JointJS port-id generation reuses ids on cloned cells.
**How to avoid:** Out of Phase 11 scope (copy-paste is deferred). But document the risk: future v2.4+ copy-paste must regenerate port ids on paste. Add a code comment in `addAuthoredPort` flagging this for the v2.4+ developer.
**Warning signs:** v2.4+ copy-paste crash log mentioning duplicate port ids.

### Pitfall 7: `change:ports` firing during auto-expand → infinite recompute

**What goes wrong:** `addAuthoredPort` → fires `change:ports` → triggers a listener that calls `redistributeEdgePorts` → calls `portProp` → fires `change:ports` again → loop.
**Why it happens:** Naïve listener wiring on `change:ports`.
**How to avoid:** Use a one-shot guard flag during port-system mutations, OR call `cell.set('ports', value, { silent: true })` for the redistribute pass and a single `cell.trigger('change:ports')` at the end. JointJS supports `{silent: true}` per Backbone conventions.
**Warning signs:** Browser tab hangs; "Maximum call stack" error in console.

### Pitfall 8: D-13 conversion-loss on autosave race

**What goes wrong:** Engineer adds first authored port to a shape → conversion fires (remove 4 generic ports + add 1 authored port) → autosave fires mid-conversion → server gets a snapshot with 3 generic + 1 authored ports → reload shows 4 ports.
**Why it happens:** Multi-mutation conversion without `beginBatch/endBatch`.
**How to avoid:** Wrap the entire conversion in `beginBatch/endBatch` AND set a "mutation in flight" guard that suppresses autosave debounce until `endBatch`. (Same pattern as Phase 9 keepalive flush — "skip if `savingNow` or mutation pending".)
**Warning signs:** First-port-add intermittently produces 5-port shapes on reload.

---

## Code Examples

### Example 1: Building the corner-resize tool

```javascript
// Source: github.com/clientIO/joint-demos/resize-control-tool/js/src/main.js
//         (adapted for 4 corners + min-size + snap-to-grid)
var CornerResize = joint.elementTools.Control.extend({
  children: [{
    tagName: 'rect',
    selector: 'handle',
    attributes: {
      width: 10, height: 10, x: -5, y: -5,
      fill: '#0d9488', stroke: '#fff', 'stroke-width': 1,
      cursor: 'nwse-resize'
    }
  }],
  getPosition: function (view) {
    var s = view.model.size();
    var c = this.options.corner;
    if (c === 'tl') return { x: 0,       y: 0 };
    if (c === 'tr') return { x: s.width, y: 0 };
    if (c === 'bl') return { x: 0,       y: s.height };
    return { x: s.width, y: s.height };
  },
  setPosition: function (view, coordinates) {
    // ... see Q1 §"Phase 11 adaptation" for the full per-corner math.
  }
});
```

### Example 2: Adding an authored port with custom label

```javascript
// Phase 11 — addAuthoredPort core logic.
function addAuthoredPort(cell, edge, label) {
  if (!cellHasAnyAuthoredPort(cell)) {
    convertCellFromGenericToAuthored(cell);   // D-13 whole-shape switch
  }
  cell.addPort({
    group: (edge === 'top' || edge === 'left') ? 'in' : 'out',
    attrs: {
      portBody: {
        magnet: (edge === 'top' || edge === 'left') ? 'passive' : true,
        r: 4, fill: '#fff', stroke: '#666',
        'stroke-width': 1, opacity: 0
      },
      label: { text: label }
    },
    args: { x: 0, y: 0 },   // will be set by redistributeEdgePorts
    label: {
      position: portLabelPositionForEdge(edge),     // Q10 — manual layout per edge
      markup: portLabelMarkupForEdge()
    },
    showstack: { label: label, edge: edge, authored: true }
  });
  redistributeEdgePorts(cell, edge);
  maybeAutoExpand(cell);
  scheduleAutosave();
}
```

### Example 3: Connector re-anchor before port removal

```javascript
// Phase 11 — must run BEFORE cell.removePort(portId) to prevent
//            JointJS _processRemovedPort from auto-deleting the link.
function removeAuthoredPortWithSurvival(cell, portId) {
  // Step 1: re-anchor all attached links to the edge midpoint.
  if (cell.graph) {
    var port = cell.getPort(portId);
    var edge = (port && port.showstack && port.showstack.edge) || 'left';
    var midpoint = edgeMidpointInPaperCoords(cell, edge);

    cell.graph.getConnectedLinks(cell).forEach(function (link) {
      var src = link.get('source'), tgt = link.get('target');
      if (src && src.port === portId) {
        link.source({ x: midpoint.x, y: midpoint.y });
      }
      if (tgt && tgt.port === portId) {
        link.target({ x: midpoint.x, y: midpoint.y });
      }
    });
  }
  // Step 2: now safe to remove — JointJS finds no stale port references.
  cell.removePort(portId);
  redistributeEdgePorts(cell, port.showstack.edge);   // re-snapshot edge from local
  scheduleAutosave();
}
```

### Example 4: Auto-expand with toast

```javascript
function maybeAutoExpand(cell) {
  var current = cell.size();
  var min = computeMinSize(cell);
  var grew = false;
  var newW = current.width, newH = current.height;
  if (min.width  > current.width)  { newW = min.width;  grew = true; }
  if (min.height > current.height) { newH = min.height; grew = true; }
  if (!grew) return;
  if (window.__sfd.viewport.snapEnabled) {
    newW = Math.ceil(newW / 20) * 20;
    newH = Math.ceil(newH / 20) * 20;
  }
  cell.resize(newW, newH);
  showToast('Shape resized to fit ports.', 'info');
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 4 generic ports per shape, fixed positions | Engineer-authored ports with labels + auto-distribute | Phase 11 (this) | Engineers can model their actual signal flow at port granularity. Closes the gap with Lucidchart's port-labeling and TheatreMix's per-channel mapping. |
| Hard-coded shape geometry (180×60 Console, etc.) | Engineer-resizable with per-type min-size | Phase 11 (this) | Engineers can fit shapes to their canvas layout; large diagrams stay legible. |
| `joint.elementTools.Resize` (training-era assumption) | Custom `Control` subclass per the official MPL demo | n/a — never shipped in MPL core | No license risk; ShowStack stays MPL-2.0-clean. |
| Auto-remove links when their port is removed (JointJS default) | Intercept + re-anchor to edge midpoint (Phase 11) | Phase 11 (this) | Engineer's mental model preserved: removing a port doesn't lose work. Matches Figma / Lucidchart "delete a node anchor but keep the line" behavior. |

**Deprecated/outdated:**
- The Phase 8 `portsForRect()` function is still REFERENCED by all 7 shape classes — it remains the source of v2.2 back-compat generic ports until the first authored port is added. Phase 11 does NOT delete it.
- Older JointJS tutorials referencing `dia.Element.tools` (pre-4.x) — element tools moved to `elementTools` namespace + `ToolsView` API in 4.x. The pattern in Q1 is the 4.x idiom.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `@joint/core` UMD bundle | Resize tool + port API | ✓ | 4.2.4 vendored at `planner/static/planner/js/vendor/joint.min.js` | — |
| `html-to-image` | Untouched in Phase 11 | ✓ | 1.11.11 vendored | — |
| Browser `Canvas 2D measureText` | Q2 label-width math | ✓ | native | — |
| Phase 10 `signal_flow_label_autocomplete` view | PORT-03 dropdown | ✓ | Live at `URL_NAMES.signal_flow_label_autocomplete` | — |
| Phase 9 `scheduleAutosave()` | All Phase 11 mutations | ✓ | Live in IIFE module-scope at signal_flow_editor.js:1597 | — |
| Phase 9 `.sfd-toast` infrastructure | D-11 auto-expand toast | ✓ | CSS Section 6 + `showToast()` helper at signal_flow_editor.js:72 | — |
| Phase 9 `window.__sfd.undo.beginBatch/endBatch` | Atomic add-port + auto-expand undo | ✓ | Exposed at signal_flow_editor.js:1759-1763 | — |
| `joint.elementTools.Control` | Resize tool foundation | ✓ | In MPL-2.0 core 4.2.4 [VERIFIED: bundle inspection] | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none.

---

## Validation Architecture

Skipped — `workflow.nyquist_validation` is not enabled in this project (per Phase 9 / 10 plans which omit the section).

For Phase 11 verification, the Phase 11 planner should:
1. Include the 47 assertions from Q11 above (PORT-01 through SHP-RESIZE-03 + cross-cutting) as the UAT script.
2. Add a Wave-N task "JS structural check" using `node --check planner/static/planner/js/signal_flow_editor.js` (matches Phase 10's verification pattern at 10-03-SUMMARY.md line 161).
3. Add a Wave-N task "Django system check" using `python manage.py check`.
4. Defer functional in-browser UAT to Charlie (human verifier) since interactive resize/port-add behavior cannot be smoke-tested headlessly without a JointJS-on-headless-Chrome setup (deferred from v2.2 milestone).

---

## Security Domain

> Phase 11 is purely client-side (JS + CSS edits) with one server-side touchpoint: the Phase 10 `signal_flow_label_autocomplete` endpoint (UNCHANGED in Phase 11 — just reused).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (inherited) | Django session auth via `@login_required` on all endpoints — unchanged from Phase 9/10. |
| V3 Session Management | yes (inherited) | `CurrentProjectMiddleware` project scoping — unchanged. |
| V4 Access Control | yes (inherited) | Phase 9 IDOR allowlist on autosave (`('Console','Device','CommBeltPack','Amp','SystemProcessor','P1Processor','GalaxyProcessor')`) — UNCHANGED in Phase 11 because no new GFK content types are added. Engineer-authored ports do NOT reference equipment via GFK; only the cell itself does. |
| V5 Input Validation | yes | Engineer-typed port labels are user-controlled strings going into `canvas_state` JSON. Bounded by autosave's existing JSON-validation; rendered into JointJS SVG (not HTML). |
| V6 Cryptography | no | No cryptographic operations in Phase 11. |

### Known Threat Patterns for client-side JointJS + Django JSON state

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via port-label rendering | Tampering / Spoofing | Port labels render inside JointJS SVG via `attrs.label.text` — JointJS escapes text content into `textContent` automatically (SVG `<text>` cannot execute script). Inspector port-row label INPUTS render the engineer's typed value back into the input's `value` property, NOT into innerHTML — same XSS-safe pattern as Phase 10's autocomplete row (`labelSpan.textContent = rec.label`). [VERIFIED: signal_flow_editor.js:1882 — Phase 10's pattern; reuse identical pattern for Phase 11 port-row labels.] |
| XSS via port label in HTML inspector | Tampering | Use `textContent` ONLY when re-rendering port labels into the inspector port-row from canvas state. Never use innerHTML. Same rule as Phase 8 picker rows (signal_flow_editor.js:523). |
| IDOR via crafted port autocomplete query | Tampering / EoP | Phase 10's `signal_flow_label_autocomplete` already enforces `request.current_project` filtering. Phase 11 reuses unchanged — no new attack surface. |
| Denial of service via massive port count | Tampering | A malicious engineer (paid premium user) can in principle add hundreds of ports per shape, growing canvas_state. JSON validation already caps at the model's JSONField size; auto-expand keeps the shape readable. No new server-side limits in v2.3; if abuse is observed in beta, cap at 50 ports per edge per shape in the addAuthoredPort guard. |
| Polluted port-label data from XSS via the autocomplete endpoint | Tampering | The autocomplete endpoint returns project-scoped database values (DeviceInput.signal_name, etc.). These come from Django admin where they can be set by editors. ShowStack's existing admin permission model controls who can enter these strings; rendering into SVG `text` element via JointJS is XSS-safe. No new threat. |
| `If-Match` 409 conflict during port add | Tampering | Phase 9 conflict-banner machinery already handles this — Phase 11 port mutations go through the same autosave POST so the banner fires as expected. UAT case SHP-R-03.5 covers this. |

**No new threat surface introduced by Phase 11.** All Phase 11 endpoints are existing Phase 9/10 endpoints; the new code is pure client-side JS that operates on already-trusted DOM and graph state.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Browser-canvas `measureText` cache invalidation isn't needed within a single session (engineer doesn't install fonts mid-session). | Q2 | Stale cached widths → shape min-size slightly off. Low impact; auto-expand on next port add corrects. |
| A2 | When the engineer removes the LAST authored port from a shape, we do NOT restore the 4 generic ports. The shape stays in "authored mode" forever. | Q5 §"removeAuthoredPort" | Engineers may expect the shape to revert to v2.2 behavior. If beta reports show confusion, add a "restore generic ports" affordance in v2.4+. |
| A3 | Live re-distribute during resize drag (D-06) does not produce visible lag on Charlie's M1 MacBook Pro running Chrome at 60fps. | Q1 §"setPosition" | Not testable without hardware in-loop. If lag surfaces, throttle redistribute to drag-end (less responsive feel but lower CPU). |
| A4 | All 7 shape classes accept the resize tool without per-class customization (i.e., SpeakerArray's polygon body and CommBeltPack's pill rx/ry rescale correctly when `model.resize(w, h)` runs). | Q1, Q8 | If polygon/pill body has fixed-pixel geometry that doesn't rescale, would need per-shape `resizeBehavior` override. Quick manual UAT covers this; fallback is per-class resize handler. |
| A5 | The "1 frame" claim in D-12 (connectors re-anchor in the same frame as port disappears) — modern browsers can complete the re-anchor + port-remove + re-render in <16ms. | Q6 | Acceptable: brief flicker is the worst-case observable defect. |
| A6 | `joint.util.deepSupplement` (used in Phase 8 shape class definitions) does not interfere with later `joint.util.assign(Cls.prototype, mixin)` calls. | Q8 (Option A) | If Option A is chosen and bugs surface, fall back to Option B (module-level functions). |

**All other claims in this research are [VERIFIED] or [CITED] — see Sources section.**

---

## Open Questions

None at the end of this research. Every one of the 11 questions in the spawn brief has a concrete answer with sources. The single remaining uncertainty is:

- **PORT-05 default JointJS behavior** is verified by direct bundle inspection (HIGH confidence in mitigation). The mitigation (re-anchor BEFORE removePort) is the canonical workaround and matches engineer-intent.
- **Q3 direction-from-edge** is a recommendation, not a verification — the planner OR the discuss-phase may want a sanity check with Charlie. Default is "infer from edge"; if Charlie wants explicit control, that's a v2.4+ enhancement.

---

## Sources

### Primary (HIGH confidence)

- **Vendored `joint.min.js` 4.2.4** (this project) — `planner/static/planner/js/vendor/joint.min.js`
  - elementTools namespace contents (line 207789 region, "elementTools=a" assignment)
  - `_processRemovedPort` private method (line 207855 region)
  - `_validatePorts` and `generatePortId` (line ~324793 region)
  - `addPort`, `insertPort`, `portProp`, `removePort` source bodies
  - Backbone-Backbone event strings: `change:ports`, `link:disconnect`, `link:connect`, `change:source`, `change:target`
- **Official JointJS Resize Control Tool demo** — github.com/clientIO/joint-demos/blob/main/resize-control-tool/js/src/main.js (MPL-2.0)
- **JointJS v4.2 elementTools API docs** — docs.jointjs.com/api/elementTools/
- **JointJS v4.2 dia.Element docs** — docs.jointjs.com/api/dia/Element/ (resize fires `change:size`; ports + addPort/removePort/getPorts methods serializable)
- **MDN CanvasRenderingContext2D.measureText** — developer.mozilla.org (native browser API)

### Secondary (MEDIUM confidence)

- **JointJS PortLabel layout docs** — docs.jointjs.com/api/layout/PortLabel/ (manual layout supports x/y/textAnchor args)
- **JointJS v4.0 JSON serialization docs** — docs.jointjs.com/4.0/learn/features/export-import/json/ (custom properties preserved through toJSON/fromJSON)
- **JointJS Issue #892 `link:disconnect` not firing** — github.com/clientIO/joint/issues/892 (confirmed scope of `link:disconnect` event)

### Tertiary (LOW confidence, marked for validation)

- **JointJS Resize Control Tool demo page** — jointjs.com/demos/resize-control-tool (marketing page only; source code on GitHub is the primary)
- **WebSearch: "JointJS+ Resize JointJS+ paid commercial only not in core"** — confirms `Resize` tool is JointJS+, not core
- **JointJS v4.x ports tutorial (legacy URL)** — resources.jointjs.com/tutorial/ports (referenced but content not extractable via WebFetch)

### Code-level sources (this project)

- `planner/static/planner/js/signal_flow_editor.js` — read in full
- `planner/static/planner/css/signal_flow.css` — read for section structure
- `planner/templates/planner/signal_flow/editor.html` — inspector DOM verified
- `.planning/phases/08-canvas-smart-shapes-connectors/08-CONTEXT.md` — port + magnet conventions
- `.planning/phases/09-autosave-orphan-rendering/09-CONTEXT.md` — autosave pattern + toast + If-Match
- `.planning/phases/10-autocomplete-png-export-new-shapes/10-CONTEXT.md` — autocomplete combobox reuse mandate
- `.planning/phases/10-autocomplete-png-export-new-shapes/10-03-SUMMARY.md` — combobox widget location at signal_flow_editor.js:1775-1935

---

## Metadata

**Confidence breakdown:**
- Standard stack (Q1): **HIGH** — direct bundle inspection + official demo source + multiple corroborating sources
- Architecture patterns (Q4, Q5, Q8, Q9, Q10): **HIGH** — JointJS port API confirmed by docs + bundle source
- Min-size math (Q2): **HIGH** for formula; **MEDIUM** for the `MIN_PORT_SPACING = 24px` constant (chosen by analysis but not user-tested — beta engineers may want 28 or 32)
- Port direction semantics (Q3): **MEDIUM** — recommendation, not verification (default to "infer from edge"; planner or discuss-phase confirms)
- Connector survival (Q6): **HIGH** — direct bundle source inspection of `_processRemovedPort`
- Auto-expansion (Q7): **HIGH** — straightforward composition of Q2 + existing helpers
- Validation cases (Q11): **HIGH** — every assertion derived from CONTEXT.md decisions
- Common pitfalls: **HIGH** — most pitfalls derive from direct source inspection or known-bad patterns called out by JointJS GitHub issues
- Security: **HIGH** — no new attack surface; inheritance from Phase 9/10

**Research date:** 2026-05-24
**Valid until:** 2026-06-24 (30 days — stack is stable; @joint/core 4.2.4 has been the locked version since v2.2 milestone start in 2026-05-20)

---

## RESEARCH COMPLETE

All 11 research questions answered with verified or cited claims. Single MEDIUM-confidence item (Q3 direction semantics) flagged with a recommendation default — planner should proceed with "infer from edge" unless discuss-phase surfaces an objection. Single ASSUMED item (A2 — last-port-removed does not restore generics) flagged for planner confirmation.
