---
phase: 08-canvas-smart-shapes-connectors
plan: 04
subsystem: ui
tags: [jointjs, smart-shapes, drag-drop, modal, autocomplete, xss, signal-flow]

# Dependency graph
requires:
  - phase: 08-canvas-smart-shapes-connectors
    plan: 01
    provides: signal_flow_autocomplete view (project-scoped equipment list, ?type=console|device|speakerarray|commbeltpack&q=...)
  - phase: 08-canvas-smart-shapes-connectors
    plan: 03
    provides: editor.html DOM contract (#sfd-paper, [data-shape-type] tiles, equipment picker modal IDs, data-* URL attrs)
provides:
  - "joint.shapes.showstack namespace with 5 shape classes (Console, Device, SpeakerArray, CommBeltPack, Generic) carrying 4 ports each"
  - "JointJS Graph + Paper instances at 4000x3000 with explicit cellNamespace + cellViewNamespace (PITFALLS §1)"
  - "Sidebar drag-drop with paper.clientToLocalPoint() translation (PITFALLS §2)"
  - "Equipment picker modal flow — open on drop, fetch with 200ms debounce, pick writes GFK payload, cancel removes placeholder (CONTEXT D-09..12)"
  - "window.__sfd handoff contract for plans 05 + 06"
affects: [08-05 (pan/zoom/snap/undo/delete bound to existing graph/paper), 08-06 (connectors + inspector + manual save bound to existing graph/paper), 09 (autosave reads window.__sfd.graph for toJSON), 10 (PNG export reads window.__sfd.paper)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "joint.shapes.<project> namespace registration BEFORE new joint.dia.Graph — explicit cellNamespace AND cellViewNamespace passed to constructors (PITFALLS §1)"
    - "graph.fromJSON(state, { undoable: false }) on initial load — keeps plan 05's undo stack clean"
    - "Single window.__sfd handoff object — plans 05/06 reuse Graph/Paper instances rather than re-instantiating"
    - "PICKER_TYPE_CONFIG dispatch map — single source of truth for modal label + backend ?type= + admin URL per shape type"
    - "XSS-safe row build — document.createElement + textContent, never innerHTML for content"
    - "Admin-DOM display toggle via setProperty('display', 'flex'|'none', 'important') — CLAUDE.md override rule"
    - "Cancel-removes-placeholder pattern: node.remove({ undoable: false }) on every cancel affordance, so half-built shapes never reach autosave (CONTEXT D-10)"
    - "Defensive type guard on drop: if (!joint.shapes.showstack[shapeType]) return — blocks crafted dataTransfer (T-08-20)"

key-files:
  created: []
  modified:
    - "planner/static/planner/js/signal_flow_editor.js — 49 -> 522 lines (+473). Extended the Phase 7 IIFE in-place; wrapper, container guard, and JointJS-loaded guard untouched."

key-decisions:
  - "Restructured the Phase 7 console.log into a [SFD] paper ready line emitted after state load, instead of at IIFE entry — version number and cell count now appear together in DevTools."
  - "Picker functions defined BEFORE the window.__sfd attachment so the openEquipmentPicker reference resolves at attachment time."
  - "currentViewport.snapEnabled read inline in the drop handler — plan 05 will replace with the live snap-toggle state, but D-13 default (ON) is honored immediately."
  - "Manual snap math (round to 20px) in the drop handler rather than relying on paper.setGridSize() — drop coords come from clientToLocalPoint, not from JointJS's internal element-drag pipeline, so the snap option does not apply."
  - "PICKER_TYPE_CONFIG label uses 'Speaker Array' (with space) and 'Beltpack' (one word) — matches UI-SPEC § Copywriting Contract."
  - "Search input event uses a 200ms debounce (CONTEXT D-11) — pickerState.searchTimer cleared on close so cancel-then-reopen never fires a stale query."
  - "renderPickerResults uses createElement + textContent for every visible string — defence-in-depth XSS mitigation (T-08-21) even though server data flows through Django ORM."
  - "Admin link href filled via setAttribute('href', cfg.admin) where cfg.admin is a hardcoded string constant — T-08-23 (open redirect) mitigated by removing any user-input path to the URL."

patterns-established:
  - "window.__sfd is the canonical handoff seam between Phase 8 plans 04, 05, and 06 — adding new shared helpers means assigning to window.__sfd.X in plan 04, reading from window.__sfd.X in plan 05/06."
  - "All Phase 8 picker UI strings flow through textContent — innerHTML is reserved for empty-string clears only."
  - "Closure-scoped pickerState object (open, shapeType, node, searchTimer) keeps modal state isolated and trivially resettable on close."

requirements-completed: [CNV-01, SHP-01, SHP-02, SHP-03, SHP-04, SHP-05, SHP-08]

# Metrics
duration: ~6min
completed: 2026-05-20
---

# Phase 08 Plan 04: JointJS Canvas + Smart Shapes + Equipment Picker Summary

**`signal_flow_editor.js` extended from the 49-line Phase 7 stub to a 522-line controller: 5 smart shape classes registered in `joint.shapes.showstack`, JointJS Graph + Paper at 4000×3000 with explicit `cellNamespace` + `cellViewNamespace`, HTML5 drag-drop from the sidebar tiles with `paper.clientToLocalPoint()` math, and a complete equipment picker modal flow (open on typed-shape drop → fetch with 200 ms debounce → XSS-safe row render → pick writes GFK payload → cancel removes placeholder).**

## Performance

- **Started:** 2026-05-20 (Wave 2 parallel executor)
- **Tasks:** 2 / 2
- **Files modified:** 1
- **Lines added:** +473 (49 → 522)

## Accomplishments

- **Namespace + 5 shape classes** — `joint.shapes.showstack.{Console, Device, SpeakerArray, CommBeltPack, Generic}` each defined with its UI-SPEC geometry (180×60 / 140×56 / 120×80 trapezoid / 80×100 pill / 140×56 dashed) and color band (`#0d9488` teal / `#475569` slate / `#ea580c` orange / `#7c3aed` purple / `#94a3b8` dashed grey).
- **4 ports per shape** (SHP-08) — `in` left + bottom mid-edge, `out` right + top mid-edge ports… correction: in-left, out-right, in-top, out-bottom per the plan must_have wording. Magnets: `passive` for inbound, `true` for outbound. Opacity `0` at rest — plan 02 CSS handles hover-reveal.
- **PITFALLS §1 closed** — `cellNamespace = Object.assign({}, joint.shapes, { showstack: joint.shapes.showstack })` passed to BOTH `new joint.dia.Graph` and `new joint.dia.Paper` (as `cellViewNamespace`). No silent blank-canvas risk.
- **PATTERNS.md risk #4 closed** — initial `graph.fromJSON(state.canvas_state, { undoable: false })` runs AFTER the namespace registration AND the viewport restore. Plan 05's undo stack will start clean.
- **Sidebar drag-drop (CNV-01)** — every `[data-shape-type]` tile binds `dragstart` that sets `application/x-shape-type` on the dataTransfer. Paper drop handler honors snap-to-grid (`currentViewport.snapEnabled`), instantiates the matching `ShapeClass` at local-translated coords, and opens the picker for typed shapes.
- **Equipment picker modal (SHP-01..04 / SHP-09)** — opens with the right title ("Console" / "Device" / "Speaker Array" / "Beltpack"), fetches `${autocompleteUrl}?type=<console|device|speakerarray|commbeltpack>&q=<query>` from plan 01's view, renders rows via `createElement + textContent` (XSS-safe), debounces search at 200 ms, writes `showstack/contentTypeId`, `showstack/objectId`, `showstack/savedLabel` on pick, and removes the placeholder node on every cancel affordance.
- **4 cancel affordances** — footer Cancel button, top-right X, backdrop click, Escape key — every one calls `closeEquipmentPicker({ assigned: false })` which calls `node.remove({ undoable: false })` (CONTEXT D-10).
- **`window.__sfd` handoff** — `graph`, `paper`, `paperEl`, `viewport`, `helpers`, `urls`, `shapeNamespace`, `cellNamespace`, `openEquipmentPicker` exposed for plans 05 + 06.

## Task Commits

Each task was committed atomically with `--no-verify` per the parallel-executor protocol:

1. **Task 1: Register joint.shapes.showstack + init Graph/Paper with 5 smart shapes** — `84f7876` (feat)
2. **Task 2: Wire sidebar drag-drop + equipment picker modal flow** — `de6e061` (feat)

_Plan metadata commit (SUMMARY.md) is added separately by the orchestrator after worktree merge._

## Files Created/Modified

- **`planner/static/planner/js/signal_flow_editor.js`** — modified (+473 / -16 lines, 49 → 522 lines).
  - Kept: IIFE wrapper, `#sfd-container` guard, JointJS-loaded guard, dataset reads (`diagramId`, `stateUrl`, `autosaveUrl`).
  - Added: `autocompleteUrl` dataset read, helpers (`$`, `$$`, `csrfToken`, `postJSON`, `getJSON`, `showToast`), 5 shape class definitions, `portsForRect()` helper, Graph + Paper instantiation, initial state load with viewport restore + `graph.fromJSON(canvas, { undoable: false })`, sidebar drag-drop wiring, equipment picker modal flow (open / fetch / render / pick / close + 4 cancel affordances), `window.__sfd` handoff.
  - Removed: `htmlToImage` availability check (Phase 10 owns that; not blocking for canvas init) and the initial `[SFD] JointJS ready` log line (replaced by `[SFD] paper ready — diagram <id> — version <N> — cells <count>` after state load).

## Decisions Made

- **Picker functions are defined BEFORE the `window.__sfd` block** so the `window.__sfd.openEquipmentPicker = openEquipmentPicker;` reference resolves at attachment time. Hoisting the function declarations would also work, but explicit ordering is easier to follow.
- **Manual snap math in the drop handler** (round to grid 20) rather than relying on `paper.setGridSize()` — JointJS's grid snap applies to element drags inside the paper, not to coordinates derived from `clientToLocalPoint`. Plan 05 will keep this same code path and just flip `currentViewport.snapEnabled` from a static `true` to a live toggle.
- **System font stack only** — REQUIREMENTS Constraint (PNG canvas integrity in Phase 10). The label `font-family` uses `'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'`.
- **`htmlToImage` availability log removed.** It belonged to Phase 10's PNG export concern and was not load-bearing for Phase 8. Phase 10 will check for it when binding the export button. Removing the line keeps the `[SFD]` console output focused on one truth: "paper ready, diagram X, version Y, N cells."
- **No `dataTransfer.types` sniff before reading `getData('application/x-shape-type')`.** The defensive `if (!joint.shapes.showstack[shapeType]) return;` is sufficient — an unknown or empty type returns `undefined`/`""` from `getData`, fails the `joint.shapes.showstack[shapeType]` check, and short-circuits. T-08-20 mitigated.

## Window.__sfd Handoff Contract

The single window-scoped attachment that plans 05 + 06 consume:

| Key | Type | Purpose |
|-----|------|---------|
| `graph` | `joint.dia.Graph` | The model. Plans 05/06 listen on `graph.on(...)`, add/remove cells, call `toJSON()`. |
| `paper` | `joint.dia.Paper` | The view. Plan 05 calls `paper.scale()`, `paper.translate()`, `paper.findViewsInArea()`; plan 06 calls `paper.on('link:pointerclick', ...)`. |
| `paperEl` | `HTMLElement` | The paper DOM mount. Plan 05 binds `mousedown` here for middle-click / space+drag pan. |
| `viewport` | `{x, y, scale, snapEnabled}` | Plan 05 mutates these; plan 06 reads for save payload. |
| `helpers` | `{$, $$, csrfToken, postJSON, getJSON, showToast}` | Reusable utilities — plans 05/06 should NOT redeclare these. |
| `urls` | `{state, autosave, autocomplete}` | Endpoint URLs from data-* attrs. |
| `shapeNamespace` | `joint.shapes.showstack` | Alias for in-namespace shape lookups. |
| `cellNamespace` | Object | The namespace passed to Graph/Paper — needed if any further deserialization happens client-side. |
| `openEquipmentPicker` | `(shapeType, node) => void` | Useful seam for plan 06's hypothetical "re-link equipment" inspector action (NOT a Phase 8 requirement; exposed for free). |

## Deviations from Plan

None — both tasks executed as specified. Two minor adjustments worth noting:

- **htmlToImage log removed from the IIFE.** Not in the plan's "ADD" list, but the existing line in the stub was Phase 10 concern. The plan said "KEEP or REMOVE — irrelevant to functionality" about the original `[SFD] JointJS ready` log. I removed the htmlToImage line on the same principle (Phase 10's pre-flight check belongs in Phase 10's code). No functional change.
- **Snap math reads `currentViewport.snapEnabled`** rather than a module-scoped `snapEnabled` variable. The plan's pseudocode used a bare `if (snapEnabled)` — I bound it to the `currentViewport` object that's already exposed on `window.__sfd`, so plan 05's snap-toggle handler has a single canonical place to write the new state. Semantically identical to the plan; structurally cleaner.

## Issues Encountered

None. JS parses cleanly (`node --check` exit 0). All Task 1 and Task 2 acceptance-criteria greps pass on first run.

## User Setup Required

None — pure JS edit. No environment variables, no migrations, no new dependencies, no Railway changes. Plans 02 (CSS) and 03 (template) provide the DOM hooks this controller binds to; plan 01 provides the autocomplete view.

## Self-Check: PASSED

Verifying every claim against filesystem + git history:

### File modified — exists on disk

- `planner/static/planner/js/signal_flow_editor.js` — FOUND (522 lines confirmed by `wc -l`).

### Commits — present in git history

- `84f7876` — FOUND (`feat(08-04): register joint.shapes.showstack + init Graph/Paper with 5 smart shapes`).
- `de6e061` — FOUND (`feat(08-04): wire sidebar drag-drop + equipment picker modal flow`).

### Acceptance-criteria greps

- **5 shapes** — `grep -c 'joint.shapes.showstack\\.' signal_flow_editor.js` returns ≥ 5: confirmed 5 declaration lines.
- **`cellNamespace: cellNamespace` on Graph** — line 227: `new joint.dia.Graph({}, { cellNamespace: cellNamespace })`.
- **Paper with cellViewNamespace + 4000x3000 + gridSize 20** — line 230 + 233–237.
- **`fromJSON(... undoable: false)`** — line 266.
- **All 5 hex band/border colors** — confirmed by `grep -c "#0d9488\\|#475569\\|#ea580c\\|#7c3aed\\|#94a3b8"` = 10 hits (each used in two places: shape declaration and adjacent comment / second reference).
- **Both magnet types** — `magnet: 'passive'` (line 93) + `magnet: true` (line 98).
- **system-ui font stack** — line 83.
- **`window.__sfd`** — 10 lines (`grep -n "window.__sfd"` returns 10 matches, exceeds the plan's ≥ 6 requirement).
- **`container.dataset.autocompleteUrl`** — line 29.
- **`clientToLocalPoint`** — line 319 (call) + line 304 (comment) — 2 total, but only one functional call as required.
- **`application/x-shape-type`** — 2 lines (setData line 297 + getData line 315).
- **`node.remove({ undoable: false })`** — line 401.
- **`setProperty('display', ...)`** — 2 lines: flex (line 386) + none (line 404).
- **`Escape`** — line 496.
- **`innerHTML =`** — both writes assign `''` (empty-string clears). No content-bearing innerHTML.
- **All 4 picker functions defined** — `openEquipmentPicker` (line 362), `closeEquipmentPicker` (line 391), `fetchPickerResults` (line 412), `assignPickerResult` (line 460).
- **GFK payload** — `showstack/contentTypeId`, `showstack/objectId`, `showstack/savedLabel` all written via `node.prop()` (lines 466–468).
- **`PICKER_TYPE_CONFIG`** — defined at line 281, used in `openEquipmentPicker` and `fetchPickerResults`.

### JS syntax

- `node --check planner/static/planner/js/signal_flow_editor.js` → exit 0.

All claims verified. SELF-CHECK PASSED.

## Next Phase Readiness

- **Plan 08-05 (pan/zoom/snap/undo/multi-select/delete)** — Ready. `window.__sfd.graph`, `window.__sfd.paper`, `window.__sfd.paperEl`, `window.__sfd.viewport.snapEnabled` are the seams. Snap toggle will write `currentViewport.snapEnabled = !currentViewport.snapEnabled` (already exposed) — the drop handler picks it up on the next drop. Pan handlers bind to `paperEl`, zoom calls `paper.scale()`, undo/redo decorates `graph.on('change', ...)` (the initial-load `fromJSON` correctly bypasses this via `undoable: false`).
- **Plan 08-06 (connectors + inspector + manual save)** — Ready. `window.__sfd.graph` + `window.__sfd.paper` for `paper.on('link:*')` handlers, `window.__sfd.helpers.postJSON` for the save button, `window.__sfd.urls.autosave` for the endpoint.
- **Plan 08-01 dependency satisfied** — picker fetches `${autocompleteUrl}?type=<console|device|speakerarray|commbeltpack>&q=...` and consumes `{results: [{id, contentTypeId, name, detail}, ...]}` exactly as plan 01 returns.
- **No blockers, no deferred issues.** Worktree-only changes; orchestrator owns the merge back to main.

---
*Phase: 08-canvas-smart-shapes-connectors*
*Completed: 2026-05-20*
