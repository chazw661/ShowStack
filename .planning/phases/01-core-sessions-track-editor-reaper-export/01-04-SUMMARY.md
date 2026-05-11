---
phase: 01-core-sessions-track-editor-reaper-export
plan: 04
subsystem: web
tags: [django, views, urls, multitrack, ajax, reaper-export, idor, xss, csrf]

# Dependency graph
requires:
  - phase: 01
    plan: 01
    provides: MultitrackSession + MultitrackTrack models, resolved_label / resolved_color / resolved_dante_number / resolved_source helpers
  - phase: 01
    plan: 02
    provides: build_rpp(session) -> str, build_rtracktemplate(session) -> str (public API of planner.utils.reaper_export)
  - phase: 01
    plan: 03
    provides: seven page-render multitrack views, _editor_context(session, tracks=None, **extras) canonical context helper, _build_picker_data helper, URL namespace planner:multitrack_*, Plan 04 URL-name reservation comment block
provides:
  - "multitrack_reorder view — dense track_number 1..N renumber via bulk_update, ordered_ids subset-check rejects cross-session injection"
  - "multitrack_add_tracks view — D-10 append order (input -> aux -> matrix -> stereo -> manual), session.console-scoped ID validation, manual track label/notes/color validation with verbatim UI-SPEC error strings"
  - "multitrack_set_color / set_label / set_enabled / remove_track views — track-level mutate endpoints routed through _get_track_for_request for IDOR-safe project scoping"
  - "multitrack_capacity_check view — GET /capacity/ returning {count, capacity, over} for the live capacity bar"
  - "multitrack_export_rpp view — text/plain Content-Disposition attachment with build_rpp body and _safe_filename slugified filename"
  - "multitrack_export_rtracktemplate view — same shape, build_rtracktemplate body, .RTrackTemplate filename"
  - "_get_track_for_request(request, track_id) — single source of truth for IDOR-safe track lookup via track.session.project = current_project chain"
  - "_HEX_COLOR_RE = ^#[0-9A-Fa-f]{6}$ regex closing color_override XSS surface"
  - "_safe_filename(name) helper restricting filename charset to [A-Za-z0-9_-] (path-traversal + Content-Disposition header-injection close)"
  - "_has_enabled_tracks(session) predicate guarding empty-set export"
  - "Nine new URL routes wired in planner/urls.py replacing the Plan 03 reservation comment block"
affects: [01-05, 01-06]

# Tech tracking
tech-stack:
  added: []  # All from existing Django 5.x stack — no new dependencies
  patterns:
    - "Discriminator-scoped IDOR-safe lookup: track-level endpoints take track_id in JSON body and verify via track.session.project chain"
    - "Per-endpoint @require_POST + Django CSRF middleware — zero @csrf_exempt across all seven AJAX mutate endpoints"
    - "Regex-locked validation at the API boundary: _HEX_COLOR_RE rejects everything except '' or '#RRGGBB' before any DB write or template render"
    - "Filename sanitization at the response boundary: _safe_filename collapses [^A-Za-z0-9_-] to '_' before any Content-Disposition header is built"
    - "View-layer delegation to a pure string-builder utility — multitrack_export_rpp/rtracktemplate import build_rpp / build_rtracktemplate and only handle HTTP shape (no RPP-format string-building in the view)"
    - "Shared context-helper reuse for empty-set fallbacks: both export views route their no-enabled-tracks render through Plan 03's _editor_context with an export_error extra, preserving the editor template's full context contract"

key-files:
  created: []
  modified:
    - "planner/views.py (+441 lines — 7 AJAX mutate views + 2 file-download views + 4 helpers + 2 section-header comment blocks + 1 inline `import re` + 1 inline `from .utils.reaper_export import build_rpp, build_rtracktemplate`)"
    - "planner/urls.py (+11 / -11 — replaced Plan 03's 11-line comment-stub block with 9 actual path() entries + 2 section header comments)"

key-decisions:
  - "Used Max('track_number') directly in multitrack_add_tracks rather than adding `from django.db import models` and using `models.Max`. `Max` is already imported at the top of views.py (line 9: `from django.db.models import Max`). The plan suggested adding the `models` namespace if missing; using the already-imported symbol is a no-op style adjustment and avoids a redundant import."
  - "Kept the multi-line formatting on `_editor_context(...)` calls in both export views (matches the plan's own example code block lines 564-573). One acceptance-criteria grep (`_editor_context(session`) only matches single-line callers — see Acceptance Criteria Notes section below. Functional intent (3 distinct call sites) is satisfied; rewriting the calls to satisfy the grep would either force a single very long line or omit kwargs."
  - "Did not add @login_required / @staff_member_required to the four track-level mutate endpoints (set_color/set_label/set_enabled/remove_track). The plan's code block as written uses only @require_POST on these. The IDOR-safe surface is enforced via `_get_track_for_request` (returns None for tracks belonging to other projects, which yields a 404 JSON). An unauthenticated POST to e.g. /multitrack/track/set-color/ with any track_id will receive 404 because `request.current_project` will be None and the helper returns None before any DB write. The Reaper-export views (multitrack_export_rpp/rtracktemplate) and the GET capacity-check view DO carry @staff_member_required per the plan."
  - "Plan acceptance-criteria typo: 'A POST with track_id from another project returns 404 without leaking existence' (threat T-04-01) — verified the helper returns None for cross-project track_id and the four track-level views all return JsonResponse({'error': 'Track not found'}, status=404). Existence is not distinguishable from cross-project, both surface as 404."

requirements-completed:
  - TRK-02
  - TRK-03
  - TRK-04
  - TRK-05
  - TRK-06
  - TRK-07
  - TRK-08
  - TRK-10
  - RPP-01
  - RPP-02
  - RPP-03
  - RPP-04
  - RPP-05

# Metrics
duration: ~10min (wall clock 56m — includes idle gap between Task 1 commit and Task 2)
completed: 2026-05-11
---

# Phase 1 Plan 04: Multitrack AJAX Mutate Endpoints + Reaper Download Views Summary

**Seven AJAX mutate endpoints + two Reaper file-download views appended to `planner/views.py`, plus nine URL routes wired in `planner/urls.py` replacing Plan 03's reservation stubs. All track-level endpoints route through a shared `_get_track_for_request` helper for IDOR-safe project scoping; all hex-color writes pass through a locked `^#[0-9A-Fa-f]{6}$` regex; all Reaper bytes come from `planner.utils.reaper_export.build_rpp` / `build_rtracktemplate` (no RPP serialization in the view layer).**

## Performance

- **Wall-clock duration:** 56 min (includes an extended idle gap after Task 1's commit before Task 2 work resumed)
- **Active execution time:** ~10 min
- **Tasks:** 3
- **Files modified:** 2 (no files created)

## Accomplishments

- Seven AJAX mutate endpoints landed in `planner/views.py` (multitrack_reorder, multitrack_add_tracks, multitrack_set_color, multitrack_set_label, multitrack_set_enabled, multitrack_remove_track, multitrack_capacity_check).
- Two file-download views landed in `planner/views.py` (multitrack_export_rpp, multitrack_export_rtracktemplate). Both delegate the RPP body building to `planner.utils.reaper_export` — zero RPP-format string-building in the view layer (per the executor's sequential-execution preamble).
- Four shared helpers extracted: `_get_track_for_request` (IDOR-safe track lookup), `_HEX_COLOR_RE` (XSS-safe hex validator), `_safe_filename` (path-traversal-safe filename slugifier), `_has_enabled_tracks` (export guard predicate).
- Nine URL routes wired in `planner/urls.py`, replacing Plan 03's comment-stub reservation block. All sixteen multitrack URLs (seven from Plan 03 + nine from this plan) now reverse() successfully.
- All four threat-model XSS / IDOR / CSRF / path-traversal mitigations applied as specified (T-04-01 through T-04-13).

## Task Commits

Each task was committed atomically with `--no-verify` (parallel-executor protocol):

1. **Task 1: 7 AJAX mutate endpoints + IDOR-safe track lookup** — `68ccb2d` (feat)
2. **Task 2: Reaper .RPP / .RTrackTemplate file-download views** — `54cbb7c` (feat)
3. **Task 3: Wire 9 URL routes (replace Plan 03 stub block)** — `685abc5` (feat)

## Final Multitrack URL Contract (Plan 03 + Plan 04 = 16 routes)

| Name | URL | Method | Plan | View | Returns |
|---|---|---|---|---|---|
| `planner:multitrack_dashboard` | `/audiopatch/multitrack/` | GET | 03 | `multitrack_dashboard` | renders `multitrack/dashboard.html` |
| `planner:multitrack_create` | `/audiopatch/multitrack/new/` | GET / POST | 03 | `multitrack_create_view` | renders `new_session.html`; POST redirects to editor |
| `planner:multitrack_editor` | `/audiopatch/multitrack/<id>/` | GET | 03 | `multitrack_editor` | renders `editor.html` via `_editor_context(session)` |
| `planner:multitrack_edit` | `/audiopatch/multitrack/<id>/edit/` | GET / POST | 03 | `multitrack_edit_view` | renders `new_session.html`; POST redirects to editor |
| `planner:multitrack_duplicate` | `/audiopatch/multitrack/<id>/duplicate/` | POST | 03 | `multitrack_duplicate` | JSON `{ok, session_id, redirect_url}` |
| `planner:multitrack_rename` | `/audiopatch/multitrack/<id>/rename/` | POST | 03 | `multitrack_rename` | JSON `{ok, name}` |
| `planner:multitrack_delete` | `/audiopatch/multitrack/<id>/delete/` | POST | 03 | `multitrack_delete` | JSON `{ok, redirect_url}` |
| `planner:multitrack_reorder` | `/audiopatch/multitrack/<id>/reorder/` | POST | 04 | `multitrack_reorder` | JSON `{ok}` |
| `planner:multitrack_add_tracks` | `/audiopatch/multitrack/<id>/add-tracks/` | POST | 04 | `multitrack_add_tracks` | JSON `{ok, created_count, redirect_url}` |
| `planner:multitrack_capacity_check` | `/audiopatch/multitrack/<id>/capacity/` | GET | 04 | `multitrack_capacity_check` | JSON `{count, capacity, over}` |
| `planner:multitrack_set_color` | `/audiopatch/multitrack/track/set-color/` | POST | 04 | `multitrack_set_color` | JSON `{ok, color}` |
| `planner:multitrack_set_label` | `/audiopatch/multitrack/track/set-label/` | POST | 04 | `multitrack_set_label` | JSON `{ok, resolved_label}` |
| `planner:multitrack_set_enabled` | `/audiopatch/multitrack/track/set-enabled/` | POST | 04 | `multitrack_set_enabled` | JSON `{ok, enabled}` |
| `planner:multitrack_remove_track` | `/audiopatch/multitrack/track/remove/` | POST | 04 | `multitrack_remove_track` | JSON `{ok}` |
| `planner:multitrack_export_rpp` | `/audiopatch/multitrack/<id>/export.rpp/` | GET | 04 | `multitrack_export_rpp` | `text/plain` attachment `<safe>.RPP` |
| `planner:multitrack_export_rtracktemplate` | `/audiopatch/multitrack/<id>/export.rtracktemplate/` | GET | 04 | `multitrack_export_rtracktemplate` | `text/plain` attachment `<safe>.RTrackTemplate` |

Track-level endpoints (`set-color` / `set-label` / `set-enabled` / `remove-track`) do NOT take `<int:session_id>` in the URL — `track_id` is in the JSON body and authorization runs through `track.session.project = current_project`. This is the simplest IDOR-safe URL shape and matches the plan's design (Action block constraints, Task 3).

## AJAX Endpoint JSON Contract (so Plan 06's fetch() can pre-derive bindings)

### POST `multitrack_reorder(session_id)`
- **Request body:** `{ordered_ids: [int, int, ...]}`
- **200:** `{ok: True}`
- **400:** `{error: 'No active project' | 'ordered_ids must be a list of integers' | 'One or more track IDs do not belong to this session'}`
- **404:** `{error: 'Session not found'}`
- **500:** `{error: str}`

### POST `multitrack_add_tracks(session_id)`
- **Request body:**
  ```json
  {
    "selections": {
      "inputs": [int, ...], "aux": [int, ...],
      "matrix": [int, ...], "stereo": [int, ...]
    },
    "manuals": [{"label": str, "color": "" | "#RRGGBB", "notes": str}, ...]
  }
  ```
- **200:** `{ok: True, created_count: int, redirect_url: '/audiopatch/multitrack/<id>/'}`
- **400:** `{error: 'Label is required for manual tracks.' | 'Label must be 100 characters or fewer.' | 'Color must be empty or #RRGGBB hex, got: <bad_value>' | 'Notes must be 200 characters or fewer.' | 'No active project'}`
- **404:** `{error: 'Session not found'}`
- **500:** `{error: str}`
- **D-10 append order:** new track_numbers continue from `MAX(existing) + 1`, inserting in order Inputs → Aux → Matrix → Stereo → Manual, each in the order received in the request.

### POST `multitrack_set_color`
- **Request body:** `{track_id: int, color: "" | "#RRGGBB"}`
- **200:** `{ok: True, color: str}`
- **400:** `{error: 'Color must be empty or #RRGGBB hex, got: <bad_value>'}`
- **404:** `{error: 'Track not found'}`  (covers both not-exists and cross-project; no existence leak)
- **500:** `{error: str}`

### POST `multitrack_set_label`
- **Request body:** `{track_id: int, label: str}`
- **200:** `{ok: True, resolved_label: str}` (Note: `resolved_label` is the *post-save* property — the label override OR the resolved channel name if label cleared)
- **400:** `{error: 'Label must be 100 characters or fewer.' | 'Label is required for manual tracks.'}`
- **404:** `{error: 'Track not found'}`
- **500:** `{error: str}`

### POST `multitrack_set_enabled`
- **Request body:** `{track_id: int, enabled: bool}`
- **200:** `{ok: True, enabled: bool}` (echoes the saved value)
- **404:** `{error: 'Track not found'}`
- **500:** `{error: str}`

### POST `multitrack_remove_track`
- **Request body:** `{track_id: int}`
- **200:** `{ok: True}`
- **404:** `{error: 'Track not found'}`
- **500:** `{error: str}`
- **No confirmation prompt** — UI-SPEC § "Destructive Confirmations" explicitly says one-click no-confirm.

### GET `multitrack_capacity_check(session_id)`
- **No request body.**
- **200:** `{count: int, capacity: int | null, over: bool}`
- **400:** `{error: 'No active project'}`
- **404:** `{error: 'Session not found'}`

### GET `multitrack_export_rpp(session_id)` / `multitrack_export_rtracktemplate(session_id)`
- **No request body.**
- **200 (happy path):** `text/plain; charset=utf-8` response with `Content-Disposition: attachment; filename="<safe>.RPP"` (or `.RTrackTemplate`). Body is the output of `build_rpp(session)` / `build_rtracktemplate(session)`.
- **200 (empty-set path):** HTML render of `planner/multitrack/editor.html` with `export_error='This session has no enabled tracks. Enable at least one track to export.'` extra in the `_editor_context` dict. The browser's "Save As" dialog is NOT triggered — the engineer sees the editor with the error in context.
- **302:** redirect to `/` (missing current_project) or `/audiopatch/multitrack/` (missing session / cross-project) — graceful degrade, no JSON 4xx body.

## Reaper Smoke-Test Status

**Status:** Not executed in this worktree.

Plan 01-02's SUMMARY already documented that the worktree environment has no Reaper install and no display server, so the manual smoke test ("open /tmp/test.rpp in Reaper 7.x and confirm three tracks visible with names + colors") is deferred to Charlie's manual review at phase-merge time. The 42 Plan 01-02 unit tests cover the structural correctness of the output. Plan 04 adds zero RPP-format logic — it only wraps `build_rpp(...)` and `build_rtracktemplate(...)` in HTTP responses — so the smoke test against the Plan 04 view is equivalent to the Plan 01-02 smoke test.

**Suggested manual verification flow (before phase merge):**
```bash
# Boot the dev server, then in another shell:
curl -i -c /tmp/cookies -b /tmp/cookies \
  http://localhost:8000/audiopatch/multitrack/<id>/export.rpp/ \
  -o /tmp/test.rpp
# Confirm headers include:
#   Content-Type: text/plain; charset=utf-8
#   Content-Disposition: attachment; filename="<safe>.RPP"
# Then open /tmp/test.rpp in Reaper 7.x and confirm tracks render.
```

## Threat Mitigations Applied (T-04-* register)

All thirteen threats in the plan's `<threat_model>` are mitigated as designed:

- **T-04-01 (IDOR — track-level):** `_get_track_for_request(request, track_id)` chains `track.session.project = current_project` before any save/delete. Cross-project track_id returns 404 without existence leak. Single source of truth — every track-level endpoint calls this helper.
- **T-04-02 (IDOR — session-level):** Every session-level endpoint inlines `filter(id=session_id, project=current_project).first()`. Cross-project session_id returns 404 (AJAX) or dashboard redirect (page).
- **T-04-03 (cross-session reorder):** `multitrack_reorder` validates `set(ordered_ids).issubset(existing_ids)` before any `bulk_update`. POSTing foreign track IDs returns 400.
- **T-04-04 (color XSS):** `_HEX_COLOR_RE` is enforced in BOTH `multitrack_set_color` AND `multitrack_add_tracks` (manual queue). `javascript:alert(1)`, `red`, `#FFF`, `#GGGGGG`, etc. all return 400. Verified via the Task 1 automated check.
- **T-04-05 (label XSS):** Stored as plain `CharField(max_length=100)`. Auto-escape applies in Plan 05 templates (Plan 05 author MUST NOT use `|safe`). Reaper exporter sanitizes `"` → `'` (Plan 02 `_sanitize_name`).
- **T-04-06 (path traversal) / T-04-12 (Content-Disposition header injection):** `_safe_filename` restricts the filename charset to `[A-Za-z0-9_-]`. `../../etc/passwd` → `______etc_passwd`; `"; alert(1); "` → `__alert_1____`; empty / None → `'session'`. Verified via the Task 2 automated check.
- **T-04-07 (CSRF):** Zero `@csrf_exempt` decorators across all nine new views. Django's CSRF middleware enforces `X-CSRFToken` header on every POST. Plan 06's JS reads the token from the page's `csrfmiddlewaretoken` form input.
- **T-04-08 (mass-assignment):** Each endpoint reads ONLY the specific field(s) from the JSON body. Unknown body keys are ignored.
- **T-04-09 (selections injection in add_tracks):** Channel-ID queries filter by `console=session.console`. IDs not belonging to that console silently drop out of the `valid_*_ids` set intersection, so only IDs that exist AND belong to the session's console can produce new `MultitrackTrack` rows.
- **T-04-10 (DoS):** accepted — bulk_update on 10000 rows is sub-second.
- **T-04-11 (DoS — unauthenticated export):** Both export views and capacity-check carry `@staff_member_required`.
- **T-04-13 (empty-set export):** `_has_enabled_tracks` guard returns the editor page with the verbatim UI-SPEC error string instead of generating a 0-track download.

## Acceptance Criteria Notes

All Task 1 / Task 2 / Task 3 acceptance criteria pass with the following note:

- **`grep -c "_editor_context(session" planner/views.py` returns 2, not 3 as the Task 2 acceptance criterion expects.** The mismatch is purely cosmetic: my two new export-fallback callers use multi-line formatting (matching the plan's own example code block at lines 564-573 of `01-04-PLAN.md`), so they read as `_editor_context(\n                session,\n                tracks=...` and don't match the single-line grep pattern. The functional intent (three call sites — Plan 03's editor + Plan 04's RPP fallback + Plan 04's RTrackTemplate fallback) is satisfied: `grep -c "_editor_context("` returns 4 (1 definition + 3 callers). Rewriting the two new calls to fit the grep would require either a single ~140-char line or omitting kwargs. Documented here as evidence of correctness despite the literal grep count.

All other 26 acceptance-criteria grep checks pass with the exact counts the plan specified.

## Threat Flags

None — no new security-relevant surface introduced outside the documented threat register.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Worktree branched from incorrect base commit**
- **Found during:** Pre-execution `<worktree_branch_check>` step.
- **Issue:** Worktree HEAD was `e7561dc` (a downstream beta-tester fix), not `741c1b6` (the expected post-Plan-01-02 merge commit). Required by the worktree_branch_check protocol.
- **Fix:** `git reset --hard 741c1b63b759a429ab674ad92b2ac797bc753f12`. Safe — fresh worktree, no user changes lost.
- **Files modified:** None (state-level fix only).

### Style adjustments (not deviations)

- Used `Max('track_number')` directly in `multitrack_add_tracks` instead of adding `from django.db import models` and using `models.Max('track_number')`. `Max` is already imported at the top of `views.py` (line 9). This avoids a duplicate / redundant import. Functionally identical. Noted as a key-decision above.

No code-level deviations from the plan's task action blocks. All seven AJAX views, both file-download views, and all nine URL routes match the plan code verbatim except for the `Max` import style adjustment.

## Issues Encountered

- **Pre-existing repo issue:** `RuntimeWarning: Model 'planner.audiochecklist' was already registered.` surfaces on every Django bootstrap. Documented in Plan 01-03 SUMMARY as out-of-scope per the executor SCOPE BOUNDARY rule. Logged for future cleanup if/when Charlie wants to investigate the double-registration.
- **Wall-clock duration overstates active work time.** The session paused for an extended period after Task 1's commit (system idle ~45 min) before Task 2 work resumed. Active execution time was ~10 min across all three tasks. Metrics duration field reflects both.

## User Setup Required

None — no external service configuration required. The new views deploy with the next push to `main` (Railway auto-redeploy). All nine URL routes inherit the existing `CurrentProjectMiddleware` session-based project resolution; no migrations needed (Plan 01-01 owns the data layer).

## Next Phase Readiness

- **Plan 05 (template authoring, Wave 4):** unblocked — the full sixteen-URL contract is in place. Template authors can write `{% url 'planner:multitrack_reorder' session.id %}`, `{% url 'planner:multitrack_set_color' %}`, etc. The `_editor_context` keys (`session`, `tracks`, `picker_data_json`, `auto_open_picker`, `total_count`, `over_count`, optional `export_error`) are now stable.
- **Plan 06 (JS authoring, Wave 4 or 5):** unblocked — all seven AJAX mutate endpoints have well-defined request/response JSON shapes (documented above) and uniform error semantics (`{error: str, status: 4xx}` for all 4xx, `{error: str, status: 500}` for unexpected). The `redirect_url` field in 200 responses lets the JS navigate after success without re-deriving URL names.
- **Production deploy:** no special steps required. The next push to `main` ships these views via Railway's standard `startCommand`. Charlie's pre-merge manual Reaper smoke test (from Plan 01-02 SUMMARY) covers both this plan's export endpoints since they only wrap `build_rpp` / `build_rtracktemplate`.

## Self-Check

Verified all claims in this SUMMARY against the worktree state.

**Modified files (git diff vs plan base 741c1b6):**
- FOUND: `planner/views.py` (+441 lines)
- FOUND: `planner/urls.py` (+12 / -11 lines)

**Commits exist:**
- FOUND: `68ccb2d` Task 1 (7 AJAX mutate endpoints + IDOR-safe track lookup)
- FOUND: `54cbb7c` Task 2 (Reaper .RPP / .RTrackTemplate file-download views)
- FOUND: `685abc5` Task 3 (wire 9 multitrack URLs)

**Verification commands:**
- FOUND: `python manage.py check` exits 0
- FOUND: All 9 new `reverse('planner:multitrack_*')` calls resolve to the expected URLs
- FOUND: All 9 new view functions + 4 helpers importable from `planner.views`
- FOUND: `_HEX_COLOR_RE.match('#FF0000')` = True; rejects `#FFF`, `red`, `javascript:alert(1)`, ''
- FOUND: `_safe_filename` rejects `../../etc/passwd` → `______etc_passwd` and `None` / `''` → `'session'`

**Acceptance criteria (plan-level grep counts):**
- FOUND: all 7 `^def multitrack_*` definitions for AJAX views (counts = 1 each)
- FOUND: 2 file-download view definitions (counts = 1 each)
- FOUND: `_get_track_for_request` defined and used (count = 1 def + multiple call sites)
- FOUND: `_HEX_COLOR_RE` referenced 4 times (definition + 2 use sites + 1 import comment)
- FOUND: 9 URL names registered (counts = 1 each)
- NOTED: `_editor_context(session` literal grep = 2 (the 2 multi-line export callers don't match the single-line pattern); functional intent satisfied (`_editor_context(` total = 4). Documented in Acceptance Criteria Notes.

## Self-Check: PASSED

---

*Phase: 01-core-sessions-track-editor-reaper-export*
*Wave: 3 (sequential — only plan in this wave)*
*Completed: 2026-05-11*
