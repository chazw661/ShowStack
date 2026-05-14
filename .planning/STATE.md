---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: milestone
status: ready_to_plan
last_updated: "2026-05-14T20:00:00.000Z"
last_activity: 2026-05-14 -- Phase 04 (Nuendo Live Export) closed: 7 plans shipped, HUMAN-UAT 5/5 required tests passed after fix 9857aec (resolved_yamaha_name → override-only). 95/95 planner tests green; Phase 1 Reaper byte-stability intact; zero migrations
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 22
  completed_plans: 22
  percent: 80
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-09)

**Core value:** ShowStack knows your patch, your labels, and your gear; once entered, that data drives every export your show needs.
**Current focus:** Phase 05 — Channel Record Defaults (next; Phase 04 complete 2026-05-14)

## Current Position

Phase: 5 (next — not started)
Plan: Not started
Status: Ready to plan
Last activity: 2026-05-14 — Phase 04 closed after HUMAN-UAT approval

Progress: [████████░░] 80% (4 of 5 phases complete)

## Roadmap Summary

5 phases, all derived from REQUIREMENTS.md and the canonical spec
(`multitrack_session_builder_spec.md`). Phase 1 carries the bulk of the
work (21 of 38 requirements) because the track editor and Reaper exporter
must ship as one coherent end-to-end capability before importers, templates,
or Nuendo Live can be validated against it.

| Phase | Goal | Reqs | UI |
|-------|------|------|----|
| 1. Core Sessions, Track Editor & Reaper Export | Build a session and export `.RPP` end-to-end | 21 | yes |
| 2. Console CSV Import | Populate channels from CL/QL + Rivage PM CSVs | 5 | — |
| 3. Multitrack Templates | Save/apply reusable session structures | 4 | — |
| 4. Nuendo Live Export | `.nlpr` template-injection exporter via `lxml` | 6 | — |
| 5. Channel Record Defaults | `default_record` + `default_record_color` seed flags | 2 | yes |

Phases 2–5 each depend only on Phase 1; sequential execution per the spec's
ordering rationale (Reaper before Nuendo because plain text is easier to
validate; CSV after editor exists; Templates after sessions exist; polish last).

## Accumulated Context

### From v1.0 Network Health Monitor (scrapped)

- Cloud-hosted ShowStack cannot reliably monitor on-site Dante networks (WiFi/Dante NIC conflicts, mDNS interface binding, link-local discovery). Standalone-app architecture is the correct path; the standalone app lives in a separate codebase.
- Reusable lesson: AJAX polling (2–3 s) is more robust than SSE for ShowStack's request lifecycle. Apply to any future near-real-time UI.
- Phase artifacts archived to `.planning/archive/v1.0-network-monitor/`.

### Open questions flagged for plan-time research

These don't block roadmap finalization but should be answered before the
relevant plans land:

1. **Phase 2 — M7CL CSV path** (already deferred to v2.1 in REQUIREMENTS.md, but if a Studio Manager CL Editor CSV path *also* covers M7CL, confirm before scoping the parser).
2. **Phase 2 — exact CL/QL CSV column structure** depends on which export path the user chose (Studio Manager vs CL Editor vs Console File Converter); confirm against real fixture files before finalizing the parser.
3. **Phase 3 — color-scheme template semantics**: do `MultitrackTemplate.color_scheme` entries apply by name pattern (regex on channel name) or are they manual-only? Spec leaves this open.
4. **Phase 4 — Nuendo Live template fixture**: Charlie must generate and commit `fixtures/nuendo_live_3_template.nlpr` (a fresh empty Nuendo Live 3 session with one default audio track) before the exporter can be implemented. The spec confirms `lxml` (not stdlib ElementTree) is required to preserve formatting.
5. **Phase 4 — Rivage→Farb color mapping table** is not yet defined in the spec (only Yamaha CL/QL→Farb is). Either build the Rivage table during Phase 4 or accept that Rivage tracks export with `Farb` omitted in v2.0.

**Planned Phase:** 4 (Nuendo Live Export) — 7 plans — 2026-05-13T22:49:39.525Z

### From Phase 04 Plan 01 (Wave 1 prerequisites)

- `lxml~=5.3.0` pinned in `requirements.txt`; Railway pip-installs on next deploy via `railway.json` `startCommand`.
- `MultitrackTrack.resolved_yamaha_name` `@property` lives next to `resolved_color` / `resolved_dante_number`. Returns palette NAME (e.g. `'Red'`), not hex — Phase 1 `resolved_color` contract is byte-stable and unchanged.
- `_HEX_TO_YAMAHA_NAME` module-level reverse map (8 entries) is the only structural addition; built once at import time via dict comprehension over `YAMAHA_TO_HEX`, filtering `None` hex values (`'Off'` / `'White'` intentionally unreachable through the override path per D-04).
- Zero migrations created. `python manage.py makemigrations planner --dry-run` reports `No changes detected`. CLAUDE.md "additive migrations only" rule naturally satisfied.
- `planner.tests.test_reaper_export`: 42/42 passing — Phase 1 Reaper byte-stable output verified intact.
- Stale `# disabled in UI until Phase 4 ships` comment at `planner/models.py:980` updated (RESEARCH Pitfall 6 cleanup).

### From Phase 04 Plan 02 (pure-function Nuendo Live exporter)

- `planner/utils/nuendo_live_export.py` shipped — 331 lines, pure `build_nlpr(session) -> bytes` using lxml template-injection. Trust-boundary docstring mirrors `reaper_export.py`; caller (Plan 04-05's view) owns project scoping.
- `YAMAHA_TO_FARB` constant locked per D-07: 8 entries; `'Off'` and `'White'` intentionally absent so `dict.get()` returns `None` and the exporter strips the `<int name='Farb'/>` element per D-05.
- `ExportTemplateError` exception class — caught by the (future Plan 04-05) view layer per D-03 contract; renders editor.html with banner instead of returning 500 when the bundled fixture is missing or malformed.
- Six private helpers implemented per RESEARCH §"Code Examples" verbatim: `_find_audio_folder` (XPath disambiguates 'Audio' from 'Input/Output Channels' MFolderTrack), `_scan_max_id` (D-08 — scans `@ID` attrs + `<int name='RuntimeID'|'ID'/>` value-attrs), `_replace_all_ids` (D-10 — burns IDs sequentially through new_track), `_set_names` (Pitfall 9 two-write protocol), `_set_channel_id`, `_apply_farb` (handles palette-match → mutate, None → remove, non-palette → remove; SubElement re-add path for A5 fallback).
- `_ordered_enabled_tracks` reused verbatim via `from .reaper_export import _ordered_enabled_tracks` — track order is universal across DAW formats.
- Helper-level in-memory exercise harness passes end-to-end against a Python-generated fake template covering all 6 helpers (no real Plan 04-03 fixture required for this plan).
- Phase 1's `planner/tests/test_reaper_export`: 42/42 passing — byte-stable Reaper contract intact.
- Zero migrations. `python manage.py makemigrations planner --dry-run` reports `No changes detected`. CLAUDE.md "additive migrations only" naturally satisfied.
- `build_nlpr` is invokable but raises `ExportTemplateError` until Plan 04-03 commits the bundled fixture at `planner/data/multitrack/nuendo_live_3_template.nlpr` — by design (graceful degradation per D-03).

### From Phase 04 Plan 04 (D-09 ID-uniqueness test)

- `planner/tests/test_nuendo_live_export.py` shipped — 248 lines, 3 tests in `NuendoLiveExportIdUniquenessTests`. Runs in 0.153 s; all 3 pass.
- D-09 floor assertion (`test_ids_unique`): collects every `@ID` attribute and every `<int name='RuntimeID'|'ID'/>` value from the export bytes, asserts `len(set(ids)) == len(ids)`. Directly verifies NLP-06.
- Two bonus structural checks (within CONTEXT.md §"Test budget — one assertion is the floor, not the ceiling"): `test_track_count_matches_enabled` confirms the seed track was removed and exactly `enabled_count` `MAudioTrackEvent` elements ship (D-10); `test_both_name_writes` confirms outer `MListNode/Name` and inner `DeviceAttributes/Name/String` agree per track (NLP-03 / Pitfall 9).
- `planner/tests/fixtures/nuendo_live_3_template_fake.nlpr` shipped — 38-line Python-generated minimal fake template carrying every element shape `build_nlpr`'s helpers traverse. Lets Plan 04-04 run independently of Plan 04-03's Charlie-hand-generated real fixture (Wave 2 parallel-safe).
- Module-global swap-and-restore pattern in `setUp` / `tearDown` (`nle._TEMPLATE_PATH = FAKE_TEMPLATE`, `nle._TEMPLATE_TREE = None`) — preserves test isolation, restores originals so other tests are unaffected. Verified by `test_reaper_export` still passing 42/42 after the new test module lands.
- Field-type adjustments to the plan's draft `<action>` test code (invited explicitly by the plan's Notes): `ConsoleAuxOutput.aux_number` and `ConsoleMatrixOutput.matrix_number` are `CharField` (passed as `'1'` not `1`); `ConsoleStereoOutput.stereo_type` choices are `'L'`/`'R'`/`'M'` only (not `'MAIN'`). No deviations — the plan documented these as expected adjustments.
- Zero migrations, zero schema drift. `python manage.py makemigrations planner --dry-run` → `No changes detected in app 'planner'`.

### From Phase 04 Plan 05 (HTTP entry point — view + URL route)

- `planner/views.py` gains `multitrack_export_nlpr(request, session_id)` (95 net new lines: import + section-header comment + view body) immediately after `multitrack_export_rtracktemplate`. Mirrors the Phase 1 `multitrack_export_rpp` pattern at `:6875-6919` line-for-line with three deltas: calls `build_nlpr(session)`, wraps the call in `try/except ExportTemplateError` (D-03 graceful fallback to `editor.html` with banner copy `'Nuendo Live export is unavailable on this server — bundled template missing or malformed. Contact support.'`), and uses `application/xml; charset=utf-8` + lowercase `.nlpr` filename.
- Auth decorator: `@staff_member_required` — RESEARCH Pitfall 5 verified current Phase 1 state (downloads kept legacy gate; CR-01/CR-02 retightened only AJAX mutate endpoints `set_color`/`set_label`/`set_enabled`/`remove_track`/reorder). Decision documented in-source via the section-header comment so future readers don't accidentally drift from Phase 1's sibling.
- `planner/urls.py` gains one route: `path('multitrack/<int:session_id>/export.nlpr/', views.multitrack_export_nlpr, name='multitrack_export_nlpr')` slotted immediately after the two existing Reaper file-download routes. `reverse('planner:multitrack_export_nlpr', args=[42])` returns `/audiopatch/multitrack/42/export.nlpr/`.
- Both error paths (no-enabled-tracks AND `ExportTemplateError`) use the IDENTICAL `_editor_context(...)` shape Phase 1 used at `:6900-6912`; only the `export_error` string differs. Keeps the editor template's context contract uniform across all export attempts.
- Atomic commits: `905b87d` (Task 1: view) + `7216f52` (Task 2: URL). No deletions in either commit (`git diff --diff-filter=D HEAD~1 HEAD` empty for both).
- Zero migrations. `python manage.py makemigrations planner --dry-run` → `No changes detected in app 'planner'`. View + URL only.
- `python manage.py check` → 0 issues. Full `planner` suite 95/95 passing in 4.745s. `planner.tests.test_reaper_export` 42/42 (Phase 1 byte-stable Reaper contract intact). `planner.tests.test_nuendo_live_export` 3/3 (Plan 04 D-09 ID-uniqueness + bonus structural checks intact).
- Plan 04-07 (toolbar button) is now unblocked — the `reverse()` URL is stable and reachable today via direct hit. The `.nlpr` button needs only one `<a>` anchor in `editor.html` per D-11 / D-13.

### From Phase 04 Plan 06 (atomic three-place nuendo_live gate removal)

- Single atomic commit (`c53a9ce`) removes all three Phase 1 belt-and-suspenders gates that disabled `nuendo_live` as a `target_daw` choice on the new-session form. Per RESEARCH Pitfall 6: removing one or two gates in isolation leaves the form half-broken; atomicity is the requirement.
- Gates removed: (1) `planner/forms.py` `MultitrackSessionForm.__init__` choices-restriction list-comp; (2) `planner/forms.py` `clean_target_daw` method (with ValidationError `'Nuendo Live export ships in v2.0 Phase 4...'`); (3) `planner/templates/planner/multitrack/new_session.html` static `<input type="radio" disabled>` placeholder block.
- 26 lines deleted across 2 files; 0 lines added. The dynamic `{% for radio in form.target_daw %}` loop at `new_session.html:66-71` is now the sole renderer of the two radios. `MultitrackSession.TARGET_DAW_CHOICES` (`planner/models.py:978-981`) drives the form's choices unmodified — both `reaper` and `nuendo_live` enabled.
- T-04-20 mitigation (Django `ChoiceField` validation against `TARGET_DAW_CHOICES`) verified intact via inline form-instantiation check: `target_daw='protools'` (bogus) still rejected. T-04-21 (previously-rejected `nuendo_live` now accepted) is the intended behavior change.
- No Phase 1 test asserted the removed `ValidationError` (grep verified across `planner/tests/`), so no test updates needed. `python manage.py test planner -v 1` → 95/95 passing in 4.750s after the change.
- `python manage.py check` → 0 issues. `python manage.py makemigrations planner --dry-run` → No changes detected. Zero migrations.
- Plan 04-01 had already removed the stale `# disabled in UI until Phase 4 ships` comment from `planner/models.py:980` (RESEARCH Pitfall 6 bonus cleanup), confirmed pre-execution by reading `planner/models.py:977-982`. No additional model-side edit needed.

### From Phase 04 Plan 07 (toolbar button — Phase 04 code-complete)

- `planner/templates/planner/multitrack/editor.html` gains one new `<a class="mts-btn mts-btn-success" href="{% url 'planner:multitrack_export_nlpr' session.id %}">Export to Nuendo Live (.nlpr)</a>` anchor inserted immediately after the existing Reaper Track Template anchor (between the previous line 81 and the closing `</div>` of `mts-toolbar-actions`). +2 lines, zero deletions. Single atomic commit `eb5dfaf` (`feat(04-07)`).
- D-11 honored: no `{% if %}` wrapper on `session.target_daw`. All three export buttons (`.RPP` success / `.RTrackTemplate` secondary / `.nlpr` success) render for every session regardless of `target_daw`. Matches the Phase 1 posture of the two Reaper anchors; `target_daw`'s semantic meaning is now "default for new sessions / template signaling" (Phase 3) rather than "what buttons appear."
- D-13 honored: zero new CSS classes. The `.nlpr` anchor reuses the existing `mts-btn mts-btn-success` pair from the `.RPP` sibling. Phase 4 ships no CSS-edit at all.
- D-14 honored: single `.nlpr` button — no separate "Nuendo Live track template" variant. Nuendo Live has no track-archive format like full Nuendo's `.npr` (spec §"Nuendo Live (.nlpr)").
- Deliberate divergence from the `.RTrackTemplate` sibling: no `title=` attribute on the new anchor. Rationale: `.nlpr` is self-explanatory as a Nuendo Live filename; `.RTrackTemplate` needed the "import via Track menu" hint because engineers wouldn't recognize that extension. The `.RPP` anchor (also success-styled, also full-export) also has no `title=`.
- End-to-end render verified: `render_to_string('planner/multitrack/editor.html', ctx)` with a minimal context produces HTML containing both `Export to Nuendo Live (.nlpr)` and the reversed URL `/multitrack/1/export.nlpr/`. No `NoReverseMatch`.
- `python manage.py check` → 0 issues. `python manage.py makemigrations planner --dry-run` → No changes detected. Zero migrations (template-only edit). `python manage.py test planner -v 0` → **95/95** passing in 4.649s — Phase 1 Reaper byte-stable contract intact; Plan 04-04 D-09 ID-uniqueness intact.
- **Phase 04 code-complete:** all 7 plans across 3 waves shipped. Wave 1 (parallel) — Plans 01/02/03/04 (model + lxml + comment, exporter, fixture, ID-uniqueness test). Wave 2 — Plan 05 (view + URL). Wave 3 (parallel) — Plans 06/07 (form gate removal, toolbar button).
- **HUMAN-UAT for NLP-01..NLP-05 is now unblocked.** Charlie's Mac + Nuendo Live 3 round-trip is the only remaining gate before `/gsd-transition` or `/gsd-complete-phase` can mark Phase 04 done. NLP-06 (ID/RuntimeID uniqueness) is already fully verified via Plan 04-04's `test_ids_unique`.
