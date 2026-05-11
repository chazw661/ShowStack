---
status: partial
phase: 01-core-sessions-track-editor-reaper-export
source: [01-VERIFICATION.md]
started: 2026-05-11T00:00:00Z
updated: 2026-05-11T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Open exported .RPP in Reaper 7.x and confirm project loads
expected: Reaper opens the file with one track per enabled MultitrackTrack, names + colors as configured, no errors
result: [pending]
why_human: Requires Reaper 7.x install + display. The 42 automated reaper_export tests cover the file-format structure (PEAKCOL, MAINSEND, NAME tokens, GUID consistency, six required tokens per block), but the actual Reaper-opens-it acceptance criterion (RPP-01..05 + ROADMAP SC #5) can only be confirmed by a live Reaper session.

### 2. Drag-reorder a track in the editor and confirm the row numbers update + new order persists after reload
expected: Sortable.js fires onEnd → POST /reorder/ → row numbers renumber 1..N client-side; reloading the page shows the same order
result: [pending]
why_human: Drag UX (cursor change, ghost row, drop animation) is a visual/interactive behavior; XHR contract is verified via 42 unit tests + URL-resolve checks but the user-facing drag behavior needs a real browser.

### 3. Color-swatch picker visual: click a track's swatch, then click a color swatch in the popover
expected: Popover opens below-left of the clicked swatch; clicked color fills the row swatch immediately; right-click on swatch clears it back to the dashed-border empty state
result: [pending]
why_human: setProperty('background-color', value, 'important') is verified in code (54 setProperty hits, no direct .style.X = Y assignments per CLAUDE.md), but the visual fill, popover positioning via getBoundingClientRect, and right-click clear are interactive behaviors.

### 4. Capacity bar transitions: under → at → over
expected: With recorder_capacity=4 and 3 tracks, bar shows '3 / 4' partially filled blue; add a 4th track, bar fills + shows '4 / 4'; add a 5th, bar turns red and shows '5 / 4 — 1 over capacity'
result: [pending]
why_human: Server-side classes (mts-capacity--under/--at/--over) and counts (total_count, over_count) are verified in code, but the live state transition (and the real visual width of the under-fill bar — see WR-01 in 01-REVIEW.md) needs a browser. **WR-01 is a known bug — under-capacity fill always renders 100% wide because no JS reads data-fill-percent.**

### 5. + New Session flow ends in editor with picker auto-opened on Inputs tab
expected: Submit form → land on /audiopatch/multitrack/<id>/ → picker overlay visible immediately, Inputs tab active (D-12)
result: [pending]
why_human: auto_open_picker context flag wires to a DOMContentLoaded shim that calls mtsOpenPicker('inputs') — verified in code, but the rendered modal visibility + tab active state needs a browser.

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
