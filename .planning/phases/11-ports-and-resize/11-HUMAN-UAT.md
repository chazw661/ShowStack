---
status: diagnosed
phase: 11-ports-and-resize
source: [11-VERIFICATION.md]
started: 2026-05-24T00:00:00Z
updated: 2026-05-25T00:00:00Z
pass: 2
---

## Current Test

[Pass 2 complete — 3 passed, 2 issues opened as GAP-11.6 + GAP-11.7]

## Tests

### 1. Re-UAT-1 — GAP-11.1 closed: port-row autocomplete per shape
expected: Open editor, drop a Device shape, click '+ Add port' on Top edge, type 1 char in the label input. Dropdown shows ONLY Device sources. DevTools shows single `?shape_class=X&q=Y` URL.
result: passed
notes: Charlie confirmed via Pass 2 browser test (2026-05-25).

### 2. Re-UAT-2 — GAP-11.2 closed: engineer-authored ports clickable (partial)
expected: Click+drag from authored port on any edge → connector forms; port dot visible (opacity 1).
result: issues
notes: "Bottom and Right ports correctly draw connector lines. Top and Left ports click pan-drags the shape instead. → GAP-11.6 (Phase 8 direction convention bleeds through: Top+Left have magnet:'passive' → validateMagnet rejects drag start)."

### 3. Re-UAT-3+4 — GAP-11.3 + GAP-11.4 closed: clean inspector + readable text (partial)
expected: Listbox count bounded; port-label text readable on dark navy.
result: issues
notes: "Listbox count appears bounded (no follow-up report). Text contrast: still too light when input is blurred/inactive; readable when focused. → GAP-11.7 (CSS specificity/cascade issue — Section 16 `color:#eee !important` should win in all states, awaiting DevTools Computed-tab readout to diagnose accurately)."

### 4. Re-UAT-5 — GAP-11.5 + PORT-06 closed: Σ(label widths) auto-expansion
expected: 5 'Channel N' ports on Console → shape auto-expands wide enough, no overlap; toast fires; no shrink on removal.
result: passed
notes: "Auto-expansion working per Charlie's Pass 2 report (no overlap reported in his summary, no toast/expansion complaint)."

### 5. Re-UAT-6 — SHP-RESIZE-02/03: min-size clamp + autosave + undo
expected: Drag BR handle → clamps at floor; autosave POST within 1500ms; Ctrl+Z reverses single step.
result: passed
notes: "Charlie: 'Resize works.' (Pass 2, 2026-05-25)."

## Summary

total: 5
passed: 3
issues: 2
pending: 0
skipped: 0
blocked: 0

## Pass 1 History (resolved 2026-05-24 via 11-07 + 11-08 + CR-01 fix)

Pass 1 reported 5 gaps (GAP-11.1..11.5). Gap-closure plans 11-07 + 11-08 + CR-01 shipped. Pass 2 confirmed 3/5 gaps fully closed; surfaced 2 new gaps below.

## Gaps

### GAP-11.6 — Top + Left authored ports not drag-source clickable
severity: high
source_test: Re-UAT-2 (Pass 2)
symptom: Clicking a Top or Left engineer-authored port pan-drags the shape instead of starting a connector. Bottom + Right work correctly.
root_cause: |
  Phase 8 directional convention: Top+Left ports = inbound (magnet:'passive'), Bottom+Right = outbound (magnet:true).
  `validateMagnet` in signal_flow_editor.js:791 explicitly rejects drag starts from passive magnets.
  Engineer-authored ports inherited this convention via `addAuthoredPort` line 305:
    magnet: (directionForEdge(edge) === 'in') ? 'passive' : true
  Charlie's expectation: engineer placed the port → engineer chose direction → all 4 edges should be drag sources.
decision: Drop direction rule for authored ports. Make all engineer-authored ports magnet:true (bidirectional). Generic Phase 8 ports (zero authored) preserve original directional convention.
fix_location: planner/static/planner/js/signal_flow_editor.js, addAuthoredPort() ~line 305
status: open

### GAP-11.7 — Port-label input text washed out when blurred
severity: medium
source_test: Re-UAT-3+4 (Pass 2)
symptom: Typed text in `.sfd-port-label-input` is readable when the input has focus, but too light to read when blurred.
root_cause: |
  Section 16 CSS rule `#sfd-inspector .sfd-port-label-input { color: #eee !important; }` (line 788-797)
  should apply in all states regardless of focus. Reported failure suggests another selector wins
  on blur — possibilities:
    - django-admin-interface override with higher specificity AND !important
    - A more specific selector elsewhere in signal_flow.css that targets the unfocused state
    - The Section 4 inspector-input base rule somehow ranking higher on blur
  Pure speculation without DOM diagnostic — do NOT patch without seeing the cascade.
diagnostic_needed: DevTools → select a blurred port-label input → Computed tab → expand `color` → screenshot showing which rule wins.
status: awaiting_data
