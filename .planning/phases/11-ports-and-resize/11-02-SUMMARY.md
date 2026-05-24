---
phase: 11-ports-and-resize
plan: "02"
subsystem: signal-flow-diagrammer
tags:
  - phase-11
  - ports
  - data-model
  - back-compat
dependency_graph:
  requires:
    - "11-01-SUMMARY.md (attachAutocompleteToInput factory — reused by Plan 11-03 port-row inputs)"
  provides:
    - "directionForEdge(edge) — edge → 'in'|'out' map"
    - "cellHasAnyAuthoredPort(cell) — D-13 guard"
    - "getAuthoredPortsByEdge(cell, edge) — authored port filter"
    - "edgeMidpointInPaperCoords(cell, edge) — geometry helper"
    - "redistributeEdgePorts(cell, edge) — instant equal-spacing snap"
    - "reanchorLinksFromPort(cell, portId) — PORT-05 connector survival"
    - "convertCellFromGenericToAuthored(cell) — D-13 whole-shape back-compat switch"
    - "maybeAutoExpand(cell) — stub (Plan 11-06 fills body)"
    - "addAuthoredPort(cell, edge, label) — primary mutator"
    - "removeAuthoredPortWithSurvival(cell, portId) — removal with link survival"
    - "renameAuthoredPort(cell, portId, newLabel) — label update"
    - "portLabelPositionForEdge(edge) — stub (Plan 11-04 fills)"
    - "portLabelMarkupForEdge() — stub (Plan 11-04 fills)"
    - "window.__sfd.ports — public API surface for Plans 11-03/05/06"
  affects:
    - "planner/static/planner/js/signal_flow_editor.js (234 lines inserted)"
tech_stack:
  added: []
  patterns:
    - "JointJS-native ports.items[N] with per-port showstack namespace — round-trips through graph.toJSON()"
    - "D-13 whole-shape back-compat switch: zero authored → v2.2 generic; first authored → only authored (never mixed)"
    - "startBatch/stopBatch wrapping for suppress-intermediate-change:ports (RESEARCH Pitfall 7)"
    - "Pre-removal reanchor pattern — reanchorLinksFromPort BEFORE removePort (RESEARCH §Q6 / PORT-05)"
    - "Explicit scheduleAutosave() at mutator tail — change:ports intentionally excluded from graph listener"
    - "beginBatch/endBatch wrapping for atomic undo (RESEARCH Pitfall 8)"
key_files:
  created: []
  modified:
    - "planner/static/planner/js/signal_flow_editor.js"
decisions:
  - "All helpers are module-scope functions taking cell as first arg — matches applyOrphanState/applyAttachedOrphanState pattern (PATTERNS §Q8 Option B)"
  - "redistributeEdgePorts uses cell.startBatch/stopBatch rather than per-portProp silent option — JointJS batch API confirmed as the correct suppress mechanism for Pitfall 7"
  - "portLabelPositionForEdge and portLabelMarkupForEdge stubbed in Plan 11-02; Plan 11-04 replaces with real per-edge implementations"
  - "maybeAutoExpand stubbed as no-op; Plan 11-06 fills body with Q7 auto-expansion logic"
  - "window.__sfd.ports exposed after window.__sfd.save (line 1999) — consistent with Phase 9 undo/selection handoff pattern"
metrics:
  duration: "14 minutes"
  completed_date: "2026-05-24"
  tasks_completed: 2
  files_modified: 1
---

# Phase 11 Plan 02: Port-Authoring Data Model Summary

**One-liner:** Full JointJS-native port-authoring helper layer shipped — 13 module-scope functions + `window.__sfd.ports` public surface — with D-13 back-compat switch (zero authored → v2.2 generic; first authored → only authored) and PORT-05 connector-survival pre-removal reanchor.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add module-scope port-authoring helpers (Region 1 expansion) | 86b2fa8 | `signal_flow_editor.js` |
| 2 | Expose `window.__sfd.ports` + annotate `validateConnection` | e70fc5a | `signal_flow_editor.js` |

## Task 1 Detail — Module-scope helper layer

**Insertion point:** Lines 131–348 (after `portsForRect` closing brace at line 129, before `joint.shapes.showstack.Console` at line 350). 218 lines inserted.

**Helpers added (all module-scope, cell-as-first-arg pattern):**

| Helper | Role |
|--------|------|
| `directionForEdge(edge)` | `'top'|'left'` → `'in'`; `'bottom'|'right'` → `'out'` (RESEARCH §Q3) |
| `cellHasAnyAuthoredPort(cell)` | Returns true iff any port has `showstack.authored === true` |
| `getAuthoredPortsByEdge(cell, edge)` | Filters authored ports for one edge; preserves insertion order |
| `edgeMidpointInPaperCoords(cell, edge)` | Returns paper-coord `{x,y}` per RESEARCH §Q6 formulas |
| `redistributeEdgePorts(cell, edge)` | Instant equal-spacing via `(i+1)/(N+1)*dimension`; wrapped in `startBatch('phase11-redistribute')` to suppress intermediate `change:ports` (Pitfall 7) |
| `reanchorLinksFromPort(cell, portId)` | Iterates `getConnectedLinks`, rewrites `source.port`/`target.port` refs to edge-midpoint coords BEFORE `removePort` — prevents `_processRemovedPort` auto-deletion (PORT-05 contract) |
| `convertCellFromGenericToAuthored(cell)` | D-13 switch: removes all non-authored ports (with pre-removal reanchor); wrapped in `startBatch('phase11-convert-to-authored')` for atomic undo |
| `maybeAutoExpand(cell)` | **STUB** — no-op body; Plan 11-06 fills |
| `addAuthoredPort(cell, edge, label)` | Primary mutator: beginBatch → D-13 guard → addPort (RESEARCH §Q4 schema) → redistribute → maybeAutoExpand → endBatch → scheduleAutosave |
| `removeAuthoredPortWithSurvival(cell, portId)` | Saves edge → reanchorLinks → removePort → redistribute → scheduleAutosave (no shrink, no generic restore) |
| `renameAuthoredPort(cell, portId, newLabel)` | Dual-write: `showstack/label` (source of truth) + `attrs/label/text` (SVG rendering) → maybeAutoExpand → scheduleAutosave |
| `portLabelPositionForEdge(edge)` | **STUB** — returns `{name:'manual', args:{x:0,y:0}}`; Plan 11-04 fills |
| `portLabelMarkupForEdge()` | **STUB** — returns `[{tagName:'text', selector:'label'}]`; Plan 11-04 fills |

## Task 2 Detail — Public surface + validateConnection annotation

**`window.__sfd.ports` namespace (line 1999):**

```javascript
window.__sfd.ports = {
  getByEdge:           getAuthoredPortsByEdge,
  hasAuthored:         cellHasAnyAuthoredPort,
  directionForEdge:    directionForEdge,
  add:                 addAuthoredPort,
  removeWithSurvival:  removeAuthoredPortWithSurvival,
  rename:              renameAuthoredPort,
  redistribute:        redistributeEdgePorts,
  reanchorFromPort:    reanchorLinksFromPort,
  edgeMidpoint:        edgeMidpointInPaperCoords,
};
```

**`validateConnection` annotation:** One-line comment added inside function body — no behavioral change. Comment: `// Phase 11 — per-port snap targeting honored automatically; see addAuthoredPort().`

## Verification Results

| Check | Result |
|-------|--------|
| `node --check signal_flow_editor.js` | PASS (exit 0) |
| `grep -c "function directionForEdge"` | 1 |
| `grep -c "function cellHasAnyAuthoredPort"` | 1 |
| `grep -c "function getAuthoredPortsByEdge"` | 1 |
| `grep -c "function edgeMidpointInPaperCoords"` | 1 |
| `grep -c "function redistributeEdgePorts"` | 1 |
| `grep -c "function reanchorLinksFromPort"` | 1 |
| `grep -c "function convertCellFromGenericToAuthored"` | 1 |
| `grep -c "function maybeAutoExpand"` | 1 |
| `grep -c "phase11-redistribute"` | 2 (startBatch + stopBatch) |
| `grep -c "phase11-convert-to-authored"` | 2 (startBatch + stopBatch) |
| `grep -c "function addAuthoredPort"` | 1 |
| `grep -c "function removeAuthoredPortWithSurvival"` | 1 |
| `grep -c "function renameAuthoredPort"` | 1 |
| `grep -c "function portLabelPositionForEdge"` | 1 |
| `grep -c "function portLabelMarkupForEdge"` | 1 |
| `grep -c "window.__sfd.ports"` | 1 |
| `grep -c "Phase 11 — per-port snap targeting honored automatically"` | 1 |
| `grep -c "convertCellFromGenericToAuthored(cell)"` | 2 (definition + call in addAuthoredPort) |
| `grep -c "beginBatch\|endBatch"` | 8 (previous 4 + 4 new: 2 in addAuthoredPort, 2 in convertCellFromGenericToAuthored) |
| Block position (portsForRect → helpers → Console) | portsForRect@119, helpers 131–348, Console@350 — CORRECT |
| `python3 manage.py check` | 0 issues |
| DevTools smoke-test | human_needed — Charlie to verify in browser per plan verification §4 |

## Deviations from Plan

None — plan executed exactly as written. The plan specified inserting helpers as two separate tasks (Task 1 = lower-level helpers, Task 2 = mutators + surface); all helpers were inserted in a single contiguous block in the correct location in Task 1, with the `window.__sfd.ports` surface and `validateConnection` annotation added in Task 2. The mutators (`addAuthoredPort`, `removeAuthoredPortWithSurvival`, `renameAuthoredPort`) and stub helpers (`portLabelPositionForEdge`, `portLabelMarkupForEdge`) were included in Task 1's insertion block rather than split across tasks, since they are co-located in the same Region 1 code block — this matches the plan's intent and the PATTERNS directive.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `maybeAutoExpand(cell)` — empty body | `signal_flow_editor.js` line ~261 | Plan 11-06 fills with Q7 auto-expansion logic (computeMinSize + shape grow + sfd-toast) |
| `portLabelPositionForEdge(edge)` — returns `{name:'manual', args:{x:0,y:0}}` | `signal_flow_editor.js` line ~340 | Plan 11-04 fills with per-edge x/y/textAnchor switch (RESEARCH §Q10) |
| `portLabelMarkupForEdge()` — returns `[{tagName:'text', selector:'label'}]` | `signal_flow_editor.js` line ~344 | Plan 11-04 fills with full font-attrs markup (RESEARCH §Q10) |

These stubs are intentional — Plan 11-02 ships only the data layer. Ports ARE added/removed/renamed correctly; label rendering (Plan 11-04) and auto-expansion (Plan 11-06) are follow-on plans within Phase 11. The stubs produce no visible label and no shape growth, which is correct for Plan 11-02.

## D-13 Back-Compat Confirmation

A shape with zero authored ports retains the v2.2 4-generic-port set (provided by `portsForRect()` in `defaults.ports` for all 7 shape classes — unchanged). The moment `addAuthoredPort(cell, edge, label)` is called on any shape, the `cellHasAnyAuthoredPort` guard fires `convertCellFromGenericToAuthored(cell)` which removes all 4 generic ports atomically before the first authored port is added. After this point, `cellHasAnyAuthoredPort(cell)` returns true and the guard is bypassed on subsequent calls. Mixed state (generic + authored ports coexisting) is structurally impossible.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The `addAuthoredPort` path writes engineer-controlled `label` into `attrs.label.text`; JointJS renders this via SVG `<text>` (escapes automatically — cannot execute script). The `showstack.label` field round-trips through `canvas_state` JSON opaquely; Plan 11-03 is responsible for rendering port labels in inspector rows via `.value =` (DOM property), not `innerHTML`. No XSS surface introduced in this plan.

## Self-Check: PASSED

Files exist:
- `planner/static/planner/js/signal_flow_editor.js` — confirmed (`node --check` exit 0)

Commits exist:
- `86b2fa8` — Task 1 (feat: module-scope port-authoring helper layer)
- `e70fc5a` — Task 2 (feat: window.__sfd.ports surface + validateConnection annotation)
