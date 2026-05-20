# Roadmap: ShowStack v2.0 — Multitrack Session Builder

## Overview

Five phases convert ShowStack console channel data into ready-to-use multitrack
recording sessions for Reaper and Nuendo Live. Phase ordering is taken from the
canonical spec (`multitrack_session_builder_spec.md`) and is deliberate:

1. **Phase 1** ships the core data model, the full track editor, and the Reaper
   exporter together. Reaper's `.RPP` is plain text and the easiest format to
   validate; the track editor is the user-visible heart of the module, so it
   must work end-to-end before any importer or second exporter goes in.
2. **Phase 2** layers CSV import on top of an editor that already works, so the
   importer's job is reduced to populating ShowStack's existing `ConsoleChannel`
   records — no new editor UX needed.
3. **Phase 3** adds reusable `MultitrackTemplate`s only after sessions exist to
   save *from*. Matching ShowStack's existing template UX (Comm Config, Mic
   Tracker) is required, not a stretch goal.
4. **Phase 4** ships the Nuendo Live `.nlpr` exporter — highest-risk format
   (XML template injection via `lxml`, opaque IDs and Farb palette indices),
   so it lands last of the major work, after the core flow is proven.
5. **Phase 5** is a small-surface polish pass adding `default_record` and
   `default_record_color` to `ConsoleChannel` so engineers don't re-tick the
   obvious tracks every gig.

Coarse granularity (per `.planning/config.json`); 5 phases sits at the upper
end of that band but is justified because each phase delivers an independently
verifiable user capability and the spec's phase boundaries hold up against the
requirement dependencies.

### Note on requirement-to-phase placement vs spec wording

The spec's "Phase 5 — Polish" bullet list mentions drag-reorder, capacity bar,
color picker, and bulk toggles. Those are written into REQUIREMENTS.md as
first-class track-editor behaviors (TRK-04, TRK-05, TRK-09, TRK-10). They
belong with the Phase 1 track editor — the editor is not "done" without them
from the user's perspective. Phase 5 is therefore narrowed to the only
genuinely channel-model-level seed work: `default_record` and
`default_record_color` (POL-01, POL-02).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4, 5): Planned milestone work
- Decimal phases (e.g. 2.1): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Core Sessions, Track Editor & Reaper Export** - Models, full track editor, and `.RPP` / `.RTrackTemplate` export
- [ ] **Phase 2: Console CSV Import** - Yamaha CL/QL and Rivage PM channel-label CSV ingestion into `ConsoleChannel`
- [x] **Phase 3: Multitrack Templates** - Save/apply reusable session structures, matching existing ShowStack template UX
- [x] **Phase 4: Nuendo Live Export** - `.nlpr` template-injection exporter with Yamaha→Farb color mapping (completed 2026-05-14)
- [x] **Phase 5: Channel Record Defaults** - `default_record` and `default_record_color` seed flags on `ConsoleChannel` (code-complete 2026-05-14)

---

## v2.1 — Collaboration & User Management

- [x] **Phase 6: Trusted Crew Rosters** - Owner-defined named groups of users that get auto-added to projects without email acceptance (closes friction for repeat collaborators)

---

## v2.2 — Signal Flow Diagrammer

- [ ] **Phase 7: Foundation, CRUD & Editor Shell** - `SignalFlowDiagram` model, migration, admin, list/create/rename/delete views, all URL patterns, and the HTML editor shell with vendored JointJS
- [ ] **Phase 8: Canvas, Smart Shapes & Connectors** - JointJS canvas init, five smart shape classes with equipment picker modal, five connector signal-type variants with port snapping, all canvas UX (pan/zoom/snap/undo/multi-select/delete/viewport restore)
- [ ] **Phase 9: Autosave & Orphan Rendering** - Debounced JSON autosave with race-condition guards, save-status indicator, HTTP 409 conflict banner, keepalive on unload, and server-side `_enrich_nodes()` for ghosted orphan rendering
- [ ] **Phase 10: Autocomplete & PNG Export** - Circuit-label autocomplete endpoint (all signal-name fields, project-scoped), JS autocomplete widget on connector labels, and one-click PNG export via `html-to-image`

## Phase Details

### Phase 1: Core Sessions, Track Editor & Reaper Export
**Goal**: Engineer can build a multitrack session from any project console's existing channel data and export a working Reaper project file
**Depends on**: Nothing (first phase)
**Requirements**: MTS-01, MTS-02, MTS-03, MTS-04, MTS-05, MTS-06, TRK-01, TRK-02, TRK-03, TRK-04, TRK-05, TRK-06, TRK-07, TRK-08, TRK-09, TRK-10, RPP-01, RPP-02, RPP-03, RPP-04, RPP-05
**Success Criteria** (what must be TRUE):
  1. Engineer lands on the Multitrack Session Builder page, sees all sessions for the current project, and can create, duplicate, rename, or delete one
  2. In the track editor, the engineer can include input channels, Aux outputs, Matrix outputs, Group outputs, FX returns, and Cue outputs as tracks; bulk-toggle Aux/Matrix/Group sections; add a manual track with no source channel; and remove any track without affecting the underlying console channel
  3. Engineer can override per-track label and color, drag-reorder the track list, enable/disable individual tracks, and see a "47 / 64" count vs `recorder_capacity` (turning red when over)
  4. Engineer clicks "Export to Reaper" and downloads a `.RPP` (and optionally `.RTrackTemplate`) where track names match the resolved labels, track colors match the resolved colors mapped to Reaper packed RGB, and the track order matches the session's `track_order_mode`
  5. Opening the exported `.RPP` in Reaper produces a project with one track per enabled MultitrackTrack, no errors, names and colors as configured
**Plans**: 6 plans
- [x] 01-01-PLAN.md — Foundation: models, migration, signals, admin, admin_ordering (Wave 1)
- [x] 01-02-PLAN.md — Reaper exporter utility (Wave 2, parallel-safe)
- [x] 01-03-PLAN.md — Forms + page-render views + URL stubs (Wave 2)
- [x] 01-04-PLAN.md — AJAX endpoints + Reaper export views (Wave 3)
- [x] 01-05-PLAN.md — Templates: dashboard, editor, new_session + four partials (Wave 4)
- [x] 01-06-PLAN.md — JS controller + Sortable.js vendor + multitrack.css (Wave 4, parallel with 05)
**UI hint**: yes

### Phase 2: Console CSV Import
**Goal**: Engineer can populate or update a console's channel list from a Yamaha CL/QL or Rivage PM CSV export, then immediately use those channels as track sources in the editor built in Phase 1
**Depends on**: Phase 1
**Requirements**: CSV-01, CSV-02, CSV-03, CSV-04, CSV-05
**Success Criteria** (what must be TRUE):
  1. Engineer uploads a Yamaha CL/QL channel-name CSV (Studio Manager / CL Editor / Console File Converter) and the channels populate or update on the matching console in ShowStack
  2. Engineer uploads a Yamaha Rivage PM channel-labels CSV and the channels populate or update on the matching console
  3. Before commit, the engineer sees a per-row diff summary (created vs updated vs unchanged) and any per-row errors (missing fields, unsupported color codes) without the entire import aborting
  4. After a successful import, the engineer lands directly in the session editor with the imported channels available as track sources
**Plans**: 4 plans
- [x] 02-01-PLAN.md — Schema foundation: YAMAHA_COLOR_CHOICES + color field on 4 channel models, ConsoleImport model, migration 0153, admin + ordering (Wave 1)
- [x] 02-02-PLAN.md — Pure-function parser utility + parser unit tests + test fixtures (Wave 1, parallel with 01)
- [x] 02-03-PLAN.md — Upload form, three views (upload/preview/commit), URL routes (Wave 2)
- [x] 02-04-PLAN.md — Templates (upload, preview, dashboard CTA) + end-to-end view integration tests (Wave 3)

### Phase 3: Multitrack Templates
**Goal**: Engineer can save a working session's structure as a reusable template scoped to the engineer's account (owner-scoped per D-05) and apply it to seed new sessions on any console
**Depends on**: Phase 1
**Requirements**: TPL-01, TPL-02, TPL-03, TPL-04
**Success Criteria** (what must be TRUE):
  1. Engineer saves the current session's structure (target DAW, feed source, track-order mode, plus a slot list keyed by cross-console portable `(source_type, source_number)` pairs) as a named `MultitrackTemplate` owned by the engineer
  2. Engineer applies a template to a new session and the track list and metadata are seeded; per-track values can still be overridden afterward
  3. Engineer can list, rename, and delete templates from the module landing page
  4. The save/load buttons, placement, and modal behavior visually and behaviorally match the existing ShowStack template patterns (Comm Config, Mic Tracker)
**Plans**: 5 plans
- [x] 03-01-PLAN.md — Models + migration: `MultitrackTemplate` + `MultitrackTemplateSlot` + `apply_to_session` + `_summarise_skipped_slots` + migration 0154 (Wave 1)
- [x] 03-02-PLAN.md — Admin registration + admin_ordering (Wave 2)
- [x] 03-03-PLAN.md — JSON endpoints: save / rename / delete + URL routes (Wave 2)
- [x] 03-04-PLAN.md — Form integration: `MultitrackSessionForm.template` ModelChoiceField (Wave 2)
- [x] 03-05-PLAN.md — UI: dashboard Templates section, editor "Save as Template" button, new_session dropdown, JS (Wave 3)

### Phase 4: Nuendo Live Export
**Goal**: Engineer can export the current session as a Nuendo Live 3 `.nlpr` file that opens cleanly with correct names and palette colors
**Depends on**: Phase 1
**Requirements**: NLP-01, NLP-02, NLP-03, NLP-04, NLP-05, NLP-06
**Success Criteria** (what must be TRUE):
  1. Engineer clicks "Export to Nuendo Live" and downloads a `.nlpr` produced by the bundled empty-template injection path (no from-scratch synthesis)
  2. Opening the exported `.nlpr` in Nuendo Live 3 succeeds with no errors and shows one track per enabled MultitrackTrack
  3. Each track's outer `Name` and inner `DeviceAttributes → Name → String` render the resolved track label correctly inside Nuendo Live
  4. Tracks with an assigned color render using the correct Farb palette index per the Yamaha→Nuendo mapping table; tracks with no assigned color render in Nuendo Live's default appearance (Farb omitted)
  5. Every `ID` and `RuntimeID` in the exported document is unique within that document
**Plans**: 7 plans
- [x] 04-01-PLAN.md — Deps + `MultitrackTrack.resolved_yamaha_name` @property (Wave 1)
- [x] 04-02-PLAN.md — `planner/utils/nuendo_live_export.py` pure exporter: YAMAHA_TO_FARB, build_nlpr, all helpers (Wave 1, parallel-safe)
- [x] 04-03-PLAN.md — CHARLIE-OWNED: hand-generated `planner/data/multitrack/nuendo_live_3_template.nlpr` on Mac + Nuendo Live 3 (Wave 1 checkpoint, autonomous=false)
- [x] 04-04-PLAN.md — Test: NuendoLiveExportIdUniquenessTests + minimal fake fixture (Wave 2, depends on 02)
- [x] 04-05-PLAN.md — View + URL: `multitrack_export_nlpr` + `path('multitrack/<id>/export.nlpr/')` (Wave 2, depends on 02 + 03)
- [x] 04-06-PLAN.md — Atomic three-place form-gate removal: forms.py:1192-1199 + 1209-1217 + new_session.html:72-78 (Wave 2, parallel)
- [x] 04-07-PLAN.md — Third toolbar button in editor.html (Wave 3, depends on 05)

### Phase 5: Channel Record Defaults
**Goal**: Engineers stop re-ticking the same obvious tracks every gig — channels carry per-channel `default_record` and `default_record_color` seed flags that pre-populate new sessions
**Depends on**: Phase 1
**Requirements**: POL-01, POL-02
**Success Criteria** (what must be TRUE):
  1. Engineer can set `default_record` (boolean) and `default_record_color` (hex) on each `ConsoleChannel` from the channel admin/edit UI
  2. Creating a new MultitrackSession pre-checks (enables) tracks whose source channel has `default_record=True`
  3. New tracks seeded from a channel with `default_record_color` set use that hex as the seed color, while still allowing per-track override afterward
**Plans**: 3 plans
- [x] 05-01-PLAN.md — Model fields + migration 0155 on all 4 ConsoleChannel models (Wave 1)
- [x] 05-02-PLAN.md — Admin form surface: expose default_record + default_record_color on 4 channel ModelForms with hex validator (Wave 2, depends on 05-01)
- [x] 05-03-PLAN.md — Seed logic in multitrack_add_tracks + regression test suite (Wave 2, depends on 05-01, parallel with 05-02)
**UI hint**: yes

---

### Phase 6: Trusted Crew Rosters
**Milestone**: v2.1 (Collaboration & User Management) — first phase
**Goal**: Owner can define named crew rosters (e.g. "Concert team", "Corporate team") and bulk-add an entire crew to a project as ProjectMembers without the email-acceptance round-trip
**Depends on**: Existing `accounts` app invitation flow (planner.Invitation, ProjectMember)
**Requirements**: SPEC-06-R01, SPEC-06-R02, SPEC-06-R03, SPEC-06-R04, SPEC-06-R05, SPEC-06-R06, SPEC-06-R07, SPEC-06-R08
**Plans**: 7 plans
- [x] 06-01-models-migration-PLAN.md — Crew + CrewMember + CrewProjectAdd models + migration 0157 (Wave 1)
- [x] 06-02-admin-registration-PLAN.md — Register Crew/CrewMember/CrewProjectAdd on showstack_admin_site + admin_ordering update (Wave 2, depends on 06-01)
- [x] 06-03-crud-views-urls-templates-PLAN.md — Crew CRUD views + URLs + crew_index/crew_detail templates (Wave 2, depends on 06-01)
- [x] 06-04-bulk-add-email-invite-panel-PLAN.md — bulk_add_crew view + send_crew_added_email + additive invite_user.html panel (Wave 3, depends on 06-01 + 06-03)
- [x] 06-05-auto-claim-register-hook-PLAN.md — planner/crew.py claim helper + atomic wrap in register() (Wave 3, depends on 06-01)
- [x] 06-06-nav-link-PLAN.md — Additive "My Crew" link in admin base_site.html + dashboard.html (Wave 3, depends on 06-03)
- [x] 06-07-tests-PLAN.md — planner/tests/test_crew_rosters.py covering all 8 SPEC requirements + D-15 constraints (Wave 4, depends on 06-01..06-06)
**UI hint**: yes

---

### Phase 7: Foundation, CRUD & Editor Shell
**Milestone**: v2.2 (Signal Flow Diagrammer)
**Goal**: Engineer can navigate to a project's signal-flow diagram list, create a named diagram, rename and delete it, and open the diagram editor page — with the JointJS vendor bundle loaded and the blank canvas div present in the DOM, ready for canvas initialization in Phase 8
**Depends on**: Phase 6 (v2.1 closed; model pattern established)
**Requirements**: DGM-01, DGM-02, DGM-03, DGM-04, DGM-05, DGM-08
**Success Criteria** (what must be TRUE):
  1. Engineer navigates to `/audiopatch/signal-flow/` and sees all diagrams for the current project (name, last-modified); page shows empty state with a "New Diagram" prompt when no diagrams exist
  2. Engineer creates a diagram by entering a name; the diagram is scoped to the current project and any attempt to access it from a different project returns 404
  3. Engineer can rename a diagram inline on the list page; the name is unique per project and a duplicate name returns a clear error
  4. Engineer can delete a diagram from the list page; the row is removed immediately with no orphaned data
  5. Opening a diagram navigates to the editor page; the browser console shows no 404 errors on JS/CSS assets and `joint` is available on `window`
**Plans**: 4 plans
- [x] 07-01-model-migration-admin-PLAN.md — SignalFlowDiagram model + migration 0158 + admin + admin_ordering (Wave 1)
- [x] 07-02-vendor-js-licensing-PLAN.md — Vendor joint.min.js + html-to-image.min.js + THIRD_PARTY_LICENSES.txt + PROJECT.md MIT->MPL-2.0 correction (Wave 1, parallel with 07-01)
- [x] 07-03-views-urls-PLAN.md — 9 view functions + 9 URL patterns + IDOR/viewer guards (Wave 2, depends on 07-01)
- [x] 07-04-templates-editor-shell-PLAN.md — list.html + editor.html + signal_flow_editor.js stub + dashboard quick-action link (Wave 3, depends on 07-01/02/03)
**UI hint**: yes

### Phase 8: Canvas, Smart Shapes & Connectors
**Milestone**: v2.2 (Signal Flow Diagrammer)
**Goal**: Engineer can draw a complete signal-flow diagram on a live JointJS canvas — dropping smart shapes linked to ShowStack Console, Device, SpeakerArray, and CommBeltPack records (plus a free-label Generic shape), connecting them with typed orthogonal connectors, and using the full canvas UX: pan, zoom, snap-to-grid, undo/redo, multi-select, keyboard delete, and viewport persistence
**Depends on**: Phase 7
**Requirements**: CNV-01, CNV-02, CNV-03, CNV-04, CNV-05, CNV-06, CNV-07, CNV-08, SHP-01, SHP-02, SHP-03, SHP-04, SHP-05, SHP-08, SHP-09, CON-01, CON-02, CON-03, CON-04, CON-05, CON-06
**Success Criteria** (what must be TRUE):
  1. Engineer drags a shape from the sidebar picker (Console, Device, SpeakerArray, CommBeltPack, Generic) onto the canvas and the shape lands at the cursor position accounting for scroll and zoom; equipment picker modal lists only records belonging to the current project
  2. Engineer pans via space+drag or middle-click, zooms via toolbar buttons (zoom-to-fit included), and toggles snap-to-grid — all without disrupting the canvas state; reopening the diagram restores the previous viewport position and zoom level
  3. Engineer performs Ctrl+Z / Ctrl+Shift+Z and changes undo and redo correctly; engineer shift-clicks or rubber-band-selects multiple nodes; pressing Delete or Backspace removes the selection
  4. Engineer drags from an output port to an input port and a connector appears; connector rejects mid-shape drops; engineer sets signal type from the 5-option dropdown (analog / AES / Dante / MADI / intercom) and each type renders with a distinct line style and dash pattern
  5. Engineer drags a midpoint waypoint to route a connector manually; engineer sets connector direction to bidirectional; each connector carries a circuit-label string that renders along the line
**Plans**: TBD
**UI hint**: yes

**Research flag (Phase 8):** Verify JointJS `Clipboard` and `CommandManager` availability in `@joint/core` 4.2.4 vs JointJS+ before finalizing undo/redo and any future copy/paste plans. Confirm during plan-phase research step.

### Phase 9: Autosave & Orphan Rendering
**Milestone**: v2.2 (Signal Flow Diagrammer)
**Goal**: Canvas changes persist automatically without the engineer thinking about saving — the editor shows live save status, handles tab-conflict and page-unload edge cases correctly, and shows ghosted shapes for equipment records deleted since the diagram was last edited
**Depends on**: Phase 8
**Requirements**: DGM-06, DGM-07, DGM-08, SHP-06, SHP-07
**Success Criteria** (what must be TRUE):
  1. Engineer edits the canvas and within 2.5 seconds a POST to the save endpoint fires; the editor shows "Saving..." then "Saved"; a failed save shows "Failed — retry" persistently
  2. Engineer opens the same diagram in a second tab and makes an edit; the losing tab's next save returns HTTP 409 and a non-dismissable banner reads "Diagram was modified elsewhere — reload to see latest"
  3. Engineer navigates away with unsaved changes; a keepalive fetch fires on `visibilitychange`/`pagehide` and the latest state is persisted on the server
  4. Engineer renames a piece of linked equipment, then reloads the diagram; the shape label reflects the new name without any manual update
  5. Engineer deletes a piece of linked equipment, then reloads the diagram; the affected shape renders ghosted (dashed border, muted style) with its last-known label preserved — the canvas does not crash

**Note on DGM-08 overlap:** DGM-08 (keepalive on tab close) was seeded in Phase 7 as a URL/view stub but its behavioral requirement (the actual keepalive fetch) is delivered here in Phase 9 alongside the full autosave system.
**Plans**: TBD

### Phase 10: Autocomplete & PNG Export
**Milestone**: v2.2 (Signal Flow Diagrammer)
**Goal**: Engineer can label connectors using autocomplete suggestions drawn from the project's existing signal-name fields (no manual lookup), and can export the finished diagram as a PNG file in one click
**Depends on**: Phase 9 (canvas must be populated and autosaving for export to be meaningful)
**Requirements**: LBL-01, LBL-02, LBL-03, EXP-01
**Success Criteria** (what must be TRUE):
  1. Typing in a connector's circuit-label field surfaces autocomplete suggestions from `DeviceInput.signal_name`, `DeviceOutput.signal_name`, `ConsoleInput.source`, and `ConsoleAuxOutput.name` — all scoped to the current project; cross-project signals never appear
  2. Engineer can override autocomplete and type any free-text string; the connector accepts it without validation error
  3. Engineer clicks "Export PNG" and downloads a PNG with a white background that captures the full canvas (not just the visible viewport), with correct system-font label rendering and no cross-origin taint errors
**Plans**: TBD

---

## Progress

**Execution Order:**
v2.0 phases: 1 → 2 → 3 → 4 → 5
v2.1 phase: 6
v2.2 phases: 7 → 8 → 9 → 10

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Core Sessions, Track Editor & Reaper Export | v2.0 | 6/6 | Complete | 2026-05-13 |
| 2. Console CSV Import | v2.0 | 4/4 | Complete | 2026-05-13 |
| 3. Multitrack Templates | v2.0 | 5/5 | Complete | 2026-05-13 |
| 4. Nuendo Live Export | v2.0 | 7/7 | Complete | 2026-05-14 |
| 5. Channel Record Defaults | v2.0 | 3/3 | Complete | 2026-05-14 |
| 6. Trusted Crew Rosters | v2.1 | 7/7 | Complete | 2026-05-15 |
| 7. Foundation, CRUD & Editor Shell | v2.2 | 0/TBD | Not started | - |
| 8. Canvas, Smart Shapes & Connectors | v2.2 | 0/TBD | Not started | - |
| 9. Autosave & Orphan Rendering | v2.2 | 0/TBD | Not started | - |
| 10. Autocomplete & PNG Export | v2.2 | 0/TBD | Not started | - |
