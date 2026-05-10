# Phase 1: Core Sessions, Track Editor & Reaper Export — Context

**Gathered:** 2026-05-09
**Status:** Ready for planning

<domain>
## Phase Boundary

End-to-end build of the Multitrack Session Builder module. After this phase, an
engineer can pick any project console, create a `MultitrackSession`, build a
track list in a full-featured editor (drag-reorder, label/color override, bulk
type toggles, manual tracks, capacity warning), and export a working Reaper
`.RPP` (and optional `.RTrackTemplate`).

Carries 21 of the milestone's 38 requirements: MTS-01..06, TRK-01..10,
RPP-01..05.

**Not in this phase:** CSV import (Phase 2), reusable templates (Phase 3),
Nuendo Live export (Phase 4), `default_record` channel seed flags (Phase 5).
</domain>

<decisions>
## Implementation Decisions

### Source-Channel Reference Model

- **D-01:** `MultitrackTrack` references its source via a discriminator pattern,
  not a real FK. Two fields:
  - `source_type` — `CharField(max_length=10, choices=[('input','Input'),('aux','Aux Output'),('matrix','Matrix Output'),('stereo','Stereo Output'),('manual','Manual')])`
  - `source_id` — `PositiveIntegerField(null=True, blank=True)` — null for manual tracks
  No FK constraint, no CASCADE risk to beta data. Resolution happens in a Python
  helper (see D-11 below).
- **D-02:** No FK constraint means orphan rows are possible if a channel is
  deleted. Handled by D-04, not by DB constraints.
- **D-03:** Phase 1 ships exactly four real channel types plus `manual`:
  `input` → `ConsoleInput`, `aux` → `ConsoleAuxOutput`, `matrix` →
  `ConsoleMatrixOutput`, `stereo` → `ConsoleStereoOutput`. Group / FX return /
  Cue output are handled as `manual` tracks for v2.0 (engineer types the label
  by hand). See Deferred Ideas for the v2.1 path.
- **D-04:** When a `ConsoleInput` / `ConsoleAuxOutput` / `ConsoleMatrixOutput` /
  `ConsoleStereoOutput` row is deleted, a `post_delete` signal converts every
  matching `MultitrackTrack` to manual:
  - `source_type='manual'`
  - `source_id=NULL`
  - `label_override` = (existing override) OR last-known channel name
  - `color_override` = (existing override) OR last-known channel color (if any)

  Engineer never silently loses a track row.

### Track Color Storage

- **D-05:** Phase 1 stores color **only** on `MultitrackTrack.color_override`
  (hex `CharField(max_length=7)`). No new color fields on the existing four
  channel models. The editor's swatch picker writes directly to
  `color_override`. Phase 2 CSV import is the natural place to populate
  channel-level colors when those land.
- **D-06:** Resolved-color helper returns `color_override` if set, else the
  Phase 5 `default_record_color` (when that field exists), else `None` (Reaper
  exporter omits color → DAW default).

### Channel Picker UX (TRK-06, TRK-07, TRK-09)

- **D-07:** "Add tracks" opens a modal picker with **type tabs**:
  `[Inputs] [Aux] [Matrix] [Stereo] [Manual]`. Each tab is a checkable list of
  channels filtered to that type. A filter/search box at the top of the modal
  filters the active tab. "Add N selected" commits all checked rows in one
  request.
- **D-08:** TRK-09 bulk toggles live **inside the picker** as per-tab
  "Select all / Clear" header controls — not as a separate sticky row in the
  editor. Single source of truth for set composition.
- **D-09:** Channels already in the session are **hidden** from the picker. The
  picker is strictly an "add" surface. Tab counts reflect remaining channels
  (`Inputs (24 available)`). Removal happens via the editor row's `[×]` button
  per TRK-08.
- **D-10:** New tracks **append to the end** of the track list in the order
  they appear in the picker. Engineer drags to reorder per TRK-05.
- **D-11:** The Manual tab is a small inline form: `Label` (required, max 100),
  `Color` (optional swatch), `Notes` (optional). "+ Add another" queues
  multiple manual tracks before applying. Submitted alongside any other-tab
  selections in the same "Add N selected" commit.

### Session Lifecycle

- **D-12:** A newly-created `MultitrackSession` lands in the editor with **zero
  tracks** and the picker auto-opened on the Inputs tab. Engineer explicitly
  chooses what's in. Pairs cleanly with Phase 5's POL-01 (`default_record`)
  once that lands — the seed becomes the principled "auto-tick the obvious
  ones."
- **D-13:** Spec correction — `MultitrackSession.console` is a `ForeignKey` to
  `planner.Console`, **not** to `Device(category='console')`. The codebase
  model is `Console` (planner/models.py:754); the spec's `Device` reference is
  inaccurate.

### Resolution Helpers (D-11 prerequisite)

- **D-14:** Add Python helpers on `MultitrackTrack`:
  - `resolved_source` — looks up source_type/source_id, returns the right
    model instance or `None`
  - `resolved_label` — `label_override or resolved_source.name or '(untitled)'`
  - `resolved_color` — `color_override or None` (Phase 5 may extend this)
  - `resolved_dante_number` — for `track_order_mode='dante'` rendering and the
    Phase 2 CSV import path

### Claude's Discretion

The planner / executor decides these — defaults to existing project patterns:

- **JS stack** for the track editor. Existing modules use jQuery-flavored JS
  (`comm_admin.js`, `pa_cable_calculations.js`); add Sortable.js (or jQuery UI
  sortable) for TRK-05 drag-reorder. Pick whichever has the smallest footprint.
- **Session creation flow** — wizard vs single form. Spec suggests a 4-step
  wizard; planner may collapse to one form if that matches existing module UX
  better.
- **Reaper `.RPP` color packing** — use Reaper's documented packed-RGB int with
  the high-bit "custom color enabled" flag; confirm exact bit layout against
  Reaper docs / a real `.RPP` fixture.
- **Capacity bar placement** in the editor (sticky top-bar vs inline). Spec
  describes the content; planner finalizes the layout.
- **Track number gap handling** on reorder/delete — renumber on save (`1..N`)
  vs sparse. Either is fine; pick the simpler one.
- **Picker URL form** — same-page modal (HTMX-style or vanilla) vs full
  separate page. Modal is the assumption; planner can adjust.
- **Indexing** on `MultitrackTrack(source_type, source_id)` for the
  `post_delete` lookup performance.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Module Specification

- `multitrack_session_builder_spec.md` — Canonical spec for the entire v2.0
  module. Required reading. Note the codebase deviations captured in D-01,
  D-03, D-13 — the spec assumes a unified `ConsoleChannel` and an `FK(Device)`
  console reference; neither is accurate. Use this CONTEXT.md as the
  authoritative reconciliation.

### Project-Level Conventions

- `.planning/REQUIREMENTS.md` — REQ-ID ledger; Phase 1 owns MTS-01..06,
  TRK-01..10, RPP-01..05.
- `.planning/ROADMAP.md` §"Phase 1" — phase boundary, dependencies, success
  criteria (5 numbered items).
- `.planning/PROJECT.md` §"Context" — architectural non-negotiables:
  `CurrentProjectMiddleware` for project scoping, `showstack_admin_site` for
  admin registration, `BaseEquipmentAdmin` for role-based perms, dark theme
  via `admin/base_site.html`.
- `CLAUDE.md` §"Architecture", §"Deployment" — solo-dev gotchas, `railway.json`
  `startCommand` (NOT Procfile) is the active deploy script.

### Codebase Targets (existing models / files Phase 1 touches)

- `planner/models.py:754` — `Console` model (FK target for
  `MultitrackSession.console`).
- `planner/models.py:777` — `ConsoleInput` (source_type='input').
- `planner/models.py:846` — `ConsoleAuxOutput` (source_type='aux').
- `planner/models.py:870` — `ConsoleMatrixOutput` (source_type='matrix').
- `planner/models.py:888` — `ConsoleStereoOutput` (source_type='stereo').
- `planner/admin_site.py` — register new admins on `showstack_admin_site`.
- `planner/admin_ordering.py` — sidebar grouping; **must update** when new
  admin-registered models land.
- `planner/middleware.py` — `CurrentProjectMiddleware`; views scope queryset
  to `request.current_project`.
- `planner/urls.py` — new module URL lives under `/audiopatch/`.

### Existing Module References (UX precedent)

- Comm Config save/load template UX (`templates/planner/comm_config.html`,
  `CommConfig.is_template + template_name` pattern at planner/models.py:3750)
  — **for Phase 3**, not Phase 1, but planner should glance at it now to
  ensure Phase 1 models leave room for the Phase 3 `MultitrackTemplate`.
- `AudioChecklistTemplate` at planner/models.py:3647 — closest existing analog
  to `MultitrackTemplate` (separate template model rather than `is_template`
  flag). Phase 1 just makes sure the multitrack models are FK-friendly for
  Phase 3.

### External Format Docs (Phase 1 consumes)

- Reaper `.RPP` format — plain text; Reaper's user-guide / Cockos wiki has the
  TRACK / NAME / COLOR / TRACKHEIGHT spec. Spec §"Reaper (.RPP)" summarizes.
- Reaper `.RTrackTemplate` format — same as `.RPP` but track-list only;
  RPP-05.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `Console` model (planner/models.py:754) — FK target for
  `MultitrackSession.console`. Project-scoped already.
- Four channel-source models on the Console:
  - `ConsoleInput` (planner/models.py:777) — has `dante_number`, `input_ch`,
    `source`, `source_hardware`, `group`, `dca`. **No `name` field** — the
    `__str__` falls back to the channel number; resolved_label will need to
    decide whether to use `source` (the channel-name field) or `input_ch`.
    No `color` field.
  - `ConsoleAuxOutput` (planner/models.py:846) — has `name`, no color.
  - `ConsoleMatrixOutput` (planner/models.py:870) — has `name`, no color.
  - `ConsoleStereoOutput` (planner/models.py:888) — has `name` + `stereo_type`,
    no color.
- `showstack_admin_site` (planner/admin_site.py) — register new ModelAdmins
  here, never on `admin.site`.
- `BaseEquipmentAdmin` — extend for role-based filtering on the new admins.
- `CurrentProjectMiddleware` (planner/middleware.py) — `request.current_project`
  is the queryset filter for everything project-scoped.

### Established Patterns

- All planner views scope querysets via `request.current_project`, not URL
  IDs. New `MultitrackSession` views follow this.
- Templates extend `admin/base_site.html` for the dark theme (see e.g.
  `templates/planner/comm_config.html`).
- Existing JS is jQuery-flavored: `planner/static/planner/js/comm_admin.js`,
  `pa_cable_calculations.js`, `mono_stereo_handler.js`. No HTMX or Alpine
  visible. Sticking with jQuery + Sortable.js (or jQuery UI sortable) keeps
  the stack consistent.
- Two template-saving conventions exist: `Console.is_template` (single-flag
  on same model, planner/models.py:759) and `CommConfig.is_template +
  template_name` (planner/models.py:3750-3751). Phase 1 doesn't need either —
  Phase 3 `MultitrackTemplate` is a separate model (closer to
  `AudioChecklistTemplate` at planner/models.py:3647).

### Integration Points

- `planner/models.py` (~4500 lines) — append new models near the existing
  Console family (after line 911 / before `Device` at 913).
- `planner/admin.py` (~6000 lines) — append ModelAdmins; register on
  `showstack_admin_site`.
- `planner/admin_ordering.py` — add a "Multitrack Sessions" group to the
  sidebar.
- `planner/views.py` (~5700 lines) — append the new module's views.
- `planner/urls.py` — add new module URLs under `/audiopatch/multitrack/`
  (or similar).
- `templates/planner/` — new templates; extend `admin/base_site.html`.
- `planner/utils/` — new submodule for the Reaper exporter alongside the
  existing `yamaha_export.py` and `pdf_exports/`.

</code_context>

<specifics>
## Specific Ideas

- "ShowStack knows your patch, your labels, and your gear" (PROJECT.md core
  value). Phase 1 stays additive; no migrations on the four existing channel
  models.
- Beta-tester safety: every Phase 1 migration is creating new tables only.
  No `ALTER TABLE` against `ConsoleInput` / `ConsoleAuxOutput` /
  `ConsoleMatrixOutput` / `ConsoleStereoOutput`. (Per PROJECT.md
  beta-sensitivity constraint.)
- Picker preview the user selected (D-07 layout):
  ```
  ┌── Add Tracks ────────────────────────────┐
  │ [Inputs] [Aux] [Matrix] [Stereo] [+]    │
  │ 🔍 filter…                              │
  │ Inputs (47 available)                   │
  │ ☑  IN 1   Kick In                        │
  │ ☑  IN 2   Kick Out                       │
  │ ☐  IN 3   Snare Top                      │
  │ ☑  IN 4   Snare Bot                      │
  │ [Add 23 selected]   [Cancel]            │
  └─────────────────────────────────────────┘
  ```

</specifics>

<deferred>
## Deferred Ideas

These came up during discussion but belong outside Phase 1.

- **Group Output / FX Return / Cue Output as first-class models** with their
  own admins, CSV import, and `MultitrackTrack.source_type` values. Best home
  is v2.1 alongside the Pro Tools work — both need fresh model design and
  fresh fixtures.
- **Channel-level color storage** on `ConsoleInput` / `ConsoleAuxOutput` /
  `ConsoleMatrixOutput` / `ConsoleStereoOutput`. Revisit during Phase 2 CSV
  import — that's the natural place to populate it from the Yamaha export
  files. Until then, color lives on `MultitrackTrack.color_override`.
- **Default-color seed inheritance from a channel-level `default_record_color`**
  — already on the v2.0 roadmap as POL-02 (Phase 5).
- **Pre-populated session presets** ("Click track / Talkback / Room mics" as
  a one-click manual track preset menu) — explicitly considered for D-11 and
  rejected for v2.0 to keep the manual tab simple.
- **`MultitrackTemplate`** — Phase 3.
- **Pro Tools `.txt` / AAF exporter** — already in REQUIREMENTS.md as PT-01
  (deferred to v2.1 pending tester access).
- **M7CL channel import** — already in REQUIREMENTS.md as M7CL-01 (deferred
  to v2.1 pending CSV path confirmation).

</deferred>

---

*Phase: 01-core-sessions-track-editor-reaper-export*
*Context gathered: 2026-05-09*
