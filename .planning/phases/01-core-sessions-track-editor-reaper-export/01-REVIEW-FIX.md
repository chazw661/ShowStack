---
phase: 01-core-sessions-track-editor-reaper-export
fixed_at: 2026-05-10T00:00:00Z
review_path: .planning/phases/01-core-sessions-track-editor-reaper-export/01-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 7
skipped: 2
status: partial
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-05-10T00:00:00Z
**Source review:** `.planning/phases/01-core-sessions-track-editor-reaper-export/01-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (2 critical + 7 warning; 6 info OUT OF SCOPE)
- Fixed: 7
- Skipped: 2 (1 grouped into a sibling commit, 1 confirmed-correct in REVIEW)

**Verification baseline:**
- `python manage.py check` — clean before and after every commit
- `python manage.py test planner.tests.test_reaper_export --settings=audiopatch.test_settings` — 42/42 OK before and after the full fix run

## Fixed Issues

### CR-01 / CR-02: AJAX mutate endpoints lack authentication decorators + create XS-Search oracle

**Files modified:** `planner/views.py`
**Commit:** `98ff672`
**Applied fix:**
- Added a centralised `_multitrack_viewer_block(request)` helper returning a 403 JsonResponse when `request.user.groups.filter(name='Viewer').exists()`, mirroring the convention used throughout `planner/admin.py`.
- Added `@login_required` decorator and a `viewer_block = _multitrack_viewer_block(request); if viewer_block is not None: return viewer_block` guard at the top of all nine multitrack AJAX mutate endpoints: `multitrack_duplicate`, `multitrack_rename`, `multitrack_delete`, `multitrack_reorder`, `multitrack_add_tracks`, `multitrack_set_color`, `multitrack_set_label`, `multitrack_set_enabled`, `multitrack_remove_track`.
- CR-01 and CR-02 share the same root cause and are closed by the same change; documented as a single atomic commit covering both findings.

### WR-01: Under-capacity progress bar always renders at 100%

**Files modified:** `planner/static/planner/css/multitrack.css`, `planner/static/planner/js/multitrack_editor.js`
**Commit:** `6573c00`
**Applied fix:**
- Removed the `!important` from `.mts-capacity__fill { width: 100% }` so an inline width can win.
- Added a `paintCapacityFill()` initializer in `multitrack_editor.js` that reads `data-fill-percent` from each `.mts-capacity__fill` and sets `el.style.setProperty('width', val + '%', 'important')`.
- Wired the initializer into the `DOMContentLoaded` handler alongside `paintInitialSwatches()`.

### WR-02: Bare `except Exception as e: return JsonResponse({'error': str(e)})` leaks internals

**Files modified:** `planner/views.py`
**Commit:** `8cddbf6`
**Applied fix:**
- Added module-level `_multitrack_logger = logging.getLogger(__name__)`.
- Replaced all 9 bare exception handlers in the multitrack mutate endpoints with `except Exception: _multitrack_logger.exception('multitrack_<endpoint> failed'); return JsonResponse({'error': 'Server error.'}, status=500)`.
- Real error details are now captured server-side (with traceback) while the client only sees a generic 500.

### WR-04: `multitrack_reorder` `issubset` allows partial reorder → duplicate `track_number`

**Files modified:** `planner/views.py`
**Commit:** `594d2c0`
**Applied fix:**
- Added an explicit duplicate-IDs check: `if len(ordered_ids) != len(set(ordered_ids))` → 400 with `'Duplicate track IDs in ordered_ids.'`.
- Replaced `set(ordered_ids).issubset(existing_ids)` with `set(ordered_ids) != existing_ids`, returning 400 with `'ordered_ids must include every track in the session exactly once.'` on mismatch.
- Preserves the `ordering = ['track_number']` invariant on `MultitrackTrack.Meta`.

### WR-05: Signal `name or f'Aux {n}' or sentinel` makes sentinel unreachable

**Files modified:** `planner/signals.py`
**Commit:** `d83a4d2`
**Applied fix:**
- Replaced the chained `or` patterns in `consoleauxoutput_to_manual`, `consolematrixoutput_to_manual`, and `consolestereooutput_to_manual` with explicit `if instance.name: ... elif instance.<channel_number>: ... else: label = '(deleted <type>)'` branches.
- For `ConsoleStereoOutput`, only call `get_stereo_type_display()` when `instance.stereo_type` is truthy (the display lookup returns an empty string for missing/invalid choices, so the sentinel still fires when both `name` and `stereo_type` are unset).

### WR-06: `_safe_filename` accepts non-ASCII letters via `str.isalnum()`

**Files modified:** `planner/views.py`
**Commit:** `ba1f59f`
**Applied fix:**
- Tightened the comprehension to `c if ((c.isascii() and c.isalnum()) or c in '-_') else '_'` so non-ASCII letters (`é`, `ñ`, `café`) are replaced with underscore, matching RFC 6266's bare-`filename=` ASCII-only requirement.

### WR-07: `_build_picker_data` lacks defence-in-depth IDOR check

**Files modified:** `planner/views.py`
**Commit:** `42b5696`
**Applied fix:**
- Added an optional `current_project=None` parameter to `_build_picker_data`. When supplied, asserts `session.project_id == current_project.id` so a future caller that forgets the IDOR check fails loudly instead of leaking another project's channel data.
- Threaded `current_project` through `_editor_context` and updated all three call sites (`multitrack_editor`, `multitrack_export_rpp`, `multitrack_export_rtracktemplate`) to pass `current_project=request.current_project`.

## Skipped Issues

### CR-02 (grouped into CR-01 commit)

**Status:** fixed (no separate commit needed)
**Reason:** REVIEW.md explicitly states CR-02 is "the same root cause as CR-01 viewed from a different angle" and the suggested fix is "Same as CR-01." The single commit `98ff672` closes both findings simultaneously by adding `@login_required` + viewer-block guard to every mutate endpoint. CR-02's listing under "Skipped" is procedural — the underlying issue is fixed, just not in a dedicated commit. The commit message references both `CR-01/CR-02` for traceability.

### WR-03: `mtsCommitPickerSelection` fallback to `[data-mts-session-id]`

**File:** `planner/static/planner/js/multitrack_editor.js:336-348`
**Reason:** REVIEW.md classifies this as confirmed-correct. The reviewer wrote: "**No functional fix required**" and "This is actually working correctly." The orchestrator prompt also explicitly instructed: "WR-03 is already noted as confirmed-good in REVIEW.md — skip (no fix needed)." No code change applied.

---

_Fixed: 2026-05-10T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
