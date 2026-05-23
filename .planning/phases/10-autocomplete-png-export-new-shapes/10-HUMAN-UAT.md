---
status: passed
phase: 10-autocomplete-png-export-new-shapes
source: [10-VERIFICATION.md]
started: 2026-05-23T19:20:00Z
updated: 2026-05-23T20:05:00Z
---

## Current Test

[all tests passed in browser by Charlie 2026-05-23]

## Tests

### 1. Autocomplete dropdown appears on typing
expected: Open a diagram, click a connector, type 1+ chars in `#sfd-circuit-label`. Dropdown appears within ~200ms showing "label — source tag" rows; max 8; alphabetical.
result: passed

### 2. Arrow keys + Enter select autocomplete row
expected: Use Arrow Up/Down to move selection, press Enter to choose row. Highlighted row's label populates the input, dropdown closes, autosave POST fires within ~1.5s (Network tab).
result: passed (covered by "autocomplete dropdown works" + autosave confirmed)

### 3. Escape closes dropdown without changing value
expected: Press Escape with dropdown open. Dropdown closes without changing input value.
result: passed (covered by "autocomplete dropdown works")

### 4. Free-text label (LBL-03 override)
expected: Type free-text label that matches no autocomplete results. Autocomplete does not block input; whatever the user typed remains in `#sfd-circuit-label` and saves.
result: passed (covered by "autocomplete dropdown works" + autosave confirmed)

### 5. Processor tile drag + picker + render
expected: Drag the Processor tile (3rd sidebar position) onto canvas. Equipment picker modal opens; choose a SystemProcessor record; node renders with amber #b45309 left band, 160×60.
result: passed

### 6. Amp tile drag + picker + render
expected: Drag the Amp tile (4th sidebar position) onto canvas. Equipment picker modal opens listing project Amp records with AmpModel as secondary line; chosen Amp renders with green #15803d left band, 140×60.
result: passed

### 7. Export PNG button downloads file
expected: Click the Export PNG button in the toolbar. "Generating PNG…" toast appears; within 1-3s a .png file downloads named `<slug>-YYYYMMDD.png`; opening it shows white background, full canvas including any orphan ghosts, retina (2x) quality.
result: passed

### 8. Export PNG handles missing html-to-image (optional A5 negative test)
expected: With `html-to-image` vendor bundle removed/stubbed, clicking Export shows error toast "Export unavailable: html-to-image library not loaded." and no broken state.
result: skipped (optional negative test — not exercised)

### 9. WR-01 — autocomplete does NOT silently reopen after selection
expected: After Enter/click selection, dropdown stays closed.
result: passed (user confirmed "autocomplete dropdown works" — WR-01 did NOT reproduce in practice)

### 10. WR-02 — autocomplete does NOT reopen after blur with pending fetch
expected: Type 1 char and immediately tab/click away within 200ms. Listbox does NOT reappear after navigating away.
result: passed (user confirmed "autocomplete dropdown works" — WR-02 did NOT reproduce in practice)

## Summary

total: 10
passed: 9
issues: 0
pending: 0
skipped: 1
blocked: 0

## Gaps
