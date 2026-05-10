# Phase 1: Core Sessions, Track Editor & Reaper Export — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-09
**Phase:** 01-core-sessions-track-editor-reaper-export
**Areas discussed:** Source-channel model & color, Channel picker UX

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Source-channel model & color (Recommended) | Polymorphic FK strategy + color storage | ✓ |
| Channel-type coverage (Group / FX return / Cue) | Whether to add new models in Phase 1 | |
| Track editor JS stack | Sortable.js / HTMX / Alpine / jQuery | |
| Channel picker UX (TRK-06) | How "add a track" works | ✓ |

**Notes:** Channel-type coverage was implicitly resolved during the Source-channel discussion (D-03). JS stack and other skipped areas became Claude's Discretion in CONTEXT.md.

---

## Source-Channel Model & Color

### Q1: How should MultitrackTrack reference its source channel?

| Option | Description | Selected |
|--------|-------------|----------|
| Discriminator + ID (Recommended) | source_type CharField + source_id PositiveInt; helper resolves | ✓ |
| GenericForeignKey | Django contenttypes; idiomatic but extra JOIN | |
| Multiple nullable FKs | One FK per type, clean() enforces single-population | |
| Unify into ConsoleChannel base model | Migrate Input/Aux/Matrix/Stereo into a shared model | |

**User's choice:** Discriminator + ID.
**Notes:** No FK constraint = no migrations on existing models, no CASCADE risk to beta data, easy to extend. Orphan handling addressed in Q4.

---

### Q2: Where should the resolved track color come from?

| Option | Description | Selected |
|--------|-------------|----------|
| Track-only — color_override on MultitrackTrack (Recommended) | No migrations on existing channel models | ✓ |
| Add `color` (hex) to all 4 channel models now | Migration on Input/Aux/Matrix/Stereo | |
| Side ConsoleChannelMeta model keyed by (channel_type, channel_id) | Extra JOIN, additive | |
| Pull from ConsoleInput.group/dca | Re-use existing fields as poor-man's color | |

**User's choice:** Track-only.
**Notes:** Smallest blast radius. Decouples the milestone — Phase 2 CSV import is the natural place to populate channel-level colors when those land.

---

### Q3: What should source_type accept in Phase 1?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 1 ships: input + aux + matrix + stereo (Recommended) | Group/FX/Cue handled via TRK-07 manual track | ✓ |
| Add stub Group / FX / Cue models in Phase 1 | 3 extra migrations + admins now | |
| Phase 1 ships all 7 types but Group/FX/Cue behave like manual | Keeps TRK-06 wording intact | |

**User's choice:** input + aux + matrix + stereo + manual.
**Notes:** Group/FX/Cue model work captured as a Deferred Idea — likely v2.1 alongside Pro Tools.

---

### Q4: When a ConsoleInput/Aux/Matrix/Stereo row is deleted, what happens to MultitrackTrack rows?

| Option | Description | Selected |
|--------|-------------|----------|
| Convert to manual track (Recommended) | post_delete signal sets source_type='manual', copies last-known label/color | ✓ |
| Cascade delete the MultitrackTrack rows | Clean but engineers can lose tracks silently | |
| Block channel deletion (Protected) | ProtectedError forces explicit cleanup | |
| Leave the orphan, surface as 'channel deleted' | Editor shows warning badge | |

**User's choice:** Convert to manual track.
**Notes:** Consistent with the additive, beta-safe philosophy. Engineer never silently loses a track row.

---

## Channel Picker UX (TRK-06)

### Q1: How should the 'add a track' picker be structured?

| Option | Description | Selected |
|--------|-------------|----------|
| Modal with type tabs + sectioned checklist (Recommended) | [Inputs][Aux][Matrix][Stereo][Manual] tabs, checkable list per tab | ✓ |
| Single sectioned checklist (no tabs) | All types as collapsible sections in one modal | |
| Dual-pane include / exclude | Available left, selected right | |
| Inline 'add row' dropdown at bottom of track list | No modal; type+channel dropdown row | |

**User's choice:** Modal with type tabs + sectioned checklist.
**Notes:** User selected the preview mock-up — bulk-toggle for Aux/Matrix sections (TRK-09) lives natively here.

---

### Q2: Where do bulk include/exclude toggles (TRK-09) live?

| Option | Description | Selected |
|--------|-------------|----------|
| Inside the picker, per-type tab (Recommended) | Each tab has 'Select all / Clear' header | ✓ |
| Separate toggle row above the track list | Sticky 'Include all Aux' row in the editor | |
| Both — quick toggles in the editor + fine-grained in the picker | Most powerful, most state to keep in sync | |

**User's choice:** Inside the picker, per-type tab.
**Notes:** Single source of truth for set composition. Cleaner mental model.

---

### Q3: How should channels already in the session be displayed in the picker?

| Option | Description | Selected |
|--------|-------------|----------|
| Hide them — only show channels not yet in session (Recommended) | Picker is strictly an 'add' surface | ✓ |
| Show them checked-and-locked | Greyed out with 'already in session' tooltip | |
| Show them checked-and-editable (uncheck = remove) | Picker becomes include/exclude surface | |

**User's choice:** Hide them.
**Notes:** Removal happens via the editor row's [×] button per TRK-08.

---

### Q4: When tracks are added from the picker, where do they land in the track order?

| Option | Description | Selected |
|--------|-------------|----------|
| Append to the end, then user drags to reorder (Recommended) | Predictable; matches typical session-editor behavior | ✓ |
| Insert in console-channel order (sorted by channel number, by type) | Auto-canonical order | |
| Insert at the current selection point | Below highlighted track if any, else end | |

**User's choice:** Append to the end.
**Notes:** Simple, predictable. Engineer drags to reorder per TRK-05.

---

### Q5: When a new MultitrackSession is created, what's the initial track list?

| Option | Description | Selected |
|--------|-------------|----------|
| Empty — user opens picker to seed (Recommended) | Picker auto-opens on Inputs tab | ✓ |
| All input channels on the chosen console, enabled | Pre-populated, fast start | |
| All input channels, enabled=False (pre-shown but unticked) | Tracks exist but disabled | |

**User's choice:** Empty.
**Notes:** Pairs with Phase 5's POL-01 (`default_record`) once that lands — POL-01 becomes the principled auto-tick.

---

### Q6: How should the 'add manual track' (TRK-07) flow work?

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated 'Manual' tab in the picker with a small form (Recommended) | Same modal, single source of truth | ✓ |
| '+ Add manual track' button on the editor itself, outside the picker | Faster for 1-off but splits the mental model | |
| Manual track is created from a click track preset menu | Predefined ('Click', 'Talkback Return'…) | |

**User's choice:** Dedicated Manual tab.
**Notes:** Picker remains single source for adds. Form fields: Label (required), Color (optional swatch), Notes (optional), "+ Add another" to queue.

---

## Claude's Discretion

Areas where the user accepted Claude/planner judgement rather than pre-deciding:

- JS stack for the editor (Sortable.js + jQuery vs HTMX vs Alpine)
- Session creation flow (4-step wizard vs single form)
- Reaper RPP color packing bit layout
- Capacity bar placement
- Track number gap handling on reorder/delete
- Picker URL form (modal vs full page)
- DB indexes on `MultitrackTrack(source_type, source_id)`

## Deferred Ideas

- Group / FX return / Cue as first-class models — v2.1
- Channel-level color storage on Input/Aux/Matrix/Stereo — Phase 2 CSV import
- Pre-populated manual-track presets ('Click', 'Talkback', 'Room mics')
- `MultitrackTemplate` — Phase 3
- Pro Tools exporter — v2.1
- M7CL channel import — v2.1
