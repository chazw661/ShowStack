---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: milestone
status: executing
last_updated: "2026-05-13T23:57:02.263Z"
last_activity: 2026-05-13 -- Plan 04-04 complete: D-09 ID-uniqueness test shipped (commits a285bb6, c52e25a)
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 22
  completed_plans: 18
  percent: 82
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-09)

**Core value:** ShowStack knows your patch, your labels, and your gear; once entered, that data drives every export your show needs.
**Current focus:** Phase 04 — Nuendo Live Export

## Current Position

Phase: 04 (Nuendo Live Export) — EXECUTING
Plan: 4 of 7
Status: Ready to execute
Last activity: 2026-05-13 -- Plan 04-04 complete: D-09 ID-uniqueness test shipped (commits a285bb6, c52e25a)

Progress: [████████░░] 82%

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
