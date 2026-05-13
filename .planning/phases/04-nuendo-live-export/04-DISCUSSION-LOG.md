# Phase 4: Nuendo Live Export — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-13
**Phase:** 04-nuendo-live-export
**Areas discussed:** Template fixture lifecycle, Color → Farb resolution, ID & RuntimeID generation, Export button visibility & target_daw

---

## Gray-Area Selection

**Question:** Which areas do you want to discuss for Phase 4 (Nuendo Live Export)?

| Option | Description | Selected |
|--------|-------------|----------|
| Template fixture lifecycle | Where the empty .nlpr template lives; how it's generated; runtime fallback for missing/malformed fixture. | ✓ |
| Color → Farb resolution | How per-track hex overrides + channel-level Yamaha names + no-color collapse to Farb 0–15 or omit. | ✓ |
| ID & RuntimeID generation | Random vs sequential strategy for the per-track XML IDs. Affects testability. | ✓ |
| Export button visibility & target_daw | Always-on vs gated buttons; default DAW choice; enable nuendo_live in form. | ✓ |

**User's choice:** All four areas selected.
**Notes:** No scope creep; all four are real Phase 4 decisions that downstream agents need.

---

## Template Fixture Lifecycle

### Q1: Where should the bundled empty .nlpr template live in the repo?

| Option | Description | Selected |
|--------|-------------|----------|
| planner/data/multitrack/ | Mirrors planner/data/csv_fixtures/ and planner/data/comm_config/pouchdb_factory/ — existing convention for vendor-binary reference artifacts. (Recommended.) | ✓ |
| planner/fixtures/ | Django's loaddata convention; would muddy the convention for opaque binary blobs. | |
| Alongside exporter | planner/utils/nuendo_live/template.nlpr — co-locates fixture with code; less browseable in data/ tree. | |

**User's choice:** planner/data/multitrack/
**Notes:** Consistent with the pattern Phase 2 used for csv_fixtures and Comm Config used for pouchdb_factory.

### Q2: What minimum guarantees should the bundled template meet?

| Option | Description | Selected |
|--------|-------------|----------|
| Exactly 1 default audio track | The single MAudioTrackEvent inside the 'Audio' MFolderTrack named 'Audio 01' — matches spec template-injection step 1. | ✓ |
| Empty session settings | Stock 120 BPM / 48k / no markers / no signature changes. | ✓ |
| Saved on Windows + Nuendo Live 3 | Pin the WIN64 platform string. | ✓ |
| No audio interface routings | Leave Devices block / Input-Output Channels folder untouched. | ✓ |

**User's choice:** All four selected.
**Notes:** Charlie owns generation on a Windows + Nuendo Live 3 box before plan execution can finish.

### Q3: What should the exporter do at runtime if the fixture is missing or malformed?

| Option | Description | Selected |
|--------|-------------|----------|
| Render editor with error | Match Phase 1's no-enabled-tracks pattern (editor.html with export_error). (Recommended.) | ✓ |
| Fail fast with 500 | Loud failure in Railway logs; worse engineer UX. | |
| Validate at startup | Django system check at deploy time. More engineering for a one-file dependency. | |

**User's choice:** Render editor with error.
**Notes:** Consistent with the Phase 1 export error pathway.

---

## Color → Farb Resolution

### Q1: Should Phase 4 wire channel-level Yamaha colors into the export pipeline?

| Option | Description | Selected |
|--------|-------------|----------|
| Add `resolved_yamaha_name` helper | New property; reverse-lookup color_override→Yamaha name, else fall back to channel-level color. Leaves resolved_color (hex) untouched. (Recommended.) | ✓ |
| Extend `resolved_color` itself | Bigger blast radius; would also fix Reaper but breaks Phase 1's byte-stable contract. | |
| Hex-only, ignore channel color | Same as Reaper; channel-level Yamaha colors stay export-invisible. | |

**User's choice:** Add `resolved_yamaha_name` helper.
**Notes:** Preserves Phase 1 Reaper contract; isolates Phase 4 surface area.

### Q2: When color_override is a hex that doesn't match Yamaha palette exactly, how should it map to Farb?

| Option | Description | Selected |
|--------|-------------|----------|
| Omit Farb (Nuendo default) | Engineer's exact-shade signal honored by not guessing; Nuendo default appearance. (Recommended.) | ✓ |
| Nearest Farb by RGB distance | Every hex gets some color; subjective and surprises engineers. | |
| Reject the export | Forces palette discipline; hostile to existing swatch picker UX. | |

**User's choice:** Omit Farb (Nuendo default).

### Q3: Rivage console scope — do we need a separate Rivage→Farb mapping table?

| Option | Description | Selected |
|--------|-------------|----------|
| Piggyback on CL/QL table | Phase 2 already collapses Rivage colors to CL/QL palette. One table covers all. (Recommended.) | ✓ |
| Build separate Rivage table | Would require reworking YAMAHA_COLOR_CHOICES in a migration — out of Phase 4 scope. | |
| Defer Rivage colors | CL/QL gets Farb; Rivage gets omit. Acknowledges the Phase 2 collapse as lossy. | |

**User's choice:** Piggyback on CL/QL table.
**Notes:** Closes STATE.md open question #5.

### Q4: Where should the Yamaha→Farb mapping table live?

| Option | Description | Selected |
|--------|-------------|----------|
| In nuendo_live_export.py | Mirrors YAMAHA_TO_HEX pattern in reaper_export.py. Each exporter owns its mappings. (Recommended.) | ✓ |
| In reaper_export.py | Conflates two unrelated targets; Reaper has no use for Farb. | |
| Shared planner/utils/color_maps.py | New module just for color tables; premature factoring for two tables. | |

**User's choice:** In nuendo_live_export.py.

---

## ID & RuntimeID Generation

### Q1: How should the exporter generate unique IDs and RuntimeIDs?

| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic sequential | Scan template once for max ID; allocate from max+1000. Deterministic; no collision risk. (Recommended.) | ✓ |
| Random 32-bit ints | uuid.uuid4().int & 0xFFFFFFFF. Non-deterministic; near-zero collision. | |
| Hash-derived per-track | hash((session.id, track.id, kind)). Couples export to DB IDs. | |

**User's choice:** Deterministic sequential.

### Q2: How should the test suite verify ID uniqueness and stability?

| Option | Description | Selected |
|--------|-------------|----------|
| Uniqueness assertion | Parse output, collect IDs/RuntimeIDs, assert set size == count. Directly verifies NLP-06. (Recommended.) | ✓ |
| Snapshot byte-for-byte diff | Diff against committed .nlpr snapshot. Brittle to format tweaks. | |
| Structural diff (parse + compare) | Walk parsed tree, assert per-track structure. (Recommended pairing — not selected.) | |
| Manual round-trip only | Skip automated tests entirely. | |

**User's choice:** Uniqueness assertion only.
**Notes:** Explicitly chose a leaner test suite — single automated assertion + manual round-trip in Nuendo Live 3 for everything else.

### Q3: Should the existing template track's IDs be reused for track 1?

| Option | Description | Selected |
|--------|-------------|----------|
| Replace all IDs | Every track 1..N gets fresh IDs from the allocator. Simpler invariant. (Recommended.) | ✓ |
| Reuse template IDs for track 1 | Lower XML churn vs template; introduces "track 1 vs 2..N" inconsistency. | |

**User's choice:** Replace all IDs.

---

## Export Button Visibility & target_daw

### Q1: How should the editor toolbar present the three export options?

| Option | Description | Selected |
|--------|-------------|----------|
| All three always shown | Third button alongside two Reaper buttons. Matches current Phase 1 pattern. (Recommended.) | ✓ |
| Gate buttons on target_daw | Show only buttons matching session.target_daw. Forces metadata edit to switch formats. | |
| All three + emphasize active DAW | Visual priority based on target_daw. More CSS for marginal value. | |

**User's choice:** All three always shown.

### Q2: Should target_daw='nuendo_live' be enabled in the new-session form, and what's the default?

| Option | Description | Selected |
|--------|-------------|----------|
| Enable, keep `reaper` default | Remove the disable gate; new sessions default to reaper. (Recommended.) | ✓ |
| Enable, no default | Force engineer to pick a DAW each time. | |
| Enable, default to last-used | Remember per-user; adds preference state and a small migration. | |

**User's choice:** Enable, keep `reaper` default.

### Q3: Should the Nuendo Live button be standard secondary styling or visually distinct?

| Option | Description | Selected |
|--------|-------------|----------|
| Match Reaper buttons | Same mts-btn classes; consistent visual grammar. (Recommended.) | ✓ |
| Distinct accent | Different color; cosmetic, better in a polish pass. | |

**User's choice:** Match Reaper buttons.

### Q4: Single .nlpr button or also a Nuendo Live template variant?

| Option | Description | Selected |
|--------|-------------|----------|
| Single .nlpr only | No separate track-archive format exists in Nuendo Live — spec says .nlpr is the only target. (Recommended.) | ✓ |
| Investigate before committing | Research alternative import formats; adds time. | |

**User's choice:** Single .nlpr only.

---

## Wrap-Up

**Question:** Any other gray areas to surface before writing CONTEXT.md?

**User's choice:** I'm ready for context.

## Claude's Discretion

Captured in CONTEXT.md `<decisions>` under "Claude's Discretion":
- Wave structure for plan execution
- Module-load vs first-export fixture parse timing
- Whether to add a Django system check for fixture
- `lxml` version pin
- CRLF / encoding preservation strategy
- Permission gate on export view (match Phase 1 post-CR-01/CR-02 state)
- Filename: `<_safe_filename(session.name)>.nlpr`
- Whether `resolve_yamaha_name` is a property or a function
- Whether to expose `build_nlpr` from a public module path

## Deferred Ideas

Captured in CONTEXT.md `<deferred>`:
- Snapshot byte-for-byte and structural regression tests
- Automated round-trip-via-real-Nuendo test
- Channel-level color flowing through `resolved_color` (hex) for Reaper
- Nearest-Farb-by-RGB-distance mapping
- Nuendo Live track-template variant (permanently out of scope per spec)
- Separate Rivage→Farb mapping table
- Pro Tools exporter
- target_daw-driven button gating
- Per-user last-used target_daw default
- Django system check for fixture
