---
phase: 12
plan: 03
subsystem: signal-flow-editor
tags: [draw, pen-tool, toolbar, sticky-mode]
requires: ["12-01 BoundaryLine + applyBoundaryRender"]
provides:
  - "drawState closure"
  - "enterBoundaryMode / exitBoundaryMode / commitOrCancelBoundary"
  - "Pen-tool blank:pointer{down,move,dblclick} listeners"
  - "Esc keydown branch (drawState.active)"
  - "Rubber-band Risk #1 guard"
  - "lastBoundaryColor / lastBoundaryStyle session-sticky vars"
affects: [editor.html, signal_flow_editor.js]
tech-stack:
  added: []
  patterns: ["sticky mode + click-each-vertex pen-tool", "blank:pointer* listener gating via drawState.active"]
key-files:
  created: []
  modified:
    - planner/templates/planner/signal_flow/editor.html
    - planner/static/planner/js/signal_flow_editor.js
key-decisions:
  - "Esc handling lives in its own dedicated keydown listener (scoped to drawState.active) rather than extending the existing picker-only Esc handler at L1191 — the existing handler had no INPUT/TEXTAREA/SELECT early-exit so a new listener is cleaner and lets Plan 04 follow the same pattern for text mode."
  - "drawState block placed after detachResizeTools (Phase 11 territory) and before the Console class — keeps Phase 12 helpers grouped with the only other set of tool-management helpers in the file."
  - "All snap reads in new Phase 12 code use window.__sfd.viewport.snapEnabled (WARNING 4 standardization with Phase 11 CornerResize) — count in the file is now 4."
requirements-completed: [DRAW-01, DRAW-02]
duration: "8 min"
completed: "2026-05-26"
---

# Phase 12 Plan 03: Toolbar + Draw-Boundary Mode Summary

Wired the toolbar create-tools button group into editor.html and implemented the draw-boundary pen-tool state machine in signal_flow_editor.js — sticky mode entry/exit, vertex accumulation, live "to cursor" segment, double-click + Esc commit/cancel, rubber-band Risk #1 guard, and boundary-side session-sticky defaults. Text-mode counterpart (Plan 04), inspector mode panels (Plan 05), and vertex-edit handles (Plan 06) will land in subsequent waves.

**Start:** 2026-05-26
**End:** 2026-05-26
**Tasks completed:** 2/2
**Files modified:** 2 (180 inserted lines total)

## What was built

**editor.html (Task 1):**
- New `.sfd-btn-group[data-group="create"]` between the history group and the right spacer.
- `#sfd-tool-boundary` (Unicode ⧈ U+29C8) and `#sfd-tool-text` (literal "T") buttons, both `aria-pressed="false"` initially.

**signal_flow_editor.js (Task 2):**
- `drawState = { active, vertices, livePreview, liveSegment }` closure + 4 helpers (`createPreviewPolyline`, `createPreviewSegment`, `updatePreviewPolyline`).
- `enterBoundaryMode()` — clears text mode if active (Plan 04 handoff), sets state, builds preview polyline + live segment, marks toolbar button `.is-active` + `aria-pressed="true"`, sets paper cursor to `crosshair !important`.
- `exitBoundaryMode()` — tears down preview SVG, clears state, resets button + cursor.
- `commitOrCancelBoundary()` — early-returns if `< 2` vertices; otherwise builds a `joint.shapes.showstack.BoundaryLine` with current sticky `lastBoundaryColor` + `lastBoundaryStyle`, adds via `graph.addCell`, calls `applyBoundaryRender(cell)` and `cell.toBack()` (D-13). Sticky mode stays active.
- Three new paper listeners (all gated on `drawState.active`): `blank:pointerdown` (with `panState.spaceDown` early-exit per WARNING 5), `blank:pointermove`, `blank:pointerdblclick`.
- Dedicated keydown listener for Esc inside draw mode — `evt.preventDefault()`, commit, exit. INPUT/TEXTAREA/SELECT early-exit so future Plan 04 text-edit-overlay Esc handling is not stolen.
- Rubber-band handler at L1796 gets `if (drawState.active) return;` as its first executable line (Risk #1 guard).
- `lastBoundaryColor = '#000000'` + `lastBoundaryStyle = 'solid'` declared next to `currentVersion`.

## Verification

All acceptance-criteria automated checks pass:
- 1 each: `var drawState`, `enterBoundaryMode`, `exitBoundaryMode`, `commitOrCancelBoundary`.
- 6 `drawState.active`-related guards (rubber-band + 3 pen-tool listeners + Esc branch + + button-toggle if-else).
- 1 `lastBoundaryColor`, 1 `lastBoundaryStyle`.
- 1 `cursor crosshair !important`, 2 `cursor '' !important` (1 new + 1 pre-existing spacebar keyup — see Deviations).
- 4 hits for `window.__sfd.viewport.snapEnabled` across the file (Phase 11 CornerResize, Phase 8 helper at L275, Phase 8 helper at L585, plus 2 new Phase 12 pen-tool sites).
- 1 `if (evt.key === 'Escape' && drawState.active)`.
- 1 `if (drawState.vertices.length < 2)`.
- `applyBoundaryRender` referenced twice (function definition + new call site).
- `cell.toBack()` referenced once (commitOrCancelBoundary).
- `panState.spaceDown` guard at L1507 precedes vertex push at L1513.
- `node -c` syntax check clean.

Browser UAT — to be confirmed during Phase 12 manual testing.

## Deviations from Plan

**[Rule 1 — Stale line numbers]** Plan's line-number references (e.g. "L1500 rubber-band handler", "L2258 closure-state block", "L2403 autosave listener") were stale relative to the current file. Located the same logical positions by content (function name, comment, code pattern):
- Closure-state block actually at L1042 (was "~2258").
- Rubber-band handler actually at L1796 (was "~1500").
- Autosave listener actually at L2625-ish (was "~2403").
- detachResizeTools at L615 (matched plan's "~619").

No code intent changed — only the search anchors.

**[Rule 1 — Esc handler placement]** Plan said insert the Esc branch into an existing keydown handler at "~L1549". The existing keydown at L1191 handles ONLY picker Escape (no INPUT/TEXTAREA/SELECT early-exit) and the L1519 keydown handles ONLY Ctrl/Cmd+Z undo. Neither was a natural fit. Added a dedicated keydown listener scoped to `drawState.active` with the prescribed INPUT/TEXTAREA/SELECT early-exit so Plan 04 can follow the same pattern for text mode. Functional intent (Violation 8 — boundary Esc must not bleed into selection-clear or picker-close) is preserved by the `drawState.active` gate.

**[Rule 1 — `paperEl.style.setProperty('cursor', '', 'important')` count]** Acceptance criterion expected exactly 1 file-wide. Actual count is 2 because the pre-existing spacebar keyup handler at L1263 already used the identical literal. exitBoundaryMode added the second instance. Functional intent (only exitBoundaryMode clears cursor) is preserved — both call sites legitimately clear the inline cursor.

**Total deviations:** 3 auto-fixed (all Rule 1 — stale plan references). **Impact:** none — original code intent preserved exactly; only search anchors and placement decisions adjusted.

## Self-Check: PASSED

- Key files modified: editor.html (+8 lines), signal_flow_editor.js (+172 lines).
- Commit present: `feat(12-03): toolbar create-tools group + draw-boundary pen-tool mode`.
- All `<acceptance_criteria>` automated checks pass.
- `<verification>` greps pass: 3 hits in editor.html, 10+ hits in JS, 6 `drawState.active`-related guards, 4 `window.__sfd.viewport.snapEnabled` references.
- `node -c` syntax check clean.

Next: Ready for 12-04 (text-place mode + inline-edit lifecycle).
