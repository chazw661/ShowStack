# Milestone v2.0 Requirements — Multitrack Session Builder

**Defined:** 2026-05-09
**Core Value:** ShowStack knows your patch, your labels, and your gear; once entered, that data drives every export your show needs.

Source: `multitrack_session_builder_spec.md` (repo root) is the canonical spec; this file is the falsifiable, user-centric ledger that the roadmap maps phases against.

## v2.0 Requirements

### Session Management — MTS

- [ ] **MTS-01**: User can create a new MultitrackSession by picking a project console, target DAW (Reaper or Nuendo Live), feed-source mode (`console_dante` / `rio_direct` / `custom`), and track-order mode (`console` / `dante`).
- [ ] **MTS-02**: User can name a session and rename it later; name is unique per project.
- [ ] **MTS-03**: User can list all sessions for the current project on a module landing page, with create/duplicate/delete actions.
- [ ] **MTS-04**: User can edit session metadata (name, target DAW, feed source, track-order mode, recorder capacity, notes) without losing track customizations.
- [ ] **MTS-05**: User can delete a session and its tracks.
- [ ] **MTS-06**: User can duplicate an existing session into a new one as a starting point.

### Track Editor — TRK

- [ ] **TRK-01**: User can see all tracks for a session in an ordered list, with track number, source channel ref (and channel type — input / aux / matrix / group / FX return / cue), resolved label, resolved color, enabled state, and notes.
- [ ] **TRK-02**: User can enable / disable individual tracks; only enabled tracks appear in exports.
- [ ] **TRK-03**: User can override a track's label (overrides the source channel's name).
- [ ] **TRK-04**: User can override a track's color via a swatch picker (overrides the source channel's color).
- [ ] **TRK-05**: User can reorder tracks via drag-and-drop; the new order persists.
- [ ] **TRK-06**: User can add a track to a session at any time by picking from any available console channel — **input channels, Aux outputs, Matrix outputs, Group outputs, FX returns, and Cue outputs are all first-class selectable sources**, not just the initial seed list. Channels are presented grouped by type with type filters.
- [ ] **TRK-07**: User can add a manual track that has no source channel (e.g. click track, room mic, talkback return) with a hand-entered label and color.
- [ ] **TRK-08**: User can remove a track from the session — works for both manual tracks and tracks tied to a console source channel (removal does not delete the underlying ConsoleChannel).
- [ ] **TRK-09**: User can bulk include or exclude all Aux, Matrix, and Group source channels via collapsible section toggles; bulk toggles seed the selection, and individual tracks can still be added or removed afterwards via TRK-06 / TRK-08.
- [ ] **TRK-10**: When `recorder_capacity` is set, the editor shows a count vs capacity ("47 / 64"); over-capacity is highlighted red ("72 / 64 — 8 over") but does not block export.

### Reaper Exporter — RPP

- [ ] **RPP-01**: User can export the current session as a Reaper `.RPP` project file with one track per enabled track.
- [ ] **RPP-02**: Track names in the exported `.RPP` match each track's resolved label.
- [ ] **RPP-03**: Track colors in the exported `.RPP` match each track's resolved color, mapped from Yamaha palette to Reaper packed RGB.
- [ ] **RPP-04**: Track order in the exported `.RPP` matches the session's `track_order_mode`.
- [ ] **RPP-05**: User can also export a Reaper track template (`.RTrackTemplate`) to merge into an existing project.

### Nuendo Live Exporter — NLP

- [x] **NLP-01
**: User can export the current session as a Nuendo Live 3 `.nlpr` file via the bundled empty-template injection path.
- [x] **NLP-02
**: The exported `.nlpr` loads in Nuendo Live 3 without errors.
- [x] **NLP-03
**: Each track's name renders correctly inside Nuendo Live (outer `Name` and inner `DeviceAttributes → Name → String` match).
- [x] **NLP-04
**: Each track's color renders correctly using a `Farb` palette index (Yamaha CL/QL → Farb mapping table from the spec).
- [x] **NLP-05
**: Tracks with no assigned color export with `Farb` omitted, so they use the Nuendo Live default appearance.
- [x] **NLP-06
**: All `ID` and `RuntimeID` values in the exported file are unique within the document.

### Console CSV Import — CSV

- [x] **CSV-01
**: User can upload a Yamaha CL/QL channel-name CSV (Studio Manager / CL Editor / Console File Converter export) and have it populate or update the console's channels in ShowStack.
- [x] **CSV-02
**: User can upload a Yamaha Rivage PM channel-labels CSV and have it populate or update the console's channels.
- [x] **CSV-03
**: Imported channel labels and colors map onto existing `ConsoleChannel` records when present, otherwise create new ones; user is shown a per-row diff summary before commit.
- [x] **CSV-04
**: Import errors surface clearly per row (missing required field, unsupported color code) without aborting the whole import.
- [x] **CSV-05
**: After a successful import, user lands in the session editor with the imported channels available as track sources.

### Templates — TPL

- [x] **TPL-01
**: User can save the current session's structure (target DAW, feed source, track-order mode, include-aux/matrix/groups flags, color scheme, naming pattern) as a named `MultitrackTemplate` scoped to the project.
- [x] **TPL-02
**: User can apply a template to a new session, seeding the track list and metadata; user can still override per-track values after.
- [x] **TPL-03
**: User can list, rename, and delete templates from the module landing page.
- [x] **TPL-04
**: Template save / load buttons, placement, and modal behavior visually and behaviorally match existing ShowStack template patterns (e.g. Comm Config, Mic Tracker).

### Polish — POL

- [ ] **POL-01**: Each `ConsoleChannel` carries a `default_record` boolean; new sessions pre-check tracks where `default_record=True` so engineers don't have to re-enable the obvious ones each gig.
- [ ] **POL-02**: Each `ConsoleChannel` carries a `default_record_color` (hex) used as the seed color for new tracks unless overridden.

## Future Requirements (deferred to v2.1+)

- **PT-01**: Pro Tools session-data `.txt` or AAF exporter — deferred until tester access secured (Pro Tools Intro free-tier viability or beta-tester recruit).
- **M7CL-01**: Yamaha M7CL channel import — deferred until a CSV export path is confirmed; if none, a `.M7C` binary parser is separate work.
- **Other-Console**: DiGiCo, Allen & Heath, Avid console families — separate effort if/when demand surfaces.

## Out of Scope (explicit exclusions)

These were considered and deliberately excluded from v2.0. Reopening any of them needs a milestone-boundary decision.

- Setlist / song-marker timeline generation in exported sessions
- File-naming pattern automation for recorded files (only naming the *tracks*, not the captured files)
- Recording-rig modeling (recorders, interfaces) inside ShowStack
- Show notes / per-recording-session log
- Virtual-soundcheck asset tracking (file-management workflow)
- Post-show delivery automation (cloud links, manifests)
- Real-time DAW control (transport, marker drop) — replaces no vendor protocol
- A replacement for the Yamaha Console Extension protocol — this exporter sits *alongside* it, not against it

## Traceability

Mapping of REQ-IDs to phases (filled in 2026-05-09 by `/gsd-roadmap` for the v2.0 Multitrack Session Builder milestone).

| Requirement | Phase | Status |
|-------------|-------|--------|
| MTS-01 | Phase 1 | Pending |
| MTS-02 | Phase 1 | Pending |
| MTS-03 | Phase 1 | Pending |
| MTS-04 | Phase 1 | Pending |
| MTS-05 | Phase 1 | Pending |
| MTS-06 | Phase 1 | Pending |
| TRK-01 | Phase 1 | Pending |
| TRK-02 | Phase 1 | Pending |
| TRK-03 | Phase 1 | Pending |
| TRK-04 | Phase 1 | Pending |
| TRK-05 | Phase 1 | Pending |
| TRK-06 | Phase 1 | Pending |
| TRK-07 | Phase 1 | Pending |
| TRK-08 | Phase 1 | Pending |
| TRK-09 | Phase 1 | Pending |
| TRK-10 | Phase 1 | Pending |
| RPP-01 | Phase 1 | Pending |
| RPP-02 | Phase 1 | Pending |
| RPP-03 | Phase 1 | Pending |
| RPP-04 | Phase 1 | Pending |
| RPP-05 | Phase 1 | Pending |
| CSV-01 | Phase 2 | Pending |
| CSV-02 | Phase 2 | Pending |
| CSV-03 | Phase 2 | Pending |
| CSV-04 | Phase 2 | Pending |
| CSV-05 | Phase 2 | Pending |
| TPL-01 | Phase 3 | Pending |
| TPL-02 | Phase 3 | Pending |
| TPL-03 | Phase 3 | Pending |
| TPL-04 | Phase 3 | Pending |
| NLP-01 | Phase 4 | Complete |
| NLP-02 | Phase 4 | Pending |
| NLP-03 | Phase 4 | Pending |
| NLP-04 | Phase 4 | Pending |
| NLP-05 | Phase 4 | Pending |
| NLP-06 | Phase 4 | Complete |
| POL-01 | Phase 5 | Pending |
| POL-02 | Phase 5 | Pending |

**Coverage:** 38 / 38 v2.0 requirements mapped to exactly one phase. No orphans.
