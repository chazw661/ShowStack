---
status: partial
phase: 11-ports-and-resize
source: [11-VERIFICATION.md]
started: 2026-05-24T00:00:00Z
updated: 2026-05-24T21:35:00Z
pass: 2
---

## Current Test

[awaiting human re-testing — Pass 2 after gap-closure cycle]

## Tests

### 1. Re-UAT-1 — GAP-11.1 closed: port-row autocomplete per shape
expected: Open editor, drop a Device shape, click '+ Add port' on Top edge, type 1 char in the label input. Dropdown shows ONLY Device Input / Device Output rows (no Amp Channel). Repeat on a Console → only Console Input / Console Aux Out. Repeat on an Amp → only Amp Channel. Repeat on a Processor → P1/Galaxy Input/Output. Repeat on a SpeakerArray, CommBeltPack, or Generic → falls back to all 9 sources (intentional — these have no labeled-channel catalog). On a connector circuit-label input → still gets all 9 sources (Phase 10 BC preserved). DevTools Network tab should show `?shape_class=showstack.Device&q=<char>` for port rows (single `?`, single `&`) and bare `?q=<char>` for circuit-label.
result: pending

### 2. Re-UAT-2 — GAP-11.2 closed: engineer-authored ports clickable
expected: Drop a Device shape, add a port on the Top edge via inspector. Port dot is visible immediately (opacity 1, not hidden). Click+drag from the port — a connector line forms and follows the cursor. Drop on another shape's port → connector lands and persists. Previously the click pan-dragged the shape instead. Backward compat: shapes with zero authored ports still get the Phase 8 hover-reveal generic ports (opacity 0 until hovered).
result: pending

### 3. Re-UAT-3+4 — GAP-11.3 + GAP-11.4 closed: clean inspector + readable text
expected: Add 3 ports to a shape, type a label in each, trash 2 of them. Open DevTools and run `document.querySelectorAll('.sfd-field--port-author .sfd-ac-listbox').length` — count must equal the visible-row count (≤ visible inputs), never accumulate to 10+. Typed text in any port-label input is clearly readable: light text (#eee) on dark navy (#1a1a2a), border #444, focus ring teal #0d9488 — visually indistinguishable from the connector circuit-label input on the same inspector.
result: pending

### 4. Re-UAT-5 — GAP-11.5 + PORT-06 closed: Σ(label widths) auto-expansion
expected: On a fresh Console (180×60), click '+ Add port' on the Top edge 5 times, then label each with realistic strings ('Channel 1', 'Channel 2', ..., 'Channel 5'). Shape MUST auto-expand wide enough that no two port labels overlap inside the body. Toast 'Shape resized to fit ports.' fires on each grow. Removing a port does NOT shrink the shape (auto-expand never auto-shrinks, per RESEARCH §Q5).
result: pending

### 5. Re-UAT-6 — SHP-RESIZE-02/03 (carry-over): min-size clamp + autosave + undo
expected: Test A — drag the BR handle of a port-less Console inward → shape stops at 180×60 (ABSOLUTE_FLOOR). Add 5 labeled ports → floor grows wider per the new Σ(label widths) formula and resize-in clamps at the wider floor. Test B — drag-end any shape → DevTools Network shows autosave POST within 1500ms. Test C — Ctrl+Z after a resize → reverses in single undo step. Page reload shows persisted (if not undone) or original (if undone) dimensions. Originally skipped in Pass 1 because GAP-11.2 blocked port creation.
result: pending

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Pass 1 History (resolved 2026-05-24 via 11-07 + 11-08 + CR-01 fix)

Pass 1 reported 5 gaps (GAP-11.1..11.5). Gap-closure plans 11-07 (4 functional gaps) + 11-08 (CSS gap) shipped, plus critical code-review fix CR-01 (double-? URL in fetchAcResults that silently re-broke GAP-11.1). All 5 Pass 1 gaps are structurally closed; the 5 items above are the re-UAT confirmation pass. Full trail: 11-VERIFICATION.md `## History`.

## Gaps
