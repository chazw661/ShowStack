---
phase: 11-ports-and-resize
verified: 2026-05-25T00:00:00Z
updated: 2026-05-25T00:00:00Z
status: passed
score: 14/14 structural + 5/5 Pass 2 browser UAT + 2 inline gaps closed and approved by Charlie in Pass 3
overrides_applied: 0
pass3_final:
  approved_by: Charlie
  approved_at: 2026-05-25
  approval_quote: "all approved."
  inline_closures:
    - "GAP-11.6 (high) — commit 34a4176 — addAuthoredPort magnet:true on all 4 edges (was directionForEdge-gated). Browser cache + pre-existing-port gotcha confirmed by Charlie after hard reload + fresh ports."
    - "GAP-11.7 (medium) — commit 48aaff7 — Section 16 port-block label colors (#555→#aaa section title, #333→#eee edge name, #888→#aaa ordinal). Diagnosed from Charlie's screenshot — original framing was wrong; the dim text was the surrounding labels, not the input."
pass2_uat_results:
  passed:
    - "Re-UAT-1 (GAP-11.1) — per-shape autocomplete confirmed by Charlie 2026-05-25"
    - "Re-UAT-5 (GAP-11.5 + PORT-06) — Σ(label widths) auto-expansion working"
    - "Re-UAT-6 (SHP-RESIZE-02/03) — resize + clamp + autosave + undo working"
  failed:
    - "GAP-11.6 (high) — RESOLVED in 34a4176 + Pass 3"
    - "GAP-11.7 (medium) — RESOLVED in 48aaff7 + Pass 3"
re_verification:
  previous_status: gaps_found
  previous_score: "9/9 structural + 5 functional gaps reported in browser UAT"
  gaps_closed:
    - "GAP-11.1 (high) — Authored port autocomplete read wrong source (Device shape suggested Amp Channels)"
    - "GAP-11.2 (critical BLOCKER) — Could not draw connector from authored port; click pan-dragged shape"
    - "GAP-11.3 (high) — Stale autocomplete listboxes accumulated in inspector across refreshes"
    - "GAP-11.4 (medium) — Port-row label input text invisible on dark inspector background"
    - "GAP-11.5 (high) — computeMinSize undercounted; port labels overlapped inside shape body"
    - "CR-01 (critical, code-review) — Double-? URL in fetchAcResults silently broke GAP-11.1 fix"
  gaps_remaining: []
  regressions: []
  closure_commits:
    - "133cc97 — feat(11-07): backend SHAPE_CLASS_SOURCES allowlist + shape_class filter (GAP-11.1 server)"
    - "fabffdf — fix(11-07): JS opacity:1 + listbox purge + URL builder + Σ(label widths) (GAP-11.1/2/3/5)"
    - "9844745 — fix(11-08): Section 16 .sfd-port-label-input dark-navy + light text + ::placeholder (GAP-11.4)"
    - "7ccc537 — fix(11): CR-01 fetchAcResults separator check (Phase 10 BC + Phase 11 both URL-clean)"
human_verification:
  - test: "Re-UAT-1: GAP-11.1 closed — port-row autocomplete per shape"
    expected: "Open editor, drop a Device shape, click '+ Add port' on Top edge, type 1 char in the label input. Dropdown shows ONLY Device Input / Device Output rows (no Amp Channel). Repeat on a Console → only Console Input / Console Aux Out. Repeat on an Amp → only Amp Channel. Repeat on a Processor → P1/Galaxy Input/Output. Repeat on a SpeakerArray, CommBeltPack, or Generic → falls back to all 9 sources (intentional — these have no labeled-channel catalog). On a connector circuit-label input → still gets all 9 sources (Phase 10 BC preserved)."
    why_human: "Requires live server + project data + visual dropdown inspection; per-shape scoping cannot be confirmed without typing in a browser. DevTools Network tab should show `?shape_class=showstack.Device&q=<char>` for port rows and bare `?q=<char>` for circuit-label."
  - test: "Re-UAT-2: GAP-11.2 closed — engineer-authored ports clickable"
    expected: "Drop a Device shape, add a port on the Top edge via inspector. Port dot is visible immediately (opacity 1, not hidden). Click+drag from the port — a connector line forms and follows the cursor. Drop on another shape's port → connector lands and persists. Previously the click pan-dragged the shape instead. Backward compat: shapes with zero authored ports still get the Phase 8 hover-reveal generic ports (opacity 0 until hovered)."
    why_human: "Requires live JointJS canvas + drag interaction; magnet click affordance only confirmable in browser."
  - test: "Re-UAT-3+4: GAP-11.3 + GAP-11.4 closed — clean inspector + readable text"
    expected: "Add 3 ports to a shape, type a label in each, trash 2 of them. Open DevTools and run `document.querySelectorAll('.sfd-field--port-author .sfd-ac-listbox').length` — count must equal the visible-row count (≤ visible inputs), never accumulate to 10+. Typed text in any port-label input is clearly readable: light text (#eee) on dark navy (#1a1a2a), border #444, focus ring teal #0d9488 — visually indistinguishable from the connector circuit-label input on the same inspector."
    why_human: "Requires DevTools to count DOM nodes; CSS rendering on the live editor required for color contrast confirmation."
  - test: "Re-UAT-5: GAP-11.5 + PORT-06 closed — Σ(label widths) auto-expansion"
    expected: "On a fresh Console (180×60), click '+ Add port' on the Top edge 5 times, then label each with realistic strings ('Channel 1', 'Channel 2', ..., 'Channel 5'). Shape MUST auto-expand wide enough that no two port labels overlap inside the body. Toast 'Shape resized to fit ports.' fires on each grow. Removing a port does NOT shrink the shape (auto-expand never auto-shrinks, per RESEARCH §Q5)."
    why_human: "Requires live canvas to observe shape grow + toast appearance + label-overlap absence."
  - test: "Re-UAT-6 (carry-over): SHP-RESIZE-02/03 — min-size clamp + autosave + undo"
    expected: "Test A: drag the BR handle of a port-less Console inward → shape stops at 180×60 (ABSOLUTE_FLOOR). Add 5 labeled ports → floor grows wider per the new Σ(label widths) formula and resize-in clamps at the wider floor. Test B: drag-end any shape → DevTools Network shows autosave POST within 1500ms. Test C: Ctrl+Z after a resize → reverses in single undo step. Page reload shows persisted (if not undone) or original (if undone) dimensions."
    why_human: "Drag interaction + DevTools observation + reload check required. Originally 'skipped' in first UAT pending GAP-11.2 unblock; now exercisable."
human_verification_addressed_in_uat: # 3 of 7 original items confirmed PASSED in first UAT — preserved here for traceability
  - test: "Inspector port-authoring block visible on all 7 shape types"
    result: "PASSED — UAT test 2 (2026-05-24)"
  - test: "SHP-RESIZE-01: 4 teal corner handles on single selection of all 7 shape types"
    result: "PASSED — UAT test 5 (2026-05-24)"
  - test: "PORT-03 port-row combobox attaches to each input"
    result: "PASSED (structural) — UAT test 3 (2026-05-24); behavior fix shipped via GAP-11.1/11.4 closures"
---

# Phase 11: Per-Shape Labeled Ports + Resizable Shapes — Verification Report

**Phase Goal:** Engineer-authored ports on all 4 edges with auto-equal-spacing, dropdown-or-custom labels via refactored `attachAutocompleteToInput` factory, corner-handle resize via `joint.elementTools.Control` subclass (MPL-2.0 only), min-size clamping, connector snap targeting per-port with whole-shape v2.2 back-compat. Closes PORT-01..06, SHP-RESIZE-01..03.

**Verified:** 2026-05-24T21:30:00Z
**Status:** `human_needed` — all 14 structural must-haves PASS; 4 browser-UAT re-tests pending Charlie
**Re-verification:** **Yes** — second pass after gap-closure cycle (commits 133cc97 + fabffdf + 9844745 + 7ccc537)

## Re-Verification Summary (Pass 2)

| Aspect | Pass 1 | Pass 2 |
|--------|--------|--------|
| Structural must-haves | 9/9 PASS | 14/14 PASS (5 new gap-closure truths added) |
| Functional gaps reported | 5 (UAT) | 0 (all closed in code) |
| Critical code-review findings | n/a | 1 (CR-01) — resolved in commit 7ccc537 |
| Status | `gaps_found` | `human_needed` (pending re-UAT) |
| Browser items requiring Charlie | 7 (original) | 5 (re-test the closure of the failed/skipped items) |

**What changed since Pass 1:** Plan 11-07 shipped 2 commits closing GAP-11.1/2/3/5 in `views.py` + `signal_flow_editor.js`. Plan 11-08 shipped 1 commit closing GAP-11.4 in `signal_flow.css`. The code-review caught one critical bug (CR-01 — double-`?` URL silently re-broke GAP-11.1) which was fixed in commit 7ccc537. All four fixes are present in the working tree as of 2026-05-24T21:30Z.

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                                                                                      | Status     | Evidence |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------- |
| 1   | REQUIREMENTS.md PORT-01 reads "4 edges: Top, Bottom, Left, Right"                                                                                                          | ✓ VERIFIED | line 15: "anchor to one of four edges per shape: **Top**, **Bottom**, **Left**, **Right**"; commit c0abf2d |
| 2   | `attachAutocompleteToInput(inputEl, url, onSelect)` factory exists with unique listbox IDs                                                                                 | ✓ VERIFIED | Function at line 2534; single declaration (`grep -c "function attachAutocompleteToInput"` = 1); listbox IDs use `sfd-label-suggestions-<id>`; `.sfd-ac-listbox` class confirmed |
| 3   | Phase 10 circuit-label combobox behavior preserved (no shape_class param sent)                                                                                             | ✓ VERIFIED | Line 2695: `attachAutocompleteToInput(circuitLabelInput, labelAutocompleteUrl, null)` — bare URL preserved; backend allowlist falls through when shape_class is absent |
| 4   | All 13 port-authoring helpers exist in module scope                                                                                                                        | ✓ VERIFIED | `cellHasAnyAuthoredPort` (157), `reanchorLinksFromPort` (211), `maybeAutoExpand` (263), `addAuthoredPort` (296+), `removeAuthoredPortWithSurvival`, `renameAuthoredPort`, `portLabelPositionForEdge`, `portLabelMarkupForEdge`, plus the 5 lookup/redistribute/midpoint/convert helpers all present; `window.__sfd.ports` at line 2477 |
| 5   | D-13 back-compat: shapes with 0 authored ports retain 4 generic ports; first authored port triggers whole-shape conversion                                                 | ✓ VERIFIED | `addAuthoredPort` guard `if (!cellHasAnyAuthoredPort(cell)) convertCellFromGenericToAuthored(cell)` at line 296; all 7 shapes use `portsForRect()` in defaults; Phase 8 generic ports still `opacity: 0` (2 grep hits, both in `standardPortGroups`) |
| 6   | PORT-05 connector survival: `reanchorLinksFromPort` called BEFORE `removePort`                                                                                             | ✓ VERIFIED | `removeAuthoredPortWithSurvival` at line ~336: saves edge → reanchor → removePort → redistribute |
| 7   | Inspector port-authoring UI: `buildPortAuthorBlock` / `refreshPortAuthorBlock` wired into `setInspectorMode('node')`                                                       | ✓ VERIFIED | `refreshPortAuthorBlock` at line 2119; `buildPortAuthorBlock` wired in `setInspectorMode('node')` branch; port block hidden in connector branch |
| 8   | Port label autocomplete via `attachAutocompleteToInput` with `renameAuthoredPort` onSelect                                                                                 | ✓ VERIFIED | Line 2174–2180: `attachAutocompleteToInput(input, portAutocompleteUrl, function(label){ window.__sfd.ports.rename(...) })` with ES5-safe IIFE closure per port row |
| 9   | Port labels render visibly on canvas: `portLabelPositionForEdge` and `portLabelMarkupForEdge` real implementations; CSS Section 14                                          | ✓ VERIFIED | Both functions return real position/markup; CSS Section 14 unchanged from Pass 1 |
| 10  | `CornerResize` tool extends `joint.elementTools.Control` (not paid `Resize`); 4 corner handles on any single element selection                                              | ✓ VERIFIED | Line 536: `var CornerResize = joint.elementTools.Control.extend({...})`; `attachResizeTools` at line 598; wired in `onSelectionChanged` at line 1882 |
| 11  | `computeMinSize` uses `ABSOLUTE_FLOORS` for 7 shape types + Σ(label widths) formula for Top/Bottom                                                                          | ✓ VERIFIED (UPGRADED) | `ABSOLUTE_FLOORS` at line 429; `computeMinSize` at line 456; **GAP-11.5 fix:** `sumLabelWidths` at line 475 + `edgeWidthRequired` at line 498; `W_topbottom = Math.max(edgeWidthRequired(topPorts), edgeWidthRequired(bottomPorts))` at line 504; old `count * MIN_PORT_SPACING` formula fully removed (0 grep matches) |
| 12  | `change:size` fires autosave (SHP-RESIZE-03) AND live port redistribute (D-06)                                                                                              | ✓ VERIFIED | Line 2402: `graph.on('add remove change:source change:target change:size', scheduleAutosave)`; line 2410: separate `graph.on('change:size', ...)` calls redistribute for all 4 edges |
| 13  | `maybeAutoExpand` fully implemented (PORT-06): grows toward right/bottom, Math.ceil snap, toast only when grown                                                              | ✓ VERIFIED | `maybeAutoExpand` at line 263; reads `cell.size()` + `computeMinSize(cell)` (now with GAP-11.5 Σ-formula); grow-only; toast 'Shape resized to fit ports.' on grow; called from `addAuthoredPort` line 326 and `renameAuthoredPort` line 359 |
| 14  | **NEW (Pass 2):** Backend `signal_flow_label_autocomplete` accepts optional `shape_class` query param; allowlist-only filter; missing/unknown → all 9 sources; Phase 10 BC preserved | ✓ VERIFIED | `views.py:7938` `SHAPE_CLASS_SOURCES` allowlist (4 entries: Console, Device, Amp, Processor); line 7975 reads `shape_class`; line 7976 filter check; line 7977–7978 narrows SOURCES; IDOR guard `filter_kw[scope_kwarg] = current_project` runs INSIDE the per-source loop AFTER filtering (line 7982+ unchanged); commit 133cc97 |
| 15  | **NEW (Pass 2):** GAP-11.2 — authored portBody renders at opacity:1 (clickable); Phase 8 generic ports still opacity:0 (hover-reveal preserved)                              | ✓ VERIFIED | `signal_flow_editor.js:308`: `opacity: 1` with inline GAP-11.2 comment; `grep -c "opacity: 0"` returns 2 (both `standardPortGroups` in/out — `portsForRect` path unchanged); commit fabffdf |
| 16  | **NEW (Pass 2):** GAP-11.3 — `refreshPortAuthorBlock` purges stale `.sfd-ac-listbox` children before rebuild                                                                  | ✓ VERIFIED | Line 2127–2129: `Array.from(portAuthorBlock.querySelectorAll('.sfd-ac-listbox')).forEach(remove)` at top of refreshPortAuthorBlock, BEFORE the per-edge PORT_EDGES.forEach loop; commit fabffdf |
| 17  | **NEW (Pass 2):** GAP-11.1 (client) — per-shape `portAutocompleteUrl` builder appends `?shape_class=<cell.type>`                                                              | ✓ VERIFIED | Line 2133–2135: URL builder; line 2176 swaps `portAutocompleteUrl` in per-row attach call; bare `labelAutocompleteUrl` preserved at line 2695 (Phase 10 BC); commit fabffdf |
| 18  | **NEW (Pass 2 — CR-01 fix):** `fetchAcResults` uses a separator check so `&q=` is appended when the base URL already carries `?shape_class=`                                  | ✓ VERIFIED | Line 2612: `var sep = (url.indexOf('?') === -1) ? '?' : '&';` line 2613: `var fetchUrl = url + sep + 'q=' + encodeURIComponent(q);` — Phase 10 path uses `?`, Phase 11 port path uses `&`; commit 7ccc537 |

**Score:** 18/18 structural truths verified (was 9/9 in Pass 1; +5 new GAP-closure truths + 4 expanded coverage items; effectively 14/14 net new structural assertions added by gap closure)

### Required Artifacts

| Artifact                                            | Expected                                                | Status     | Details |
| --------------------------------------------------- | ------------------------------------------------------- | ---------- | ------- |
| `.planning/REQUIREMENTS.md`                         | PORT-01 amended to 4 edges                              | ✓ VERIFIED | Line 15 verified |
| `planner/views.py`                                  | `SHAPE_CLASS_SOURCES` allowlist + filter branch         | ✓ VERIFIED | line 7938 (declaration), 7975 (param read), 7976–7978 (filter); AST parses; 8011 lines total (+22 over Pass 1) |
| `planner/static/planner/js/signal_flow_editor.js`   | All Phase 11 helpers + CornerResize + GAP-closure fixes | ✓ VERIFIED | `node --check` exit 0; 2751 lines (+43 over Pass 1's 2708); 18 grep verifications all pass |
| `planner/static/planner/css/signal_flow.css`        | Section 16 GAP-11.4 fix + ::placeholder rule            | ✓ VERIFIED | 875 lines (+14 over Pass 1's 861); GAP-11.4 fix comment + dark-navy bg + light text + ::placeholder rule all present; Section 4 byte-for-byte unchanged |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| Port-row label input | `signal_flow_label_autocomplete?shape_class=<type>` | `buildPortAutocompleteUrl(cell)` at line 2133 | ✓ WIRED | URL composes `?shape_class=showstack.Device` for Device cells |
| `fetchAcResults` | Backend with both `?shape_class` + `&q` | Line 2612 separator check | ✓ WIRED | CR-01 closed: Phase 11 path produces `?shape_class=X&q=Y`, Phase 10 path produces `?q=Y` |
| Authored portBody | JointJS magnet (visible + clickable) | `opacity: 1` literal at line 308 | ✓ WIRED | Click reaches `validateMagnet`; pan-drag bug closed |
| `refreshPortAuthorBlock` entry | Stale `.sfd-ac-listbox` purge | Line 2127 querySelectorAll + remove loop | ✓ WIRED | DOM is clean before per-row rebuild |
| `computeMinSize` Top/Bottom | Σ(measureLabelWidth) + (N-1) × spacing + 2 × padding | `sumLabelWidths` (line 475) + `edgeWidthRequired` (line 498) | ✓ WIRED | Auto-expansion grows shape wide enough for labels |
| Section 16 `.sfd-port-label-input` | Section 4 inspector-input visual contract | Same `background-color`, `color`, `border`, `font-family` values | ✓ WIRED | No new hex codes; placeholder #aaa from .sfd-field-help |
| `attachAutocompleteToInput` BC call site | `circuitLabelInput` (Phase 10) | Line 2695: `attachAutocompleteToInput(circuitLabelInput, labelAutocompleteUrl, null)` | ✓ WIRED | Phase 10 BC byte-for-byte preserved; backend allowlist falls through |
| `change:size` | autosave + redistribute | Lines 2402 + 2410 | ✓ WIRED | Unchanged from Pass 1 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `refreshPortAuthorBlock` | `port.showstack.label` | `cell.getPorts()` → JointJS graph state | Yes — live JointJS cell model | ✓ FLOWING |
| Per-row autocomplete dropdown | `data.results[]` | `fetchAcResults(q)` → backend filtered by `shape_class` + `q` | Yes — backend SOURCES narrowed by allowlist, then per-source DB query (project-scoped) | ✓ FLOWING |
| `portLabelMarkupForEdge` SVG `<text>` | Port label text | `addAuthoredPort` writes `attrs.label.text` AND `showstack.label`; `renameAuthoredPort` dual-write | Yes — engineer-authored string round-trips through canvas_state JSON | ✓ FLOWING |
| `computeMinSize` Top/Bottom | `sumLabelWidths(ports)` | Per-port `measureLabelWidth(label, 11)` Canvas-2D measurement | Yes — real label-width measurement; auto-expansion grows shape correctly | ✓ FLOWING |
| `maybeAutoExpand` | `newW` / `newH` | `cell.size()` + `computeMinSize(cell)` (now with Σ-formula) | Yes — auto-expand grows to fit Σ(label widths) | ✓ FLOWING |
| canvas_state persistence | Entire graph | `graph.toJSON()` via `scheduleAutosave` (on `change:size` and all port mutations) | Yes — JointJS-native ports.items[N] with showstack namespace round-trip | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| JS syntax validity | `node --check signal_flow_editor.js` | Exit 0 | ✓ PASS |
| Python syntax validity | `python3 -c "import ast; ast.parse(open('planner/views.py').read())"` | Exit 0 | ✓ PASS |
| `SHAPE_CLASS_SOURCES` present in views.py | `grep -c "SHAPE_CLASS_SOURCES" planner/views.py` | 3 | ✓ PASS (≥2) |
| `shape_class = ` read in views.py | `grep -c "shape_class = " planner/views.py` | 1 | ✓ PASS |
| GAP-11.2 comment marker | `grep -c "GAP-11.2: authored ports always visible"` | 1 | ✓ PASS |
| Phase 8 generic ports preserved at opacity:0 | `grep -c "opacity: 0" signal_flow_editor.js` | 2 | ✓ PASS (standardPortGroups in + out) |
| Authored port at opacity:1 | `grep -c "opacity: 1" signal_flow_editor.js` | 1 | ✓ PASS |
| `sumLabelWidths` helper present | `grep -c "function sumLabelWidths"` | 1 | ✓ PASS |
| `edgeWidthRequired` helper present | `grep -c "function edgeWidthRequired"` | 1 | ✓ PASS |
| Old min-size formula fully removed | `grep -E "Math.max\(N_T, N_B\) \* MIN_PORT_SPACING"` | 0 matches | ✓ PASS |
| `.sfd-ac-listbox` purge present | `grep -c "querySelectorAll('.sfd-ac-listbox')"` | 1 | ✓ PASS |
| Port autocomplete URL with shape_class | `grep -c "shape_class="` | 2 (URL builder + CR-01 comment) | ✓ PASS |
| `portAutocompleteUrl` declaration + use | `grep -c "portAutocompleteUrl"` | 2 | ✓ PASS |
| Phase 10 circuit-label BC call preserved | `grep -c "attachAutocompleteToInput(circuitLabelInput, labelAutocompleteUrl, null)"` | 1 | ✓ PASS |
| **CR-01 fix:** `fetchAcResults` separator check | `grep -n "sep = (url.indexOf('?')" signal_flow_editor.js` | 1 match at line 2612 | ✓ PASS |
| GAP-11.4 fix comment in CSS | `grep -c "GAP-11.4 fix" signal_flow.css` | 1 | ✓ PASS |
| New ::placeholder rule | `grep -c ".sfd-port-label-input::placeholder" signal_flow.css` | 1 | ✓ PASS |
| Section 16 dark-navy bg | `grep -c "background-color: #1a1a2a !important" signal_flow.css` | 3 (Section 4 + Section 16 new + 1 elsewhere) | ✓ PASS (≥2) |
| Old white bg fully removed | `grep -nE "\.sfd-port-label-input \{[^}]*background: #fff"` | 0 matches | ✓ PASS |
| Old light-grey border fully removed | `grep -nE "\.sfd-port-label-input \{[^}]*border: 1px solid #d0d0d0"` | 0 matches | ✓ PASS |
| Closure commits exist | `git log --oneline 133cc97^..7cdeefe` | 8 commits present in correct order | ✓ PASS |
| TODOs / FIXMEs in modified files | `grep -nE "TODO\|FIXME\|XXX\|HACK" signal_flow_editor.js` | 0 matches | ✓ PASS |
| Live browser smoke-test (per-shape autocomplete + clickable ports + Σ-expansion + readable text) | Charlie's re-UAT | SKIPPED — requires live server + canvas | ? SKIP (queued for Charlie) |
| Prior-phase regression tests (Phase 9 + Phase 10) | `python manage.py test planner.tests.test_signal_flow_phase9 test_signal_flow_phase10` | All 32 tests PASS (per user-supplied confirmation) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| **PORT-01** | 11-01, 11-02, 11-04 | Add labeled port to any shape; 4-edge model | ✓ SATISFIED | REQUIREMENTS.md amended; `addAuthoredPort` wires to all 4 edges; port labels visible via Section 14 + real `portLabelPositionForEdge` |
| **PORT-02** | 11-02, 11-03 | Auto-distribute to equal spacing on add/remove | ✓ SATISFIED | `redistributeEdgePorts` called in `addAuthoredPort` and `removeAuthoredPortWithSurvival`; instant snap via undo batch |
| **PORT-03** | 11-01, 11-03, 11-07, 11-08 | Dropdown-or-freetext label via Phase 10 combobox | ✓ SATISFIED | `attachAutocompleteToInput` factory reused per port row; **GAP-11.1 closed:** per-shape autocomplete scoping via `shape_class` param + backend SHAPE_CLASS_SOURCES allowlist; **GAP-11.4 closed:** input text now readable; CR-01 URL bug fixed |
| **PORT-04** | 11-02, 11-03, 11-07 | Per-port snap target; v2.2 back-compat for 0 authored ports | ✓ SATISFIED | D-13 whole-shape switch in `addAuthoredPort`; **GAP-11.2 closed:** authored portBody opacity:1 → JointJS magnet clickable → connector draw works; Phase 8 generic ports preserved at opacity:0 (back-compat) |
| **PORT-05** | 11-02, 11-03, 11-07 | Remove port via inspector; connectors survive pinned to edge midpoint | ✓ SATISFIED | `reanchorLinksFromPort` called BEFORE `cell.removePort` in `removeAuthoredPortWithSurvival`; **GAP-11.2 unblocks UAT:** connector draw now works, so trash-survival is exercisable |
| **PORT-06** | 11-06, 11-07 | Auto-expand shape when port-add pushes past current size | ✓ SATISFIED | `maybeAutoExpand` fully implemented; **GAP-11.5 closed:** `computeMinSize` Top/Bottom now uses Σ(label widths) — auto-expansion correctly grows wider to fit horizontal labels; toast fires on grow |
| **SHP-RESIZE-01** | 11-05 | Resize any of 7 smart shapes via corner handle | ✓ SATISFIED | `CornerResize` extends `joint.elementTools.Control` (MPL-2.0); all 4 corners; UAT Pass 1 confirmed handle presence on all 7 shapes |
| **SHP-RESIZE-02** | 11-05, 11-07 | Resize constrained to per-type min-size | ✓ SATISFIED | `computeMinSize` with `ABSOLUTE_FLOORS` (7 types) + **GAP-11.5 Σ-formula** for label widths; applied in `CornerResize.setPosition` via `Math.max(newDim, minSize.dim)` |
| **SHP-RESIZE-03** | 11-05 | Resize in autosave + undo + 409 path | ✓ SATISFIED | `change:size` added to autosave listener (line 2402); undo records `change:size` via generic graph listener; 409 path unchanged |

**All 9 phase requirements SATISFIED structurally.** UAT re-test (5 items above) pending Charlie's browser session to flip REQUIREMENTS.md traceability rows from "TBD / Pending" → "Done".

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `signal_flow.css` | ~858-861 | Section 15 `#sfd-paper .joint-tools .joint-tool { cursor: nwse-resize }` applies to ALL JointJS tools, including link vertex/anchor/remove handles | ⚠️ Warning (WR-01 — carried from Pass 1) | Wrong cursor on connector tool handles; cosmetic only |
| `signal_flow_editor.js` | 561–568 | `CornerResize.setPosition` snap path: `newX`/`newY` independently rounded, not re-derived from pinned opposite corner | ⚠️ Warning (WR-03 — carried from Pass 1) | Opposite corner drifts up to ~19px when snap-on dragging from TL/TR/BL corner; cosmetic during snap-mode resize |
| `signal_flow_editor.js` | 322 | Comment "Plan 11-06 fills the body" inside `addAuthoredPort` — stale; `maybeAutoExpand` is fully implemented at line 263 | ℹ️ Info | Stale comment only; no functional impact |
| `signal_flow.css` | 858–861 | (same as WR-01) | n/a | n/a |

**No BLOCKER anti-patterns found.** WR-01 and WR-03 are pre-existing advisories from Pass 1's code review; both are cosmetic and tracked for v2.3 polish. WR-02 (stale autocomplete listboxes) has been **closed** by GAP-11.3 fix in plan 11-07. CR-01 has been **closed** by commit 7ccc537. No new anti-patterns introduced by gap-closure work.

### Human Verification Required

Five UAT re-tests confirm gap closure in the live browser. Three of the original 7 UAT items (inspector port-authoring block, SHP-RESIZE-01 handles on all 7 shapes, PORT-03 combobox attaches) already PASSED in Pass 1 and remain confirmed.

#### Re-UAT 1: GAP-11.1 closed — per-shape autocomplete scoping

**Test:** Open editor with any project; drop one of each smart shape type. For each shape, click "+ Add port" on Top and type 1 character in the label input. Then test the connector circuit-label autocomplete.

**Expected:**
- Device → only `Device Input` / `Device Output` rows
- Console → only `Console Input` / `Console Aux Out` rows
- Amp → only `Amp Channel` rows
- Processor → only `P1 Input/Output` + `Galaxy Input/Output` rows
- SpeakerArray / CommBeltPack / Generic → all 9 sources (intentional fall-through)
- Connector circuit-label → all 9 sources (Phase 10 BC preserved)
- DevTools Network: port rows request `?shape_class=showstack.Device&q=<char>` (with the `&`, not double `?`)

**Why human:** Requires live server + project data + visual dropdown inspection. The CR-01 URL-builder bug silently re-broke GAP-11.1 in commits before 7ccc537 — must verify the fix landed cleanly in the running app.

#### Re-UAT 2: GAP-11.2 closed — authored ports clickable (BLOCKER closed)

**Test:** Drop a Device shape, add a port on Top edge via inspector. Click+drag from the port — connector line should follow the cursor. Drop on another shape's port.

**Expected:**
- Port dot visible immediately (opacity:1)
- Click+drag starts a connector (NOT a shape pan-drag)
- Connector lands on the target port and persists across reload
- Shapes with zero authored ports STILL hover-reveal Phase 8 generic ports (back-compat)

**Why human:** Magnet click affordance only confirmable via live JointJS canvas interaction.

#### Re-UAT 3+4: GAP-11.3 + GAP-11.4 closed — clean inspector + readable text

**Test:**
- Add 3 ports, type a label in each, trash 2.
- DevTools console: `document.querySelectorAll('.sfd-field--port-author .sfd-ac-listbox').length` ≤ visible-row count.
- Inspect a port-label input visually: light text on dark navy, border #444, focus ring teal #0d9488 — visually identical to connector circuit-label input.
- DevTools: `getComputedStyle(document.querySelector('.sfd-port-label-input')).color` returns `rgb(238, 238, 238)`.

**Why human:** Requires DevTools count + CSS rendering check in a browser.

#### Re-UAT 5: GAP-11.5 + PORT-06 closed — Σ(label widths) auto-expansion

**Test:** Fresh Console (180×60). Add 5 ports to Top edge, label each "Channel 1", "Channel 2", …, "Channel 5".

**Expected:**
- Shape auto-expands wide enough that no two labels overlap inside the body
- Toast "Shape resized to fit ports." fires on each grow
- Removing a port does NOT shrink the shape

**Why human:** Visual canvas check + toast observation.

#### Re-UAT 6: SHP-RESIZE-02 / SHP-RESIZE-03 — min-size clamp + autosave + undo (was SKIPPED in Pass 1)

**Test A:** Drag BR handle of port-less Console inward → stops at 180×60 (ABSOLUTE_FLOOR).
**Test A':** Add 5 labeled ports → floor grows wider per new Σ-formula; resize-in clamps at the wider floor.
**Test B:** Drag-end any shape → autosave POST within 1500ms (DevTools Network).
**Test C:** Ctrl+Z after a resize → reverses in single undo step. Reload page → dimensions persisted (or original if undone).

**Why human:** Drag interaction + DevTools observation + reload check.

---

## History

### Pass 1 (2026-05-24 — initial verification → UAT → gaps_found)

- **Initial structural verification:** Status `human_needed`, score 9/9 must-haves verified, 7 browser UAT items queued. Three code-review warnings (WR-01 cursor CSS scope, WR-02 stale autocomplete listboxes, WR-03 snap corner drift) — all advisory.
- **Human UAT session (2026-05-24):** Charlie exercised the 7 UAT items in the browser. 2 passed, 4 failed, 1 skipped (blocked by GAP-11.2).
- **Status changed:** `human_needed` → `gaps_found`. Five functional gaps reported in `11-HUMAN-UAT.md`:
  - GAP-11.1 (high) — autocomplete read wrong source (Device → Amp Channels)
  - GAP-11.2 (critical, BLOCKER) — could not draw connector from authored port
  - GAP-11.3 (high) — stale autocomplete listboxes accumulated (WR-02 manifested)
  - GAP-11.4 (medium) — port-label input text too faint on dark inspector
  - GAP-11.5 (high) — computeMinSize undercounted; labels overlapped
- **Outcome:** Routed to `/gsd-plan-phase 11 --gaps`.

### Pass 1.5 (2026-05-24 — gap-closure planning + execution)

- Two parallel gap-closure plans created (11-07 JS+backend, 11-08 CSS-only — non-overlapping files).
- **11-07 (commits 133cc97 + fabffdf, ~12min):** Closed GAP-11.1 (backend SHAPE_CLASS_SOURCES allowlist + frontend portAutocompleteUrl builder), GAP-11.2 (opacity:1 on authored ports), GAP-11.3 (listbox purge in refreshPortAuthorBlock), GAP-11.5 (sumLabelWidths + edgeWidthRequired formula).
- **11-08 (commit 9844745, ~4min):** Closed GAP-11.4 (Section 16 .sfd-port-label-input dark-navy bg + light text + ::placeholder rule; copied verbatim from Section 4 visual contract).
- **Code review (commit adce13b, status `issues_found`):** Caught CR-01 — the new `portAutocompleteUrl` builder pre-appended `?shape_class=` to the URL, but the existing `fetchAcResults` unconditionally appended `?q=`, producing a malformed double-`?` URL that silently re-broke GAP-11.1 (shape-scoping disabled because the literal `shape_class` value now contained `?q=Vox`).
- **CR-01 fix (commit 7ccc537):** Replaced unconditional `?q=` in `fetchAcResults` with a separator check (`sep = (url.indexOf('?') === -1) ? '?' : '&'`). Phase 10 path unchanged (no pre-existing `?`); Phase 11 port path now correctly produces `?shape_class=X&q=Y`.

### Pass 2 (2026-05-24T21:30Z — this re-verification)

- All 5 gaps closed in code; all structural checks pass; 18/18 truths verified including 5 new GAP-closure truths and the CR-01 fix.
- Three pre-existing advisories (WR-01, WR-03, IN-01/IN-02 from CR) remain noted but non-blocking.
- Status: `human_needed` — flipped back from `gaps_found` because the 5 UAT-blocking issues are structurally resolved. 5 re-UAT items queued for Charlie to confirm in browser; once those pass, REQUIREMENTS.md traceability table flips PORT-01..06 and SHP-RESIZE-01..03 to "Done".

---

## Gaps Summary

**Zero open gaps.** All 5 functional gaps from Pass 1's UAT (`GAP-11.1` through `GAP-11.5`) are structurally closed in code, plus the code-review's critical CR-01 finding. The REQUIREMENTS.md traceability rows for PORT-01..06 and SHP-RESIZE-01..03 remain at "TBD / Pending" pending Charlie's UAT re-test confirmation.

**Three items remain advisory / non-blocking:**
- WR-01 (cursor CSS scope) — Section 15 `.joint-tool` resize cursor leaks onto connector vertex/anchor handles. Cosmetic; v2.3+ polish.
- WR-03 (snap corner drift) — `CornerResize.setPosition` rounds `newX`/`newY` independently; opposite corner drifts ~19px when snap-on resize. Cosmetic; v2.3+ polish.
- IN-01 / IN-02 (code-review info advisories) — `SHAPE_CLASS_SOURCES` dict re-created per request (style only); `cell.get('type') || ''` masks impossible falsy case (defensive style only). Not blocking.

Next action (after re-UAT passes): `/gsd-update-state` to flip REQUIREMENTS.md traceability + close out Phase 11. Phase 12 (Boundary Lines + Text Annotations) is unblocked structurally.

---

_Verified: 2026-05-24T21:30:00Z (Pass 2 re-verification — gaps closed structurally; 5 UAT items queued)_
_Verifier: Claude (gsd-verifier); Pass 1 + Pass 2; UAT: Charlie Lawson (browser)_
