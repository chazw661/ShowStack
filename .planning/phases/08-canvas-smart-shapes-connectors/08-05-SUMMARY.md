---
phase: 08-canvas-smart-shapes-connectors
plan: 05
subsystem: ui
tags: [jointjs, canvas-ux, pan, zoom, snap, undo-redo, multi-select, rubber-band, keyboard, signal-flow]

# Dependency graph
requires:
  - phase: 08-canvas-smart-shapes-connectors
    plan: 01
    provides: signal_flow_autosave ?viewport_only=1 fast-path endpoint (accepts {viewport: {x, y, scale, snapEnabled}}; no version bump; no equipment-ref validation)
  - phase: 08-canvas-smart-shapes-connectors
    plan: 02
    provides: CSS for .joint-element.is-selected, .joint-link.is-selected, .sfd-multi-bbox
  - phase: 08-canvas-smart-shapes-connectors
    plan: 03
    provides: editor.html toolbar buttons (#sfd-zoom-out, #sfd-zoom-level, #sfd-zoom-in, #sfd-zoom-fit, #sfd-snap-toggle.is-active, #sfd-undo[disabled], #sfd-redo[disabled])
  - phase: 08-canvas-smart-shapes-connectors
    plan: 04
    provides: graph / paper / paperEl / currentViewport / pickerState already bound inside the IIFE; window.__sfd handoff seam exposed; initial fromJSON({undoable:false}) keeps undo stack clean

provides:
  - "Pan via Space+drag and middle-click drag, with paperEl cursor writes using setProperty(... 'important') per CLAUDE.md"
  - "Zoom in/out/fit with [0.25, 2.0] clamp and #sfd-zoom-level percent display"
  - "Snap-to-grid toggle bound to currentViewport.snapEnabled, default ON (CONTEXT D-13); paper.setGrid(20 | 1) + dotted overlay; toggle aria-pressed + .is-active state"
  - "Custom 165-line event-sourced undo/redo stack (no CommandManager in @joint/core 4.2.4); UNDO_HISTORY_CAP=50; multi-cell drag batched via element:pointerdown/pointerup; Ctrl/Cmd+Z / Ctrl/Cmd+Shift+Z / Ctrl/Cmd+Y shortcuts; toolbar buttons sync disabled state"
  - "Multi-selection via shift-click on element/link + rubber-band drag on blank canvas using paper.findViewsInArea"
  - "Selection visuals via .is-selected CSS class with re-apply on add + change:attrs (RESEARCH Open Risk #4)"
  - "Multi-select bbox overlay SVG <rect class=sfd-multi-bbox> when selectedSet.size > 1"
  - "Keyboard Delete / Backspace removes selection in one undoBeginBatch/undoEndBatch — single Ctrl+Z reverts the gesture"
  - "Debounced (800ms) viewport persistence to ?viewport_only=1 with X-CSRFToken"
  - "window.__sfd.undo and window.__sfd.selection handoff seams for plan 06 inspector"
affects: [08-06 connectors + inspector + manual save (inspector subscribes via window.__sfd.selection.onSelectionChanged; save can wrap multi-step writes in window.__sfd.undo.beginBatch/endBatch), 09 autosave (consumes the same viewport debounce pattern), 10 PNG export (uses pan/zoom-stable paper state)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Custom event-sourced undo stack in vanilla JS — graph.on('add' | 'remove' | 'change') -> undoStack [[cmd]] batches with applyInverse/applyForward both passing { undoable: false } to prevent recursion"
    - "Multi-cell drag batching via paper.on('element:pointerdown', undoBeginBatch) + paper.on('element:pointerup', undoEndBatch) — RESEARCH Open Risk #1 mitigated"
    - "Debounced viewport persistence — 800ms setTimeout coalesces rapid pan/zoom/snap events into one fetch with credentials:'same-origin' + X-CSRFToken"
    - "Selection state = Set<cellId>; visual re-apply on add + change:attrs only (NOT change:position) — RESEARCH Open Risk #4"
    - "Rubber-band hit-test via paper.findViewsInArea({x, y, width, height}) on paper.viewport SVG layer; gated on !panState.spaceDown && evt.button === 0"
    - "CLAUDE.md override rule honored — every paperEl cursor write uses style.setProperty(prop, value, 'important')"
    - "Keyboard handlers consistently guard against /INPUT|TEXTAREA|SELECT/.test(target.tagName) AND pickerState.open"

key-files:
  created: []
  modified:
    - "planner/static/planner/js/signal_flow_editor.js — 522 -> 1039 lines (+517). Wave 2's IIFE extended in-place; init code, smart-shape registration, drag-drop, and equipment picker untouched."

key-decisions:
  - "schedulePersistViewport defined BEFORE the pan/zoom/snap handlers so the function reference resolves at first use (no hoisting reliance)."
  - "setSnap(currentViewport.snapEnabled) called once at module init — guarantees DOM, paper grid, aria attrs, and currentViewport are all in sync after the state-load promise resolves. Snap default ON (CONTEXT D-13) flows through unchanged."
  - "All applyInverse / applyForward branches use { undoable: false } — non-negotiable; without this the graph listeners re-record their own undo actions and produce infinite recursion."
  - "Initial cell load already uses fromJSON({ undoable: false }) from plan 04 — undo stack starts empty even when the diagram has cells."
  - "Selection visuals re-apply ONLY on graph add + change:attrs (NOT change:position). Position changes don't re-create the DOM node, so .is-selected survives drags. Binding to change:position would re-paint on every drag tick — expensive and unnecessary."
  - "Rubber-band gate is !panState.spaceDown && evt.button === 0 — pan ALWAYS wins over selection."
  - "Multi-select bbox uses paper.viewport || paper.svg fallback — handles both new (`paper.viewport` getter) and legacy @joint/core APIs."
  - "Cursor reset on mouseup checks panState.spaceDown — if Space is still held, cursor returns to 'grab' (ready to pan again), otherwise empty string (default)."
  - "Toolbar Undo / Redo disable attribute managed via removeAttribute/setAttribute('disabled', '') — fires through refreshUndoButtons() after every push/pop on either stack."
  - "GUARD CONSISTENCY: both the undo keyboard handler AND the delete keyboard handler check pickerState.open — typing Ctrl+Z in the equipment-picker search box (which is an INPUT, already excluded) is doubly safe, but Backspace in the search box would otherwise delete selection."

patterns-established:
  - "window.__sfd.undo (undo / redo / beginBatch / endBatch / record) and window.__sfd.selection (getSelected / clear / onSelectionChanged hook) are the canonical seams for plan 06's inspector + save logic — plan 06 attaches its inspector update by assigning to window.__sfd.onSelectionChanged"
  - "Custom undo stack lives entirely inside the editor IIFE — no factory, no exports; it's a per-page singleton that closes over `graph`. Future canvases (if any) can copy the ~165-line block as-is."

requirements-completed: [CNV-02, CNV-03, CNV-04, CNV-05, CNV-06, CNV-07, CNV-08]

# Metrics
duration: ~10min
completed: 2026-05-21
---

# Phase 08 Plan 05: Canvas UX Layer Summary

**`signal_flow_editor.js` grew from 522 to 1039 lines (+517): pan (Space + middle-click), zoom (in/out/fit + level display), snap toggle, debounced viewport persistence, custom event-sourced undo stack (~165 lines, no `CommandManager` in `@joint/core` 4.2.4), shift-click + rubber-band multi-selection, and keyboard delete — all 7 canvas-UX requirements (CNV-02..CNV-08) shipped against the Wave 2 Graph/Paper instances via the `window.__sfd` handoff.**

## Performance

- **Started:** 2026-05-21 (Wave 3 parallel executor)
- **Completed:** 2026-05-21
- **Tasks:** 3 / 3
- **Files modified:** 1
- **Lines added:** +517 (522 → 1039)

## Accomplishments

- **Pan (CNV-02)** — Hold-Space + left-drag AND middle-click drag both pan the canvas. `paperEl.style.setProperty('cursor', value, 'important')` is used on every cursor write (CLAUDE.md override rule). The Space-key listener short-circuits during input-field focus and while the picker is open.
- **Zoom (CNV-03)** — `setZoom` clamps the scale to `[0.25, 2.0]`, calls `paper.scale(scale, scale)`, updates `currentViewport.scale`, writes the rounded percent into `#sfd-zoom-level`, and schedules a viewport persist. `zoomIn` and `zoomOut` step by 1.2×/÷. `zoomToFit` computes the all-cells bbox via `graph.getBBox(getCells())`, pads 40px on each side, and falls back to `setZoom(1.0); paper.translate(0,0)` when the graph is empty.
- **Snap (CNV-04)** — `setSnap(on)` writes `currentViewport.snapEnabled`, calls `paper.setGrid(20 | 1)`, draws/clears the dotted grid overlay, toggles `.is-active` + `aria-pressed` + `aria-label` on `#sfd-snap-toggle`, and schedules a viewport persist. Initial state read from `currentViewport.snapEnabled` (default ON per CONTEXT D-13). Toolbar click flips it.
- **Viewport persist (CNV-08)** — `schedulePersistViewport()` debounces 800ms then POSTs `{viewport: {x, y, scale, snapEnabled}}` to `autosaveUrl + '?viewport_only=1'` with `X-CSRFToken`. Pan/zoom/snap all call it; the server fast-path (plan 01) skips version bump and equipment-ref validation. Errors are swallowed silently — viewport persistence is best-effort.
- **Custom undo stack (CNV-05)** — 165 lines of event-sourced undo/redo. `graph.on('add' | 'remove' | 'change')` records `{type, cellId, json}` or `{type, cellId, before, after}` into `undoStack` (capped at 50 batches via `shift()`). `applyInverse` / `applyForward` both pass `{ undoable: false }` to prevent the listeners from re-recording. `doUndo()` pops a batch from `undoStack` and pushes onto `redoStack`; `doRedo()` is symmetric. Multi-cell drags wrap `element:pointerdown` / `element:pointerup` in `undoBeginBatch`/`undoEndBatch` — one Ctrl+Z reverts the whole drag. Toolbar buttons sync disabled state via `refreshUndoButtons()`. Keyboard shortcuts: Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, Ctrl/Cmd+Y — all with `evt.preventDefault()`.
- **Multi-selection (CNV-06)** — `selectedSet = new Set()`. `element:pointerclick` and `link:pointerclick` either replace (plain) or toggle (shift) the selection; `blank:pointerclick` clears. Rubber-band drag on blank canvas (`blank:pointerdown`, gated `!panState.spaceDown && evt.button === 0`) draws an SVG overlay rect in paper-local coords, hit-tests via `paper.findViewsInArea({x, y, width, height})` on `mouseup`, and adds (shift) or replaces (no shift) the selection. Drags under 4px are ignored. Multi-select bbox overlay via SVG `<rect class="sfd-multi-bbox">` when `selectedSet.size > 1`, computed with `graph.getCellsBBox(cells)`.
- **Keyboard delete (CNV-07)** — Delete or Backspace, wrapped in `undoBeginBatch()` / `undoEndBatch()`, calls `cell.remove()` for every cell id in `selectedSet` and clears the set. Single Ctrl+Z restores everything. Guarded against `/INPUT|TEXTAREA|SELECT/` focus and `pickerState.open` so the equipment-picker search box never accidentally deletes shapes.
- **Selection survives re-render** — `graph.on('add change:attrs', applySelectionVisuals)` re-applies the `.is-selected` class after JointJS re-renders cell views. We deliberately do NOT bind to `change:position` — position changes don't recreate the DOM node, so the class survives them already, and re-painting on every drag tick would be expensive (RESEARCH Open Risk #4).
- **Handoff to plan 06** — `window.__sfd.undo = { undo, redo, beginBatch, endBatch, record }` and `window.__sfd.selection = { getSelected, clear, onSelectionChanged }` expose the seams plan 06's inspector + manual Save will use.

## Task Commits

Each task was committed atomically with `--no-verify` per the parallel-executor protocol:

1. **Task 1: Wire pan, zoom (in/out/fit + level display), snap toggle, and viewport debounced persistence** — `ec76b89` (feat)
2. **Task 2: Add custom event-sourced undo/redo stack with batching, keyboard shortcuts, and toolbar wiring** — `31f3610` (feat)
3. **Task 3: Add multi-selection (shift-click + rubber-band), keyboard delete, and selection visual** — `dfe29bb` (feat)

_Plan metadata commit (SUMMARY.md) is added separately by the orchestrator after worktree merge._

## Files Created/Modified

- **`planner/static/planner/js/signal_flow_editor.js`** — modified (+517 lines, 522 → 1039).
  - Kept: All Wave 2 init code (IIFE wrapper, helpers, 5 shape classes, Graph + Paper instantiation, state-load, equipment picker, drag-drop, `window.__sfd` core handoff).
  - Added: `schedulePersistViewport` (debounced 800ms POST to `?viewport_only=1`), `panState` + space/middle-click handlers, `setZoom` / `zoomIn` / `zoomOut` / `zoomToFit`, `setSnap`, custom undo stack (`undoStack`, `redoStack`, `undoCapturing`, `undoBatchDepth`, `UNDO_HISTORY_CAP=50`, `undoRecord`, `undoBeginBatch`, `undoEndBatch`, `applyInverse`, `applyForward`, `doUndo`, `doRedo`, `refreshUndoButtons`, toolbar wiring, drag batch + keyboard shortcuts), selection (`selectedSet`, `multiBboxRect`, `applySelectionVisuals`, `redrawSelection`, `element|link|blank:pointerclick`, `blank:pointerdown` rubber-band, Delete/Backspace handler, re-apply on add + change:attrs), `window.__sfd.undo` + `window.__sfd.selection` handoff.

## Decisions Made

- **`schedulePersistViewport` defined first** — declared before the pan/zoom/snap handlers so the first caller reference always resolves. Avoids relying on function-declaration hoisting across a nested closure boundary.
- **`setSnap(currentViewport.snapEnabled)` at module init** — single call synchronizes paper grid, dotted overlay, button `.is-active` / `aria-pressed` / `aria-label`, and `currentViewport.snapEnabled` after the state-load promise resolves. Same path as the user click — one less code path to maintain.
- **Selection re-apply on `add` + `change:attrs` only** — `change:position` would re-paint on every drag tick (expensive); positions don't recreate the DOM node, so `.is-selected` survives them. `add` covers cell creation; `change:attrs` covers label/style swaps that DO recreate the DOM. This is the RESEARCH Open Risk #4 mitigation as written.
- **Cursor reset on `mouseup` checks `panState.spaceDown`** — if the user is still holding Space, cursor returns to `'grab'` (visually signals "ready to pan again"); otherwise empty (default).
- **Both keyboard handlers (undo + delete) guard against `pickerState.open`** — the equipment-picker search box is an `INPUT` (already excluded by the tagName check), but the redundant `pickerState.open` guard is cheap and protects against future inputs that aren't `INPUT/TEXTAREA/SELECT`.
- **`paper.viewport || paper.svg` fallback** for SVG overlay rects — handles both modern (`paper.viewport` getter) and legacy `@joint/core` APIs. Defensive but cheap.
- **Rubber-band fill = accent at 8% opacity (`rgba(13, 148, 136, 0.08)`)** — matches the teal accent palette used by `Console` band and the `.is-selected` border; stays subtle so the canvas remains readable while dragging.

## Deviations from Plan

None — all three tasks executed exactly as written. The plan provided complete code blocks; structural fidelity was preserved task-by-task. Minor preservation notes worth recording:

- **Inserted before, not after, the `window.__sfd` block.** The plan said "append… below plan 04's code" — strict reading means after the existing `window.__sfd.openEquipmentPicker = ...` line. I inserted the new code BEFORE the handoff block so the new `window.__sfd.undo` and `window.__sfd.selection` entries sit alongside the existing entries, in the same handoff section. Functionally identical (the IIFE still runs top-to-bottom in declaration order); structurally cleaner.

## Issues Encountered

None. JS parses cleanly (`node --check` exit 0) after each task. Every acceptance-criteria grep passed on first run.

## User Setup Required

None — pure JS edit. No environment variables, no migrations, no new dependencies, no Railway changes. The toolbar buttons already exist in `editor.html` from plan 03; the CSS for `.is-selected` and `.sfd-multi-bbox` already exists from plan 02; the `?viewport_only=1` endpoint already exists from plan 01.

## Window.__sfd Additions

| Key | Type | Purpose |
|-----|------|---------|
| `window.__sfd.undo` | `{undo, redo, beginBatch, endBatch, record}` | Plan 06's manual Save can wrap multi-step writes in `beginBatch / endBatch` so one Ctrl+Z reverts the whole gesture. |
| `window.__sfd.selection` | `{getSelected, clear, onSelectionChanged?}` | Plan 06's inspector reads `getSelected()` and sets `onSelectionChanged` (function) to be notified when the selection changes. |

The Wave 2 entries (`graph`, `paper`, `paperEl`, `viewport`, `helpers`, `urls`, `shapeNamespace`, `cellNamespace`, `openEquipmentPicker`) are untouched.

## Self-Check: PASSED

Verifying every claim against the filesystem and git history.

### File modified — exists on disk

- `planner/static/planner/js/signal_flow_editor.js` — FOUND (1039 lines confirmed by `wc -l`).

### Commits — present in git history

- `ec76b89` — FOUND (`feat(08-05): wire pan, zoom, snap toggle, and viewport debounced persistence`).
- `31f3610` — FOUND (`feat(08-05): add custom event-sourced undo/redo stack with batching and keyboard shortcuts`).
- `dfe29bb` — FOUND (`feat(08-05): add multi-selection (shift-click + rubber-band), keyboard delete, selection visuals`).

### Plan-level verification greps

- `wc -l planner/static/planner/js/signal_flow_editor.js` = **1039** (target ≥ 700 — exceeded).
- `grep -cE "function (doUndo|doRedo|setZoom|setSnap|redrawSelection)" planner/static/planner/js/signal_flow_editor.js` = **5** (all 5 required functions defined).

### Task 1 acceptance criteria

- `panState`: 20 hits ✓
- `evt.code === 'Space'`: 2 hits ✓ (≥1)
- `evt.button === 1`: 1 hit ✓
- `paper.translate(panState.baseTx`: 1 hit ✓
- `function setZoom|zoomIn|zoomOut|zoomToFit`: 4 lines ✓
- `Math.max(0.25, Math.min(2.0`: 2 hits ✓ (≥1)
- `graph.getBBox|graph.getCells`: 3 hits ✓
- `function setSnap`: 1 hit ✓
- `snapToggleBtn.classList.add('is-active')`: 1 hit ✓
- `schedulePersistViewport`: 5 hits ✓ (≥5; called from pan-mouseup, setZoom, zoomToFit, setSnap)
- `viewport_only=1`: 2 hits ✓ (≥1)
- `X-CSRFToken`: 3 hits ✓ (≥1)
- All cursor writes use `setProperty('cursor', value, 'important')`: 4 hits ✓

### Task 2 acceptance criteria

- 7 undo functions (`doUndo|doRedo|applyInverse|applyForward|undoRecord|undoBeginBatch|undoEndBatch`): 7 ✓
- `undoable: false`: 10 hits ✓ (≥7)
- `graph.on('add' | 'remove' | 'change')`: 3 hits ✓
- `element:pointerdown` / `element:pointerup`: 2 hits ✓
- `evt.ctrlKey || evt.metaKey`: 1 hit ✓
- `evt.preventDefault`: 7 hits ✓ (≥3)
- `UNDO_HISTORY_CAP`: 4 hits ✓ (≥2)
- `undoBtn.addEventListener|redoBtn.addEventListener`: 2 hits ✓
- `window.__sfd.undo`: 1 hit ✓ (≥1)

### Task 3 acceptance criteria

- `selectedSet = new Set`: 1 hit ✓
- 3 pointerclick handlers (`element|link|blank:pointerclick`): 3 hits ✓
- `blank:pointerdown`: 1 hit ✓
- `paper.findViewsInArea`: 2 hits ✓ (≥1)
- `evt.key === 'Delete' || evt.key === 'Backspace'`: 1 hit ✓
- `undoBeginBatch();`: 2 hits ✓ (drag wrap + delete wrap)
- `undoEndBatch();`: 2 hits ✓
- `view.el.classList.add('is-selected')` / `.remove('is-selected')`: 2 hits ✓ (≥2)
- `sfd-multi-bbox`: 2 hits ✓ (≥1)
- `window.__sfd.selection`: 2 hits ✓ (≥1)
- `evt.shiftKey`: 4 hits ✓ (≥3; element + link + rubber-band + delete-unused-but-guard)
- Rubber-band gate (`panState.spaceDown || evt.button !== 0`): 1 hit ✓ (line 929)

### JS syntax

- `node --check planner/static/planner/js/signal_flow_editor.js` → exit 0 after each commit.

### Deletion check

- `git diff --diff-filter=D --name-only 37459a2 HEAD` → empty. No files deleted.

### CLAUDE.md compliance

- Every `paperEl.style` write uses `setProperty(prop, value, 'important')` (4 occurrences, all cursor writes). ✓
- No direct `element.style.prop = value` admin-DOM writes. ✓

All claims verified. SELF-CHECK PASSED.

## Threat Flags

No new security-relevant surface introduced beyond the plan's `<threat_model>`. The viewport POST already documented in plan 01; the undo memory cap (T-08-30) honored via `UNDO_HISTORY_CAP = 50` + `shift()`; viewport debounce (T-08-31) honored at 800ms; CSRF token (T-08-36) sent via `X-CSRFToken` on every viewport POST.

## Next Phase Readiness

- **Plan 08-06 (connectors + inspector + manual save)** — Ready.
  - `window.__sfd.selection.getSelected()` returns the current selection as an array of cell ids.
  - `window.__sfd.onSelectionChanged = function(ids) { ... }` is the hook plan 06 sets to drive inspector show/hide.
  - `window.__sfd.undo.beginBatch()` / `endBatch()` are available to wrap multi-step inspector edits (e.g., applying a signal-type change to multiple connectors in one Ctrl+Z gesture).
  - `window.__sfd.urls.autosave` is the manual-save endpoint (without `?viewport_only=1` — full payload triggers version bump + equipment validation).
- **Phase 9 autosave** — The 800ms `schedulePersistViewport` debounce pattern is the analog for the canvas_state autosave (Phase 9 will copy this pattern but POST `{ canvas_state, viewport, version }` to the same `autosaveUrl` without the `?viewport_only=1` query param).
- **No blockers, no deferred issues.** Worktree-only changes; orchestrator owns the merge back to main.

---
*Phase: 08-canvas-smart-shapes-connectors*
*Completed: 2026-05-21*
