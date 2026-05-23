---
phase: 10-autocomplete-png-export-new-shapes
plan: 01
subsystem: signal-flow-diagrammer
tags: [server, django, idor, autocomplete, enrichment, picker]
requires:
  - planner.models.DeviceInput
  - planner.models.DeviceOutput
  - planner.models.ConsoleInput
  - planner.models.ConsoleAuxOutput
  - planner.models.AmpChannel
  - planner.models.P1Input
  - planner.models.P1Output
  - planner.models.GalaxyInput
  - planner.models.GalaxyOutput
  - planner.models.Amp
  - planner.models.SystemProcessor
  - planner.views._enrich_nodes (Phase 9)
  - planner.views.signal_flow_autocomplete (Phase 8)
  - planner.views.signal_flow_autosave (Phase 9)
provides:
  - planner.views.signal_flow_label_autocomplete
  - planner:signal_flow_label_autocomplete URL
  - Amp + SystemProcessor IDOR allowlist entries
  - Amp + SystemProcessor _enrich_nodes entries
  - 'processor' + 'amp' MODEL_MAP picker entries
affects:
  - Wave-2 plan 10-02 (relies on picker + IDOR + enrich for new shape types)
  - Wave-2 plan 10-03 (consumes signal_flow_label_autocomplete URL)
  - Future Phase 11 PORT-03 (D-04 — same endpoint reused unchanged)
tech-stack:
  added: []
  patterns:
    - Multi-source UNION-like aggregation via iterated per-model values_list
    - select_related guard at picker queryset level to prevent N+1 on Amp.amp_model
    - IDOR allowlist + project FK scoping for all 9 label sources
key-files:
  created:
    - planner/tests/test_signal_flow_phase10.py
  modified:
    - planner/views.py
    - planner/urls.py
decisions:
  - "D-05 honored: SystemProcessor.name excluded from label autocomplete sources (device identifier, not signal name)"
  - "Allowlist scope: Amp + SystemProcessor only — NOT P1Processor/GalaxyProcessor (child config models, never canvas GFK targets per research §Open Q1)"
  - "Picker 'processor' type targets SystemProcessor (research §Pitfall 2): badge text via get_device_type_display()"
  - "select_related('amp_model') added to amp picker queryset to prevent N+1 on lambda detail_fn"
  - "Label sort: case-insensitive alphabetical by .lower() per D-03"
  - "Test refinement: test_no_active_project_returns_400 uses a zero-project user (CurrentProjectMiddleware auto-selects first owned project for any user with owned projects)"
metrics:
  duration: "~6 minutes"
  completed: "2026-05-23T13:59Z"
  tasks_completed: 2
  files_created: 1
  files_modified: 2
  tests_added: 20
  tests_passing: 20
---

# Phase 10 Plan 01: Server-side foundation (autocomplete + picker + IDOR + enrich) Summary

Four targeted server-side changes in `planner/views.py` + 1 URL registration in `planner/urls.py` unlock Phase 10's new features: a new `signal_flow_label_autocomplete` view that aggregates 9 signal-name sources, an extended equipment picker (Processor + Amp), and IDOR + enrich allowlists extended for Amp and SystemProcessor so the new Phase 10 shape types do not silently 422 on autosave or render as permanent orphans on load.

## What Changed

### 1. `signal_flow_label_autocomplete` (new view, ~80 lines)

`planner/views.py` (added immediately before `signal_flow_export_png`):

- `@staff_member_required` + `@require_GET`.
- Reads `q` (optional) and `request.current_project` (mandatory — returns 400 if absent).
- Iterates a hard-coded `SOURCES` list of 9 tuples `(Model, label_field, scope_kwarg, source_tag)`.
- Per source: `.filter(<scope_kwarg>=current_project)` + optional `<field>__icontains=q` + `.exclude(<field>='')` + `.exclude(<field>__isnull=True)` + `.values_list(field, flat=True).distinct()[:50]`.
- Dedupes by `(label, source_tag)` via a `seen` set, then sorts case-insensitively, returns `results[:8]`.
- URL: `signal-flow/label-autocomplete/` (name `signal_flow_label_autocomplete`).

Full `SOURCES` list (9 entries, SystemProcessor excluded per D-05):

| Model | Label field | IDOR scope kwarg | Source tag (D-02) |
|---|---|---|---|
| `DeviceInput` | `signal_name` | `device__project` | `Device Input` |
| `DeviceOutput` | `signal_name` | `device__project` | `Device Output` |
| `ConsoleInput` | `source` | `console__project` | `Console Input` |
| `ConsoleAuxOutput` | `name` | `console__project` | `Console Aux Out` |
| `AmpChannel` | `channel_name` | `amp__project` | `Amp Channel` |
| `P1Input` | `label` | `p1_processor__system_processor__project` | `P1 Input` |
| `P1Output` | `label` | `p1_processor__system_processor__project` | `P1 Output` |
| `GalaxyInput` | `label` | `galaxy_processor__system_processor__project` | `Galaxy Input` |
| `GalaxyOutput` | `label` | `galaxy_processor__system_processor__project` | `Galaxy Output` |

### 2. `signal_flow_autocomplete` MODEL_MAP — added `processor` + `amp`

`planner/views.py` (in `MODEL_MAP` block):

- `'processor'` → `SystemProcessor` (badge from `get_device_type_display()` per D-10 — "L'Acoustics P1" / "Meyer GALAXY").
- `'amp'` → `Amp` (badge from `str(a.amp_model) if a.amp_model else '—'`).
- Added `if shape_type == 'amp': qs = qs.select_related('amp_model')` after the initial `Model.objects.filter(**project_kw)` to prevent N+1 on `str(a.amp_model)`.
- Docstring updated to include `processor` + `amp` in the `type` parameter description, with explicit note that `processor` targets `SystemProcessor` (not P1Processor/GalaxyProcessor — research §Pitfall 2).

### 3. `_enrich_nodes` allowlist — added Amp + SystemProcessor

`planner/views.py` (around former line 7573, now ~7577 after change 1's comment block):

```python
elif model_name in ('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor'):
```

Both `Amp.name` and `SystemProcessor.name` work with the existing `values_list('id', 'name')` call unchanged — no further changes needed.

### 4. `signal_flow_autosave` IDOR allowlist — added Amp + SystemProcessor

`planner/views.py` (around former line 7704):

```python
elif model_name in ('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor'):
```

This is the most-critical change in the plan: without it, every autosave POST containing an Amp or SystemProcessor cell would return HTTP 422 — the client's 422 handler logs the error but does not surface it to the user, causing silent data loss (research §Pitfall 1).

### 5. URL registration

`planner/urls.py` (immediately after `signal-flow/autocomplete/`, before `<int:diagram_id>` routes):

```python
path('signal-flow/label-autocomplete/', views.signal_flow_label_autocomplete, name='signal_flow_label_autocomplete'),
```

Resolves to: `/audiopatch/signal-flow/label-autocomplete/`.

## Import additions

`planner/views.py` model import block extended with:

- `DeviceInput`
- `DeviceOutput`
- `AmpChannel`

All other models used by the new view (`Amp`, `SystemProcessor`, `ConsoleInput`, `ConsoleAuxOutput`, `P1Input`, `P1Output`, `GalaxyInput`, `GalaxyOutput`) were already imported in the same block. No new top-level `from ... import` lines added — the existing consolidated block was extended in-place per plan instructions.

## Test Suite

New: `planner/tests/test_signal_flow_phase10.py` — 20 tests across 4 classes, 542 lines.

| Class | Tests | What it locks |
|---|---|---|
| `SignalFlowLabelAutocompleteTests` | 8 | Endpoint shape (`{results: [{label, source}]}`), max-8 / alphabetical, source-tag D-02 format, blank/null exclusion, IDOR (cross-project), P1/Galaxy labels, no-active-project 400 |
| `SignalFlowAutosaveAllowlistTests` | 4 | Amp cell → 200, SystemProcessor cell → 200, unallowlisted model (Project) → 422, cross-project Amp → 422 |
| `SignalFlowStateEnrichAmpProcessorTests` | 4 | Amp cell `isOrphan=false` when record exists, `isOrphan=true` + D-14 label preservation when deleted; same for SystemProcessor |
| `SignalFlowPickerProcessorAmpTests` | 4 | `?type=processor` + `?type=amp` results, correct ContentType id (SystemProcessor, not P1Processor), cross-project IDOR exclusion |

Shared `_Phase10Base` mirrors the Phase 9 `force_login` + `session['current_project_id']` wiring exactly.

## Allowlist & Enrichment Reference (for Wave 2)

**`_enrich_nodes` model allowlist (planner/views.py around line 7575):**

```
('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor')
```
(plus `SpeakerArray` handled separately via `prediction__project`)

**`signal_flow_autosave` IDOR allowlist (planner/views.py around line 7710):**

```
('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor')
```
(plus `SpeakerArray` handled separately via `prediction__project`)

**`MODEL_MAP` picker keys (planner/views.py signal_flow_autocomplete):**

```
console, device, speakerarray, commbeltpack, processor, amp
```

## URL Name for Wave 2 (Plan 10-03)

```python
reverse('planner:signal_flow_label_autocomplete')  # -> /audiopatch/signal-flow/label-autocomplete/
```

The JS in plan 10-03 should read this URL from a `data-label-autocomplete-url` attribute on `#sfd-container` (research §Open Q3). Adding that attribute is plan 10-03's concern — this plan only registers the URL.

## Decisions Made

1. **D-05 (CONTEXT decision) honored as research-recommended:** SystemProcessor excluded from label autocomplete sources. The signal-name data lives on the child P1Input/P1Output/GalaxyInput/GalaxyOutput models (via P1Processor / GalaxyProcessor → SystemProcessor → project IDOR path).
2. **Allowlist scope:** Only `Amp` + `SystemProcessor` added (not `P1Processor` / `GalaxyProcessor`). Research §Open Q1 / §Pitfall 2 establishes that the picker targets SystemProcessor — P1Processor and GalaxyProcessor are child-config models that never appear as canvas GFK targets.
3. **N+1 guard for Amp picker:** `select_related('amp_model')` added before any search filter, scoped to `shape_type == 'amp'` so other shape types pay nothing.
4. **Sort:** Case-insensitive alphabetical via `key=lambda r: r['label'].lower()`. Matches D-03 ("alphabetical by label") and produces stable ordering for mixed-case labels.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test design fix] `test_no_active_project_returns_400` rewritten to use zero-project user**

- **Found during:** GREEN verification of Task 2 (1 of 20 tests failed: 200 != 400).
- **Root cause:** `CurrentProjectMiddleware` (planner/middleware.py:55-66) auto-selects the user's first owned project when `session['current_project_id']` is missing. The original test deleted the session key, but the middleware then auto-selected `self.project` again — so `request.current_project` was never `None`.
- **Fix:** Test now creates a third `User` (`loner`) with zero owned projects and zero `ProjectMember` rows, force_logs-in via a fresh `Client`, and hits the endpoint. With no projects to auto-select, the middleware leaves `request.current_project = None` and the view's `if not current_project: return 400` guard fires correctly.
- **Files modified:** `planner/tests/test_signal_flow_phase10.py` (single test method)
- **Commit:** `ada1ff4` (folded into Task 2 GREEN commit)

No other deviations. Plan instructions executed as written. The CONTEXT.md plan-checker reminder that the `from itertools import chain` import was "possibly needed" turned out to be unnecessary — the final implementation iterates the 9 sources in a simple `for` loop without needing `chain()`.

## Authentication Gates

None. All tests run via `Client.force_login()` against an in-memory test database. No external auth required.

## TDD Gate Compliance

Plan executed as TDD per `tdd="true"` task markers:

| Gate | Commit | Result |
|---|---|---|
| RED  | `814ca7a` test(10-01): add failing tests ... | 16 fail/error, 4 incidental passes |
| GREEN | `ada1ff4` feat(10-01): add label autocomplete view, extend picker/enrich/IDOR ... | 20/20 PASS |

No REFACTOR commit needed — implementation landed clean.

## Known Stubs

None. `signal_flow_export_png` remains a 501 stub (intentional — Wave 2 plan 10-03 handles client-side PNG export via html-to-image; no server-side rasterization needed per D-08).

## Threat Flags

None. The new view only adds defensive surface (a `q` parameter scoped to `current_project` via 9 explicit IDOR paths). All threats in the plan's `<threat_model>` are mitigated as designed (T-10-01..T-10-05 all dispositioned `mitigate` or `accept` with rationale).

## Verification Run (all green)

```
$ /Users/charlielawsonmacair/DjangoProjects/audiopatch/venv/bin/python manage.py test planner.tests.test_signal_flow_phase10
Ran 20 tests in 6.290s
OK

$ python manage.py test planner.tests.test_signal_flow_phase9   # regression
Ran 12 tests in 3.555s
OK

$ python manage.py check
System check identified no issues (0 silenced).

$ python manage.py makemigrations --check --dry-run
No changes detected

$ reverse('planner:signal_flow_label_autocomplete')
/audiopatch/signal-flow/label-autocomplete/
```

## Commits

| Hash | Subject |
|---|---|
| `814ca7a` | test(10-01): add failing tests for label autocomplete, IDOR allowlist, enrichment, picker |
| `ada1ff4` | feat(10-01): add label autocomplete view, extend picker/enrich/IDOR for Amp + SystemProcessor |

## Self-Check: PASSED

Files created/modified verification:
- FOUND: `planner/tests/test_signal_flow_phase10.py`
- FOUND: `planner/views.py` (signal_flow_label_autocomplete defined + 4 changes)
- FOUND: `planner/urls.py` (signal_flow_label_autocomplete URL registered)

Commit verification:
- FOUND: `814ca7a` (RED — tests)
- FOUND: `ada1ff4` (GREEN — implementation)

URL resolution: confirmed via `reverse('planner:signal_flow_label_autocomplete')` returning `/audiopatch/signal-flow/label-autocomplete/`.

Test outcomes: 20/20 Phase 10 PASS + 12/12 Phase 9 regression PASS.
