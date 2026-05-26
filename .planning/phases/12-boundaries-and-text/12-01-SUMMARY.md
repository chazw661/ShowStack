---
phase: 12
plan: 01
subsystem: signal-flow-editor
tags: [draw, txt, jointjs, cell-class]
requires: []
provides:
  - "joint.shapes.showstack.BoundaryLine"
  - "joint.shapes.showstack.TextLabel"
  - "applyBoundaryRender(cell)"
  - "BOUNDARY_PALETTE, TEXT_PALETTE, BOUNDARY_LINE_STYLES, TEXT_FONT_SIZES (closure-scoped)"
affects: [signal_flow_editor.js]
tech-stack:
  added: []
  patterns: ["JointJS cell-class registration before graph instantiation (PITFALLS §1)"]
key-files:
  created: []
  modified:
    - planner/static/planner/js/signal_flow_editor.js
key-decisions:
  - "Constants placed inside IIFE between Amp class and Graph init so they are closure-visible to plans 03/04/05/06 without becoming globals."
  - "applyBoundaryRender uses flat (0,+3) y-offset for double-line secondary polyline — acceptable for horizontal architectural boundaries; per-segment unit-normal math deferred to v2.4 (Risk #3)."
requirements-completed: [DRAW-01, DRAW-02, TXT-01, TXT-02]
duration: "5 min"
completed: "2026-05-26"
---

# Phase 12 Plan 01: Cell-Class Registration Summary

Registered two new JointJS custom element classes — `joint.shapes.showstack.BoundaryLine` (polyline, no ports, no magnets) and `joint.shapes.showstack.TextLabel` (SVG `<text>` over invisible hitArea) — plus four module-level constants (`BOUNDARY_PALETTE`, `TEXT_PALETTE`, `BOUNDARY_LINE_STYLES`, `TEXT_FONT_SIZES`) and the `applyBoundaryRender` render helper. All 122 inserted lines live inside the existing IIFE, lexically after the Amp class (L761) and before `new joint.dia.Graph(...)` (now L892) so saved diagrams with these cell types deserialize correctly per PITFALLS §1.

**Start:** 2026-05-26
**End:** 2026-05-26
**Tasks completed:** 1/1
**Files modified:** 1

## What was built

- `joint.shapes.showstack.BoundaryLine` — markup of `<g>` + 2 `<polyline>` (primary + secondary); `vertices`, `color`, `lineStyle`, `strokeWidth` property bag; `size: {0,0}` to disable JointJS layout helpers.
- `joint.shapes.showstack.TextLabel` — markup of invisible `<rect>` hitArea + SVG `<text>`; `fontSize`, `color` property bag; `FONT_STACK` (system fonts only — PNG-export font-taint safe).
- `applyBoundaryRender(cell)` — single render entry point used by future plans 03/05/06; reads `vertices`/`color`/`lineStyle` props and writes to both polylines' points/stroke/dasharray/display attrs.
- Closure-scoped constants: `BOUNDARY_PALETTE` (8 hexes), `TEXT_PALETTE` (8 + white), `BOUNDARY_LINE_STYLES` (4 keys), `TEXT_FONT_SIZES` ({small:12, medium:16, large:24}).

## Verification

All 10 acceptance-criteria greps returned the expected counts (1/1/1/1/1/1/1). Class-before-graph ordering confirmed: BoundaryLine at L784, Graph init at L892. Both classes have no `ports:` key and no `magnet` attribute on any child — preventing connector-endpoint snapping per R-05.

Browser smoke test (manual) — to be confirmed during Phase 12 UAT.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- Key file modified: `planner/static/planner/js/signal_flow_editor.js` exists with 122 new lines.
- Commit present: `feat(12-01): register BoundaryLine + TextLabel cell classes` (HEAD).
- All `<acceptance_criteria>` automated greps pass.
- `<verification>` ordering check passes.

Next: Ready for 12-02 (CSS sections 17 + 18).
