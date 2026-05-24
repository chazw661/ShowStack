---
phase: 11-ports-and-resize
verified: 2026-05-24T00:00:00Z
updated: 2026-05-24T18:00:00Z
status: gaps_found
score: 9/9 must-haves verified structurally; 5 functional gaps reported in browser testing
overrides_applied: 0
gaps_reported: 5
human_uat: 11-HUMAN-UAT.md
human_verification:
  - test: "Port authoring UI: select any of the 7 shape types → inspector shows 'Ports' section with Top / Bottom / Left / Right sub-sections each having a '+ Add port' button"
    expected: "Four labeled edge sections visible; clicking '+ Add port' on any edge creates a port row with ordinal, label input, and trash icon; port dot appears on canvas at auto-distributed position"
    why_human: "DOM build + CSS rendering requires a live browser; cannot verify inspector layout programmatically"
  - test: "Port label autocomplete: click '+ Add port', type 1 char in the new label input"
    expected: "Autocomplete dropdown appears within ~200ms with up to 8 project-scoped suggestions in 'label — source' format; selecting a row OR typing freeform and blurring commits the label via renameAuthoredPort"
    why_human: "Requires live server + project data; autocomplete endpoint is project-scoped"
  - test: "PORT-05 connector survival: add a port, draw a connector to it, then trash the port via inspector"
    expected: "Connector endpoint moves to the shape's edge midpoint (not deleted); port row disappears from inspector; remaining ports on that edge redistribute"
    why_human: "Requires live JointJS canvas interaction to observe connector re-anchoring"
  - test: "SHP-RESIZE-01: select each of the 7 shape types (Console, Device, SpeakerArray, CommBeltPack, Generic, Processor, Amp) → 4 teal corner handles appear; deselect → handles disappear; multi-select → no handles"
    expected: "All 7 types show handles on single selection; handles absent for connectors and multi-select"
    why_human: "Visual browser check of JointJS SVG tool rendering"
  - test: "SHP-RESIZE-02 min-size: drag BR corner inward on a port-less Console shape"
    expected: "Shape stops shrinking at 180×60 (ABSOLUTE_FLOOR); adding authored ports with long labels grows the floor"
    why_human: "Requires live drag interaction to observe min-size clamping"
  - test: "SHP-RESIZE-03 autosave + undo: drag a corner handle to resize, wait 1500ms, then Ctrl+Z"
    expected: "DevTools Network shows autosave POST within 1500ms of drag-end; Ctrl+Z reverses the resize in one gesture; page reload persists resized dimensions"
    why_human: "Requires live browser with DevTools to observe autosave POST and undo behavior"
  - test: "PORT-06 auto-expansion: add enough ports to a small shape (e.g. 8 ports on Top edge of Console 180×60) that they cannot fit at 24px spacing"
    expected: "Shape grows to fit; toast 'Shape resized to fit ports.' appears and auto-dismisses; removing a port does NOT shrink the shape"
    why_human: "Requires live canvas to observe shape grow + toast appearance"
---

# Phase 11: Per-Shape Labeled Ports + Resizable Shapes — Verification Report

**Phase Goal:** Engineer-authored ports on all 4 edges with auto-equal-spacing, dropdown-or-custom labels via refactored `attachAutocompleteToInput` factory, corner-handle resize via `joint.elementTools.Control` subclass (MPL-2.0 only), min-size clamping, connector snap targeting per-port with whole-shape v2.2 back-compat. Closes PORT-01..06, SHP-RESIZE-01..03.
**Verified:** 2026-05-24
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | REQUIREMENTS.md PORT-01 reads "4 edges: Top, Bottom, Left, Right" | ✓ VERIFIED | `grep -c "four edges per shape"` returns 1; "three edges" count is 0; commit c0abf2d |
| 2 | `attachAutocompleteToInput(inputEl, url, onSelect)` factory exists with unique listbox IDs | ✓ VERIFIED | Function at line 2496; `_acAttachCounter` declared; listbox IDs use `sfd-label-suggestions-<id>`; CSS updated to `.sfd-ac-listbox` class; commit 3e974e8 |
| 3 | Phase 10 circuit-label combobox behavior preserved | ? HUMAN_NEEDED | `attachAutocompleteToInput(circuitLabelInput, labelAutocompleteUrl, null)` wired at line 2652; structural check passes; requires browser smoke-test to confirm behavioral parity |
| 4 | All 13 port-authoring helpers exist in module scope | ✓ VERIFIED | All functions found: `directionForEdge` (150), `cellHasAnyAuthoredPort` (157), `getAuthoredPortsByEdge` (163), `edgeMidpointInPaperCoords` (170), `redistributeEdgePorts` (180), `reanchorLinksFromPort` (211), `convertCellFromGenericToAuthored` (234), `maybeAutoExpand` (263), `addAuthoredPort` (292), `removeAuthoredPortWithSurvival` (329), `renameAuthoredPort` (350), `portLabelPositionForEdge` (359), `portLabelMarkupForEdge` (390); `window.__sfd.ports` at line 2439; commits 86b2fa8 + e70fc5a |
| 5 | D-13 back-compat: shapes with 0 authored ports retain 4 generic ports; first authored port triggers whole-shape conversion | ✓ VERIFIED | All 7 shapes use `portsForRect()` in defaults (lines 613/633/653/674/693/714/735); `addAuthoredPort` guard `if (!cellHasAnyAuthoredPort(cell)) convertCellFromGenericToAuthored(cell)` at line 296; conversion removes all non-authored ports atomically in `startBatch('phase11-convert-to-authored')` |
| 6 | PORT-05 connector survival: `reanchorLinksFromPort` called BEFORE `removePort` | ✓ VERIFIED | `removeAuthoredPortWithSurvival` at line 329: saves edge → `reanchorLinksFromPort(cell, portId)` → `cell.removePort(portId)` → redistribute; pre-removal reanchor present; commit 86b2fa8 |
| 7 | Inspector port-authoring UI: `buildPortAuthorBlock` / `refreshPortAuthorBlock` wired into `setInspectorMode('node')` | ✓ VERIFIED | Lines 2029 (buildPortAuthorBlock), 2096 (refreshPortAuthorBlock); wired at lines 2193–2195: lazy build + `display:block` + `refreshPortAuthorBlock(cell)`; port block hidden in connector branch at line 2170; commits 8fddd96 + 41bf45e |
| 8 | Port label autocomplete via `attachAutocompleteToInput` with `renameAuthoredPort` onSelect | ✓ VERIFIED | Lines 2136–2143: `attachAutocompleteToInput(input, labelAutocompleteUrl, function(label){ window.__sfd.ports.rename(...) })` with ES5-safe IIFE closure per port row; trash icon calls `removeWithSurvival` in undo batch |
| 9 | Port labels render visibly on canvas: `portLabelPositionForEdge` and `portLabelMarkupForEdge` real implementations; CSS Section 14 | ✓ VERIFIED | Stubs replaced: `portLabelPositionForEdge` switch (top/bottom/left/right) at line 359; `portLabelMarkupForEdge` returns 11px system-font markup at line 390; CSS Section 14 at line 811: `.joint-port-label text { opacity:1 !important; ... }` |
| 10 | `CornerResize` tool extends `joint.elementTools.Control` (not paid `Resize`); 4 corner handles on any single element selection | ✓ VERIFIED | `var CornerResize = joint.elementTools.Control.extend({...})` at line 513; `getPosition`/`setPosition` for tl/tr/bl/br corners; `attachResizeTools` at line 575; wired in `onSelectionChanged` at line 1859 for single-element selection; detached for connector/multi-select/empty |
| 11 | `computeMinSize` uses `ABSOLUTE_FLOORS` for 7 shape types + live port-count/label-width formula | ✓ VERIFIED | `ABSOLUTE_FLOORS` table at line 425 with all 7 types; `computeMinSize` at line 452; `measureLabelWidth` memoized Canvas-2D at line 440; `window.__sfd.resize = { computeMinSize, measureLabelWidth }` at line 2455 |
| 12 | `change:size` fires autosave (SHP-RESIZE-03) AND live port redistribute (D-06) | ✓ VERIFIED | Line 2364: `graph.on('add remove change:source change:target change:size', scheduleAutosave)`; line 2372: separate `graph.on('change:size', ...)` calls `redistributeEdgePorts` for all 4 edges + `view.updateTools()`; undo records `change:size` via generic `graph.on('change', ...)` at line 1288 |
| 13 | `maybeAutoExpand` fully implemented (PORT-06): grows toward right/bottom, Math.ceil snap, toast only when grown | ✓ VERIFIED | Lines 263–287: reads `cell.size()` + `computeMinSize(cell)`, only grows (no shrink path), `Math.ceil` snap, `cell.resize(newW, newH)`, `showToast('Shape resized to fit ports.', 'info')`; `cell.resize` fires `change:size` → Plan 11-05 listeners handle autosave + redistribute; commit d9c0409 |

**Score:** 9/9 truths verified (automated), 7 human verification items required for behavioral confirmation

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.planning/REQUIREMENTS.md` | PORT-01 amended to 4 edges | ✓ VERIFIED | Line 15: "four edges per shape: **Top**, **Bottom**, **Left**, **Right**"; commit c0abf2d |
| `planner/static/planner/js/signal_flow_editor.js` | All Phase 11 helpers + CornerResize + inspector UI | ✓ VERIFIED | `node --check` exit 0; 2708 lines; all 13+ functions present at correct positions |
| `planner/static/planner/css/signal_flow.css` | Sections 14 (port labels), 15 (resize handles), 16 (inspector rows) | ✓ VERIFIED | Section 16 at line 711, Section 14 at line 811, Section 15 at line 833; all `.sfd-ac-listbox` class migration from `#sfd-label-suggestions` confirmed |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `attachAutocompleteToInput` BC call site | `circuitLabelInput` | Line 2652: `attachAutocompleteToInput(circuitLabelInput, labelAutocompleteUrl, null)` | ✓ WIRED | Old `initAutocomplete()` removed; single factory in use |
| `+ Add port` click | `window.__sfd.ports.add(cell, edge, '')` | Click handler in `buildPortAuthorBlock` at line 2071 | ✓ WIRED | Correctly passes empty string as initial label |
| Port row label input | `renameAuthoredPort(cell, portId, label)` | `attachAutocompleteToInput` with onSelect closure at line 2136 | ✓ WIRED | onSelect calls `window.__sfd.ports.rename` |
| Trash icon click | `window.__sfd.ports.removeWithSurvival(cell, portId)` | Click handler at line 2145 wrapped in undo batch | ✓ WIRED | Uses PORT-05-safe removal |
| `setInspectorMode('node', cell)` | `buildPortAuthorBlock` + `refreshPortAuthorBlock` | Lines 2193–2195 | ✓ WIRED | Lazy build + show + refresh on every node selection |
| Single shape selection | `attachResizeTools(cell)` | `window.__sfd.onSelectionChanged` at line 1859 | ✓ WIRED | Detached for connectors, multi-select, and empty |
| `CornerResize.setPosition` | `model.resize(newW, newH)` + `model.position(newX, newY)` | `setPosition` at lines 537–571 | ✓ WIRED | All 4 corners with correct opposite-corner math |
| `change:size` | `scheduleAutosave` + `redistributeEdgePorts` | Two listeners at lines 2364 and 2372 | ✓ WIRED | SHP-RESIZE-03 autosave + D-06 live redistribute |
| `addAuthoredPort` / `renameAuthoredPort` | `maybeAutoExpand(cell)` | Call sites at lines 322 and 355 | ✓ WIRED | Both mutators call the fully-implemented expand function |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `refreshPortAuthorBlock` | `port.showstack.label` | `window.__sfd.ports.getByEdge(cell, edge)` → `cell.getPorts()` → JointJS graph state | Yes — from live JointJS cell model | ✓ FLOWING |
| `portLabelPositionForEdge` / `portLabelMarkupForEdge` | Port label SVG `<text>` | `addAuthoredPort` writes `attrs.label.text = label` and `showstack.label = label` | Yes — engineer-authored string via `renameAuthoredPort` dual-write | ✓ FLOWING |
| `computeMinSize` | `minWidth` / `minHeight` | `getAuthoredPortsByEdge(cell, edge)` → live port array; `measureLabelWidth` → Canvas-2D measurement | Yes — real port count and label width data | ✓ FLOWING |
| `maybeAutoExpand` | `newW` / `newH` | `cell.size()` current + `computeMinSize(cell)` min | Yes — compare real values; resize only if min exceeds current | ✓ FLOWING |
| canvas_state persistence | Entire graph | `graph.toJSON()` in autosave via `scheduleAutosave` | Yes — JointJS-native ports.items[N] with showstack namespace round-trip through JSON | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| JS syntax validity | `node --check signal_flow_editor.js` | Exit 0 | ✓ PASS |
| `attachAutocompleteToInput` function present | `grep -c "function attachAutocompleteToInput"` | 1 | ✓ PASS |
| All port helper functions present | grep for each of 13 functions | All found at correct module-scope positions | ✓ PASS |
| D-13 guard in `addAuthoredPort` | `grep -n "if (!cellHasAnyAuthoredPort"` | Line 296 | ✓ PASS |
| PORT-05 pre-removal reanchor | `grep -n "reanchorLinksFromPort(cell, portId)"` in `removeAuthoredPortWithSurvival` | Line 336 — before `cell.removePort` | ✓ PASS |
| `maybeAutoExpand` stub replaced | Check lines 263–287 | Real Q7 implementation present; `showToast('Shape resized to fit ports.', 'info')` at line 286 | ✓ PASS |
| All 7 shape classes use `portsForRect()` | grep shape class defaults | Console/Device/SpeakerArray/CommBeltPack/Generic/Processor/Amp all present | ✓ PASS |
| ABSOLUTE_FLOORS has 7 entries | sed lines 425–433 | All 7 shape type strings correct | ✓ PASS |
| `CornerResize` uses Control not paid Resize | `grep "joint.elementTools.Resize"` count in code (not comments) | 0 code uses; 1 comment only | ✓ PASS |
| `change:size` in autosave listener | Line 2364 | `change:size` appended to graph listener string | ✓ PASS |
| Live redistribute on resize | Lines 2372–2382 | `graph.on('change:size')` calls redistributeEdgePorts for all 4 edges | ✓ PASS |
| Admin-DOM style writes use setProperty | `grep "\.style\.[a-zA-Z]* ="` (non-comment) | 0 matches — all use `setProperty(.., 'important')` | ✓ PASS |
| XSS: innerHTML count unchanged | `grep -c "innerHTML"` | 5 (all are `= ''` clear operations) | ✓ PASS |
| port row labels use `.value` not innerHTML | Line 2120: `input.value = port.showstack.label || ''` | `.value` property write confirmed | ✓ PASS |
| All documented commits exist | `git log --oneline grep` | All 12 commits verified: c0abf2d through d9c0409 | ✓ PASS |
| Live browser smoke-test (circuit-label autocomplete) | Open editor, select connector, type in circuit-label | SKIPPED — requires live server | ? SKIP |
| Live browser UAT (port authoring + resize) | PORT-01..06 + SHP-RESIZE-01..03 assertions | SKIPPED — requires live browser | ? SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PORT-01 | 11-01, 11-02, 11-04 | Add labeled port to any shape; 4-edge model (T/B/L/R) | ✓ SATISFIED | REQUIREMENTS.md amended; `addAuthoredPort` wires to all 4 edges; port labels visible via Section 14 + real `portLabelPositionForEdge` |
| PORT-02 | 11-02, 11-03 | Auto-distribute to equal spacing on add/remove | ✓ SATISFIED | `redistributeEdgePorts` called in `addAuthoredPort` and `removeAuthoredPortWithSurvival`; instant snap via `startBatch('phase11-redistribute')` |
| PORT-03 | 11-01, 11-03 | Dropdown-or-freetext label via Phase 10 combobox | ✓ SATISFIED | `attachAutocompleteToInput` factory reused per port row; onSelect + blur-commit path; freeform typing overrides dropdown selection |
| PORT-04 | 11-02, 11-03 | Per-port snap target; v2.2 back-compat for 0 authored ports | ✓ SATISFIED | D-13 whole-shape switch in `addAuthoredPort`; generic ports preserved for 0-authored shapes; `validateConnection` unchanged (both ends must be port magnets) |
| PORT-05 | 11-02, 11-03 | Remove port via inspector; connectors survive pinned to edge midpoint | ✓ SATISFIED | `reanchorLinksFromPort` called BEFORE `cell.removePort` in `removeAuthoredPortWithSurvival`; trash icon uses `removeWithSurvival`; PORT-05 structural contract enforced |
| PORT-06 | 11-06 | Auto-expand shape when port-add pushes past current size | ✓ SATISFIED | `maybeAutoExpand` fully implemented; grows toward right/bottom; Math.ceil snap; `showToast('Shape resized to fit ports.', 'info')`; no shrink on removal |
| SHP-RESIZE-01 | 11-05 | Resize any of 7 smart shapes via corner handle | ✓ SATISFIED | `CornerResize` extends `joint.elementTools.Control` (MPL-2.0); all 4 corners (tl/tr/bl/br); all 7 shape classes work via JointJS `Element.resize()` |
| SHP-RESIZE-02 | 11-05 | Resize constrained to per-type min-size | ✓ SATISFIED | `computeMinSize` with `ABSOLUTE_FLOORS` (7 types) + live port-count × spacing + label widths; applied in `CornerResize.setPosition` via `Math.max(newDim, minSize.dim)` |
| SHP-RESIZE-03 | 11-05 | Resize in autosave + undo + 409 path | ✓ SATISFIED | `change:size` added to autosave listener (line 2364); undo records `change:size` via generic `graph.on('change', ...)` at line 1288; 409 path unchanged |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `signal_flow.css` | 858–861 | `#sfd-paper .joint-tools .joint-tool { cursor: nwse-resize }` — applies to ALL JointJS tools, including link vertex/anchor/remove handles | ⚠️ Warning (WR-01) | Wrong cursor on connector tool handles; cosmetic only |
| `signal_flow_editor.js` | 2096–2103 + 2516 | `refreshPortAuthorBlock` only clears `<li>` rows, not stale `<ul.sfd-ac-listbox>` elements appended to `portAuthorBlock`; each `attachAutocompleteToInput` call appends a new listbox | ⚠️ Warning (WR-02) | DOM growth + duplicate `id` attributes after repeated port add/rename/remove cycles; autocomplete still functional (live closure ref is always current) |
| `signal_flow_editor.js` | 561–568 | `CornerResize.setPosition` snap path: `newX`/`newY` independently rounded, not re-derived from pinned opposite corner; invariant `newX + newW === p.x + s.width` breaks after rounding | ⚠️ Warning (WR-03) | Opposite corner drifts up to ~19px when snap-on dragging from TL/TR/BL corner; cosmetic during snap-mode resize |
| `signal_flow_editor.js` | 322 | Comment "Plan 11-06 fills the body" inside `addAuthoredPort` — stale; `maybeAutoExpand` is fully implemented at line 263 | ℹ️ Info | Stale comment only; no functional impact |

No BLOCKER anti-patterns found. The three warnings match exactly the findings documented in 11-REVIEW.md. None prevent goal achievement; all are cosmetic or edge-case issues noted for v2.3 polish.

### Human Verification Required

#### 1. Circuit-Label Autocomplete Regression (Phase 10 BC)

**Test:** Open the Signal Flow Diagrammer, select an existing connector, type 1 character in the circuit-label input.
**Expected:** Dropdown appears within ~200ms with project-scoped suggestions in `label — source` format; click a row → label populates; type freeform → input accepts arbitrary text; reload → label persisted.
**Why human:** Requires live server + project data to test behavioral parity post-refactor.

#### 2. Inspector Port-Authoring Block

**Test:** Select any of the 7 smart shape types → inspect the right-hand inspector panel.
**Expected:** "Ports" section visible with 4 labeled sub-sections (Top / Bottom / Left / Right), each with a "+ Add port" button. Clicking "+ Add port" on "Top" creates a port row with ordinal, label input, and trash icon, and adds a port dot at the top edge midpoint.
**Why human:** Inspector DOM rendering requires live browser; CSS Section 16 styling only verifiable in browser.

#### 3. PORT-03 Autocomplete on Port Rows

**Test:** Click "+ Add port" on any edge, type 1 character in the label input.
**Expected:** Phase 10 autocomplete combobox appears (same behavior as circuit-label); selecting a row sets the port label; blurring with freeform text also commits; port label appears on the canvas shape.
**Why human:** Requires live server endpoint; each port row has its own combobox attachment.

#### 4. PORT-05 Connector Survival

**Test:** Add a port to a shape, draw a connector from another shape to that port, then click the trash icon on the port row.
**Expected:** Connector's endpoint moves to the shape's edge midpoint — connector is NOT deleted. Remaining ports on that edge redistribute instantly.
**Why human:** Requires live JointJS canvas + drag interaction.

#### 5. SHP-RESIZE-01: Handle Presence on All 7 Shape Types

**Test:** Select Console, Device, SpeakerArray, CommBeltPack, Generic, Processor, and Amp shapes one at a time.
**Expected:** 4 teal corner handles appear at TL/TR/BL/BR on each. Handles disappear on deselect. Selecting a connector shows NO handles. Selecting two shapes simultaneously shows NO handles.
**Why human:** SVG tool rendering and cursor requires live browser.

#### 6. SHP-RESIZE-02/03: Min-Size Clamping, Autosave, Undo

**Test A:** Drag the BR handle of a port-less Console inward.
**Expected:** Shape stops at 180×60 (ABSOLUTE_FLOOR). Cannot drag below this floor.

**Test B:** Drag-end any shape → check DevTools Network tab.
**Expected:** autosave POST fires within 1500ms.

**Test C:** Ctrl+Z after a resize.
**Expected:** Resize reverses in a single undo step. Page reload shows persisted (if not undone) or original (if undone) dimensions.
**Why human:** Drag interaction + DevTools observation required.

#### 7. PORT-06 Auto-Expansion + Toast

**Test:** On a fresh Console shape (180×60), click "+ Add port" on the Top edge 9 times (at 24px min-spacing, 9 ports need ~9×24+24 = 240px, wider than 180px default).
**Expected:** Shape width grows to accommodate; toast "Shape resized to fit ports." appears briefly. Removing a port does NOT shrink the shape.
**Why human:** Requires live canvas to observe shape grow and toast.

---

## Gaps Summary

**Status changed `human_needed` → `gaps_found`** after browser UAT (2026-05-24). All 9 phase requirements pass structural automated checks, but 5 functional gaps surfaced when the user exercised the feature in the browser. Details in `11-HUMAN-UAT.md`. Summary:

| # | UAT Test | Result | Gap |
|---|----------|--------|-----|
| 1 | Circuit-label autocomplete (Phase 10 BC) | failed | GAP-11.1 + GAP-11.3 |
| 2 | Inspector port-authoring block | **passed** | — |
| 3 | PORT-03 autocomplete on port rows | partial | GAP-11.1 + GAP-11.4 |
| 4 | PORT-05 connector survival | failed | GAP-11.2 (BLOCKER) |
| 5 | SHP-RESIZE-01 handles on 7 shapes | **passed** | — |
| 6 | SHP-RESIZE-02/03 min-size + autosave + undo | skipped | re-test post-fix |
| 7 | PORT-06 auto-expansion + toast | failed | GAP-11.5 |

**Gaps (full detail in 11-HUMAN-UAT.md):**

- **GAP-11.1** (high) — Authored port autocomplete reads from the wrong source (Device shape suggests Amp Channels). Endpoint is not shape-scoped.
- **GAP-11.2** (critical, BLOCKER) — Cannot draw connector from any authored port; click drags the shape instead. Likely cause: `opacity: 0` hover-reveal selector doesn't match authored ports added via `cell.addPort` (only matches `portsForRect()`-added ports).
- **GAP-11.3** (high) — Stale autocomplete listboxes accumulate in the inspector (WR-02 from code review now manifests visibly).
- **GAP-11.4** (medium) — Port-row label input text too faint to see on the dark inspector background.
- **GAP-11.5** (high) — `computeMinSize` undercounts: port-count × spacing without Σ(label widths) per edge → labels overlap inside shape body.

Three code-review warnings (WR-01 cursor CSS scope, WR-02 stale autocomplete listboxes, WR-03 snap corner drift) — WR-02 has now escalated to GAP-11.3 (functional bug), WR-01 and WR-03 remain advisory.

The REQUIREMENTS.md traceability table still shows PORT-01..06 and SHP-RESIZE-01..03 as "TBD / Pending" — flip to Done only after gap-closure phase passes UAT.

Next action: `/gsd-plan-phase 11 --gaps` to create gap-closure plans, then `/gsd-execute-phase 11 --gaps-only`.

---

_Verified: 2026-05-24 (structural) / 2026-05-24 (UAT: gaps found)_
_Verifier: Claude (gsd-verifier); UAT: Charlie Lawson (browser)_
