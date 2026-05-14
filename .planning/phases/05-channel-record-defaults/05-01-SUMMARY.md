---
phase: 05-channel-record-defaults
plan: 01
subsystem: model

tags: [model-fields, migration, channel-record-defaults, pol-01, pol-02, additive-migration]

# Dependency graph
requires:
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: MultitrackTrack.color_override (max_length=7, blank=True, default='') — the exact CharField shape default_record_color mirrors for seed-copy compatibility
  - phase: 02-console-csv-import
    provides: ConsoleChannel `color` (Yamaha palette NAME) field — left untouched; default_record_color is a separate hex field
provides:
  - "ConsoleInput.default_record / ConsoleAuxOutput.default_record / ConsoleMatrixOutput.default_record / ConsoleStereoOutput.default_record (BooleanField, default=True)"
  - "ConsoleInput.default_record_color / ConsoleAuxOutput.default_record_color / ConsoleMatrixOutput.default_record_color / ConsoleStereoOutput.default_record_color (CharField max_length=7, blank=True, default='')"
  - "Migration 0155_channel_record_defaults.py — 8 AddField operations, single dependency on 0154_multitrack_template"
affects: [05-02, 05-03, console-admin-form, multitrack-session-seed-logic]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive-only Django migration with constant defaults — Postgres metadata-only ALTER TABLE ADD COLUMN on PG 11+, sub-second across all Railway-tenant projects"
    - "Hex-color CharField (max_length=7) at the ConsoleChannel level, matching MultitrackTrack.color_override exactly so seed-copy is a one-liner with no None-handling"
    - "Validation deferred to form layer (Plan 02) and AJAX boundary (Plan 03) per Phase 1 defence-in-depth pattern — no model-layer validator"

key-files:
  created:
    - "planner/migrations/0155_channel_record_defaults.py — 8 AddField operations"
  modified:
    - "planner/models.py — +40 lines across 4 ConsoleChannel classes (default_record + default_record_color × 4)"

key-decisions:
  - "default_record=True backfill chosen over False — preserves today's UX (every picker-added track is enabled by default; opt OUT for talkback/monitor sends, not opt IN every gig)"
  - "default_record_color uses default='' (not None) and max_length=7 — matches MultitrackTrack.color_override's exact signature so Plan 03's seed-copy is `track.color_override = channel.default_record_color` with no transformation"
  - "No choices= on default_record_color — engineers paint with custom hex via the swatch picker, constraining to palette swatches would block that path"
  - "No model-layer hex validator — validation lives at the form layer (Plan 02) and AJAX boundary (Plan 03 add_tracks), matching the same pattern Phase 1 used for MultitrackTrack.color_override (no model validator; _HEX_COLOR_RE at the picker view boundary)"
  - "Field placement: immediately after each class's existing `color = ...` line — clusters seed-recording metadata visually so future readers see the related fields together"

patterns-established:
  - "Two-field seed-default pattern on a ConsoleChannel model: boolean toggle + optional hex string, both blank-default backwards-compatible, both consumed by downstream session-builder seed logic via @property or direct attribute read"
  - "Migration naming convention: {seq}_{snake_case_description}.py with `--name` flag explicitly set on makemigrations — keeps the auto-generated filename predictable and reviewable"

requirements-completed: [POL-01, POL-02]

# Metrics
duration: ~3min
completed: 2026-05-14
---

# Phase 5 Plan 01: Channel Record Defaults — Model Foundation Summary

**Added `default_record` (bool, default=True) and `default_record_color` (CharField max_length=7, blank=True, default='') to all 4 ConsoleChannel models and shipped the additive migration 0155 — the schema floor POL-01 and POL-02 need before Plan 02's admin form surface and Plan 03's session-seed logic can land.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-14T19:44:22Z
- **Completed:** 2026-05-14T19:46:35Z
- **Tasks:** 2 / 2
- **Files modified:** 1 (planner/models.py)
- **Files created:** 1 (planner/migrations/0155_channel_record_defaults.py)

## Accomplishments

- All 4 ConsoleChannel models (`ConsoleInput`, `ConsoleAuxOutput`, `ConsoleMatrixOutput`, `ConsoleStereoOutput`) now carry the two new fields with identical signatures across the board. Verified by in-process `hasattr` assertion (`from planner.models import ...; assert all(hasattr(m, 'default_record') and hasattr(m, 'default_record_color') for m in [...])`).
- Migration `planner/migrations/0155_channel_record_defaults.py` generated cleanly via `python manage.py makemigrations planner --name channel_record_defaults` — exactly 8 AddField operations, single dependency on `('planner', '0154_multitrack_template')`, no AUTH_USER_MODEL swap (neither new field references User).
- `python manage.py check planner` exits 0 (no model errors).
- `python manage.py makemigrations planner --dry-run` reports `No changes detected in app 'planner'` — proves the migration captures the full model delta with zero residual drift.
- `ConsoleImport` (audit-snapshot model) was correctly left untouched per plan instruction; only the 4 channel models received the new fields.
- The existing `color` field (Yamaha palette NAME, used by Rivage/Nuendo exporters and CSV import) was preserved unchanged on all 4 models — `default_record_color` is a separate hex CharField at `max_length=7`, distinct from the palette-name field.
- No `python manage.py migrate` invocation — migration will run automatically on Railway via `railway.json` `startCommand`'s `migrate` step on next deploy. Per CLAUDE.md "Charlie runs migrations against prod" rule.

## Task Commits

Each task was committed atomically on `main` (sole-developer workflow per CLAUDE.md):

1. **Task 1: Add `default_record` and `default_record_color` fields to all 4 ConsoleChannel models** — `8003594` (feat) — `planner/models.py` only, +40 lines / -0 lines.
2. **Task 2: Generate migration `0155_channel_record_defaults`** — `f4c0a99` (feat) — `planner/migrations/0155_channel_record_defaults.py` only, +53 lines (new file).

No file deletions in either commit (`git diff --diff-filter=D HEAD~1 HEAD` empty for both).

## Files Created/Modified

### `planner/models.py` (modified — commit `8003594`)

For each of the 4 channel model classes, inserted these two fields immediately after the existing `color = models.CharField(...)` line:

```python
default_record = models.BooleanField(
    default=True,
    help_text="If True, new multitrack sessions pre-check (enable) tracks created from this channel. POL-01.",
)
default_record_color = models.CharField(
    max_length=7,
    blank=True,
    default='',
    help_text="Optional hex seed color (#RRGGBB) for tracks created from this channel. Empty = no seed; per-track override always wins. POL-02.",
)
```

Insertion points: lines following the pre-existing `color = ...` declaration on:
- `ConsoleInput` (was line 858 — fields now follow it)
- `ConsoleAuxOutput` (was line 896)
- `ConsoleMatrixOutput` (was line 915)
- `ConsoleStereoOutput` (was line 931)

### `planner/migrations/0155_channel_record_defaults.py` (created — commit `f4c0a99`)

Auto-generated by `makemigrations planner --name channel_record_defaults`. Structure:

- Header: `# Generated by Django 5.2.4 on 2026-05-14 19:45`
- Dependencies: `[('planner', '0154_multitrack_template')]` (single dependency; no AUTH_USER_MODEL swap)
- Operations: 8 `migrations.AddField` ops, alphabetical-by-model order (consoleauxoutput → consoleinput → consolematrixoutput → consolestereooutput, two ops each)
- Every `default_record` AddField carries `default=True` and the POL-01 help_text
- Every `default_record_color` AddField carries `blank=True`, `default=''`, `max_length=7`, and the POL-02 help_text

## Decisions Made

- **`default_record` default = True (not False).** Backwards-compatible: every existing channel becomes a default-on track, matching today's behaviour where every picker-added track is enabled by default. Engineers opt OUT obvious-don't-record channels (talkback, monitor sends) once at the channel level rather than uncheck them on every new session. Net change in user-observable behaviour at deploy time: zero.
- **`default_record_color` default = `''` (empty string, not None).** Matches `MultitrackTrack.color_override`'s `blank=True, default=''` contract exactly, so Plan 03's seed-copy step is a one-liner `track.color_override = channel.default_record_color` with no None-handling. `max_length=7` matches `color_override` so the two values are 100% interchangeable in the seed direction.
- **No `choices=` on `default_record_color`.** The Phase 3 swatch picker offers both palette swatches AND a custom-hex path; constraining the channel field to palette names would break engineers who paint tracks with off-palette hexes. Kept the field open per the plan's explicit instruction.
- **No model-layer hex validator.** Validation lives at the form layer (Plan 02 — Django form `clean_default_record_color` will run `_HEX_COLOR_RE`) and the AJAX boundary (Plan 03's `add_tracks` view defence-in-depth re-checks before persisting to `color_override`). This matches Phase 1's pattern for `MultitrackTrack.color_override` exactly (no model validator; `_HEX_COLOR_RE` at the picker view boundary at `planner/views.py:6259`).
- **Field placement: immediately after each class's existing `color = ...` line.** Clusters seed-recording metadata visually — future readers see `color` (palette NAME, for Rivage CSV export) → `default_record` (session-seed bool) → `default_record_color` (session-seed hex) as a coherent group rather than scattered across the class.
- **Migration generated, not hand-written.** Per the plan's explicit "DO NOT hand-edit the migration file beyond confirming" instruction. `makemigrations` produced exactly the expected shape on the first run — no model fix-and-regenerate cycle needed.

## Deviations from Plan

None — plan executed exactly as written. All `<verify>` automated checks pass and all `<acceptance_criteria>` items are green:

- ✅ `grep -c "default_record = models.BooleanField" planner/models.py` → 4
- ✅ `grep -c "default_record_color = models.CharField" planner/models.py` → 4
- ✅ `grep -c "max_length=7" planner/models.py` → 8 (4 new `default_record_color` + 4 pre-existing — well above the "at least 4 new matches" floor)
- ✅ `python manage.py check planner` exits 0
- ✅ File `planner/migrations/0155_channel_record_defaults.py` exists
- ✅ `grep -c "migrations.AddField" planner/migrations/0155_channel_record_defaults.py` → 8
- ✅ `grep "'planner', '0154_multitrack_template'" planner/migrations/0155_channel_record_defaults.py` → 1 match
- ✅ `grep -c "name='default_record'" planner/migrations/0155_channel_record_defaults.py` → 4
- ✅ `grep -c "name='default_record_color'" planner/migrations/0155_channel_record_defaults.py` → 4
- ✅ `grep -c "default=True" planner/migrations/0155_channel_record_defaults.py` → 4 (one per `default_record` AddField)
- ✅ `python manage.py makemigrations planner --dry-run` reports `No changes detected in app 'planner'` after Task 2

## Issues Encountered

- Local `python` was not on PATH (Mac dev env quirk — Python is installed as `python3` at `/Library/Frameworks/Python.framework/...`). Resolved by using the project's `venv/bin/python` for all manage.py invocations. Not a plan deviation; pre-existing developer-environment shape.
- Three `READ-BEFORE-EDIT REMINDER` PreToolUse hook warnings were emitted on consecutive `Edit` calls against `planner/models.py`. The file was read at session start (lines 800-950 and 1060-1075) so the warnings were spurious; all four model edits succeeded. Not a plan deviation.
- Pre-existing `RuntimeWarning: Model 'planner.audiochecklist' was already registered` emitted by every `manage.py` invocation. Out of scope for this plan per the scope-boundary rule — pre-existing, unrelated to the new fields, and reported by Django itself (not a test failure). Logged here for future cleanup tracking.

## Notes for Plan 02 (admin form surface)

The form classes that need to expose the two new fields are in **`planner/forms.py`**. Look for:

- `ConsoleInputForm` — surface `default_record` (BooleanField → checkbox) and `default_record_color` (CharField → text input or swatch picker)
- `ConsoleAuxOutputForm` — same two fields
- `ConsoleMatrixOutputForm` — same two fields
- `ConsoleStereoOutputForm` — same two fields

Suggested form-layer validation (matches Phase 1 `_HEX_COLOR_RE` regex at `planner/views.py:6259`):

```python
def clean_default_record_color(self):
    value = self.cleaned_data.get('default_record_color', '')
    if value and not _HEX_COLOR_RE.match(value):
        raise ValidationError('Color must be #RRGGBB hex format (e.g. #FF5500) or empty.')
    return value
```

The `help_text` strings on the model fields are deliberately written as form-friendly labels — Plan 02 may reuse them verbatim for form help text without re-wording.

## Notes for Plan 03 (session-seed logic)

The exact attribute names to read on a resolved-source channel:

- `channel.default_record` — boolean. Seed `MultitrackTrack.enabled = channel.default_record` at track creation in `add_tracks`.
- `channel.default_record_color` — string (`''` or `'#RRGGBB'`). Seed `MultitrackTrack.color_override = channel.default_record_color` directly; the empty-string case naturally falls through to the existing color-resolution chain (override → source.color → None).

Both attributes are available on all 4 channel model classes, so the seed logic does not need type-dispatch — a single read works regardless of whether the source is `ConsoleInput`, `ConsoleAuxOutput`, `ConsoleMatrixOutput`, or `ConsoleStereoOutput`.

Defence-in-depth check at the AJAX boundary (matches Phase 1 pattern):

```python
if channel.default_record_color and _HEX_COLOR_RE.match(channel.default_record_color):
    track.color_override = channel.default_record_color
```

The leading `if` clause protects against any future channel record that somehow bypassed Plan 02's form validator (manual SQL, fixture import, etc.) — same pattern Phase 1 uses for `MultitrackTrack.color_override` writes.

## User Setup Required

None — the migration is purely additive (8 AddField with constant defaults). On the next push to `main`:

1. Railway's `railway.json` `startCommand` will run `python manage.py migrate` automatically as part of the deploy chain.
2. Postgres will execute 8 `ALTER TABLE ADD COLUMN` operations. PG 11+ treats `ADD COLUMN` with a constant default as a metadata-only operation — sub-second across all tenant projects regardless of console table size (a fully populated Yamaha CL5 = 107 channel rows; trivial).
3. Every existing channel row receives `default_record=TRUE` and `default_record_color=''` automatically. No data backfill script required; the Django field defaults are the backfill.

No environment variables, secrets, or external service configuration required. No local-dev action needed — `runserver` will apply 0155 automatically on next start.

## Threat Flags

None.

The plan's `<threat_model>` correctly anticipated zero new attack surface from a model-fields-only plan — no new request/response paths, no new auth gates, no new user-input handling. Post-implementation scan confirms: no files in this plan create network endpoints, auth paths, file-system access, or trust-boundary code. The XSS concern flagged in the orchestrator's brief (`default_record_color` rendered unsanitized → XSS) is correctly deferred to Plan 02 (form input boundary) and Plan 03 (template rendering of seeded color); Plan 01 has no rendering or input-handling code.

## Self-Check: PASSED

Verified before STATE.md update:

- `.planning/phases/05-channel-record-defaults/05-01-SUMMARY.md` (this file) exists — FOUND (the file you're reading)
- `planner/migrations/0155_channel_record_defaults.py` exists — FOUND (`ls planner/migrations/0155_channel_record_defaults.py` returns 0)
- Commit `8003594` exists in `git log --oneline --all` — FOUND
- Commit `f4c0a99` exists in `git log --oneline --all` — FOUND
- `grep -c "default_record = models.BooleanField" planner/models.py` returns `4` — FOUND
- `grep -c "default_record_color = models.CharField" planner/models.py` returns `4` — FOUND
- `grep -c "migrations.AddField" planner/migrations/0155_channel_record_defaults.py` returns `8` — FOUND
- `python manage.py check planner` exits 0 — FOUND
- `python manage.py makemigrations planner --dry-run` reports "No changes detected" — FOUND
- In-process `hasattr` assertion across all 4 models prints `OK` — FOUND

## Next Phase Readiness

- **Plan 05-02 unblocked.** All 4 `Console{Input,AuxOutput,MatrixOutput,StereoOutput}` models carry `default_record` and `default_record_color`. The 4 corresponding `Form` subclasses in `planner/forms.py` are ready to add the two new fields and a `clean_default_record_color` validator.
- **Plan 05-03 unblocked at the schema level.** The seed logic in `add_tracks` (or wherever Phase 1 instantiates `MultitrackTrack` from a picker selection) can now read `channel.default_record` and `channel.default_record_color` directly. The empty-string default on `default_record_color` means the no-seed path requires no extra branching — it falls through to the existing color-resolution chain naturally.
- **Railway deploy gate:** the migration only kicks in on the next push to `main` triggering the Railway redeploy. If Charlie pushes Phase 5 work in a single batch (Plans 01+02+03 together), the migration lines up with the first runtime read of the new fields — zero risk of a "field doesn't exist yet" error window.
- **Phase-level Success Criterion 1** (engineer can set defaults from channel admin/edit UI) — schema floor complete; Plan 02 owns the form surface.
- **Phase-level Success Criterion 2** (pre-check tracks where `default_record=True`) — `default_record` field exists with `default=True` backfill; Plan 03 owns the seed logic.
- **Phase-level Success Criterion 3** (seed color from `default_record_color`) — `default_record_color` field exists with `max_length=7` matching `MultitrackTrack.color_override`; Plan 03 owns the seed copy.

---
*Phase: 05-channel-record-defaults*
*Completed: 2026-05-14*
