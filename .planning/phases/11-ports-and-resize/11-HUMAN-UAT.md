---
status: diagnosed
phase: 11-ports-and-resize
source: [11-VERIFICATION.md]
started: 2026-05-24T00:00:00Z
updated: 2026-05-24T18:00:00Z
---

## Current Test

[testing complete — routed to gap closure]

## Tests

### 1. Circuit-Label Autocomplete Regression (Phase 10 BC)
expected: Open the Signal Flow Diagrammer, select an existing connector, type 1 character in the circuit-label input. Dropdown appears within ~200ms with project-scoped suggestions in `label — source` format; click a row → label populates; type freeform → input accepts arbitrary text; reload → label persisted.
result: failed
notes: "Autocomplete reads from the wrong source — clicking on a Device shape shows Amp inputs in autocomplete. Plus: autocomplete listbox text remains stranded on the right sidebar after the dropdown closes (visible 'Ch 2 — Amp Channel' row in Image #2 inspector). Matches WR-02 from code review."

### 2. Inspector Port-Authoring Block
expected: Select any of the 7 smart shape types → inspect the right-hand inspector panel. "Ports" section visible with 4 labeled sub-sections (Top / Bottom / Left / Right), each with a "+ Add port" button. Clicking "+ Add port" on "Top" creates a port row with ordinal, label input, and trash icon, and adds a port dot at the top edge midpoint.
result: passed
notes: "4 edge sections + '+ Add port' + trash icon all visible and working."

### 3. PORT-03 Autocomplete on Port Rows
expected: Click "+ Add port" on any edge, type 1 character in the label input. Phase 10 autocomplete combobox appears; selecting a row sets the port label; blurring with freeform text also commits; port label appears on the canvas shape.
result: partial
notes: "Combobox attaches to each port-label input (approved). BUT label text inside port-row input is too light to see (Image #1 — 'INput 1' placeholder barely visible on dark inspector background). Same wrong-source autocomplete issue from test 1 applies here too."

### 4. PORT-05 Connector Survival
expected: Add a port to a shape, draw a connector from another shape to that port, then click the trash icon on the port row. Connector's endpoint moves to the shape's edge midpoint — connector is NOT deleted. Remaining ports on that edge redistribute instantly.
result: failed
notes: "BLOCKER — cannot draw a connector from any authored port. Clicking on a port lets the user move the shape instead of starting a link drag. PORT-05 trash survival cannot be tested until connector draw works."

### 5. SHP-RESIZE-01: Handle Presence on All 7 Shape Types
expected: Select Console, Device, SpeakerArray, CommBeltPack, Generic, Processor, and Amp shapes one at a time. 4 teal corner handles appear at TL/TR/BL/BR on each. Handles disappear on deselect. Selecting a connector shows NO handles. Selecting two shapes simultaneously shows NO handles.
result: passed
notes: "4 teal corner resize handles confirmed on selected shapes."

### 6. SHP-RESIZE-02/03: Min-Size Clamping, Autosave, Undo
expected: (A) Drag BR handle of port-less Console inward → shape stops at 180×60 (ABSOLUTE_FLOOR). (B) Drag-end any shape → autosave POST fires within 1500ms (check DevTools Network). (C) Ctrl+Z after a resize → reverses in single undo step; reload shows persisted dimensions.
result: skipped
notes: "Not exercised in this session — re-test after gaps closed."

### 7. PORT-06 Auto-Expansion + Toast
expected: On a fresh Console shape (180×60), click "+ Add port" on the Top edge 9 times (9 ports × 24px min-spacing > 180px default width). Shape width grows to accommodate; toast "Shape resized to fit ports." appears briefly. Removing a port does NOT shrink the shape.
result: failed
notes: "Shape does not expand enough when ports are added (Image #2 — 'Test 1608' Device shape has 5 port labels 'INput Input 2 Inoput Ch 2 Ch 1' on Top edge all overlapping inside ~180px width). computeMinSize is not accounting for label width sums correctly."

## Summary

total: 7
passed: 2
issues: 4
pending: 0
skipped: 1
blocked: 0

## Gaps

### GAP-11.1 — Authored port autocomplete reads wrong source
severity: high
evidence: "Image #2 shows 'Ch 2 — Amp Channel' suggestion appearing in the Top edge port row of a Device shape ('Test 1608'). Device shape ports should suggest from Device's I/O label catalog, not from Amp Channel."
likely_cause: "The Phase 10 `labelAutocompleteUrl` is a single project-scoped endpoint. Plan 11-03 wires it directly to every port input regardless of which shape class owns the port. The endpoint either returns all sources, or the per-shape filtering at the backend was never added for the new port-label use case."
files: planner/static/planner/js/signal_flow_editor.js, planner/views.py (autocomplete endpoint)

### GAP-11.2 — Cannot draw connector from authored ports (BLOCKER for PORT-05)
severity: critical
evidence: "User reports clicking on an authored port causes the shape to move (drag-pan) instead of starting a link drag. No connector appears."
likely_cause: "Port dot has `opacity: 0` (hover-revealed per Phase 8 CSS Section 7). The CSS hover-reveal selector at `.joint-port body` may not match the authored ports because they were added via `cell.addPort(...)` with a custom group rather than via `portsForRect()`. With opacity 0 and no hover-reveal, JointJS sees no clickable magnet — the click bubbles up to the cell drag handler. Alternative cause: validateMagnet path may not include authored ports' magnet attribute correctly."
files: planner/static/planner/css/signal_flow.css (Section 7 hover-reveal selectors), planner/static/planner/js/signal_flow_editor.js (addAuthoredPort port attrs)

### GAP-11.3 — Stale autocomplete listbox accumulates on inspector (WR-02 manifests in production)
severity: high
evidence: "Image #2 shows 'Ch 2 — Amp Channel' row stranded at the bottom of the inspector panel after dropdown should have closed. WR-02 code-review warning is now a real visible bug."
likely_cause: "Each `attachAutocompleteToInput` call appends a fresh `<ul.sfd-ac-listbox>` to the input's `.sfd-field` ancestor (`portAuthorBlock`). `refreshPortAuthorBlock` clears `<li>` rows but not the orphaned listbox <ul>s. Stable IDs collide; old listboxes never get cleaned up."
files: planner/static/planner/js/signal_flow_editor.js (attachAutocompleteToInput container lookup + refreshPortAuthorBlock cleanup)

### GAP-11.4 — Port label input text too faint to see
severity: medium
evidence: "Image #1 shows 'INput 1' placeholder text barely visible on the dark navy inspector background."
likely_cause: "CSS Section 16 `.sfd-port-label-input` color rule missing or set to a too-light value for the dark inspector theme. Placeholder color may also be inheriting default browser styles (~#aaa) which is too light on dark navy."
files: planner/static/planner/css/signal_flow.css (Section 16 .sfd-port-label-input)

### GAP-11.5 — Auto-expansion insufficient — port labels overlap inside shape
severity: high
evidence: "Image #2 shows 'Test 1608' Device shape with 5 top-edge port labels 'INput Input 2 Inoput Ch 2 Ch 1' all overlapping in ~180px width."
likely_cause: "`computeMinSize` math undercounts. Likely: port-count × MIN_PORT_SPACING is being used but per-edge label-width SUM is not added correctly. Per RESEARCH §Q2, top/bottom edges should add Σ(label widths) + (count-1) × spacing + padding, not just count × spacing."
files: planner/static/planner/js/signal_flow_editor.js (computeMinSize, maybeAutoExpand)
