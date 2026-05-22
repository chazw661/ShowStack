---
phase: 09-autosave-orphan-rendering
fixed_at: 2026-05-21T00:00:00Z
review_path: .planning/phases/09-autosave-orphan-rendering/09-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 9: Code Review Fix Report

**Fixed at:** 2026-05-21
**Source review:** .planning/phases/09-autosave-orphan-rendering/09-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (WR-01 through WR-04; Info findings excluded per fix_scope=critical_warning)
- Fixed: 4
- Skipped: 0

Post-fix verification: all 12 server tests in `planner.tests.test_signal_flow_phase9` pass (`Ran 12 tests in 3.544s OK`). JS file passes `node --check`. Python file passes `ast.parse`.

## Fixed Issues

### WR-01: `force` flag bypasses `savingNow` guard

**Files modified:** `planner/static/planner/js/signal_flow_editor.js`
**Commit:** ec27667
**Applied fix:** Removed `&& !opts.force` from the `savingNow` guard in `flushAutosave` (line 1564). The guard now unconditionally returns `Promise.resolve()` when a save is in flight, regardless of `opts.force`. The retry path is safe because `savingNow` is always `false` by the time the user can click retry.

---

### WR-02: `maybeKeepaliveFlush` does not reschedule on keepalive failure

**Files modified:** `planner/static/planner/js/signal_flow_editor.js`
**Commit:** 602f512
**Applied fix:** Added `.catch(function() { scheduleAutosave(); })` to the `flushAutosave({ keepalive: true })` call in `maybeKeepaliveFlush`. If the keepalive fetch fails (network down on tab-hide), the debounce timer is rescheduled so the change is retried when the tab becomes visible again rather than being silently abandoned.

---

### WR-03: `signal_flow_state` missing `@require_GET`

**Files modified:** `planner/views.py`
**Commit:** 9587fd2
**Applied fix:** Added `@require_GET` decorator to `signal_flow_state` directly beneath `@staff_member_required`. `require_GET` was already imported at `views.py:6` — no import change needed. Non-GET requests now receive a proper `405 Method Not Allowed`.

---

### WR-04: `hasattr(Model, 'project')` IDOR predicate replaced with explicit allowlist

**Files modified:** `planner/views.py`
**Commit:** 66b4739
**Applied fix:** Both occurrences of the `hasattr` guard were replaced with an explicit `model_name in ('Console', 'Device', 'CommBeltPack')` check:
- `_enrich_nodes` (line ~7573): `elif hasattr(...) or model_name in (...)` replaced with `elif model_name in ('Console', 'Device', 'CommBeltPack')`. Comment updated to `# unknown model -> orphan (safe default)`.
- `signal_flow_autosave` (line ~7702): same replacement, with comment updated to explain why `hasattr()` is intentionally avoided.
Unknown model types now safely fall through to the orphan/422 branch rather than risking silent scope bypass from a future non-FK `project` attribute.

## Skipped Issues

None — all 4 in-scope findings were fixed successfully.

---

_Fixed: 2026-05-21_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
