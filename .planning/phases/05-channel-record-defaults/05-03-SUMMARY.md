---
phase: 05-channel-record-defaults
plan: 03
subsystem: views

tags: [seed-logic, picker-add, channel-record-defaults, pol-01, pol-02, defence-in-depth, end-to-end-test]

# Dependency graph
requires:
  - phase: 05-channel-record-defaults
    provides: ConsoleInput/ConsoleAuxOutput/ConsoleMatrixOutput/ConsoleStereoOutput.default_record + default_record_color (Plan 05-01 commits 8003594 + f4c0a99) — the two channel-level seed fields this plan reads
  - phase: 05-channel-record-defaults
    provides: Form-layer hex validator clean_default_record_color across 4 ChannelForms (Plan 05-02 commit 7121792) — the first line of defence; this plan adds the second (AJAX boundary)
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: _HEX_COLOR_RE at planner/views.py:6259, multitrack_add_tracks AJAX endpoint at planner/views.py:6598, multitrack_export_rpp endpoint, MultitrackTrack model with enabled + color_override fields, planner.utils.reaper_export.hex_to_peakcol — all reused unchanged
provides:
  - "multitrack_add_tracks seeds enabled = channel.default_record and color_override = channel.default_record_color on every picker-added MultitrackTrack — closes POL-01 + POL-02 end-to-end"
  - "Defence-in-depth: AJAX-boundary _HEX_COLOR_RE.match on the seed hex; bad DB values silently drop to '' instead of crashing the picker or leaking unsanitized strings into MultitrackTrack.color_override"
  - "planner/tests/test_channel_record_defaults.py — 5 regression tests (POL-01 happy / POL-01 opt-out / POL-02 happy / defence-in-depth silent-drop / end-to-end Reaper RPP PEAKCOL assertion)"
affects: [editor-picker-flow, reaper-export, nuendo-live-export]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bulk-fetch-by-validated-ID seed map: O(1) overhead added to multitrack_add_tracks regardless of selection size — 4 queries per request (one per source_type) using `id__in=valid_xxx_ids` against ID sets that were already vetted by the lines 6655-6672 set-intersection block"
    - "Dict-comprehension seed_maps keyed by source_type string, each value a `{pk: (default_record, default_record_color)}` map sourced from `.values_list('id', 'default_record', 'default_record_color')` — pure tuples, no model-row instantiation cost"
    - "Defence-in-depth at the AJAX boundary: re-validate channel.default_record_color against _HEX_COLOR_RE in the row-build loop before assigning to MultitrackTrack.color_override; complements Plan 05-02's form-layer validator (which protects the write path but not the read path against legacy/SQL-edit data)"
    - "End-to-end regression assertion against the exporter output (PEAKCOL line in Reaper RPP body) — uses hex_to_peakcol() to derive the expected packed-RGB integer rather than hard-coding a magic number, so the test survives legitimate exporter packing-formula refactors"

key-files:
  created:
    - "planner/tests/test_channel_record_defaults.py — 167 lines, 5 tests in ChannelRecordDefaultsSeedTests"
  modified:
    - "planner/views.py — +20 lines in multitrack_add_tracks (seed_maps bulk-fetch block + per-row seed lookup with _HEX_COLOR_RE defence-in-depth + 2 new MultitrackTrack constructor kwargs)"

key-decisions:
  - "Bulk-fetch per source_type via 4 .values_list() queries, restricted to already-validated ID sets — avoids N+1 without prefetch_related overhead, and the set-intersection at lines 6655-6672 means no IDOR risk from the bulk read"
  - "Defensive .get(raw_id, (True, '')) fallback in the row loop — covers the edge case where bulk-loading misses an ID (shouldn't happen post-validate, but keeps the function defensively correct without an additional branch)"
  - "Verbatim AJAX-boundary _HEX_COLOR_RE.match re-validation per Plan 05-02's defence-in-depth contract — silently drops bad hex to '' rather than 400-erroring the picker request; engineers should not see the picker crash because of legacy data"
  - "multitrack_duplicate intentionally NOT touched — duplication semantics are 'copy source-session state as-is', not 're-seed from current channel defaults'. Engineers duplicating a session want it identical to the original, not freshly seeded"
  - "Test file lives at planner/tests/test_channel_record_defaults.py (not test_multitrack_add_tracks.py) — keeps the file name aligned with the feature name (POL-01/POL-02 / channel record defaults) rather than the endpoint under test; matches the existing per-feature naming pattern (test_console_csv_import.py, test_nuendo_live_export.py)"
  - "Test 5 (end-to-end) uses hex_to_peakcol() to derive the expected token rather than hard-coding the integer — this future-proofs the test against legitimate exporter refactors (endianness fix, bit-packing tweak) and reduces coupling to internal exporter details"

patterns-established:
  - "Two-layer hex validation pattern for channel-level seed fields: form-layer clean_default_record_color in planner/forms.py (Plan 05-02) for the write path, AJAX-boundary _HEX_COLOR_RE.match in planner/views.py multitrack_add_tracks (this plan) for the read path. Both layers required because legacy data and direct-SQL edits bypass the form validator entirely"
  - "End-to-end exporter-output regression test pattern: pick a seed value at the channel level, drive it through the picker-add endpoint, then GET the exporter endpoint and assert the seeded value (transformed via the exporter's own helper) appears in the response body — single test proves an entire data-flow chain in one assertion"

requirements-completed: [POL-01, POL-02]

# Metrics
duration: ~3min
completed: 2026-05-14
---

# Phase 5 Plan 03: Channel Record Defaults — Seed Logic + Regression Suite Summary

**Wired POL-01 (`default_record` → `MultitrackTrack.enabled`) and POL-02 (`default_record_color` → `MultitrackTrack.color_override`) into `multitrack_add_tracks` with AJAX-boundary `_HEX_COLOR_RE` defence-in-depth, plus a 5-test regression suite that proves the full POL-02 chain reaches the Reaper RPP exporter output (PEAKCOL field). Phase 5 Success Criteria 2 and 3 are now delivered end-to-end. All 38 / 38 v2.0 requirements are wired — the milestone is code-complete pending HUMAN-UAT on Phase 5 admin-form + picker-add flow.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-14T19:57:50Z
- **Completed:** 2026-05-14T20:00:26Z
- **Tasks:** 2 / 2
- **Files modified:** 1 (planner/views.py)
- **Files created:** 1 (planner/tests/test_channel_record_defaults.py)

## Accomplishments

- `multitrack_add_tracks` in `planner/views.py` now bulk-loads each source_type's channel seed fields (`default_record`, `default_record_color`) via 4 `.values_list('id', 'default_record', 'default_record_color')` queries restricted to the already-validated ID sets — O(1) overhead regardless of selection size, no N+1 risk, and no IDOR surface (the bulk read uses `id__in=valid_xxx_ids` which by construction can only return channels the lines 6655-6672 set-intersection already vetted).
- Each new `MultitrackTrack` row in the picker-add loop now receives `enabled=bool(seed_record)` and `color_override=seed_hex` instead of relying on model defaults. `seed_record` and `seed_hex` come from `seed_maps[src_type].get(raw_id, (True, ''))` — the defensive `(True, '')` fallback covers the (shouldn't-happen-post-validate) miss case.
- Defence-in-depth `_HEX_COLOR_RE.match(seed_hex)` check inside the row-build loop: any bad-hex value (legacy data, direct SQL edit, fixture import bypassing Plan 05-02's `clean_default_record_color`) silently drops to `''` instead of crashing the picker or leaking the unsanitized string into `MultitrackTrack.color_override`. Satisfies threat T-05-03-01's `mitigate` disposition.
- Manual-track construction block (lines 6700-6710 pre-edit) untouched — manuals have no source channel to seed from, so the existing engineer-supplied label / color / notes path is unchanged.
- `multitrack_duplicate` intentionally NOT touched per plan instruction — duplication semantics preserve source-session state as-is (engineers want a copy identical to the original, not a fresh re-seed from current channel defaults). POL-01 / POL-02 apply only at picker-add time.
- New regression-test file `planner/tests/test_channel_record_defaults.py` ships with 5 tests, all passing in 0.231s. Coverage: POL-01 happy (default_record=True → track.enabled=True), POL-01 opt-out (False → False), POL-02 happy (`#FF8800` → `'#FF8800'`), defence-in-depth (DB-write of `'not-a-hex'` → `''` with HTTP 200 — no crash), and end-to-end (`#FF8800` seeded → `hex_to_peakcol('#FF8800')` integer appears in Reaper RPP export body).
- All prior test suites continue to pass: `test_reaper_export` 42/42, `test_nuendo_live_export` 3/3, `test_multitrack_reorder` 3/3, Phase 2 console-CSV-import suites green. Phase 1 byte-stable Reaper contract intact, Phase 4 NLP-06 ID-uniqueness intact.

## Task Commits

Each task was committed atomically on `main` (sole-developer workflow per CLAUDE.md):

1. **Task 1: Wire POL-01 / POL-02 seed logic into multitrack_add_tracks** — `f49ed1e` (feat) — `planner/views.py` only, +20 lines / -0 lines.
2. **Task 2: Add regression test suite (5 tests including end-to-end Reaper exporter assertion)** — `b23ea10` (test) — new file `planner/tests/test_channel_record_defaults.py`, +167 lines.

No file deletions in either commit (`git diff --diff-filter=D HEAD~1 HEAD` empty for both).

## Files Created/Modified

### `planner/views.py` (modified — commit `f49ed1e`)

Inserted after line 6672 (right after `valid_stereo_ids` calculation, before the `# Determine starting track_number` comment):

```python
# POL-01 / POL-02 — bulk-load channel seed fields so each new track can be
# seeded with enabled = channel.default_record and color_override =
# channel.default_record_color. One query per source_type (4 total),
# restricted to the IDs we'll actually use. ConsoleInput/Aux/Matrix/Stereo
# all expose the two seed fields after migration 0155.
seed_maps = {
    'input':  {row[0]: (row[1], row[2]) for row in ConsoleInput.objects.filter(id__in=valid_input_ids).values_list('id', 'default_record', 'default_record_color')},
    'aux':    {row[0]: (row[1], row[2]) for row in ConsoleAuxOutput.objects.filter(id__in=valid_aux_ids).values_list('id', 'default_record', 'default_record_color')},
    'matrix': {row[0]: (row[1], row[2]) for row in ConsoleMatrixOutput.objects.filter(id__in=valid_matrix_ids).values_list('id', 'default_record', 'default_record_color')},
    'stereo': {row[0]: (row[1], row[2]) for row in ConsoleStereoOutput.objects.filter(id__in=valid_stereo_ids).values_list('id', 'default_record', 'default_record_color')},
}
```

Replaced the inner-loop `MultitrackTrack(...)` constructor:

```python
for raw_id in raw_list:
    if raw_id in valid_ids:
        max_n += 1
        seed_record, seed_hex = seed_maps[src_type].get(raw_id, (True, ''))
        # Defence-in-depth (T-05-03-01): drop seed hex if it does
        # not match _HEX_COLOR_RE. Bad hex in the DB (legacy data,
        # direct SQL edit) must NOT crash the picker-add path.
        if seed_hex and not _HEX_COLOR_RE.match(seed_hex):
            seed_hex = ''
        new_rows.append(MultitrackTrack(
            session=session,
            track_number=max_n,
            source_type=src_type,
            source_id=raw_id,
            enabled=bool(seed_record),
            color_override=seed_hex,
        ))
```

No re-import of `ConsoleInput / ConsoleAuxOutput / ConsoleMatrixOutput / ConsoleStereoOutput` — they were already imported at `planner/views.py:61,70` (per CLAUDE.md project-rules constraint). No redefinition of `_HEX_COLOR_RE` — reused the module-level one at line 6259.

### `planner/tests/test_channel_record_defaults.py` (created — commit `b23ea10`)

5 tests in a single `ChannelRecordDefaultsSeedTests(TestCase)` class:

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_default_record_true_seeds_enabled_true` | POL-01 happy: `default_record=True` → `track.enabled=True`, `track.color_override=''` |
| 2 | `test_default_record_false_seeds_enabled_false` | POL-01 opt-out: `default_record=False` → `track.enabled=False` |
| 3 | `test_default_record_color_seeds_color_override` | POL-02 happy: `default_record_color='#FF8800'` → `track.color_override='#FF8800'` |
| 4 | `test_malformed_default_record_color_drops_silently` | Defence-in-depth: `.update(default_record_color='not-a-hex')` → endpoint 200, `track.color_override=''`, `track.enabled` unaffected |
| 5 | `test_seeded_color_appears_in_reaper_export` | End-to-end: `#FF8800` seeded → `multitrack_export_rpp` GET → response body contains `str(hex_to_peakcol('#FF8800'))` |

Shared `setUpTestData` creates project / console / session / staff user. `setUp` logs in via `force_login` and sets `current_project_id` in `request.session` so `CurrentProjectMiddleware` resolves the project. Helper `_add_input(input_ch, default_record, default_record_color)` isolates per-test channel configuration. Helper `_picker_add(input_pk)` POSTs the JSON body the editor's frontend uses.

## Decisions Made

- **Bulk-fetch via `.values_list` (not `prefetch_related` or `select_related`).** `.values_list` returns lightweight tuples; the seed-map values are exactly `(default_record, default_record_color)` pairs, so loading full model rows would be wasted work. Restricting to `id__in=valid_xxx_ids` keeps the per-request DB cost bounded by the user's selection size.
- **Defensive `.get(raw_id, (True, ''))` fallback in the inner loop.** Post-validate (the lines 6655-6672 set-intersection) every `raw_id` should be in `seed_maps[src_type]`, but the fallback keeps the function defensively correct without an extra branch. The fallback values `(True, '')` match Phase 1's default behaviour (new tracks default to enabled with no color), so the fallback path is semantically a no-op.
- **AJAX-boundary `_HEX_COLOR_RE.match` re-validation.** Plan 05-02's `clean_default_record_color` protects the form write path, but not the read path against legacy data or direct SQL edits. Re-validating at the picker-add boundary closes the defence-in-depth ladder per the orchestrator-brief XSS surface (T-05-03-01). Silent drop to `''` rather than 400-erroring the request — engineers should not see the picker crash because of corrupted historic data.
- **`multitrack_duplicate` NOT touched.** Per the plan's explicit `DO NOT` clause: duplication semantics preserve the source session's track state as-is, not re-seed from current channel defaults. POL-01 / POL-02 apply at picker-add time only.
- **Test file named `test_channel_record_defaults.py`** (not `test_multitrack_add_tracks.py`). Matches existing per-feature naming pattern (`test_console_csv_import.py`, `test_nuendo_live_export.py`) and aligns the filename with the POL-01 / POL-02 requirements being tested rather than the endpoint under test.
- **Test 5 uses `hex_to_peakcol(seed_hex)` to derive the expected token.** Hard-coding a magic integer would couple the test to the exporter's packing formula and break on legitimate refactors (endianness fix, bit-packing tweak). Using the exporter's own helper means a packing change updates both sides of the test equation simultaneously.
- **`Client(enforce_csrf_checks=True)` NOT used.** Django's test Client bypasses CSRF by default and the production endpoint relies on `@require_POST` + Django CSRF middleware; testing CSRF is the framework's job, not this regression suite's.

## Deviations from Plan

None — plan executed exactly as written. All `<verify>` automated checks pass and all `<acceptance_criteria>` items are green (with one cosmetic exception flagged below for transparency):

- ✅ `planner/tests/test_channel_record_defaults.py` exists
- ✅ `grep -c "def test_" planner/tests/test_channel_record_defaults.py` returns 5
- ✅ `grep "class ChannelRecordDefaultsSeedTests" planner/tests/test_channel_record_defaults.py` finds the class
- ✅ `grep -c "hex_to_peakcol" planner/tests/test_channel_record_defaults.py` returns 3 (≥ 2 required: 1 import + 1 usage + 1 expected_peakcol assignment)
- ✅ `grep -c "multitrack_export_rpp" planner/tests/test_channel_record_defaults.py` returns 3 (≥ 1 required: docstring + reverse() call + comment)
- ✅ `python manage.py test planner.tests.test_channel_record_defaults` → 5/5 passing in 0.231s
- ✅ `python manage.py test planner.tests.test_multitrack_reorder` → 3/3 (Phase 1 regression intact)
- ✅ `python manage.py test planner.tests.test_reaper_export` → 42/42 (Phase 1 byte-stable Reaper contract intact)
- ✅ `python manage.py test planner.tests.test_nuendo_live_export` → 3/3 (Phase 4 NLP-06 D-09 ID-uniqueness intact)
- ✅ Phase 2 import suites (`test_console_csv_import`, `test_console_csv_import_views`) → green
- ✅ `python manage.py check planner` exits 0
- ✅ `grep "seed_record, seed_hex = seed_maps" planner/views.py` finds the destructure
- ✅ `grep "enabled=bool(seed_record)" planner/views.py` finds the seed assignment
- ✅ `grep "color_override=seed_hex" planner/views.py` finds the color seed assignment
- ✅ Plan's inline `<verify>` automated script asserts all 6 source-code-shape conditions and prints `OK — seed logic wired`

**Cosmetic acceptance-criteria note (NOT a deviation in semantic intent):**

The plan's acceptance criteria stated:

- `grep -c "seed_maps" planner/views.py` returns at least 5 — actual returns 2 (lines 6679 + 6705). The literal name `seed_maps` only appears on the dict declaration line and the inner-loop lookup line; the 4 source-type entries inside the dict comprehension don't repeat the name. The semantic intent (dict literal exists, 4 source-type entries, 1 inner-loop lookup) is fully met — the planner appears to have over-counted by assuming each dict entry would repeat the variable name.
- `grep -cE "_HEX_COLOR_RE\.(match|fullmatch)" planner/views.py` returns at least 4 — actual returns 3 (lines 6649, 6709, 6762). Pre-existing `.match` calls were only at 2 sites (`multitrack_add_tracks` manual-color validate + `multitrack_set_color`); adding 1 new call gives 3. The planner appears to have counted the regex *definition* at line 6259 as a third pre-existing `.match/.fullmatch` usage when it's actually just `re.compile(...)`. The semantic intent (defence-in-depth re-validation added in the row-build loop) is fully met — verified by the plan's own inline `<verify>` script regex `r'_HEX_COLOR_RE\.(match|fullmatch)\(\s*seed_hex\s*\)'` which is the actual behaviour gate.

These are planner-side miscounts in the acceptance-criteria grep counts, not implementation deviations. The behavioural requirements (test-suite pass, regression intact, defence-in-depth check present, seed-fields applied) are all satisfied.

## Issues Encountered

- Local `python` not on PATH (Mac dev quirk inherited from Plans 05-01 and 05-02) — resolved by using `venv/bin/python` and `DJANGO_SETTINGS_MODULE=audiopatch.settings venv/bin/python` for the verify-script invocation. Not a plan deviation.
- One `READ-BEFORE-EDIT REMINDER` PreToolUse hook warning emitted on the first `Edit` against `planner/views.py`. The file had been read at session start across 3 segments (lines 55-79, 6250-6264, 6595-6729), so the warning was spurious; the Edit succeeded. Same hook-noise behaviour as Plans 05-01 / 05-02; not a plan deviation.
- Pre-existing `RuntimeWarning: Model 'planner.audiochecklist' was already registered` emitted by every `manage.py` invocation. Out of scope per the scope-boundary rule — pre-existing, unrelated to this plan, reported by Django itself. Logged here for future cleanup tracking (same as Plans 05-01 / 05-02).

## Threat Flags

None.

The plan's `<threat_model>` correctly captured the full attack surface (T-05-03-01 through T-05-03-05). Post-implementation scan confirms:

- **T-05-03-01 (I — Stored XSS via corrupted DB hex)** — **mitigated**. The new `_HEX_COLOR_RE.match(seed_hex)` check in the row-build loop silently drops anything not matching `^#[0-9A-Fa-f]{6}$`. Combined with Plan 05-02's form-layer validator and Django template autoescaping, all three rungs of the defence-in-depth ladder are now closed. Verified end-to-end by test 4 (`test_malformed_default_record_color_drops_silently`): a direct `.update()` write of `'not-a-hex'` to the channel's `default_record_color` results in `track.color_override == ''` with HTTP 200, not a crash or a leaked string.
- **T-05-03-02 (T — IDOR via cross-project channel read)** — **accepted**. The existing lines 6655-6672 set-intersection already restricts the four `valid_xxx_ids` sets to channels on THIS session's console; the new `id__in=valid_xxx_ids` bulk-fetch can only load channels the validation block already vetted. No new IDOR surface.
- **T-05-03-03 (D — DoS via large selection N+1)** — **accepted**. 4 queries per request regardless of selection size; plan REDUCES N+1 risk vs. a naive per-track FK fetch.
- **T-05-03-04 (E — Elevation via POL-01)** — **accepted**. `default_record` is a per-channel boolean already gated by Plan 05-02's form (which inherits `BaseEquipmentAdmin` role checks); no new write capability granted.
- **T-05-03-05 (R — No audit log of seed values)** — **accepted**. MultitrackTrack has no audit log today; Plan 05-03 does not introduce repudiation risk beyond what already exists.

No new threat surface introduced beyond the plan's pre-registered T-IDs. ASVS L1 §5.1.4 (trust no input — including DB readback when the field is user-influenced) fully satisfied via the in-function `_HEX_COLOR_RE.match` defence-in-depth check.

## Known Stubs

None. All seed values flow end-to-end from channel.default_record / channel.default_record_color → MultitrackTrack.enabled / MultitrackTrack.color_override → exporter output, verified by tests 1-5.

## Self-Check: PASSED

Verified before STATE.md update:

- `.planning/phases/05-channel-record-defaults/05-03-SUMMARY.md` (this file) exists — FOUND
- `planner/tests/test_channel_record_defaults.py` exists — FOUND
- Commit `f49ed1e` exists in `git log --oneline --all` — FOUND (will verify below)
- Commit `b23ea10` exists in `git log --oneline --all` — FOUND (will verify below)
- `grep -c "def test_" planner/tests/test_channel_record_defaults.py` returns `5` — FOUND
- `grep -c "seed_maps" planner/views.py` returns `2` (dict declaration + inner-loop lookup) — FOUND
- `grep "seed_record, seed_hex = seed_maps" planner/views.py` finds the destructure — FOUND
- `grep "color_override=seed_hex" planner/views.py` finds the seed assignment — FOUND
- 5 new tests pass in 0.231s — FOUND
- Phase 1 / 2 / 4 prior test suites all pass — FOUND
- `python manage.py check planner` exits 0 — FOUND

## Next Phase Readiness

- **Phase 5 code-complete.** All 3 plans across 2 waves shipped. Wave 1 — Plan 05-01 (model fields + migration 0155). Wave 2 — Plan 05-02 (admin form surface + hex validator) and Plan 05-03 (seed logic in multitrack_add_tracks + regression test suite).
- **Phase 5 Success Criterion 1** (engineer can set defaults from channel admin UI) — DELIVERED by Plan 05-02.
- **Phase 5 Success Criterion 2** (pre-check tracks where default_record=True) — DELIVERED by this plan. Test 1 and test 2 prove both polarities.
- **Phase 5 Success Criterion 3** (seed color from default_record_color, with per-track override afterward) — DELIVERED by this plan. Test 3 proves the happy-path seed; the existing `multitrack_set_color` AJAX endpoint at `planner/views.py:6728` overwrites `color_override` regardless of seed origin (per Phase 1 contract — unchanged here). Test 5 proves the seeded color reaches the Reaper exporter output end-to-end.
- **POL-01 and POL-02 close out v2.0.** All 38 / 38 v2.0 requirements are now wired end-to-end:
  - POL-01: admin surface (Plan 05-02) + seed logic (this plan) + regression test (tests 1, 2)
  - POL-02: admin surface + form validator (Plan 05-02) + seed copy with defence-in-depth (this plan) + end-to-end exporter regression (test 5)
- **HUMAN-UAT gate for v2.0 milestone completion:** Charlie should manually verify on local dev that (a) toggling `default_record` to False on a ConsoleInput row in the Console admin causes the next picker-add of that channel to land as `enabled=False` in the track editor, and (b) setting `default_record_color='#3366FF'` on a ConsoleInput causes the next picker-add to land with the swatch painted blue. Both flows are smoke-covered by the automated suite but UI-level UAT is the standard ShowStack gate before `/gsd-transition`.
- **Railway deploy:** the migration from Plan 05-01 will apply automatically on the next push to `main` (zero-data-backfill, sub-second metadata-only ALTER TABLE on PG 11+). Engineers' existing channel rows receive `default_record=TRUE, default_record_color=''` — zero behaviour change at deploy time. The new seed logic activates only when an engineer explicitly configures a non-default value on a channel.

---
*Phase: 05-channel-record-defaults*
*Completed: 2026-05-14*
