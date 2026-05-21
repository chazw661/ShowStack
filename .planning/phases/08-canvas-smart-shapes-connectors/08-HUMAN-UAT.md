---
status: resolved
phase: 08-canvas-smart-shapes-connectors
source: [08-VERIFICATION.md]
started: 2026-05-21T18:20:00Z
updated: 2026-05-21T22:55:00Z
---

## Current Test

[complete — all 5 tests passed in browser]

## Tests

### 1. Sidebar drag-drop lands shape at cursor accounting for scroll/zoom

setup: Open `/audiopatch/signal-flow/<id>/`. Pan the canvas (Space + drag) until you're far from the origin. Set zoom to ~75% via the `−` button (or 125% via `+`).

action: Drag the **Console** tile from the sidebar and release at an arbitrary on-canvas point.

expected:
  - The shape lands at the cursor — not at (0,0) and not at the pre-pan original coordinate.
  - For typed shapes (Console / Device / SpeakerArray / CommBeltPack), the equipment picker modal opens with the current project's records only (and an "Add equipment in Admin" empty-state link if none exist).
  - The Generic tile drops the shape directly without opening the picker.

result: passed

### 2. Pan + zoom + snap + viewport restore

setup: At least one shape on the canvas.

action:
  - Hold Space + left-drag — canvas pans; release Space; canvas pans stop.
  - Middle-click drag — canvas pans.
  - Click `−` → zoom shows ~83%; click `+` → 100%; click `[⊡]` zoom-to-fit centers all cells.
  - Click snap-toggle → `.is-active` flips off, grid dots disappear, shapes drag freely; click again → grid + snap restore.
  - Reload the page.

expected:
  - After reload: pan position, zoom %, and snap state restore exactly as left.
  - Zoom clamped between 25% and 200%.
  - During pan: paperEl cursor = `grabbing`; Space-hold without drag = `grab`; on release = default.

result: passed

### 3. Undo/redo + multi-select + keyboard delete

setup: Drop 3 shapes (any types).

action:
  - Press Ctrl/Cmd+Z three times — all 3 vanish in reverse order.
  - Press Ctrl/Cmd+Shift+Z three times — all 3 return.
  - Drag a shape to a new position; press Ctrl/Cmd+Z — shape returns to start.
  - Shift-click two shapes — both show the `.is-selected` teal outline.
  - Drag from blank canvas across all 3 — rubber-band rect appears, on release all 3 are selected with the dashed `.sfd-multi-bbox` overlay.
  - Press Delete or Backspace — all 3 vanish.
  - Press Ctrl/Cmd+Z once — all 3 reappear together (single batch).
  - Click into the circuit-label input; press Backspace — character deletes from input, NOT the selected connector.
  - Open the equipment picker; press Backspace in the search box — character deletes, NOT a canvas shape.

result: passed

### 4. Port-snapped orthogonal connectors + signal-type styles

setup: 2+ shapes on the canvas.

action:
  - Hover over a shape — 4 ports (in left, out right, in top, out bottom) become visible (opacity 0 → 1).
  - Drag from an output port (right or bottom) to another shape's input port (left or top) — orthogonal right-angle connector appears with rounded corners.
  - Try dropping a link onto mid-shape (no port magnet) — link is rejected.
  - Try connecting a shape to itself — rejected.
  - Click the connector — Vertices + SourceAnchor + TargetAnchor + Remove tools appear.
  - Drag a midpoint vertex — line reroutes around it.
  - Select the connector; change signal-type dropdown:
    - analog → black solid line, black arrow
    - AES → blue (`#1565c0`) solid, blue arrow
    - Dante → cyan (`#00bcd4`) dashed 6-4, cyan arrow
    - MADI → orange (`#ef6c00`) dashed 10-3-3-3 (heavier 2.5px), orange arrow
    - intercom → purple (`#7b1fa2`) dashed 2-4, purple arrow

result: passed

### 5. Inspector + bidirectional + circuit-label + manual Save round-trip

setup: At least one connector exists.

action:
  - Click empty area (selection: 0) — inspector hidden.
  - Click a shape (selection: 1 node) — inspector hidden.
  - Click a connector (selection: 1 link) — inspector slides in showing current signalType, direction, circuitLabel.
  - Shift-click another connector (selection: 2 links) — inspector hides.
  - Click "Bidirectional" — both arrow markers strip; switch back to "Source → Target" — target arrow returns matching the current signal-type color.
  - Type "MAIN-FOH" in the circuit-label input — after 200ms debounce, label renders centered on the line with 85%-white pill background + grey border.
  - Press Tab to blur — label commits any pending change.
  - Click **Save** — status flips "All changes saved." → "Saving…" → "All changes saved." (or "Save failed — retry" on error).
  - Reload — every connector restores with its signalType + direction + circuitLabel + dragged vertices intact.
  - Open the editor as a Viewer-group user — Save returns 403 → toast shows "Save failed."
  - (Optional adversarial) POST a crafted canvas_state with a foreign-project contentTypeId — server returns HTTP 422 with "Equipment reference out of project."

result: passed

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

None blocking. Three small UAT-time spec additions landed before sign-off
(commit 55a0169): manhattan router with padding for parallel-link
separation, `linkTools.Segments()` for per-segment knuckle editing, and
two extra signal types (AVB / Network). User-addable input/output ports
were considered and deferred per SHP-08 ("Per-channel ports deferred
to v2.3"); revisit as a Phase 8.1 if real-world use demands it before
v2.3.
