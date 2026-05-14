---
phase: 04-nuendo-live-export
plan: 03
subsystem: infra

tags: [nuendo-live, fixture, binary-asset, mac-saved, template-injection]

# Dependency graph
requires:
  - phase: 04-nuendo-live-export
    plan: 02
    provides: build_nlpr() exporter that loads this fixture
provides:
  - planner/data/multitrack/nuendo_live_3_template.nlpr — Mac-saved empty Nuendo Live 3 project (63,714 bytes), the source-of-truth seed template for build_nlpr() deep-copy injection
affects: [04-05, build_nlpr-runtime]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Bundled vendor-binary fixture under planner/data/<module>/ (parallels planner/data/csv_fixtures/, planner/data/comm_config/pouchdb_factory/)"
    - "Mac-saved Nuendo Live 3 export: no Audio MFolderTrack wrapper, seed lives directly in MTrackList/<list name='Tracks'>"

key-files:
  created:
    - "planner/data/multitrack/nuendo_live_3_template.nlpr — 63714 bytes, utf-8, bare-CR line endings, Platform=MAC64 LE, 1 MAudioTrackEvent, 1 MFolderTrack (I/O Channels)"
  modified: []

key-decisions:
  - "Mac save platform accepted in lieu of Windows (D-02 amendment 2026-05-13 — Charlie has no Windows access). End users on Windows Nuendo Live can still open the exporter's output because the Platform attribute is metadata, not a load-time validation."
  - "Fixture has no Audio MFolderTrack — Mac Nuendo Live 3 places audio tracks directly inside MTrackList/<list name='Tracks'>. Plan 04-02 was refactored in a follow-up commit (d7075d2) to find the seed first and use its parent as the injection container, handling both Mac and Windows shapes."

patterns-established:
  - "Mac-saved Nuendo .nlpr structural template: MTrackList/<list name='Tracks'> contains both MFolderTrack(I/O Channels) AND MAudioTrackEvent (audio seed) as direct siblings, no Audio folder wrapper. Documented for future maintainers."

requirements-completed: [NLP-01 (export button + download path foundation), NLP-02 (template-injection source for opens-cleanly-in-Nuendo-Live-3 round trip)]
requirements-pending: []

# Metrics
duration: ~30min (mostly debugging Mac-vs-Windows structural divergence; fixture generation itself was ~5min in Nuendo Live 3)
completed: 2026-05-14
---

# Phase 4 Plan 03: Nuendo Live 3 Empty Template Fixture

## Objective

Generate and commit the bundled `.nlpr` template that `build_nlpr()`
deep-copies into every exported file. This was a Charlie-owned manual
checkpoint (autonomous=false) — Claude cannot produce a valid Nuendo
Live binary export from a CLI session.

## What Shipped

`planner/data/multitrack/nuendo_live_3_template.nlpr` — 63,714-byte
Mac-saved empty project file with exactly one default audio track
named `Audio 01` (outer Name `Track 001`).

## Generation Path

1. Charlie opened Nuendo Live 3 on Mac
2. File → New Project (default empty template)
3. File → Save As → `nuendo_live_3_template.nlpr` to scratch location
4. Quit Nuendo cleanly
5. `mkdir -p planner/data/multitrack` + `cp` into repo
6. Verified parse via Plan 02's `_load_template()`
7. Committed as `c79808a`

## Surprises / Deviations

Two structural realities of Mac-saved Nuendo Live 3 output that
diverged from the spec (which was reverse-engineered from
Windows-saved files only):

1. **No Audio MFolderTrack wrapper.** Windows-saved files nest audio
   tracks inside `MFolderTrack[name='Audio']`. Mac-saved files place
   them directly inside `MTrackList/<list name='Tracks'>`. Plan 02's
   `_find_audio_folder` helper assumed Windows shape and would have
   raised `ExportTemplateError`. **Fix: commit `d7075d2` refactored
   the exporter** to find the seed `MAudioTrackEvent` first and use
   its parent `<list>` as the injection container — works for both
   shapes.

2. **Raw control bytes inside `wide="true"` attribute values.**
   Nuendo's UTF-16 storage idiom embeds bytes like `\x01-\x08` inside
   attribute values that XML 1.0 strict mode rejects. lxml's default
   parser raised `XMLSyntaxError`. **Fix: same commit `d7075d2`**
   switched `_load_template()` to a recover-mode parser
   (`recover=True, huge_tree=True`).

A third concern surfaced during verification: the original D-09
uniqueness assertion in `test_ids_unique` over-flagged Steinberg's
reference-anchor pattern (`<root name='X' ID='N'/>` and class-less
`<obj name='X' ID='N'/>` both mirror an `<obj class='Y' ID='N'>`
body's ID — they are pointers, not duplicates). Same commit refined
the test predicate to scope uniqueness to `<obj @ID @class>` bodies
+ `<int name='RuntimeID|ID'>` values, with a separate
reference-integrity check.

## Verification

Against the committed fixture:
- `_load_template()` parses successfully via recover-mode parser
- `_find_seed_and_container()` returns `(MAudioTrackEvent#5054466768,
  <list name='Tracks'>)`
- `_scan_max_id()` returns 105553181739312; allocator base
  `max + 1000`
- End-to-end `build_nlpr()` with 5 mock tracks produces 108,862-byte
  output: 135/135 unique IDs among `<obj class='...'>` bodies +
  RuntimeID/ID int-values, 0 orphaned reference anchors
- `python manage.py test planner.tests.test_nuendo_live_export -v 2`
  → 3/3 pass
- `python manage.py test planner -v 0` → 95/95 pass (no regressions)

## HUMAN-UAT Remaining (NLP-02)

Charlie must still confirm the exporter's output actually opens
cleanly in Nuendo Live 3. The automated tests verify structure +
uniqueness; only Nuendo Live 3 itself can confirm Nuendo accepts
the output. Test plan: after Plan 04-05 (view + URL) lands, hit the
export endpoint with a real session, save the `.nlpr` to disk, drag
into Nuendo Live 3 on Charlie's Mac, confirm:

- File opens with no errors
- Track count matches enabled MultitrackTracks
- Names render correctly
- Colored tracks render with the right Farb palette index
- Tracks with no color match render in Nuendo's default appearance

## Self-Check: PASSED

- [x] Fixture committed to `planner/data/multitrack/`
- [x] Exactly 1 MAudioTrackEvent in the file
- [x] Platform attribute present (`MAC64 LE`)
- [x] `_load_template()` accepts it (recover-mode parser)
- [x] `build_nlpr()` produces structurally valid output against it
- [x] Test suite green (3/3 phase tests, 95/95 full suite)
- [ ] HUMAN-UAT round trip in Nuendo Live 3 — deferred to after 04-05
