---
phase: 09-autosave-orphan-rendering
plan: "04"
subsystem: signal-flow-diagrammer
tags: [javascript, orphan-render, inspector, re-link, jointjs, autosave]

dependency_graph:
  requires:
    - "09-01: _enrich_nodes writes data.isOrphan + data.label per cell on GET"
    - "09-02: CSS Section 11 — [joint-orphan='true'] + [joint-orphan-attached='true'] selectors"
    - "09-03: conflicted, scheduleAutosave, currentVersion seams in IIFE"
  provides:
    - "applyOrphanState(cell): reads showstack.isOrphan prop, toggles joint-orphan attr on cell view"
    - "applyAttachedOrphanState(link): toggles joint-orphan-attached attr on link when endpoint is orphan"
    - "graph.on('change:showstack'): live re-evaluation on re-link or server enrich"
    - "setInspectorMode('node' | 'connector', cell): dual-mode inspector routing"
    - "buildNodeModeBlock(): lazy Re-link + Delete button construction in #sfd-inspector"
    - "assignPickerResult Phase 9 tail: isOrphan=false + applyOrphanState + scheduleAutosave"
  affects:
    - "Phase 10 (PNG export, autocomplete) — inspector DOM is extended; node-mode block coexists"

tech_stack:
  added: []
  patterns:
    - "Deferred setAttribute: setTimeout(fn, 0) so paper.findViewByModel() resolves after fromJSON add event"
    - "graph.getConnectedLinks(cell): re-evaluates attached links when endpoint orphan state changes"
    - "Lazy DOM construction: buildNodeModeBlock() called once on first node selection, cached in closure"
    - "setProperty(..., 'important') on inspector buttons per CLAUDE.md admin CSS override rule"

key_files:
  created: []
  modified:
    - planner/static/planner/js/signal_flow_editor.js

decisions:
  - "Deferred applyOrphanState via setTimeout(0) rather than paper.on('render:done') — simpler, matches Phase 8 link add-handler deferral pattern already in the file"
  - "Node-mode UI built dynamically by JS (not in editor.html) — keeps template unchanged per plan D-16 constraint; cached on first call"
  - "Re-link button hidden when cell has no contentTypeId (Generic shape) — Delete still shown for cleanup"
  - "Three separate graph.on('add') handlers coexist — JointJS event emitter supports multiple listeners; Phase 8 link-style handler stays untouched"

metrics:
  duration: "~40 min"
  completed: "2026-05-21"
  tasks_completed: 2
  tasks_total: 3
  files_modified: 1

checkpoint_status: "Task 3 (human-verify) — APPROVED 2026-05-22 by Charlie; all 5 success criteria pass in browser"
---

# Phase 09 Plan 04: Orphan Render Hook + Node-Mode Inspector Summary

**Orphan ghost rendering wired client-side via `applyOrphanState` / `applyAttachedOrphanState` DOM attribute hooks; inspector extended to node-mode with Re-link + Delete buttons routed through the existing Phase 8 equipment picker seam**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-05-21
- **Tasks:** 3 of 3 (Task 3 human-verify approved by Charlie 2026-05-22)
- **Files modified:** 1 (planner/static/planner/js/signal_flow_editor.js)

## Accomplishments

### Task 1 — Orphan ghost render hook (commit f3f3183)

- Added `applyOrphanState(cell)`: reads `cell.prop('showstack/isOrphan')`, sets `joint-orphan="true"` or removes the attribute on the cell view's root `<g>` — Section 11 CSS does the visual work
- Added `isCellOrphan(cell)`: helper for endpoint orphan check
- Added `applyAttachedOrphanState(link)`: checks source + target elements, sets/removes `joint-orphan-attached="true"` on link view root `<g>`
- Deferred variants (`applyOrphanStateDeferred`, `applyAttachedOrphanStateDeferred`) use `setTimeout(0)` so `paper.findViewByModel()` resolves after `fromJSON` fires the `add` event before views are rendered
- New `graph.on('add')` handler: routes elements to orphan hook, links to attached-orphan hook (does NOT replace the Phase 8 link-style handler — JointJS supports multiple listeners)
- `graph.on('change:showstack')`: re-evaluates the element AND all connected links when the orphan prop changes (re-link clears, future server enrich updates)
- `graph.on('change:source change:target')`: re-evaluates link attached-orphan attribute on endpoint swap
- `assignPickerResult` Phase 9 tail: writes `showstack/isOrphan = false`, calls `applyOrphanState(node)` to clear the ghost immediately, re-evaluates connected links, calls `scheduleAutosave()` — total `scheduleAutosave` call sites now 6 (exceeds the >= 6 requirement)

### Task 2 — Node-mode inspector + Re-link/Delete UI (commit e1042c1)

- `buildNodeModeBlock()`: lazily builds a `div.sfd-field.sfd-field--node-actions` with `#sfd-node-relink` (Re-link equipment) and `#sfd-node-delete` (Delete shape) buttons, appended to `#sfd-inspector` on first node selection
- `setInspectorMode('connector' | 'node', cell)`: routes the inspector between the Phase 8 connector fields (shown) and the Phase 9 node block (shown), hiding the other; updates inspector header text to "Connector" or "Node"
- Re-link button handler: extracts `shapeType` from `cell.get('type').split('.').pop()`, calls `window.__sfd.openEquipmentPicker(shapeType, inspectorCurrentNode)` — the existing Phase 8 seam
- Delete button handler: wraps `cell.remove()` in `window.__sfd.undo.beginBatch()` / `endBatch()` for Ctrl+Z support; clears selection; hides inspector
- Re-link button hidden when cell has no `contentTypeId` (Generic shape — nothing to re-link to)
- `hideInspector()` extended to also null `inspectorCurrentNode`
- `window.__sfd.onSelectionChanged` widened: single link → `setInspectorMode('connector')`, single element → `setInspectorMode('node')`, all other cases → `hideInspector()`

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | applyOrphanState + graph.on change:showstack + assignPickerResult Phase 9 tail | f3f3183 | planner/static/planner/js/signal_flow_editor.js |
| 2 | setInspectorMode + buildNodeModeBlock + Re-link/Delete UI | e1042c1 | planner/static/planner/js/signal_flow_editor.js |
| 3 | Human verification (checkpoint) | APPROVED 2026-05-22 | — |

## Deviations from Plan

None within the Phase 9 JS scope — plan executed exactly as written. All verbatim function bodies and literal strings from the plan spec were used without modification. Both `node -e` verification scripts pass. `node --check` confirms valid JS parse.

**Adjacent template fix (post-UAT, off-plan)**

During the human verification step, Charlie spotted stray Django template comment text leaking onto the rendered editor page. Root cause: multi-line `{# … #}` comments — Django's `{# #}` syntax is single-line only, so the comment body rendered as literal text. The Phase 9 conflict banner comment (introduced by 09-02) and the pre-existing equipment picker file-header comment were both affected.

Fixed in commit `52fbc86` (signal_flow templates) and `6259eec` (mobile components, same class of bug found project-wide). Both rewrites use `{% comment %}…{% endcomment %}` blocks. Pure cosmetic — no behavior change.

## Threat Surface Scan

No new network endpoints. The Re-link button routes through `window.__sfd.openEquipmentPicker` (existing Phase 8 seam) which calls the project-scoped autocomplete endpoint — T-09-21 mitigation intact. The Delete button only removes cells loaded from the project-scoped `signal_flow_state` GET — T-09-19 mitigation intact. The `isOrphan` prop cleared in `assignPickerResult` before calling `scheduleAutosave` — autosave POST IDOR walk (09-01) still validates every (ct_id, obj_id) pair — T-09-18 mitigation intact.

## Known Stubs

None. All functionality fully implemented. Ghost rendering, Re-link, and Delete are wired end-to-end.

## Checkpoint Resolved

Task 3 (`checkpoint:human-verify`) **APPROVED 2026-05-22 by Charlie**. All five Phase 9 success criteria pass in browser:

- ✅ SC-1: Autosave + three-state indicator
- ✅ SC-2: 409 banner with locked copy + canvas lock
- ✅ SC-3: Keepalive flush on pagehide + visibilitychange
- ✅ SC-4: Label propagation on reload
- ✅ SC-5: Ghost rendering + Re-link + Delete

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| signal_flow_editor.js exists | FOUND |
| function applyOrphanState | FOUND |
| function applyAttachedOrphanState | FOUND |
| function isCellOrphan | FOUND |
| graph.on('change:showstack') | FOUND |
| function setInspectorMode | FOUND |
| function buildNodeModeBlock | FOUND |
| sfd-node-relink (button id) | FOUND |
| sfd-node-delete (button id) | FOUND |
| Re-link equipment (button label) | FOUND |
| Delete shape (button label) | FOUND |
| node.prop('showstack/isOrphan', false) in assignPickerResult | FOUND |
| scheduleAutosave() in assignPickerResult | FOUND |
| graph.getConnectedLinks(node).forEach(applyAttachedOrphanState) | FOUND |
| JS parse (node --check) | PASSED |
| Task 1 literal verify (node -e) | OK |
| Task 2 literal verify (node -e) | OK |
| Commit f3f3183 | FOUND |
| Commit e1042c1 | FOUND |
