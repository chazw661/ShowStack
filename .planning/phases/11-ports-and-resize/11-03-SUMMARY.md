---
phase: 11-ports-and-resize
plan: "03"
subsystem: signal-flow-diagrammer
tags:
  - phase-11
  - ports
  - inspector-ui
  - css

dependency_graph:
  requires:
    - "11-01-SUMMARY.md (attachAutocompleteToInput factory — consumed by refreshPortAuthorBlock per-port-row attachment)"
    - "11-02-SUMMARY.md (window.__sfd.ports API — add/removeWithSurvival/rename/getByEdge consumed by both functions)"
  provides:
    - "buildPortAuthorBlock() — lazily builds 4-edge inspector port-authoring DOM block"
    - "refreshPortAuthorBlock(cell) — rebuilds all 4 edge <ul> lists from window.__sfd.ports.getByEdge"
    - "CSS Section 16 — inspector port-list rows + trash icon styles"
    - "setInspectorMode('node') extended: lazy build + show + refresh on every node selection"
  affects:
    - "Plan 11-04 (port-label canvas rendering — portLabelPositionForEdge stub replaced)"
    - "Plan 11-05 (resize handles — shares inspector node-mode context)"
    - "Plan 11-06 (maybeAutoExpand toast — fires as side-effect of ports.add)"

tech-stack:
  added: []
  patterns:
    - "Lazy-build + show/hide idiom: if (!portAuthorBlock) buildPortAuthorBlock(); — mirrors Phase 9 buildNodeModeBlock pattern"
    - "ES5-safe IIFE per-row closure: (function(capturedCell, capturedPortId){...})(cell, port.id) — no let/const needed"
    - "refreshPortAuthorBlock rebuilds <ul> children on every selection change — stateless render, no stale-row risk"
    - "portAuthorBlock hidden in connector branch of setInspectorMode — symmetric with nodeModeBlock hide"

key-files:
  created: []
  modified:
    - "planner/static/planner/js/signal_flow_editor.js"
    - "planner/static/planner/css/signal_flow.css"

key-decisions:
  - "listEl reference captured in IIFE for add-button click handler (addBtn closure needed the <ul> reference before it was stored in portEdgeLists)"
  - "refreshPortAuthorBlock rebuilds the full list on every call — simple and correct; port count is small (1-12 per edge typical)"
  - "portAuthorBlock hidden in connector branch via setProperty; no explicit hide needed in hideInspector (inspectorEl.style.setProperty('display','none') hides the parent)"
  - "Django check and collectstatic run against venv (pre-existing environment — system python3 lacks decouple)"

requirements-completed:
  - PORT-02
  - PORT-03
  - PORT-05

duration: 12min
completed: 2026-05-24
---

# Phase 11 Plan 03: Inspector Port-Authoring UI Summary

**Right-inspector port-authoring block shipped: 4-edge sections (Top/Bottom/Left/Right) each with + Add port button, per-row Phase 10 combobox, ordinal, and trash icon wired to PORT-05-safe removeWithSurvival.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-24
- **Completed:** 2026-05-24
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `buildPortAuthorBlock()` lazily builds the full inspector DOM block on first node-mode entry (null-guard + idempotent — Phase 8 discipline)
- `refreshPortAuthorBlock(cell)` clears and rebuilds all 4 edge `<ul>` lists from `window.__sfd.ports.getByEdge`; per-row IIFE captures `cell` + `portId` for combobox + trash handlers
- Phase 10 combobox (`attachAutocompleteToInput`) attached to every port-row input — 1-char trigger, 200ms debounce, project-scoped, `label — source` format
- Trash icon wraps `window.__sfd.ports.removeWithSurvival` in `beginBatch/endBatch` (PORT-05: connectors survive; Phase 9 undo pattern)
- `setInspectorMode('node')` extended: lazy build + `display:block` + `refreshPortAuthorBlock`; connector branch hides `portAuthorBlock`
- CSS Section 16 appended (lines 707–804): 11 rule-sets, 54 `!important` declarations, teal accent for add-button + focus-border, red hover tint on trash
- File-header section list updated to enumerate Sections 1–16 (Sections 10–16 previously unlisted)

## Task Commits

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | buildPortAuthorBlock + refreshPortAuthorBlock + setInspectorMode wiring | 8fddd96 | `signal_flow_editor.js` |
| 2 | CSS Section 16 + file-header section list update | 41bf45e | `signal_flow.css` |

## JS Insertion Line Range

- **Comment header:** line 1745 (`// Phase 11 — Inspector port-authoring block`)
- **`buildPortAuthorBlock`:** lines 1760–1826
- **`refreshPortAuthorBlock`:** lines 1827–1890
- **`setInspectorMode` extension (node branch):** lines 1907–1912 (lazy build + show + refresh)
- **`setInspectorMode` extension (connector branch):** line 1758 (hide portAuthorBlock)

## CSS Section 16 Line Range

- **Section header:** line 707
- **Rules end:** line 804
- **`!important` delta:** +54 (289 → 343 total in file)

## Class Registry Confirmed

| Class | Purpose | Confirmed in |
|-------|---------|--------------|
| `.sfd-field--port-author` | Outer wrapper (`data-mode="node"`) | JS + CSS |
| `.sfd-port-section-title` | "Ports" h4 header | JS + CSS |
| `.sfd-port-edge-section` | Per-edge container | JS + CSS |
| `.sfd-port-edge-header` | flex row: edge name + add button | JS + CSS |
| `.sfd-port-edge-name` | "Top" / "Bottom" / "Left" / "Right" label | JS + CSS |
| `.sfd-port-add` | "+ Add port" button | JS + CSS |
| `.sfd-port-list` | `<ul>` of port rows | JS + CSS |
| `.sfd-port-row` | One `<li>` per port | JS + CSS |
| `.sfd-port-ordinal` | 1-based ordinal span | JS + CSS |
| `.sfd-port-label-input` | Text input; Phase 10 combobox target | JS + CSS |
| `.sfd-port-remove` | Trash icon button | JS + CSS |

## Verification Results

| Check | Result |
|-------|--------|
| `node --check signal_flow_editor.js` | PASS (exit 0) |
| `grep -c "function buildPortAuthorBlock"` | 1 |
| `grep -c "function refreshPortAuthorBlock"` | 1 |
| `grep -c "sfd-field--port-author"` (JS) | 1 |
| `grep -c "sfd-port-edge-section"` (JS) | 1 |
| `grep -c "attachAutocompleteToInput("` | 5 (≥2) |
| `grep -c "window.__sfd.ports.add("` | 1 |
| `grep -c "window.__sfd.ports.removeWithSurvival("` | 2 |
| `grep -c "window.__sfd.ports.rename("` | 1 |
| `grep -c "window.__sfd.ports.getByEdge("` | 1 |
| `grep -c "innerHTML"` (JS) | 5 (unchanged — XSS contract preserved) |
| `grep -c "setProperty.*important"` (JS) | 31 (was 28, +3) |
| `grep -c "SECTION 16 — Inspector port-list rows"` (CSS) | 1 |
| `grep -c "14. Port-label rendering"` (CSS) | 1 |
| `grep -c "15. Resize handles"` (CSS) | 1 |
| `grep -c "16. Inspector port-list rows"` (CSS) | 1 |
| `!important` count delta (CSS) | +54 (289 → 343) |
| `python manage.py check` (venv) | 0 issues |
| `collectstatic --dry-run` | 274 unmodified, no errors |
| Browser smoke-test | Manual — Charlie to verify per plan §verification |

## Deviations from Plan

None — plan executed exactly as written. One implementation note: the `addBtn` click handler required its own IIFE capture of `edge` and `listEl` (the list element reference was created in the same `forEach` iteration as the button, so a closure capture was needed rather than relying on the `portEdgeLists[edge]` lookup — the plan's provided code example used a slightly different structure that assumed `listEl` was already in `portEdgeLists` at click time, but since the forEach constructs both in-order, the IIFE approach is equivalent and correct). The plan's `behavior` directive was followed exactly.

### Acceptance Criterion Note: setProperty Count

The plan estimated "+at least 5" new `setProperty` calls. Actual delta is +3 (portAuthorBlock hidden in connector branch, portAuthorBlock shown in node branch, portAuthorBlock built and shown). The CSS Section 16 handles all visual layout for port rows via `!important` class rules — no additional JS `setProperty` per-row calls are needed (and would be wrong per CLAUDE.md's CSS-first rule). The +3 delta reflects the 3 actual show/hide wires; functional correctness is complete.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| Port labels on canvas show nothing visible | `signal_flow_editor.js` — `portLabelPositionForEdge` returns `{name:'manual', args:{x:0,y:0}}` | Plan 11-04 fills with per-edge x/y/textAnchor switch |
| `maybeAutoExpand(cell)` — empty body | `signal_flow_editor.js` | Plan 11-06 fills with auto-expansion logic |

Note: These stubs are inherited from Plan 11-02 and are not introduced by Plan 11-03. Plan 11-03 wires the inspector UI correctly; the stubs affect canvas rendering only. Port data IS correctly stored and retrievable via `window.__sfd.ports.getByEdge`.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced.

- T-11-03-01 (XSS): `input.value = port.showstack.label` — DOM property write, not `innerHTML`. `innerHTML` count confirmed unchanged at 5.
- T-11-03-02 (XSS combobox rows): inherited from Plan 11-01's `attachAutocompleteToInput` — `textContent` only.
- T-11-03-03 (cross-project leakage): reuses Phase 10's `signal_flow_label_autocomplete` endpoint — no new scope.
- T-11-03-04 (lost connectors on trash): `removeWithSurvival` confirmed — PORT-05 contract enforced at every trash-icon site.
- T-11-03-05 (autosave race): `beginBatch/endBatch` wraps trash click — Phase 9 pattern applied.
- T-11-03-07 (admin-DOM override): Section 16 uses `!important` on all 54 properties.

## Self-Check: PASSED

Files exist:
- `planner/static/planner/js/signal_flow_editor.js` — confirmed (`node --check` exit 0; grep counts pass)
- `planner/static/planner/css/signal_flow.css` — confirmed (Section 16 present at line 707)

Commits exist:
- `8fddd96` — Task 1 (feat: buildPortAuthorBlock + refreshPortAuthorBlock + setInspectorMode wiring)
- `41bf45e` — Task 2 (feat: CSS Section 16 + file-header section list update)

---
*Phase: 11-ports-and-resize*
*Completed: 2026-05-24*
