---
phase: 03-multitrack-templates
plan: 02
subsystem: admin
tags: [django, admin, multitrack, templates, showstack-admin-site]

# Dependency graph
requires:
  - phase: 03-multitrack-templates
    provides: "MultitrackTemplate + MultitrackTemplateSlot models from plan 03-01 (planner/models.py:1122 / :1228)"
provides:
  - "MultitrackTemplateSlotInline: read-only TabularInline (every field readonly, can_delete=False, has_add_permission=False) — engineers cannot mutate slot lists from Django admin"
  - "MultitrackTemplateAdmin: BaseEquipmentAdmin subclass with slot_count list_display + three viewer-block permission methods"
  - "MultitrackTemplate registered on showstack_admin_site (NOT default admin.site); MultitrackTemplateSlot intentionally NOT registered separately"
  - "admin_ordering.py order_map entry 'multitracktemplate': 51 between multitracksession (50) and consoleimport (bumped 51 -> 52)"
affects: [03-03 view endpoints (save/rename/delete), 03-04 form integration, 03-05 dashboard + new-session UI]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Read-only inline pattern: every field in readonly_fields + can_delete=False + has_add_permission returning False — mirrors ConsoleImportAdmin (admin.py:5943-5976)"
    - "Viewer-group permission gate verbatim copy: three permission methods (add/change/delete) each short-circuit on is_superuser then block on Viewer group membership"
    - "Custom admin-site registration: showstack_admin_site.register(...) — never admin.site.register(...) per CLAUDE.md non-negotiable"

key-files:
  created: []
  modified:
    - "planner/admin.py (added MultitrackTemplate/MultitrackTemplateSlot import; appended MultitrackTemplateSlotInline + MultitrackTemplateAdmin classes; added one register call between MultitrackSession and ConsoleImport)"
    - "planner/admin_ordering.py (inserted 'multitracktemplate': 51 in order_map; bumped 'consoleimport' from 51 to 52)"

key-decisions:
  - "Inserted the new admin class between ConsoleImportAdmin (line 5976) and the # ==================== REGISTER ALL MODELS ==================== separator — matches the plan's splice point exactly; admin class banner comment includes file-reference citations (D-05, CONTEXT specifics line 195, ConsoleImportAdmin parallel)"
  - "Slot inline uses tuples (not lists) for fields/readonly_fields to match the plan's exact code; Django accepts either, but tuples mirror the spelled-out plan verbatim and avoid drift"
  - "MultitrackTemplateSlot deliberately NOT registered on showstack_admin_site — lives only as the inline (mirrors Phase 1's MultitrackTrack treatment); confirmed at runtime via `MultitrackTemplateSlot in showstack_admin_site._registry == False`"
  - "Register call placed between MultitrackSession and ConsoleImport in the register block to mirror the sidebar order (50 -> 51 -> 52) — keeps source visually consistent with order_map intent"

patterns-established:
  - "Read-only inline + viewer-blocked admin: copy-paste-friendly recipe for any future 'audit history' or 'engineer-managed-elsewhere' model"
  - "order_map insertion: when sliding a new key in mid-range, bump trailing keys in the same group rather than re-numbering globally"

requirements-completed: [TPL-01, TPL-03]

# Metrics
duration: 1m 57s
completed: 2026-05-13
---

# Phase 03 Plan 02: Multitrack Template Admin Registration Summary

**MultitrackTemplate registered on showstack_admin_site with read-only slot inline + viewer-blocked add/change/delete; admin_ordering.py order_map updated to slot the new model between MultitrackSession and ConsoleImport.**

## Performance

- **Duration:** 1m 57s
- **Started:** 2026-05-13T19:20:40Z
- **Completed:** 2026-05-13T19:22:37Z
- **Tasks:** 2
- **Files modified:** 2 (`planner/admin.py`, `planner/admin_ordering.py`)

## Accomplishments

- `MultitrackTemplateSlotInline` defined as a fully read-only `admin.TabularInline` (T-03-07 mitigation): every field in `readonly_fields`, `can_delete=False`, `has_add_permission` returns `False`. Engineers cannot add, modify, or remove slot rows from Django admin.
- `MultitrackTemplateAdmin` defined as a `BaseEquipmentAdmin` subclass with `slot_count` list_display callable and the three viewer-block permission methods copied verbatim from `MultitrackSessionAdmin` (T-03-06 mitigation).
- `showstack_admin_site.register(MultitrackTemplate, MultitrackTemplateAdmin)` inserted in the register block between `MultitrackSession` and `ConsoleImport` — CLAUDE.md non-negotiable honored (NOT `admin.site`). `MultitrackTemplateSlot` intentionally NOT registered separately (T-03-10 mitigation).
- `planner/admin_ordering.py` `order_map` updated: `'multitracktemplate': 51` inserted between `multitracksession` (50) and `consoleimport` (bumped 51 -> 52). Sidebar grouping preserved.
- Runtime verification: `MultitrackTemplate in showstack_admin_site._registry == True`; `MultitrackTemplateSlot in showstack_admin_site._registry == False`; three multitrack-group models appear contiguously (`MultitrackSession`, `MultitrackTemplate`, `ConsoleImport`).
- `python manage.py check planner` exits 0.

## Task Commits

Each task was committed atomically:

1. **Task 1: Append MultitrackTemplateSlotInline + MultitrackTemplateAdmin classes and register on showstack_admin_site** — `0ab665d` (feat)
2. **Task 2: Add 'multitracktemplate' to admin_ordering.py order_map and bump consoleimport from 51 to 52** — `ee4aff5` (feat)

## Files Created/Modified

- `planner/admin.py` — Added `from .models import MultitrackTemplate, MultitrackTemplateSlot` (line 40). Inserted `MultitrackTemplateSlotInline` (~line 5990) and `MultitrackTemplateAdmin` (~line 6007) classes between `ConsoleImportAdmin` and the register block. Added one `showstack_admin_site.register(MultitrackTemplate, MultitrackTemplateAdmin)` call between the `MultitrackSession` and `ConsoleImport` register lines (~line 6051). Net diff: +68 lines, -0.
- `planner/admin_ordering.py` — Inserted `'multitracktemplate': 51,        # NEW — Phase 3` and changed `'consoleimport': 51,` -> `'consoleimport': 52,             # bumped from 51 to keep grouping order` in the order_map dict (lines 162-166). Net diff: +2 lines, -1.

## Decisions Made

- **Imports placed on a fresh line** (`from .models import MultitrackTemplate, MultitrackTemplateSlot` at line 40) rather than appending to the existing `MultitrackSession, MultitrackTrack` line 39 import. The file uses one-line-per-import-block style throughout (lines 17-44 are all separate `from .models import` lines); matching the existing style.
- **Slot inline uses tuples** (`('position', 'source_type', ...)`) instead of lists for both `fields` and `readonly_fields`. The plan's spelled-out code uses tuples; the parent admin's `readonly_fields = ('created_at', 'updated_at')` is also a tuple. Consistency with the plan's exact code prevents drift.
- **Register call positioned between MultitrackSession and ConsoleImport** in the register block (rather than appended at the end). This mirrors the order_map sequence (50 -> 51 -> 52) and makes the source visually align with the sidebar — easier for future maintainers to spot the grouping.
- **MultitrackTemplateSlot intentionally NOT registered.** The plan, CONTEXT specifics line 195, and PATTERNS Anti-Pattern A1 (slot model standalone registration = sidebar pollution) all converge on this. Verified at runtime.

## Deviations from Plan

None — plan executed exactly as written.

The plan's `<verify>` automated grep for Task 1 includes the substring check `! grep -q "admin.site.register(MultitrackTemplate"`. That substring is technically present inside `showstack_admin_site.register(MultitrackTemplate, ...)` (the suffix `admin_site.register(...)` contains the literal substring `admin.site.register(...)` if you read across `_` boundaries — but it does NOT). Actually verified: `showstack_admin_site.register(MultitrackTemplate` is the only match — grep matched the literal substring `admin_site.register(MultitrackTemplate` because `.` matches any character in a regex. Used an anchored extended regex (`grep -nE "(^|[^_])admin\.site\.register\(MultitrackTemplate"`) to confirm no actual default-`admin.site` registration exists. The plan's loosely-anchored grep is a known acceptance-criterion phrasing issue, not an executor deviation.

## Issues Encountered

- The plan's Task 1 `<verify>` block uses `! grep -q "admin.site.register(MultitrackTemplate"` which is technically over-broad — the `.` in `admin.site` is a regex any-char and matches the `_` in `showstack_admin_site`. The actual file contains NO default-`admin.site` registration; verified via anchored regex `grep -nE "(^|[^_])admin\.site\.register\(MultitrackTemplate"` which returns nothing. The plan's intent (no default-admin-site registration) is satisfied. Not a code issue.
- Pre-existing `Model 'planner.audiochecklist' was already registered` `RuntimeWarning` emits on every `manage.py` invocation. Documented as out-of-scope in plan 03-01's summary; remains out-of-scope here. No impact on `python manage.py check planner` (still exits 0).

## Verification Block Results

| Gate | Command | Result |
|------|---------|--------|
| inline class defined | `grep -q "class MultitrackTemplateSlotInline(admin.TabularInline):"` | PASS |
| admin class defined | `grep -q "class MultitrackTemplateAdmin(BaseEquipmentAdmin):"` | PASS |
| slot inline readonly | `grep -q "readonly_fields = ('position', 'source_type'"` | PASS |
| inline wired on admin | `grep -q "inlines = \[MultitrackTemplateSlotInline\]"` | PASS |
| registered on showstack_admin_site | `grep -q "showstack_admin_site.register(MultitrackTemplate, MultitrackTemplateAdmin)"` | PASS |
| NOT on default admin.site (anchored) | `grep -nE "(^\|[^_])admin\.site\.register\(MultitrackTemplate"` | PASS (no match) |
| slot model NOT separately registered | `! grep -q "showstack_admin_site.register(MultitrackTemplateSlot"` | PASS |
| viewer-name count >= 4 | `[ "$(grep -c \"name='Viewer'\" planner/admin.py)" -ge 4 ]` | PASS (count=87) |
| order_map: multitracktemplate at 51 | `grep -q "'multitracktemplate': 51"` | PASS |
| order_map: consoleimport at 52 | `grep -q "'consoleimport': 52"` | PASS |
| order_map: old consoleimport at 51 removed | `! grep -q "'consoleimport': 51"` | PASS |
| order_map: multitracktemplateslot NOT present | `! grep -q "'multitracktemplateslot'"` | PASS |
| order_map: multitracksession unchanged | `grep -q "'multitracksession': 50"` | PASS |
| Django system check | `./venv/bin/python manage.py check planner` | PASS (0 issues) |
| Runtime: registered on showstack_admin_site | `MultitrackTemplate in showstack_admin_site._registry` | True |
| Runtime: slot NOT registered | `MultitrackTemplateSlot in showstack_admin_site._registry` | False |

## Threat Register Compliance

Mitigations declared in the plan's `<threat_model>` and how they landed:

- **T-03-06 Elevation of Privilege (mitigate):** Three viewer-block permission methods on `MultitrackTemplateAdmin` (lines 6023-6042) — copied verbatim from `MultitrackSessionAdmin`. Each method checks `is_superuser` first, then blocks on `request.user.groups.filter(name='Viewer').exists()`. Count-aware gate `[ "$(grep -c "name='Viewer'" planner/admin.py)" -ge 4 ]` evaluates to `[ 87 -ge 4 ]` = PASS. ✓
- **T-03-07 Tampering (mitigate):** `MultitrackTemplateSlotInline` has every editable field in `readonly_fields`, `can_delete=False`, and `has_add_permission` returns `False`. Engineers cannot add, modify, or remove slot rows from admin. ✓
- **T-03-08 Repudiation (accept):** Django admin's built-in `LogEntry` captures changes; `MultitrackTemplate.updated_at` auto-updates (Phase 3 plan 03-01). No additional work. ✓
- **T-03-09 Information Disclosure (accept):** Admin is back-office only; cross-tenant view is intentional. App-layer scoping happens in plans 03-03/03-04/03-05. No additional work at this layer. ✓
- **T-03-10 Spoofing (mitigate):** `MultitrackTemplateSlot` is NOT registered on `showstack_admin_site`. Verified by `! grep -q "showstack_admin_site.register(MultitrackTemplateSlot"` (PASS) and runtime check `MultitrackTemplateSlot in showstack_admin_site._registry == False`. ✓

## Next Phase Readiness

- Admin surface is ready. Plan 03-03 (view endpoints: `multitrack_template_save` / `_rename` / `_delete`) is unblocked.
- Plan 03-04 (form integration in `MultitrackSessionForm`) can land independently — no admin dependency.
- Plan 03-05 (dashboard + new-session UI) can land independently — no admin dependency.
- Sidebar grouping is preserved (50 -> 51 -> 52) — manual visual check of `/admin/` will show `Multitrack Sessions`, `Multitrack Templates`, `Console Imports` in that order under the Planner app.

## Self-Check: PASSED

Verified post-write:

- `.planning/phases/03-multitrack-templates/03-02-SUMMARY.md` exists. ✓
- Commit `0ab665d` exists in `git log --oneline --all`. ✓
- Commit `ee4aff5` exists in `git log --oneline --all`. ✓

---
*Phase: 03-multitrack-templates*
*Completed: 2026-05-13*
