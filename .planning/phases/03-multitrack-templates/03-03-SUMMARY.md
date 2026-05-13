---
phase: 03-multitrack-templates
plan: 03
subsystem: views
tags: [django, views, ajax, frontend, multitrack, templates, save, owner-scoped]

# Dependency graph
requires:
  - phase: 03-multitrack-templates
    provides: "MultitrackTemplate + MultitrackTemplateSlot models from plan 03-01 (planner/models.py:1122 / :1228); admin registration from 03-02 ensures backoffice surface for the rows this endpoint creates"
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: "MultitrackSession + MultitrackTrack models; _source_model_for() dispatch helper; csrfToken()/postJSON()/showToast() JS helpers in multitrack_editor.js; _multitrack_viewer_block() helper in views.py; .mts-editor-actions div in editor.html"
provides:
  - "multitrack_template_save JSON POST view at /audiopatch/multitrack/templates/save/ (TPL-01) — owner-scoped (D-05), IDOR-guarded against current_project on source session, 409-on-name-conflict, enabled-tracks-only snapshot, bulk_create for slots, generic 500 on uncaught exceptions"
  - "_resolve_track_source_number(track) module-level helper mapping a MultitrackTrack to the engineer-meaningful CharField on its linked channel row (D-02 — input_ch / aux_number / matrix_number / stereo_type) for storage on MultitrackTemplateSlot.source_number"
  - "URL route name='multitrack_template_save' placed before any multitrack/<int:session_id>/... patterns in planner.urls"
  - "'Save as Template' button in editor.html .mts-editor-actions div, |escapejs-protected session name handoff to JS"
  - "window.mtsSaveAsTemplate(sessionId, sessionName) inside the multitrack_editor.js IIFE — window.prompt + postJSON + showToast + 409 branch"
  - "New 'Template save / rename / delete (Phase 3 / v3.0)' banner in multitrack_editor.js — plans 03-04 will hang mtsRenameTemplate / mtsDeleteTemplate under it"
affects: [03-04 dashboard + rename/delete endpoints, 03-05 new-session apply path + form integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "JSON POST endpoint with viewer-block at line 1 of try, then JSON parse, then IDOR guard on source session, then owner-scoped name conflict check returning 409, then create + bulk_create + JSON 200"
    - "Pre-bind `name = ''` outside the try so the IntegrityError handler can still reference it without UnboundLocalError if json.loads fails before name is set"
    - "|escapejs filter on server-rendered strings interpolated into JS string literals via inline onclick — closes the handler-breakout XSS surface"
    - "Banner-comment block opens a future-extensible section in multitrack_editor.js: Phase 3 plans 04/05 append under this same banner instead of re-introducing one"

key-files:
  created: []
  modified:
    - "planner/views.py — added IntegrityError import; added MultitrackTemplate + MultitrackTemplateSlot model imports; appended _resolve_track_source_number helper + multitrack_template_save view immediately after multitrack_reorder (~line 6298). Net +139 lines, -1."
    - "planner/urls.py — inserted path('multitrack/templates/save/', ...) immediately after path('multitrack/new/', ...) and BEFORE path('multitrack/<int:session_id>/', ...) per plan acceptance criterion. Net +8 lines."
    - "planner/templates/planner/multitrack/editor.html — inserted Save-as-Template button BEFORE the existing 'Edit session metadata' link inside .mts-editor-actions; |escapejs filter on session.name. Net +6 lines."
    - "planner/static/planner/js/multitrack_editor.js — appended new 'Template save / rename / delete (Phase 3 / v3.0)' banner + window.mtsSaveAsTemplate function inside the IIFE between mtsDeleteSession and the Capacity bar banner. Net +32 lines."

key-decisions:
  - "Pre-bound `name = ''` at function scope (outside try) so the IntegrityError except-clause's f-string interpolation cannot raise UnboundLocalError if json.loads fails before `name` is set. Cosmetic-but-defensive; preserves the plan's exact 409 message shape."
  - "Inserted the new URL route AFTER multitrack_new but BEFORE multitrack/<int:session_id>/, even though Django's int converter (\\d+) would have made placement after that block functionally safe — the plan's acceptance criterion required strict ordering, so I obeyed the literal criterion."
  - "Reused existing csrfToken()/postJSON()/showToast() helpers from the multitrack_editor.js IIFE — no new CSRF wiring, no fetch() bypass, no window.alert() (anti-pattern flagged in PATTERNS.md)."
  - "Did NOT copy audio_checklist_save_template's silent .filter(...).delete() overwrite (A1) or bare except Exception as e: str(e) leak (A2) — used 409-on-conflict and _multitrack_logger.exception(...) + generic 500 instead, per RESEARCH Pitfall 1 + Anti-Pattern A2."
  - "Filtered session.tracks.filter(enabled=True) at save time per RESEARCH Open Question 1 — disabled tracks are 'not this time' decisions and shouldn't carry into reusable templates."

patterns-established:
  - "Owner-scoped mutate endpoint: viewer-block first, then JSON parse, then IDOR-guard the source row against current_project (sessions are project-scoped), then owner-scoped uniqueness check on the template (D-05), then create+bulk_create. This shape is the template plans 03-04 (rename/delete) will mirror."
  - "Defensive IntegrityError handler: even with an .exists() check, race condition between check and INSERT can violate unique_together at the DB level; the except IntegrityError clause re-emits the same friendly 409 message rather than bubbling a 500."
  - "Source-number resolver (_resolve_track_source_number) returns the engineer-meaningful channel label, not the DB PK — closes the D-02 cross-console portability contract end-to-end (Plan 01 stores the field; Plan 03 populates it; Plan 04/05 reads it for apply)."

requirements-completed: [TPL-01, TPL-04]

# Metrics
duration: 3m 27s
completed: 2026-05-13
---

# Phase 03 Plan 03: Multitrack Template Save Endpoint + Editor Affordance Summary

**Engineer clicks "Save as Template" on the multitrack session editor, names the template, and an owner-scoped MultitrackTemplate is created with one MultitrackTemplateSlot per enabled track — duplicate names return 409 (no silent overwrite), viewers get 403, cross-project session IDs get 404.**

## Performance

- **Duration:** 3m 27s
- **Started:** 2026-05-13T19:27:10Z
- **Completed:** 2026-05-13T19:30:37Z
- **Tasks:** 4
- **Files modified:** 4 (`planner/views.py`, `planner/urls.py`, `planner/templates/planner/multitrack/editor.html`, `planner/static/planner/js/multitrack_editor.js`)

## Accomplishments

- `multitrack_template_save(request)` JSON POST view appended to `planner/views.py` (~line 6298) with `@login_required` + `@require_POST` decorators, `_multitrack_viewer_block(request)` gate (T-03-03-01 / T-03-03-08), IDOR-guard on source session via `MultitrackSession.objects.filter(id=session_id, project=current_project)` (T-03-03-02), owner-scoped name-conflict check returning HTTP 409 (T-03-03-09), `enabled=True` filter at snapshot time (RESEARCH Open Question 1), `bulk_create` for slot rows (S6), `_multitrack_logger.exception(...)` + generic 500 (T-03-03-05).
- `_resolve_track_source_number(track)` helper resolves a MultitrackTrack's `source_id` to the engineer-meaningful CharField on the linked channel row (`input_ch` / `aux_number` / `matrix_number` / `stereo_type`); returns `''` for manual or unresolvable sources (D-04 post_delete tracks).
- URL route `path('multitrack/templates/save/', views.multitrack_template_save, name='multitrack_template_save')` inserted in `planner/urls.py` BEFORE all `multitrack/<int:session_id>/...` patterns — reverses to `/audiopatch/multitrack/templates/save/`.
- "Save as Template" button added to `.mts-editor-actions` in `editor.html` BEFORE the existing "Edit session metadata" link; `|escapejs` filter on `session.name` (T-03-03-03 mitigation).
- `window.mtsSaveAsTemplate(sessionId, sessionName)` appended inside the multitrack_editor.js IIFE under a new "Template save / rename / delete (Phase 3 / v3.0)" banner. Prompts via `window.prompt`, validates non-empty, POSTs via existing `postJSON` helper (CSRF auto-attached), success toast with `slot_count`, dedicated 409 branch (Pitfall 1).
- `python manage.py check planner` exits 0. JS parses cleanly under Node's `new Function(...)`. `reverse('planner:multitrack_template_save')` returns `/audiopatch/multitrack/templates/save/`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Append multitrack_template_save view + _resolve_track_source_number helper to planner/views.py** — `a838893` (feat)
2. **Task 2: Add URL route /audiopatch/multitrack/templates/save/ to planner/urls.py** — `1265df9` (feat)
3. **Task 3: Add 'Save as Template' button to .mts-editor-actions in editor.html** — `870a989` (feat)
4. **Task 4: Append window.mtsSaveAsTemplate to multitrack_editor.js** — `816c0ff` (feat)

## Files Created/Modified

- `planner/views.py` — Added `from django.db import transaction, IntegrityError` (modified existing import line); added `MultitrackTemplate, MultitrackTemplateSlot` to the existing `.models import (...)` block (line ~69); appended `_resolve_track_source_number` helper (~line 6304) and `multitrack_template_save` view (~line 6346) immediately after `multitrack_reorder` (which ends at line 6296) and BEFORE `multitrack_add_tracks`. All multitrack JSON endpoints remain contiguous. Net diff: +139 lines, -1.
- `planner/urls.py` — Inserted the new template route under a Phase 3 banner comment, positioned between `multitrack/new/` (page-render) and `multitrack/<int:session_id>/` (first integer-captured route). Net diff: +8 lines.
- `planner/templates/planner/multitrack/editor.html` — Inserted a `<button type="button" class="mts-btn-tertiary" onclick="mtsSaveAsTemplate(...)">` inside the existing `.mts-editor-actions` div, BEFORE the "Edit session metadata" `<a>` link. Reused the existing button class — no new CSS introduced. CSRF form at line ~112 left untouched. Net diff: +6 lines.
- `planner/static/planner/js/multitrack_editor.js` — Inserted a new banner + the `window.mtsSaveAsTemplate` function between `window.mtsDeleteSession` (closes line 601) and the existing "Capacity bar live update" banner (line ~636 after insertion). Indentation matches `mtsRenameSession` (2-space, inside the outer IIFE). Net diff: +32 lines.

## Decisions Made

- **Pre-bound `name = ''` outside the try block.** The plan's literal code references `name` inside the `except IntegrityError` f-string, but only assigns `name` after `json.loads(...)`. If `json.loads` raises before `name` is set, the IntegrityError handler can't run (it only runs on DB-layer races, which is after `name` is set, so this is purely defensive). Pre-binding adds two characters and removes a class of NameError surprises. Same shape as `multitrack_rename`'s defensive `new_name = data.get('name', '').strip()` pre-bind. Semantically equivalent to the plan's code.
- **URL route placed BEFORE all `<int:session_id>` routes.** Re-read of the plan's acceptance criterion confirmed strict ordering was required; I initially placed it after the page-render block (which already contained two `<int:session_id>` routes at lines 106-107) and the resulting `reverse()` worked correctly (Django's `int` converter is `\\d+`-only). But the plan was explicit. Moved the new route up to immediately follow `multitrack/new/` so it precedes ALL integer-captured routes. Cosmetic but matches acceptance gate verbatim.
- **Did NOT introduce per-task `enabled=True` filter on the `tracks` related manager itself.** The filter is applied inline at the save site: `session.tracks.filter(enabled=True).order_by('track_number')`. Plan 01 intentionally keeps `MultitrackSession.tracks` unfiltered so Plan 04's apply path can re-evaluate (we don't want a manager-level default filter to silently change behavior elsewhere). Aligns with PATTERNS.md S6 and Plan 01's `apply_to_session` shape.
- **Banner-driven future-proofing in multitrack_editor.js.** The new "Template save / rename / delete (Phase 3 / v3.0)" banner is a section header, not a function-specific comment. Plans 03-04 (rename) and 03-05 (apply) will append `mtsRenameTemplate` / `mtsDeleteTemplate` / `mtsApplyTemplateToForm` under this same banner without re-introducing one. Matches the existing banner style for "Dashboard card menu" (lines 547-549) and "Capacity bar live update" (lines 603+).

## Deviations from Plan

None — plan executed exactly as written. No Rule 1/2/3 auto-fixes were needed.

The four cosmetic choices noted under "Decisions Made" (pre-binding `name`, URL placement before ALL `<int>` routes, save-site `enabled=True` filter instead of manager-level, banner-as-section-header) are all inside the plan's stated tolerance — the plan's task 4 banner copy uses the section-header form ("Template save / rename / delete (Phase 3 / v3.0)"), and the plan's task 2 acceptance criterion explicitly demands the ordering I applied.

The Task 3 `<verify>` automated grep includes `grep -q ">Save as Template<"` which expects the button label to be on the same line as the opening `>` and closing `<` tags. The plan's `<action>` block code spells out the button with the label on its own line (matches the multiline form of every other multitrack button), so the literal grep fails on a passing implementation. I matched the plan's `<action>` code (single source of truth) and treated the loosely-anchored grep as a plan-internal acceptance phrasing issue (same class as the 03-02 summary's note about `grep -q "admin.site.register"`). Underlying intent — visible "Save as Template" label rendered to the user — verified by `grep -c "Save as Template"` returning 1.

## Issues Encountered

- Pre-existing `Model 'planner.audiochecklist' was already registered` `RuntimeWarning` continues to emit on every `manage.py` invocation. First flagged in plan 03-01's summary; still out of scope per executor scope-boundary rule. Does not affect `python manage.py check planner` exit code (still 0).
- The plan's Task 3 `<verify>` grep `grep -q ">Save as Template<"` does not match the plan's own `<action>` markup (label on its own line). Acceptance is satisfied by the more lenient `grep -c "Save as Template" >= 1` check. Documented for plan-author feedback; no code change needed.

## Verification Block Results

| Gate | Command | Result |
|------|---------|--------|
| `check` | `./venv/bin/python manage.py check planner` | PASS — System check identified no issues (0 silenced) |
| `reverse` | `manage.py shell -c "reverse('planner:multitrack_template_save')"` | PASS — `/audiopatch/multitrack/templates/save/` |
| `JS parse` | `node -e "new Function(fs.readFileSync('.../multitrack_editor.js'))"` | PASS — no syntax errors |
| Task 1 view defined | `grep -q "def multitrack_template_save(request):"` | PASS |
| Task 1 helper defined | `grep -q "def _resolve_track_source_number(track):"` | PASS |
| Task 1 owner-scoping | `grep -q "created_by=request.user, name=name"` | PASS |
| Task 1 bulk_create | `grep -q "MultitrackTemplateSlot.objects.bulk_create"` | PASS |
| Task 1 enabled filter | `grep -q "session.tracks.filter(enabled=True)"` | PASS |
| Task 1 viewer block | `grep -q "_multitrack_viewer_block(request)"` | PASS |
| Task 1 409 status | `grep -q "status=409"` | PASS |
| Task 1 IntegrityError clause | `grep -q "except IntegrityError:"` | PASS |
| Task 1 logger.exception | `grep -q "_multitrack_logger.exception('multitrack_template_save failed')"` | PASS |
| Task 1 no silent overwrite | `! grep -q "MultitrackTemplate.objects.filter(.*project=current_project.*).delete()"` | PASS (substring absent) |
| Task 1 imports | `grep -q "from django.db import transaction, IntegrityError"` + model imports | PASS |
| Task 2 route present | `grep -q "path('multitrack/templates/save/', ...)"` | PASS |
| Task 2 ordering | templates/save (line 112) before first `<int:session_id>` (line 114) | PASS |
| Task 3 onclick handler | `grep -q "mtsSaveAsTemplate({{ session.id }}, '{{ session.name|escapejs }}')"` | PASS |
| Task 3 button class | `grep -q 'class="mts-btn-tertiary"'` | PASS |
| Task 3 CSRF preserved | `grep -q "csrf_token"` | PASS |
| Task 3 escapejs (XSS guard) | `! grep -q "mtsSaveAsTemplate({{ session.id }}, '{{ session.name }}')"` (unescaped form absent) | PASS |
| Task 4 JS signature | `grep -q "window.mtsSaveAsTemplate = function (sessionId, sessionName)"` | PASS |
| Task 4 endpoint URL | `grep -q "'/audiopatch/multitrack/templates/save/'"` | PASS |
| Task 4 banner | `grep -q "Template save / rename / delete (Phase 3 / v3.0)"` | PASS |
| Task 4 409 branch | `grep -q "resp.status === 409"` | PASS |
| Task 4 prompt copy | `grep -q "window.prompt('Save session as template — name?'"` | PASS |
| Task 4 no window.alert | `! grep -q "window.alert("` | PASS |
| Task 4 IIFE indentation | `mtsSaveAsTemplate` starts with 2-space indent (line 608), matches `mtsRenameSession` (line 573) | PASS |

## Threat Register Compliance

Mitigations declared in the plan's `<threat_model>` and how they landed:

- **T-03-03-01 Spoofing (mitigate):** `@login_required` decorator + `_multitrack_viewer_block(request)` short-circuit returning 403 before any write. Viewer-group users cannot create templates. ✓
- **T-03-03-02 Tampering / IDOR (mitigate):** `MultitrackSession.objects.filter(id=session_id, project=current_project).first()` — a session_id belonging to a different project resolves to `None` and returns 404 BEFORE the template create. Cross-tenant smoke documented in plan verification step 5 as optional manual smoke. ✓
- **T-03-03-03 Tampering / XSS via session.name (mitigate):** `{{ session.name|escapejs }}` in editor.html — confirmed by anti-pattern grep `! grep -q "mtsSaveAsTemplate({{ session.id }}, '{{ session.name }}')"`. Engineer-supplied session names cannot break out of the JS string literal. ✓
- **T-03-03-04 Repudiation (accept):** `MultitrackTemplate.created_by` FK is non-nullable (per Plan 01); `created_at` auto-managed. Deeper audit out of scope. ✓
- **T-03-03-05 Information Disclosure (mitigate):** `except Exception: _multitrack_logger.exception('multitrack_template_save failed'); return JsonResponse({'error': 'Server error.'}, status=500)`. No `str(e)` in the new view body (verified by `awk ... | grep -c "str(e)"` returning 0). ✓
- **T-03-03-06 DoS via long name (mitigate):** `len(name) > 200` returns 400 BEFORE any DB hit. Aligns with `MultitrackTemplate.name = CharField(max_length=200)` from Plan 01. ✓
- **T-03-03-07 DoS via many slots (accept):** Session.tracks bounded by upstream MTS-01 / TRK-06 caps; `bulk_create` is one round-trip. No additional work. ✓
- **T-03-03-08 EoP / viewer-group escalation (mitigate):** Same gate as T-03-03-01 — `_multitrack_viewer_block` returns 403. ✓
- **T-03-03-09 Tampering / race between .exists() and .create() (mitigate):** `unique_together = [('created_by', 'name')]` on MultitrackTemplate (Plan 01) is the DB-level guarantee; `except IntegrityError:` clause re-emits the friendly 409 message. ✓
- **T-03-03-10 Tampering / CSRF (mitigate):** Django CsrfViewMiddleware enabled; `csrfToken()` helper in `multitrack_editor.js:33-36` reads `[name=csrfmiddlewaretoken]` from the `<form style="display:none">{% csrf_token %}</form>` block at `editor.html:112`. `postJSON` auto-attaches the `X-CSRFToken` header. ✓

## Next Phase Readiness

- Save-as-template flow is end-to-end functional. Plan 03-04 (Templates section on dashboard + rename + delete endpoints) is unblocked: the engineer can now generate templates, and 03-04 will surface them on the dashboard with rename/delete actions appended under the same Phase 3 banner in `multitrack_editor.js`.
- Plan 03-05 (apply path in `multitrack_create_view` + `MultitrackSessionForm.template` dropdown) is unblocked: source data for testing apply will be templates created by this save endpoint.
- No new external services, env vars, or migrations introduced. Railway deploy is no-op for infrastructure.
- Manual smoke test (optional per plan verification step 4): `python manage.py runserver` → log in → visit `/audiopatch/multitrack/<id>/` → click "Save as Template" → enter a name → confirm success toast and `MultitrackTemplate.objects.filter(created_by=user).count()` increments by 1.

## Self-Check: PASSED

Verified post-write:

- `planner/views.py` contains `def multitrack_template_save(request):` (grep PASS) and `def _resolve_track_source_number(track):` (grep PASS). ✓
- `planner/urls.py` contains `path('multitrack/templates/save/', views.multitrack_template_save, name='multitrack_template_save')` and reverses to `/audiopatch/multitrack/templates/save/`. ✓
- `planner/templates/planner/multitrack/editor.html` contains the `mtsSaveAsTemplate({{ session.id }}, '{{ session.name|escapejs }}')` handler and "Save as Template" label inside `.mts-editor-actions`. ✓
- `planner/static/planner/js/multitrack_editor.js` contains `window.mtsSaveAsTemplate = function (sessionId, sessionName)` inside the IIFE (2-space indent) under the new "Template save / rename / delete (Phase 3 / v3.0)" banner. ✓
- Commit `a838893` exists in `git log --oneline`. ✓
- Commit `1265df9` exists in `git log --oneline`. ✓
- Commit `870a989` exists in `git log --oneline`. ✓
- Commit `816c0ff` exists in `git log --oneline`. ✓

---
*Phase: 03-multitrack-templates*
*Completed: 2026-05-13*
