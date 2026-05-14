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
- [ ] **Phase 4: Nuendo Live Export** - `.nlpr` template-injection exporter with Yamaha→Farb color mapping
- [ ] **Phase 5: Channel Record Defaults** - `default_record` and `default_record_color` seed flags on `ConsoleChannel`

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
- [ ] 04-03-PLAN.md — CHARLIE-OWNED: hand-generate `planner/data/multitrack/nuendo_live_3_template.nlpr` on Windows + Nuendo Live 3 (Wave 1 checkpoint, autonomous=false)
- [x] 04-04-PLAN.md — Test: NuendoLiveExportIdUniquenessTests + minimal fake fixture (Wave 2, depends on 02)
- [ ] 04-05-PLAN.md — View + URL: `multitrack_export_nlpr` + `path('multitrack/<id>/export.nlpr/')` (Wave 2, depends on 02 + 03)
- [x] 04-06-PLAN.md — Atomic three-place form-gate removal: forms.py:1192-1199 + 1209-1217 + new_session.html:72-78 (Wave 2, parallel)
- [ ] 04-07-PLAN.md — Third toolbar button in editor.html (Wave 3, depends on 05)

### Phase 5: Channel Record Defaults
**Goal**: Engineers stop re-ticking the same obvious tracks every gig — channels carry per-channel `default_record` and `default_record_color` seed flags that pre-populate new sessions
**Depends on**: Phase 1
**Requirements**: POL-01, POL-02
**Success Criteria** (what must be TRUE):
  1. Engineer can set `default_record` (boolean) and `default_record_color` (hex) on each `ConsoleChannel` from the channel admin/edit UI
  2. Creating a new MultitrackSession pre-checks (enables) tracks whose source channel has `default_record=True`
  3. New tracks seeded from a channel with `default_record_color` set use that hex as the seed color, while still allowing per-track override afterward
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5
(Phases 2, 3, 4, and 5 each depend only on Phase 1 and could in principle run
in parallel, but solo dev means sequential execution per the spec's order.)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Sessions, Track Editor & Reaper Export | 0/6 | Planned (6 plans, 4 waves) | - |
| 2. Console CSV Import | 0/4 | Planned (4 plans, 3 waves) | - |
| 3. Multitrack Templates | 0/0 | Not started | - |
| 4. Nuendo Live Export | 0/7 | Planned (7 plans, 3 waves) | - |
| 5. Channel Record Defaults | 0/0 | Not started | - |
