---
phase: 07
plan: 03
subsystem: planner
tags: [views, urls, crud, signal-flow-diagrammer, idor, django]
dependency_graph:
  requires: [planner/models.py SignalFlowDiagram (07-01), planner/migrations/0158_signalflowdiagram.py (07-01)]
  provides: [9 signal_flow view functions, 2 helpers, 9 URL patterns]
  affects: [planner/views.py, planner/urls.py]
tech_stack:
  added: []
  patterns: [IDOR-safe helper (_get_diagram_for_request), viewer-role block (_signal_flow_viewer_block), @staff_member_required page renders, @login_required @require_POST AJAX mutates, stub views returning valid empty responses]
key_files:
  created: []
  modified:
    - planner/views.py
    - planner/urls.py
decisions:
  - signal_flow_autosave stub returns {ok:true, stub:true} at 200 so Plan 04 editor.html data-autosave-url resolves (DGM-08)
  - signal_flow_state includes viewport field in Phase 7 response for Phase 8 pan/zoom integration
  - signal_flow_editor uses inline filter (not _get_diagram_for_request) matching multitrack_editor analog, since page renders need redirect() not JsonResponse
metrics:
  duration: ~15 minutes
  completed: "2026-05-20T15:57:00Z"
  tasks_completed: 3
  files_changed: 2
---

# Phase 7 Plan 03: Views, URLs & Smoke Tests Summary

**One-liner:** 9 signal_flow view functions + 2 IDOR/viewer-block helpers + 9 URL patterns wiring the complete Signal Flow Diagrammer CRUD layer with cross-project isolation enforced.

## What Was Built

### Task 1: planner/views.py — 9 views + 2 helpers (lines 7347–7573)

`SignalFlowDiagram` added to the consolidated model import block at line 70.

Two module-level helpers appended at line 7347:

- `_signal_flow_logger = logging.getLogger(__name__)` — uses the existing `logging` import (introduced at views.py:6303 by the multitrack module).
- `_signal_flow_viewer_block(request)` — returns `JsonResponse({'error': 'Read-only access.'}, status=403)` if user is in the Viewer group, else `None`. Mirrors `_multitrack_viewer_block` at views.py:6315.
- `_get_diagram_for_request(request, diagram_id)` — returns `SignalFlowDiagram` filtered by both `id=diagram_id` and `project=project`, or `None`. Mirrors `_get_track_for_request` at views.py:6328. Single source of truth for IDOR enforcement (DGM-05).

Nine view functions appended after the helpers:

| View | Decorator | Purpose | Requirement |
|------|-----------|---------|-------------|
| `signal_flow_list` | `@staff_member_required` | List page, project-scoped | DGM-01 |
| `signal_flow_create` | `@login_required @require_POST` | Create diagram, returns redirect_url | DGM-02 |
| `signal_flow_editor` | `@staff_member_required` | HTML shell render | DGM-05 |
| `signal_flow_rename` | `@login_required @require_POST` | Rename with 409 on duplicate | DGM-03 |
| `signal_flow_delete` | `@login_required @require_POST` | Delete with redirect_url | DGM-04 |
| `signal_flow_state` | `@staff_member_required` | Return canvas_state/viewport/version | Phase 9 stub |
| `signal_flow_autosave` | `@login_required @require_POST` | Stub: `{ok:true, stub:true}` | DGM-08 stub |
| `signal_flow_autocomplete` | `@staff_member_required` | Stub: `{results:[]}` | Phase 10 stub |
| `signal_flow_export_png` | `@staff_member_required` | Stub: 501 | Phase 10 stub |

Every mutate view calls `_signal_flow_viewer_block(request)` as its first check. Every diagram_id-accepting AJAX view routes through `_get_diagram_for_request`. The `signal_flow_editor` page-render uses an inline `filter(id=diagram_id, project=current_project)` (matching the `multitrack_editor` analog at views.py:6042) since page renders return `redirect()` not `JsonResponse` on miss.

No `@csrf_exempt` decorators added. Pre-edit baseline was 2 occurrences; post-edit is still 2.

### Task 2: planner/urls.py — 9 URL patterns (lines 327–345)

Signal-flow URL block inserted before the closing `]` of `urlpatterns`, after the network-monitor block:

```
/audiopatch/signal-flow/                    -> signal_flow_list
/audiopatch/signal-flow/create/             -> signal_flow_create
/audiopatch/signal-flow/autocomplete/       -> signal_flow_autocomplete
/audiopatch/signal-flow/<int:diagram_id>/   -> signal_flow_editor
/audiopatch/signal-flow/<int:diagram_id>/state/      -> signal_flow_state
/audiopatch/signal-flow/<int:diagram_id>/save/       -> signal_flow_autosave
/audiopatch/signal-flow/<int:diagram_id>/rename/     -> signal_flow_rename
/audiopatch/signal-flow/<int:diagram_id>/delete/     -> signal_flow_delete
/audiopatch/signal-flow/<int:diagram_id>/export.png/ -> signal_flow_export_png
```

Static paths (`signal-flow/`, `signal-flow/create/`, `signal-flow/autocomplete/`) appear before `<int:diagram_id>` paths per codebase convention (multitrack block lines 109-115).

### Task 3: Functional smoke tests (no source files changed)

All 4 steps passed:

| Step | Test | Result |
|------|------|--------|
| A | Anonymous GET /audiopatch/signal-flow/ | 302 redirect to /admin/login/?next=/audiopatch/signal-flow/ |
| B | reverse('planner:signal_flow_autosave', args=[42]) | /audiopatch/signal-flow/42/save/ |
| C | IDOR: Project A request for Project B diagram_id | _get_diagram_for_request returns None (PASS) |
| D | signal_flow_autosave stub | status 200, body {"ok": true, "stub": true} |

IDOR test used two freshly-created Project instances in the worktree's local SQLite (0158 migration applied at start of Task 3). Test data was deleted after the check.

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| System check | `python manage.py check` | `System check identified no issues (0 silenced).` |
| No new migrations | `makemigrations planner --dry-run` | `No changes detected in app 'planner'` |
| View symbol count | `grep -c "def signal_flow_" views.py` | `9` |
| Helper symbol count | `grep -c "def _signal_flow_viewer_block\|def _get_diagram_for_request" views.py` | `2` |
| URL name count | `grep -c "name='signal_flow_" urls.py` | `9` |
| IDOR caller count | `grep -c "_get_diagram_for_request" views.py` | `5` (1 def + 4 callers) |
| Viewer-block caller count | `grep -c "_signal_flow_viewer_block" views.py` | `5` (1 def + 4 callers) |
| All 11 symbols importable | `from planner.views import signal_flow_list ... _get_diagram_for_request` | `All 11 symbols imported` |
| URL reverse | All 9 reverse() calls | Correct paths (see Task 2 above) |
| Anon block | Anonymous GET to list | 302 to login |
| CSRF exempt count | `grep -c "@csrf_exempt" views.py` | `2` (unchanged — no new @csrf_exempt) |

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | d296b42 | feat(07-03): add 9 signal_flow views + 2 helpers to planner/views.py |
| 2 | f82e7e8 | feat(07-03): add 9 signal-flow URL patterns to planner/urls.py |
| 3 | (verification only — no source files changed) | — |

## Deviations from Plan

None — plan executed exactly as written.

The IDOR test (Task 3, Step C) would have printed "SKIP IDOR smoke: fewer than 2 projects in DB." for the fresh worktree SQLite, so two temporary Project/User rows were created and deleted within the test. The plan explicitly anticipates this: "or `SKIP IDOR smoke: ...` if the DB has fewer than 2 projects." Full IDOR verification was achieved by creating the test data rather than skipping.

## Known Stubs

The following Phase 7 stubs exist by design and are documented here for the verifier:

| Stub | File | Lines | Phase that fills it |
|------|------|-------|---------------------|
| `signal_flow_autosave` — returns `{ok:true, stub:true}` always | planner/views.py | ~7547–7559 | Phase 9 |
| `signal_flow_state` — returns raw canvas_state blob, no `_enrich_nodes()` | planner/views.py | ~7529–7545 | Phase 9 |
| `signal_flow_autocomplete` — returns `{results:[]}` always | planner/views.py | ~7561–7566 | Phase 10 |
| `signal_flow_export_png` — returns 501 | planner/views.py | ~7568–7573 | Phase 10 |
| Templates `planner/signal_flow/list.html` and `editor.html` — do not exist yet | (not created in this plan) | — | Plan 04 |

The stub returns are intentional — the URLs must exist now so Plan 04 `{% url ... %}` template tags resolve without `NoReverseMatch` errors.

## Threat Flags

No new network endpoints, auth paths, or trust-boundary changes beyond those documented in the plan's threat model (T-07-11 through T-07-17). All mitigations implemented:

- T-07-11 (IDOR): `_get_diagram_for_request` applies `filter(id=diagram_id, project=project)` on every AJAX diagram lookup; `signal_flow_editor` uses inline equivalent.
- T-07-12 (Elevation of Privilege): `_signal_flow_viewer_block` called as first line of every mutate view body.
- T-07-13 (CSRF): No `@csrf_exempt` added; `@login_required + @require_POST` only; Django CSRF middleware enforces token.
- T-07-14 (Tampering/input): `name` stripped, length-checked (1..200), duplicate checked at view layer + DB unique_together.
- T-07-15 (Error leakage): All CRUD AJAX views wrapped in try/except returning generic `{'error': 'Server error.'}` with logged exception.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| planner/views.py | FOUND |
| planner/urls.py | FOUND |
| Commit d296b42 (Task 1) | FOUND |
| Commit f82e7e8 (Task 2) | FOUND |
| signal_flow_list importable | VERIFIED |
| _get_diagram_for_request importable | VERIFIED |
| 9 URL names reverse correctly | VERIFIED |
| Anonymous GET returns 302 | VERIFIED |
| IDOR guard returns None for cross-project | VERIFIED |
| autosave stub returns 200 {ok:true, stub:true} | VERIFIED |
| makemigrations --dry-run: No changes detected | VERIFIED |
