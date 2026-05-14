---
status: resolved
phase: 04-nuendo-live-export
source: [04-VERIFICATION.md]
started: 2026-05-14T15:55:33Z
updated: 2026-05-14T20:00:00Z
---

## Current Test

All required tests passed (1-5). Test 6 (optional D-03 missing-fixture banner) deferred.

## Tests

### 1. Click → download UX (NLP-01)
expected: Browser downloads `<session-name>.nlpr` with Content-Type `application/xml; charset=utf-8` when you click the "Export to Nuendo Live (.nlpr)" button on a real session. No 500 error, file size > 1KB.
result: passed (2026-05-14 — Charlie clicked Export to Nuendo Live (.nlpr), browser downloaded the file successfully)

### 2. Open the downloaded `.nlpr` in Nuendo Live 3 on Mac (NLP-02)
expected: File opens cleanly with no errors or warnings. Project loads.
result: passed (2026-05-14 — file opened in Nuendo Live 3 on Mac with no errors; all 21 tracks visible)

### 3. Verify track count and names inside Nuendo Live 3 (NLP-03)
expected: Exactly N tracks where N = session.enabled_tracks count. Each track displays its `resolved_label` in BOTH the Mixer (outer Name) AND the Track Inspector (inner DeviceAttributes/Name/String). Names match exactly — no truncation, no encoding artifacts.
result: passed (2026-05-14 — 21 tracks shown in Nuendo, names match ShowStack editor exactly: ch1-ch8, Pod 1-4, VOG, Spare, Vid 1L, Vid 1R, Vid 3-Vid 5)

### 4. Verify Farb palette indices render correctly inside Nuendo Live 3 (NLP-04)
expected: Tracks with Yamaha-palette colors render with the expected Nuendo color: Red→0, Orange→1, Yellow→2, Green→5, Sky Blue→8 (cyan), Blue→10, Purple→12, Pink→14.
result: passed (2026-05-14 — ch1 Red, ch2 Orange, ch3 Yellow, ch4 Yellow all rendered with the correct Yamaha→Farb palette indices)

### 5. Confirm default appearance for non-palette tracks (NLP-05)
expected: Tracks with non-palette hex overrides OR `Off`/`White`/missing source.color render with Nuendo's default gray appearance (no Farb element emitted).
result: failed initially (2026-05-14) — Pod 1, Pod 2 rendered Green; Vid 1L rendered Pink; ch5-ch8 / Pod 3-4 / VOG / Spare / Vid 1R-Vid 5 rendered Blue. Editor showed all of these as "no color" (slashed-circle swatch). Root cause: `MultitrackTrack.resolved_yamaha_name` D-04 step 2 fell back to `resolved_source.color` (Phase 2 channel-level color field from Rivage CSV import), but the editor's `resolved_color` consults `color_override` only — asymmetry surfaced as editor-vs-export mismatch.
fix: 9857aec — dropped D-04 step 2; resolution is now override-only (symmetric with `resolved_color`). CONTEXT.md D-04 amended with rationale.
result: passed after fix (2026-05-14 — Charlie re-tested and approved; no-override tracks now render default appearance in Nuendo Live 3)

### 6. (Optional) Exercise the D-03 missing-fixture graceful-degradation path
expected: Temporarily renaming `planner/data/multitrack/nuendo_live_3_template.nlpr` aside, then clicking the toolbar button, renders `editor.html` with the banner copy "Nuendo Live export is unavailable on this server — bundled template missing or malformed. Contact support." instead of returning 500.
result: [pending — optional]

## Summary

total: 6
passed: 5
issues: 0 (1 surfaced + resolved during UAT)
pending: 0
skipped: 1 (optional #6 D-03 banner check)
blocked: 0

## Gaps

### Gap 1: D-04 step 2 created editor-vs-export color mismatch (RESOLVED)
- surfaced: 2026-05-14 during HUMAN-UAT test 5
- root cause: `resolved_yamaha_name` fell back to `resolved_source.color`, but the editor's `resolved_color` does not — Rivage-imported channel colors flowed to Nuendo without preview
- fix: commit 9857aec — dropped D-04 step 2; CONTEXT.md D-04 amended
- status: resolved (Charlie re-tested and approved 2026-05-14)
