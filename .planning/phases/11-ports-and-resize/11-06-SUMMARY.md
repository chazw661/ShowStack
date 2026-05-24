---
phase: 11-ports-and-resize
plan: "06"
subsystem: signal-flow-diagrammer
tags:
  - phase-11
  - ports
  - auto-expand
  - toast

dependency_graph:
  requires:
    - "11-02-SUMMARY.md (addAuthoredPort + renameAuthoredPort call sites — already wired by stub)"
    - "11-05-SUMMARY.md (computeMinSize helper + change:size listeners + window.__sfd.resize)"
  provides:
    - "maybeAutoExpand(cell) — Q7 real implementation replacing Plan 11-02 stub"
    - "PORT-06 closure — shape auto-expands when port-add/rename pushes above current size"
  affects:
    - "addAuthoredPort (Plan 11-02) — called at tail of beginBatch wrap; now triggers real expansion"
    - "renameAuthoredPort (Plan 11-02) — called after label dual-write; now triggers real expansion"

tech_stack:
  added: []
  patterns:
    - "Math.ceil snap-to-grid (NEVER Math.round) — ensures snap rounding never shrinks below min (Pitfall 4)"
    - "change:size event chain: cell.resize() → Plan 11-05 listeners → scheduleAutosave + redistributeEdgePorts"
    - "Toast-only-on-grow pattern: grew boolean gates showToast; silent no-op when add/rename fits"
    - "Defensive null-check on window.__sfd.viewport for snap state — safe in test harness"

key_files:
  created: []
  modified:
    - "planner/static/planner/js/signal_flow_editor.js"

decisions:
  - "No scheduleAutosave() call inside maybeAutoExpand — Plan 11-05 change:size listener handles it; direct call would only reset the same debounce timer (harmless but noisy); cleaner to rely on the listener"
  - "No cell.position() call — JointJS anchors top-left when only resize() is called; grows toward right and bottom as per RESEARCH §Q7"
  - "Defensive null-check `window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled` — matches CornerResize.setPosition pattern from Plan 11-05 (consistent guard style)"

metrics:
  duration: "8 minutes"
  completed_date: "2026-05-24"
  tasks_completed: 1
  files_modified: 1
---

# Phase 11 Plan 06: maybeAutoExpand — PORT-06 Auto-Expansion Summary

**One-liner:** Replaced Plan 11-02's no-op `maybeAutoExpand` stub with the RESEARCH §Q7 implementation — shape grows toward right/bottom when port-add or label-rename pushes `computeMinSize` above current size, with Math.ceil snap-grid rounding and a single toast notification.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Replace maybeAutoExpand stub body with Q7 auto-expansion | d9c0409 | `signal_flow_editor.js` |

## Task 1 Detail — Stub replacement

**Edit location:** Lines 258–287 (replacing lines 258–263 stub — net +24 lines)

**Before (stub):**
```javascript
// Stub — Plan 11-06 replaces this body with the Q7 auto-expansion logic
// (compute min-size from live port set + label widths, grow shape if needed,
// fire .sfd-toast "Shape resized to fit ports").
function maybeAutoExpand(cell) {
  // Phase 11 Plan 11-06 fills in.
}
```

**After (real implementation):**
```javascript
// Phase 11 Plan 11-06 — PORT-06 auto-expansion on port-add / label-rename overflow.
function maybeAutoExpand(cell) {
  var current = cell.size();
  var min = computeMinSize(cell);
  var grew = false;
  var newW = current.width, newH = current.height;
  if (min.width  > current.width)  { newW = min.width;  grew = true; }
  if (min.height > current.height) { newH = min.height; grew = true; }
  if (!grew) return;   // silent no-op

  var snap = window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled;
  if (snap) {
    newW = Math.ceil(newW / 20) * 20;
    newH = Math.ceil(newH / 20) * 20;
  }

  cell.resize(newW, newH);
  showToast('Shape resized to fit ports.', 'info');
}
```

**computeMinSize source order:** Defined at line 428 (after maybeAutoExpand at line 263). Both are `function` declarations — JavaScript hoisting resolves `computeMinSize` at call time regardless of text order. Call sites are invoked at runtime (not at parse time), so no forward-reference issue exists.

**No scheduleAutosave double-fire:** Code review confirms zero `scheduleAutosave()` calls inside `maybeAutoExpand`. The `cell.resize(newW, newH)` fires `change:size`, which Plan 11-05's listener handles (autosave + live-redistribute). Threat T-11-06-04 mitigated.

**No shrink path:** Code review confirms only `>` comparisons — `newW`/`newH` are initialized to current dimensions and can only increase. No `Math.min` or conditional shrink. Threat T-11-06-05 mitigated.

## Verification Results

| Check | Result |
|-------|--------|
| `node --check signal_flow_editor.js` | PASS (exit 0) |
| `grep -c "Phase 11 Plan 11-06 fills in"` | 0 (stub comment removed) |
| `grep -c "Shape resized to fit ports."` | 1 |
| `grep -c "Math.ceil"` | 4 (2 new in maybeAutoExpand snap block + 1 FONT_LINE_HEIGHT + 1 comment) |
| `grep -c "showToast('Shape resized"` | 1 |
| `grep -c "cell.resize(newW, newH)"` | 1 (maybeAutoExpand; CornerResize uses different var names) |
| `grep -c "computeMinSize(cell)"` | 2 (CornerResize.setPosition + maybeAutoExpand) |
| `python manage.py check` (via venv) | 0 issues |
| No scheduleAutosave inside maybeAutoExpand | CONFIRMED — code review |
| No shrink path inside maybeAutoExpand | CONFIRMED — code review |
| No cell.position() call | CONFIRMED — code review |
| Post-commit deletions check | NO UNEXPECTED DELETIONS |

## Threat Model Verification

| Threat | Disposition | Verification |
|--------|-------------|-------------|
| T-11-06-01 — Toast XSS | accept | `showToast` uses `t.textContent` (line 80); static string literal flows in — no engineer input rendered |
| T-11-06-02 — Toast spam on rapid port adds | accept | Each call fires at most one toast; most rapid adds won't push above already-grown size |
| T-11-06-03 — Auto-expand bypass via direct POST | accept | Client-side only; purely visual impact; documented as accept in plan threat register |
| T-11-06-04 — double-fire scheduleAutosave | mitigate | CONFIRMED: zero scheduleAutosave() calls in maybeAutoExpand body |
| T-11-06-05 — auto-shrink data loss | mitigate | CONFIRMED: only > comparisons; newW/newH can only increase from current.width/height |

## UAT Cases (PORT-06) — Awaiting Charlie Browser Verification

The following manual checks must be performed in-browser after this wave merges to main:

**PORT-06.1:** Console (180×60 default) → add 10 short-labeled ports to Top edge → shape width grows to fit; toast "Shape resized to fit ports." appears.

**PORT-06.2:** Toast dismisses automatically (Phase 9 timing: hide at 3000ms, remove at 3500ms).

**PORT-06.3:** Add a port with very long label to Left edge → shape grows to accommodate label width; toast fires.

**PORT-06.4:** Rename existing port to a longer string → shape grows; toast fires.

**PORT-06.5:** Remove a port → shape does NOT shrink (RESEARCH §Q5 — only manual resize shrinks).

**PORT-06.6:** Shape top-left corner unchanged after auto-expand (shape grows toward right/bottom).

**PORT-06.7:** Ctrl+Z undoes both port-add AND auto-grow as a single gesture (Plan 11-02 beginBatch/endBatch wrap in addAuthoredPort).

**Cross-check A:** Add a port that fits within current shape size (one port on 180×60 Console) → NO toast, shape stays at 180×60.

**Cross-check B:** snap-grid OFF → auto-grow lands at exact min-size; snap-grid ON → grows to next 20px multiple (Math.ceil).

**Cross-check C:** Reload after auto-expand → grown dimensions persisted (change:size → autosave via Plan 11-05 listener).

## Phase 11 Final Cross-Cutting Regression Smoke

The following prior-phase behaviors must be confirmed preserved during full-phase UAT:

| Behavior | Source | Expected |
|----------|--------|---------|
| Shapes with zero authored ports get 4 generic ports + snap connectors | Phase 8/9 D-13 back-compat | Still true — zero-authored shapes not touched by this plan |
| Connector circuit-label autocomplete | Phase 10 LBL-01..03 | Unchanged — this plan modifies only maybeAutoExpand |
| PNG export without font-taint | Phase 10 EXP-01 | Unchanged |
| 409 conflict banner on stale tab edits | Phase 9 D-07 | Unchanged |
| Orphan ghost rendering for shapes with deleted equipment | Phase 9 SHP-07 | Unchanged |

## v2.4+ Backlog Ideas (Observed During Analysis)

- **Per-corner resize cursors:** Current CornerResize uses uniform `nwse-resize` cursor. Per-corner cursors (nw/ne/sw/se) deferred per Plan 11-05 decision.
- **Canvas hover ✕ for port removal:** Currently ports are removed via inspector list; hover-to-remove on shape canvas would improve flow for mouse-heavy workflows. v2.4+ candidate.
- **Per-port direction picker:** Current `directionForEdge` maps edge → in/out automatically. Manual override per-port would allow non-standard signal flow diagrams. v2.4+ candidate.
- **Smart alignment guides on auto-expand:** When auto-expand overlaps adjacent shape, engineer must drag manually. Snap-to-guide on expansion is a v2.4+ alignment feature (noted in RESEARCH §Q7 and CONTEXT.md).

## Phase 11 Final Status

All 9 REQ-IDs are addressed across the 6 plans:

| REQ-ID | Plan | Status |
|--------|------|--------|
| PORT-01 | 11-02 | Shipped — addAuthoredPort + D-13 back-compat switch |
| PORT-02 | 11-02 | Shipped — removeAuthoredPortWithSurvival + PORT-05 connector survival |
| PORT-03 | 11-02 | Shipped — renameAuthoredPort + dual-write label |
| PORT-04 | 11-03 | Shipped — inspector port-list UI + add/rename/remove controls |
| PORT-05 | 11-02 | Shipped — reanchorLinksFromPort pre-removal reanchor |
| PORT-06 | 11-06 | Shipped — maybeAutoExpand Q7 implementation (this plan) |
| SHP-RESIZE-01 | 11-05 | Shipped — CornerResize 4-handle tool on all 7 shape types |
| SHP-RESIZE-02 | 11-05 | Shipped — computeMinSize ABSOLUTE_FLOORS + port-count clamp |
| SHP-RESIZE-03 | 11-05 | Shipped — change:size autosave + live-redistribute listeners |

Phase 11 is ready for `/gsd-verify-phase 11`.

## Deviations from Plan

None — plan executed exactly as written. The stub body was replaced verbatim with the RESEARCH §Q7 Example 4 implementation, including the defensive null-check on `window.__sfd.viewport` noted in the task behavior specification.

## Known Stubs

None — this plan closes the last stub in Phase 11. All previously-noted stubs from Plans 11-02 and 11-05 have been filled:
- `portLabelPositionForEdge` — filled by Plan 11-04
- `portLabelMarkupForEdge` — filled by Plan 11-04
- `maybeAutoExpand` — filled by this plan (11-06)

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

Files exist:
- `planner/static/planner/js/signal_flow_editor.js` — confirmed (`node --check` exit 0)

Commits exist:
- `d9c0409` — Task 1 (feat: replace maybeAutoExpand stub with Q7 auto-expansion — PORT-06)
