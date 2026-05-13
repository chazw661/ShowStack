---
phase: 04-nuendo-live-export
plan: 04
subsystem: testing

tags: [lxml, pytest-style-django-testcase, monkeypatch-module-globals, nuendo-live, id-uniqueness, d-09]

# Dependency graph
requires:
  - phase: 04-nuendo-live-export
    provides: Plan 04-02 — build_nlpr(session) → bytes + ExportTemplateError + _TEMPLATE_PATH module-global
  - phase: 04-nuendo-live-export
    provides: Plan 04-01 — MultitrackTrack.resolved_yamaha_name @property used end-to-end by build_nlpr
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: _SessionFixtureMixin shape from test_reaper_export.py + Console/ConsoleInput/Aux/Matrix/Stereo/MultitrackSession/MultitrackTrack ORM models
provides:
  - planner/tests/fixtures/nuendo_live_3_template_fake.nlpr — minimal Python-generated fake .nlpr (38 lines) carrying every element shape build_nlpr's XPaths target
  - planner/tests/test_nuendo_live_export.py — NuendoLiveExportIdUniquenessTests TestCase with the locked D-09 assertion + 2 cheap structural bonus checks (248 lines)
  - Module-global swap-and-restore pattern (setUp/tearDown mutates nle._TEMPLATE_PATH and nle._TEMPLATE_TREE so the test runs against the fake fixture independent of Plan 04-03's real binary)
affects: [04-05, 04-06, 04-07, nuendo-live-exporter-regression-coverage]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wave-2-parallel-safe test fixture strategy: Python-generated minimal .nlpr template lets the exporter test run without Plan 04-03's Charlie-hand-generated Windows binary"
    - "Module-global swap-and-restore in setUp/tearDown (preserves test isolation while monkeypatching _TEMPLATE_PATH + invalidating _TEMPLATE_TREE module cache)"
    - "_SessionFixtureMixin parallel to test_reaper_export.py — same shape, target_daw='nuendo_live' instead of 'reaper'"

key-files:
  created:
    - "planner/tests/fixtures/nuendo_live_3_template_fake.nlpr — 38-line minimal hand-rolled fake template"
    - "planner/tests/test_nuendo_live_export.py — 248-line TestCase with D-09 + 2 bonus structural assertions"
  modified: []

key-decisions:
  - "Field-type corrections vs the plan's draft action block: ConsoleAuxOutput.aux_number and ConsoleMatrixOutput.matrix_number are CharField (not Integer); ConsoleStereoOutput.stereo_type choices are 'L'/'R'/'M' only (not 'MAIN'). The plan's <action> block explicitly invited these adjustments under Task 2: '_build_* helpers may need adjustments if Phase 1's Console / ConsoleInput / etc. require different mandatory fields than the Reaper test mixin used'."
  - "Three tests ship, not one: the D-09 floor plus two bonus structural checks (track-count = enabled_count, both-name-writes equality) which surface naturally per CONTEXT.md §'Test budget — one assertion: this is the floor, not the ceiling'."
  - "Module-global monkeypatch (nle._TEMPLATE_PATH = FAKE_TEMPLATE, nle._TEMPLATE_TREE = None) chosen over Django @override_settings because _TEMPLATE_PATH lives on the utility module, not in Django settings. setUp + tearDown restore both globals; no test pollution observed."
  - "Test target_daw='nuendo_live' (not 'reaper') for semantic consistency — even though the exporter is target-agnostic per D-11, the field name signals intent."

patterns-established:
  - "Pure-function exporter test pattern (mirror of test_reaper_export.py): _SessionFixtureMixin → multiple TestCase subclasses, integration tests against real ORM, no mocks of the exporter itself."
  - "Module-global override pattern for tests that need to swap a utility-module file path: setUp saves originals → assigns test values → tearDown restores. Documented inline with comments so future maintainers don't accidentally break test isolation."

requirements-completed: [NLP-06]

# Metrics
duration: 2min
completed: 2026-05-13
---

# Phase 4 Plan 04: Nuendo Live Export ID-Uniqueness Test Summary

**Ships the single automated assertion Phase 4 commits to (D-09 / NLP-06) plus two cheap bonus structural checks — `len(set(ids)) == len(ids)` over every `@ID` attribute and every `<int name='RuntimeID'|'ID'/>` value-attribute in the exported `.nlpr` bytes — running against a Python-generated minimal fake template so the test is independent of Plan 04-03's Charlie-hand-generated Windows binary.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-13T23:52:10Z
- **Completed:** 2026-05-13T23:54:29Z
- **Tasks:** 2 / 2
- **Files created:** 2 (38 + 248 lines)
- **Files modified:** 0
- **Test runtime:** 0.153 s for 3 tests (well under any practical CI budget)

## Accomplishments

- `planner/tests/fixtures/nuendo_live_3_template_fake.nlpr` — minimal 38-line hand-rolled `.nlpr` carrying every element shape the Plan 04-02 exporter helpers traverse:
  - Exactly one `<obj class="MFolderTrack">` whose inner `Name` reads `"Audio"` (the target of `_find_audio_folder`'s XPath).
  - A second `<obj class="MFolderTrack">` named `"Input/Output Channels"` — proves the XPath disambiguates correctly and would never falsely select the wrong folder.
  - One seed `<obj class="MAudioTrackEvent">` inside the Audio folder's `<list name="Tracks">` with: outer `MListNode/Name` string, inner `MAudioTrack` with `<int name="Channel ID"/>` + nested `DeviceAttributes/Name/String`, plus an `Additional Attributes/Farb` int and a sibling `<int name="RuntimeID"/>` — so `_set_names`, `_set_channel_id`, `_apply_farb`, and `_scan_max_id`'s value-attr branch all have something to bite on.
- `planner/tests/test_nuendo_live_export.py` — `NuendoLiveExportIdUniquenessTests` TestCase with three assertions:
  1. **`test_ids_unique` (D-09 / NLP-06 — the locked floor)** — collects every `@ID` attribute and every `<int name='RuntimeID'|'ID'/>` value from the parsed export bytes, asserts `len(set(ids)) == len(ids)`. Passes against a 5-enabled-track session spanning input / aux / matrix / stereo / manual source types.
  2. **`test_track_count_matches_enabled` (bonus, CONTEXT.md §"Test budget")** — exactly 5 `<obj class="MAudioTrackEvent">` elements inside the Audio folder (seed correctly removed per D-10).
  3. **`test_both_name_writes` (bonus, RESEARCH Pitfall 9 / NLP-03)** — every output track has both outer `MListNode/Name` AND inner `DeviceAttributes/Name/String` populated with the same non-empty value.
- `setUp` / `tearDown` swap `nle._TEMPLATE_PATH` to the Task 1 fake fixture and reset the `_TEMPLATE_TREE` cache (the plan's locked link path). `tearDown` restores both globals — verified by running the full `planner.tests.test_reaper_export` suite afterward (42/42 still OK).
- `python manage.py test planner.tests.test_nuendo_live_export -v 2` exits 0 with `OK` in 0.153 s, 3 tests run.
- `python manage.py test planner.tests.test_reaper_export -v 1` continues to exit 0 with 42/42 OK — Phase 1's byte-stable Reaper contract is intact.
- `python manage.py makemigrations planner --dry-run` reports `No changes detected in app 'planner'` — zero schema drift (Phase 4 ships zero migrations through Plan 04-04, naturally compliant with CLAUDE.md §"additive migrations only").

## Task Commits

Each task was committed atomically:

1. **Task 1: Create minimal fake .nlpr fixture** — `a285bb6` (test)
2. **Task 2: Write `NuendoLiveExportIdUniquenessTests` test module** — `c52e25a` (test)

_Note: Plan 04-04 has `tdd="true"` flags on both tasks but is `type: execute`. Per the plan's own Task 2 `<action>` note ("the test is expected to PASS as soon as both Plan 02 (Task 2) and Task 1 of this plan are in place, so the RED phase here is 'test file exists but verify-import fails because we haven't written the body yet' — don't over-engineer the cycle"), one `test(...)` commit per task is the correct shape. Both commits use the `test:` type because the file content is test code, not feature code._

## Files Created/Modified

- **Created:** `planner/tests/fixtures/nuendo_live_3_template_fake.nlpr` — 38 lines. Minimal hand-rolled fake Nuendo Live template carrying every element shape Plan 04-02's `build_nlpr` helpers traverse. Not a real Nuendo file — opaque vendor boilerplate (Eths, OwnInputBus, SendFolder, transport state, etc.) is deliberately absent because Phase 4's "does this open in Nuendo Live" check is HUMAN-UAT against Plan 04-03's real fixture, not this fake.
- **Created:** `planner/tests/test_nuendo_live_export.py` — 248 lines. Pure-function exporter test module mirroring `test_reaper_export.py`'s shape: `_SessionFixtureMixin` (TestCase-less helper for User/Project/Console/Session creation), `NuendoLiveExportIdUniquenessTests` (3 tests against a 5-enabled-track session). `setUp` / `tearDown` swap the module-global `nle._TEMPLATE_PATH` and `nle._TEMPLATE_TREE` so the test runs against the Task 1 fake without touching Plan 04-03's future deliverable.
- **Modified:** none.

## Decisions Made

- **Field-type corrections vs the plan's draft `<action>` code.** The plan's draft inside Task 2 used `aux_number=1` and `matrix_number=1` (integers) and `stereo_type='MAIN'`. Inspection of `planner/models.py:880` and `:905` confirms those are `CharField(max_length=10)` and the plan's draft would have failed at `MultitrackTrack.objects.create()` time. Similarly, `ConsoleStereoOutput.STEREO_CHOICES` is `[('L', 'Stereo Left'), ('R', 'Stereo Right'), ('M', 'Mono')]` — `'MAIN'` is not a valid choice. The plan's Task 2 `<action>` Notes block explicitly anticipated this: *"`_build_*` helpers may need adjustments if Phase 1's `Console` / `ConsoleInput` / etc. require different mandatory fields than the Reaper test mixin used. Inspect `planner/tests/test_reaper_export.py` to confirm the field names and minimum-required attributes; the same patterns apply here."* — I followed that instruction. Real values used: `aux_number='1'`, `matrix_number='1'`, `stereo_type='L'`. Dante numbers passed as ints for `ConsoleAuxOutput`/`Matrix`/`Stereo` (all `IntegerField`) and as a string `'1'` for `ConsoleInput.dante_number` (`CharField`).
- **Three tests ship, not one** — CONTEXT.md §"Test budget — one assertion" explicitly authorizes this: *"the planner / executor may add additional cheap structural assertions under Claude's Discretion (e.g. 'output contains `enabled_track_count` MAudioTrackEvent elements', 'every track has both name elements populated') — but the floor of ONE test must ship."* The two bonus checks were already drafted in the plan's `<action>` block; I implemented them verbatim.
- **`target_daw='nuendo_live'` on the test session** — even though the exporter is target-agnostic per D-11, this makes the test's intent self-documenting. The Reaper test mixin uses `target_daw='reaper'` for the same reason.

## Deviations from Plan

None substantive — plan executed exactly as written, with one trivial acceptance-criterion typo observation documented below.

### Acceptance-criterion clarification (Task 1)

The Task 1 `<acceptance_criteria>` listed `grep -c 'name="Audio"' planner/tests/fixtures/nuendo_live_3_template_fake.nlpr returns at least 1`. The literal grep against my fixture (which I wrote verbatim from the plan's `<action>` XML block) returns `0` — because the Audio folder identifier is `value="Audio"`, not `name="Audio"`. The element shape per the plan's locked XML is `<string name="Name" value="Audio" wide="true"/>`. The literal text matched by `grep 'name="Audio"'` does not occur anywhere in the fixture, by design.

This is a trivial typo in the acceptance criterion text — the spirit of the check (Audio folder identifiable in the file) is satisfied (`grep -c 'value="Audio"'` returns 1, the lxml structural verify command from the plan's `<verify>` block prints `OK`, and the Task 2 test's XPath predicate `[.//string[@name='Name' and @value='Audio']]` selects the correct folder). All other Task 1 acceptance criteria pass at the literal-grep level. No action required — the fixture is correct; the acceptance criterion phrasing has a single-character bug.

### Field-type adjustment scope (Task 2)

The field-type corrections noted under "Decisions Made" are not deviations from the plan — the plan's `<action>` Notes block invited them. They're documented here for traceability.

---

**Total deviations:** 0 auto-fixed (no Rule 1/2/3 fixes needed; plan execution was clean).
**Impact on plan:** None. All Task 1 and Task 2 acceptance criteria are met (with the single phrasing-only observation above). The `<verification>` block's four commands all return success: fixture parses with lxml, the new test suite runs OK with 3/3 passing, `test_reaper_export` still runs OK with 42/42 passing, full `planner` test suite remains green for the Phase 1+2+3 surface this plan touches.

## Issues Encountered

- **Local Python venv `lxml` is already installed** (Plan 04-02 installed it locally; no fresh install needed here). The plan's `<verify>` commands invoked `python` which on the dev box resolved to `./venv/bin/python` for the lxml import to work — same dev-env quirk noted in Plan 04-01 and 04-02 SUMMARYs.
- **No checkpoint blockers, no auth gates, no architectural decisions.** Plan 04-04 is a pure unit-test-authoring plan against an exporter that's already shipped (Plan 04-02).

## User Setup Required

None — Plan 04-04 ships only test code + a Python-generated fake fixture. No external services, no environment variables, no Railway config. Plan 04-03's Charlie-generated real fixture is still outstanding but is NOT a prerequisite for Plan 04-04's tests (by design — that's exactly why the fake fixture exists).

## Threat Flags

None. Plan 04-04's surface is:
- One read-only binary fixture committed to git (`planner/tests/fixtures/nuendo_live_3_template_fake.nlpr`).
- One test module that creates ephemeral in-memory SQLite rows during the test run and exercises pure-function `build_nlpr`.

No new network endpoints, no new auth paths, no new schema, no new file-write surface, no new trust boundaries beyond the existing test-module-swap pattern flagged in the plan's `<threat_model>` (T-04-12: cache reset / setUp+tearDown restore — mitigated and verified, see "Accomplishments" bullet on test_reaper_export regression check).

## TDD Gate Compliance

Plan 04-04's frontmatter is `type: execute`, but both tasks carry `tdd="true"`. Per the plan's Task 2 `<action>` block: *"the test is expected to PASS as soon as both Plan 02 (Task 2) and Task 1 of this plan are in place, so the RED phase here is 'test file exists but verify-import fails because we haven't written the body yet' — don't over-engineer the cycle; one commit landing the file with the full implementation is fine for this plan."* Both commits use the `test:` conventional-commit type because the file content is exclusively test code (a test fixture and a test module). No RED/GREEN/REFACTOR sequence applies because (a) the implementation under test (`build_nlpr`) is already complete from Plan 04-02 and (b) the plan itself directs the executor not to over-engineer the cycle. No SUMMARY warning needed.

## Self-Check: PASSED

Verified before STATE.md update:
- `planner/tests/fixtures/nuendo_live_3_template_fake.nlpr` exists (FOUND; 38 lines, ≥25 min_lines)
- `planner/tests/test_nuendo_live_export.py` exists (FOUND; 248 lines, ≥100 min_lines)
- `grep -c 'class NuendoLiveExportIdUniquenessTests' planner/tests/test_nuendo_live_export.py` → 1 (FOUND)
- `grep -c 'def test_ids_unique' planner/tests/test_nuendo_live_export.py` → 1 (FOUND)
- `grep -c 'len(set(' planner/tests/test_nuendo_live_export.py` → 2 (FOUND, ≥1 required — one in the assertion, one in the failure-message f-string)
- `grep -E 'from planner.utils.nuendo_live_export import build_nlpr|from planner.utils import nuendo_live_export'` → both imports present (FOUND)
- `nle._TEMPLATE_PATH = FAKE_TEMPLATE` present at line 167 (FOUND — the path swap)
- `nle._TEMPLATE_TREE = None` present at line 168 (FOUND — the cache reset)
- `python manage.py test planner.tests.test_nuendo_live_export -v 2` → 3/3 OK in 0.153 s (FOUND)
- `python manage.py test planner.tests.test_reaper_export -v 0` → 42/42 OK (FOUND — no Phase 1 regression)
- `python manage.py makemigrations planner --dry-run` → `No changes detected in app 'planner'` (FOUND — zero schema drift)
- Task 1 commit `a285bb6` exists in `git log --oneline -3` (FOUND)
- Task 2 commit `c52e25a` exists in `git log --oneline -3` (FOUND)
- Both fixture and test file structurally valid: `lxml.etree.parse('planner/tests/fixtures/nuendo_live_3_template_fake.nlpr')` prints `Fixture parses OK` (FOUND)

## Next Phase Readiness

- **Plan 04-04 deliverable is complete and CI-ready.** The D-09 test floor ships; Phase 4 has its single automated regression check for ID/RuntimeID uniqueness (NLP-06). Any future structural change to `build_nlpr` that accidentally generates duplicate IDs will be caught immediately.
- **Plan 04-05 (view + URL) is unblocked.** The view will catch `ExportTemplateError` and render `editor.html` with `export_error=` (D-03 banner). The wire-up doesn't depend on Plan 04-04's test artifact.
- **Plan 04-06 (form + toolbar button) is unblocked.** Pure template / form work; no dependency on Plan 04-04.
- **Plan 04-03 (Charlie-generated real fixture) remains outstanding** but does NOT block Plans 04-04, 04-05, or 04-06. The real fixture is required for end-to-end "open in Nuendo Live 3" HUMAN-UAT, which is the only thing this phase cannot automate.

---
*Phase: 04-nuendo-live-export*
*Completed: 2026-05-13*
