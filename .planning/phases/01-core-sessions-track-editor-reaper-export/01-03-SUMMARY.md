---
phase: 01-core-sessions-track-editor-reaper-export
plan: 03
subsystem: web
tags: [django, views, forms, urls, multitrack, idor, project-scoping, page-render]

# Dependency graph
requires:
  - phase: 01
    plan: 01
    provides: MultitrackSession + MultitrackTrack models, _source_model_for helper, MultitrackSessionAdmin redirect target
provides:
  - MultitrackSessionForm (planner/forms.py) — ModelForm with current-project console scoping, MTS-02 unique-name validation, Nuendo-Live server-side reject
  - Seven page-render views in planner/views.py — multitrack_dashboard, multitrack_editor, multitrack_create_view, multitrack_edit_view, multitrack_duplicate, multitrack_rename, multitrack_delete
  - Two private helpers in planner/views.py — _build_picker_data (D-09 already-added-row hiding) and _editor_context (canonical context contract for the editor template — Plan 04's no-enabled-tracks fallback also routes through this)
  - Seven URL routes under /audiopatch/multitrack/* with planner:multitrack_* names
  - Resolves the admin-bounce target planner:multitrack_dashboard owned by Plan 01-01
affects: [01-04, 01-05, 01-06]

# Tech tracking
tech-stack:
  added: []  # All from existing Django 5.x stack — no new dependencies
  patterns:
    - "ModelForm with request= kwarg for project-scoped queryset narrowing (avoids hidden-field tampering)"
    - "Combined filter(id=X, project=current_project).first() for IDOR-safe single-row lookup"
    - "Page-render redirect (graceful degrade) vs AJAX 4xx JSON for missing-row handling"
    - "Shared context-builder helper (_editor_context) so every renderer of one template gets the same context contract"
    - "bulk_create for child-row duplication (single SQL INSERT)"

key-files:
  created: []
  modified:
    - "planner/forms.py (+100 lines, -2 — appended MultitrackSessionForm + Console/MultitrackSession imports)"
    - "planner/views.py (+345 lines, -2 — appended seven views + two helpers + model/form imports)"
    - "planner/urls.py (+29 lines — appended Multitrack Session Builder block with seven routes + Plan-04 reservation comments)"

key-decisions:
  - "MultitrackSessionForm takes request= as a keyword arg (not as a hidden form field). This pattern blocks tampered POSTs that try to re-target the project."
  - "Cross-project access redirects to dashboard (page) or returns 404 JSON (AJAX) rather than raising Http404. Plan rationale: graceful degrade, no existence leak."
  - "_editor_context is the single source of truth for the editor template's context dict. Plan 04's no-enabled-tracks export fallback will route through this helper instead of inlining a partial dict."
  - "URL contract for Plan-04-owned routes is reserved with comment lines — those names are NOT registered here (would cause NoReverseMatch on import). Plan 04 replaces the comment block with the actual path() entries."
  - "multitrack_duplicate copies tracks via bulk_create (single SQL INSERT). bulk_create skips pre/post-save signals — fine because Phase 1 has no signals on MultitrackTrack itself; the post_delete orphan-conversion receivers are on the channel models, not on MultitrackTrack.save."

requirements-completed:
  - MTS-01
  - MTS-02
  - MTS-03
  - MTS-04
  - MTS-05
  - MTS-06

# Metrics
duration: ~6min
completed: 2026-05-10
---

# Phase 1 Plan 03: Multitrack Page-Render Views, Form, and URL Wiring Summary

**Page-render views (list / create / edit-metadata / duplicate / rename / delete) + the MultitrackSessionForm + URL routes for the Multitrack Session Builder, with IDOR-safe project scoping and a shared `_editor_context` helper that locks the editor template's context contract for Plan 04 to reuse.**

## Performance

- **Duration:** ~6 min
- **Tasks:** 3
- **Files modified:** 3 (no files created in this plan)

## Accomplishments

- `MultitrackSessionForm` validates name uniqueness per-project (MTS-02), rejects `nuendo_live` server-side as belt + suspenders against tampered POSTs, and auto-fills `instance.project = request.current_project` on create — no project field is exposed to the form, closing the project-swap surface (T-03-02 / T-03-07).
- Seven page-render views appended to `planner/views.py`, each starting with the defensive `current_project = getattr(request, 'current_project', None)` guard and using `filter(id=X, project=current_project).first()` for every single-row lookup (T-03-01 mitigation).
- Two private helpers extracted: `_build_picker_data` precomputes the four channel lists with already-added rows hidden (D-09; closes Pitfall 7 — picker doesn't re-fetch on every keystroke); `_editor_context` is the single source of truth for the editor template's context contract (`session`, `tracks`, `picker_data_json`, `auto_open_picker`, `total_count`, `over_count`, plus `**extras`).
- `multitrack_duplicate` copies the source session and all tracks in two SQL statements (one create + one `bulk_create`) and returns `{ok, session_id, redirect_url}` so the JS can navigate after success.
- Seven URL routes registered under `/audiopatch/multitrack/*` with the `planner:multitrack_*` namespace; `python manage.py check` exits 0 and every reverse() call resolves.
- Plan 01-01's admin-bounce target `planner:multitrack_dashboard` now resolves to `/audiopatch/multitrack/`.

## Task Commits

Each task was committed atomically with `--no-verify`:

1. **Task 1: Append MultitrackSessionForm to planner/forms.py** — `2f99fc6` (feat)
2. **Task 2: Append _editor_context helper + seven page-render views to planner/views.py** — `5d247cf` (feat)
3. **Task 3: Add URL routes for the seven views to planner/urls.py** — `67a85aa` (feat)

## URL Contract (Plan 03 — seven of the eventual sixteen routes)

| Name | URL | Method | View | Returns |
|---|---|---|---|---|
| `planner:multitrack_dashboard` | `/audiopatch/multitrack/` | GET | `multitrack_dashboard` | renders `planner/multitrack/dashboard.html` |
| `planner:multitrack_create` | `/audiopatch/multitrack/new/` | GET / POST | `multitrack_create_view` | renders `new_session.html` (mode='create'); POST -> redirects to editor on success |
| `planner:multitrack_editor` | `/audiopatch/multitrack/<int:session_id>/` | GET | `multitrack_editor` | renders `editor.html` via `_editor_context(session)` |
| `planner:multitrack_edit` | `/audiopatch/multitrack/<int:session_id>/edit/` | GET / POST | `multitrack_edit_view` | renders `new_session.html` (mode='edit'); POST -> redirects to editor on success |
| `planner:multitrack_duplicate` | `/audiopatch/multitrack/<int:session_id>/duplicate/` | POST | `multitrack_duplicate` | JSON `{ok, session_id, redirect_url}` or `{error, status: 400/404/409/500}` |
| `planner:multitrack_rename` | `/audiopatch/multitrack/<int:session_id>/rename/` | POST | `multitrack_rename` | JSON `{ok, name}` or `{error, status: 400/404/409/500}` |
| `planner:multitrack_delete` | `/audiopatch/multitrack/<int:session_id>/delete/` | POST | `multitrack_delete` | JSON `{ok, redirect_url}` or `{error, status: 400/404/500}` |

Plan 04 will register the remaining nine routes (reorder, add-tracks, capacity-check, set-color, set-label, set-enabled, remove-track, export.rpp, export.rtracktemplate). Their URL names are reserved as comments in `planner/urls.py` — Plan 04 replaces the comment block with `path()` entries.

## View Function Signatures (so Plan 04 / Plan 06 can call without re-deriving)

### `MultitrackSessionForm(*args, request=None, **kwargs)`

- `request` kwarg is REQUIRED (form raises `ValidationError('No active project — cannot validate name.')` otherwise).
- `Meta.fields` whitelist: `name`, `console`, `target_daw`, `feed_source`, `track_order_mode`, `recorder_capacity`, `notes`. **`project` is NOT in the field list — POST cannot inject it.**
- Console queryset narrowed to `Console.objects.filter(project=request.current_project)` in `__init__`.
- `clean_name` raises with verbatim UI-SPEC string: `A session named "{name}" already exists in this project. Pick a different name.`
- `clean_target_daw` raises if value is `'nuendo_live'`.
- `save(commit=True)` — on create, sets `instance.project = self.request.current_project`.

### `multitrack_dashboard(request)` — GET

- Decorator: `@staff_member_required`
- Returns `render(..., 'planner/multitrack/dashboard.html', {sessions, current_project})` where sessions are `select_related('console').order_by('-updated_at')`.

### `multitrack_editor(request, session_id)` — GET

- Decorator: `@staff_member_required`
- Missing `current_project` -> `redirect('/')`.
- Cross-project / missing session -> `redirect('planner:multitrack_dashboard')`.
- Returns `render(..., 'planner/multitrack/editor.html', _editor_context(session))`.

### `multitrack_create_view(request)` — GET / POST

- Decorator: `@staff_member_required`
- POST: `MultitrackSessionForm(request.POST, request=request)`. On valid: `redirect('planner:multitrack_editor', session_id=session.id)`.
- GET / invalid POST: render `new_session.html` with `{form, mode: 'create'}`.

### `multitrack_edit_view(request, session_id)` — GET / POST

- Decorator: `@staff_member_required`
- Same form-handling pattern as create, but with `instance=session`. On valid POST: `redirect('planner:multitrack_editor', session_id=session.id)`.
- Render context: `{form, session, mode: 'edit'}`.

### `multitrack_duplicate(request, session_id)` — POST

- Decorator: `@require_POST`
- Body: JSON `{new_name?: str}` (defaults to `'{original} (copy)'`).
- Returns: `{ok: True, session_id: int, redirect_url: str}` (200) or `{error: str}` with status `400` (no project), `404` (session not found / cross-project), `409` (name conflict — verbatim UI-SPEC string), or `500` (other).

### `multitrack_rename(request, session_id)` — POST

- Decorator: `@require_POST`
- Body: JSON `{name: str}` (required, max 100 chars).
- Returns: `{ok: True, name: str}` (200) or `{error: str}` with status `400` (no project / empty name / >100 chars), `404` (cross-project), `409` (name conflict — verbatim UI-SPEC string), or `500` (other).
- Server side: `session.save(update_fields=['name', 'updated_at'])`.

### `multitrack_delete(request, session_id)` — POST

- Decorator: `@require_POST`
- Body: empty (or any JSON — ignored).
- Returns: `{ok: True, redirect_url: '/audiopatch/multitrack/'}` (200) or `{error: str}` with status `400` / `404` / `500`.
- Cascades to all `MultitrackTrack` rows via the FK CASCADE configured in Plan 01-01.

### `_editor_context(session, tracks=None, **extras)` — helper

**Canonical builder for `planner/multitrack/editor.html` context. Every render of that template MUST go through this function.**

Returns a dict with keys (defaults shown when not overridden by extras):

| Key | Value |
|---|---|
| `session` | the `MultitrackSession` instance |
| `tracks` | `list(session.tracks.all().order_by('track_number'))` when `tracks=None`, else `list(tracks)` |
| `picker_data_json` | `json.dumps(_build_picker_data(session, tracks))` |
| `auto_open_picker` | `True` iff `tracks` is empty (D-12) |
| `total_count` | `len(tracks)` |
| `over_count` | `max(0, total_count - session.recorder_capacity)` when capacity is set, else `0` |

Extras take precedence over computed defaults. Plan 04 calls this helper with `tracks=enabled_tracks_qs, export_error='...', auto_open_picker=False` for the no-enabled-tracks export fallback.

### `_build_picker_data(session, existing_tracks)` — helper

Returns `{inputs, aux, matrix, stereo}` lists where each list is `[{id, label, channel_number, dante_number}, ...]`. Already-added rows are excluded via `.exclude(id__in=used_ids[source_type])` per source type — closes Pitfall 7 (picker re-fetch loop) by computing the full picker data ONCE at editor-page render time.

## Threat Mitigations Applied

All threats in the plan's `<threat_model>` are mitigated as designed:

- **T-03-01 (IDOR):** Every single-row lookup uses `filter(id=session_id, project=current_project).first()`. Cross-project session_id returns 404 JSON or dashboard redirect — never reveals existence.
- **T-03-02 (project swap):** `MultitrackSessionForm.save` overrides `instance.project = self.request.current_project` on create. `project` is not in `Meta.fields`, so POST cannot inject it.
- **T-03-03 (Nuendo Live bypass):** `clean_target_daw` rejects `nuendo_live` server-side regardless of any HTML `disabled` attribute Plan 05 will add.
- **T-03-04 (CSRF):** Django CSRF middleware is enabled globally; all POST endpoints rely on it. Zero `@csrf_exempt` decorators added.
- **T-03-05 / T-03-06 (XSS):** `name` and `notes` are stored as plain CharField/TextField; auto-escape applies in Plan 05 (template authors must NOT use `|safe`).
- **T-03-07 (mass-assignment):** `Meta.fields` whitelist is explicit. `project`, `created_at`, `updated_at`, `id` are NOT in the list.
- **T-03-08 / T-03-09 / T-03-10:** accepted as documented (DoS / race / generic str(e) errors — existing codebase pattern).

## Deviations from Plan

None — plan executed exactly as written. The three `<read_first>` reads / verifications all passed first try.

## Issues Encountered

- Worktree branch was created from a base ahead of the expected merge-base (`e7561dc` instead of `97cb1df`). Hard-reset to the expected base per `<worktree_branch_check>` protocol before starting work; no user changes lost (fresh worktree).
- The pre-existing `RuntimeWarning: Model 'planner.audiochecklist' was already registered` warning surfaces under the local Python 3.14 dev environment whenever `manage.py check` or any Django bootstrap runs. This is a pre-existing repo issue (planner.models registers AudioChecklist twice somewhere upstream of this plan); out of scope per SCOPE BOUNDARY rule. Logged for future cleanup.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 04 (Wave 3):** unblocked — the `planner:multitrack_*` URL namespace exists, the `_editor_context` helper is in place for the no-enabled-tracks export fallback, and the seven page-render views are committed. Plan 04 will append nine more views and replace the URL-comment block with nine `path()` entries.
- **Plan 05 (templates):** `_editor_context` defines the binding contract (`session`, `tracks`, `picker_data_json`, `auto_open_picker`, `total_count`, `over_count`). The template MUST consume these context vars without computing them inline.
- **Plan 06 (JS):** the seven URL names are reserved — `fetch()` calls in Plan 06 reference them via `{% url %}` tags rendered into JS bootstrap blocks.

## Self-Check

Verified all claims in this SUMMARY against the worktree state.

**Modified files (git diff vs plan base 97cb1df):**
- FOUND: `planner/forms.py` (+100 / -2)
- FOUND: `planner/views.py` (+345 / -2)
- FOUND: `planner/urls.py` (+29 / 0)

**Commits exist:**
- FOUND: `2f99fc6` Task 1 (MultitrackSessionForm)
- FOUND: `5d247cf` Task 2 (views + helpers)
- FOUND: `67a85aa` Task 3 (URL routes)

**Verification commands:**
- FOUND: `python manage.py check` exits 0
- FOUND: All seven `reverse('planner:multitrack_*')` calls resolve
- FOUND: All view functions and helpers importable from `planner.views`
- FOUND: `MultitrackSessionForm` importable from `planner.forms`

## Self-Check: PASSED

---

*Phase: 01-core-sessions-track-editor-reaper-export*
*Completed: 2026-05-10*
