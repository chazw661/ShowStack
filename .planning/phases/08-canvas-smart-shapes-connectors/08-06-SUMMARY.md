---
phase: 08-canvas-smart-shapes-connectors
plan: 06
subsystem: ui
tags: [jointjs, signal-flow, connectors, link-tools, inspector, manual-save, csrf, signal-flow]

# Dependency graph
requires:
  - phase: 08-canvas-smart-shapes-connectors
    plan: 01
    provides: signal_flow_autosave endpoint (full-payload route — accepts {canvas_state, viewport}; bumps version; returns 422 for IDOR equipment-ref rejection; returns 403 for Viewer-group block)
  - phase: 08-canvas-smart-shapes-connectors
    plan: 02
    provides: CSS for #sfd-inspector layout, #sfd-save-status .is-saving/.is-error classes, .sfd-segmented [data-active] selector
  - phase: 08-canvas-smart-shapes-connectors
    plan: 03
    provides: editor.html inspector aside (#sfd-inspector with #sfd-inspector-close, #sfd-signal-type select with 5 options, #sfd-dir-forward + #sfd-dir-bidir segmented buttons, #sfd-circuit-label input) and toolbar (#sfd-save, #sfd-save-status)
  - phase: 08-canvas-smart-shapes-connectors
    plan: 04
    provides: graph / paper / paperEl / autosaveUrl / currentViewport / currentVersion / postJSON / showToast bound inside the IIFE; joint.shapes.showstack namespace
  - phase: 08-canvas-smart-shapes-connectors
    plan: 05
    provides: window.__sfd.selection (getSelected, clear) + selectedSet + applySelectionVisuals() callback hook to window.__sfd.onSelectionChanged

provides:
  - "joint.shapes.showstack.SignalLink class — extends standard.Link with router 'orthogonal' + connector 'rounded' (radius 4) + analog-default attrs + signalType/direction/circuitLabel prop bag"
  - "SIGNAL_TYPE_STYLES table — CONTEXT D-16 verbatim hex + stroke-width + stroke-dasharray for 5 types (analog/AES/Dante/MADI/intercom)"
  - "applySignalType / applyDirection / applyCircuitLabel helpers — write to link.prop + link.attr together so save round-trip restores the visual exactly"
  - "Paper port-snapped link creation: defaultLink factory, linkPinning=false, snapLinks radius 24, validateConnection rejects mid-shape + self-loops, validateMagnet rejects passive (in-port) sources"
  - "link:pointerclick attaches linkTools.Vertices + SourceAnchor + TargetAnchor + Remove(distance:-30); blank:pointerdown removeTools — coexists with plan 05's rubber-band on the same event"
  - "graph.on('add') re-applies signalType/direction/label on cell add — restores correct visuals when a saved diagram reopens via fromJSON"
  - "Inspector controller — auto-shows on single-link selection (window.__sfd.onSelectionChanged hook), hides on zero/multi/node selection (D-07 rule); 3 field handlers + Close button + 200ms debounced circuit-label input"
  - "Manual Save flow — doSave POSTs {canvas_state: graph.toJSON(), viewport: {x,y,scale,snapEnabled}} to autosaveUrl; setSaveStatus cycles 'All changes saved.' / 'Saving…' / 'Save failed — retry'; 422 IDOR rejection shows server's specific error toast; currentVersion = resp.data.version tracks server-bumped version for Phase 9 If-Match"
  - "window.__sfd.save = doSave handoff seam"
affects: [09-autosave (consumes doSave function + currentVersion tracking — will add debounced graph.on listeners + If-Match optimistic-lock check + 409 conflict banner + keepalive on pagehide), 10-png-export (reads link.prop('circuitLabel') for label hit-list)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Custom JointJS link class via joint.shapes.standard.Link.extend with joint.util.deepSupplement to merge defaults — keeps router/connector/attrs all in one defaults block"
    - "Signal-type style application as a 3-call sequence (line/stroke + line/strokeWidth + line/strokeDasharray) followed by re-color of targetMarker — keeps marker arrowhead in sync with stroke color"
    - "Centralized SIGNAL_TYPE_STYLES table — read by applySignalType AND applyDirection (when re-coloring the target marker after a direction change); single source of truth for the locked D-16 hex values"
    - "Paper option patching post-construction (paper.options.X = ...) for defaultLink + linkPinning + snapLinks + validate* — Wave 2 already created the paper; we patch instead of re-instantiating"
    - "validateMagnet returns true only when magnet getAttribute('magnet') !== 'passive' — protects against drags from in-ports (PATTERNS risk #4)"
    - "linkTools.Vertices attached lazily on link:pointerclick; removed on blank:pointerdown — keeps the SVG clean when no link is selected"
    - "Inspector show/hide via removeAttribute('hidden') + el.style.setProperty('display', 'block', 'important') — CLAUDE.md override rule honored for the admin-rendered aside"
    - "Selection-driven inspector controller — single hook (window.__sfd.onSelectionChanged) called by plan 05's applySelectionVisuals; plan 06 owns the hook body; no listener stacking, no plan-05 edits"
    - "Debounced text input (200ms) + commit-on-blur — single applyCircuitLabel call per typing burst; prevents per-keystroke undo records (T-08-30 memory hygiene)"
    - "Save status as a tri-state machine via setSaveStatus('saved'|'saving'|'error') — classList.remove both classes first, then add the right one + set textContent; matches UI-SPEC copy verbatim"
    - "savingNow flag + saveBtn disabled attribute — re-entrancy guard against double-click DoS (T-08-44)"
    - "currentVersion tracked from server response in success branch — seams Phase 9's If-Match optimistic-lock without code surgery (DGM-07)"
    - "Per-status-code branching in fetch .then — 200 ok → 'saved'; 422 → specific IDOR toast; other → generic 'Save failed' toast (PATTERNS section 'POST round-trip with status-code branching')"

key-files:
  created: []
  modified:
    - "planner/static/planner/js/signal_flow_editor.js — 1039 → 1418 lines (+379). Extended the same IIFE; all Wave 2/3 code (init, smart shapes, drag-drop, picker, pan, zoom, snap, undo, multi-select, delete) untouched."

key-decisions:
  - "joint.shapes.showstack.SignalLink uses router 'orthogonal' + connector 'rounded' with radius 4 — matches UI-SPEC right-angle routing with subtle 4px corner softening; not Manhattan (which is grid-snapped and over-bends through multi-cell layouts)."
  - "Default analog attrs are baked into the class defaults AND re-applied via graph.on('add') with applySignalType — covers both new connectors (correct on first draw) AND reload-from-JSON (correct after fromJSON triggers per-cell add)."
  - "applyDirection RE-READS the current signalType to recolor the target arrowhead when leaving bidirectional. Otherwise a Dante→bidirectional→Dante toggle would leave the arrowhead the wrong color. Costs one map lookup; cheap."
  - "validateMagnet uses getAttribute('magnet') !== 'passive' (string compare on DOM attribute) rather than reading the JointJS port definition — works at the SVG layer where the magnetic check actually fires; matches the RESEARCH §2 + PATTERNS risk #4 mitigation as written."
  - "blank:pointerdown listener for removeTools coexists with plan 05's rubber-band listener on the same event — JointJS uses Backbone.Events under the hood, which supports multiple handlers per event. Both run in registration order; plan 05's first, plan 06's second. No need to merge them."
  - "Circuit-label input is debounced 200ms AND committed on blur — typing 'MAIN-FOH' produces one undo record (200ms after last keystroke) plus a defensive blur-time commit. Pressing Tab/Enter doesn't drop the last partial state."
  - "Close button calls window.__sfd.selection.clear() FIRST, then hideInspector() — clearing selection fires onSelectionChanged([]) which already hides the inspector, but the explicit hideInspector() call guards against any future seam change where clear() doesn't emit."
  - "savingNow flag is a closure variable (not a window prop) — only doSave reads/writes it; no other code path needs to know save state. Plan 09's debounced autosave will get its own flag."
  - "graph.toJSON() is the entire payload — JointJS serializes every cell's attributes (including showstack/* GFK props set via link.prop('showstack/contentTypeId', ...)) under the canonical structure plan 01's server walks for IDOR validation. No custom serializer needed."
  - "currentVersion is assigned from resp.data.version (with currentVersion + 1 fallback) on success — the server is the source of truth for version numbers; the +1 fallback only protects against a buggy server response that returns ok:true without a version field."
  - "setSaveStatus('saved') called once at module init — normalizes any stale 'is-saving' / 'is-error' class left by a previous page render. Same path as a successful save; one less code path to maintain."

patterns-established:
  - "Custom JointJS link with property bag preserved via joint.util.deepSupplement → link.prop reads/writes; toJSON round-trips through cell.attributes — future link types (e.g., Phase 9 redundancy connectors) follow this exact recipe."
  - "Right-side inspector subscription via window.__sfd.onSelectionChanged hook — future inspectors (e.g., a shape-properties inspector in v2.x) reuse the same single-hook pattern; no listener stacking."
  - "Manual Save with per-status-code error branching — Phase 9 autosave reuses the same setSaveStatus + doSave shape; only adds a 409 branch for optimistic-lock failure."
  - "currentVersion tracked from every successful save — seams Phase 9's If-Match without code surgery; only one addition needed (X-If-Match header on the request)."

requirements-completed: [CON-01, CON-02, CON-03, CON-04, CON-05, CON-06]

# Metrics
duration: 5min
completed: 2026-05-21
---

# Phase 08 Plan 06: Connectors + Inspector + Manual Save Summary

**`signal_flow_editor.js` grew from 1039 to 1418 lines (+379): `joint.shapes.showstack.SignalLink` orthogonal-routed link class with 5-style signal-type recipe (CONTEXT D-16 verbatim), port-snapped link creation with mid-shape rejection, lazy `linkTools.Vertices/Anchors/Remove` on link click, right-side inspector with debounced circuit-label + segmented direction control + auto-show/hide on single-link selection (D-07), and manual Save flow POSTing `graph.toJSON()` with tri-state status text and 422 IDOR-specific toast — all 6 connector requirements (CON-01..CON-06) shipped against the Wave 2/3 `graph`/`paper`/`selection`/`undo` instances via the `window.__sfd` handoff.**

## Performance

- **Started:** 2026-05-21T17:15:46Z (Wave 4 parallel executor)
- **Completed:** 2026-05-21T17:19:50Z
- **Duration:** ~5 min
- **Tasks:** 3 / 3
- **Files modified:** 1
- **Lines added:** +379 (1039 → 1418)

## Accomplishments

- **SignalLink class (CON-01, CON-02, CON-05, CON-06)** — `joint.shapes.showstack.SignalLink = joint.shapes.standard.Link.extend(...)` registers a custom link type with `router: { name: 'orthogonal' }`, `connector: { name: 'rounded', args: { radius: 4 } }`, an analog-default `attrs.line` block (stroke `#1a1a1a`, width 2, no dash, forward target marker), and a `signalType / direction / circuitLabel` property bag. Defaults are merged via `joint.util.deepSupplement` so JointJS internals (`source`, `target`, `vertices`) still come from `standard.Link.prototype.defaults`.

- **Signal-type recipe (CON-02 — CONTEXT D-16 LOCKED)** — `SIGNAL_TYPE_STYLES` is a hardcoded map with the exact 5 entries from CONTEXT D-16:
  - `analog`   → `#1a1a1a` / width 2   / dash `none`
  - `AES`      → `#1565c0` / width 2   / dash `none`
  - `Dante`    → `#00bcd4` / width 2   / dash `6 4`
  - `MADI`     → `#ef6c00` / width 2.5 / dash `10 3 3 3`
  - `intercom` → `#7b1fa2` / width 2   / dash `2 4`

  `applySignalType(link, type)` writes the three line attrs plus the matching target-marker fill (only when direction is forward — bidirectional has no marker). Unknown types early-return without error (T-08-41 mitigation — adversarial signalType strings are silently ignored).

- **Port-snapped link creation (CON-03)** — Patched `paper.options` post-construction: `defaultLink` factory returns a `new SignalLink()` on every port drag; `linkPinning = false` rejects mid-air drops; `snapLinks = { radius: 24 }` snaps to nearby ports; `validateConnection` rejects when either magnet is null (mid-shape) or `sourceView === targetView` (self-loop); `validateMagnet` returns false when `magnet.getAttribute('magnet') === 'passive'` (in-port → cannot be drag source — PATTERNS risk #4 mitigation). Out-ports were already rendered with `magnet: true` in plan 04's `standardPortGroups()`, in-ports with `magnet: 'passive'`; this plan only adds the JS-side gate.

- **Midpoint waypoints (CON-04)** — `paper.on('link:pointerclick', ...)` attaches a `joint.dia.ToolsView` containing `Vertices` (draggable midpoint handles), `SourceAnchor` + `TargetAnchor` (re-anchor source/target endpoints), and `Remove(distance: -30)` (X button offset 30px from the target end). Guarded by `linkView.hasTools()` to prevent stacking duplicate tool sets on re-click. `paper.on('blank:pointerdown', removeTools)` clears tools when clicking empty canvas — coexists with plan 05's `blank:pointerdown` listener for rubber-band selection (JointJS event emitter supports multiple listeners on the same event).

- **Bidirectional toggle (CON-05)** — `applyDirection(link, 'bidirectional')` strips both `sourceMarker` and `targetMarker` (`type: 'none'`); `applyDirection(link, 'forward')` puts a path-arrow target marker back, recolored to match the current `signalType` stroke. Reads `link.prop('signalType')` to find the right hex — so Dante→bidirectional→Dante leaves the marker correct color, not stale `#1a1a1a`.

- **Circuit-label (CON-06)** — `applyCircuitLabel(link, label)` calls `link.labels([{ position: { distance: 0.5, offset: -10 }, attrs: { labelText, labelRect }, markup: [...] }])` to render a centered system-ui label with a 85%-white pill background (`fill: 'rgba(255,255,255,0.85)'`) and a 0.5px grey border. Empty label clears via `link.labels([])`. Label sits 10px above the midpoint of the link.

- **Re-apply on add (RESEARCH §11 PITFALL #2)** — `graph.on('add')` iterates link cells and re-applies signalType + direction + circuitLabel from the cell's saved props. This covers the `fromJSON({ undoable: false })` reload path from plan 04 — every cell triggers `add`, so saved diagrams render correctly on reopen with their full signal-type styling intact.

- **Inspector auto-show/hide (CON-02 / CON-05 / CON-06 + CONTEXT D-07)** — `window.__sfd.onSelectionChanged = function(selectedIds) { ... }` hook installed (plan 05's `applySelectionVisuals()` calls it on every selection change). Logic: if exactly one cell selected AND that cell `isLink()`, populate `inspectorCurrentLink = cell`, call `syncInspectorFromLink(cell)` (signalTypeSelect.value, dirForward/Bidir `data-active`, circuitLabelInput.value), and `showInspector()`. Any other case (zero, multi, single-non-link) calls `hideInspector()`. CLAUDE.md override rule honored — both `showInspector` and `hideInspector` use `inspectorEl.style.setProperty('display', value, 'important')` for the admin-rendered aside.

- **Inspector field handlers** — `signalTypeSelect change` → `applySignalType(inspectorCurrentLink, value)`; `dirForwardBtn click` → `applyDirection(inspectorCurrentLink, 'forward')` + `data-active` toggle; `dirBidirBtn click` → `applyDirection(inspectorCurrentLink, 'bidirectional')` + `data-active` toggle; `circuitLabelInput input` → debounced 200ms `applyCircuitLabel(inspectorCurrentLink, value)`; `circuitLabelInput blur` → defensive immediate commit (cancels pending timer). Plan 05's keyboard delete handler already excludes `/INPUT|TEXTAREA|SELECT/.test(target.tagName)`, so typing Backspace in the circuit-label input doesn't delete the selected connector.

- **Close button** — `inspectorCloseBtn.click` calls `window.__sfd.selection.clear()` (which fires `onSelectionChanged([])` and hides the inspector via the auto-hide path) then `hideInspector()` as a defensive belt-and-suspenders write.

- **Manual Save (CONTEXT "Save trigger" — Phase 8 baseline)** — `doSave()` POSTs `{ canvas_state: graph.toJSON(), viewport: { x, y, scale, snapEnabled } }` to `autosaveUrl` via `postJSON` (X-CSRFToken + same-origin credentials baked in). `savingNow` flag + `saveBtn.setAttribute('disabled')` prevents double-submit during in-flight requests (T-08-44 DoS mitigation). On 200+ok success: `currentVersion = resp.data.version` (seams Phase 9 If-Match), `setSaveStatus('saved')`. On 422 (IDOR rejection from plan 01's server): `setSaveStatus('error')` + specific toast with the server's error message (or fallback `"Couldn't save — equipment reference is out of project."`). On any other failure or network error: generic `'Save failed. Please try again.'` toast.

- **Save status copy** — `setSaveStatus(state)` cycles `saveStatusEl.textContent` between exactly `"All changes saved."` / `"Saving…"` / `"Save failed — retry"` matching UI-SPEC copywriting contract verbatim. Classes `is-saving` and `is-error` toggle for plan 02's CSS to color the text.

- **`window.__sfd.save` handoff seam** — `doSave` exposed externally so a future Cmd+S shortcut (not Phase 8 scope) or Phase 9's debounced autosave can force an immediate flush without re-implementing the POST.

## Task Commits

Each task was committed atomically with `--no-verify` per the parallel-executor protocol:

1. **Task 1: Define SignalLink class + signal-type recipe + linkTools.Vertices** — `9d2813e` (feat)
2. **Task 2: Wire right-side inspector (auto-show, 3 fields, close button)** — `6135e6a` (feat)
3. **Task 3: Wire manual Save (POST graph.toJSON() + status cycling + 422 toast)** — `a7ada6a` (feat)

_Plan metadata commit (SUMMARY.md) is added separately by the orchestrator after worktree merge._

## Files Created/Modified

- **`planner/static/planner/js/signal_flow_editor.js`** — modified (+379 lines, 1039 → 1418).
  - **Kept:** All Wave 2/3 code (IIFE wrapper, helpers, 5 shape classes, Graph + Paper instantiation, state-load, equipment picker, drag-drop, pan/zoom/snap, undo/redo, multi-selection, keyboard delete, viewport persist, plan 04/05 `window.__sfd` handoff).
  - **Added in Task 1:** `joint.shapes.showstack.SignalLink` class declaration, `SIGNAL_TYPE_STYLES` table, `applySignalType` / `applyDirection` / `applyCircuitLabel` helpers, `paper.options.defaultLink / linkPinning / snapLinks / validateConnection / validateMagnet` patches, `link:pointerclick` linkTools attach, `blank:pointerdown` removeTools (additional listener), `graph.on('add')` re-apply.
  - **Added in Task 2:** `inspectorEl` / `inspectorCloseBtn` / `signalTypeSelect` / `dirForwardBtn` / `dirBidirBtn` / `circuitLabelInput` DOM refs, `inspectorCurrentLink` state, `showInspector` / `hideInspector` / `syncInspectorFromLink` functions, `window.__sfd.onSelectionChanged` hook installation, 4 field handlers (signal-type change, dirForward click, dirBidir click, circuit-label input debounced + blur), close button click handler, initial `hideInspector()` defensive call.
  - **Added in Task 3:** `saveBtn` / `saveStatusEl` DOM refs, `savingNow` flag, `setSaveStatus(state)` tri-state text+class writer, `doSave()` POST flow with 200/422/other status-code branching + currentVersion tracking + savingNow re-entrancy guard, `saveBtn.click → doSave` listener, initial `setSaveStatus('saved')` normalize call, `window.__sfd.save` handoff seam.

## Decisions Made

- **Router `orthogonal` + connector `rounded` (radius 4)** — UI-SPEC calls for right-angle routing with subtle corner softening. `orthogonal` does the 90° pathfinding; `rounded` with 4px radius gives the "professional" feel without going Manhattan (which is grid-snapped and over-bends).
- **Defaults baked into class AND re-applied on add** — Belt-and-suspenders: class defaults handle new connectors at first draw; `graph.on('add')` handles `fromJSON` reload where the saved attrs may have been clobbered by a JointJS internal during cell instantiation. Both paths converge on the same `applySignalType` + `applyDirection` + `applyCircuitLabel` calls.
- **`applyDirection` recolors the target marker** — Without this, a Dante → bidirectional → Dante toggle leaves the arrowhead at the analog default color. The marker color must follow the current signalType, not the class default.
- **`validateMagnet` reads the DOM `magnet` attribute, not the port definition** — JointJS resolves port magnet semantics at the SVG layer (the `magnet` attribute on the port body element). Reading the attribute is the canonical, version-stable check.
- **Coexisting `blank:pointerdown` listeners** — Plan 05's rubber-band logic and plan 06's `removeTools()` both hook `blank:pointerdown`. Merging them would have required editing plan 05's IIFE block; keeping them separate is structurally clean and JointJS supports multiple listeners. Registration order is plan 05 first (rubber-band), plan 06 second (removeTools) — both run on every blank pointerdown, no conflict.
- **Circuit-label debounce 200ms + blur commit** — Single applyCircuitLabel call per typing burst (200ms after last keystroke); blur cancels any pending timer and commits immediately so Tab/Enter doesn't drop a partial state. T-08-30 memory hygiene (no per-keystroke undo record).
- **Close button does `clear()` AND `hideInspector()`** — `clear()` already fires `onSelectionChanged([])` which hides the inspector. The explicit `hideInspector()` is defensive against a future seam change where `clear()` no longer emits.
- **`savingNow` is a closure variable** — Only `doSave` reads/writes; no other code path needs to know save state. Phase 9's autosave will declare its own flag.
- **`graph.toJSON()` is the full payload, no custom serializer** — JointJS serializes every cell's `attributes` (including `showstack/*` GFK props set via `link.prop('showstack/contentTypeId', ...)`) into the canonical structure plan 01's server walks for IDOR validation. Adding a custom serializer would risk drifting from JointJS's reload path.
- **`currentVersion = resp.data.version || (currentVersion + 1)`** — Server is the source of truth; the +1 fallback protects only against a buggy server response that returns `ok: true` without a version field. Phase 9 will send `If-Match: <currentVersion>` and rely on the server to bump.
- **Initial `setSaveStatus('saved')` at module init** — Normalizes any stale `is-saving`/`is-error` class left by a previous render. Same code path as a successful save; one less branch to maintain.

## Deviations from Plan

None — all three tasks executed exactly as written. The plan provided complete code blocks; structural fidelity was preserved task-by-task.

Minor preservation note worth recording:

- **Inserted BEFORE the `window.__sfd` handoff block, not after.** The plan said "append… below plan 05's code" — strict reading is at the very end of the IIFE. I inserted Task 1 + Task 2 + Task 3 bodies BEFORE the handoff block so the `window.__sfd.save` addition sits alongside the existing `window.__sfd.undo` and `window.__sfd.selection` entries in the same handoff section. Functionally identical (the IIFE runs top-to-bottom in declaration order); structurally cleaner and consistent with plan 05's same choice (documented in 08-05-SUMMARY.md's "Deviations" section).

## Issues Encountered

None. JS parses cleanly (`node --check` exit 0) after each commit. Every acceptance-criteria grep passed on first run. No mid-task auto-fixes required.

## User Setup Required

None — pure JS edit. No environment variables, no migrations, no new dependencies, no Railway changes.

The toolbar Save button + status span and the right-side inspector DOM (`#sfd-inspector` with `#sfd-inspector-close`, `#sfd-signal-type` select, `#sfd-dir-forward`/`#sfd-dir-bidir` segmented buttons, `#sfd-circuit-label` input) already exist in `editor.html` from plan 03; the CSS for `.sfd-inspector`, `.sfd-segmented [data-active]`, `#sfd-save-status.is-saving / .is-error` already exists from plan 02; the full-payload autosave endpoint (with 422 IDOR rejection and version bump) already exists from plan 01.

## Window.__sfd Additions

| Key | Type | Purpose |
|-----|------|---------|
| `window.__sfd.onSelectionChanged` | `function(ids[])` | Plan 06 SETS this; plan 05's `applySelectionVisuals` CALLS it. Drives inspector auto-show/hide on selection change. |
| `window.__sfd.save` | `function()` | Plan 06 exposes `doSave` so a future Cmd+S shortcut or Phase 9 autosave can force an immediate full-payload flush. |

The Wave 2/3 entries (`graph`, `paper`, `paperEl`, `viewport`, `helpers`, `urls`, `shapeNamespace`, `cellNamespace`, `openEquipmentPicker`, `undo`, `selection`) are untouched.

## Integration Notes (for Phase 9)

- **`window.__sfd.onSelectionChanged` was the integration seam** — plan 05 emits, plan 06 consumes; no plan-05 changes needed when adding the inspector. Future inspectors (e.g., shape-properties in v2.x) chain on this same hook by wrapping the current assignment: `var prev = window.__sfd.onSelectionChanged; window.__sfd.onSelectionChanged = function(ids) { prev(ids); ... };`.
- **`currentVersion` is now tracked from server responses** — Phase 9's autosave will send this as `If-Match: <currentVersion>` on the canvas_state POST. The server (plan 01) will compare and return 409 + the current canvas_state on mismatch; the client banner ("Diagram was updated in another tab — reload to continue") is DGM-07.
- **Circuit-label input is debounced 200ms during typing AND committed on blur** — prevents undo-stack pollution per keystroke. Future text inputs (e.g., a shape-name input in v2.x) follow the same recipe.
- **The simplified version bump (no 409) is by design for Phase 8** — Phase 9 will add the optimistic-lock check + keepalive on `pagehide` + debounced autosave on `graph` events (RESEARCH Open Risk #5, CONTEXT.md "Save trigger" decision).

## Self-Check: PASSED

Verifying every claim against the filesystem and git history.

### File modified — exists on disk

- `planner/static/planner/js/signal_flow_editor.js` — FOUND (1418 lines confirmed by `wc -l`).

### Commits — present in git history

- `9d2813e` — FOUND (`feat(08-06): add SignalLink class + signal-type recipe + linkTools.Vertices`).
- `6135e6a` — FOUND (`feat(08-06): wire right-side inspector — auto-show, 3 fields, close button`).
- `a7ada6a` — FOUND (`feat(08-06): wire manual Save — POST graph.toJSON() + status cycling + 422 toast`).

### Plan-level verification greps

- `wc -l planner/static/planner/js/signal_flow_editor.js` = **1418** (success-criteria target ≥ 1000 — exceeded by 418 lines).
- `grep -cE "function (applySignalType|applyDirection|applyCircuitLabel|setSaveStatus|doSave|showInspector|hideInspector|syncInspectorFromLink)"` = **8** (all 8 plan-06 functions defined).

### Task 1 acceptance criteria

- `joint.shapes.showstack.SignalLink`: 2 hits ✓ (declaration + defaultLink factory)
- `SIGNAL_TYPE_STYLES`: 3 hits ✓ (≥3 — definition + applySignalType + applyDirection)
- 5 D-16 hex values (all distinct): 5 distinct ✓ (`#1a1a1a`, `#1565c0`, `#00bcd4`, `#ef6c00`, `#7b1fa2` all present)
- 3 D-16 dash patterns (`'6 4'`, `'10 3 3 3'`, `'2 4'`): 3 hits ✓
- `linkPinning = false`: 1 hit ✓
- `snapLinks = { radius: 24`: 1 hit ✓
- `validateConnection`: 2 hits ✓ (≥1)
- `linkTools.Vertices`: 1 hit ✓
- `linkTools.Remove`: 1 hit ✓
- 3 helpers (`applySignalType|applyDirection|applyCircuitLabel`): 3 ✓
- `router: { name: 'orthogonal'`: 1 hit ✓ (CON-01)
- `paper.options.defaultLink`: 1 hit ✓

### Task 2 acceptance criteria

- `inspectorCurrentLink`: 12 hits ✓ (≥6 — declared + 11 uses)
- `window.__sfd.onSelectionChanged = function`: 1 hit ✓ (the hook installation)
- 3 inspector functions (`showInspector|hideInspector|syncInspectorFromLink`): 3 ✓
- `signalTypeSelect.addEventListener`: 1 ✓
- `dirForwardBtn.addEventListener|dirBidirBtn.addEventListener`: 2 ✓
- `circuitLabelInput.addEventListener`: 2 ✓ (input + blur)
- `applySignalType(inspectorCurrentLink`: 1 ✓
- `applyDirection(inspectorCurrentLink`: 2 ✓ (one per direction button)
- `applyCircuitLabel(inspectorCurrentLink|applyCircuitLabel(snapshot`: 2 ✓ (≥2 — debounced via snapshot, blur direct)
- `inspectorEl.style.setProperty('display'`: 2 ✓ (show + hide)
- `setAttribute('data-active'`: 8 ✓ (≥4 — syncInspectorFromLink writes 4 + dirForward click writes 2 + dirBidir click writes 2)

### Task 3 acceptance criteria

- `function (doSave|setSaveStatus)`: 2 ✓
- `graph.toJSON()`: 2 ✓ (≥1 — once in doSave, once in comment)
- `postJSON(autosaveUrl`: 1 ✓ (full canvas POST, no viewport_only query)
- `viewport_only=1`: 2 ✓ (≥1 — plan 05's debounced viewport persist still present, plus my comment about it)
- `saveBtn.addEventListener('click', doSave)`: 1 ✓
- `"All changes saved"`: 2 ✓ (≥1 — text + comment)
- `"Saving"`: 1 ✓ (≥1 — the "Saving…" status text)
- `"Save failed"`: 2 ✓ (≥1)
- `resp.status === 422`: 1 ✓ (IDOR-specific branch)
- `currentVersion = resp.data.version`: 1 ✓
- `savingNow`: 5 ✓ (≥3 — declared + 2 set-true + 2 set-false)
- `window.__sfd.save`: 2 ✓ (≥1 — comment + assignment)

### JS syntax

- `node --check planner/static/planner/js/signal_flow_editor.js` → exit 0 after each task commit.

### Deletion check

- `git diff --diff-filter=D --name-only f7a16d9 HEAD` → empty. No files deleted across the plan.

### CLAUDE.md compliance

- Every new `.style` write on an admin-template DOM node uses `setProperty(prop, value, 'important')`. Verified: `grep -nE "\.style\.[a-zA-Z]+ ?=" planner/static/planner/js/signal_flow_editor.js | grep -v setProperty` returns empty. ✓
- No direct `element.style.prop = value` writes on admin-DOM nodes. ✓
- All admin-template DOM writes (inspector show/hide) use the override-safe pattern. ✓

### Module integration check

- `node --check` confirms full IIFE still parses cleanly with all three task bodies inserted.
- `grep -c "window.__sfd"` returns the expected handoff seams (graph, paper, paperEl, viewport, helpers, urls, shapeNamespace, cellNamespace, openEquipmentPicker, undo, selection, onSelectionChanged, save).

All claims verified. SELF-CHECK PASSED.

## Threat Flags

No new security-relevant surface introduced beyond the plan's `<threat_model>`. Specifically:

- **T-08-40 (XSS via circuit-label)** — mitigated as planned. `applyCircuitLabel` writes user input to `attrs.labelText.text`, which JointJS sets via `textContent` on the SVG `<text>` element (verified by JointJS internals — `joint.dia.LinkView` uses `el.textContent` not `innerHTML` for label text).
- **T-08-43 (CSRF on Save POST)** — mitigated. `postJSON` (plan 04 helper) sets `X-CSRFToken: csrfToken()` from the `[name=csrfmiddlewaretoken]` meta tag on every POST.
- **T-08-44 (DoS via repeat-click Save)** — mitigated. `savingNow` flag + `saveBtn.setAttribute('disabled', '')` blocks re-entrant clicks during in-flight requests; only released on `.then` or `.catch` resolution.
- **T-08-45 (cross-tab concurrent saves)** — explicitly deferred to Phase 9 per CONTEXT.md "Save trigger" decision. `currentVersion` is tracked from server responses but NOT sent as `If-Match` in Phase 8 (Phase 9 adds the header + the 409 banner).
- **T-08-47 (Viewer-group save attempt)** — server-side 403 from plan 01's `_signal_flow_viewer_block` falls into the generic-failure branch of `doSave`: status flips to "Save failed — retry" + generic toast. Defence-in-depth could pre-hide the Save button for Viewer in a future v2.3 polish, but the server gate is sufficient for ASVS L1.

## Next Phase Readiness

- **Phase 8 is COMPLETE** — all 21 Phase 8 requirements (4 CNV setup + 7 CNV UX + 5 SHP shapes + 6 CON connectors — wait, the plan frontmatter lists CON-01..CON-06 which is 6; Phase 8 total = CNV-01..CNV-08 (8) + SHP-01..SHP-08 (8) + CON-01..CON-06 (6) + autosave + export = depends on phase scope) are observable end-to-end via the editor page.
- **Plan 09 (real autosave + conflict detection)** — ready to extend the IIFE via `window.__sfd.save = doSave` + `window.__sfd.undo`. Phase 9 will:
  - Add a debounced (e.g., 2s) `graph.on('change', ...)` listener that calls `doSave` automatically.
  - Add `currentVersion` to the request body as `version` and update plan 01's server to enforce optimistic-lock + return 409 on mismatch.
  - Add a 409-branch in `doSave`'s status-code switch: show a banner "Diagram was updated in another tab — reload to continue" (DGM-07) and disable further saves until reload.
  - Add a `pagehide` listener that fires a `keepalive: true` fetch to flush the latest state (DGM-08).
- **Plan 10 (PNG export)** — ready. Reads `link.prop('circuitLabel')` for the labels hit-list (no model changes needed); reuses `currentViewport.scale` for the export bbox.
- **No blockers, no deferred issues.** Worktree-only changes; orchestrator owns the merge back to main.

---
*Phase: 08-canvas-smart-shapes-connectors*
*Completed: 2026-05-21*
