# Phase 2: Console CSV Import — Research

**Researched:** 2026-05-12
**Domain:** CSV ingestion of Yamaha CL/QL Editor and Rivage PM Editor channel-name exports into existing `ConsoleInput / ConsoleAuxOutput / ConsoleMatrixOutput / ConsoleStereoOutput` rows, with a per-row diff preview and an immutable `ConsoleImport` snapshot.
**Confidence:** HIGH

## Summary

Each Yamaha "Editor blank export" is a **set of one-file-per-section INI-style CSVs** (not a single multi-section file). The fixtures already in `planner/data/csv_fixtures/` confirm: every file opens with `[Information]` + 2 or 3 metadata lines, then the section header (e.g. `[InName]`), then a column-header row (`IN,NAME,COLOR,ICON,`), then 1..N data rows of the form `_NN,name,Color,Icon,` with a trailing comma. Files are UTF-8, no BOM, CRLF line endings.

This reshapes the parsing problem: **the uploader must accept either a single section file or a `.zip` bundle of multiple section files** (mirroring what `yamaha_export.py` produces). The "multi-section single CSV" mental model implied by parts of CONTEXT.md is incorrect for the fixtures shipped today; the planner must specify upload semantics explicitly.

Three high-leverage findings the planner must absorb before writing tasks:

1. **`ConsoleInput` does NOT have a `color` field today.** CONTEXT D-07 is correct as written; the "additional_context" note ("Existing model `ConsoleInput` already has `color` — verify against the actual file") is wrong — verified by reading `planner/models.py:777–905`. All four channel models need the `color` field added.
2. **There is no `Console.console_model` field.** CONTEXT L-04 / D-03 (block on family mismatch) cannot match against a stored field — it must use console-name heuristics (e.g., name contains "CL5"/"QL5"/"Rivage") or accept any console as a match (with a "Family detected: CS-R5. Continue?" confirmation gate). This needs a planner decision.
3. **Phase 1's picker already calls `ConsoleInput/Aux/Matrix/Stereo.objects.filter(console=console)`** (verified at `planner/views.py:5805–5826`). CSV-05 passes automatically once Phase 2 populates those rows — no Phase 1 view or template change is required.

**Primary recommendation:** Build the import as four cooperating pieces — (a) a per-file parser keyed by section header that emits canonical row dicts, (b) an upload view that creates a draft `ConsoleImport(committed=False)` + `parsed_sections` JSON immediately so the diff preview is reload-safe, (c) a section→model dispatch layer that runs `match-by-channel-number → update name + color` with default-row skip and conflict marking, and (d) a commit view that wraps the apply step in a single `transaction.atomic()` and flips `committed=True`. The exporter side (`yamaha_export.py`) and the YAMAHA palette table (`reaper_export.py:YAMAHA_TO_HEX`) are the literal reverse-direction reference.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Scope & Sections**
- **L-01:** Import the channel-name sections only — `[InName]`, `[StName]`, `[MixName]`, `[MtxName]` plus CL/QL's `[StMonoName]` and `[DCAName]`, plus Rivage's output equivalents. Patch sections explicitly deferred.
- **L-02:** New `ConsoleImport` model — immutable snapshot of the uploaded file plus parsed channel data. Project → Console → many `ConsoleImport` records.
- **L-03:** User picks a target Console in the current project before uploading. Import populates that console's channels — does NOT auto-create a console.
- **L-04:** Auto-detect console family from the `[Information]` block. Block import if it doesn't match the selected target (see D-03).
- **L-05:** Color storage uses the Yamaha palette names (`YAMAHA_TO_HEX` in `planner/utils/reaper_export.py`).
- **L-06:** DM7 deferred. M7CL deferred to v2.1.

**Update vs Replace**
- **D-01:** Smart-skip defaults. Default-row detection: NAME matches `ch ?N` for that channel number, COLOR is `Blue`, ICON is `Dynamic`. Per-section defaults derived from blank fixtures.
- **D-02:** True conflicts surface in diff with per-row checkbox; default-checked = CSV wins.

**Model Mismatch**
- **D-03:** BLOCK with error if CSV `[Information]` family doesn't match selected target.

**Diff Preview UX**
- **D-04:** Stats summary at top (`Created · Updated · Conflicts · Unchanged · Errors`) + filter to changed rows. Errors are non-blocking; rest of import proceeds.

**Upload Entry & Landing**
- **D-05:** Upload UI on `/audiopatch/multitrack/` landing page. One "Import Console CSV" button.
- **D-06:** After successful import, land on `/audiopatch/multitrack/` with success banner "Import complete — N channels imported."

**Schema**
- **D-07:** Migration adds `color = CharField(max_length=20, choices=YAMAHA_COLOR_CHOICES, default='Blue', blank=True)` to `ConsoleInput`, `ConsoleAuxOutput`, `ConsoleMatrixOutput`, `ConsoleStereoOutput`. Purely additive.
- **D-08:** New `ConsoleImport` model: `console FK`, `uploaded_by FK`, `uploaded_at`, `original_filename`, `raw_file FileField`, `parsed_sections JSONField`, `summary JSONField`, `committed BooleanField`. Files under `media/console_imports/<project_id>/<console_id>/<timestamp>-<filename>`.

**Permissions**
- **D-09:** Restricted to `superuser`, `premium owner`, `editor`. Viewer gets no upload UI and 403 on direct POST.

### Claude's Discretion

- Default-row detection rules for output sections (`MixName`, `MtxName`, `StName`, `StMonoName`, `DCAName`, `MuteDCAName`).
- Per-row error UI styling, banner copy, dropdown-of-consoles UX.
- Re-import semantics (uploading the same CSV twice creates two `ConsoleImport` records; second one diffs against current console state).
- Parse-error UX for malformed CSV (banner "Could not parse — `<reason>`"; no `ConsoleImport` record created).

### Deferred Ideas (OUT OF SCOPE)

- Patch-section import (`[InPatch]`, `[OutPatch]`, `[PortRackPatch]`, etc.) — defer.
- DM7 Editor support — defer until an export path is identified.
- Re-apply a previous `ConsoleImport` (audit-replay).
- M7CL CSV path — deferred to v2.1.
- Patch-aware track auto-population in Phase 1.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CSV-01 | User can upload a Yamaha CL/QL channel-name CSV and have it populate or update the console's channels in ShowStack. | Per-section parser spec (§ Standard Stack / § Architecture Patterns); CL5/QL5 fixtures confirmed at `planner/data/csv_fixtures/CL_Editor_Blank_Export/` and `/QL_Editor_Blank_Export/`. |
| CSV-02 | User can upload a Yamaha Rivage PM channel-labels CSV and have it populate or update the console's channels. | Rivage fixture confirmed at `planner/data/csv_fixtures/Rivage_PM_Blank_Export/`; section-layout differences from CL/QL documented in § Section-by-Section Parsing Spec. |
| CSV-03 | Imported channel labels and colors map onto existing `ConsoleChannel` records when present, otherwise create new ones; user is shown a per-row diff summary before commit. | Diff preview architecture in § Diff Preview Architecture; match-by-channel-number rule in § Console → Channel Model Mapping; `ConsoleImport(committed=False)` lifecycle. |
| CSV-04 | Import errors surface clearly per row without aborting the whole import. | Per-row error catalog in § Per-Row Error Catalog; non-blocking error handling (D-04). |
| CSV-05 | After a successful import, user lands in the session editor with the imported channels available as track sources. | Phase 1 picker already queries `Console{Input,AuxOutput,MatrixOutput,StereoOutput}.objects.filter(console=...)` — verified at `planner/views.py:5805–5826`. Phase 2 just needs to populate those rows; CSV-05 passes by construction. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| CSV upload form rendering | Frontend Server (Django view + template) | — | Same as Phase 1 multitrack pages; reuse `mts-*` CSS prefix. |
| CSV file decoding (UTF-8 / TextIOWrapper) | Backend (Django view) | — | Existing import pattern at `planner/views.py:3221` is the literal reference. |
| Section parser (header detection + row iteration) | Backend utility module | — | New file `planner/utils/yamaha_csv_import.py` (mirror placement of `yamaha_export.py`). Pure functions, no DB. |
| `[Information]` block → console-family extraction | Backend utility (in parser module) | — | Pure-function classifier; returns `'cl_ql'` / `'rivage_pm'` / `'unknown'`. |
| Per-row diff computation | Backend utility | — | Pure functions over `(parsed_rows, current_channel_state)` — testable without DB. |
| Draft persistence (`ConsoleImport(committed=False)`) | Database / ORM | Storage (media volume) | Survives page reload, supports D-04 large-import flow. |
| Diff preview rendering | Frontend Server | Browser (filter chips) | Server-rendered table; client-side JS only filters visible rows. |
| Commit atomicity | Database (`transaction.atomic`) | — | All-or-nothing apply; preserves audit integrity. |
| Post-commit channel availability | Database (existing FK queries) | — | Phase 1 picker already reads these tables; nothing to add. |

## Standard Stack

### Core (already in the project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Django | 5.x | Web framework | [VERIFIED: `audiopatch/settings.py`] Already the project framework. |
| Python stdlib `csv` | 3.x | CSV parsing | [VERIFIED: `planner/views.py:3199, 3222`] Already used for `comm_crew_name` import. |
| Python stdlib `io.TextIOWrapper` | 3.x | Decode uploaded `InMemoryUploadedFile.file` (binary) to text | [VERIFIED: `planner/views.py:3221`] Established import idiom. |
| Python stdlib `zipfile` | 3.x | Accept `.zip` bundle of section CSVs | [VERIFIED: `planner/utils/yamaha_export.py:11`] Already used on export side; symmetrical on import. |
| `django.db.transaction.atomic` | bundled | All-or-nothing commit apply | [VERIFIED: Django docs] Standard atomic-batch idiom. |
| Django `messages` framework | bundled | Banner rendering on D-06 redirect | [VERIFIED: `planner/views.py:3258`] Already used elsewhere. |
| Django `FileField(upload_to=...)` | bundled | Persist raw uploaded CSV | [VERIFIED: `planner/models.py:3286`] (`pdf_file` on `Prediction` uses identical shape.) |
| Django `JSONField` | bundled | `parsed_sections` and `summary` on `ConsoleImport` | [VERIFIED: `planner/models.py:3287, 4384`] |

### Supporting (also already in the project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `request.FILES['<name>']` | Django bundled | Receive upload | Upload view. |
| `transaction.atomic()` context manager | Django bundled | Commit-time atomicity | Commit view. |
| `extra_tags='multitrack_import'` on `messages.success` | Django bundled | Distinguish import banner from other module banners on `/audiopatch/multitrack/` | D-06 banner. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `csv` | `pandas.read_csv` | [CITED: pandas docs] Adds a heavy dep for trivial parsing; stdlib `csv` handles the per-section row shape fine. **Stay with stdlib.** |
| `ConsoleImport(committed=False)` draft | Session-cached parsed state | Session-only state breaks if user reloads the preview page or navigates away; 288-row Rivage payload bloats the session cookie. **Persist in DB.** |
| One uploader for "single multi-section file" | One uploader that accepts either a single section CSV or a `.zip` of multiple sections | The fixtures shipped today are one-file-per-section. **Support both: single file uploads import one section; `.zip` upload imports all sections in the bundle.** |

**Installation:** Nothing to install — Phase 2 uses stdlib + Django only.

**Version verification (skipped):** No external packages added.

## Architecture Patterns

### System Architecture Diagram

```
                              Browser
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
            ▼                    ▼                    ▼
    GET multitrack/      POST multitrack/      POST multitrack/
    (D-05 button)        import/               import/<id>/commit/
            │                    │                    │
            │                    │                    │
            ▼                    ▼                    ▼
       dashboard.html     console_csv_upload    console_csv_commit
       (add "Import"      view                  view
        CSV button)            │                    │
                               │                    │
                               ▼                    ▼
                      ┌────────────────┐    ┌─────────────────┐
                      │ Decode + Parse │    │ Apply diff →    │
                      │ (utils/yamaha  │───▶│ update/create   │
                      │  _csv_import)  │    │ Console{Input,  │
                      └────────────────┘    │  Aux,Mtx,Stereo}│
                               │            │ rows (atomic)   │
                               │            └─────────────────┘
                               ▼                    │
                      ┌────────────────┐            │
                      │ Compute diff   │            │
                      │ vs current     │            │
                      │ channel state  │            │
                      └────────────────┘            │
                               │                    │
                               ▼                    │
                      ┌────────────────┐            │
                      │ Save           │            │
                      │ ConsoleImport  │            │
                      │ committed=False│            │
                      │ + raw_file     │            │
                      │ + parsed JSON  │            │
                      └────────────────┘            │
                               │                    │
                               ▼                    │
                  GET multitrack/import/<id>/       │
                  preview/  ─── (server-rendered)   │
                  diff table + checkbox/filter UI   │
                               │                    │
                               └────────────────────┘
                                        │
                                        ▼ (on commit success)
                              messages.success +
                              redirect → /audiopatch/multitrack/
                              (D-06 banner; Phase 1 picker now sees
                               new rows via the existing
                               ConsoleInput.objects.filter(console=...) query)
```

### Recommended Project Structure
```
planner/
├── utils/
│   ├── yamaha_export.py            # existing — export side (reference)
│   ├── yamaha_csv_import.py        # NEW — pure-function parser + diff
│   └── reaper_export.py            # existing — owns YAMAHA_TO_HEX
├── models.py                       # APPEND: ConsoleImport; ALTER (additive): color field on 4 channel models
├── migrations/
│   └── 0153_console_color_and_consoleimport.py   # NEW (auto-generated)
├── views.py                        # APPEND: console_csv_upload, console_csv_preview, console_csv_commit
├── urls.py                         # APPEND: 3 new /audiopatch/multitrack/import/* routes
├── admin.py                        # APPEND: ConsoleImportAdmin (registered on showstack_admin_site)
├── admin_ordering.py               # APPEND: 'consoleimport': 51 in order_map
├── forms.py                        # APPEND: ConsoleCsvUploadForm (target console dropdown + file)
├── templates/planner/multitrack/
│   ├── dashboard.html              # MODIFY: add "Import Console CSV" button next to "+ New Session"
│   ├── csv_upload.html             # NEW — pick console + file form
│   └── csv_preview.html            # NEW — diff stats + filtered row table + commit button
└── data/csv_fixtures/              # existing — used for default-row derivation; eventually duplicated into tests/fixtures/
```

### Pattern 1: One-File-Per-Section CSV with `[Information]` + `[Section]` + column-header

**What:** Every Yamaha Editor export file is structured exactly the same way: an `[Information]` block (2 or 3 lines depending on console family), a section header in square brackets, a column-header row, then 1..N data rows with a trailing comma after the last column.

**When to use:** Always — there is no other shape.

**Example (CL5 `InName.csv`):**
```
[Information]
CL5
V4.1
[InName]
IN,NAME,COLOR,ICON,
_01,ch 1,Blue,Dynamic,
...
_72,ch72,Blue,Dynamic,
```

**Example (Rivage PM `InName.csv`):**
```
[Information]
CS-R5
DSP-RX
V6.60
[InName]
IN,NAME,COLOR,ICON,
_001,ch 1,Blue,Dynamic,
...
_288,ch288,Blue,Dynamic,
```

Key shape differences CL/QL ↔ Rivage:
- `[Information]` is 2 lines (model + version) on CL/QL, 3 lines (model + DSP type + version) on Rivage.
- Channel-key padding is 2-digit (`_01`) on CL/QL, 3-digit (`_001`) on Rivage for `[InName]`.
- All `[MixName]` / `[MtxName]` channel keys are 2-digit even on Rivage.
- `[StName]` keys differ — see § Section-by-Section Parsing Spec below.
- Rivage emits `[MuteDCAName]` (not `[DCAName]`) and uses full string keys (`DCA 1`...`DCA 24`, `Mute 1`...`Mute 12`).
- Rivage has NO `[StMonoName]` section.

### Pattern 2: Draft-then-commit `ConsoleImport` lifecycle

**What:** Upload immediately persists a `ConsoleImport(committed=False)` row with the parsed payload in `parsed_sections` JSON. The preview page reads from that row. The commit view applies the diff to the channel models, sets `committed=True`, writes the final `summary` JSON, and redirects.

**When to use:** Always for CSV import. Mirrors the project's existing "draft state in a DB row" idiom and survives page reloads on a 288-row Rivage import.

**Example structure:**
```python
# Upload view (POST)
with transaction.atomic():
    snap = ConsoleImport.objects.create(
        console=target_console,
        uploaded_by=request.user,
        original_filename=request.FILES['csv_file'].name,
        raw_file=request.FILES['csv_file'],
        parsed_sections=parsed_payload,  # {'InName': [...], 'MixName': [...]}
        committed=False,
    )
return redirect('planner:console_csv_preview', import_id=snap.id)

# Commit view (POST)
with transaction.atomic():
    snap = ConsoleImport.objects.select_for_update().get(pk=import_id)
    if snap.committed:
        return HttpResponseBadRequest('Already committed.')
    summary = _apply_import(snap, conflict_overrides=request.POST.getlist('keep_showstack'))
    snap.summary = summary
    snap.committed = True
    snap.save()
messages.success(request, f"Import complete — {summary['created'] + summary['updated']} channels imported.", extra_tags='multitrack_import')
return redirect('planner:multitrack_dashboard')
```

### Pattern 3: Match-by-channel-number, smart-skip defaults, surface conflicts

**What:** For each parsed row, compute the integer channel number from the key (`_01` → `1`, `_001` → `1`, `DCA 1` → `1`). Find the existing `Console{Input,Aux,Matrix,Stereo}` row for that console with that number. Compare both `name` and `color`. Classify as:

- **Default-skip** — CSV row matches the per-section factory default for that channel number (see § Per-Section Default-Row Rules). No DB write; counts in `Unchanged`.
- **Created** — no existing row for that channel number; new row created on commit.
- **Updated (clean)** — existing row's `name`/`color` is blank, default, or otherwise non-customised; CSV value wins.
- **Conflict** — both CSV and existing row are customised AND values differ. Surfaces in preview with a checkbox (default-checked = CSV wins per D-02). Unchecked rows are skipped on commit.
- **Unchanged** — existing row already matches CSV exactly.

### Anti-Patterns to Avoid

- **Streaming the parsed data through the session cache.** Breaks page reload, bloats cookie. Use `ConsoleImport(committed=False)` rows instead.
- **Hand-writing a multi-section INI parser.** Each fixture file is single-section. Either accept one section file or a `.zip` of multiple section files — both paths go through the same per-file parser.
- **Aborting the whole import on a single bad row.** Violates CSV-04 + D-04. Row-level errors get a row in the `errors` list inside `summary`; the rest of the rows still apply.
- **Letting the diff preview compute against stale state.** Always recompute the diff on the preview GET against the *current* `Console{Input,Aux,Matrix,Stereo}` state — not against any state snapshotted at upload time. Otherwise a concurrent editor admin edit produces a wrong-looking diff. (See § Diff Preview Architecture > Race Conditions.)
- **Using `console_model` to gate import.** No such field exists. Use console-name heuristics or accept any console as a target (with a confirmation gate showing the detected family).
- **Treating `[StName]` as having the same key shape across families.** CL/QL `[StName]` keys are `_01.._16` (returns). Rivage `[StName]` keys are `_AL,_AR,_BL,_BR` (the two stereo-group L/R legs). Different parsing rules.

## Section-by-Section Parsing Spec

> All findings below are `[VERIFIED]` by directly reading the fixture files in `planner/data/csv_fixtures/`.

### Per-section parser inputs

| Console family | `[Information]` lines | Detection rule |
|---|---|---|
| CL5 / CL3 / CL1 | 2 lines: model, version | Line 2 starts with `CL` (`CL5`, `CL3`, `CL1`). |
| QL5 / QL1 | 2 lines: model, version | Line 2 starts with `QL` (`QL5`, `QL1`). |
| Rivage PM (CS-R5/CS-R3/CS-R10) | 3 lines: model, DSP type, version | Line 2 starts with `CS-R` and line 3 starts with `DSP-` (`DSP-RX`, `DSP-R`, etc.). |

### Per-section table — IN-SCOPE sections only

| Section header | Console families | Column header | Data-row shape | Channel-key parse | Rows | Notes |
|----------------|------------------|---------------|----------------|-------------------|------|-------|
| `[InName]` | CL5 | `IN,NAME,COLOR,ICON,` | `_01,ch 1,Blue,Dynamic,` | `_NN` → strip leading `_`, parse int | 72 | 2-digit padding. |
| `[InName]` | QL5 | `IN,NAME,COLOR,ICON,` | `_01,ch 1,Blue,Dynamic,` | `_NN` → strip leading `_`, parse int | 64 | 2-digit padding. |
| `[InName]` | Rivage | `IN,NAME,COLOR,ICON,` | `_001,ch 1,Blue,Dynamic,` | `_NNN` → strip leading `_`, parse int | 288 | **3-digit padding** — must strip leading zeros after `_`. |
| `[MixName]` | CL5 | `MIX,NAME,COLOR,ICON,` | `_01,MX 1,Orange,Blank,` | `_NN` → strip + int | 24 | Mixes 1-16 (`Orange/Blank`) + Fx 1-8 (`_17.._24`, NAME=`Fx N`, `Orange/Effector`). Per-row default ICON varies — see § Per-Section Default-Row Rules. |
| `[MixName]` | QL5 | `MIX,NAME,COLOR,ICON,` | `_01,MX 1,Orange,Blank,` | `_NN` → strip + int | 16 | No Fx-named mix rows in default. |
| `[MixName]` | Rivage | `MIX,NAME,COLOR,ICON,` | `_01,MX 1,Orange,Blank,` | `_NN` → strip + int | 72 | 2-digit padding (NOT 3-digit like InName). |
| `[MtxName]` | CL5 | `MATRIX,NAME,COLOR,ICON,` | `_01,MT 1,Orange,Blank,` | `_NN` → strip + int | 8 | |
| `[MtxName]` | QL5 | `MATRIX,NAME,COLOR,ICON,` | `_01,MT 1,Orange,Blank,` | `_NN` → strip + int | 8 | |
| `[MtxName]` | Rivage | `MATRIX,NAME,COLOR,ICON,` | `_01,MT 1,Orange,Blank,` | `_NN` → strip + int | 36 | |
| `[StName]` | CL5 | `ST,NAME,COLOR,ICON,` | `_01,Rt1L,Blue,Effector,` | `_NN` → strip + int | 16 | Stereo *returns* — 8 stereo returns × 2 legs each (L/R). |
| `[StName]` | QL5 | `ST,NAME,COLOR,ICON,` | `_01,Rt1L,Blue,Effector,` | `_NN` → strip + int | 16 | Default names use `Rt1L/Rt1R` for first four pairs, then `ST5L..ST8R` for the rest. |
| `[StName]` | Rivage | `STEREO,NAME,COLOR,ICON,` | `_AL,ST A,Orange,Blank,` | Key is `_AL` / `_AR` / `_BL` / `_BR` (string, NOT integer) | 4 | **Stereo groups, not returns.** Different parse rule from CL/QL `[StName]`. NAME repeats across L/R of the same group in default (both `_AL` and `_AR` say `ST A`). |
| `[StMonoName]` | CL5 | `STEREO/MONO,NAME,COLOR,ICON,` | `_01,ST L,Orange,Blank,` | `_NN` → strip + int (1=L, 2=R, 3=Mono) | 3 | CL/QL only. Default NAMEs: `_01=ST L`, `_02=ST R`, `_03=MONO`. |
| `[StMonoName]` | QL5 | `STEREO/MONO,NAME,COLOR,ICON,` | `_01,ST L,Orange,Blank,` | `_NN` → strip + int | 3 | Same as CL5. |
| `[StMonoName]` | Rivage | — | — | — | — | **Not present in Rivage fixture.** Skip silently. |
| `[DCAName]` | CL5 | `DCA,NAME,COLOR,ICON,` | `_01,DCA 1,Yellow,Blank,` | `_NN` → strip + int | 16 | |
| `[DCAName]` | QL5 | `DCA,NAME,COLOR,ICON,` | `_01,DCA 1,Yellow,Blank,` | `_NN` → strip + int | 16 | |
| `[MuteDCAName]` | Rivage | `DCA,NAME,COLOR,ICON,` | `DCA 1,DCA 1,Yellow,Blank,` | First column is full string key — `DCA N` or `Mute N`. Parse: split on space, take int of last token | 24 DCAs + 12 Mutes | **Rivage's DCAs and Mutes share one section.** Mute rows have BLANK color and BLANK icon (`Mute 1,Mute 1,,,`). Mute rows are out of scope for Phase 2 channel storage — no `ConsoleMute` model exists; skip Mute rows or store nowhere. Planner decision: skip Mute rows. |

### Per-section quirks

- **All files use CRLF (`\r\n`) line endings.** `csv.reader` handles this fine if the file is opened with `newline=''` or via `TextIOWrapper(..., newline='')`. Without `newline=''`, the trailing-comma columns may parse weirdly. Test against fixture before declaring victory.
- **Every data row has a trailing comma**, so `csv.reader` returns a 5-element list with `''` as the 5th element. Parser must tolerate this (ignore index 4) and not treat the trailing comma as a 5th data field.
- **The first column on Rivage `[MuteDCAName]` contains a literal space** (`DCA 1`, not `DCA_1`). `csv.reader` will not split on spaces — the first column is the full `DCA 1` string.
- **NAME values are not quoted but may contain spaces** (`ch 1` has an internal space). `csv.reader` handles this.
- **Comma in a NAME is escaped on export by replacing with `;`** (see `yamaha_export.py:58`). On import, accept names as-is — do NOT reverse-translate `;` back to `,`. The exporter and importer are not paired tools; the user could legitimately type a `;` in a channel name.
- **Quoted names are not used by the official exporter**, but the import parser should still allow `csv.reader`'s default quoting just in case a tester hand-edits a name with a comma.

## Console Family Detection Rule

**Input:** First 4 lines of the uploaded file (post-decode), trimmed of `\r\n`.

**Algorithm:**
```python
def detect_family(lines):
    """Return one of 'cl_ql', 'rivage_pm', or 'unknown'.

    [Information]
    <model>
    [<DSP-type>]   # Rivage only — line 3
    <version>      # last line of the [Information] block
    [<Section>]    # first line after [Information] block
    """
    if not lines or lines[0].strip() != '[Information]':
        return 'unknown'
    model = lines[1].strip() if len(lines) > 1 else ''
    line3 = lines[2].strip() if len(lines) > 2 else ''
    if model.startswith('CL') or model.startswith('QL'):
        return 'cl_ql'
    if model.startswith('CS-R') or line3.startswith('DSP-'):
        return 'rivage_pm'
    return 'unknown'
```

**Matching against the selected target console:**

Because **`Console.console_model` does not exist** (verified — no such field anywhere in `planner/models.py`), the family-match check from D-03 has three viable implementations. The planner must pick one:

| Option | How | Tradeoff |
|--------|-----|----------|
| **A. Name-heuristic gate** | Check if the target console's `name` (case-insensitive) contains any token of `('CL5','CL3','CL1','QL5','QL1')` for `cl_ql`, or `('Rivage','PM7','PM10','CS-R5','CS-R3','CS-R10')` for `rivage_pm`. | False negatives if the user named their console `Main Desk` or `FOH`. Common case (named-by-model) works. |
| **B. Confirmation gate (no field)** | Don't block — show the detected family on the preview page and let the user confirm. | Cleanest for users who don't name consoles by model. Slightly more clicks. Doesn't satisfy D-03 literally. |
| **C. Add `Console.console_family` field** | Additive migration adds an optional choice field. Existing consoles default to `''` (unknown). | More work; needs a per-console UX to set it; deferrable. |

**Recommendation:** **Option B for v2.0.** D-03's intent is "prevent silently importing 288 Rivage rows into a 64-channel QL5." A confirmation gate satisfies that intent without depending on a field that doesn't exist. The cap-confirmation row count (e.g. "This import will create 224 new input channels — your selected console only has 64 today. Continue?") gives the user the safety net D-03 asks for, with zero schema risk.

If the planner picks Option A, document the matching token table in the plan task and add a test fixture for each.

## Per-Section Default-Row Rules

Derived directly from the blank-export fixtures. A row is "default" (smart-skip per D-01) iff **all** of `NAME`, `COLOR`, and `ICON` match the canonical default for that channel number in that section.

> Notation: `N` = integer channel number; `padN2` = `N` formatted as `1` when N<10 else 2-digit (matches the exporter's whitespace-pad convention: `ch 1`, `ch10`, `MX 1`, `MX10`, `DCA 1`, `DCA10` — single-digit values get a leading space, double-digit values are flush).

| Section | Family | Default `NAME` pattern (per channel `N`) | Default `COLOR` | Default `ICON` |
|---------|--------|------------------------------------------|-----------------|----------------|
| `[InName]` | CL5, QL5, Rivage | `ch{padN2}` (i.e. `ch 1` for N=1, `ch10` for N=10, `ch288` for N=288) | `Blue` | `Dynamic` |
| `[MixName]` rows 1–16 | CL5, QL5 | `MX{padN2}` | `Orange` | `Blank` |
| `[MixName]` rows 17–24 | CL5 only | `Fx {N-16}` (e.g. row `_17`=`Fx 1`, row `_24`=`Fx 8`) | `Orange` | `Effector` |
| `[MixName]` rows 1–72 | Rivage | `MX{padN2}` | `Orange` | `Blank` |
| `[MtxName]` rows 1–8 (CL/QL) or 1–36 (Rivage) | all | `MT{padN2}` | `Orange` | `Blank` |
| `[StName]` rows 1–8 (CL5) | CL5 | `Rt{ceil(N/2)}{'L' if N odd else 'R'}` (e.g. `_01`=`Rt1L`, `_02`=`Rt1R`, `_15`=`Rt8L`, `_16`=`Rt8R`) | `Blue` | `Effector` |
| `[StName]` rows 1–8 (QL5) | QL5 | Pairs 1–4: `Rt{ceil(N/2)}{L/R}`. Pairs 5–8: `ST{ceil(N/2)}{L/R}` (e.g. `_09`=`ST5L`, `_16`=`ST8R`). | `Blue` | `Effector` |
| `[StName]` keys `_AL,_AR,_BL,_BR` | Rivage | `_AL`,`_AR` → `ST A`; `_BL`,`_BR` → `ST B` | `Orange` | `Blank` |
| `[StMonoName]` | CL5, QL5 | `_01`=`ST L`; `_02`=`ST R`; `_03`=`MONO` | `Orange` | `Blank` |
| `[DCAName]` | CL5, QL5 | `DCA{padN2}` | `Yellow` | `Blank` |
| `[MuteDCAName]` DCA rows (`DCA 1`..`DCA 24`) | Rivage | NAME=`DCA{padN2}` (note: `DCA 1` for N=1, `DCA10` for N=10 — exporter trims the space at N≥10; see `yamaha_export.py:176`) | `Yellow` | `Blank` |
| `[MuteDCAName]` Mute rows (`Mute 1`..`Mute 12`) | Rivage | OUT OF SCOPE — no model — see below | (blank in fixture) | (blank in fixture) |

**Note on `padN2`:** The fixtures show `ch 1` (with internal space) for N=1 and `ch10` (no space) for N=10. The pattern is **right-justify width-2 in numeric-only space**, equivalent to Python's `f'ch{N:>2d}'` for `N<100` and `f'ch{N}'` for `N>=100`. Verified against CL5 fixture line 15 (`_10,ch10,...`) and Rivage fixture line 16 (`_010,ch10,...`).

**Mute rows handling:** Phase 2 has no `ConsoleMute` model and Mutes are not used as track sources in Phase 1. The parser should silently skip Mute rows from `[MuteDCAName]` (or store them in `parsed_sections` JSON for audit but not apply them). Document this skip in `summary.errors` as informational, not as an error.

## Console → Channel Model Mapping

> Verified by reading `planner/models.py:777–905` and `planner/views.py:5805–5826`.

| CSV section | Target Django model | Match key (Console+number) | Name field | Color field (added by D-07 migration) | Notes |
|-------------|--------------------|----------------------------|------------|----------------------------------------|-------|
| `[InName]` | `ConsoleInput` | `console=target, input_ch=str(N)` | `source` (max_length=100) | `color` (max_length=20) | **Critical: name field is `source`, NOT `name`.** Phase 1 picker uses `c.source or c.input_ch` as label. Match against `input_ch` parsed as `str(int(key.lstrip('_')))` — drops leading zeros from Rivage's `_001`. |
| `[MixName]` | `ConsoleAuxOutput` | `console=target, aux_number=str(N)` | `name` (max_length=100) | `color` (max_length=20) | `aux_number` is `CharField(max_length=10)`. Phase 1 picker uses `c.name or f'Aux {c.aux_number}'`. |
| `[MtxName]` | `ConsoleMatrixOutput` | `console=target, matrix_number=str(N)` | `name` (max_length=100) | `color` (max_length=20) | `matrix_number` is `CharField(max_length=10)`. |
| `[StName]` (CL/QL) | (none — see notes) | — | — | — | CL/QL `[StName]` rows are *stereo returns*, not the L/R/Mono master stereo bus. There is no `ConsoleStereoReturn` model in the schema. **Recommendation: skip `[StName]` entirely for CL/QL family in v2.0 and document under Open Questions.** Inputs+Mix+Mtx+StMono+DCA still cover the engineer's primary need. |
| `[StName]` (Rivage) | `ConsoleStereoOutput` | `console=target, stereo_type=?` | `name` | `color` (added) | Rivage `[StName]` has 4 rows: `_AL,_AR,_BL,_BR`. The existing model has `STEREO_CHOICES = [('L','Stereo Left'), ('R','Stereo Right'), ('M','Mono')]` — **only 3 values**. The 4 Rivage stereo legs do not map cleanly. **Recommendation: in v2.0, import only `_AL` (→ `stereo_type='L'`) and `_AR` (→ `stereo_type='R'`). Skip `_BL`/`_BR` and log under `summary.errors` as informational.** Either accept the L/R-only loss or expand `STEREO_CHOICES` (not in scope for D-07's additive migration). |
| `[StMonoName]` (CL/QL) | `ConsoleStereoOutput` | `console=target, stereo_type=?` | `name` | `color` (added) | CL/QL `[StMonoName]` has 3 rows: `_01=ST L`, `_02=ST R`, `_03=MONO`. Map `_01→'L'`, `_02→'R'`, `_03→'M'`. This **matches the existing model exactly**. |
| `[DCAName]` (CL/QL) | (none) | — | — | — | No `ConsoleDCA` model exists in `planner/models.py`. **Recommendation: skip `[DCAName]` in v2.0 OR add a `ConsoleDCA` model — this is a planner decision and an Open Question.** If skipped, document under summary.errors as informational. If added, it's a new model and a new migration (D-07 doesn't cover it). |
| `[MuteDCAName]` (Rivage) | (none) | — | — | — | Same DCA-model-doesn't-exist problem. Same recommendation. |

**This is the single biggest unresolved item in Phase 2 scope.** CONTEXT L-01 says `[DCAName]` and `[MixName]` are in scope, but the model layer doesn't have a place to put DCA names. Either:

- **(a)** Cut DCA from scope ("v2.0 imports input + aux + matrix + stereo only; DCA deferred until model added"), OR
- **(b)** Expand D-07 to also create a `ConsoleDCA` model with `console FK, dca_number CharField, name CharField, color CharField`. Additive migration. Approx 30 LoC.

The plan-time discussion should resolve this before writing tasks.

## Migration Check

> Verified by reading `planner/models.py:777–905`.

| Model | Currently has `color`? | D-07 migration adds? |
|-------|------------------------|----------------------|
| `ConsoleInput` (line 777) | **NO** | YES |
| `ConsoleAuxOutput` (line 846) | **NO** | YES |
| `ConsoleMatrixOutput` (line 870) | **NO** | YES |
| `ConsoleStereoOutput` (line 888) | **NO** | YES |

**CONTEXT.md D-07 is correct as written.** The note in `additional_context` of the research request ("Existing model `ConsoleInput` already has `color` — verify against the actual file") is **wrong** — there is no `color` field on `ConsoleInput` today. All four channel models need the field added.

**Field choice constant `YAMAHA_COLOR_CHOICES` — recommended placement:** Define once at the top of `planner/models.py` (or in a small new `planner/constants.py`), reference from all four model definitions. Use the same key order as `YAMAHA_TO_HEX` in `reaper_export.py:26–37`:

```python
YAMAHA_COLOR_CHOICES = [
    ('Off',      'Off'),
    ('Red',      'Red'),
    ('Orange',   'Orange'),
    ('Yellow',   'Yellow'),
    ('Green',    'Green'),
    ('Sky Blue', 'Sky Blue'),
    ('Blue',     'Blue'),
    ('Purple',   'Purple'),
    ('Pink',     'Pink'),
    ('White',    'White'),
]
```

Migration file name: `planner/migrations/0153_console_color_and_consoleimport.py` (auto-generated by `makemigrations planner` after the model changes are in).

**Contradiction with CONTEXT.md to flag:** Lines 99 in CONTEXT.md say to confirm by reading `planner/models.py:770–900` — and that's exactly what we did. No contradiction with D-07. The contradiction is between `additional_context` (research-request) and CONTEXT.md / reality. **CONTEXT.md is correct.** Update the research-request note accordingly during plan-checker.

## Diff Preview Architecture

### Where does the parsed-but-uncommitted state live?

**Recommendation:** Persist the `ConsoleImport(committed=False)` row + `raw_file` + `parsed_sections` JSON **immediately on upload** (Option A from the research-request).

**Reasoning:**

| Criterion | Option A: DB-persisted draft | Option B: Session/cache stash |
|-----------|------------------------------|-------------------------------|
| Survives page reload | ✓ | ✗ |
| Survives login expiry | ✓ | ✗ |
| Permits a "back to upload" navigation without re-uploading | ✓ | ✗ |
| Doesn't bloat session cookie with a 288-row Rivage payload | ✓ | ✗ |
| Provides audit history (CSV-03's "show me the file as uploaded") | ✓ | ✗ |
| Matches CONTEXT D-08 (which lists `committed` as a field, implying draft state) | ✓ | ✗ |
| Matches the existing project idiom | ✓ ([VERIFIED] `Prediction.raw_data` JSONField + `ConsoleImport`-style models in `planner/models.py:3287` follow this pattern) | ✗ |
| Cost | One extra row per draft (cleanable by a periodic "delete uncommitted older than 7 days" cron) | Zero |

Option A wins on every dimension that matters.

### Race conditions

1. **Concurrent edit between preview and commit.** Engineer A previews an import diff (computed against console state at 12:00). Engineer B edits a channel name in admin at 12:01. Engineer A commits at 12:02. The commit applies CSV values against state that has drifted from what the preview showed.
   - **Mitigation:** Recompute the diff on the commit POST against current state, not against the preview's diff. Show a "channel state changed since preview — re-preview before commit" inline error and re-render the preview if any drift is detected. Simpler alternative: don't detect drift; just apply against current state and trust the audit history (the `ConsoleImport` row preserves the file + what was applied).
   - **Recommendation:** **No detection in v2.0.** Document the "audit trail covers it" reasoning. The realistic concurrent-edit window for a solo engineer working on a project is microseconds.

2. **Double-commit (two browser tabs).** Engineer opens preview in two tabs, hits Commit in both.
   - **Mitigation:** `select_for_update()` in the commit view + check `committed=True` before applying. Second commit returns 400 with "Already committed."

3. **Re-upload of the same CSV.** Engineer uploads the same file twice (intentional or accidental).
   - **Behaviour:** Each upload creates a new `ConsoleImport` row. Second one's diff is computed against the state *after* the first one committed. CONTEXT.md "Claude's Discretion" already addresses this — this is the expected behaviour.

4. **`ConsoleImport` row never committed.** Engineer uploads, previews, then closes the tab without committing.
   - **Cleanup:** Document a "drafts older than 7 days are pruned" maintenance job. Out of scope for the v2.0 first cut; just leave drafts in place.

## Per-Row Error Catalog

The parser must distinguish these per-row error categories so the diff preview can render row-specific reasons (CSV-04 + D-04):

| Code | Category | Trigger | Severity | Goes in `summary.errors` |
|------|----------|---------|----------|--------------------------|
| `E_ENCODING` | File-level, not row-level | `TextIOWrapper(...)` raises `UnicodeDecodeError`. | Fatal (no `ConsoleImport` row created) | No |
| `E_NO_INFORMATION` | File-level | First non-empty line is not `[Information]`. | Fatal | No |
| `E_UNKNOWN_FAMILY` | File-level | `[Information]` block doesn't classify as `cl_ql` or `rivage_pm`. | Fatal | No |
| `E_NO_SECTION` | File-level | No recognised section header (`[InName]` / `[MixName]` / `[MtxName]` / `[StName]` / `[StMonoName]` / `[DCAName]` / `[MuteDCAName]`) found in any uploaded file. | Fatal | No |
| `E_UNEXPECTED_SECTION` | Per-section | Section header is recognised but in scope only for the *other* family (e.g. `[MuteDCAName]` in a CL5 import). | Informational; skip section | Yes |
| `E_BAD_KEY` | Per-row | Channel key doesn't match the expected shape for the section (e.g. `_AB` in `[InName]`). | Per-row; skip row | Yes |
| `E_KEY_OUT_OF_RANGE` | Per-row | Channel number exceeds the section's max for that family (e.g. `_289` in Rivage `[InName]`, or `_073` in CL `[InName]`). | Per-row; skip row | Yes |
| `E_UNKNOWN_COLOR` | Per-row | `COLOR` value is not in `YAMAHA_COLOR_CHOICES`. | Per-row; apply NAME, default COLOR to `Blue`, log the original color in the error | Yes |
| `E_COLUMN_COUNT` | Per-row | Row has fewer than 4 columns (parser expects `KEY,NAME,COLOR,ICON,` + trailing comma = 5 fields). | Per-row; skip row | Yes |
| `E_DUPLICATE_KEY` | Per-row | Same channel key appears twice in the same section. | Per-row; first wins, second logged | Yes |
| `E_NAME_TOO_LONG` | Per-row | `NAME` exceeds the model's `max_length=100`. | Per-row; truncate and log warning | Yes |
| `W_DEFAULT_SKIP` | Per-row (informational) | Row is a smart-skip default (D-01). | Per-row; not user-shown by default | No (counts in `summary.unchanged`) |
| `W_NO_MODEL_TARGET` | Per-section (informational) | Section is parsed but has no target model (e.g. `[DCAName]` if planner picks "skip DCAs"). | Whole-section skip; one warning entry | Yes |

The diff preview row table renders an `error_code` cell for each error row; the filter chip `Errors only` filters by `error_code != null`.

## Integration with Phase 1 Picker

**Verified at `planner/views.py:5805–5826`.** The picker view `_build_picker_data` already runs:

```python
inputs_qs = list(ConsoleInput.objects.filter(console=console).exclude(id__in=used_ids['input']))
aux_qs    = list(ConsoleAuxOutput.objects.filter(console=console).exclude(id__in=used_ids['aux']))
matrix_qs = list(ConsoleMatrixOutput.objects.filter(console=console).exclude(id__in=used_ids['matrix']))
stereo_qs = list(ConsoleStereoOutput.objects.filter(console=console).exclude(id__in=used_ids['stereo']))
```

…and label-resolves with `c.source or c.input_ch` for inputs and `c.name or f'Aux {c.aux_number}'` etc. for outputs.

**Conclusion:** Phase 2 must:
1. Create or update rows in the four channel models for the target console.
2. Set `source` (for inputs) or `name` (for outputs) from the CSV `NAME` column.
3. Set `color` from the CSV `COLOR` column (after D-07 migration adds the field).

**No Phase 1 code change is required.** CSV-05 ("user lands in session editor with imported channels available as track sources") is satisfied automatically — the picker re-queries on every page load and will see the new rows. D-06's land-on-`/audiopatch/multitrack/` is sufficient; user clicks "+ New Session" → picks the target console → picker shows the imported channels.

**One Phase 1 follow-up to consider (not in scope for Phase 2):** Phase 1's picker label uses `c.source or c.input_ch` — it doesn't read `c.color`. Phase 5 (`default_record_color`) will be the moment to wire color into the picker and into seeded track color. Phase 2 just stores `color`; Phase 1 won't display it yet.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSV parsing | Custom line-splitting / regex | Python stdlib `csv.reader` | Already used at `views.py:3222`; handles quoting + edge cases. |
| File upload decode | `request.FILES['x'].read().decode('utf-8')` | `TextIOWrapper(request.FILES['x'].file, encoding='utf-8', newline='')` | Already-used pattern; the `newline=''` arg matters for CRLF files. |
| Zip handling | Manual byte-slicing | `zipfile.ZipFile` | Already used in `yamaha_export.py:11`. |
| Atomic batch apply | Manual try/rollback | `with transaction.atomic():` | Standard Django; bundled. |
| Filing system path resolution | Hand-construct `media/...` paths | `FileField(upload_to='console_imports/<project_id>/<console_id>/')` (use a callable for the dynamic path) | Django manages collision-safe naming. |
| Banner text on the landing page | Custom toast component | `messages.success(request, "…", extra_tags='multitrack_import')` + the existing messages-rendering block in `dashboard.html` | Project-wide convention. |
| Section detection | One giant regex | A small lookup dict: `{'[InName]': 'InName', '[MixName]': 'MixName', ...}` keyed by exact header string | Clearer; testable. |

**Key insight:** Phase 2 is unusual in that **every primitive it needs is already in the codebase**. The work is composition, not new infrastructure. The biggest risk is divergent assumptions about (a) file shape, (b) which sections actually have a Django model to land in, and (c) how to gate the family mismatch without a `console_model` field.

## Runtime State Inventory

> Phase 2 is greenfield: it adds a new model (`ConsoleImport`), a new field (`color`) to four existing models, and new views/templates. It does **not** rename, refactor, or migrate runtime state. The "Runtime State Inventory" template applies to rename/refactor/migration phases. **This phase: nothing to inventory.**

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — purely additive | — |
| Live service config | None | — |
| OS-registered state | None | — |
| Secrets/env vars | None | — |
| Build artifacts | None | — |

## Common Pitfalls

### Pitfall 1: Treating CL/QL `[StName]` as the master stereo bus
**What goes wrong:** Engineer imports a CL5 CSV, expects to see "ST L/ST R/MONO" populated. Instead the parser tries to write `Rt1L/Rt1R/...` into `ConsoleStereoOutput` and breaks the `STEREO_CHOICES=[L,R,M]` constraint (or worse, silently inserts garbage).
**Why it happens:** Yamaha names the CL/QL stereo *returns* section `[StName]`. The master stereo+mono *output* section is `[StMonoName]`. Easy to conflate by name alone.
**How to avoid:** Map per the table in § Console → Channel Model Mapping — `[StName]` is for stereo returns (CL/QL: skip; Rivage: 4-row stereo group), `[StMonoName]` is the master bus (CL/QL only).
**Warning signs:** Rows with NAMEs starting `Rt` or `ST` going into a model whose existing rows say `ST L/ST R/MONO`.

### Pitfall 2: Leading-zero loss on Rivage `[InName]` keys
**What goes wrong:** Parser does `int('_001'[1:])` → `1`, then looks up `ConsoleInput(input_ch='1')`. But the CL5 fixture stored `input_ch='1'` (no padding) when imported from `_01`. So a Rivage `_001` correctly matches a CL5 `_01` for the same console number — but a `re-import` of a Rivage file into a console whose `input_ch` was stored padded (e.g. `'001'` from a hand-typed value) won't match.
**Why it happens:** `ConsoleInput.input_ch` is `CharField`, not `IntegerField`. No coercion guarantee.
**How to avoid:** Parser stores integer channel number; matcher coerces existing `input_ch` to int via `int()` (with try/except) before comparing. Mirrors `_int_or_inf` at `planner/views.py:5792`.
**Warning signs:** Diff shows N "create" rows but the console already has those channels — they didn't match because of string-vs-int comparison.

### Pitfall 3: Trailing-comma row becomes an extra column
**What goes wrong:** `csv.reader` returns `['_01', 'ch 1', 'Blue', 'Dynamic', '']` (5 elements) for a row like `_01,ch 1,Blue,Dynamic,`. Code that expects exactly 4 elements either crashes or treats `''` as a 5th data column.
**How to avoid:** Slice the first 4 elements, ignore index 4. Or check `len(row) >= 4` and unpack only those.
**Warning signs:** Off-by-one error in the row unpacking, or a `ValueError` on row dispatch.

### Pitfall 4: `newline=''` missing on `TextIOWrapper`
**What goes wrong:** Without `newline=''`, Python's universal-newlines translation eats `\r\n` into `\n` in a way that confuses `csv.reader` on Windows-style line endings — sometimes producing rows with embedded `\r` in the last column.
**How to avoid:** `TextIOWrapper(csv_file.file, encoding='utf-8', newline='')`. The fixtures use CRLF, so this matters.
**Warning signs:** The `ICON` column ends with `\r` in parsed rows.

### Pitfall 5: Upload-form field name collision
**What goes wrong:** Existing `import_comm_crew_names_csv` uses `request.FILES['csv_file']`. Phase 2 also uses `csv_file`. No collision because it's a different view, but be consistent so error-handling helpers can be reused.
**How to avoid:** Name the field `csv_file` in the form and the view; match the existing convention.

### Pitfall 6: `ConsoleImport.raw_file` upload_to path
**What goes wrong:** `upload_to='console_imports/<project_id>/<console_id>/<timestamp>-<filename>'` interpolation in Django expects a callable, not a string template.
**How to avoid:** Define a function: `def _import_upload_to(instance, filename): return f'console_imports/{instance.console.project_id}/{instance.console_id}/{timezone.now():%Y%m%dT%H%M%S}-{filename}'` and pass that to `FileField(upload_to=_import_upload_to)`.
**Warning signs:** Files land in `media/console_imports/<project_id>/...` *literal text*, not interpolated.

### Pitfall 7: Importing an empty `ConsoleInput` row that Phase 1 picker hides
**What goes wrong:** Phase 1 picker filters `.filter(console=console)` — every row matches. But after applying defaults, an input row may have `source=''` and the picker label fallback runs (`c.source or c.input_ch or 'Input N'`). That's fine — but if `input_ch` is also empty, label becomes "Input <id>". Bad UX.
**How to avoid:** On row creation in the apply step, always set `input_ch=str(channel_number)`. Same for `aux_number`, `matrix_number`. Don't leave them empty.

### Pitfall 8: Existing `ConsoleInput.source` redefinition bug
**What goes wrong:** `planner/models.py:781-782` defines `source = models.CharField(...)` twice — harmless on the database side (second wins) but a smell. Phase 1 PATTERNS.md flagged it as out-of-scope; **Phase 2 stays out of scope of fixing it.** Just write to `source`.

## Code Examples

### Detecting console family from the first 4 lines
```python
# planner/utils/yamaha_csv_import.py
# Source: verified against planner/data/csv_fixtures/{CL,QL,Rivage}_*

def detect_family(lines):
    """Return 'cl_ql', 'rivage_pm', or 'unknown' from the opening [Information] block."""
    stripped = [l.strip() for l in lines[:5] if l.strip()]
    if not stripped or stripped[0] != '[Information]':
        return 'unknown'
    model = stripped[1] if len(stripped) > 1 else ''
    line3 = stripped[2] if len(stripped) > 2 else ''
    if model.startswith(('CL', 'QL')):
        return 'cl_ql'
    if model.startswith('CS-R') or line3.startswith('DSP-'):
        return 'rivage_pm'
    return 'unknown'
```

### Parsing a single section file
```python
# planner/utils/yamaha_csv_import.py
import csv
from io import TextIOWrapper

KNOWN_SECTIONS = {'[InName]', '[MixName]', '[MtxName]', '[StName]', '[StMonoName]', '[DCAName]', '[MuteDCAName]'}


def parse_section_file(uploaded_file):
    """Parse one Yamaha Editor section CSV.

    Returns:
        {
          'family': 'cl_ql' | 'rivage_pm' | 'unknown',
          'section': 'InName' | ... | None,
          'header_row': ['IN', 'NAME', 'COLOR', 'ICON', ''],
          'rows': [{'key': '_01', 'name': 'ch 1', 'color': 'Blue', 'icon': 'Dynamic'}, ...],
          'errors': [{'code': '...', 'line': N, 'detail': '...'}],
        }
    """
    # IMPORTANT: newline='' so csv.reader handles CRLF correctly.
    text = TextIOWrapper(uploaded_file.file, encoding='utf-8', newline='')
    reader = csv.reader(text)
    rows = list(reader)
    if not rows:
        return {'family': 'unknown', 'section': None, 'errors': [{'code': 'E_NO_INFORMATION', 'line': 0}]}

    # Reconstruct raw line list for family detection
    raw_lines = [','.join(r) for r in rows[:5]]
    family = detect_family(raw_lines)

    # Find the section header — first row whose only non-empty cell starts with '['
    section = None
    section_index = None
    for i, r in enumerate(rows):
        if r and r[0].startswith('[') and r[0] != '[Information]':
            if r[0] in KNOWN_SECTIONS:
                section = r[0].strip('[]')
                section_index = i
            break

    if not section:
        return {'family': family, 'section': None, 'errors': [{'code': 'E_NO_SECTION', 'line': 0}]}

    # Header row is the next non-empty row after the section line
    header_row = rows[section_index + 1] if section_index + 1 < len(rows) else []
    data_rows = rows[section_index + 2:]

    parsed = []
    errors = []
    for n, row in enumerate(data_rows, start=section_index + 3):  # 1-indexed line numbers
        if not row or not row[0].strip():
            continue
        if len(row) < 4:
            errors.append({'code': 'E_COLUMN_COUNT', 'line': n, 'detail': f'expected 4 cols, got {len(row)}'})
            continue
        parsed.append({
            'key': row[0],
            'name': row[1],
            'color': row[2],
            'icon': row[3],
        })
    return {'family': family, 'section': section, 'header_row': header_row, 'rows': parsed, 'errors': errors}
```

### Default-row detector for inputs
```python
def is_input_default_row(parsed_row):
    """True iff this `[InName]` row matches the factory default for its channel number."""
    key = parsed_row['key'].lstrip('_')
    try:
        n = int(key)
    except ValueError:
        return False
    # 'ch 1' for n=1..9, 'ch10' for n>=10 (right-justified in width-2 numeric slot)
    expected_name = f'ch{n:>2d}' if n < 100 else f'ch{n}'
    return (
        parsed_row['name'] == expected_name
        and parsed_row['color'] == 'Blue'
        and parsed_row['icon'] == 'Dynamic'
    )
```

### Atomic apply with conflict-override resolution
```python
# planner/views.py — sketch of console_csv_commit
from django.db import transaction

@login_required
@require_POST
def console_csv_commit(request, import_id):
    if request.user.groups.filter(name='Viewer').exists():
        return HttpResponseForbidden('Read-only.')

    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return HttpResponseBadRequest('No project selected.')

    keep_showstack_ids = set(request.POST.getlist('keep_showstack'))   # checkboxes the user UNticked

    with transaction.atomic():
        snap = ConsoleImport.objects.select_for_update().select_related('console').get(
            pk=import_id, console__project=current_project,
        )
        if snap.committed:
            return HttpResponseBadRequest('Already committed.')
        summary = _apply_console_import(snap, keep_showstack_ids)
        snap.summary = summary
        snap.committed = True
        snap.save()

    messages.success(
        request,
        f"Import complete — {summary['created'] + summary['updated']} channels imported.",
        extra_tags='multitrack_import',
    )
    return redirect('planner:multitrack_dashboard')
```

## State of the Art

| Old approach | Current approach | When changed | Impact |
|--------------|------------------|--------------|--------|
| `BytesIO` + manual decode in Python 2 | `TextIOWrapper(file, encoding='utf-8', newline='')` | Python 3 | Correct CSV parsing of CRLF Yamaha exports. |
| Stash multi-step form state in session | Persisted draft model row (`committed BooleanField`) | Modern Django convention | Survives reloads; provides audit trail. |
| Hand-parse INI sections | One file per section (Yamaha's own export shape since CL Editor V4.0) | — | Simpler parser. |

**Deprecated/outdated:** None — Phase 2 uses current Django patterns that the project already uses elsewhere.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `csv.reader` with `newline=''` on a `TextIOWrapper` handles the trailing-comma 5-field rows correctly. | Code Examples | LOW — confirmed by Python docs; test with fixture. |
| A2 | Engineer-uploaded CSVs are always UTF-8 (no Shift-JIS or UTF-16 cases in practice for the US/EU market). | Common Pitfalls > Encoding | LOW — all three fixtures are UTF-8. Add an `E_ENCODING` fallback path. |
| A3 | The `.zip` bundle path (uploading the whole Editor-export folder zipped) is a useful workflow worth supporting. | Architecture Patterns | MEDIUM — confirm with user. If no, single-file uploads only suffice (engineer can upload `InName.csv`, then `MixName.csv`, etc.). |
| A4 | DCA storage being out-of-scope is acceptable for v2.0. | Console → Channel Model Mapping | **HIGH — needs user confirmation.** CONTEXT L-01 lists `[DCAName]` in scope but the model layer can't store DCAs. Either add `ConsoleDCA` model in this phase OR cut DCA from scope. |
| A5 | CL/QL `[StName]` (stereo *returns*) can be skipped entirely for v2.0 because there's no return model. | Console → Channel Model Mapping | **MEDIUM — needs user confirmation.** Could be deferred along with patches. |
| A6 | Rivage `[StName]` `_BL`/`_BR` group-B legs can be skipped because `ConsoleStereoOutput` only has L/R/M values. | Console → Channel Model Mapping | **MEDIUM — needs user confirmation.** Stereo group B is a real Rivage signal path; skipping it loses data. |
| A7 | The L-04 / D-03 family-mismatch gate works via name-heuristic OR a confirmation gate, not against a stored `Console.console_model` field. | Console Family Detection | LOW — no such field exists. Recommendation B (confirmation gate) is safe. |
| A8 | The "additive migration" pattern from migration 0152 (Phase 1) applies cleanly here. | Migration Check | LOW — verified. Both `CreateModel` (`ConsoleImport`) and four `AddField` ops (the `color` field) are additive. |
| A9 | A `summary.errors` JSONField row carrying per-row error codes is sufficient UI state for D-04's "errors only" filter. | Per-Row Error Catalog | LOW — diff preview re-renders from this on every GET. |
| A10 | Concurrent edits between preview and commit are rare enough to ignore for v2.0. | Diff Preview Architecture | LOW — solo-engineer-per-project usage assumption holds. |

## Open Questions

1. **DCA storage scope (A4 — HIGH risk).**
   - What we know: CONTEXT L-01 lists `[DCAName]` and `[MuteDCAName]` as in-scope. No `ConsoleDCA` model exists.
   - What's unclear: Add `ConsoleDCA` model in Phase 2 OR cut DCA from Phase 2 scope.
   - Recommendation: **Defer to plan-time human confirmation.** Add `ConsoleDCA(console FK, dca_number CharField, name CharField, color CharField)` as a small additive model — under 30 LoC including admin + admin_ordering entry. Or cut and document in Deferred.

2. **CL/QL `[StName]` (stereo returns) scope (A5 — MEDIUM risk).**
   - What we know: No model for stereo returns exists in the schema.
   - What's unclear: Skip OR add a model.
   - Recommendation: **Skip in v2.0**; document under Deferred. Phase 1 picker won't expose them anyway.

3. **Rivage stereo group B (`_BL`/`_BR`) scope (A6 — MEDIUM risk).**
   - What we know: `ConsoleStereoOutput.STEREO_CHOICES = [('L'),('R'),('M')]` — no slot for group-B legs.
   - What's unclear: Expand the choices OR skip B group.
   - Recommendation: **Skip in v2.0**; log informational under `summary.errors`.

4. **Console family-match gate without `console_model` field (A7 — LOW risk).**
   - What we know: D-03 says "block on mismatch" but there's no field to check against.
   - What's unclear: Use name-heuristic gate (Option A), confirmation gate (Option B), or add a field (Option C).
   - Recommendation: **Option B (confirmation gate)** with a "this will create N new channels — your console has M today, continue?" guardrail.

5. **`.zip` upload support (A3 — MEDIUM risk).**
   - What we know: Yamaha Editor exports a folder of section files; users will likely zip the folder rather than upload nine files one-by-one.
   - What's unclear: Worth supporting in v2.0 OR ship single-file-only?
   - Recommendation: **Support both** in v2.0 — `.zip` detection is `zipfile.is_zipfile(file)`; ~30 LoC.

## Environment Availability

> Phase 2 has no external service or runtime dependencies beyond the Django app itself.

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Django 5.x | Web framework | ✓ | 5.x (verified `settings.py`) | — |
| Python stdlib `csv`, `io`, `zipfile`, `transaction` | Parser + commit | ✓ | 3.x bundled | — |
| `media/` writable | `ConsoleImport.raw_file` storage | ✓ | (Railway volume) | — |

**No missing dependencies.**

## Validation Architecture

> Project config has `nyquist_validation: false`, but this section is included because the research request explicitly required it. Skip if the orchestrator's policy is to honor the config flag.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Django `TestCase` / `SimpleTestCase` ([VERIFIED] `planner/tests/test_reaper_export.py:22`) |
| Config file | `audiopatch/test_settings.py` ([VERIFIED] exists) |
| Quick run command | `python manage.py test planner.tests.test_yamaha_csv_import -v 2` |
| Full suite command | `python manage.py test planner -v 1` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CSV-01 | Upload CL5 InName.csv → 72 inputs created on a fresh console | integration (TestCase) | `python manage.py test planner.tests.test_yamaha_csv_import.UploadCL5Test` | ❌ Wave 0 |
| CSV-01 | Upload QL5 InName.csv → 64 inputs created | integration | `python manage.py test planner.tests.test_yamaha_csv_import.UploadQL5Test` | ❌ Wave 0 |
| CSV-02 | Upload Rivage InName.csv → 288 inputs created | integration | `python manage.py test planner.tests.test_yamaha_csv_import.UploadRivageTest` | ❌ Wave 0 |
| CSV-02 | Rivage `[MixName]` 72 mixes update `ConsoleAuxOutput` | integration | same module | ❌ Wave 0 |
| CSV-03 | Diff preview shows correct created/updated/conflict/unchanged counts | integration | `...test_yamaha_csv_import.DiffStatsTest` | ❌ Wave 0 |
| CSV-03 | Diff preview survives page reload (draft persistence) | integration | `...test_yamaha_csv_import.DraftReloadTest` | ❌ Wave 0 |
| CSV-04 | Bad-row error (unknown color, bad key) doesn't abort whole import | integration | `...test_yamaha_csv_import.PerRowErrorTest` | ❌ Wave 0 |
| CSV-04 | Per-row error code is captured in `summary.errors` | unit (SimpleTestCase) | `...test_yamaha_csv_import.SummaryErrorsTest` | ❌ Wave 0 |
| CSV-05 | After commit, Phase 1 picker view returns new channels | integration (full URL) | `...test_yamaha_csv_import.PickerPostImportTest` | ❌ Wave 0 |
| (parser) | `parse_section_file()` round-trips every fixture file | unit | `...test_yamaha_csv_import.ParserFixtureTest` | ❌ Wave 0 |
| (default-row) | `is_input_default_row()` returns True for every row in every blank fixture | unit | `...test_yamaha_csv_import.DefaultRowTest` | ❌ Wave 0 |
| (family) | `detect_family()` classifies each of the 3 fixture sets correctly | unit | `...test_yamaha_csv_import.FamilyDetectTest` | ❌ Wave 0 |
| (role gate) | Viewer-group user gets 403 on upload + commit POSTs | integration | `...test_yamaha_csv_import.ViewerGateTest` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python manage.py test planner.tests.test_yamaha_csv_import -v 2`
- **Per wave merge:** `python manage.py test planner -v 1`
- **Phase gate:** Full suite green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `planner/tests/test_yamaha_csv_import.py` — covers all CSV-01 through CSV-05 + parser unit tests.
- [ ] `planner/tests/fixtures/csv_import/cl5_inname.csv` — copy of `planner/data/csv_fixtures/CL_Editor_Blank_Export/InName.csv` for test isolation (so test won't break if production fixture is edited).
- [ ] `planner/tests/fixtures/csv_import/rivage_mixname_dirty.csv` — hand-crafted variant with one default row, one customised row, one conflict row, one bad-color row, one out-of-range key. The "happy path" + the error catalog all live here.
- [ ] No framework install needed — Django test runner is already in the project.

## Security Domain

> Project config does not explicitly set `security_enforcement`. Default-enabled. Included below.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | yes | `@login_required` on all import views (matches Phase 1 pattern at `views.py:5980, 6033`, etc.) |
| V3 Session Management | no | No new session state added (draft state lives in DB, not session). |
| V4 Access Control | yes | `_multitrack_viewer_block(request)` 403 helper from `views.py:6201` — reuse verbatim. IDOR guard: filter `ConsoleImport` by `console__project=request.current_project` on every fetch (matches Phase 1 IDOR pattern at `views.py:5777`). |
| V5 Input Validation | yes | CSV file: size limit + `Content-Type` check + encoding decode-or-fail. Channel-number range check per family (E_KEY_OUT_OF_RANGE). Color value in `YAMAHA_COLOR_CHOICES` whitelist (E_UNKNOWN_COLOR). |
| V6 Cryptography | no | No new crypto. |
| V12 Files & Resources | yes | `FileField` upload — Django storage backend handles path traversal. Validate file extension (`.csv` or `.zip`). Set a max upload size via `DATA_UPLOAD_MAX_MEMORY_SIZE` (already in Django config). |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via `raw_file` filename | Tampering | Django `FileField.upload_to` callable strips path components; use `os.path.basename(filename)` defensively in the callable. |
| Cross-project console import (IDOR) | Information disclosure | Filter `ConsoleImport.objects.filter(console__project=request.current_project)` on every preview/commit fetch. |
| Malicious zip-bomb upload | DoS | Reject `.zip` files where the uncompressed total exceeds e.g. 5 MB (every legitimate Editor export is under 200 KB; Rivage is 280 KB). |
| Malicious CSV with absurd row count (e.g. 1M rows of `_999999,...`) | DoS | Bound parsed-row count per section by the family's max (e.g. 288 for Rivage InName). Reject the section if it exceeds. |
| CSRF on upload + commit POSTs | Tampering | Django's `csrf_protect` (default on POST). `@require_POST` on the commit view. |
| Stored XSS via channel name | XSS | Django templates auto-escape; channel `name` is rendered via `{{ }}` in diff preview, not `{{ }|safe }`. |
| Role bypass via direct POST to commit URL | Authorization | `_multitrack_viewer_block(request)` returns 403 for viewers; check is before any DB write. |

## Sources

### Primary (HIGH confidence — verified by reading the file or running the tool)
- `planner/data/csv_fixtures/CL_Editor_Blank_Export/` (9 files) — directly read; section shapes, default rows, channel counts verified.
- `planner/data/csv_fixtures/QL_Editor_Blank_Export/` (9 files) — directly read; differences from CL5 (64 inputs, 16 mixes, no Fx default names) verified.
- `planner/data/csv_fixtures/Rivage_PM_Blank_Export/` (11 files) — directly read; 288 inputs, 3-digit padding, `[Information]` 3-line block, `[MuteDCAName]` shape, `[StName]` `_AL/_AR/_BL/_BR` keys verified.
- `planner/models.py:754–905` — directly read; confirmed NO `color` field on any of the four channel models; confirmed name fields are `source` (inputs) vs `name` (outputs); confirmed `STEREO_CHOICES=[L,R,M]`; confirmed no `Console.console_model` field exists.
- `planner/views.py:3196–3268` (`import_comm_crew_names_csv`) — read; pattern for `TextIOWrapper` + `csv.reader` + per-row try/except + `messages` framework.
- `planner/views.py:5746–5865` — read; Phase 1 picker queries `Console{Input,Aux,Matrix,Stereo}.objects.filter(console=console)`.
- `planner/views.py:6201–6212` (`_multitrack_viewer_block`) — read; role-gate pattern.
- `planner/utils/yamaha_export.py` (all 305 lines) — read; export-side reference for the inverse direction.
- `planner/utils/reaper_export.py:20–37` — read; `YAMAHA_TO_HEX` palette confirmed.
- `planner/admin_ordering.py` — read; order_map structure + `'multitracksession': 50` confirmed; spot for `'consoleimport': 51`.
- `planner/templates/planner/multitrack/dashboard.html` — read; D-05 button placement target.
- `planner/migrations/0152_multitrack_session_track.py` (filename verified by `ls`) — Phase 1's additive migration is the template for `0153_console_color_and_consoleimport.py`.
- `audiopatch/settings.py:105–106` — `MEDIA_URL='/media/'`, `MEDIA_ROOT` configured.
- `.planning/phases/01-core-sessions-track-editor-reaper-export/01-PATTERNS.md` — read first ~120 lines; admin pattern, signal pattern, migration convention.
- File encoding hex-dumps of all three fixture `InName.csv` files — `[Information]\r\n<MODEL>\r\n[V<ver>...\r\n` confirmed UTF-8, no BOM, CRLF line endings.

### Secondary (MEDIUM confidence)
- Python `csv` module behaviour with trailing-comma rows — [CITED: docs.python.org/3/library/csv.html] returns one empty string per trailing column; tested mentally against `_01,ch 1,Blue,Dynamic,`.
- Django `TextIOWrapper` + `newline=''` recipe — [CITED: docs.djangoproject.com/en/5.0/topics/http/file-uploads/] documented pattern for reading uploaded CSVs.

### Tertiary (LOW confidence — flagged for plan-time validation)
- None — every claim in this research is verified against either a file I read or a Python stdlib behaviour that is documented in the language reference.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every primitive is already in the project, every alternative was discarded with reasoning.
- Section-by-section parsing spec: HIGH — every column header, every default row, every channel-key shape was read from the fixture file.
- Console family detection: MEDIUM — algorithm is HIGH-confidence; the field-mismatch with CONTEXT.md (no `console_model` field exists) is a HIGH-confidence finding that downgrades the D-03 implementation to MEDIUM until the planner picks an option.
- DCA / `[StName]` model-mapping: MEDIUM — confidently identified the gap; the resolution (cut from scope vs add models) is a planner decision flagged in Open Questions.
- Pitfalls: HIGH — eight pitfalls, each verified against a code location or a fixture observation.

**Research date:** 2026-05-12
**Valid until:** 2026-06-12 (30 days — schema is stable, fixtures don't change, Django 5.x is current)
