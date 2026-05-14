---
phase: 04-nuendo-live-export
plan: 07
subsystem: ui-template
tags: [template, html, toolbar, nuendo-live, multitrack-editor, url-reverse]

# Dependency graph
requires:
  - phase: 04-nuendo-live-export
    plan: 05
    provides: URL name 'planner:multitrack_export_nlpr' mapped to /audiopatch/multitrack/<int:session_id>/export.nlpr/ — the {% url %} target
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: mts-btn / mts-btn-success / mts-btn-secondary toolbar class grammar; the existing two Reaper anchors at editor.html:77-81 as structural analogs; mts-toolbar-actions div
provides:
  - planner/templates/planner/multitrack/editor.html — third toolbar anchor 'Export to Nuendo Live (.nlpr)' immediately after the Reaper Track Template anchor
  - End-to-end clickable .nlpr download path: editor toolbar → multitrack_export_nlpr view → build_nlpr(session) → file download
affects: [phase-04-complete, human-uat-nlp-02, human-uat-nlp-01-through-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reused mts-btn mts-btn-success class verbatim (D-13) — no new CSS classes introduced for the third export anchor"
    - "Always-visible export buttons regardless of session.target_daw (D-11) — confirmed by absence of {% if %} wrapper; matches Phase 1's posture on the two Reaper anchors"

key-files:
  created: []
  modified:
    - "planner/templates/planner/multitrack/editor.html — +2 lines: one <a class='mts-btn mts-btn-success'> anchor with {% url 'planner:multitrack_export_nlpr' session.id %} href and 'Export to Nuendo Live (.nlpr)' label"

key-decisions:
  - "No title= attribute on the new anchor (deliberate divergence from the Reaper Track Template sibling). Rationale documented in plan <action>: .nlpr is self-explanatory as a Nuendo Live filename, unlike .RTrackTemplate which engineers wouldn't recognize without the 'import via Track menu' hint."
  - "Reused the exact mts-btn mts-btn-success class pair from the .RPP anchor rather than introducing a Nuendo-specific class (D-13 locked this). The Phase 4 plan deliberately ships zero new CSS classes."
  - "Single .nlpr button — no separate 'Nuendo Live track template' variant (D-14). Per spec §'Nuendo Live (.nlpr)': Nuendo Live has no track-archive format like full Nuendo's .npr — .nlpr is the only target."

patterns-established:
  - "Atomic template-only plan pattern: the smallest plan in a phase can be a single anchor insertion when all upstream wiring (view + URL + utility module + form gates) lands in earlier waves. Future modules adding a new export format alongside existing ones (e.g. Pro Tools .txt in v2.1 per PT-01) can mirror this exact one-edit pattern in Wave 3."

requirements-completed: [NLP-01]

# Metrics
duration: ~3min
completed: 2026-05-14
---

# Phase 4 Plan 07: Nuendo Live Toolbar Button Summary

**Third export anchor `<a class="mts-btn mts-btn-success" href="{% url 'planner:multitrack_export_nlpr' session.id %}">Export to Nuendo Live (.nlpr)</a>` added to the multitrack editor's `mts-toolbar-actions` div, completing the end-to-end NLP-01 user flow — engineers can now click to download `.nlpr` files from any session regardless of `target_daw`.**

## Performance

- **Duration:** ~3 min (template edit + verify); ~30 min wall-clock including upfront CONTEXT.md / PATTERNS.md re-reads
- **Started:** 2026-05-14T14:39:48Z
- **Completed:** 2026-05-14T15:10:00Z
- **Tasks:** 1 / 1
- **Files modified:** 1

## Accomplishments

- `planner/templates/planner/multitrack/editor.html` now renders three toolbar export anchors in the documented order: Reaper (`.RPP`, success), Reaper Track Template (secondary), and Nuendo Live (`.nlpr`, success). All three render regardless of `session.target_daw` per D-11.
- The new anchor reuses the existing `mts-btn mts-btn-success` class pair (no new CSS classes — D-13).
- `{% url 'planner:multitrack_export_nlpr' session.id %}` resolves at render time to `/audiopatch/multitrack/<id>/export.nlpr/` (Plan 04-05's URL is live).
- No `{% if %}` wrapper guards the new button (D-11 — always-visible posture matches the two Reaper anchors).
- End-to-end render check confirmed: `render_to_string('planner/multitrack/editor.html', ctx)` against a minimal context produces HTML containing both `Export to Nuendo Live (.nlpr)` and the reversed URL `/multitrack/1/export.nlpr/`. No `NoReverseMatch` raised.
- `python manage.py check` → 0 issues. `python manage.py makemigrations planner --dry-run` → No changes detected (no model changes; template-only edit).
- `python manage.py test planner.tests.test_nuendo_live_export -v 1` → 3/3 OK in 0.154s.
- `python manage.py test planner -v 0` → **95/95** OK in 4.649s (no regression anywhere in the planner suite).

## Task Commits

Each task was committed atomically:

1. **Task 1: Append Nuendo Live toolbar button to editor.html** — `eb5dfaf` (feat). Two lines inserted (the new `<a>` opening tag + the line carrying the href and label) between the existing Reaper Track Template anchor and the closing `</div>` of `mts-toolbar-actions`.

_Note: Plan 04-07 is `type: execute`, not `tdd`. The single commit is `feat(...)`; no RED/GREEN/REFACTOR cycle applies._

## Files Created/Modified

- **Created:** none.
- **Modified:**
  - `planner/templates/planner/multitrack/editor.html` (+2 / -0). The two new lines are inserted between line 81 (the closing `</a>` of the Reaper Track Template anchor) and line 82 (the closing `</div>` of `mts-toolbar-actions`). The result is a three-anchor toolbar row that mirrors the plan's locked HTML in the `<interfaces>` block.

## Decisions Made

- **No `title=` attribute on the new anchor** (deliberate divergence from the Reaper Track Template sibling at lines 79-81). The plan's `<action>` documents this: `.nlpr` is self-explanatory as a Nuendo Live filename, unlike `.RTrackTemplate` which engineers wouldn't recognize without the "import via Track menu" hint. The `.RPP` anchor at lines 77-78 also lacks a `title=`, so the new anchor matches its primary-export sibling.
- **Class pair `mts-btn mts-btn-success` reused verbatim** from the `.RPP` anchor (D-13 lock). The Phase 4 plan ships zero new CSS classes; both `.RPP` and `.nlpr` use the primary-success styling because both are full-export-format anchors, while the Reaper Track Template (secondary) is a partial / subset export and uses `mts-btn-secondary` accordingly.
- **No `download` / `target="_blank"` / `onclick` attributes.** Plan 04-05's view sets `Content-Disposition: attachment; filename="...nlpr"`, so the browser triggers the download flow on a plain GET without any client-side hints. Matches the Phase 1 Reaper anchors verbatim.
- **No `{% if %}` wrapper on `session.target_daw`** (D-11 lock). The field's semantic meaning is now "default DAW for new sessions / template signaling" rather than "what buttons appear" — Phase 3 templates carry `target_daw` for legitimate reasons (covered in CONTEXT.md §"Specifics"), so the field stays in place but no longer gates the toolbar.

## Deviations from Plan

None — plan executed exactly as written. The two-line insertion landed verbatim with the indentation prescribed by the plan's `<action>` block (6 spaces from the start of the line, matching the surrounding anchors). All acceptance-criteria grep counts hit their target values on first attempt.

## Issues Encountered

- **`python` not on PATH; used `./venv/bin/python` instead.** Same local-dev quirk every Plan 04-* SUMMARY has noted. Resolution: prefix all verification commands with `./venv/bin/`. Railway deploys are unaffected.
- **PreToolUse:Edit hook fired once as a READ-BEFORE-EDIT advisory** despite editor.html having been read earlier in the session as part of the `<files_to_read>` startup sweep. The edit had already succeeded ("The file ... has been updated successfully.") before the hook reminder appeared. Identical to the same hook's behavior in Plans 04-02 and 04-05.

## User Setup Required

None — pure template edit, no env vars, no API keys, no migrations.

**HUMAN-UAT (now unblocked for NLP-01..05):** Per CONTEXT.md D-02 (amended 2026-05-13) and Plan 04-05's deferred UAT block, Charlie should:

1. Push to `main` (Railway auto-deploys) OR run locally via `./venv/bin/python manage.py runserver`.
2. Open an existing multitrack session in the editor.
3. Confirm the toolbar shows three buttons in order: `Export to Reaper (.RPP)`, `Export to Reaper (Track Template)`, `Export to Nuendo Live (.nlpr)`.
4. Click `Export to Nuendo Live (.nlpr)`.
5. Confirm the browser downloads a file named `<session-name>.nlpr` with `Content-Type: application/xml; charset=utf-8`.
6. Open the `.nlpr` in Nuendo Live 3 on Mac.
7. Verify: track count matches the session's enabled tracks; outer + inner track names match `MultitrackTrack.resolved_label`; Yamaha-palette colors render as the correct Farb indices (Red→0, Orange→1, Yellow→2, Green→5, Sky Blue→8, Blue→10, Purple→12, Pink→14); non-palette / `Off` / `White` tracks render with Nuendo's default appearance.

This is the canonical round-trip test for NLP-02 through NLP-05 (NLP-06 is the only fully-automated assertion per D-09 and was verified in Plan 04-04).

## Threat Flags

None — Plan 04-07's surface (one anchor element wrapping a Django `{% url %}` tag) is fully contained by the plan's `<threat_model>` entries:

- **T-04-22 (Tampering — XSS via `session.id` interpolation):** accepted. `session.id` is a server-side `int` from the ORM, not user input. Django's `{% url %}` reverser produces a safe path string.
- **T-04-23 (Spoofing / CSRF on the GET endpoint):** accepted. The downstream view is GET-only, idempotent, side-effect-free (no DB writes — `build_nlpr` is pure per the trust-boundary docstring). Django's default middleware doesn't require CSRF tokens for GET. Same posture as the Phase 1 Reaper download anchors.

No new network endpoints (Plan 04-05 registered the route), no new auth paths, no new schema, no new trust boundaries.

## TDD Gate Compliance

N/A — plan `type: execute`, not `type: tdd`. No RED/GREEN gates apply.

## Self-Check: PASSED

Verified before STATE.md update:

- `planner/templates/planner/multitrack/editor.html`:
  - `grep -c "{% url 'planner:multitrack_export_nlpr' session.id %}"` → 1 (FOUND)
  - `grep -c 'Export to Nuendo Live (.nlpr)'` → 1 (FOUND)
  - `grep -c 'mts-btn mts-btn-success'` → 2 (FOUND — `.RPP` + `.nlpr`)
  - `grep -c 'multitrack_export_rpp'` → 1 (FOUND, unchanged)
  - `grep -c 'multitrack_export_rtracktemplate'` → 1 (FOUND, unchanged)
  - `grep -c 'multitrack_export_nlpr'` → 1 (FOUND, exactly one new button)
  - `grep -B2 'multitrack_export_nlpr'` shows the previous Reaper Track Template anchor's closing `</a>` and the new anchor's opening `<a class="mts-btn mts-btn-success"` — NO `{% if %}` wrapper (FOUND)
  - New button is inside the `<div class="mts-toolbar-actions">` block per the plan's automated position check (FOUND)
- Django runtime:
  - `python manage.py check` → 0 issues (FOUND)
  - `python manage.py makemigrations planner --dry-run` → `No changes detected in app 'planner'` (FOUND)
  - `reverse('planner:multitrack_export_nlpr', args=[1])` → `/audiopatch/multitrack/1/export.nlpr/` (FOUND, ends with `/multitrack/1/export.nlpr/`)
  - `render_to_string('planner/multitrack/editor.html', ctx)` produces HTML containing both `Export to Nuendo Live (.nlpr)` and `/multitrack/1/export.nlpr/` — no `NoReverseMatch` (FOUND)
- Tests:
  - `planner.tests.test_nuendo_live_export` → 3/3 OK in 0.154s (FOUND)
  - Full `planner` suite → 95/95 OK in 4.649s (FOUND, no regression)
- Git:
  - Task 1 commit `eb5dfaf` exists in `git log --oneline -3` (FOUND)
  - Zero unexpected deletions in the commit (FOUND; `git diff --diff-filter=D HEAD~1 HEAD` empty)

## Next Phase Readiness

- **Plan 04-07 deliverable is complete and fully verified.** The third export button is live in the editor toolbar; clicking it triggers the `.nlpr` download flow end-to-end (Plan 04-05's view + Plan 04-02's exporter + Plan 04-03's bundled fixture).
- **Phase 04 (Nuendo Live Export) is now complete in code.** All 7 plans across 3 waves have shipped:
  - Wave 1 (parallel): Plans 04-01 (model + lxml + comments), 04-02 (pure exporter), 04-03 (Mac-saved fixture), 04-04 (D-09 ID-uniqueness test)
  - Wave 2: Plan 04-05 (view + URL route)
  - Wave 3 (parallel): Plans 04-06 (atomic form gate removal), 04-07 (this — toolbar button)
- **HUMAN-UAT for NLP-01..NLP-05 is now unblocked** — Charlie's Mac + Nuendo Live 3 round-trip is the only remaining gate before `/gsd-transition` or `/gsd-complete-phase` can mark Phase 04 done. NLP-06 (ID/RuntimeID uniqueness) is already fully verified via Plan 04-04's `test_ids_unique`.
- **Phase 05 (Channel Record Defaults) is the only remaining v2.0 phase** per the roadmap. It is independent of Phase 04 (depends only on Phase 1), so it could in principle start in parallel with Charlie's Phase 04 round-trip UAT — operator's call via `/gsd-transition` whether to advance now or wait for UAT sign-off.

---
*Phase: 04-nuendo-live-export*
*Completed: 2026-05-14*
