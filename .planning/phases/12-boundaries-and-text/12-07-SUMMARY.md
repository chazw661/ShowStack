---
phase: 12
plan: 07
subsystem: signal-flow-editor
tags: [draw, txt, backend, idor, regression]
requires: []
provides:
  - "_Phase12Base reusable setUp (User + Project + Console + force_login + session)"
  - "4 regression tests locking IDOR `continue` branch + canvas_state opacity"
affects: [planner/tests/test_signal_flow_phase12.py]
tech-stack:
  added: []
  patterns: ["Django TestCase + force_login + session-current-project pattern (mirrors _Phase9Base)"]
key-files:
  created:
    - planner/tests/test_signal_flow_phase12.py
  modified: []
key-decisions:
  - "Mirrors _Phase9Base setUp exactly (no Group assignment needed; project owner has full access in this app) to avoid divergent test bases across phases."
  - "Tests treat the server as opaque to canvas_state JSON — garbage colors and unknown line styles round-trip unchanged. Locks the 'client owns palette validation' contract."
requirements-completed: [DRAW-02, TXT-02]
duration: "5 min"
completed: "2026-05-26"
---

# Phase 12 Plan 07: Backend Autosave Tests Summary

Created `planner/tests/test_signal_flow_phase12.py` with `_Phase12Base` (reusable setUp mirroring `_Phase9Base`) and `SignalFlowPhase12AutosaveTests` containing 4 regression tests that lock two server-side contracts Phase 12 inherits but does not modify:

1. The IDOR allowlist at `planner/views.py:7693` passes through cells without `showstack.contentTypeId/objectId` via its `continue` statement (R-04). Without these tests, a future refactor could promote the pass-through to a strict-enum check, silently breaking BoundaryLine + TextLabel saves.
2. The server treats `canvas_state` as opaque JSON — invalid colors and unknown line styles still round-trip.

**Start:** 2026-05-26
**End:** 2026-05-26
**Tasks completed:** 1/1
**Files created:** 1
**Tests:** 4 (all pass in 0.652s)

## What was built

- `_Phase12Base.setUp`: staff User, Project owned by user, Console in project, force_login client, session `current_project_id` set.
- `_Phase12Base._post_autosave(diagram, payload, if_match=None)`: helper mirroring Phase 9's signature.
- `test_boundary_only_canvas_state_round_trips`: BoundaryLine-only canvas, asserts HTTP 200, version 1→2, full property round-trip (color, lineStyle, vertices).
- `test_text_only_canvas_state_round_trips`: TextLabel-only canvas with white text (D-19 +white palette), asserts round-trip of `attrs.label.text`, `fontSize`, `color`.
- `test_mixed_boundary_text_equipment_round_trip`: BoundaryLine + Console (with GFK) + TextLabel in one canvas; asserts all 3 round-trip and IDOR walk skips decorative cells while validating the Console GFK.
- `test_boundary_with_invalid_color_still_saves`: posts `color='not-a-real-hex'` and `lineStyle='plaid'`; asserts they round-trip unchanged — server-opacity contract.

## Verification

- `python manage.py test planner.tests.test_signal_flow_phase12 -v 2` → 4 tests pass in 0.652s.
- Cross-phase regression (`phase9 + phase10 + phase12`) → 36 tests pass in 10.559s. No regression.
- `git diff --name-only HEAD planner/views.py` returns empty — IDOR allowlist unchanged.
- No migrations created.
- No imports from `planner.views` (no `_enrich_nodes` reference per acceptance criterion).

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- Key file created: `planner/tests/test_signal_flow_phase12.py` exists (271 lines).
- Commit present: `test(12-07): add Phase 12 backend autosave round-trip tests`.
- All `<acceptance_criteria>` automated greps + test-suite execution pass.
- `<verification>` cross-phase regression passes.

Next: Wave 1 complete (12-01, 12-02, 12-07). Ready for Wave 2 (12-03 toolbar + draw-boundary mode).
