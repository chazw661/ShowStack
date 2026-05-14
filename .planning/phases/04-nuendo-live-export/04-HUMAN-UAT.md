---
status: partial
phase: 04-nuendo-live-export
source: [04-VERIFICATION.md]
started: 2026-05-14T15:55:33Z
updated: 2026-05-14T15:55:33Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Click → download UX (NLP-01)
expected: Browser downloads `<session-name>.nlpr` with Content-Type `application/xml; charset=utf-8` when you click the "Export to Nuendo Live (.nlpr)" button on a real session. No 500 error, file size > 1KB.
result: [pending]

### 2. Open the downloaded `.nlpr` in Nuendo Live 3 on Mac (NLP-02)
expected: File opens cleanly with no errors or warnings. Project loads.
result: [pending]

### 3. Verify track count and names inside Nuendo Live 3 (NLP-03)
expected: Exactly N tracks where N = session.enabled_tracks count. Each track displays its `resolved_label` in BOTH the Mixer (outer Name) AND the Track Inspector (inner DeviceAttributes/Name/String). Names match exactly — no truncation, no encoding artifacts.
result: [pending]

### 4. Verify Farb palette indices render correctly inside Nuendo Live 3 (NLP-04)
expected: Tracks with Yamaha-palette colors render with the expected Nuendo color: Red→0, Orange→1, Yellow→2, Green→5, Sky Blue→8 (cyan), Blue→10, Purple→12, Pink→14.
result: [pending]

### 5. Confirm default appearance for non-palette tracks (NLP-05)
expected: Tracks with non-palette hex overrides OR `Off`/`White`/missing source.color render with Nuendo's default gray appearance (no Farb element emitted).
result: [pending]

### 6. (Optional) Exercise the D-03 missing-fixture graceful-degradation path
expected: Temporarily renaming `planner/data/multitrack/nuendo_live_3_template.nlpr` aside, then clicking the toolbar button, renders `editor.html` with the banner copy "Nuendo Live export is unavailable on this server — bundled template missing or malformed. Contact support." instead of returning 500.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
