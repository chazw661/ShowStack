---
phase: 09-autosave-orphan-rendering
plan: 01
subsystem: api
tags: [django, signal-flow, optimistic-locking, content-types, autosave, orphan-detection]

# Dependency graph
requires:
  - phase: 08-canvas-smart-shapes-connectors
    provides: SignalFlowDiagram model + signal_flow_autosave view stub + IDOR walk + signal_flow_state GET stub
  - phase: 07-foundation-crud-editor-shell
    provides: SignalFlowDiagram.version IntegerField (migration 0158) + _get_diagram_for_request helper
provides:
  - _enrich_nodes(canvas_state, project) helper in planner/views.py — bulk-SELECT per ContentType, orphan flagging, deep-copy guarantee
  - signal_flow_state GET returns enriched canvas_state (live label + isOrphan flag per cell)
  - signal_flow_autosave reads If-Match header + atomic version-pinned UPDATE (409 on missing/stale, 200 on match)
  - planner/tests/test_signal_flow_phase9.py — 12 tests locking DGM-07, SHP-06, SHP-07 server contracts
affects:
  - 09-02 (autosave debounce JS — consumes the If-Match 409 contract)
  - 09-03 (orphan ghost render JS — consumes isOrphan flag from enriched GET)
  - 09-04 (keepalive flush — mirrors autosave path with keepalive:true)
  - 10-autocomplete-png-export (may extend signal_flow_state or add new GET endpoint)

# Tech tracking
tech-stack:
  added:
    - django.db.models.F (first use in signal_flow block — version=F('version')+1)
    - django.utils.timezone (timezone.now() on updated_at in atomic UPDATE)
    - copy.deepcopy (stdlib, local import inside _enrich_nodes)
  patterns:
    - Optimistic-lock via filter(id=..., version=loaded_version).update(...) — cheaper than select_for_update; rowcount==0 → 409
    - _enrich_nodes() bulk-fetch pattern: one SELECT per ContentType, (ct_id, obj_id) dict, second-pass mutation on deep copy
    - If-Match header read: request.headers.get('If-Match', '').strip(); missing/non-int → 409 version_required
    - SpeakerArray IDOR scope via prediction__project (no direct project FK) — mirrored from existing IDOR walk

key-files:
  created:
    - planner/tests/test_signal_flow_phase9.py
  modified:
    - planner/views.py

key-decisions:
  - "Atomic UPDATE (filter+update) chosen over select_for_update() — single DB round-trip; rowcount==0 is the conflict signal (D-06)"
  - "If-Match header NOT read on viewport-only (?viewport_only=1) path — those writes remain last-write-wins (D-05)"
  - "_enrich_nodes() deep-copies input blob; persisted canvas_state is never mutated by the GET path (D-12)"
  - "One SELECT per ContentType in _enrich_nodes() regardless of cell count — O(CT) queries, not O(cells) (D-13)"
  - "Unknown ContentType silently treated as orphan in _enrich_nodes() — never raises; autosave IDOR walk still returns 422 on unknown CT (asymmetry by design)"
  - "F and timezone added as module-level imports to planner/views.py top block (not local) — consistent with existing Max/Sum/Q imports"

patterns-established:
  - "Optimistic-lock UPDATE pattern: filter(pk=..., version=loaded).update(..., version=F('version')+1) + rowcount check"
  - "_enrich_nodes() placement: pure helper above its only caller (signal_flow_state), below _get_diagram_for_request"
  - "Test session wiring: client.session['current_project_id'] = project.id + session.save() per test_console_csv_import_views.py pattern"

requirements-completed: [DGM-07, SHP-06, SHP-07]

# Metrics
duration: 45min
completed: 2026-05-22
---

# Phase 09 Plan 01: Autosave Server Foundation Summary

**Optimistic-lock autosave (If-Match + atomic version-pinned UPDATE returning 409) + _enrich_nodes() for live label propagation and orphan flagging on the state GET endpoint, locked by 12 passing tests**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-05-22T00:00:00Z
- **Completed:** 2026-05-22T00:45:00Z
- **Tasks:** 3
- **Files modified:** 2 (planner/views.py modified, planner/tests/test_signal_flow_phase9.py created)

## Accomplishments

- Added `_enrich_nodes(canvas_state, project)` helper to `planner/views.py`: deep-copies the blob, bulk-SELECTs by ContentType (one query per CT), flags missing/cross-project refs as `isOrphan=True`, refreshes `savedLabel` and `attrs.label.text` for live refs — never mutates the persisted blob (D-12, D-13, D-14)
- Extended `signal_flow_state` GET to call `_enrich_nodes()` before returning — callers receive an enriched view; the DB row is untouched (SHP-06, SHP-07)
- Replaced the Phase 8 unconditional `diagram.save()` block in `signal_flow_autosave` with an `If-Match` header read + `transaction.atomic()` version-pinned `filter(...).update(...)` — 409 on missing/non-integer header, 409 with `current_version` on stale version, 200 with bumped version on match (DGM-07, D-05, D-06)
- Viewport-only path (`?viewport_only=1`) preserved as last-write-wins — no If-Match required on that branch
- Existing IDOR walk (lines 7663-7712) preserved verbatim — still runs after the If-Match check and returns 422 on cross-project equipment refs (T-09-01)
- Wrote 12-test suite covering all Phase 9 server contracts; all pass with `OK`

## Task Commits

Each task was committed atomically:

1. **Task 1: Add `_enrich_nodes()` + wire signal_flow_state GET** - `cfb2625` (feat)
2. **Task 2: Replace autosave save block with If-Match + atomic UPDATE** - `3982f62` (feat)
3. **Task 3: Phase 9 server-side test suite** - `dba1293` (test)

## Files Created/Modified

- `planner/views.py` — Added `F` + `timezone` imports; inserted `_enrich_nodes()` helper (69 lines) between `_get_diagram_for_request` and `signal_flow_state`; replaced `signal_flow_state` body with enrichment call; replaced `signal_flow_autosave` save block (12 lines) with If-Match read + atomic UPDATE (37 lines); updated docstring
- `planner/tests/test_signal_flow_phase9.py` — New file: 401 lines, 2 test classes, 12 test methods covering DGM-07 + SHP-06 + SHP-07 server contracts

## Decisions Made

- Atomic `filter+update` over `select_for_update()` — single DB round-trip; `rowcount==0` is the conflict signal; avoids row-lock duration overhead (D-06, PITFALLS.md §3)
- `If-Match` NOT read on viewport-only path — those writes stay last-write-wins by design (D-05)
- `_enrich_nodes()` deep-copies input; the persisted blob is never touched by the GET path (D-12)
- One SELECT per ContentType in `_enrich_nodes()` regardless of how many cells share that CT — O(CT) queries, never O(cells) (D-13)
- Unknown ContentType in `_enrich_nodes()` → treated as orphan silently (never raises); this is asymmetric with autosave (which returns 422) — intentional because GET enrichment must be non-destructive
- `F` and `timezone` added at module-level (top of file) consistent with existing `Max`, `Sum`, `Q` pattern

## Deviations from Plan

None — plan executed exactly as written. All three verbatim function bodies from the plan spec were used without modification. All acceptance criteria met.

## Issues Encountered

None. All 12 tests passed on first run.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. The `_enrich_nodes()` helper runs only on the existing `signal_flow_state` GET path (already behind `@staff_member_required`). The atomic UPDATE runs only on the existing `signal_flow_autosave` POST path (already behind `@login_required + @require_POST`). Threat mitigations T-09-01 through T-09-03 are implemented and locked by tests:

- T-09-01 (IDOR cross-project equipment in autosave body): IDOR walk preserved verbatim, `test_idor_walk_still_rejects_cross_project_equipment_with_422` regression gate in place
- T-09-02 (attacker sets If-Match=0 or huge int): atomic `filter(version=loaded_version)` is the only writer; any mismatch → rowcount=0 → 409
- T-09-03 (cross-project name leak via _enrich_nodes): project-scoped querysets in bulk SELECT; `test_cross_project_reference_is_orphan` locks the contract

## Known Stubs

None — all functionality fully implemented and tested.

## Next Phase Readiness

Wave 2 (plans 09-02, 09-03, 09-04) can proceed:
- **09-02** (autosave debounce JS): server If-Match 409 contract is locked and tested; JS can safely send `If-Match: currentVersion` on every full save
- **09-03** (orphan ghost render JS): `_enrich_nodes()` contract locked; JS can read `cell.showstack.isOrphan` and apply ghost CSS
- **09-04** (keepalive flush): same autosave endpoint accepts `keepalive: true` fetch with `If-Match` header

No blockers. No migrations needed (no model changes). No new Python dependencies.

---
*Phase: 09-autosave-orphan-rendering*
*Completed: 2026-05-22*
