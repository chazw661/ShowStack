---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: one-liners
status: completed
stopped_at: Phase 12 context gathered
last_updated: "2026-05-26T01:40:19.633Z"
last_activity: 2026-05-25
progress:
  total_phases: 12
  completed_phases: 11
  total_plans: 57
  completed_plans: 57
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-19)

**Core value:** ShowStack knows your patch, your labels, and your gear; once entered, that data drives every export your show needs.
**Current focus:** Phase 12 — Boundary Lines + Text Annotations (next)

## Current Position

Phase: 12
Plan: Not started
Status: Phase 11 complete; Phase 12 pending discuss/plan
Last activity: 2026-05-25

Progress: [█████████░] Phase 11/12 of v2.3

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
Stopped at: Phase 12 context gathered
Resume file: --resume-file

**Planned Phase:** 11 (Per-Shape Labeled Ports + Resizable Shapes (gap closure)) — 2 plans — 2026-05-24T20:34:04.025Z

## Deferred Items

Acknowledged at v2.2 milestone close on 2026-05-22. All from pre-v2.2 phases that were
already de-facto shipped; deferred rather than reopened because resolution would not
change shipped behavior. Tracked here so future audits do not re-surface as blockers.

| Category | Phase | Item | Status | Note |
|----------|-------|------|--------|------|
| UAT gap | 01 | 01-HUMAN-UAT.md | passed (0 pending) | False positive — UAT closed |
| UAT gap | 03 | 03-HUMAN-UAT.md | resolved (0 pending) | False positive — UAT closed |
| UAT gap | 04 | 04-HUMAN-UAT.md | resolved (0 pending) | False positive — UAT closed |
| UAT gap | 06 | 06-HUMAN-UAT.md | partial (6 pending) | Crew Rosters — shipped in beta, scenarios deferred |
| UAT gap | 08 | 08-HUMAN-UAT.md | resolved (0 pending) | False positive — UAT closed |
| Verification gap | 01 | 01-VERIFICATION.md | human_needed | Carried from v2.0 |
| Verification gap | 03 | 03-VERIFICATION.md | human_needed | Carried from v2.0 |
| Verification gap | 05 | 05-VERIFICATION.md | human_needed | Carried from v2.0 |
| Verification gap | 06 | 06-VERIFICATION.md | human_needed | Carried from v2.1 |
