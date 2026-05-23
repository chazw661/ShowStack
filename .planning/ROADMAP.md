# ShowStack Roadmap

## Shipped Milestones

| Version | Name | Phases | Shipped | Archive |
|---------|------|--------|---------|---------|
| v2.0 | Multitrack Session Builder | 1–5 | 2026-05-14 | _(pre-dates milestone-close workflow)_ |
| v2.1 | Collaboration & User Management | 6 | 2026-05-15 | _(pre-dates milestone-close workflow)_ |
| **v2.2** | **Signal Flow Diagrammer** | **7–9** | **2026-05-22** | [`milestones/v2.2-ROADMAP.md`](./milestones/v2.2-ROADMAP.md) |

### v2.0 one-liners (for context)

- [x] **Phase 1: Core Sessions, Track Editor & Reaper Export** — multitrack session model + full track editor + `.RPP` / `.RTrackTemplate` export (2026-05-13)
- [x] **Phase 2: Console CSV Import** — Yamaha CL/QL + Rivage PM channel-label CSV ingestion (2026-05-13)
- [x] **Phase 3: Multitrack Templates** — reusable session structures (2026-05-13)
- [x] **Phase 4: Nuendo Live Export** — `.nlpr` template-injection exporter with Yamaha→Farb color mapping (2026-05-14)
- [x] **Phase 5: Channel Record Defaults** — `default_record` + `default_record_color` seed flags (2026-05-14)

### v2.1 one-liners

- [x] **Phase 6: Trusted Crew Rosters** — owner-defined named groups that auto-attach to projects without email acceptance (2026-05-15)

### v2.2 one-liners ← see `milestones/v2.2-ROADMAP.md` for full detail

- [x] **Phase 7: Foundation, CRUD & Editor Shell** — `SignalFlowDiagram` model + admin + 9 views/URLs with IDOR guards + JointJS vendor bundle + editor shell (2026-05-20)
- [x] **Phase 8: Canvas, Smart Shapes & Connectors** — full JointJS canvas (pan/zoom/snap/undo/multi-select/delete + viewport restore), 5 smart shape classes with equipment picker, typed orthogonal connectors with 5 signal styles (2026-05-21)
- [x] **Phase 9: Autosave & Orphan Rendering** — debounced autosave + If-Match 409 banner + keepalive flush + `_enrich_nodes()` label propagation + ghost rendering for deleted equipment + node-mode Re-link/Delete (2026-05-22)

---

## Active Milestone: v2.3 Signal Flow Diagrammer Export & Enhancements

**Driver:** Issue #14 + carried scope from v2.2 Phase 10
**Defined:** 2026-05-22

**Goal:** Close the v2.2 deferred scope (autocomplete + PNG export) and ship the engineer-requested Signal Flow Diagrammer power-user features from issue #14: per-shape labeled ports with project-scoped autofill, resizable shapes, two new smart shape types (Processor + Amp), freeform boundary lines, and freeform text annotations.

### v2.3 Phases

Phase numbering continues from v2.2 (next integer is 10). Build order is dependency-driven: data-model + autocomplete plumbing first (Phase 10), then the shape/port UX that depends on the autocomplete (Phase 11), then the canvas-decoration primitives that don't depend on shapes (Phase 12), then export which needs everything else rendered (Phase 13).

- [ ] **Phase 10: Autocomplete, PNG Export & New Shape Types** — `signal_flow_autocomplete` extended to surface signal-name fields from all sources (Device, Console, Amp, all 3 Processor types), JS autocomplete widget on connector labels, one-click PNG export via `html-to-image`, plus Processor + Amp smart shape classes with their equipment picker entries. Closes LBL-01..03, EXP-01, SHP-10, SHP-11.
- [ ] **Phase 11: Per-Shape Labeled Ports + Resizable Shapes** — engineer-authored ports on top/left/right edges with auto-equal-spacing, dropdown-or-custom labels (consuming Phase 10's autocomplete plumbing), corner-handle shape resize gated by a per-type min-size, connector snap targeting updated to per-port endpoints. Closes PORT-01..06, SHP-RESIZE-01..03.
- [ ] **Phase 12: Boundary Lines + Text Annotations** — toolbar boundary-draw mode with color + style picker (solid/dashed/dotted/double), inspector edit for selected boundary lines, freeform text labels with font-size + color, full integration with the autosave + undo + 409 + keepalive paths from v2.2. Closes DRAW-01..04, TXT-01..03.

### Carried decisions (still in force)

- State lives in the existing `SignalFlowDiagram.canvas_state` `JSONField` blob — no schema migration on `SignalFlowDiagram` itself.
- Resizable applies to ALL shape types (including v2.2's existing 5), not just the new Processor + Amp shapes.
- Autocomplete sources include all v2.2-scoped fields plus the new Amp + Processor I/O label fields.

### Backlog ideas (not yet scoped — capture via `/gsd-add-backlog` or `/gsd-plant-seed`)

_(empty)_

---

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. Core Sessions, Track Editor & Reaper Export | v2.0 | 6/6 | ✅ Complete | 2026-05-13 |
| 2. Console CSV Import | v2.0 | 4/4 | ✅ Complete | 2026-05-13 |
| 3. Multitrack Templates | v2.0 | 5/5 | ✅ Complete | 2026-05-13 |
| 4. Nuendo Live Export | v2.0 | 7/7 | ✅ Complete | 2026-05-14 |
| 5. Channel Record Defaults | v2.0 | 3/3 | ✅ Complete | 2026-05-14 |
| 6. Trusted Crew Rosters | v2.1 | 7/7 | ✅ Complete | 2026-05-15 |
| 7. Foundation, CRUD & Editor Shell | v2.2 | 4/4 | ✅ Complete | 2026-05-20 |
| 8. Canvas, Smart Shapes & Connectors | v2.2 | 6/6 | ✅ Complete | 2026-05-21 |
| 9. Autosave & Orphan Rendering | v2.2 | 4/4 | ✅ Complete | 2026-05-22 |
| 10. Autocomplete, PNG Export & New Shape Types | v2.3 | 0/TBD | Not started | — |
| 11. Per-Shape Labeled Ports + Resizable Shapes | v2.3 | 0/TBD | Not started | — |
| 12. Boundary Lines + Text Annotations | v2.3 | 0/TBD | Not started | — |
