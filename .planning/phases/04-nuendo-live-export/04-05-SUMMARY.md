---
phase: 04-nuendo-live-export
plan: 05
subsystem: view-layer

tags: [view, url, nuendo-live, http-download, project-scoping, idor-safe, export-error-fallback]

# Dependency graph
requires:
  - phase: 04-nuendo-live-export
    plan: 02
    provides: build_nlpr(session) -> bytes + ExportTemplateError exception class
  - phase: 04-nuendo-live-export
    plan: 03
    provides: planner/data/multitrack/nuendo_live_3_template.nlpr (Mac-saved fixture; D-03 graceful path stays exercised via ExportTemplateError if absent)
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: _safe_filename, _has_enabled_tracks, _editor_context helpers (verbatim reuse); multitrack_export_rpp pattern (structural mirror)
provides:
  - planner/views.py — multitrack_export_nlpr(request, session_id) HTTP download view
  - planner/urls.py — URL route 'multitrack_export_nlpr' mapped to /audiopatch/multitrack/<int:session_id>/export.nlpr/
  - Public reversible URL name 'planner:multitrack_export_nlpr' (consumed by Plan 04-07's toolbar button)
affects: [04-07, editor-toolbar, download-flow]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mirror-of-Phase-1 download view: @staff_member_required + getattr(request, 'current_project') + filter(id=, project=current_project) + _has_enabled_tracks() guard"
    - "ExportTemplateError caught at view layer (D-03) — graceful editor.html re-render with export_error banner instead of bubbling 500"
    - "Content-Disposition filename uses lowercase .nlpr suffix (matches Steinberg convention; differs from Reaper's .RPP uppercase)"

key-files:
  created: []
  modified:
    - "planner/views.py — added 95 lines: import line for build_nlpr/ExportTemplateError + section-header comment + multitrack_export_nlpr view function"
    - "planner/urls.py — added 1 line + 1-line comment update: path('multitrack/<int:session_id>/export.nlpr/', views.multitrack_export_nlpr, name='multitrack_export_nlpr')"

key-decisions:
  - "Auth decorator confirmed as @staff_member_required (RESEARCH Pitfall 5 — VERIFIED). Phase 1's CR-01/CR-02 retightened only AJAX mutate endpoints (set_color/set_label/set_enabled/remove_track/reorder), NOT download views. multitrack_export_rpp at planner/views.py:6875 still uses @staff_member_required as of this plan; Phase 4 matches verbatim."
  - "Section-header comment block inserted between multitrack_export_rtracktemplate and the Phase 2 CSV-import header. References CR-01/CR-02 fix scope in-source so future readers don't 'helpfully' retighten the decorator without checking the AJAX-vs-download distinction."
  - "Both error paths (no-enabled-tracks AND missing-fixture) use the EXACT same _editor_context call shape as Phase 1's no-tracks fallback at planner/views.py:6900-6912. Only the export_error string content differs (D-03 banner copy verbatim per CONTEXT.md). Keeps the editor template's contract uniform across export attempts."

patterns-established:
  - "Try/except ExportTemplateError → editor.html render: established as the standard graceful-degradation path for any future template-injection exporter that depends on a bundled vendor fixture (parallel to D-03's contract). Future Phase 5+ exporters that share the lxml-template-injection pattern can mirror this two-branch error structure verbatim."

requirements-completed: [NLP-01, NLP-02]

# Metrics
duration: 6m
completed: 2026-05-14
---

# Phase 4 Plan 05: Nuendo Live View + URL Summary

**Wired the HTTP entry point for Nuendo Live `.nlpr` export — `multitrack_export_nlpr` view at planner/views.py and `name='multitrack_export_nlpr'` URL route at planner/urls.py. Mirror-of-Phase-1 structure: `@staff_member_required` auth gate, project-scoped IDOR-safe session lookup, `_has_enabled_tracks()` guard, plus a `try/except ExportTemplateError` graceful-degradation path that re-renders `editor.html` with the D-03 banner copy when the bundled fixture is missing or malformed.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-14T14:29:15Z
- **Completed:** 2026-05-14T14:35:18Z
- **Tasks:** 2 / 2
- **Files modified:** 2 (`planner/views.py` +95 lines net; `planner/urls.py` +1 line + 1-line comment update)
- **Files created:** 0

## Accomplishments

- `planner/views.py` contains a new `multitrack_export_nlpr(request, session_id)` function immediately after `multitrack_export_rtracktemplate`, with:
  - `@staff_member_required` decorator (RESEARCH Pitfall 5 — verbatim match with Phase 1 download views).
  - `getattr(request, 'current_project', None) → redirect('/')` guard (matches Phase 1).
  - `MultitrackSession.objects.filter(id=session_id, project=current_project).select_related('console').first()` — IDOR-closed combined filter (T-04-14).
  - `_has_enabled_tracks(session)` guard rendering `editor.html` with the verbatim Phase 1 no-tracks banner via `_editor_context(...)`.
  - `try: body = build_nlpr(session)` wrapped in `except ExportTemplateError` that re-renders `editor.html` with the D-03 banner copy.
  - `HttpResponse(body, content_type='application/xml; charset=utf-8')` + `Content-Disposition: attachment; filename="<_safe_filename(session.name)>.nlpr"`.
- A new section-header comment block precedes the view, documenting the auth-decorator decision (CR-01/CR-02 scope) inline so future readers don't accidentally retighten the gate.
- One new exporter-import line at planner/views.py:6854: `from .utils.nuendo_live_export import build_nlpr, ExportTemplateError`. Placed immediately under the existing `from .utils.reaper_export import build_rpp, build_rtracktemplate` line (matches the one-import-per-module convention in this section).
- `planner/urls.py` contains a new route entry slotted in immediately after the two Reaper file-download routes at the previous `:139`: `path('multitrack/<int:session_id>/export.nlpr/', views.multitrack_export_nlpr, name='multitrack_export_nlpr')`. The section comment header was updated from `# File downloads (Plan 04)` to `# File downloads (Plan 04 + Phase 4 Plan 05)`.
- `reverse('planner:multitrack_export_nlpr', args=[42])` returns `/audiopatch/multitrack/42/export.nlpr/` (the `/audiopatch/` prefix is added by `audiopatch/urls.py` mounting `planner.urls`).
- `python manage.py check` reports `System check identified no issues (0 silenced)`.
- `python manage.py makemigrations planner --dry-run` reports `No changes detected in app 'planner'` (CLAUDE.md "additive migrations only" naturally satisfied — view + URL only).
- `python manage.py test planner.tests.test_reaper_export -v 1` → 42/42 pass in 1.157s (Phase 1 Reaper byte-stable contract intact).
- `python manage.py test planner.tests.test_nuendo_live_export -v 1` → 3/3 pass in 0.153s (Plan 04 ID-uniqueness + bonus structural checks intact).
- `python manage.py test planner -v 0` → **95/95** pass in 4.745s (no regression anywhere in the planner suite).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add `multitrack_export_nlpr` view to `planner/views.py`** — `905b87d` (feat). Adds the import line, section-header comment, and the full view function with both error-path branches (no-tracks + missing-fixture).
2. **Task 2: Register URL route for `multitrack_export_nlpr`** — `7216f52` (feat). One new `path(...)` line + comment header update.

_Note: Plan 04-05 is `type: execute`, not `tdd`. Both commits are `feat(...)`; no RED/GREEN/REFACTOR cycle applies._

## Files Created/Modified

- **Created:** none.
- **Modified:**
  - `planner/views.py` (+95 / -0). Three discrete additions:
    1. One-line import: `from .utils.nuendo_live_export import build_nlpr, ExportTemplateError` (immediately under the existing `reaper_export` import).
    2. Section-header comment block (7 lines) before the new view, referencing CR-01/CR-02 scope so the auth decorator decision is documented in-source.
    3. `multitrack_export_nlpr(request, session_id)` function body — 75 lines including docstring (failure modes + NLP-01..06 mapping) + four control-flow branches (no-project / no-session / no-tracks / fixture-error) + success path.
  - `planner/urls.py` (+2 / -1). One-line URL pattern addition + section comment-header extension.

## Decisions Made

- **Auth decorator: `@staff_member_required` (NOT `@login_required` + viewer-block).** RESEARCH Pitfall 5 verified the current state of Phase 1's two download views (`multitrack_export_rpp` at `:6875`, `multitrack_export_rtracktemplate` at `:6922`) — both still use `@staff_member_required`. CR-01/CR-02's retightening was scoped to AJAX *mutate* endpoints (`set_color`, `set_label`, `set_enabled`, `remove_track`, reorder — which use `@login_required` + `_multitrack_viewer_block` at `planner/views.py:6697-6710`). Downloads stayed on the legacy gate. Documented in-source via the section-header comment so future readers don't accidentally drift from the Phase 1 sibling.
- **Both error paths use the same `_editor_context` shape, only `export_error` text differs.** Keeps the editor template's contract uniform — no special-case context flags for fixture errors vs. no-track errors. The two branches differ only in the user-facing message string per D-03 / CONTEXT.md.
- **`Content-Type: application/xml; charset=utf-8` (not `text/plain`).** Diverges from Reaper's `text/plain` content type because `.nlpr` *is* XML — the MIME type signals this to browsers and any downstream tooling. The Nuendo Live 3 parser doesn't check `Content-Type` (it's a file-open dialog, not a web fetch), but RFC 7303 + general hygiene argue for the correct MIME label.
- **Filename suffix `.nlpr` (lowercase).** Matches Steinberg's convention in their saved files. Diverges from Reaper's uppercase `.RPP` — both are documented in the plan-locked code and align with each format's native convention.
- **`HttpResponse(body, ...)` works correctly with `bytes` input.** `build_nlpr` returns `bytes` from `etree.tostring(..., xml_declaration=True, encoding='utf-8')`. Django's `HttpResponse` accepts `bytes` directly; no encoding step needed.

## Deviations from Plan

None — plan executed exactly as written. All `<verify>` automated checks pass and all 11 `<acceptance_criteria>` items across Task 1 + Task 2 are satisfied, with a single mechanical clarification noted below.

### Acceptance-criterion clarification

The Task 1 acceptance criterion `grep -c 'Nuendo Live export is unavailable on this server' planner/views.py` returns `1` is satisfied by **string-concatenation semantics, not literal line-grep**. The plan-prescribed code in `<action>` wraps the banner copy across three adjacent string literals for PEP-8 line-length compliance:

```python
export_error='Nuendo Live export is unavailable on '
             'this server — bundled template missing '
             'or malformed. Contact support.',
```

Python concatenates these at parse time to the exact target string `'Nuendo Live export is unavailable on this server — bundled template missing or malformed. Contact support.'`. A literal grep against the source-text form returns `0` because the substring `'on this'` is split across two lines. Substring greps of either fragment (`'Nuendo Live export is unavailable on'` or `'bundled template missing'`) each return `1`. The runtime behavior is correct — the banner copy reaches the editor template verbatim per CONTEXT.md D-03. The plan's `<action>` block prescribes exactly this wrapped form, so no Rule-1 fix is warranted.

## Issues Encountered

- **`python` not on PATH; used `./venv/bin/python` instead.** Same local-dev quirk Plan 04-01 and Plan 04-02 noted in their SUMMARY.md files. Resolution: prefix all verification commands with `./venv/bin/`. Railway deploys are unaffected (Railway's startCommand uses the appropriate interpreter).
- **PreToolUse:Edit hook fired twice as a "READ-BEFORE-EDIT" advisory** despite views.py and urls.py having been read multiple times in this session before each Edit. Both Edits succeeded on first attempt; the hook is informational, not blocking. No work was lost. Identical to Plan 04-02's note about the same hook.

## User Setup Required

None — no auth gates, no manual config, no external API keys. Plan 04-05 is pure server-side wiring.

**Optional HUMAN-UAT (deferred until Plan 04-07 lands the toolbar button):** Once Plan 04-07 adds the visible `Export to Nuendo Live (.nlpr)` button in the editor toolbar, Charlie should:
1. Open an existing multitrack session in the editor.
2. Click the new `.nlpr` button.
3. Confirm browser downloads a file named `<session-name>.nlpr` with `Content-Type: application/xml; charset=utf-8`.
4. Open the downloaded file in Nuendo Live 3 (Mac OK per D-02 amendment).
5. Verify track count, names (outer + inner DeviceAttributes), and Farb palette indices match expectations.

The view + URL are reachable today via direct URL (`/audiopatch/multitrack/<id>/export.nlpr/`) for any staff user with a session in their `current_project` — Plan 04-07 only changes the discoverability surface.

## Threat Flags

None — Plan 04-05's surface (one view function + one URL route) is fully contained by the plan's `<threat_model>` entries T-04-13 through T-04-19:

- **T-04-13 (Spoofing — unauthenticated request):** mitigated by `@staff_member_required` decorator.
- **T-04-14 (Tampering — cross-tenant IDOR via session_id):** mitigated by combined filter `filter(id=session_id, project=current_project)`.
- **T-04-15 (Tampering — header injection via session name):** mitigated by reusing `_safe_filename()` verbatim from Phase 1.
- **T-04-16 (Repudiation — no audit log of downloads):** accepted per RESEARCH (Phase 1 doesn't log downloads either).
- **T-04-17 (Information Disclosure — cross-tenant data leak):** mitigated; `build_nlpr` is a pure function of the project-scoped session, no out-of-band tenant data reachable.
- **T-04-18 (DoS — repeated downloads of huge sessions):** accepted per RESEARCH §Security (~30-50 MB peak for 1000-track session).
- **T-04-19 (Elevation of Privilege — bypassing `@staff_member_required`):** mitigated; Django stdlib decorator has no known bypass path.

No new network endpoints beyond the documented one, no new auth paths, no new schema, no new file-write surface, no new trust boundaries.

## TDD Gate Compliance

N/A — plan `type: execute`, not `type: tdd`. No RED/GREEN gates apply.

## Self-Check: PASSED

Verified before STATE.md update:

- `planner/views.py`:
  - `grep -c 'def multitrack_export_nlpr'` → 1 (FOUND)
  - `grep -c 'from .utils.nuendo_live_export import build_nlpr, ExportTemplateError'` → 1 (FOUND)
  - `grep -c 'application/xml; charset=utf-8'` → 2 (FOUND; one in view body, one in docstring)
  - `grep -c '\.nlpr"'` → 1 (FOUND; the Content-Disposition filename suffix)
  - `grep -c 'except ExportTemplateError'` → 1 (FOUND)
  - `grep -B5 'def multitrack_export_nlpr' planner/views.py | grep -c '@staff_member_required'` → 1 (FOUND; decorator immediately above)
  - Substring greps `'Nuendo Live export is unavailable on'` and `'bundled template missing'` → each 1 (FOUND; the D-03 banner copy, wrapped across 2 lines per PEP-8)
- `planner/urls.py`:
  - `grep -c "name='multitrack_export_nlpr'"` → 1 (FOUND)
  - `grep -c 'multitrack/<int:session_id>/export\.nlpr/'` → 1 (FOUND)
  - `grep -c 'views\.multitrack_export_nlpr'` → 1 (FOUND)
- Django runtime:
  - `python manage.py check` → 0 issues (FOUND)
  - `python manage.py makemigrations planner --dry-run` → `No changes detected in app 'planner'` (FOUND)
  - `reverse('planner:multitrack_export_nlpr', args=[42])` → `/audiopatch/multitrack/42/export.nlpr/` (FOUND; ends with `/multitrack/42/export.nlpr/`)
- Tests:
  - `planner.tests.test_reaper_export` → 42/42 OK in 1.157s (FOUND; Phase 1 byte-stable Reaper contract intact)
  - `planner.tests.test_nuendo_live_export` → 3/3 OK in 0.153s (FOUND; Plan 04 D-09 + bonus tests intact)
  - Full `planner` suite → 95/95 OK in 4.745s (FOUND; no regression)
- Git:
  - Task 1 commit `905b87d` exists in `git log --oneline -3` (FOUND)
  - Task 2 commit `7216f52` exists in `git log --oneline -3` (FOUND)
  - Zero unexpected deletions in either commit (FOUND; `git diff --diff-filter=D` empty)

## Next Phase Readiness

- **Plan 04-05 deliverable is complete and fully verified.** The `.nlpr` download endpoint is live at `/audiopatch/multitrack/<int:session_id>/export.nlpr/` for any staff user with a session in their `current_project`. Direct-URL hits work today; only the visible toolbar button is missing.
- **Plan 04-07 (toolbar button) is now unblocked.** The `reverse('planner:multitrack_export_nlpr', args=[session.id])` URL is stable and reachable. Plan 04-07 only needs to add one `<a>` anchor in `planner/templates/planner/multitrack/editor.html` per D-11 / D-13.
- **HUMAN-UAT for NLP-02 remains deferred** to after Plan 04-07 — needs the visible button to drive the end-to-end click → save-`.nlpr` → open-in-Nuendo-Live-3 path. Charlie's Mac + Nuendo Live 3 are the test rig per CONTEXT.md D-02 (amended 2026-05-13).
- **The D-03 graceful-degradation path is exercisable today** by temporarily renaming `planner/data/multitrack/nuendo_live_3_template.nlpr` aside and hitting the export URL with an enabled-track session — should render `editor.html` with the banner copy `"Nuendo Live export is unavailable on this server — bundled template missing or malformed. Contact support."` instead of 500-ing. (Not exercised in this plan's verification run; the real fixture is in place from Plan 04-03 and the ExportTemplateError exception class is already exercised in `planner.tests.test_nuendo_live_export`.)

---
*Phase: 04-nuendo-live-export*
*Completed: 2026-05-14*
