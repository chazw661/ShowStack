---
gsd_state_version: 1.0
milestone: v2.1
milestone_name: — Collaboration & User Management
status: executing
stopped_at: Phase 9 context gathered
last_updated: "2026-05-22T01:35:41.679Z"
last_activity: 2026-05-22 -- Phase 09 execution started
progress:
  total_phases: 9
  completed_phases: 8
  total_plans: 46
  completed_plans: 42
  percent: 91
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-19)

**Core value:** ShowStack knows your patch, your labels, and your gear; once entered, that data drives every export your show needs.
**Current focus:** Phase 09 — autosave-orphan-rendering

## Current Position

Phase: 09 (autosave-orphan-rendering) — EXECUTING
Plan: 1 of 4
Status: Executing Phase 09
Last activity: 2026-05-22 -- Phase 09 execution started

Progress: [          ] 0% (v2.2 scope only)

## Roadmap Summary

| Phase | Goal | Requirements |
|-------|------|--------------|
| 7. Foundation, CRUD & Editor Shell | List/create/rename/delete diagrams + editor HTML shell with JointJS vendor | DGM-01–05, DGM-08 (6 reqs) |
| 8. Canvas, Smart Shapes & Connectors | Live canvas, 5 smart shapes with equipment picker, 5 connector types, full canvas UX | CNV-01–08, SHP-01–05, SHP-08–09, CON-01–06 (21 reqs) |
| 9. Autosave & Orphan Rendering | Debounced autosave, 409 conflict, keepalive on unload, label propagation, ghost rendering | DGM-06–07, SHP-06–07 (4 reqs) |
| 10. Autocomplete & PNG Export | Signal-name autocomplete on connector labels + one-click PNG export | LBL-01–03, EXP-01 (4 reqs) |

Next: `/gsd-plan-phase 7`

## Accumulated Context

### From v1.0 Network Health Monitor (scrapped)

- Cloud-hosted ShowStack cannot reliably monitor on-site Dante networks. Standalone-app architecture is the correct path.
- AJAX polling (2-3 s) is more robust than SSE for ShowStack's request lifecycle.

### From v2.0 Multitrack Session Builder (shipped 2026-05-14)

- Defence-in-depth at AJAX boundary: server-side validation must re-run even when client already validated.
- Additive migrations only. `CharField(default='')` over nullable for optional string fields.
- Atomic per-task commits with `feat(NN-MM): ...` subject convention.

### From v2.1 Trusted Crew Rosters (shipped 2026-05-15)

- `CurrentProjectMiddleware` scoping is the standard — never URL-route project IDs.
- Hidden-from-sidebar pattern: `admin_ordering.py` `always_hidden` set + `order_map` entry both required.

### v2.2 Locked Scope Decisions

1. **`@joint/core` 4.2.4 (MPL-2.0)** is the canvas library — vendored as unmodified UMD bundle; `THIRD_PARTY_LICENSES.txt` required at project root.
2. **`html-to-image` 1.11.11 (MIT)** for PNG export — `format.toPNG()` is JointJS+ (paid) only, must not be used.
3. **Single `JSONField` blob** on `SignalFlowDiagram` — no `DiagramNode`/`DiagramEdge` tables.
4. **GFK-in-JSON** for equipment linking (`content_type_id`, `object_id` inside `canvas_state.cells[]`).
5. **HTML shell + `GET .../state/` JSON endpoint** — no inline JSON in editor template; enables future v2.3 mobile viewer.
6. **Research flag (Phase 8):** Verify `CommandManager` and `Clipboard` availability in `@joint/core` 4.2.4 vs JointJS+ before finalizing undo/redo plans.
7. **System fonts only** on shape/connector labels — cross-origin webfonts taint PNG export canvas.

### Blockers/Concerns

None at roadmap creation.

## Session Continuity

Last session: --stopped-at
Stopped at: Phase 9 context gathered
Resume file: --resume-file

**Planned Phase:** 9 (Autosave & Orphan Rendering) — 4 plans — 2026-05-22T00:44:34.227Z
