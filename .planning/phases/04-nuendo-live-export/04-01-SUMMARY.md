---
phase: 04-nuendo-live-export
plan: 01
subsystem: infra

tags: [lxml, dependency-pin, django-model-property, color-resolution, yamaha-palette, nuendo-live]

# Dependency graph
requires:
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: YAMAHA_TO_HEX palette table + MultitrackTrack.resolved_source / resolved_color / resolved_dante_number @property pattern
  - phase: 02-console-csv-import
    provides: channel-level color CharField on ConsoleInput / ConsoleAuxOutput / ConsoleMatrixOutput / ConsoleStereoOutput (Phase 2 D-07)
provides:
  - lxml~=5.3.0 declared in requirements.txt (Railway pip-installs on next deploy)
  - MultitrackTrack.resolved_yamaha_name @property (D-04 / D-05 resolution chain)
  - _HEX_TO_YAMAHA_NAME module-level reverse-lookup map (8 entries, 'Off' and 'White' intentionally absent)
affects: [04-02, 04-03, 04-04, 04-05, 04-06, 04-07, nuendo-live-exporter, farb-mapping]

# Tech tracking
tech-stack:
  added: [lxml~=5.3.0]
  patterns:
    - "Reverse-lookup constant built once at module load from sibling exporter's palette table"
    - "Three-step color resolution (override → source.color → None) returns palette-name not hex, keeping Phase 1 byte-stable Reaper exporter untouched"

key-files:
  created: []
  modified:
    - "requirements.txt — appended lxml~=5.3.0"
    - "planner/models.py — _HEX_TO_YAMAHA_NAME import + reverse-map; MultitrackTrack.resolved_yamaha_name @property; stale comment cleanup at TARGET_DAW_CHOICES"

key-decisions:
  - "lxml pinned at ~=5.3.0 (compatible-release; admits 5.3.x patch, blocks 5.4/6.x) — 5.3.x has broader manylinux wheel coverage than 6.x on Railway base image"
  - "Reverse-lookup dict built once at module load via dict-comprehension over YAMAHA_TO_HEX, filtering out None hex values ('Off' and 'White') — those palette names are unreachable through the override path by design (D-04)"
  - "resolved_yamaha_name returns palette name (not hex) so the Nuendo exporter can call YAMAHA_TO_FARB[name] cleanly; resolved_color (hex) is intentionally NOT touched so the Phase 1 Reaper exporter's byte-stable output contract holds"

patterns-established:
  - "Module-level reverse-lookup map pattern: `from .utils.<exporter> import <TABLE> as _ALIAS` + dict-comprehension into `_REVERSE = {v.lower(): k for k,v in _ALIAS.items() if v is not None}`. Reusable for any future exporter that needs hex→palette-name resolution."
  - "Color resolution order on MultitrackTrack: override (palette-match-only) → resolved_source.color (Phase 2 D-07 channel field) → None. Non-palette hex overrides return None → 'omit color' signal to exporter (D-05)."

requirements-completed: [NLP-04, NLP-05]

# Metrics
duration: 3min
completed: 2026-05-13
---

# Phase 4 Plan 01: Nuendo Live Prerequisites Summary

**Pinned lxml~=5.3.0 in requirements.txt and added `MultitrackTrack.resolved_yamaha_name` @property (override → source.color → None) without disturbing Phase 1's byte-stable Reaper exporter contract.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-13T23:36:53Z
- **Completed:** 2026-05-13T23:39:19Z
- **Tasks:** 2 / 2
- **Files modified:** 2

## Accomplishments

- `requirements.txt` now declares `lxml~=5.3.0` — Railway's automatic `pip install -r requirements.txt` (inside the `railway.json` `startCommand`) will resolve a pre-built manylinux wheel on the next deploy. No Procfile or railway.json edit required.
- `MultitrackTrack.resolved_yamaha_name` @property added, returning the Yamaha palette name (e.g. `'Red'`, `'Blue'`) for downstream Nuendo Farb mapping. Resolution order matches Phase 4 CONTEXT D-04 / D-05 exactly: color_override hex → palette-name match (non-palette hex returns `None`); else `resolved_source.color` (or `None` if source is `'Off'` / missing).
- Module-level `_HEX_TO_YAMAHA_NAME` reverse-lookup built once via dict-comprehension over `YAMAHA_TO_HEX`, filtering out `'Off'` and `'White'` (both have `None` hex values). Result: exactly 8 entries, all lower-case keys for case-insensitive lookup.
- Stale comment `# disabled in UI until Phase 4 ships` at `planner/models.py:980` updated to `# both options available; new sessions default to 'reaper'` (RESEARCH Pitfall 6 cleanup).
- Phase 1's `planner/tests/test_reaper_export` continues to pass 42/42 — the byte-stable Reaper contract is intact.
- `python manage.py makemigrations planner --dry-run` reports `No changes detected in app 'planner'`, confirming zero schema drift (CLAUDE.md §"additive migrations only" naturally satisfied).

## Task Commits

Each task was committed atomically:

1. **Task 1: Pin lxml in requirements.txt** — `be3f151` (chore)
2. **Task 2: Add resolved_yamaha_name @property on MultitrackTrack** — `8630fda` (feat)

_Note: Task 2 bundled two model edits (reverse-map + @property) plus the D-12 comment cleanup into one commit because they form a single logical unit per the plan's `<action>` block. No TDD gates apply (plan type=`execute`, not `tdd`)._

## Files Created/Modified

- `requirements.txt` — appended `lxml~=5.3.0` (one new line, file ends with `\n`).
- `planner/models.py` — two edits:
  1. After `YAMAHA_COLOR_CHOICES` (around line 770): added `from .utils.reaper_export import YAMAHA_TO_HEX as _YAMAHA_TO_HEX` and the `_HEX_TO_YAMAHA_NAME` dict-comprehension.
  2. Inside `MultitrackTrack` (after `resolved_dante_number`, before `def __str__`): added the `resolved_yamaha_name` @property.
  3. At line 980: refreshed the `TARGET_DAW_CHOICES` comment for `'nuendo_live'`.

## Decisions Made

- **lxml version pin:** chose `~=5.3.0` per RESEARCH §"Standard Stack" — admits 5.3.x patch releases (security fixes flow in), blocks 5.4/6.x (broader manylinux wheel coverage on older Linux base images; pre-built wheels for Python 3.9–3.14 → no compilation on Railway).
- **Reverse-map placement:** inserted next to `YAMAHA_COLOR_CHOICES` (line 770) rather than at the top of `models.py` near `from django.db import models`. Rationale: keeps the constant adjacent to the palette-name definition it semantically derives from, easier to maintain when the palette grows.
- **Import alias `_YAMAHA_TO_HEX`:** imported with a leading-underscore alias to keep the public `YAMAHA_TO_HEX` source-of-truth strictly inside `planner/utils/reaper_export.py`. Nothing else in `models.py` will inadvertently re-export the table.

## Deviations from Plan

None — plan executed exactly as written. All `<verify>` automated checks and all `<acceptance_criteria>` items pass.

## Issues Encountered

- Local Python interpreter (`python`) wasn't on PATH; the project's `venv/bin/python` was used for `manage.py makemigrations --dry-run` and the in-process module-load assertion. This is a developer-environment quirk, not a plan deviation.

## User Setup Required

None — Railway will install `lxml~=5.3.0` automatically on the next push to `main` via the existing `startCommand` in `railway.json`. No environment variables, secrets, or external service configuration required.

## Threat Flags

None — Plan 04-01's surface (one dependency line + one read-only property reading existing in-memory data via dict `.get(...)` with `.lower()` normalization) is fully contained by the plan's threat register entries T-04-01 / T-04-02 / T-04-03. No new network endpoints, no new auth paths, no schema changes.

## Self-Check: PASSED

Verified before STATE.md update:
- `requirements.txt` contains `lxml~=5.3.0` (FOUND; `grep -c '^lxml~=5\.3\.' requirements.txt` returned `1`)
- `planner/models.py` contains `def resolved_yamaha_name` (FOUND; `grep -c` returned `1`)
- `planner/models.py` contains 2× `_HEX_TO_YAMAHA_NAME` references (FOUND; definition + property body)
- `planner/models.py` contains 1× `from .utils.reaper_export import YAMAHA_TO_HEX` (FOUND)
- `planner/models.py` `@property` count went 36 → 37 (FOUND; +1 exactly)
- `planner/models.py` retains 1× `def resolved_color` (FOUND; unchanged)
- Stale comment `disabled in UI until Phase 4` count went 1 → 0 (FOUND)
- Commit `be3f151` exists (FOUND in `git log --oneline`)
- Commit `8630fda` exists (FOUND in `git log --oneline`)
- `python manage.py makemigrations planner --dry-run` reports `No changes detected in app 'planner'` (FOUND)
- `planner.tests.test_reaper_export`: 42/42 OK (FOUND; Phase 1 byte-stable contract intact)
- Python import test prints `OK` and `_HEX_TO_YAMAHA_NAME` matches the expected 8-entry dict exactly (FOUND)

## Next Phase Readiness

- **Wave 1 prerequisites ready.** Plan 04-02 (the pure exporter `build_nlpr(session) → bytes`) can now `from lxml import etree` and `from planner.models import MultitrackTrack` and call `track.resolved_yamaha_name` directly.
- **Charlie-owned blocker still outstanding:** the bundled `planner/data/multitrack/nuendo_live_3_template.nlpr` fixture (per CONTEXT D-02, generated on Windows + Nuendo Live 3) is required before any end-to-end view test or HUMAN-UAT round-trip. Wave 1 unit tests can stand on the Python-generated fake template per RESEARCH §"Test fixture strategy".
- **Railway deploy gate:** the lxml install only kicks in on the next push to `main` triggering the Railway redeploy. If Charlie pushes the Phase 4 work in a single batch (recommended), the `lxml` install lines up with the exporter's first runtime need — zero risk.

---
*Phase: 04-nuendo-live-export*
*Completed: 2026-05-13*
