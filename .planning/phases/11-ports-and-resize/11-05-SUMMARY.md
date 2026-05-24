---
phase: 11-ports-and-resize
plan: "05"
subsystem: signal-flow-diagrammer
tags:
  - phase-11
  - resize
  - element-tools
  - autosave
  - css

dependency_graph:
  requires:
    - "11-02-SUMMARY.md (getAuthoredPortsByEdge, cellHasAnyAuthoredPort, redistributeEdgePorts — consumed by computeMinSize + change:size listener)"
    - "11-04-SUMMARY.md (portLabelMarkupForEdge real implementation — measureLabelWidth font stack matches rendering)"
  provides:
    - "ABSOLUTE_FLOORS table — per-shape resize floor keyed by type string"
    - "measureLabelWidth(text, fontSize) — memoized Canvas-2D measureText helper"
    - "computeMinSize(cell) — full Q2 formula: port-count × spacing + label widths + body label + floor"
    - "CornerResize — joint.elementTools.Control subclass with 4 corner handles"
    - "attachResizeTools(cell) / detachResizeTools(cell) — selection-driven tool lifecycle"
    - "_resizeAttachedCell tracker — prevents stale handle accumulation (T-11-05-03)"
    - "change:size autosave listener extension (SHP-RESIZE-03 + Plan 11-06 programmatic resize)"
    - "change:size live-redistribute listener (D-06 — redistributeEdgePorts all 4 edges + view.updateTools)"
    - "window.__sfd.resize = { computeMinSize, measureLabelWidth } (Plan 11-06 consumes computeMinSize)"
    - "CSS Section 15 — teal corner resize handle styling"
  affects:
    - "Plan 11-06 (maybeAutoExpand) — calls window.__sfd.resize.computeMinSize to check PORT-06 auto-expand trigger"

tech_stack:
  added: []
  patterns:
    - "joint.elementTools.Control subclass — MPL-2.0 core (NOT joint.elementTools.Resize which is JointJS+ paid-only)"
    - "Snap-then-clamp ordering: newW = Math.round(newW/20)*20 THEN Math.max(newW, minSize.width) (Pitfall 4)"
    - "Memoized Canvas-2D measureText with (fontSize|text) cache key — avoids repeated DOM layout"
    - "view.removeTools() + addTools(new ToolsView) per selection change — prevents SVG tool node accumulation"
    - "Separate change:size listeners: one for autosave (extends existing add/remove/source/target listener), one for redistribute + updateTools (D-06 + Pitfall 3)"

key_files:
  created: []
  modified:
    - "planner/static/planner/js/signal_flow_editor.js"
    - "planner/static/planner/css/signal_flow.css"

decisions:
  - "joint.elementTools.Control subclass chosen over joint.elementTools.Resize — vendored bundle (JointJS 4.2.4 MPL-2.0) does not include the paid Resize tool; confirmed by RESEARCH §Q1 bundle inspection"
  - "_resizeAttachedCell tracker placed before onSelectionChanged definition (line ~1811); detach called at the top of EVERY branch so stale handles cannot accumulate regardless of selection path"
  - "Separate change:size listener for redistribute rather than combining with autosave listener — preserves ability to opt out per-cell in v2.4+ without touching the autosave path"
  - "ABSOLUTE_FLOORS keyed by full type string ('showstack.Console' etc.) — matches cell.get('type') which returns the full namespaced string; verified against lines 383-573 shape class defaults"
  - "measureLabelWidth cache keyed as fontSize+'|'+text — pipe separator avoids any collision between fontSize prefix digits and label text digits"

metrics:
  duration: "22 minutes"
  completed_date: "2026-05-24"
  tasks_completed: 3
  files_modified: 2
---

# Phase 11 Plan 05: Corner-Handle Resize Tool Summary

**One-liner:** CornerResize (joint.elementTools.Control subclass) ships all 7 shape types with per-shape min-size clamp (ABSOLUTE_FLOORS + port-count × spacing + label widths), snap-after-clamp ordering, live port redistribute on resize drag, and full autosave + undo + 409 integration via existing Phase 9 infrastructure.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Min-size constants + measureLabelWidth + computeMinSize + ABSOLUTE_FLOORS | 4f83cc7 | `signal_flow_editor.js` |
| 2 | CornerResize + attachResizeTools/detachResizeTools + selection wiring + change:size listeners + window.__sfd.resize | d2b01b4 | `signal_flow_editor.js` |
| 3 | CSS Section 15 — resize handle styling | 6cc774c | `signal_flow.css` |

## Task 1 Detail — Min-size math infrastructure

**Insertion point:** Lines 382–481 (after `portLabelMarkupForEdge` closing brace at line 380, before Console shape class at line 482)

**Constants declared:**
- `MIN_PORT_SPACING = 24` — center-to-center port spacing (off-grid; 20px is too tight for 11px labels)
- `PORT_LABEL_FONT_SIZE = 11` — matches Plan 11-04 `portLabelMarkupForEdge` font-size exactly
- `EDGE_PADDING_PARALLEL = 12` — corner clearance along an edge
- `EDGE_PADDING_PERPENDICULAR_INSIDE = 8` — label inset from edge into shape body
- `FONT_LINE_HEIGHT = Math.ceil(11 * 1.4)` = 16px

**ABSOLUTE_FLOORS table (7 entries):**

| Shape type | Floor W | Floor H |
|------------|---------|---------|
| showstack.Console | 180 | 60 |
| showstack.Device | 140 | 56 |
| showstack.SpeakerArray | 120 | 80 |
| showstack.CommBeltPack | 80 | 100 |
| showstack.Generic | 140 | 56 |
| showstack.Processor | 160 | 60 |
| showstack.Amp | 140 | 60 |

> **Maintenance note:** If any shape's `defaults.size` changes in a future phase, update the ABSOLUTE_FLOORS table entry here. The table is the authoritative min-size floor for resize drag AND Plan 11-06 auto-expansion.

**measureLabelWidth(text, fontSize):** Module-scope canvas singleton + cache dict keyed `"<fontSize>|<text>"`. Font stack is verbatim system-ui stack matching `portLabelMarkupForEdge` — ensures measurement and rendering agree.

**computeMinSize(cell) Q2 formula:**
- `W_topbottom` = 2×EDGE_PADDING_PARALLEL + max(N_T, N_B) × MIN_PORT_SPACING (if ports on top/bottom)
- `W_leftright` = maxLabelWidth(left) + EDGE_PADDING_PERP + maxLabelWidth(right) + EDGE_PADDING_PERP + bodyLabelReserveW
- `minWidth` = max(W_topbottom, W_leftright, bodyLabelReserveW, floor.width)
- `H_topbottom` = (N_T>0 ? FONT_LINE_HEIGHT+EDGE_PADDING_PERP : 0) + (N_B>0 ? FONT_LINE_HEIGHT+EDGE_PADDING_PERP : 0) + 16
- `H_leftright` = 2×EDGE_PADDING_PARALLEL + max(N_L, N_R) × MIN_PORT_SPACING (if ports on left/right)
- `minHeight` = max(H_topbottom, H_leftright, floor.height)

For shapes with zero authored ports, all port-contribution terms are zero and `minSize` equals the ABSOLUTE_FLOOR + bodyLabelReserve.

## Task 2 Detail — CornerResize tool + wiring

**CornerResize class (lines 489–573):** `joint.elementTools.Control.extend()` with:
- `children[0]`: 10×10 rect, `selector: 'handle'`, teal fill, white stroke, `cursor: nwse-resize`
- `getPosition(view)`: returns corner coords in view-local space based on `this.options.corner` ∈ {tl, tr, bl, br}
- `setPosition(view, coordinates)`: computes new W/H/X/Y per corner geometry → applies `computeMinSize` clamp → applies snap-to-grid (if `viewport.snapEnabled`) → re-clamps after snap (Pitfall 4) → calls `model.position()` then `model.resize()`

**attachResizeTools(cell) (lines 551–566):** Guards `cell.isElement()` → finds view → `view.removeTools()` → adds `ToolsView({name:'sfd-resize', tools:[tl, tr, bl, br CornerResize instances]})`

**detachResizeTools(cell) (lines 567–573):** null-guards `cell.findView` → `view.removeTools()`

**_resizeAttachedCell tracker (line 1811):** Module-scope null variable. Detached at the top of every `onSelectionChanged` branch before potentially attaching a new cell. This ensures the handle count cannot grow beyond 4 no matter how fast the engineer clicks between shapes (T-11-05-03 mitigation).

**onSelectionChanged extension (lines 1810–1852):** Extended Phase 9 callback — link branch: detach only. Element branch: detach previous + attach new + record. Multi-select / empty: detach only + hide inspector.

**change:size listeners (lines 2338–2358):**
- Autosave: `graph.on('add remove change:source change:target change:size', scheduleAutosave)` — `change:size` appended to existing listener string (SHP-RESIZE-03 + Plan 11-06 programmatic resize path)
- Live redistribute: separate `graph.on('change:size', function(cell) {...})` — calls `redistributeEdgePorts` for all 4 edges on authored-port shapes; calls `view.updateTools()` so corner handles re-render at new corners during drag (Pitfall 3)

**window.__sfd.resize (line 2431):**
```javascript
window.__sfd.resize = {
  computeMinSize:    computeMinSize,
  measureLabelWidth: measureLabelWidth,
};
```
Plan 11-06 calls `window.__sfd.resize.computeMinSize(cell)` inside `maybeAutoExpand` to decide whether auto-expansion is needed (PORT-06 trigger).

## Task 3 Detail — CSS Section 15

**Appended at:** line 832 (end-of-file, after Section 14)

**Rules (31 lines):**
- Base handle: `#sfd-paper .joint-tools .joint-tool [selector="handle"]` + `g.joint-tool rect[joint-selector="handle"]` → `fill: #0d9488`, `stroke: #ffffff` — both selector forms target the JointJS tool child rect
- Hover: `#sfd-paper .joint-tools .joint-tool:hover [selector="handle"]` + `g.joint-tool:hover rect[joint-selector="handle"]` → `fill: #0f766e` (darker teal)
- Cursor: `#sfd-paper .joint-tools .joint-tool` → `cursor: nwse-resize` — v2.3 uniform cursor; per-corner cursors (nw/ne/sw/se) deferred to v2.4+

All rules `!important` per file-header SVG-namespace defence-in-depth convention.

## Verification Results

| Check | Result |
|-------|--------|
| `node --check signal_flow_editor.js` | PASS (exit 0) |
| `grep -c "function computeMinSize"` | 1 |
| `grep -c "function measureLabelWidth"` | 1 |
| `grep -c "ABSOLUTE_FLOORS"` | 2 (declaration + access in computeMinSize) |
| `grep -c "'showstack.Console'"` | 3 (shape class + ABSOLUTE_FLOORS + type string in shape def) |
| `grep -c "MIN_PORT_SPACING"` | 3 (declaration + 2 accesses) |
| `grep -c "PORT_LABEL_FONT_SIZE"` | 3 (declaration + 2 accesses) |
| `grep -c "_textMeasureCache"` | 3 (declaration + read + write) |
| `grep -c "var CornerResize"` | 1 |
| `grep -c "joint.elementTools.Control"` | 2 (extend call + comment) |
| `grep -c "joint.elementTools.Resize"` (must be code-free) | 1 (comment only — not used in code) |
| `grep -c "function attachResizeTools"` | 1 |
| `grep -c "function detachResizeTools"` | 1 |
| `grep -c "change:size"` | 3 (comment + autosave listener + redistribute listener) |
| `grep -c "view.updateTools"` | 2 (redistribute listener + tool re-render) |
| `grep -c "window.__sfd.resize"` | 1 |
| `grep -c "_resizeAttachedCell"` | 11 (declaration + detach-checks + assignments) |
| `grep -c "SECTION 15 — Resize handles"` (CSS) | 1 |
| `grep -c "joint-tool"` (CSS) | 6 (>= 3 — multiple Section 15 selectors) |
| `grep -c "nwse-resize"` (CSS) | 1 |
| `grep -c "#0d9488"` (CSS) | 14 (previous + new Section 15 fill rule) |
| `python3 manage.py check` | 0 issues |
| `collectstatic --noinput --dry-run` | 2 copied, 274 unmodified, no errors |
| Browser UAT | Manual — Charlie to verify SHP-RESIZE-01..03 assertion cases |

## UAT Assertion Cases (SHP-RESIZE-01..03) — Awaiting Charlie Browser Verification

**SHP-RESIZE-01 (Handle presence):**
- SHP-R-01.1..01.7: Select each of the 7 shape types → 4 teal corner handles appear at TL/TR/BL/BR
- Deselect (click canvas) → handles disappear from all shapes
- Multi-select two shapes → handles do not appear on either

**SHP-RESIZE-02 (Min-size enforcement):**
- SHP-R-02.1: Drag BR inward on a port-less Console → clamps at 180×60 (ABSOLUTE_FLOOR)
- SHP-R-02.2..02.6: Add authored ports to edges → drag floor grows; long label widens min-width

**SHP-RESIZE-03 (Autosave + undo + 409):**
- SHP-R-03.1: Drag-end → autosave POST fires within 1500ms (DevTools Network)
- SHP-R-03.2: Reload page → resized dimensions persisted
- SHP-R-03.3: Ctrl+Z → resize reverses
- SHP-R-03.4..03.6: Snap-on → 20px grid; 409 conflict in two-tab scenario handled same as any other edit

## Assumption Tracking

**A3 — Live redistribute doesn't lag at 60fps during drag:**
Implementation ships live redistribute on every `change:size` event. If Charlie observes lag during UAT (unlikely for shapes with < 20 ports), the fallback per RESEARCH §A3 is to move the redistribute call from `change:size` to `element:pointerup` (drag-end-only). This is a one-line change — remove the `change:size` redistribute listener and add a `paper.on('element:pointerup')` branch that redistributes only authored-port shapes.

**A4 — All 7 shapes accept resize without per-class customization:**
The `CornerResize` tool subclasses `joint.elementTools.Control` which operates on any `joint.dia.Element` — all 7 shape classes (including polygon SpeakerArray and pill-cornered CommBeltPack) are `Element` subclasses. The `model.resize(w, h)` call applies uniformly. No per-class override is needed. Charlie should visually confirm during UAT that SpeakerArray's polygon body scales correctly and CommBeltPack's rounded corners remain proportional.

## Deviations from Plan

None — plan executed exactly as written.

- Edit A (CornerResize + attach/detach): inserted immediately after `computeMinSize` closing brace, before Console shape class — matches plan action spec exactly.
- Edit B (change:size listeners): existing autosave listener string extended with `change:size`; separate redistribute listener added immediately after — matches plan action spec exactly.
- Edit C (selection wiring + resize surface): `_resizeAttachedCell` tracker added before `onSelectionChanged`; callback extended with attach/detach branches at each path; `window.__sfd.resize` namespace added adjacent to `window.__sfd.ports` — matches plan action spec exactly.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `maybeAutoExpand(cell)` — empty body | `signal_flow_editor.js` | Plan 11-06 fills with Q7 auto-expansion logic using `window.__sfd.resize.computeMinSize` |

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced.

- T-11-05-01 (autosave race during drag): debounced 1500ms — each frame resets the timer; one POST fires after drag-end. Verified by Phase 9 design.
- T-11-05-03 (handle accumulation): `_resizeAttachedCell` tracker + `view.removeTools()` at top of every selection branch mitigates SVG node leak.
- T-11-05-06 (handle hijacking): `!important` on all Section 15 rules matches Section 8 selection-visual defense pattern.

## Self-Check: PASSED

Files exist:
- `planner/static/planner/js/signal_flow_editor.js` — confirmed (`node --check` exit 0)
- `planner/static/planner/css/signal_flow.css` — confirmed (Section 15 at line 832)

Commits exist:
- `4f83cc7` — Task 1 (feat: min-size math infrastructure)
- `d2b01b4` — Task 2 (feat: CornerResize tool + wiring)
- `6cc774c` — Task 3 (feat: CSS Section 15)
