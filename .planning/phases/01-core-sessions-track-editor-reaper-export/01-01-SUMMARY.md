---
phase: 01-core-sessions-track-editor-reaper-export
plan: 01
subsystem: database
tags: [django, models, signals, admin, multitrack, post-delete, discriminator-pattern]

# Dependency graph
requires:
  - phase: bootstrap
    provides: Console / ConsoleInput / ConsoleAuxOutput / ConsoleMatrixOutput / ConsoleStereoOutput models, BaseEquipmentAdmin, showstack_admin_site, admin_ordering monkey-patch, planner.signals auto-registration via apps.py:13 ready()
provides:
  - MultitrackSession model (project + console FK, target_daw / feed_source / track_order_mode choices, recorder_capacity, notes, audit timestamps, unique_together=(project,name))
  - MultitrackTrack model (discriminator source_type/source_id, label/color overrides, enabled flag, track_number, notes; resolved_source / resolved_label / resolved_color / resolved_dante_number @property helpers)
  - Module-level _source_model_for(source_type) dispatch helper in planner/models.py for downstream signals/views
  - Four post_delete receivers in planner/signals.py converting orphan tracks to manual on channel deletion (D-04 contract)
  - MultitrackSessionAdmin on showstack_admin_site that bounces /admin/planner/multitracksession/ to /audiopatch/multitrack/ (URL name 'planner:multitrack_dashboard' — owned by Plan 03)
  - admin_ordering.py order_map entry 'multitracksession': 12.7 (sidebar slot between Communications and Show Mic Tracker)
  - Migration 0152_multitrack_session_track.py — additive only, two CreateModel ops, zero ALTER on existing channel models
affects: [01-02, 01-03, 01-04, 01-05, 01-06]

# Tech tracking
tech-stack:
  added: []  # All from existing Django 5.x stack — no new dependencies
  patterns:
    - "Discriminator-based source reference (source_type, source_id) — no FK constraint to channel models, beta-tester data safe"
    - "Module-level dispatch helper (_source_model_for) so signals can resolve the source class without import-cycle risk"
    - "post_delete orphan conversion with snapshot label/color preservation (engineer never silently loses a track row)"
    - "BaseEquipmentAdmin subclass that bounces changelist_view to a custom UI URL (mirrors CommConfigAdmin precedent at admin.py:5932)"

key-files:
  created:
    - "planner/migrations/0152_multitrack_session_track.py"
    - ".planning/phases/01-core-sessions-track-editor-reaper-export/01-01-SUMMARY.md"
  modified:
    - "planner/models.py (appended MultitrackSession + MultitrackTrack + _source_model_for helper, +162 lines)"
    - "planner/signals.py (added post_delete imports + _convert_orphans_to_manual + four receivers, +62 lines)"
    - "planner/admin.py (added MultitrackSessionAdmin class + showstack_admin_site registration, +47 lines)"
    - "planner/admin_ordering.py ('multitracksession': 12.7 entry, +5/-1 lines)"

key-decisions:
  - "ConsoleInput.dante_number is CharField (not IntegerField) — resolved_dante_number coerces via int() with try/except so all four source types return a normalised int (or None)"
  - "ConsoleInput has no `name` field; resolved_label falls back source -> input_ch -> 'Input {dante_number}' -> '(untitled)'"
  - "MultitrackTrackAdmin not registered in Phase 1 (CONTEXT D-09) — tracks are exclusively edited through the custom editor page that lands in Plan 03/04"
  - "Skipped local `python manage.py migrate` end-to-end run because legacy migration 0112_fix_showday_date_constraint contains Postgres-specific raw SQL that fails on SQLite. Pre-existing in the repo, out of scope for this task. Verified the new migration in isolation against in-memory SQLite (CreateModel ops + index applied cleanly) and ran an end-to-end orphan-conversion smoke test with MIGRATION_MODULES disabled — all 4 channel deletes correctly converted MultitrackTrack rows to source_type='manual', source_id=NULL, with snapshot label preserved."

patterns-established:
  - "Discriminator pattern for cross-table references when CASCADE-on-delete would be unsafe"
  - "Resolved-* @property helpers for late-bound, override-aware label/color/identifier lookup"
  - "Local-import inside signal helper to break the signals -> models -> apps -> signals cycle"
  - "Snapshot-on-delete: capture human-meaningful label BEFORE delete fires the signal (instance still hydrated inside post_delete; row gone after the receiver returns)"
  - "Admin class redirect-to-custom-UI via changelist_view returning redirect(planner:url_name) — matches CommConfigAdmin"

requirements-completed:
  - MTS-01
  - MTS-02
  - MTS-04
  - MTS-05
  - TRK-01
  - TRK-02
  - TRK-03
  - TRK-04
  - TRK-08
  - TRK-10

# Metrics
duration: 8min
completed: 2026-05-10
---

# Phase 1 Plan 01: Multitrack Session + Track Models Summary

**MultitrackSession + MultitrackTrack models with discriminator-based channel sourcing, four post_delete signals that convert orphan tracks to manual on channel deletion, and admin sidebar bounce to the custom editor at /audiopatch/multitrack/.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-10T22:52:25Z
- **Completed:** 2026-05-10T23:00:25Z
- **Tasks:** 4
- **Files modified:** 5 (1 created migration + 4 edited source files)

## Accomplishments

- Two new tables — `planner_multitracksession` and `planner_multitracktrack` — created via a purely additive migration. Zero ALTER against the four beta-tester-loaded channel models.
- Discriminator pattern (`source_type`, `source_id`) on `MultitrackTrack` with a DB index on the pair for fast orphan-conversion lookups (`mts_track_src_idx`).
- Four `@property` resolver helpers (`resolved_source` / `resolved_label` / `resolved_color` / `resolved_dante_number`) that downstream forms / views / Reaper exporter will lean on.
- Four `post_delete` receivers that convert orphan tracks to `source_type='manual'`, `source_id=NULL` with the channel's last-known label/color preserved as overrides — engineer never silently loses a track when a channel is deleted.
- `MultitrackSessionAdmin` registered on `showstack_admin_site` (NEVER `admin.site`), with three permission gates blocking the `Viewer` group and a redirect to the future `/audiopatch/multitrack/` UI.
- `admin_ordering.py` entry placing the new section at sidebar slot 12.7 (between Communications and Show Mic Tracker).

## Task Commits

Each task was committed atomically:

1. **Task 1: Append MultitrackSession + MultitrackTrack models to planner/models.py** — `f9cb2dd` (feat)
2. **Task 2: Append four post_delete receivers + helper to planner/signals.py** — `1ce63ee` (feat)
3. **Task 3: Add MultitrackSessionAdmin to planner/admin.py + admin_ordering entry** — `c158941` (feat)
4. **Task 4: Generate the additive migration for the two new tables** — `0f6d327` (feat)

_Plan-metadata commit (this SUMMARY) is created next by the executor's git_commit_metadata step._

## Files Created/Modified

- `planner/models.py` — appended `MultitrackSession`, module-level `_source_model_for(source_type)` dispatch helper, and `MultitrackTrack` (with four `@property` resolver helpers + DB index `mts_track_src_idx` on `(source_type, source_id)`).
- `planner/signals.py` — added `post_delete` import, four sender models to the import block, helper `_convert_orphans_to_manual(source_type, source_id, snapshot_label, snapshot_color='')`, and four `@receiver(post_delete, sender=...)` functions (one per channel type). Existing `ensure_user_profile` untouched.
- `planner/admin.py` — added `from .models import MultitrackSession, MultitrackTrack`, `class MultitrackSessionAdmin(BaseEquipmentAdmin):` with `changelist_view` redirect + three role-gated permission methods, and `showstack_admin_site.register(MultitrackSession, MultitrackSessionAdmin)` immediately after the `Console` registration.
- `planner/admin_ordering.py` — inserted `'multitracksession': 12.7` into `order_map` between the Communications block (12-15) and the Show Mic Tracker block (16-20).
- `planner/migrations/0152_multitrack_session_track.py` — auto-generated by `makemigrations`, two `CreateModel` ops only (`MultitrackSession` + `MultitrackTrack`), no operations against any of the four existing channel models.

## Field Set Reference (downstream plans may quote)

### MultitrackSession

| Field | Type | Notes |
|---|---|---|
| project | FK -> Project, CASCADE | related_name='multitrack_sessions' |
| console | FK -> Console, CASCADE | D-13 spec correction (NOT Device) |
| name | CharField(100) | unique per project (see Meta.unique_together) |
| target_daw | CharField(20) choices=[reaper, nuendo_live] | default='reaper'; nuendo_live disabled in UI until Phase 4 |
| feed_source | CharField(20) choices=[console_dante, rio_direct, custom] | default='console_dante' |
| track_order_mode | CharField(10) choices=[console, dante, custom] | default='console' |
| recorder_capacity | PositiveIntegerField | nullable; backs TRK-10 capacity warning |
| notes | TextField | blank=True, default='' |
| created_at / updated_at | DateTimeField auto_now_add / auto_now | audit |

`Meta`: `verbose_name='Multitrack Session'`, `ordering=['-updated_at','name']`, `unique_together=[('project','name')]` — backs MTS-02 rename validation.

### MultitrackTrack

| Field | Type | Notes |
|---|---|---|
| session | FK -> MultitrackSession, CASCADE | related_name='tracks' |
| track_number | PositiveIntegerField | default=1 |
| source_type | CharField(10) choices=[input, aux, matrix, stereo, manual] | discriminator (D-01) |
| source_id | PositiveIntegerField | nullable for manual / orphan-converted |
| label_override | CharField(100) | blank=True, default='' |
| color_override | CharField(7) | hex; blank=True, default='' |
| enabled | BooleanField | default=True |
| notes | CharField(200) | blank=True, default='' |

`Meta`: `verbose_name='Multitrack Track'`, `ordering=['track_number']`, `indexes=[Index(fields=['source_type','source_id'], name='mts_track_src_idx')]`.

`@property` helpers:
- `resolved_source` — looks up via `_source_model_for(source_type).objects.filter(pk=source_id).first()`; returns the channel instance or `None` (manual / orphan / missing).
- `resolved_label` — `label_override` or, depending on source_type, `src.source` / `src.input_ch` / `src.name` / `f'Input {dante}'` / `f'Aux {aux_number}'` / `f'Matrix {matrix_number}'` / `src.get_stereo_type_display()` / `'(untitled)'`.
- `resolved_color` — `color_override or None` (Phase 5 may extend with `default_record_color`).
- `resolved_dante_number` — coerces both CharField (ConsoleInput) and IntegerField (the other three) to `int` via try/except; returns `None` if absent or unparseable.

## Migration Filename

`planner/migrations/0152_multitrack_session_track.py` (depends on `0151_discovereddevice_clock_role_and_more`).

## Admin Bounce Target

`changelist_view` returns `redirect('planner:multitrack_dashboard')`. The URL name is owned by Plan 03 (Wave 2). If Plan 03 changes the name, this admin's redirect breaks — keep them in sync.

## Signal Receivers — Sender Models

| Receiver | Sender | Snapshot label fallback chain |
|---|---|---|
| `consoleinput_to_manual` | `ConsoleInput` | `source` -> `input_ch` -> `'Input {dante_number}'` -> `'(deleted input)'` |
| `consoleauxoutput_to_manual` | `ConsoleAuxOutput` | `name` -> `'Aux {aux_number}'` -> `'(deleted aux)'` |
| `consolematrixoutput_to_manual` | `ConsoleMatrixOutput` | `name` -> `'Matrix {matrix_number}'` -> `'(deleted matrix)'` |
| `consolestereooutput_to_manual` | `ConsoleStereoOutput` | `name` -> `get_stereo_type_display()` -> `'(deleted stereo)'` |

All four route through the shared `_convert_orphans_to_manual(source_type, source_id, snapshot_label)` helper which `track.save(update_fields=[...])` per-row to preserve any existing engineer overrides.

## Decisions Made

- **`ConsoleInput.dante_number` is `CharField`, not `IntegerField`.** The other three channel models use `IntegerField`. `resolved_dante_number` coerces both via `int()` with `try/except` so callers always see `int | None`.
- **`ConsoleInput` has no `name` field.** `resolved_label` for inputs falls back through the engineer-typed `source` (channel name field) -> `input_ch` -> `'Input {dante_number}'` -> `'(untitled)'`. This matched the `__str__` precedent in the existing model (planner/models.py:836-842).
- **No `MultitrackTrackAdmin` registered.** Per CONTEXT D-09, tracks are exclusively edited through the custom editor page (Plan 03/04). Adding an admin would invite the engineer to bypass capacity/orphan-aware UI.
- **Did not run full `python manage.py migrate planner` end-to-end against the SQLite dev DB.** The legacy migration `0112_fix_showday_date_constraint` (unrelated to this plan, pre-existing in the repo) uses Postgres-only raw SQL that errors on SQLite (`near "CONSTRAINT": syntax error`). This is **out of scope** for Plan 01-01 per the executor SCOPE BOUNDARY rule. Production runs on Postgres so the legacy migration is fine there. I verified the new migration's correctness in two ways:
  1. Dry-run check: `python manage.py makemigrations --dry-run --check planner` exits 0.
  2. Isolated apply: with an in-memory SQLite + stub `planner_project` / `planner_console` tables, the new migration's two `CreateModel` ops create both tables and the `mts_track_src_idx` index cleanly.
  3. End-to-end smoke test: with `MIGRATION_MODULES` disabled (direct schema sync), all four channel-delete -> orphan-conversion paths verified — `t.source_type` becomes `'manual'`, `t.source_id` becomes `NULL`, and `t.label_override` snapshots the channel's name.

## Deviations from Plan

None — plan executed exactly as written. The four `<read_first>` reads / verifications all passed first try. The smoke-test pivot (in-memory + isolated migration application) is a verification choice, not a code change.

## Issues Encountered

- Pre-existing legacy migration `0112_fix_showday_date_constraint` fails on SQLite (Postgres raw SQL with `CONSTRAINT` clause unsupported by SQLite). Documented in Decisions; out of scope. Logged for future cleanup if the team wants a SQLite-compatible local-dev path.
- Worktree branch was created from an older base (`e7561dc`); hard-reset to the correct base `708ca0d` per the worktree_branch_check protocol before starting work. Safe — fresh worktree, no user changes lost.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All Plan 01-02..01-06 dependencies provided. Subsequent plans can `from planner.models import MultitrackSession, MultitrackTrack, _source_model_for`.
- The admin bounce target `planner:multitrack_dashboard` is referenced but not yet defined — Plan 03 (Wave 2) is responsible for the URL registration. Until Plan 03 lands, the admin link will 404 (acceptable: Plan 01 ships only the data layer, no UI surface).
- Production deploy of this plan's migration happens via the Railway `startCommand` (`migrate`) on the next push to main, after the rest of Phase 1 lands.

## Self-Check

Verified all claims in this SUMMARY against the worktree state.

**Created files:**
- FOUND: `planner/migrations/0152_multitrack_session_track.py`
- FOUND: `.planning/phases/01-core-sessions-track-editor-reaper-export/01-01-SUMMARY.md`

**Modified files (git diff vs plan base):**
- FOUND: `planner/models.py` (+162 / -5)
- FOUND: `planner/signals.py` (+62 / -3)
- FOUND: `planner/admin.py` (+47 / 0)
- FOUND: `planner/admin_ordering.py` (+5 / -1)

**Commits exist:**
- FOUND: `f9cb2dd` Task 1
- FOUND: `1ce63ee` Task 2
- FOUND: `c158941` Task 3
- FOUND: `0f6d327` Task 4

## Self-Check: PASSED

---

*Phase: 01-core-sessions-track-editor-reaper-export*
*Completed: 2026-05-10*
