# Phase 2: Console CSV Import — Context

**Gathered:** 2026-05-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Engineer can populate or update a console's channel-name and color data from a Yamaha CL/QL or Rivage PM Editor CSV export. After import, channels are immediately available as track sources in the Phase 1 Multitrack Session Builder.

**In scope:** Channel-name + color import for inputs and outputs. Per-row diff preview before commit. Per-row error reporting without aborting the whole import. Immutable snapshot of every uploaded file (`ConsoleImport` record).

**Out of scope:** Patch-section import (`[InPatch]`, `[OutPatch]`, `[PortRackPatch]`) — defer to a later phase. DM7 Editor support — defer until an export path is identified. M7CL — already deferred to v2.1 in REQUIREMENTS.md.

</domain>

<decisions>
## Implementation Decisions

### Scope & Sections (locked from prior conversation)

- **L-01:** Import the channel-name sections only — `[InName]`, `[StName]`, `[MixName]`, `[MtxName]` plus CL/QL's `[StMonoName]` and `[DCAName]`, plus Rivage's output equivalents. **Patch sections explicitly deferred** to a later phase. Rationale: engineers track stems off auxes and matrices, so output names need to land in Phase 2; patch routing is a separate problem.
- **L-02:** New `ConsoleImport` model — immutable snapshot of the uploaded file plus its parsed channel data. Project → Console → many `ConsoleImport` records. The console can drift from any single import after the fact (engineer edits in ShowStack); the import record stays as audit history and re-apply source.
- **L-03:** User picks a target Console in the current project before uploading. Import populates that console's channels — does NOT auto-create a new console.
- **L-04:** Auto-detect console family from the `[Information]` block (CL5 / QL5 / CS-R5/DSP-RX). Block import if it doesn't match the selected target (see D-03).
- **L-05:** Color storage uses the Yamaha palette names — already declared in `planner/utils/reaper_export.py:YAMAHA_TO_HEX`. The exporter explicitly states *"Phase 2 CSV import populates channel-level Yamaha colors and resolves through this table."* Phase 2 ships the storage half; the resolution half already exists.
- **L-06:** DM7 deferred (no obvious CSV export from DM7 Editor); M7CL deferred to v2.1 per REQUIREMENTS.md.

### Update vs Replace Semantics

- **D-01:** **Smart-skip defaults.** If a CSV row matches the console's factory default (e.g., `_01,ch 1,Blue,Dynamic,`), treat it as "no real edit" and do NOT overwrite the corresponding ShowStack channel. Only import rows where the engineer actually changed something on the physical console. Preserves user-typed labels in ShowStack with no clicks.
  - **Default-row detection rule:** A row is "default" iff *all* of the following are true:
    - `NAME` matches `ch ?N` where N matches the channel number (e.g. `ch 1` for `_01`, `ch10` for `_10`)
    - `COLOR` is `Blue`
    - `ICON` is `Dynamic`
  - Per-section defaults for output sections (Mix/Mtx/St/DCA): planner derives the canonical defaults from the blank fixtures in `planner/data/csv_fixtures/`.

- **D-02:** **True conflicts (CSV and ShowStack both customized, both differ) surface in the diff preview.** Default behavior: CSV wins. UI: every conflict row appears in the diff with a checkbox; engineer can untick rows to keep the ShowStack value. Default-checked = engineer can commit with one click if CSV-wins is correct for all conflicts.

### Model-Mismatch Handling

- **D-03:** **Block with error** if the CSV `[Information]` block reports a console family that doesn't match the selected target's family. Show: *"This CSV is from a `<file_model>` console. The selected target is a `<target_model>`. Pick a `<file_model>` console or change the target."* Prevents silently importing 288 Rivage rows into a 64-channel QL5.

### Diff Preview UX

- **D-04:** **Stats summary at top + filter to changed rows.** Top-line counts: `Created · Updated · Conflicts · Unchanged · Errors`. Below: a row table showing only the rows that aren't `Unchanged` (typically ~25 rows even for a 288-channel Rivage import). Filter chips to toggle `Show unchanged` / `Errors only`. Conflict rows have the checkbox from D-02. Errors are non-blocking — they appear in the table with the error reason and a `Skip` indicator; the rest of the import proceeds on commit.

### Upload Entry & Post-Import Landing

- **D-05:** **Upload UI lives on the Multitrack module landing page** (`/audiopatch/multitrack/`). One "Import Console CSV" button. Engineer picks the target console from a dropdown of project consoles, uploads the file, lands on the diff preview page, commits, lands back on the Multitrack list (D-06).
- **D-06:** **After successful import, land on `/audiopatch/multitrack/`** with a success banner: *"Import complete — N channels imported."* Plus the existing "+ New Session" CTA. Satisfies CSV-05 ("user lands in session editor with the imported channels available as track sources") without forcing session creation — the engineer can immediately hit `+ New Session` and the imported channels are already there as track sources.

### Schema Changes (additive migration)

- **D-07:** Phase 2 ships a migration adding a `color` field to:
  - `ConsoleInput` — currently has no color field.
  - `ConsoleAuxOutput` — currently has no color field.
  - `ConsoleMatrixOutput` — currently has no color field.
  - `ConsoleStereoOutput` — currently has no color field.

  Field type: `CharField(max_length=20, choices=YAMAHA_COLOR_CHOICES, default='Blue', blank=True)`. Choices match `YAMAHA_TO_HEX` keys exactly (`Off`, `Red`, `Orange`, `Yellow`, `Green`, `Sky Blue`, `Blue`, `Purple`, `Pink`, `White`). Migration is purely additive — zero `ALTER TABLE` against existing data. Plan 1 / migration 0152 set the precedent for additive-only migrations in this milestone.

- **D-08:** New model `ConsoleImport`:
  - `console = ForeignKey(Console, on_delete=CASCADE)` — many imports per console.
  - `uploaded_by = ForeignKey(User)` — audit.
  - `uploaded_at = DateTimeField(auto_now_add=True)`.
  - `original_filename = CharField`.
  - `raw_file = FileField` — uploaded `.csv` preserved verbatim. Uploaded files live under `media/console_imports/<project_id>/<console_id>/<timestamp>-<filename>`.
  - `parsed_sections = JSONField` — list of section names that were parsed (e.g. `["InName", "MixName", "MtxName"]`).
  - `summary = JSONField` — final commit stats: `{created: N, updated: N, conflicts_resolved: N, errors: [...]}`.
  - `committed = BooleanField(default=False)` — set when engineer clicks Commit on the diff preview. Uncommitted imports are draft state.

### Permissions

- **D-09:** CSV import is restricted to roles that can edit the console: `superuser`, `premium owner`, `editor`. The `viewer` role gets no upload UI and a 403 on direct POST. This matches the role pattern Phase 1 established.

### Claude's Discretion

- Default-row detection for output sections (`MixName`, `MtxName`, `StName`, `StMonoName`, `DCAName`): derive from blank fixtures. Same shape as input default-row detection (D-01).
- Per-row error UI styling, banner messaging copy, dropdown-of-consoles UX details.
- Re-import semantics (uploading the same CSV twice creates two `ConsoleImport` records; second one diffs against current console state, not against the first import).
- Parse-error UX (malformed CSV file): show banner *"Could not parse — `<reason>`"* on upload, no `ConsoleImport` record created.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Format intel & fixtures
- `planner/data/csv_fixtures/CL_Editor_Blank_Export/` — blank export from Yamaha CL Editor V4.1 for a CL5 console. 9 sections; 72-channel `[InName]`. Use to derive default-row detection rules.
- `planner/data/csv_fixtures/QL_Editor_Blank_Export/` — blank export from Yamaha QL Editor V4.1 for a QL5 console. Same 9 sections; 64-channel `[InName]`.
- `planner/data/csv_fixtures/Rivage_PM_Blank_Export/` — blank export from Yamaha Rivage PM Editor V6.60 (CS-R5 / DSP-RX). 11 sections; 288-channel `[InName]`. Different output section layout than CL/QL.

### Phase 1 (already-shipped) artifacts
- `planner/utils/reaper_export.py` lines 20–55 — `YAMAHA_TO_HEX` palette (the canonical color name → hex map). Exporter comment explicitly says *"Phase 2 CSV import populates channel-level Yamaha colors and resolves through this table."*
- `planner/utils/yamaha_export.py` — the EXPORT half (Console → Rivage CSV). Phase 2 is the inverse direction; the export side is the reference for section names, INI block format, and per-section row layout.
- `planner/models.py` lines ~770–900 — `ConsoleInput`, `ConsoleAuxOutput`, `ConsoleMatrixOutput`, `ConsoleStereoOutput` definitions. Confirm none have a `color` field today; D-07 migration adds one.

### Project conventions
- `CLAUDE.md` — register all admin classes on `showstack_admin_site`; `CurrentProjectMiddleware` for project scoping; additive migrations only against beta-tester data; collectstatic on every Railway deploy.
- `.planning/REQUIREMENTS.md` — CSV-01 through CSV-05 (the binding requirements).
- `.planning/ROADMAP.md` § Phase 2 — Goal and Success Criteria.

### Existing import pattern reference
- `planner/views.py` line 3215 (`comm_crew_name` import) — existing CSV import pattern using `csv.reader` + `TextIOWrapper`. Stylistic reference for the row loop, error collection, and message rendering. Phase 2's parser is more involved (multi-section INI-style file) but the per-row error pattern transfers directly.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `YAMAHA_TO_HEX` palette (`planner/utils/reaper_export.py`) — single source of truth for Yamaha color name ↔ hex. Phase 2 stores the name; this table resolves to hex when needed (already used by Phase 1 export).
- `yamaha_export.py:generate_input_csv` — per-section export logic. Reverse-engineering this gives the parser exact column-order and INI section structure.
- `BaseEquipmentAdmin` and the role-based permission pattern from Phase 1 admin — reuse for any admin actions on `ConsoleImport`.
- `CurrentProjectMiddleware` (per CLAUDE.md) — `request.current_project` already scopes everything.
- `request.FILES['<name>']` + `TextIOWrapper(file.file, encoding='utf-8')` pattern from existing CSV imports.

### Established Patterns
- All planner admin classes register on `showstack_admin_site` (NOT `admin.site`). When adding `ConsoleImport` to admin, use the same site.
- All views scope to `request.current_project`; never trust client-provided project IDs.
- Role gates: superuser / premium owner / editor can mutate; viewer is read-only. Apply to upload + commit endpoints.
- `@login_required` + role check decorators on all mutate endpoints (Phase 1 CR-01/CR-02 fix established this).
- Migrations are additive-only against beta-tester-loaded data; no `ALTER TABLE` of existing fields.

### Integration Points
- New URL routes under `/audiopatch/multitrack/` namespace (matches D-05 entry point):
  - `GET /audiopatch/multitrack/import/` — upload form (pick console + file).
  - `POST /audiopatch/multitrack/import/` — receive upload, parse, create draft `ConsoleImport` (uncommitted), redirect to preview.
  - `GET /audiopatch/multitrack/import/<import_id>/preview/` — diff preview page.
  - `POST /audiopatch/multitrack/import/<import_id>/commit/` — apply changes, mark committed, redirect to dashboard.
- Multitrack module landing template (`planner/templates/planner/multitrack/dashboard.html`) — add an "Import Console CSV" link/button alongside the existing "+ New Session" CTA.
- Banner rendering on the dashboard: reuse Django's `messages` framework — already in use elsewhere in the project.

</code_context>

<specifics>
## Specific Ideas

- The mental model the user articulated for `ConsoleImport`: *"the CSV file is the truth of what's on the physical console; the ShowStack console is what the engineer uses for planning. Don't conflate them."* The console can drift from any single import after the fact (engineer renames a channel for a show); the import record stays as a snapshot of what was on the desk at upload time.
- The user explicitly wants both inputs AND output names because *"if an engineer wants to track a stem it might come off an aux or matrix."*
- Smart-skip defaults rationale: the user expects the import to "just work" without forcing engineers to manually preserve their custom labels. The CSV almost always has factory defaults for unused channels, so skipping defaults preserves the user's careful labeling work in ShowStack.
- Diff preview UX rationale: "Stats summary + filter to changed rows" was chosen specifically because Rivage exports are 288 rows and most rows in any real-world import are unchanged (engineer changes 10–30 channels per gig).
- Block-on-mismatch rationale: prevents the worst-case bug where someone imports a Rivage CSV into a QL5 console and silently truncates 224 channels of label data.

</specifics>

<deferred>
## Deferred Ideas

- **Patch-section import** (`[InPatch]`, `[OutPatch]`, `[PortRackPatch]`, etc.) — would let ShowStack also know which Dante stream each input is patched from. Phase 2.x or its own phase. Useful but separate from name/color import.
- **DM7 Editor support** — Charlie noted no obvious CSV export from DM7. Revisit when an export path is identified.
- **Re-apply a previous `ConsoleImport`** — engineer browses past imports for a console and re-runs one. Useful for "revert this import" scenarios. Out of scope for Phase 2 first cut; can layer on later because the snapshot data is preserved.
- **M7CL CSV path** — already deferred to v2.1 in REQUIREMENTS.md.
- **Patch-aware track auto-population** in Phase 1 (when patches arrive) — once we know which Dante stream feeds each input, the Multitrack picker could auto-suggest the right tracks. Not in Phase 2.

</deferred>

---

*Phase: 02-console-csv-import*
*Context gathered: 2026-05-12*
