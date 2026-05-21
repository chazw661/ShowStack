---
phase: 08-canvas-smart-shapes-connectors
plan: 01
subsystem: api
tags: [django, json-api, idor, contenttype, signal-flow, jointjs]

# Dependency graph
requires:
  - phase: 07-foundation-crud-editor-shell
    provides: SignalFlowDiagram model (canvas_state/viewport/version), 9 URL patterns with stub views, _signal_flow_viewer_block + _get_diagram_for_request helpers
provides:
  - signal_flow_autocomplete real body (project-scoped equipment dispatch — console/device/speakerarray/commbeltpack)
  - signal_flow_autosave real body (canvas_state + viewport persist, unconditional version bump, cross-project IDOR rejection, viewport_only=1 fast path)
  - MODEL_MAP dispatch pattern for per-type IDOR-safe equipment queries
  - SpeakerArray prediction__project scoping pattern (no direct project FK)
affects: [08-04 picker JS, 08-06 manual save trigger, Phase 9 autosave debounce + 409, Phase 10 separate signal_flow_label_autocomplete URL]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-type MODEL_MAP dispatch with (Model, project_filter_kwargs, search_fields, label_fn, detail_fn) tuples — keeps IDOR special-cases (SpeakerArray) isolated"
    - "Server-side cross-project equipment ref validation walking canvas_state.cells (PITFALLS.md §4 baseline)"
    - "Local ContentType import inside view body — avoids polluting the module-level imports for one feature"

key-files:
  created: []
  modified:
    - planner/views.py (signal_flow_autocomplete + signal_flow_autosave: stubs at 7558–7564 / 7547–7555 replaced with real bodies; ~190 lines net added)

key-decisions:
  - "Repurpose signal_flow_autocomplete URL for equipment picker now (Option A from PATTERNS.md risk #1). Phase 10 adds a SEPARATE signal_flow_label_autocomplete URL — no ?kind= branching."
  - "MODEL_MAP uses verified planner/models.py field names. The CONTEXT.md D-11 / RESEARCH.md §17 secondary-field guesses (dsp_mixer, channel_count, model, serial, cabinet_count, beltpack_id) were wrong for every type and were rejected."
  - "viewport_only=1 query param folded into the same autosave URL — keeps URL count stable (no urls.py edit). Plan 08-01 frontmatter restricts files_modified to planner/views.py."
  - "Version bumps unconditionally on every save in Phase 8 (no If-Match check). Single-tab manual save cannot race itself; Phase 9 adds the real optimistic lock + HTTP 409."
  - "SpeakerArray IDOR uses prediction__project=current_project in BOTH the autocomplete dispatch and the autosave validation walk. PATTERNS.md risk #3 closed in two places."

patterns-established:
  - "Per-type IDOR dispatch: build a config dict whose value is a tuple including the project-filter kwarg dict, so models with non-standard scoping (SpeakerArray.prediction.project) plug in without polluting the standard branch."
  - "Cell-walk equipment validation: iterate canvas_state.cells, read showstack/{contentTypeId, objectId}, resolve via ContentType, branch on model_name == 'SpeakerArray' for the prediction__project query, fall back to project= for the rest. HTTP 422 on cross-project ref."
  - "Per-row try/except in the autocomplete result list — one bad row (e.g. SpeakerArray with NULL configuration) doesn't poison the whole response. Logged via _signal_flow_logger.exception."

requirements-completed: [SHP-09]

# Metrics
duration: 2min 17s
completed: 2026-05-21
---

# Phase 8 Plan 01: Autocomplete + Autosave View Bodies Summary

**Project-scoped equipment-picker autocomplete (4 model types via MODEL_MAP dispatch) and canvas_state persist endpoint with cross-project IDOR rejection on every cell ref — the two server endpoints Phase 8's JS layer talks to.**

## Performance

- **Duration:** 2 min 17 s (137 seconds)
- **Started:** 2026-05-21T01:44:43Z
- **Completed:** 2026-05-21T01:47:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- `signal_flow_autocomplete` (GET, `@staff_member_required`) replaced: returns `{results: [{id, contentTypeId, name, detail}, ...]}` filtered by `?type=` ∈ {console, device, speakerarray, commbeltpack} and `?q=` substring match. Project-scoped. Hard cap `[:50]`. ContentType pk looked up once per request.
- `signal_flow_autosave` (POST, `@login_required + @require_POST`) replaced: persists `canvas_state` + `viewport`, bumps `version`, rejects cross-project equipment refs with HTTP 422 (walking every cell), supports a viewport-only fast path via `?viewport_only=1`. Viewer group blocked with 403 before any DB hit.
- PATTERNS.md risks #1 (URL semantics), #2 (verified equipment-model field names), #3 (SpeakerArray prediction__project) all resolved inline.
- Threat-model mitigations T-08-01 / T-08-02 / T-08-03 / T-08-04 implemented; T-08-05 (50-row cap) and T-08-08 (`_signal_flow_logger.exception` on 500s) in place. No HIGH-severity threats remain unmitigated.

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace signal_flow_autocomplete stub with project-scoped per-type equipment lookup** — `7be782f` (feat)
2. **Task 2: Replace signal_flow_autosave stub with canvas_state + viewport persist (simplified, no 409)** — `cee8bd3` (feat)

## Files Created/Modified

- `planner/views.py` — Replaced two Phase 7 stubs (at lines 7547–7555 and 7558–7564 in the pre-edit file) with full implementations. Net ~190 lines added, no other regions touched. Logger `_signal_flow_logger` and helpers `_signal_flow_viewer_block` / `_get_diagram_for_request` reused from Phase 7.

## Decisions Made

- **PATTERNS.md risk #1 → Option A.** `signal_flow_autocomplete` is now the equipment picker view; its docstring documents that Phase 10 will add a separate `signal_flow_label_autocomplete` URL for circuit-label string completion. No `?kind=` parameter, no shared URL between two unrelated features.
- **MODEL_MAP field names verified, not guessed.** Console only has `name` + `is_template` + `primary_ip_address`; Device has `name` + `input_count` + `output_count`; SpeakerArray has `source_name` + `array_base_name` (NO `name`); CommBeltPack has `bp_number` IntegerField + `manufacturer` choices (NO `name` CharField). Detail strings render from these verified fields. `get_configuration_display()` and `get_manufacturer_display()` are used for human-readable labels.
- **`bp_number` search uses exact-match on digits only.** It's an `IntegerField`; building `__icontains` on it would 500 inside the ORM. The dispatch branches on field name = `'bp_number'` and falls through to `__icontains` for everything else.
- **SpeakerArray IDOR via `prediction__project`** in both view bodies. The naive `Model.objects.filter(project=...)` would have raised `FieldError` on SpeakerArray — silent broken UX, not silent cross-project leak — but the plan's threat model still requires the prediction__project filter as the authoritative IDOR check.
- **viewport_only=1 folded into the existing autosave URL.** Adding a separate `signal_flow_save_viewport` URL would have required editing `planner/urls.py`, which is outside `files_modified` in the plan frontmatter. Branching inside the view body keeps the contract.
- **Unconditional version bump.** Plan 08-01 frontmatter explicitly says "no 409 yet — Phase 9". Phase 8's verification flow is single-tab manual save; there's no race condition to lose. Phase 9 will add `If-Match` against `diagram.version`.

## Deviations from Plan

None — plan executed exactly as written. Both tasks completed without invoking any deviation rule. The plan's `must_haves.truths` (five behavioral invariants) and `acceptance_criteria` greps all pass on first run.

## Issues Encountered

None.

## Self-Check: PASSED

- `planner/views.py` modification: **FOUND** — `git log --name-only HEAD~2..HEAD` shows two commits each touching only `planner/views.py`.
- Commit `7be782f`: **FOUND** — `git log --oneline | grep 7be782f` returns the Task 1 commit subject `feat(08-01): implement signal_flow_autocomplete equipment picker view`.
- Commit `cee8bd3`: **FOUND** — `git log --oneline | grep cee8bd3` returns the Task 2 commit subject `feat(08-01): implement signal_flow_autosave canvas_state persist view`.
- `python manage.py check planner` exits 0 after both tasks.
- All acceptance-criteria grep checks (Task 1 and Task 2) pass with the predicted hit counts. The single non-zero hit in the "forbidden field-name guesses" check (`'serial'` at views.py:4396) is inside unrelated CommConfig 4W-port logic, far from the autocomplete view (lines 7558–7662) — not a violation.

## User Setup Required

None — no external service configuration, no new migrations, no new dependencies.

## Next Phase Readiness

- **Plan 08-04 (equipment picker JS)** can now `GET /audiopatch/signal-flow/autocomplete/?type=console&q=foo` and consume `{results: [...]}`. The shape exactly matches RESEARCH.md §17 / §18 picker flow.
- **Plan 08-06 (toolbar manual Save)** can now `POST /audiopatch/signal-flow/<id>/save/` with `{canvas_state, viewport}` body. Response: `{ok: true, version: N}` on success; `422` on stale/cross-project equipment ref; `403` for Viewer group; `404` for cross-project diagram id.
- **Phase 9** inherits a clean version-bump baseline. Adding the optimistic-lock check means: read `If-Match` header → compare to `diagram.version` → return 409 instead of bumping. No refactor of the existing body needed.
- **Phase 10** has the contract for `signal_flow_label_autocomplete` (separate URL, separate view) flagged in `signal_flow_autocomplete`'s docstring. No URL conflict to untangle later.

---
*Phase: 08-canvas-smart-shapes-connectors*
*Completed: 2026-05-21*
