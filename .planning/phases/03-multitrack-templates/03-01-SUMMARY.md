---
phase: 03-multitrack-templates
plan: 01
subsystem: database
tags: [django, models, migration, multitrack, templates, owner-scoped]

# Dependency graph
requires:
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: "MultitrackSession + MultitrackTrack models, _source_model_for() dispatch helper, TARGET_DAW_CHOICES / FEED_SOURCE_CHOICES / TRACK_ORDER_MODE_CHOICES / SOURCE_TYPE_CHOICES constants"
provides:
  - "MultitrackTemplate model (owner-scoped via created_by, NOT project-scoped)"
  - "MultitrackTemplateSlot model with cross-console portable (source_type, source_number) slot keys"
  - "MultitrackTemplate.apply_to_session(session) instance method returning (mapped, skipped, summary)"
  - "_summarise_skipped_slots(skipped) module-level helper for D-10 banner text"
  - "Additive migration 0154_multitrack_template creating both tables with zero ALTER TABLE on existing tables"
affects: [03-02 admin registration, 03-03 view endpoints (save/rename/delete), 03-04 form integration, 03-05 dashboard + new-session UI]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Owner-scoped persistence (created_by FK, no project FK) — divergence from CurrentProjectMiddleware standard, documented inline"
    - "Cross-console portable slot keys via (source_type, source_number) CharField pair instead of FK to channel-row PK"
    - "Apply algorithm placed as instance method on parent model + module-level pure helper (testable surface)"
    - "Additive-only migration: CreateModel + AddIndex + AlterUniqueTogether ops touch only the newly-created tables"

key-files:
  created:
    - "planner/migrations/0154_multitrack_template.py"
  modified:
    - "planner/models.py (appended 169 lines after MultitrackTrack class, before stray comment block)"

key-decisions:
  - "Reused MultitrackSession.TARGET_DAW_CHOICES / FEED_SOURCE_CHOICES / TRACK_ORDER_MODE_CHOICES and MultitrackTrack.SOURCE_TYPE_CHOICES verbatim instead of redefining (single source of truth)"
  - "Placed apply_to_session as instance method on MultitrackTemplate per RESEARCH Assumption A7 (clean test surface)"
  - "Guarded MultitrackTrack.objects.bulk_create with `if new_tracks:` to avoid empty-list INSERT noise on metadata-only templates (D-13 path)"
  - "Generated migration via `makemigrations --name multitrack_template` rather than hand-writing — canonical autodetector form, AlterUniqueTogether ops apply to newly-created tables (no ALTER on existing tables)"

patterns-established:
  - "D-05 owner-scoping: MultitrackTemplate.created_by is the sole ownership anchor; no project FK anywhere in this subsystem"
  - "D-02 cross-console portability: slot rows persist source_number (CharField, engineer-meaningful channel label), not source_id (DB PK)"
  - "D-10 skip-and-summarise: unresolvable slots collected as (source_type, source_number) tuples, grouped by source_type into human-readable banner text"

requirements-completed: [TPL-01, TPL-02]

# Metrics
duration: 2m 9s
completed: 2026-05-13
---

# Phase 03 Plan 01: Multitrack Template Models + Migration Summary

**Owner-scoped MultitrackTemplate persistence with cross-console portable (source_type, source_number) slot keys, apply_to_session algorithm, and additive 0154 migration creating both tables with zero ALTER TABLE on existing data.**

## Performance

- **Duration:** 2m 9s
- **Started:** 2026-05-13T19:14:07Z
- **Completed:** 2026-05-13T19:16:16Z
- **Tasks:** 2
- **Files modified:** 1 modified (`planner/models.py`) + 1 created (`planner/migrations/0154_multitrack_template.py`)

## Accomplishments

- `MultitrackTemplate` model: owner-scoped via `created_by` FK (D-05 — no `project` FK), `unique_together=[('created_by', 'name')]`, `mtt_owner_idx` index, name max_length=200.
- `MultitrackTemplateSlot` model: cross-console portable via `(source_type, source_number)` CharField pair (D-02), `unique_together=[('template', 'position')]`, `mtt_slot_pos_idx` composite index, FK CASCADE to template with `related_name='slots'`.
- `MultitrackTemplate.apply_to_session(session)` instance method: dispatches via `_source_model_for(source_type)` + per-source-type channel-number field map (`input→input_ch`, `aux→aux_number`, `matrix→matrix_number`, `stereo→stereo_type`); manual slots always materialise; unresolvable slots collected for the banner; `bulk_create` writes new tracks in a single INSERT.
- `_summarise_skipped_slots(skipped)` module-level helper: groups by source_type, formats `"matrix 9, 10, 11 not present on this console"`; returns empty string when input is empty.
- Migration `0154_multitrack_template.py`: 2 `CreateModel` ops + 2 `AddIndex` + 2 `AlterUniqueTogether` — all targeting the newly-created tables. Zero `AlterField`/`RemoveField`/`RenameField`/`RunSQL` on existing tables.
- Migration applied cleanly against local SQLite; `makemigrations --dry-run` reports no further changes; `python manage.py check planner` exits 0.

## Task Commits

Each task was committed atomically:

1. **Task 1: Append MultitrackTemplate + MultitrackTemplateSlot + apply_to_session + _summarise_skipped_slots to planner/models.py** — `87638fb` (feat)
2. **Task 2: Generate additive migration 0154_multitrack_template.py via makemigrations** — `a914b51` (feat)

## Files Created/Modified

- `planner/models.py` — Appended 169 lines after `MultitrackTrack` class (line 1119) and before the stray `# planner/models.py` / `from django.db import models` re-import block (line 1122). Added two model classes, one instance method, and one module-level helper.
- `planner/migrations/0154_multitrack_template.py` — New additive migration. Depends on `planner.0153_console_color_and_consoleimport` and `settings.AUTH_USER_MODEL`.

## Decisions Made

- **Reused choice constants verbatim** (`MultitrackSession.TARGET_DAW_CHOICES`, `FEED_SOURCE_CHOICES`, `TRACK_ORDER_MODE_CHOICES`, `MultitrackTrack.SOURCE_TYPE_CHOICES`) instead of redefining — single source of truth, matches plan instruction.
- **Placed `apply_to_session` as an instance method on `MultitrackTemplate`** (RESEARCH Assumption A7) rather than a free-standing function. Clean test surface; downstream callers do `template.apply_to_session(session)` rather than `apply_template_to_session(template, session)`.
- **Guarded the `bulk_create` call with `if new_tracks:`**. The plan's example pseudocode unconditionally calls `MultitrackTrack.objects.bulk_create(new_tracks)`. Calling `bulk_create([])` works in Django but emits an unnecessary log statement on a zero-slot template (D-13 metadata-only path). Guarding is cosmetic but explicit. No semantic difference vs the plan.
- **Generated migration via `makemigrations`** per the plan's `<action>` block (canonical autodetector form), rather than hand-writing the file. The autodetector emitted `AddIndex` + `AlterUniqueTogether` as separate ops (instead of inlined in `CreateModel.options`), but both target the **newly-created** tables — they do not violate the "zero ALTER TABLE on existing tables" rule. Verified by the acceptance grep: `grep -E "AlterField|RemoveField|RenameField|RunSQL"` returns nothing.

## Deviations from Plan

None — plan executed exactly as written. No Rule 1/2/3 auto-fixes were needed.

The two cosmetic choices noted under "Decisions Made" (guarding `bulk_create` with `if new_tracks:`, accepting the autodetector's separate `AddIndex`/`AlterUniqueTogether` ops) are both inside the plan's stated tolerance — the plan's `<action>` for Task 2 explicitly says *"Recommend running `python manage.py makemigrations planner` and committing the generated file rather than hand-writing"*.

## Issues Encountered

- `python` symlink not on `$PATH` (only `python3` and `./venv/bin/python` resolve). Used `./venv/bin/python manage.py ...` for all Django commands. No semantic impact — the venv is the project's authoritative interpreter (Procfile uses it on Railway too).
- Django reload warning surfaced on every `manage.py` invocation (`Model 'planner.audiochecklist' was already registered`). Pre-existing; not introduced by this plan. Out of scope per executor scope-boundary rule — logged here for visibility, no fix.

## Verification Block Results

| Gate | Command | Result |
|------|---------|--------|
| `check` | `./venv/bin/python manage.py check planner` | PASS — System check identified no issues (0 silenced) |
| `dry-run` | `./venv/bin/python manage.py makemigrations planner --dry-run` | PASS — No changes detected in app 'planner' |
| `migrate` | `./venv/bin/python manage.py migrate planner` | PASS — Applying planner.0154_multitrack_template... OK |
| `_meta.unique_together` | `MultitrackTemplate._meta.unique_together, MultitrackTemplateSlot._meta.unique_together` | `(('created_by', 'name'),) (('template', 'position'),)` ✓ |
| `apply_to_session` callable | `callable(MultitrackTemplate().apply_to_session)` | `True` ✓ |
| `_summarise_skipped_slots` grouped | `_summarise_skipped_slots([('matrix', '9'), ('matrix', '10')])` | `"matrix 9, 10 not present on this console"` ✓ |
| `_summarise_skipped_slots` empty | `_summarise_skipped_slots([])` | `''` ✓ |

## Threat Register Compliance

Mitigations declared in the plan's `<threat_model>` and how they landed:

- **T-03-01 Tampering (mitigate):** `unique_together = [('created_by', 'name')]` enforced at both model + migration level. DB-level guarantee against duplicate template names per owner. ✓
- **T-03-02 Information Disclosure (mitigate):** `created_by` FK is the sole ownership anchor; `mtt_owner_idx` index makes `created_by=request.user` filters cheap. No `project` FK in `MultitrackTemplate`. ✓
- **T-03-04 Repudiation (mitigate):** `created_by` is non-nullable with `on_delete=CASCADE`. `created_at` and `updated_at` are auto-managed. Every template is auditable. ✓
- **T-03-03 / T-03-05:** accepted at the model layer — apply downstream in Plans 03/04/05.

## Next Phase Readiness

- Schema is ready. Plans 02–05 of phase 03 can now consume `MultitrackTemplate` + `MultitrackTemplateSlot` + `apply_to_session` + `_summarise_skipped_slots`.
- Plan 03-02 (admin registration on `showstack_admin_site` + `admin_ordering.py` entry) is unblocked.
- Plan 03-03 (view endpoints: save/rename/delete) is unblocked — both the parent model's `unique_together` and the IntegrityError-as-409 contract are in place.
- Plan 03-04 (form integration in `MultitrackSessionForm`) is unblocked — `MultitrackTemplate.objects.filter(created_by=request.user)` is an indexed query.
- Plan 03-05 (apply path in `multitrack_create_view`) is unblocked — `apply_to_session` returns `(mapped, skipped, summary)` exactly matching the plan's caller signature.

## Self-Check: PASSED

Verified post-write:

- `planner/models.py` exists and contains `class MultitrackTemplate(models.Model):` at line 1122, `class MultitrackTemplateSlot(models.Model):` at line 1228, `def apply_to_session(self, session):` at line 1160, `def _summarise_skipped_slots(skipped):` at line 1267. ✓
- `planner/migrations/0154_multitrack_template.py` exists. ✓
- Commit `87638fb` exists in `git log --oneline -5`. ✓
- Commit `a914b51` exists in `git log --oneline -5`. ✓

---
*Phase: 03-multitrack-templates*
*Completed: 2026-05-13*
