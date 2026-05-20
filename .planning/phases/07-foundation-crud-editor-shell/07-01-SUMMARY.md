---
phase: 07
plan: 01
subsystem: planner
tags: [model, migration, admin, signal-flow-diagrammer, django]
dependency_graph:
  requires: [planner/migrations/0157_crew_crewmember_crewprojectadd.py]
  provides: [SignalFlowDiagram model, migration 0158, SignalFlowDiagramAdmin]
  affects: [planner/admin_ordering.py sidebar order]
tech_stack:
  added: []
  patterns: [BaseEquipmentAdmin subclass, showstack_admin_site registration, always_hidden + order_map dual update, unique_together FK scoping]
key_files:
  created:
    - planner/migrations/0158_signalflowdiagram.py
  modified:
    - planner/models.py
    - planner/admin.py
    - planner/admin_ordering.py
decisions:
  - viewport + version fields added in Phase 7 to avoid Phase 8/9 extra migrations (locked research decision)
  - canvas_state excluded from admin form; shown as read-only canvas_state_display to prevent admin tampering (T-07-01 mitigation)
  - changelist_view redirects to planner:signal_flow_list — URL created in Plan 03, safe as lazy Django resolver
metrics:
  duration: ~5 minutes
  completed: "2026-05-20T14:05:35Z"
  tasks_completed: 2
  files_changed: 4
---

# Phase 7 Plan 01: SignalFlowDiagram Model, Migration & Admin Summary

**One-liner:** SignalFlowDiagram single-blob model with viewport/version fields, migration 0158, and admin registered on showstack_admin_site with sidebar suppression.

## What Was Built

Task 1 added the `SignalFlowDiagram` Django model to `planner/models.py` appended after the `MultitrackTemplateSlot` class and helper function. The model follows the MultitrackSession pattern exactly: project FK with `related_name='signal_flow_diagrams'`, `name` (max_length=200), `canvas_state` + `viewport` JSONFields (default=dict), `version` IntegerField (default=1), and `created_at`/`updated_at` auto timestamps. The `Meta` class enforces `unique_together = [('project', 'name')]` at the DB layer.

`SignalFlowDiagramAdmin` was appended to `planner/admin.py`, registered with `@admin.register(SignalFlowDiagram, site=showstack_admin_site)`. It includes a `changelist_view` redirect to `planner:signal_flow_list`, a `canvas_state_display` read-only method rendering JSON as a collapsible `<details>` block, and Viewer-role guards on all three permission methods (matching MultitrackSessionAdmin pattern at admin.py:5906).

Both required `admin_ordering.py` edits were made in the same commit: `'signalflowdiagram'` added to the `always_hidden` set (with explanatory comment) and `'signalflowdiagram': 52` added to `order_map` after `'multitracktemplate': 51`.

Task 2 ran `python manage.py makemigrations planner` from the worktree, producing `planner/migrations/0158_signalflowdiagram.py` — a single `CreateModel` operation depending on `0157_crew_crewmember_crewprojectadd`. Migration applied cleanly to local SQLite. `makemigrations --dry-run --check` reports no further changes.

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| System check | `python manage.py check` | `System check identified no issues (0 silenced).` |
| No further changes | `makemigrations --dry-run --check planner` | `No changes detected in app 'planner'` |
| unique_together | `SignalFlowDiagram._meta.unique_together` | `(('project', 'name'),)` |
| Admin registry | `SignalFlowDiagram in showstack_admin_site._registry` | `True` |
| admin_ordering entries | `grep -c "'signalflowdiagram'" admin_ordering.py` | `2` (always_hidden + order_map) |
| Table accessible | `SignalFlowDiagram.objects.count()` | `0` (no error) |
| Migration filename | `ls planner/migrations/0158_signalflowdiagram.py` | Present |
| Migration dependency | `grep 0157_crew...` in migration | 1 match |

## Migration Details

- **Filename:** `planner/migrations/0158_signalflowdiagram.py`
- **Depends on:** `('planner', '0157_crew_crewmember_crewprojectadd')`
- **Operations:** Single `migrations.CreateModel` for `SignalFlowDiagram`
- **Fields:** id (auto), project (FK/CASCADE), name, canvas_state, viewport, version, created_at, updated_at
- **Options:** unique_together={('project', 'name')}, ordering=['-updated_at', 'name']
- **Local migrate output:** `Applying planner.0158_signalflowdiagram... OK`

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | a67841c | feat(07-01): add SignalFlowDiagram model, admin, and admin_ordering entries |
| 2 | e7e094d | feat(07-01): add migration 0158_signalflowdiagram + verify local SQLite migrate |

## Deviations from Plan

None — plan executed exactly as written.

The `python manage.py check` and `makemigrations` commands were run from the worktree directory (`/Users/.../worktrees/agent-ad85ab84`) using the project's `venv` Python after discovering that running from the main project directory would operate on the main branch's (unmodified) `planner/models.py` rather than the worktree's modified copy. This is expected worktree behavior, not a deviation.

## Known Stubs

None in this plan. The `changelist_view` redirect targets `planner:signal_flow_list` which does not yet exist (Plan 03 creates it), but this is intentional — Django resolves URL names lazily, so registering the admin class now is safe. This is documented in the PLAN.md action steps and is not a stub that blocks the plan's goal.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries beyond those already documented in the plan's threat model (T-07-01 through T-07-05). All mitigations from the threat register are implemented:
- T-07-01: `exclude = ['canvas_state', 'viewport']` prevents direct admin form edit
- T-07-02: `has_add/change/delete_permission` returns False for Viewer group
- T-07-03: `'signalflowdiagram'` in `always_hidden` suppresses sidebar; `changelist_view` redirects

## Self-Check: PASSED

| Item | Status |
|------|--------|
| planner/models.py | FOUND |
| planner/admin.py | FOUND |
| planner/admin_ordering.py | FOUND |
| planner/migrations/0158_signalflowdiagram.py | FOUND |
| Commit a67841c (Task 1) | FOUND |
| Commit e7e094d (Task 2) | FOUND |
