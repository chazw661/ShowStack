---
phase: 05-channel-record-defaults
verified: 2026-05-14T20:12:02Z
status: human_needed
score: 5/5 must-haves verified (automated); 2 admin/picker UX checks pending HUMAN-UAT
requirements_met: 2
requirements_total: 2
overrides_applied: 0
re_verification: false
human_verification:
  - test: "Toggle default_record=False on a ConsoleInput in Console admin, then picker-add that channel to a new MultitrackSession"
    expected: "The resulting track row in the editor renders disabled by default; toggling its per-track checkbox to enabled still works (no regression of multitrack_set_enabled)"
    why_human: "Plan 05-02 surface is admin-inline UI; visual rendering of the new checkbox column, vertical centering, and the round-trip from admin save → picker-add → editor display can only be confirmed by eyeballing the rendered admin page and editor against a real Postgres DB after migration 0155 applies"
  - test: "Set default_record_color='#3366FF' on a ConsoleInput in Console admin, then picker-add that channel"
    expected: "The new track row shows the blue swatch; the HTML pattern='#[0-9A-Fa-f]{6}' browser hint fires on bad input; submitting bad hex shows the verbatim error 'Color must be empty or #RRGGBB hex, got: <repr>'"
    why_human: "Widget styling (80px width, monospace, placeholder/pattern/title attrs) and the swatch-color rendering in the editor partial are visual concerns not captured by Django form-level tests"
  - test: "Confirm Railway migration 0155 applies cleanly on next deploy"
    expected: "Postgres ALTER TABLE ADD COLUMN runs sub-second per the additive-migration plan; all existing channel rows backfill to default_record=TRUE / default_record_color=''; the planner app boots without errors against the new schema"
    why_human: "Migration has NOT been applied to Railway Postgres yet — runs automatically on next push to main via railway.json startCommand. Cannot be verified programmatically from this terminal per CLAUDE.md 'do not run destructive operations against Railway Postgres' rule"
---

# Phase 5: Channel Record Defaults Verification Report

**Phase Goal:** Engineers stop re-ticking the same obvious tracks every gig — channels carry per-channel `default_record` and `default_record_color` seed flags that pre-populate new sessions
**Verified:** 2026-05-14T20:12:02Z
**Status:** human_needed (all 5 automated truths verified; 3 visual/deploy items routed to HUMAN-UAT)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All 4 ConsoleChannel models expose `default_record` (Bool, default=True) and `default_record_color` (CharField, max_length=7, default='') | ✓ VERIFIED | Field introspection: `for M in (ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput, ConsoleStereoOutput): M._meta.get_field('default_record')` returns `BooleanField/default=True` and `default_record_color` returns `CharField/max_length=7/default=''` on all 4; planner/models.py lines 859, 907, 936, 962 (default_record) and 863, 911, 940, 966 (default_record_color) |
| 2 | All 4 ConsoleChannel ModelForms in planner/forms.py surface the two fields in Meta.fields AND validate hex via `clean_default_record_color` | ✓ VERIFIED | `grep -c "def clean_default_record_color" planner/forms.py` → 4; `grep -c "must be empty or #RRGGBB hex" planner/forms.py` → 4; live form bind with `'#GG0000'` raises `"Color must be empty or #RRGGBB hex, got: '#GG0000'"`; admin inlines bind these forms at planner/admin.py:585, 646, 691, 736 |
| 3 | When picker adds a channel with `default_record=False`, resulting MultitrackTrack lands disabled (POL-01) | ✓ VERIFIED | Test `test_default_record_false_seeds_enabled_false` passes; `enabled=bool(seed_record)` at planner/views.py:6716; `seed_record` sourced from `seed_maps[src_type][raw_id][0]` which is the channel's `default_record` |
| 4 | When picker adds a channel with `default_record_color='#XXXXXX'`, resulting MultitrackTrack `color_override` is seeded with that hex (POL-02) | ✓ VERIFIED | Test `test_default_record_color_seeds_color_override` passes (`#FF8800` → `track.color_override='#FF8800'`); `color_override=seed_hex` at planner/views.py:6717; defence-in-depth `_HEX_COLOR_RE.match` at planner/views.py:6709 silently drops malformed hex |
| 5 | Seeded color flows end-to-end to Reaper RPP export (PEAKCOL field) | ✓ VERIFIED | Test `test_seeded_color_appears_in_reaper_export` passes: seed `#FF8800` → `multitrack_export_rpp` body contains `str(hex_to_peakcol('#FF8800'))`; full chain channel → seed → MultitrackTrack.color_override → exporter PEAKCOL confirmed in 0.237s |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `planner/models.py` | 4 channel models gain `default_record` (Bool, default=True) + `default_record_color` (CharField max_length=7, default='') | ✓ VERIFIED | grep counts: `default_record = models.BooleanField` → 4, `default_record_color = models.CharField` → 4; lines 859-868, 907-916, 936-945, 962-971; ConsoleImport correctly NOT touched |
| `planner/migrations/0155_channel_record_defaults.py` | 8 AddField operations (2 fields × 4 models), single dep on 0154_multitrack_template | ✓ VERIFIED | `grep -c "migrations.AddField" planner/migrations/0155_channel_record_defaults.py` → 8; dependencies = `[('planner', '0154_multitrack_template')]`; all `default_record` AddField carry `default=True`; all `default_record_color` AddField carry `blank=True, default='', max_length=7`; additive-only, metadata-only ALTER TABLE on PG 11+; `makemigrations --dry-run` → No changes detected |
| `planner/forms.py` | 4 ConsoleChannel ModelForms expose the fields + `clean_default_record_color` regex validator | ✓ VERIFIED | 4 form classes have `default_record` in Meta.fields (lines 64, 154, 223, 285); 4 `def clean_default_record_color` methods (lines 119, 189, 255, 302); 4 verbatim error strings; widget styling block (80px, font-mono, #RRGGBB placeholder) on default_record_color across all 4 forms; ConsoleStereoOutputForm got new explicit `__init__` matching the other 3 |
| `planner/views.py` (multitrack_add_tracks) | Bulk-fetch seed_maps + per-track seeded MultitrackTrack construction with _HEX_COLOR_RE defence-in-depth | ✓ VERIFIED | `seed_maps` dict literal at line 6679 with 4 source_type entries (input/aux/matrix/stereo); destructure `seed_record, seed_hex = seed_maps[src_type].get(raw_id, (True, ''))` at line 6705; `_HEX_COLOR_RE.match(seed_hex)` guard at line 6709; `enabled=bool(seed_record)` at line 6716; `color_override=seed_hex` at line 6717 |
| `planner/tests/test_channel_record_defaults.py` | 5-test regression class with end-to-end Reaper export assertion | ✓ VERIFIED | 5 `def test_` methods in `ChannelRecordDefaultsSeedTests`; imports `hex_to_peakcol` from planner.utils.reaper_export; test_5 reverses `planner:multitrack_export_rpp` and asserts `str(hex_to_peakcol(seed_hex))` appears in body; all 5 tests pass in 0.237s |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `planner/models.py` ConsoleInput/Aux/Matrix/Stereo new fields | `planner/migrations/0155_channel_record_defaults.py` | makemigrations detected fields → 8 AddField ops | ✓ WIRED | `makemigrations --dry-run` reports "No changes detected"; migration applies cleanly in test DB (visible in test output: "Applying planner.0155_channel_record_defaults... OK") |
| `planner/forms.py` ConsoleXxxForm.Meta.fields | Django admin Console change-form TabularInline rows | `form = ConsoleXxxForm` on 4 Inline classes | ✓ WIRED | planner/admin.py:585, 646, 691, 736 each bind the corresponding form; Django attaches the new Meta.fields automatically — no admin-class edit required |
| `planner/views.py` multitrack_add_tracks seed_maps lookup | ConsoleInput/Aux/Matrix/Stereo.default_record + default_record_color | `.values_list('id', 'default_record', 'default_record_color').filter(id__in=valid_xxx_ids)` | ✓ WIRED | 4 query lines at 6680-6683; restricted to validated ID sets (no IDOR — already vetted at lines 6655-6672); tests 1-5 all exercise this path live |
| MultitrackTrack rows created by picker | Reaper / Nuendo Live exporters | `resolved_color` / `enabled` @property unchanged from Phase 1 | ✓ WIRED | Test 5 proves the chain end-to-end: seeded color appears in Reaper RPP PEAKCOL; Phase 1's 42-test test_reaper_export and Phase 4's 3-test test_nuendo_live_export still green |
| Form-layer hex regex | views.py `_HEX_COLOR_RE` | Verbatim duplicate (not import — would be circular) | ✓ WIRED (intentional dupe) | Same `^#[0-9A-Fa-f]{6}$` pattern in 4 places in forms.py + module-level in views.py:6259; Plan 02 documented this as deliberate to avoid `forms.py ↔ views.py` circular import; defence-in-depth ladder closed by re-validation at AJAX boundary at views.py:6709 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `multitrack_add_tracks` view (planner/views.py:6598) | `seed_maps[src_type]` | Live DB query against ConsoleInput/Aux/Matrix/Stereo restricted to validated IDs | Yes — `.values_list('id','default_record','default_record_color')` returns real tuples per channel | ✓ FLOWING |
| `MultitrackTrack.color_override` (DB column) | `color_override=seed_hex` (line 6717) | seed_maps lookup → defence-in-depth filter → assignment | Yes — verified by Test 3 (live picker POST → DB read shows '#FF8800') | ✓ FLOWING |
| `MultitrackTrack.enabled` (DB column) | `enabled=bool(seed_record)` (line 6716) | seed_maps lookup → bool cast → assignment | Yes — verified by Tests 1 & 2 (True polarity AND False polarity round-trip through DB) | ✓ FLOWING |
| Reaper RPP exporter PEAKCOL line | hex `#FF8800` → `hex_to_peakcol` → integer in body | MultitrackTrack.color_override (DB) → `resolved_color` @property → exporter | Yes — Test 5 asserts `str(hex_to_peakcol('#FF8800'))` is `in body` | ✓ FLOWING |
| Admin form input → channel row write | `cleaned_data['default_record_color']` | `clean_default_record_color` returns stripped value or raises ValidationError | Yes — live form bind with `'abc1234'` produces verbatim error message | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 5 regression suite | `venv/bin/python manage.py test planner.tests.test_channel_record_defaults -v 2` | 5 tests pass in 0.237s | ✓ PASS |
| Full planner test suite (regression) | `venv/bin/python manage.py test planner -v 0` | 103 tests pass in 5.082s | ✓ PASS |
| Django system check | `venv/bin/python manage.py check planner` | "System check identified no issues (0 silenced)" | ✓ PASS |
| Migration captures full model delta | `venv/bin/python manage.py makemigrations planner --dry-run` | "No changes detected in app 'planner'" | ✓ PASS |
| Form validator emits documented error string | Live form bind `ConsoleInputForm({'default_record_color': '#GG0000'}).errors` | Error literal: `"Color must be empty or #RRGGBB hex, got: '#GG0000'"` | ✓ PASS |
| Form validator accepts valid hex | Live form bind `ConsoleInputForm({'default_record_color': '#A1B2C3'})` | No error on `default_record_color` field | ✓ PASS |
| Form validator accepts empty | Live form bind `ConsoleInputForm({'default_record_color': ''})` | No error on `default_record_color` field | ✓ PASS |
| Field metadata introspection | Python introspect `_meta.get_field(...)` on all 4 models | All 4 expose the two fields with documented signatures | ✓ PASS |
| Phase 1 reorder regression intact | `venv/bin/python manage.py test planner.tests.test_multitrack_reorder` | Green | ✓ PASS |
| Phase 1 Reaper byte-stable contract intact | `venv/bin/python manage.py test planner.tests.test_reaper_export` | 42/42 green | ✓ PASS |
| Phase 4 Nuendo Live ID-uniqueness intact | `venv/bin/python manage.py test planner.tests.test_nuendo_live_export` | 3/3 green | ✓ PASS |
| All 5 phase commits present | `git log --oneline --all | grep -E "8003594|f4c0a99|7121792|f49ed1e|b23ea10"` | All 5 commits present | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| POL-01 | 05-01, 05-02, 05-03 | Each ConsoleChannel carries a `default_record` boolean; new sessions pre-check tracks where `default_record=True` | ✓ SATISFIED | Field exists on all 4 channel models with `default=True` (Plan 01); surfaced as checkbox in admin TabularInline (Plan 02); seeded into MultitrackTrack.enabled at picker-add (Plan 03); Tests 1 & 2 verify both polarities |
| POL-02 | 05-01, 05-02, 05-03 | Each ConsoleChannel carries a `default_record_color` (hex) used as seed color for new tracks unless overridden | ✓ SATISFIED | Field exists on all 4 channel models (CharField max_length=7, default=''); surfaced + hex-validated in 4 forms; seeded into MultitrackTrack.color_override at picker-add with defence-in-depth; Test 3 verifies happy path; Test 4 verifies malformed-hex safe-drop; Test 5 verifies end-to-end chain into Reaper RPP PEAKCOL output |

No orphaned requirements found. REQUIREMENTS.md maps POL-01 + POL-02 to Phase 5; both are claimed by all 3 plans and verified above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TODO/FIXME/placeholder/stub patterns in any phase 5 file | — | — |

`placeholder='#RRGGBB'` widget attr in forms.py is intentional HTML placeholder text (UI hint), not a stub. All seed code paths are fully wired with live data sources; no hardcoded empty returns, no commented-out branches, no logging-only handlers.

### Code Review Cross-Reference

05-REVIEW.md flagged 0 Critical, 0 Warning, 3 Info findings — all deliberate trade-offs documented in plans:

- **IN-01:** Verbatim duplication of `clean_default_record_color` across 4 forms (avoids circular import; future refactor via `planner/validators.py` extraction noted).
- **IN-02:** Local `import re` inside the 4 validator methods (matches Phase 1 forms.py import-locality posture).
- **IN-03:** Long dict-comprehension lines in `seed_maps` (~160 chars vs informal 100-char limit elsewhere). Optional formatting cleanup; behavior is correct.

None of these affect goal achievement. Logged for future refactor visibility.

### Human Verification Required

Three items require eyeball / Railway-side validation that cannot be exercised from the test runner:

#### 1. Admin form surface — checkbox + hex input render correctly on Console admin

**Test:** In the Console admin change-form, scroll to a ConsoleInput row in the inline table. Confirm a "Default record" checkbox column exists, an 80px monospace hex input column exists with `#RRGGBB` placeholder text, and toggling the checkbox + saving the form persists the new state. Then picker-add that channel to a new MultitrackSession.
**Expected:** With default_record toggled OFF, the new track lands disabled in the editor. With default_record_color='#3366FF', the new track row paints blue.
**Why human:** Visual rendering of admin inline columns (vertical-centering of the new checkbox, monospace width of the hex input, tooltip on hover, the editor's swatch-render of the seeded color) is not coverable by Django form-level tests.

#### 2. Form-layer hex validator UX — pattern attr fires; error message renders cleanly

**Test:** In the Console admin change-form, enter `'#GG0000'` (7-char non-hex) into the default_record_color input on a ConsoleInput row, submit. Confirm: (a) browser HTML5 `pattern` attribute fires a tooltip-style hint before submission AND (b) on submit, Django renders the error `"Color must be empty or #RRGGBB hex, got: '#GG0000'"` adjacent to the offending row.
**Expected:** Both UX layers fire. The server-side error message is byte-identical to the documented string.
**Why human:** HTML5 pattern-attribute behavior is browser-rendered and not testable from Django's test Client (which bypasses HTML5 validation entirely).

#### 3. Railway migration 0155 applies cleanly on next deploy

**Test:** After next push to `main`, watch `railway logs` for the `migrate` step in the deploy chain. Confirm "Applying planner.0155_channel_record_defaults... OK" appears with no errors; subsequently confirm via `railway run python manage.py shell` that `ConsoleInput.objects.first().default_record` returns `True` and `default_record_color` returns `''` (i.e., backfill applied to existing channel rows).
**Expected:** Sub-second migration runtime per CLAUDE.md additive-migrations rule; zero data backfill required (Django field defaults are the backfill); all existing channel rows usable post-migration.
**Why human:** Per CLAUDE.md "Do not run destructive SQL against Railway Postgres without confirming with Charlie first" — Charlie owns the Railway-deploy gate. Migration 0155 is additive-only per the plan's threat model (T-05-01-03: 8 AddField with constant defaults → PG 11+ metadata-only ALTER TABLE) but the actual deploy outcome can only be confirmed against the live Railway environment.

### Gaps Summary

**No gaps blocking goal achievement.** All 5 observable truths verified through programmatic checks (field introspection, full 103-test regression suite green including 5 dedicated POL-01/POL-02 tests, live form-bind validation, system check clean, dry-run migration clean). All 5 required artifacts verified at all four levels (exists, substantive, wired, data flows). All 5 key links verified, including the critical end-to-end chain `channel → seed → MultitrackTrack → Reaper PEAKCOL` proved by Test 5. POL-01 and POL-02 are SATISFIED.

The remaining items are visual UAT (admin inline column rendering + swatch paint in editor) and an external-environment confirmation (Railway migration apply on next deploy). Neither blocks code-complete status; both are the standard ShowStack HUMAN-UAT gate documented in 05-03-SUMMARY.md and STATE.md ("HUMAN-UAT pending POL-01 + POL-02 picker/admin smoke").

---

_Verified: 2026-05-14T20:12:02Z_
_Verifier: Claude (gsd-verifier)_
