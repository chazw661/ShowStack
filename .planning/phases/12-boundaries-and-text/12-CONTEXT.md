# Phase 12: Boundary Lines + Text Annotations — Context

**Gathered:** 2026-05-25
**Status:** Ready for planning
**Milestone:** v2.3 (Signal Flow Diagrammer — Export & Enhancements)
**Driver:** Issue #14 (engineer-requested freeform canvas-annotation primitives)

<domain>
## Phase Boundary

Phase 12 ships two decorative canvas primitives on top of the v2.2/v2.3 Signal Flow Diagrammer:

- **DRAW-01..04** — Engineer-drawn freeform boundary polylines used to mark zones (FOH, Amp World, Stage Left/Right, etc.). Toolbar-armed mode → click each vertex → double-click or Esc to finish. Editable color (8-color palette) + line-style (solid / dashed / dotted / double) via inspector. Vertices draggable for reshape; same Delete/Backspace path as shapes/connectors.
- **TXT-01..03** — Freeform on-canvas text labels ("FOH", "Stage Left", "Spare Rack", etc.). Toolbar-armed mode → click to place → inline edit immediately. Selectable, draggable, deletable. Font-size in 3 sizes (12 / 16 / 24 px) + text color (8-color palette + white).

Both primitives are **decoupled from shapes and connectors** — they do not carry signal type, do not snap to ports, and are not valid connection endpoints. Both ship inside the existing `canvas_state` JSONField blob; no migration on `SignalFlowDiagram`. Both ride the Phase 9 autosave + If-Match 409 + keepalive path with no special-casing.

**Out of phase scope:**
- Curved boundary lines (DRAW-CURVE-01, milestone-deferred to v2.4+)
- Filled translucent zone shapes (DRAW-FILL-01, milestone-deferred to v2.4+)
- Rich text formatting (bold/italic — TXT body-only, milestone-deferred)
- Boundaries as semantic zones (engineer cannot "put a shape inside a zone" with cascading style or behavior)
- Add/delete vertex post-creation (drag-only in Phase 12; right-click-delete deferred to v2.4+)
- Multi-line text (Shift+Enter for newlines — single-line in Phase 12; deferred to v2.4+ if engineers report needing callout paragraphs)
- Engineer-controlled z-order overrides (bring-forward / send-back — defer to v2.4+; fixed defaults in v2.3)

</domain>

<decisions>
## Implementation Decisions

### A. Drawing UX

- **D-01:** **Sticky draw mode.** Clicking the toolbar "Draw boundary" button enters draw-boundary mode and keeps it active until: (a) Esc, (b) re-click of the boundary button, or (c) click of another mode button (Place text). Engineer can draw multiple boundaries back-to-back without re-arming. Same sticky rule applies to "Place text" mode. Matches Figma/Lucidchart line-tool feel; DRAW-01 explicitly allows this exit set.
- **D-02:** **Click-each-vertex pen-tool input.** Engineer clicks once per vertex; an in-progress "live to cursor" segment draws while moving. Double-click OR Esc commits the polyline. Minimum 2 vertices required; a single-vertex click followed by Esc is treated as "no polyline drawn" (no degenerate point cell). Rejected freeform click-drag because it generates dozens of vertices per gesture, making DRAW-04 vertex-edit unusable without a decimation pass.
- **D-03:** **Vertices snap to 20px grid when the existing snap toggle is on**, freeform pixels when off. Matches Phase 8 D-13 — one snap rule across the whole canvas (shape-drag, shape-resize per Phase 11 D-05, and now boundary vertices).
- **D-04:** **New "creation tools" toolbar group inserted between `#sfd-redo` and the right-aligned spacer.** A single `.sfd-btn-group` contains both buttons: `#sfd-tool-boundary` ("Draw boundary") and `#sfd-tool-text` ("Place text"), with the existing `.sfd-toolbar-divider` on each side. Matches the existing toolbar grammar (zoom | snap | undo/redo | **[new tools]** | spacer | export). This group is the canonical home for future creation-tool primitives (v2.4+).
- **D-05:** **Esc mid-polyline commits at current vertex.** If the engineer has placed ≥2 vertices before pressing Esc, the polyline commits with the vertices placed so far (the in-progress "live to cursor" segment is dropped). If only 1 vertex is placed, Esc cancels with no polyline created (per D-02 minimum). Lets the engineer abandon the trailing segment without losing the actual zone outline.
- **D-06:** **Vertex-edit handles are always visible on a selected boundary.** Each vertex shows a small circular handle in the same teal accent (`#0d9488`) as Phase 11 D-05 corner-resize handles. Drag any handle to reshape that vertex. Matches the existing selection-visual language; engineer learns one "handles = drag points" pattern across resize and reshape.
- **D-07:** **Visual mode feedback.** While draw-boundary or place-text mode is active: (a) the toolbar button gets the existing `.is-active` treatment (same as `#sfd-snap-toggle`, `aria-pressed="true"`), and (b) `#sfd-paper` cursor changes to `crosshair` (via JS `setProperty('cursor', 'crosshair', 'important')` per CLAUDE.md admin-CSS override rule). Two strong signals so engineer never wonders "am I in mode."

### B. Color + Line-Style Picker

- **D-09:** **8-color palette, print-safe (Tailwind 600 family).** Final hex values:
  - Black `#000000`
  - Grey `#666666`
  - Red `#dc2626`
  - Orange `#ea580c`
  - Yellow `#eab308`
  - Green `#16a34a`
  - Blue `#2563eb`
  - Purple `#9333ea`

  All saturated enough to read against the **white** PNG-export background (Phase 10 D-09). Grey is medium so it doesn't disappear on white or confuse with black. Same palette serves DRAW boundaries and TXT text (TXT adds white per D-19).
- **D-10:** **Inspector-only pickers + session-sticky defaults.** All color/style editing happens in the right-side inspector when a boundary (or text) is selected — matches Phase 9 inspector mode-switch pattern (connector-mode / node-mode; Phase 12 adds boundary-mode / text-mode). The **next** boundary or text element the engineer creates inherits the last-used color + style as session-sticky defaults (engineer drawing 6 red zones doesn't re-pick red each time). **No toolbar color/style controls** — keeps the toolbar lean; one editing surface.
- **D-11:** **"Double" line style = two parallel solid strokes, 3px apart.** Classic architectural-drawing convention; visually distinct from solid (where double = thicker single stroke would just look like a heavier solid line). Implementation: SVG `<g>` with two `<polyline>` siblings, each rendered with the same color + solid stroke, offset perpendicular by 3px. Both strokes reshape together when the engineer drags a vertex. Researcher confirms whether `joint.shapes.standard.Polyline` supports this out-of-the-box or whether a custom shape class is needed.
- **D-12:** **Line-style picker = 4 segmented buttons with SVG stroke previews** (solid / dashed / dotted / double). Each button is ~30px wide and shows a miniature SVG `<line>` rendered in the active color with that style's stroke pattern. Matches the Phase 8/9 `.sfd-segmented` inspector pattern used for connector signal-type. One click to switch.

### C. Z-Order / Layering

- **D-13:** **Boundary lines default behind shapes + connectors.** Boundary cells get a low JointJS `z` index (sorted before all shape cells). Matches the "FOH zone is a background wall, the console rack sits inside it" mental model — engineers draw zones first to plan layout, then drop equipment shapes inside. Connectors stay above boundaries so signal paths remain visible across the diagram.
- **D-14:** **Text annotations default on top of everything.** Text cells get the highest JointJS `z` index — above shapes, connectors, and boundaries. Labels like "FOH", "Stage Left", or a per-shape callout must stay readable regardless of what's underneath.
- **D-15:** **No per-element layer-override controls in v2.3.** Inspector does NOT include bring-forward / send-back / front / back arrows. Default z-order rules (D-13 / D-14) are fixed; engineer cannot manually layer one boundary in front of another. Deferred to v2.4+ if engineers report defaults aren't enough. Keeps inspector simple.

### D. Text Annotation Lifecycle

- **D-16:** **Click → inline edit immediately.** When the engineer is in place-text mode and clicks the canvas, the text element is placed AND the engineer drops into edit mode immediately with a blinking caret. They start typing without an intermediate "select and double-click" step. **Enter** OR **click-outside** commits the text and exits edit mode (sticky place-text mode from D-01 stays armed unless engineer pressed Esc to exit mode). **Esc during edit** cancels and deletes the just-placed empty element. Matches Figma / Lucidchart / Miro text-tool flow.
- **D-17:** **Double-click on a text element re-enters edit mode.** Selecting (single-click) shows font-size + color controls in the inspector but does NOT enter edit mode (so engineer can drag, change style, or delete without triggering character editing). Double-click drops the engineer back into the same inline-edit flow as D-16: caret blinks, type replaces, Enter / click-out / Esc commit-or-cancel.
- **D-18:** **Single-line text only. Empty text auto-deletes.** **Enter** commits and exits edit mode — no newline insertion (live-audio labels are all single-line: "FOH", "Stage Left", "Amp World"). If the engineer commits with empty body (typed nothing, or cleared all chars before commit), the text element auto-deletes — no orphan empty placeholders on the canvas. Aligns with the "no rich text" milestone constraint.
- **D-19:** **Font sizes + background:**
  - **Small** = 12px (matches Phase 11 D-08 port-label font size)
  - **Medium** = 16px (default for new text — matches toolbar text)
  - **Large** = 24px (callout-grade — "FOH", "STAGE LEFT" zone titles)
  - **Background:** transparent. No white pill / no shadow / no outline. Engineer color-picks the text color (DRAW palette + **white** so light text reads on dark boundaries) to handle legibility against whatever's behind. Cleanest visual; matches the "no chrome" Phase 8/9 canvas language; avoids the "white-on-white pill disappears in PNG export" footgun.
  - **Text color palette:** the same 8 colors as D-09 **plus white** (`#ffffff`). White is text-only (boundaries don't need white because they're never against a dark surface — canvas background is white per Phase 10 D-09).

### E. Carried Decisions (already locked from prior phases)

- **Canvas state schema** — DRAW + TXT cells live as new entries inside the existing `SignalFlowDiagram.canvas_state` JSONField blob (per the v2.2 user decision 2026-05-22). No model migration on `SignalFlowDiagram` itself. Researcher picks the cell-type encoding (e.g., `joint.shapes.showstack.BoundaryLine` + `.TextLabel` custom classes vs. extending `joint.shapes.standard.Polyline` + `.TextBlock`).
- **Autosave path** — Phase 9 1500 ms debounced autosave + `If-Match` optimistic-lock 409 conflict handling + keepalive flush on unload. **All Phase 12 edits (boundary draw, vertex drag, style change, text place, text edit, delete) ride this same path.** No new autosave codepath.
- **Snap grid** — Phase 8 D-13 20 px grid. **Boundary vertices snap to the same grid** when the toolbar snap toggle is on (per D-03 above). Text placement also snaps (cell origin lands on the grid).
- **Inspector mode-switch pattern** — Phase 9 introduced `setInspectorMode('connector' | 'node' | ...)` for selection-driven exclusive inspector panels. **Phase 12 adds `'boundary'` and `'text'` modes** — engineer never sees two mode panels at once.
- **Toolbar group scaffold** — Phase 10 D-13 established the "create a button group even for a single button, future siblings will land here" convention. Phase 12's new tools group (D-04) holds two buttons today; future text/shape primitive tools (v2.4+) land here.
- **CSS section append rule** — `signal_flow.css` is organized as numbered sections; new functionality appends a new section rather than editing existing ones (Sections 1–16 exist after Phase 11). **Phase 12 appends Section 17 (boundary lines — DRAW) + Section 18 (text annotations — TXT)**, plus updates the header section list comment at the top of the file.
- **System fonts only** — Phase 8/9/11 constraint (no cross-origin font taint that breaks `html-to-image` PNG export). Applies to TXT labels as well.
- **Delete / Backspace keyboard path** — DRAW-04 + TXT-03 explicitly inherit the existing shape/connector deletion path. Selection rules + Phase 9 conflict-locked guards apply unchanged.
- **PNG export already covers both** — Phase 10 EXP-01 promised "all canvas elements: shapes, ports, connectors, boundary lines (DRAW), and text annotations (TXT)" — because `html-to-image` snapshots whatever SVG is on `#sfd-paper`, DRAW + TXT cells flow into the export with **no special handling** in Phase 12.
- **IDOR allowlist** — Phase 9/10 added an explicit allowlist (`Console`, `Device`, `CommBeltPack`, `Amp`, `SystemProcessor`, `P1Processor`, `GalaxyProcessor`) at the autosave POST validation path (`planner/views.py` ~line 7702). **Boundary + text cells have no `type/id` equipment link** — they're pure canvas-state JSON with no GFK. Plan should add a branch to skip equipment-allowlist validation for DRAW + TXT cell types, OR confirm the existing code already passes them through (cells without a ContentType pointer should bypass the allowlist; researcher to verify and document).
- **Connector `validateMagnet` / `validateConnection`** (`signal_flow_editor.js:291-308`) — **Boundary lines must NOT be valid connection endpoints.** Connectors should not be drag-able to a boundary, and a boundary should not be drag-able as a connector. Boundary cells declare no magnets (or `magnet: false` equivalent). Plan should add a no-op exit branch or rely on the existing "both ends MUST be magnets" rule keeping boundaries out automatically.

### F. Claude's Discretion

- **JointJS cell-class names** — e.g., `joint.shapes.showstack.BoundaryLine` and `joint.shapes.showstack.TextLabel` vs. extending `joint.shapes.standard.Polyline` / `.TextBlock`. Researcher picks based on what gives clean `canvas_state` serialization and vertex/style/font-size editing.
- **Color-swatch layout** in the inspector — 4×2 grid vs. 8×1 row vs. 9×1 row (for TXT to include white). Visual choice; planner picks.
- **Selected-swatch visual** — ring, outline, checkmark — pick what matches the existing inspector selection styling (probably teal `#0d9488` ring to match the rest of the editor's selection language).
- **Stroke width default** for boundary lines — likely 2 px (matches connector default from Phase 8). Researcher confirms; not engineer-configurable in v2.3.
- **Session-sticky default storage** — closure-scoped IIFE state vs. `sessionStorage`. Both work; closure is simpler and resets per page-load (acceptable).
- **Initial defaults** (before any sticky value exists) — suggest **boundary: black solid 2px**; **text: medium (16px) black**. Planner picks.
- **Vertex-handle hit-target size** — visible handle can be ~6 px circle but the SVG transparent hit area should be ~12 px for easy click targeting. Researcher / planner to specify.
- **Edge-case: clicking outside the canvas** while a boundary/text mode is sticky-active — treat as no-op (just like a click on a non-paper region today). Don't exit mode; engineer would lose the in-progress draw.
- **Toast on first boundary draw or first text place** — not required. The visible result (boundary appears, text caret blinks) is enough feedback. No "Boundary added" toast.
- **Text element bounding box / drag-target** — the text glyph itself OR a 4 px padding around it should be the drag target. Researcher decides based on JointJS-native vs custom-element behavior.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope
- `.planning/REQUIREMENTS.md` §"Boundary Drawing — DRAW" (lines 42–49) — DRAW-01..04 acceptance criteria
- `.planning/REQUIREMENTS.md` §"Text Annotations — TXT" (lines 51–57) — TXT-01..03 acceptance criteria
- `.planning/REQUIREMENTS.md` §"Future Requirements (deferred to v2.4+)" (lines 75–88) — DRAW-CURVE-01, DRAW-FILL-01, rich-text exclusions
- `.planning/REQUIREMENTS.md` §"Out of Scope (explicit exclusions for v2.3)" (lines 90–99)
- `.planning/REQUIREMENTS.md` §"Constraints (held from v2.2 unless noted)" (lines 101–108) — JSONField, system fonts, additive migrations only, project scoping
- `.planning/ROADMAP.md` "Phase 12" entry (line 59) — defines goal, dependency on Phase 11, full requirement IDs closed

### v2.3 patterns already shipped (reuse, don't reinvent)
- `.planning/phases/10-autocomplete-png-export-new-shapes/10-CONTEXT.md` — D-13 toolbar-group scaffold pattern, D-08/D-09 PNG export (boundaries + text included automatically)
- `.planning/phases/10-autocomplete-png-export-new-shapes/10-02-SUMMARY.md` — exact toolbar HTML insertion site (right-side button group before `#sfd-canvas-container`), CSS Section 13 export-group reference
- `.planning/phases/11-ports-and-resize/11-CONTEXT.md` — D-05 four-corner resize handle pattern + teal accent `#0d9488` for handles (Phase 12 vertex-edit handles match this), D-13 "this is yours now" mental model parallel for boundary/text editor-authored data
- `.planning/phases/11-ports-and-resize/11-05-SUMMARY.md` — `CornerResize` JointJS `elementTools.Control` subclass implementation (Phase 12 vertex-edit handles likely follow the same elementTools pattern, just per-vertex instead of per-corner)
- `.planning/phases/11-ports-and-resize/11-PATTERNS.md` — Phase 11 file/pattern map; Phase 12's planner runs the same mapping for boundary + text cells

### v2.2 patterns to extend
- `.planning/phases/08-canvas-smart-shapes-connectors/08-CONTEXT.md` — D-13 (20px snap grid — boundary vertices snap to this), D-14 (4000×3000 finite canvas — boundary + text positions clamped to this), magnet semantics (boundaries declare no magnets), `.sfd-segmented` inspector control pattern (Phase 12 line-style picker uses this)
- `.planning/phases/09-autosave-orphan-rendering/09-CONTEXT.md` — autosave 1500 ms debounce, If-Match 409 conflict, keepalive flush, **inspector mode-switch pattern** (`setInspectorMode('connector' | 'node' | …)` — Phase 12 adds `'boundary'` and `'text'` modes), Delete/Backspace deletion path
- `.planning/milestones/v2.2-ROADMAP.md` — full v2.2 context (Phases 7–9 shipped)

### Code-level entry points
- `planner/static/planner/js/signal_flow_editor.js:80-122` — `standardPortGroups()` + `portsForRect()`. Phase 12 does NOT modify these (boundary + text have no ports).
- `planner/static/planner/js/signal_flow_editor.js:128-360` — 7 shape class definitions (Phase 8 + 10 + 11). **Phase 12 adds two more cell classes** (or extends `joint.shapes.standard.Polyline` + `.TextBlock`) in the `joint.shapes.showstack` namespace: `BoundaryLine` and `TextLabel`. Researcher picks custom-class vs standard-extend.
- `planner/static/planner/js/signal_flow_editor.js:291-308` — `defaultLink`, `validateMagnet`, `validateConnection`. **Phase 12 must confirm boundaries are NOT valid connector endpoints** (no magnets exposed; existing "both ends must be magnets" rule should auto-reject).
- `planner/static/planner/js/signal_flow_editor.js:1300-1900` — inspector mode logic (`setInspectorMode(...)`, `connectorFieldRows`, node-mode block). **Phase 12 adds two new mode branches** (boundary-mode with color swatches + line-style segmented; text-mode with font-size segmented + color swatches including white).
- `planner/static/planner/js/signal_flow_editor.js` — autosave IIFE — new boundary/text mutations call the existing `scheduleAutosave()` debounce; no new endpoint or payload shape (canvas_state is opaque JSON to the server).
- `planner/templates/planner/signal_flow/editor.html:40-66` — `#sfd-toolbar` markup. **Phase 12 inserts a new `.sfd-btn-group` between `#sfd-redo` (line ~58) and the right-spacer at line ~60**, containing `#sfd-tool-boundary` + `#sfd-tool-text` buttons with surrounding `.sfd-toolbar-divider`s.
- `planner/static/planner/css/signal_flow.css` Sections 1–16 already exist. **Phase 12 appends Section 17 (boundary line styles — DRAW, including the 4 stroke patterns + double-line `<g>` pair) + Section 18 (text annotation styles — TXT, including font-size classes + color swatches including white-text option)** per the established append-at-end convention. Update the section-list comment at top of file.
- `planner/views.py` — `signal_flow_autosave` POST validation (~line 7702 area; refactored for the WR-04 allowlist fix in Phase 10). **Boundary + text cells have no `type/id` equipment link.** Researcher confirms current allowlist branch passes them through unchanged OR adds a "no GFK = skip allowlist" branch.
- `planner/views.py` — `_enrich_nodes` (Phase 9). Boundary + text cells are engineer-authored decorative data with no equipment link → `_enrich_nodes` does NOT touch them.

### Vendored libraries (already loaded in Phase 7 vendor bundle)
- `joint.min.js` 4.2.4 — has `joint.shapes.standard.Polyline` (for boundaries) and `joint.shapes.standard.TextBlock` (for text). Researcher confirms whether Phase 12 extends these or creates `joint.shapes.showstack.BoundaryLine` / `.TextLabel` custom classes.
- `html-to-image.min.js` 1.11.11 — already snapshots the full `#sfd-paper` SVG. Boundary + text cells flow into the PNG export with no Phase 12 code changes (per Phase 10 EXP-01).

### Architectural constraint
- `CLAUDE.md` §"Overriding Django admin CSS from JavaScript" — **The toolbar + inspector live inside admin templates. DOM-style writes from JS MUST use `el.style.setProperty(prop, value, 'important')`.** This applies to: `#sfd-paper { cursor: crosshair }` mode-on (D-07), inspector color-swatch active-state ring, font-size segmented active-state. JointJS-managed SVG inside `#sfd-paper` is in its own namespace and does not need `!important`.
- `CLAUDE.md` §"Custom admin site" — Phase 12 does not register new models (no migrations); no admin-site updates needed.

### Test patterns
- `planner/tests/test_signal_flow_phase9.py` — Phase 9 test file; Phase 11 added `test_signal_flow_phase11.py` (or extended phase9 file — researcher confirms). **Phase 12 tests live in a new `test_signal_flow_phase12.py` if the testable surface is non-trivial** (autosave round-trip on boundary + text cells; IDOR-skip for cells without equipment link). UI behavior (mode toggles, vertex drag, text inline edit) is browser-UAT, not backend-test.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`.sfd-segmented` inspector pattern** (Phase 8/9) — the connector signal-type picker is exactly the right precedent for the Phase 12 line-style picker (4 buttons with stroke previews per D-12) and the text font-size picker (3 buttons S/M/L per D-19).
- **`setInspectorMode()` mode switcher** (Phase 9) — already handles selection-driven exclusive inspector panels (connector-mode, node-mode). Phase 12 adds two new modes by extending the switch with `'boundary'` and `'text'` branches; the panel-show/hide plumbing is already in place.
- **`.is-selected` selection visual + teal accent `#0d9488`** (Phase 8 + Phase 11) — vertex-edit handles (D-06) use the exact same teal as Phase 11 D-05 corner-resize handles. Same hit-area + handle-circle approach (visible 6px, hit 12px) — one selection language across the whole editor.
- **`scheduleAutosave()` debounce + `If-Match` 409 conflict + keepalive flush** (Phase 9) — every Phase 12 mutation hooks here. Zero new autosave codepath.
- **`html-to-image` PNG export** (Phase 10) — captures DRAW + TXT cells automatically because they're SVG on `#sfd-paper`. EXP-01 already promised this; no Phase 12 code to confirm beyond a visual UAT screenshot.
- **`.sfd-btn-group` + `.sfd-toolbar-divider` toolbar pattern** (Phase 8/9/10) — Phase 12 adds one new group with two buttons per D-04.
- **Phase 9 `_enrich_nodes()`** — explicitly skips engineer-authored data with no equipment link. Boundary + text cells are this case; no enrichment.

### Established Patterns

- **CSS append-section convention** — Phase 12 appends Section 17 (DRAW) + Section 18 (TXT). Update the section-list comment at file top.
- **Cell-class registration** — each shape class registers on `joint.shapes.showstack.*`; sidebar tile or toolbar button references it. Phase 12 registers `BoundaryLine` + `TextLabel` (or standard-extend equivalents) on the same namespace.
- **Mode-active toolbar button** — `aria-pressed="true"` + `.is-active` class (precedent: `#sfd-snap-toggle`). Phase 12 boundary + text mode buttons follow this exact pattern.
- **Cursor override via JS setProperty** — `setProperty('cursor', 'crosshair', 'important')` per CLAUDE.md admin-CSS override rule (D-07). Restore to default on mode exit.
- **Session-sticky defaults via closure-scoped state** — autosave-IIFE already holds session state (`conflicted`, `graph`, etc.). Add `lastBoundaryColor`, `lastBoundaryStyle`, `lastTextSize`, `lastTextColor` to the same closure (or sessionStorage — see Claude's Discretion).

### Integration Points

- **`signal_flow_autosave` POST IDOR validation** (`planner/views.py` ~line 7702) — boundary + text cells have no `type/id` equipment link. The existing allowlist branch (extended in Phase 10 to include the v2.3 shapes) should already bypass cells without a ContentType pointer, but **researcher MUST verify**. If the current branch rejects them, add a `cell_type in ('BoundaryLine', 'TextLabel') → skip equipment-allowlist` early-return. **Forgetting this is the most likely silent bug in Phase 12** (parallel to the WR-04 allowlist bug in Phase 10).
- **`signal_flow_state` GET response + `_enrich_nodes()`** (Phase 9) — boundary + text cells have no equipment link, so `_enrich_nodes` does NOT touch them. No code change needed there beyond confirming the iteration skips non-equipment cells gracefully.
- **`validateMagnet` / `validateConnection`** (`signal_flow_editor.js:291-308`) — boundary cells declare no magnets; the existing "both ends must be magnets" rule should auto-reject connector-to-boundary drags. **Researcher confirms this auto-rejects; no code change needed if so.**
- **Toolbar HTML insertion** (`editor.html:~58–60`) — new `.sfd-btn-group` between `#sfd-redo` and the right-spacer. Two buttons; two-divider wrap.
- **Inspector HTML** — no new template changes; mode-panel content is built by JS via `setInspectorMode('boundary' | 'text')`.
- **Keyboard handler** — existing Delete/Backspace handler (Phase 8/9) deletes selected cells via `cell.remove()`. Boundary + text cells inherit this for free as long as they're standard JointJS elements/links.
- **Esc keyboard handler** — Phase 12 adds a new Esc branch: (a) if in draw-boundary mode mid-polyline with ≥2 vertices, commit and exit; (b) if in draw mode with 0–1 vertices, cancel mode; (c) if in text edit mode, cancel edit (delete empty element per D-16, D-18). Existing Esc-clears-selection behavior preserved when no Phase 12 mode is active.

</code_context>

<specifics>
## Specific Ideas

- **Print-safe palette is non-negotiable.** PNG export ends up in Slack and on printed riders (Phase 10 D-09 white background). The Tailwind 600 family reads against white at thumbnail size in chat; pastels would not. Same reason TXT white text exists — engineers need a light glyph color for placing text directly on a saturated boundary stroke.
- **Boundary-behind / text-on-top mental model.** The live-audio diagram workflow is: zone first (FOH, Amp World, Stage Left/Right) → equipment shapes inside → connectors → text callouts on top. Z-order defaults match that exact authoring order.
- **Vertex handle visual reuses Phase 11's teal accent intentionally.** Same color, same hit-target size, same `.is-selected` activation. Engineers learn one "selection-handle = drag point" pattern across all of resize, port-handle, and now vertex-edit.
- **Inspector-mode-only color picking eliminates a class of bugs** — there's no "toolbar shows red but I drew a blue line because state was out of sync" failure mode. The active boundary's inspector IS the source of truth for that boundary's color. Next-drawn inherits last-edited.
- **Pen-tool over freeform drag is a real opinion.** Engineers will draw 3–6-vertex zones. Pen-tool gives them exactly that vertex count, immediately usable for DRAW-04 reshape. Freeform would generate 30+ vertices per gesture, requiring a decimation pass and degrading reshape UX. Worth holding the line.
- **The new "creation tools" toolbar group is a forward-looking anchor.** v2.4+ will likely add more primitives (rectangles, callouts, leader lines, arrows). Establishing the group in Phase 12 with two buttons (and a real divider on each side) means those future additions land without rearranging the toolbar.
- **"No special handling for PNG export" is a feature.** EXP-01 promised it; Phase 12 inherits it for free. The only verification is a screenshot UAT: draw a boundary, place text, click Export PNG, confirm both appear.

</specifics>

<deferred>
## Deferred Ideas

Captured during analysis but explicitly out of Phase 12 scope:

- **Curved boundary lines (Bezier)** — `DRAW-CURVE-01`, already milestone-deferred to v2.4+ (REQUIREMENTS line 78).
- **Filled translucent zone shapes** (vs lines) — `DRAW-FILL-01`, already milestone-deferred to v2.4+ (REQUIREMENTS line 79).
- **Rich text formatting in TXT** (bold / italic / underline) — milestone-deferred (REQUIREMENTS line 96); plain text with font-size + color only.
- **Multi-line text via Shift+Enter** — Phase 12 ships single-line per D-18; revisit v2.4+ if engineers report needing callout paragraphs. Adds wrap measurement and a "remove on empty" branch.
- **Add / delete vertex on a placed boundary** (right-click vertex → delete, double-click edge → insert) — Phase 12 ships drag-existing-vertices only per DRAW-04; v2.4+ if engineers ask.
- **Engineer-controlled z-order overrides** (bring forward / send back / front / back) — Phase 12 ships fixed defaults per D-13/D-14; v2.4+ if defaults aren't enough.
- **Toolbar color/style defaults** (vs inspector-only per D-10) — rejected; revisit only if engineers complain about session-stickiness.
- **White-pill text background** (vs transparent per D-19) — rejected; white-on-white pill disappears in PNG export.
- **"Clean export" mode** (hide DRAW + TXT in PNG) — not requested; PNG includes everything per Phase 10 D-08.
- **Boundary stroke width as engineer-configurable** — not in v2.3; default fixed (likely 2px). Revisit if engineers want emphasis-via-thickness.
- **Per-port routing intelligence on boundaries** — milestone-excluded; boundaries are decorative, not semantic (REQUIREMENTS line 94).
- **Right-click context menu on canvas** — out of editor scope (no right-click anywhere today). Stays out in v2.3.

</deferred>

---

*Phase: 12-boundaries-and-text*
*Context gathered: 2026-05-25*
