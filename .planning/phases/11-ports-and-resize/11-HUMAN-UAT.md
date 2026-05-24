---
status: partial
phase: 11-ports-and-resize
source: [11-VERIFICATION.md]
started: 2026-05-24T00:00:00Z
updated: 2026-05-24T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Circuit-Label Autocomplete Regression (Phase 10 BC)
expected: Open the Signal Flow Diagrammer, select an existing connector, type 1 character in the circuit-label input. Dropdown appears within ~200ms with project-scoped suggestions in `label — source` format; click a row → label populates; type freeform → input accepts arbitrary text; reload → label persisted.
result: [pending]

### 2. Inspector Port-Authoring Block
expected: Select any of the 7 smart shape types → inspect the right-hand inspector panel. "Ports" section visible with 4 labeled sub-sections (Top / Bottom / Left / Right), each with a "+ Add port" button. Clicking "+ Add port" on "Top" creates a port row with ordinal, label input, and trash icon, and adds a port dot at the top edge midpoint.
result: [pending]

### 3. PORT-03 Autocomplete on Port Rows
expected: Click "+ Add port" on any edge, type 1 character in the label input. Phase 10 autocomplete combobox appears; selecting a row sets the port label; blurring with freeform text also commits; port label appears on the canvas shape.
result: [pending]

### 4. PORT-05 Connector Survival
expected: Add a port to a shape, draw a connector from another shape to that port, then click the trash icon on the port row. Connector's endpoint moves to the shape's edge midpoint — connector is NOT deleted. Remaining ports on that edge redistribute instantly.
result: [pending]

### 5. SHP-RESIZE-01: Handle Presence on All 7 Shape Types
expected: Select Console, Device, SpeakerArray, CommBeltPack, Generic, Processor, and Amp shapes one at a time. 4 teal corner handles appear at TL/TR/BL/BR on each. Handles disappear on deselect. Selecting a connector shows NO handles. Selecting two shapes simultaneously shows NO handles.
result: [pending]

### 6. SHP-RESIZE-02/03: Min-Size Clamping, Autosave, Undo
expected: (A) Drag BR handle of port-less Console inward → shape stops at 180×60 (ABSOLUTE_FLOOR). (B) Drag-end any shape → autosave POST fires within 1500ms (check DevTools Network). (C) Ctrl+Z after a resize → reverses in single undo step; reload shows persisted dimensions.
result: [pending]

### 7. PORT-06 Auto-Expansion + Toast
expected: On a fresh Console shape (180×60), click "+ Add port" on the Top edge 9 times (9 ports × 24px min-spacing > 180px default width). Shape width grows to accommodate; toast "Shape resized to fit ports." appears briefly. Removing a port does NOT shrink the shape.
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0
blocked: 0

## Gaps
