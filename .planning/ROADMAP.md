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

## Active Milestone

**Current:** _none — v2.2 just shipped._

The next milestone (v2.3) has not been planned yet. Run `/gsd-new-milestone` to scope it.

### Carried forward from v2.2 (top candidates for v2.3 Phase 1)

These were scoped to v2.2 but never started — recommended as the opening phase of v2.3:

- [ ] **Autocomplete & PNG Export** _(was v2.2 Phase 10)_ — Circuit-label autocomplete endpoint (signal-name fields from all 4 equipment types, project-scoped) + JS autocomplete widget on connector labels + one-click PNG export via the already-vendored `html-to-image` (Phase 7 bundle). Closes LBL-01, LBL-02, LBL-03, EXP-01.

### Backlog ideas (not yet scoped)

_(empty — capture ideas via `/gsd-add-backlog` or `/gsd-plant-seed`)_

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
