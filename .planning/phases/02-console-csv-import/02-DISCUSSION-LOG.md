# Phase 2: Console CSV Import — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-12
**Phase:** 02-console-csv-import
**Areas discussed:** Update vs replace semantics, Model-mismatch handling, Diff preview UX, Upload entry + post-import landing

---

## Pre-discussion lock-ins (from prior conversation)

Before discuss-phase began, the following were already locked in conversation between Charlie and Claude:

| Lock | Decision | Rationale |
|---|---|---|
| L-01 | Scope: InName + output name sections (Mix/Mtx/St/StMono/DCA for CL/QL; output equivalents for Rivage). Patches deferred. | Engineers track stems off auxes/matrices, so output names need to land in Phase 2. |
| L-02 | New `ConsoleImport` model — immutable snapshot entity, separate from Console. | Mental model: CSV = truth of what's on physical console; ShowStack console = what engineer uses for planning. |
| L-03 | User picks target Console before upload; import populates that console. | No surprise auto-creation of consoles. |
| L-04 | Auto-detect console family from `[Information]` block. | Files have CL5 / QL5 / CS-R5 model markers. |
| L-05 | Color storage uses Yamaha palette names (matches `YAMAHA_TO_HEX`). | Phase 1's reaper_export.py already declares this is Phase 2's job. |
| L-06 | DM7 deferred (no obvious export path); M7CL deferred to v2.1. | Confirmed by Charlie + REQUIREMENTS.md. |

---

## Update vs Replace Semantics

### Question 1: Default-row behavior

> When a ShowStack channel already exists with a custom name (e.g. 'Lead Vox' on ch01) and the CSV has the default 'ch01' label — what should happen?

| Option | Description | Selected |
|---|---|---|
| Smart-skip defaults | If the CSV row matches the console's factory default (`ch01`, `Blue`, `Dynamic`), treat as 'no real edit' and don't overwrite. Only import rows where engineer actually changed something. Preserves user labels with no clicks. | ✓ |
| Always overwrite | CSV wins every time. Simpler, but blows away custom labels. | |
| Per-row toggle in diff preview | Engineer ticks/unticks each row. Most control, more clicks. | |
| Always skip if ShowStack was edited | Track 'edited by user' flag; never overwrite. Requires new field, hard to fix mistakes. | |

**User's choice:** Smart-skip defaults
**Notes:** Detection rule for inputs: row is "default" iff name matches `ch ?N` pattern AND color=Blue AND icon=Dynamic. For output sections, planner derives equivalent rules from blank fixtures.

### Question 2: True conflicts (both customized, both differ)

> When the CSV says 'Lead Vox' on ch01 AND ShowStack already says 'Vocal 1' on ch01 (both customized, both differ) — what should happen?

| Option | Description | Selected |
|---|---|---|
| Show conflict in diff preview, user picks | Default CSV-wins, but flag conflicts visually with checkbox; engineer unticks rows to keep ShowStack value. | ✓ |
| CSV always wins | Newest data wins. Engineer re-edits after import if needed. | |
| ShowStack always wins | Engineer's manual edits sacred; CSV only fills blanks. | |

**User's choice:** Show conflict in diff preview, user picks

---

## Model-Mismatch Handling

### Question: What if CSV `[Information]` doesn't match selected console family?

> Engineer targets a QL5 console in ShowStack but uploads a CSV whose `[Information]` block says CL5 or Rivage — what should ShowStack do?

| Option | Description | Selected |
|---|---|---|
| Block with error | Refuse import. Show clear error message. Prevents silent data corruption (e.g. 288 Rivage rows → 64-channel QL5). | ✓ |
| Warn-and-confirm | Show warning, allow override. Higher risk if engineer clicks without reading. | |
| Allow silently with truncation | Just import what fits. Fastest UX, but data dropped silently. | |

**User's choice:** Block with error

---

## Diff Preview UX

### Question: How should the per-row diff display for large imports?

> Before commit, the engineer sees a diff of what will change. For a 288-row Rivage import, how should that diff look?

| Option | Description | Selected |
|---|---|---|
| Stats summary + filter to changed rows | Top-line counts + table showing only changed rows. Filter chips for Show unchanged / Errors only. Clean signal-to-noise. | ✓ |
| Full table, all 288 rows | Maximum transparency, lots of scrolling for unchanged rows. | |
| Stats only, no row table | Fastest commit, but engineer can't see what's changing TO before committing. | |

**User's choice:** Stats summary + filter to changed rows

---

## Upload Entry + Post-Import Landing

### Question 1: Where does the upload UI live?

> Where does the CSV upload UI live?

| Option | Description | Selected |
|---|---|---|
| Console detail page | Per-console 'Import CSV' button. Target console implicit. Most discoverable. | |
| Multitrack module landing page | Top of /audiopatch/multitrack/. Engineer picks console + uploads + lands in editor. | ✓ |
| Project Dashboard quick-action | Top-level Import card on /admin/. Most prominent, but detached from console list. | |
| All three | Same import view, three entry points. Maximum discoverability. | |

**User's choice:** Multitrack module landing page

### Question 2: What does CSV-05 'land in session editor' mean?

> After a successful import, what does CSV-05's 'land in session editor' mean?

| Option | Description | Selected |
|---|---|---|
| Land on Multitrack list w/ 'Create session' CTA | Redirect to /audiopatch/multitrack/ with success banner. Engineer chooses whether to make a session now or later. | ✓ |
| Auto-create a session, land in its editor | Import → instantly create new MultitrackSession → redirect to editor. Zero clicks to start tracking. | |
| Land back on the console detail page | Just return to start with success message. Doesn't satisfy CSV-05. | |

**User's choice:** Land on Multitrack list w/ 'Create session' CTA

---

## Claude's Discretion

The following implementation details were left to Claude / planner discretion:

- Default-row detection rules for output sections (`MixName`, `MtxName`, `StName`, `StMonoName`, `DCAName`) — derived from blank fixtures.
- Per-row error UI styling.
- Banner messaging copy.
- Dropdown-of-consoles UX details.
- Re-import semantics (uploading same CSV twice).
- Parse-error UX (malformed CSV file).

## Deferred Ideas

- Patch-section import (`[InPatch]`, `[OutPatch]`, `[PortRackPatch]`).
- DM7 Editor support.
- Re-apply a previous `ConsoleImport`.
- M7CL CSV path (already deferred to v2.1).
- Patch-aware track auto-population in Phase 1.
