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

- [x] **Phase 10: Autocomplete, PNG Export & New Shape Types** — `signal_flow_autocomplete` extended to surface signal-name fields from all sources (Device, Console, Amp, all 3 Processor types), JS autocomplete widget on connector labels, one-click PNG export via `html-to-image`, plus Processor + Amp smart shape classes with their equipment picker entries. Closes LBL-01..03, EXP-01, SHP-10, SHP-11. (completed 2026-05-23)
  **Plans:** 3 plans
  Plans:
  - [x] 10-01-PLAN.md — Server: label-autocomplete view, extend picker/enrich/IDOR for Amp + SystemProcessor, tests
  - [x] 10-02-PLAN.md — JS + HTML + CSS: Processor + Amp shape classes, sidebar tiles, export button scaffold, CSS sections 12+13
  - [x] 10-03-PLAN.md — JS behavior: autocomplete combobox widget + PNG export handler
- [x] **Phase 11: Per-Shape Labeled Ports + Resizable Shapes** — engineer-authored ports on all 4 edges (Top / Bottom / Left / Right per amended PORT-01) with auto-equal-spacing, dropdown-or-custom labels (consuming Phase 10's autocomplete plumbing via a refactored `attachAutocompleteToInput` factory), corner-handle shape resize via a custom `joint.elementTools.Control` subclass (MPL-2.0 only; `joint.elementTools.Resize` is JointJS+ paid and NOT used) gated by a per-type min-size computed from live port set + label widths, connector snap targeting updated to per-port endpoints with whole-shape v2.2 back-compat (zero authored ports → 4 generic ports preserved). Closes PORT-01..06, SHP-RESIZE-01..03. (completed 2026-05-25)
  **Plans:** 8 plans (6 + 2 gap-closure from browser UAT)
  Plans:
  - [x] 11-01-PLAN.md — Foundation: amend REQUIREMENTS.md PORT-01 (4 edges) + refactor Phase 10 combobox into reusable `attachAutocompleteToInput(inputEl, url, onSelect)` factory
  - [x] 11-02-PLAN.md — Port data model: module-scope helpers (addAuthoredPort, removeAuthoredPortWithSurvival, renameAuthoredPort, redistributeEdgePorts, convertCellFromGenericToAuthored, reanchorLinksFromPort, edgeMidpointInPaperCoords, directionForEdge); D-13 whole-shape back-compat switch; window.__sfd.ports surface
  - [x] 11-03-PLAN.md — Inspector port-authoring UI: 4 per-edge sections with + Add port + trash icon per row; Phase 10 combobox attached to each label input; PORT-05 connector re-anchor via removeWithSurvival; CSS Section 16
  - [x] 11-04-PLAN.md — Canvas label rendering: replace stubs with per-edge portLabelPositionForEdge (top y+14 / bottom y-6 / left x+8 / right x-8) + portLabelMarkupForEdge (11px system fonts); CSS Section 14 (labels always-visible) + Section 7 header amendment
  - [x] 11-05-PLAN.md — Corner-handle resize tool: CornerResize subclass of joint.elementTools.Control (4 corners, snap-then-clamp); computeMinSize + ABSOLUTE_FLOORS table; change:size graph listener for autosave + live re-distribute; CSS Section 15
  - [x] 11-06-PLAN.md — PORT-06 auto-expansion: replace maybeAutoExpand stub with Q7 implementation (Math.ceil snap, top-left anchored, .sfd-toast "Shape resized to fit ports.")
  - [x] 11-07-PLAN.md — Gap closure (JS + backend): per-shape autocomplete scoping (GAP-11.1), authored-port click-magnet visibility (GAP-11.2, BLOCKER), stale-listbox purge (GAP-11.3), Top/Bottom computeMinSize Σ(label widths) (GAP-11.5)
  - [x] 11-08-PLAN.md — Gap closure (CSS-only): align .sfd-port-label-input colors with Section 4 inspector-input pattern so port-row text is readable on dark navy (GAP-11.4)
- [x] **Phase 12: Boundary Lines + Text Annotations** — toolbar boundary-draw mode with color + style picker (solid/dashed/dotted/double), inspector edit for selected boundary lines, freeform text labels with font-size + color, full integration with the autosave + undo + 409 + keepalive paths from v2.2. Closes DRAW-01..04, TXT-01..03. (2026-05-26)
  **Plans:** 7 plans
  Plans:
  - [x] 12-01-PLAN.md — JS cell-class registration: BoundaryLine + TextLabel + applyBoundaryRender + palette/style constants (Wave 1)
  - [x] 12-02-PLAN.md — CSS Sections 17 (DRAW) + 18 (TXT) skeleton + section-list update (Wave 1)
  - [x] 12-03-PLAN.md — Toolbar create-tools group + draw-boundary pen-tool state machine + rubber-band guard + Esc commit/cancel (Wave 2)
  - [x] 12-04-PLAN.md — Place-text mode + inline-edit overlay + dblclick re-entry + pan/zoom force-commit (Wave 3)
  - [x] 12-05-PLAN.md — Inspector boundary-mode + text-mode panels: color swatches, line-style + font-size segmented, setInspectorMode branches (Wave 4)
  - [x] 12-06-PLAN.md — BoundaryVertex elementTools.Control + attachBoundaryVertexTools + onSelectionChanged branches + change:vertices listener (Wave 5)
  - [x] 12-07-PLAN.md — Regression tests for IDOR pass-through + canvas_state opacity (R-04, R-13, R-14) (Wave 1 — independent)

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
| 10. Autocomplete, PNG Export & New Shape Types | v2.3 | 3/3 | Complete    | 2026-05-23 |
| 11. Per-Shape Labeled Ports + Resizable Shapes | v2.3 | 8/8 | Complete    | 2026-05-25 |
| 12. Boundary Lines + Text Annotations | v2.3 | 0/7 | Not started | — |
