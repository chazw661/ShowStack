---
phase: 12
plan: 06
subsystem: signal-flow-editor
tags: [draw, vertex-tool, selection, txt]
requires: ["12-01 BoundaryLine + applyBoundaryRender", "12-03 onSelectionChanged context", "12-04 TextLabel + dblclick", "12-05 setInspectorMode boundary/text branches"]
provides:
  - "BoundaryVertex joint.elementTools.Control subclass"
  - "attachBoundaryVertexTools / detachBoundaryVertexTools + _vertexAttachedCell tracker"
  - "Standalone graph.on('change:vertices', ...) listener"
  - "BoundaryLine + TextLabel branches in onSelectionChanged"
affects: [signal_flow_editor.js]
tech-stack:
  added: []
  patterns: ["joint.elementTools.Control subclass mirroring Phase 11 CornerResize", "standalone change:vertices listener (Violation 5)"]
key-files:
  created: []
  modified:
    - planner/static/planner/js/signal_flow_editor.js
key-decisions:
  - "Standalone graph.on('change:vertices', ...) listener instead of extending the line-3198 comma-list — applyBoundaryRender writes attrs that could re-fire if the listener handled the event side-effect on the same event registration (Violation 5)."
  - "BoundaryVertex.setPosition does NOT call applyBoundaryRender directly — that's owned by the change:vertices listener. Avoids double-render under fast drag."
  - "onSelectionChanged places boundary + text branches BEFORE the generic isLink/isElement branches so type-specific behavior takes precedence; the existing branches detach _vertexAttachedCell on entry to prevent stale handles."
requirements-completed: [DRAW-04, TXT-03]
duration: "8 min"
completed: "2026-05-26"
---

# Phase 12 Plan 06: Vertex Tools + Selection Wiring Summary

Final Phase 12 plan — wires the vertex-edit handle tool and the selection-driven inspector + tool installation. Plus the standalone change:vertices listener that closes the autosave loop for vertex drags. Plan 04's text-dblclick path was already in place; Plan 06 adds the click-to-select path that opens the text inspector. Delete/Backspace is inherited from the existing handler without modification.

**Start:** 2026-05-26
**End:** 2026-05-26
**Tasks completed:** 2/2
**Files modified:** 1 (+137 lines)

## What was built

**BoundaryVertex + attach/detach (Task 1 EDIT 1):**
- `var BoundaryVertex = joint.elementTools.Control.extend({...})` with `vertexIndex` option.
- Two children: visible 6px teal `#0d9488` circle + transparent 12px hit-area circle.
- `getPosition(view)` reads `view.model.prop('vertices')[this.options.vertexIndex]`.
- `setPosition(view, coords)` takes a `.slice()` copy (Violation 7), snaps to 20px when `window.__sfd.viewport.snapEnabled`, writes back via `cell.prop('vertices', verts)`. Does NOT call applyBoundaryRender here — the listener owns it.
- `attachBoundaryVertexTools(cell)` — null-guards + type-checks + `view.removeTools()` + creates ToolsView with one BoundaryVertex per vertex; sets `_vertexAttachedCell = cell`.
- `detachBoundaryVertexTools(cell)` — inverse.

**Standalone change:vertices listener (Task 1 EDIT 2):**
- `graph.on('change:vertices', function (cell) { ... })` added immediately after the existing autosave listener at L3198. Type-guards on `showstack.BoundaryLine`, then `applyBoundaryRender(cell)` → `view.updateTools()` → `scheduleAutosave()`. Violation 5 honored — NOT added to the comma-list.

**onSelectionChanged extension (Task 2 EDIT 1 + EDIT 2):**
- New BoundaryLine branch (placed BEFORE isLink/isElement) — detaches stale resize/vertex tools, calls `setInspectorMode('boundary', cell)`, `showInspector()`, `attachBoundaryVertexTools(cell)`, returns.
- New TextLabel branch — symmetric, no vertex tools (TextLabel uses JointJS native drag).
- Existing isLink branch — added vertex-tool detach so prior boundary handles don't linger when selecting a connector.
- Existing isElement branch — same vertex-tool detach.
- Trailing `hideInspector()` block — detaches vertex tools on multi-select / empty-select.

## Verification

All acceptance criteria pass:
- `var BoundaryVertex = joint.elementTools.Control.extend(`: 1
- `function attachBoundaryVertexTools`: 1
- `function detachBoundaryVertexTools`: 1
- `var _vertexAttachedCell = null`: 1
- `graph.on('change:vertices'` — listener registration: 1 (plus 2 comment references)
- Violation 5 negative: `graph.on('add remove change:source change:target change:size change:vertices'` count = 0
- Violation 7: `(model.prop('vertices') || []).slice()` count = 1
- WARNING 4: `window.__sfd.viewport.snapEnabled` total = 6 across the file (≥4 required for Phase 12)
- `setInspectorMode('boundary', cell)` / `setInspectorMode('text', cell)` each = 1
- `attachBoundaryVertexTools(cell)` = 2 (definition + call)
- `detachBoundaryVertexTools(_vertexAttachedCell)` = 5 (multiple call sites for clean transitions)
- BoundaryLine type-checks: 3 (attach guard with !==, onSelectionChanged with ===, change:vertices listener with !==)
- TextLabel type-checks: 2 (Plan 04 dblclick + Plan 06 onSelectionChanged)
- `node -c` syntax check clean.
- Cross-phase regression (Phases 9 + 10 + 12, 36 tests) all pass in 10.54s.

Browser UAT to be confirmed during Phase 12 manual testing pass.

## Deviations from Plan

**[Rule 1 — `graph.on('change:vertices'` grep count]** Acceptance criterion expected `grep -c "graph.on('change:vertices'"` to return exactly 1. Actual: 3 (one listener registration + two comment references — one carried over from Plan 01 documenting future call sites, one in this plan's listener comment block). Functional intent satisfied: exactly one listener registration. Comment references do not affect behavior.

**Total deviations:** 1 documentation-only (Rule 1 — comment hits in literal grep). **Impact:** none.

## Self-Check: PASSED

- Key file modified: `planner/static/planner/js/signal_flow_editor.js` +137 lines.
- Commit present: `feat(12-06): vertex-edit tools + selection wiring`.
- All `<acceptance_criteria>` automated checks pass.
- Violation 5 + Violation 7 negative checks pass.
- WARNING 4 standardized snap source-of-truth confirmed (4 Phase 12 snap sites use the same expression).
- `node -c` syntax check clean.
- Cross-phase backend regression clean.

**Phase 12 implementation complete.** All 7 plans across 5 waves shipped. Ready for verifier pass + browser UAT.
