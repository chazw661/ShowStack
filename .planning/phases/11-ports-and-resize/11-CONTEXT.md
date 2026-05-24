# Phase 11: Per-Shape Labeled Ports + Resizable Shapes — Context

**Gathered:** 2026-05-24
**Status:** Ready for planning
**Milestone:** v2.3 (Signal Flow Diagrammer — Export & Enhancements)
**Driver:** Issue #14 (engineer-requested signal-flow power-user features)

<domain>
## Phase Boundary

Phase 11 ships two related capabilities to the Signal Flow Diagrammer:

- **PORT-01..06** — Engineer-authored labeled ports on each smart shape. Replaces v2.2's fixed 4-generic-port model. Ports live on the 4 edges (Top / Bottom / Left / Right), label themselves from either a project-scoped signal-name dropdown (reusing Phase 10's autocomplete) or free text, auto-distribute to equal spacing on add/remove, and become per-port snap targets for connectors.
- **SHP-RESIZE-01..03** — Corner-handle resize across ALL 7 smart shape types (the v2.2 5 plus Phase 10's Processor + Amp). Resize lands in the Phase 9 autosave + If-Match + undo path with no special-casing.

**Out of phase scope:**
- Manual port-position drag (PORT-MANUAL-01, deferred to v2.4+ if engineers find equal-spacing too restrictive)
- Boundary lines (DRAW-01..04) → Phase 12
- Text annotations (TXT-01..03) → Phase 12
- New shape types beyond the 7 already shipped — none in v2.3

**Carries no migration on `SignalFlowDiagram`** — all per-port labels live inside the existing `canvas_state` JSONField blob, same as the v2.2 connector labels and Phase 10's new shape entries.

</domain>

<decisions>
## Implementation Decisions

### A. Edge model — amends REQUIREMENTS PORT-01

- **D-01:** Ports anchor to **4 edges per shape: Top, Bottom, Left, Right** — not 3. REQUIREMENTS.md PORT-01 currently says "3 edges, bottom reserved for shape label." That reservation was over-cautious: all 7 shape classes left-anchor their label inside the colored band (`refX: 16`, `refY: '50%'` in `signal_flow_editor.js`), so the bottom edge is structurally free. PORT-01 must be amended during the plan phase to read "Top / Bottom / Left / Right" so REQUIREMENTS.md, the planner task list, and the verifier all agree.

### B. Inspector UX for port authoring

- **D-02:** **Per-edge sections in the right-side inspector** when a shape is selected. Each section (Top / Bottom / Left / Right) shows the current port list for that edge plus its own "+ Add port" button. Most explicit — engineer always knows which edge they're adding to. Slight vertical cost in the inspector is acceptable (the inspector already scrolls).
- **D-03:** **Port label uses Phase 10's combobox widget** verbatim — type to autocomplete from the 9-source label endpoint, OR ignore the dropdown and type freeform. One control, two paths (PORT-03's "exclusive" requirement is naturally satisfied because freeform typing overrides the dropdown selection in the same input). Zero new label-input UI to build.
- **D-04:** **Removal via a trash icon next to each port row in the inspector list.** Discoverable, matches the Phase 9 node-mode "Re-link / Delete" affordance pattern. No canvas-hover ✕ in v2.3 (re-evaluate if engineers ask for it in beta).

### C. Resize handle visual + behavior

- **D-05:** **All 4 corner handles** on the selected shape (top-left, top-right, bottom-left, bottom-right). Matches Figma / Miro / Lucidchart conventions — what an engineer expects. Aspect ratio is unconstrained in v2.3 (no Shift-to-constrain modifier — defer to v2.4+ if requested).
- **D-06:** **Live re-distribute during the resize drag.** Ports + their labels re-position on every drag frame so the engineer sees the final layout in real time. Honors the "snap instantly" Area-4 decision (D-10) and matches Phase 8's precision-tool feel.
- **D-07:** **Min-size per shape type is a research output** (per SHP-RESIZE-02). Researcher derives min-width and min-height from `(longest port label width on each edge + padding)` and `(port-count × minimum-spacing)`. Do NOT hard-code per-shape floor numbers in CONTEXT.md — they would become wrong the moment a long label is added.

### D. Port label positioning on canvas

- **D-08:** **Labels render inside the shape body, perpendicular to the edge** they belong to:
  - **Left** edge → labels read left-to-right, left-anchored just inside the edge
  - **Right** edge → labels read left-to-right, right-anchored just inside the edge
  - **Top** edge → labels read horizontally just below the port dot, inside the shape
  - **Bottom** edge → labels read horizontally just above the port dot, inside the shape
  Most space-efficient and never collides with connectors outside the shape. Feeds directly into D-07 min-size math.
- **D-09:** **Label only on the canvas** — no index number prefix. Engineers identify ports by the labels they chose. The inspector port list may still show an ordinal in the row for reference, but the canvas stays minimal.

### E. Auto-distribute timing + visual

- **D-10:** **Snap instantly** on port add/remove — no animation tween. Matches Phase 8's snap-to-grid feel; zero animation budget; one less moving part to debug.
- **D-11:** **PORT-06 auto-expansion** is the default behavior: when a new port would overflow the current shape size at minimum spacing, the shape grows just enough to fit. Show a **subtle toast** ("Shape resized to fit ports") using the existing Phase 9 toast pattern, so the engineer knows why the shape just grew.

### F. Connector behavior on port operations

- **D-12:** **Connectors re-anchor immediately** to the shape's edge midpoint when their port is removed (PORT-05). Same frame as the port disappears. Honors the "snap instantly" spirit and avoids stale-looking connectors.
- **D-13:** **PORT-04 back-compat switch is whole-shape, not per-edge.** A shape with zero custom ports keeps the v2.2 4-generic-port snap behavior. The moment the engineer adds the first custom port to ANY edge, the v2.2 generic ports disappear and only engineer-authored ports remain as snap targets across the entire shape. Cleanest mental model: "this shape is yours now."

### G. Claude's Discretion

- **Port state storage** — whether per-port labels live inside JointJS-native `ports.items[N].attrs` or as a sibling `portLabels` map on `element.attributes` is a researcher/planner pick. Both work; JointJS-native is the path of least resistance unless the researcher finds a serialization issue.
- **Exact pixel size / hover / active styling of the corner resize handles** — follow the existing Phase 8 selection-visual treatment (`.is-selected`); specific handle geometry is implementation detail.
- **Toast styling for D-11 "Shape resized to fit ports"** — reuse the existing `.sfd-toast` pattern from Phase 9 autosave; copy is fine as-is or planner may tighten.
- **Inspector port-list row ordinal display** — whether each row shows `1, 2, 3...` ordinal next to the label in the inspector (not on canvas) is a small UI choice; planner picks.

### H. Carried decisions (already locked from prior phases)

- **Phase 10 D-05** — `SystemProcessor` is excluded from the 9-source autocomplete (no canonical channel/label field on the model). PORT-03 dropdown inherits this exclusion automatically because it reuses the same endpoint.
- **Phase 10 D-02** — autocomplete results display as `<label> — <source tag>` (e.g., `FOH Lead — Device Input`). PORT-03 dropdown gets this same display format for free.
- **Phase 9** — autosave is 1500ms debounced with `If-Match` optimistic-lock 409 conflict handling. **All Phase 11 edits (port add/remove, port label change, shape resize) land in this same path** — no special autosave codepath.
- **Phase 8 D-13** — 20px snap grid. **Shape resize dimensions snap to multiples of 20px** when snap is enabled (engineer can toggle off in toolbar).
- **Phase 8 magnet semantics** — `magnet: 'passive'` = inbound-only port, `magnet: true` = outbound source port. Engineer-authored ports still need to declare in/out direction. **Open for research:** is direction a per-port attribute the engineer sets in the inspector, or is direction inferred from edge (Top/Left = in, Right/Bottom = out, matching the v2.2 generic-port convention)? Default toward "inferred from edge" unless research shows engineers want explicit control.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope
- `.planning/REQUIREMENTS.md` §PORT (lines 12–20) — PORT-01..06. **NOTE: PORT-01 must be amended from "3 edges" to "4 edges (T/B/L/R)" per D-01 in this CONTEXT.**
- `.planning/REQUIREMENTS.md` §"Shape Sizing — SHP-RESIZE" (lines 22–28) — SHP-RESIZE-01..03
- `.planning/ROADMAP.md` "Phase 11" entry (line 48) — defines goal and dependency on Phase 10

### v2.3 patterns already shipped (reuse, don't reinvent)
- `.planning/phases/10-autocomplete-png-export-new-shapes/10-CONTEXT.md` — D-01..D-04 lock the autocomplete behavior (1-char trigger, 200ms debounce, 8 results, alphabetical, `label — source` display). PORT-03 dropdown inherits all of this.
- `.planning/phases/10-autocomplete-png-export-new-shapes/10-01-SUMMARY.md` — exact endpoint URL (`planner:signal_flow_label_autocomplete`), 9-source SOURCES list, SystemProcessor exclusion rationale
- `.planning/phases/10-autocomplete-png-export-new-shapes/10-03-SUMMARY.md` — the JS combobox widget (`signal_flow_editor.js:1775-1935`) — port-label control should be the same control, attached to a different input

### v2.2 patterns to extend
- `.planning/phases/08-canvas-smart-shapes-connectors/08-CONTEXT.md` — D-13 (20px snap grid), D-14 (4000×3000 finite canvas), magnet semantics, hover-revealed ports
- `.planning/phases/09-autosave-orphan-rendering/09-CONTEXT.md` — autosave debounce, If-Match 409 conflict, toast pattern, node-mode inspector ("Re-link / Delete") affordance pattern that D-04 follows

### Code-level entry points
- `planner/static/planner/js/signal_flow_editor.js:80-122` — current `standardPortGroups()` + `portsForRect()`. **Phase 11 replaces these with engineer-authored port arrays per shape, while preserving the back-compat 4-generic-port behavior per D-13 until the first custom port is added.**
- `planner/static/planner/js/signal_flow_editor.js:128-360` — the 7 shape class definitions. All 7 must gain resize + per-shape port authoring; the new behavior must not regress any of them.
- `planner/static/planner/js/signal_flow_editor.js:291-308` — `defaultLink`, `validateMagnet`, `validateConnection`. **PORT-04 per-port snap targeting must update `validateConnection`** so connectors can only end on port magnets, not on the shape body. Currently this is already the rule (line 305: "both ends MUST be magnets") — Phase 11 just changes which magnets exist on the shape.
- `planner/static/planner/js/signal_flow_editor.js:1300-1900` — inspector mode logic (`setInspectorMode('connector' | 'node' | ...)`, `connectorFieldRows`). **Phase 11 adds a port-authoring section to node mode** for any shape that supports ports — see D-02.
- `planner/static/planner/css/signal_flow.css` — Sections 1–13 already exist (Phase 8 + 9 + 10). Phase 11 appends **Section 14 (port-label rendering — per D-08 perpendicular-inside) + Section 15 (resize handles — per D-05 four corners) + Section 16 (inspector port-list row + trash icon — per D-02/D-04)** per the established append-at-end convention.
- `planner/views.py` (Phase 9 `_enrich_nodes` at the original line cited in Phase 10 CONTEXT) — when canvas_state grows new per-port label data, `_enrich_nodes` does NOT need to touch the port labels themselves (they're engineer-authored strings, not server-derived). But if a labeled port references an equipment record that gets deleted, the port label stays as-is (last-known good text) — engineer-authored data, never propagated.

### Vendored libraries (already loaded in Phase 7 vendor bundle)
- `joint.min.js` 4.2.4 — has the `joint.elementTools.Resize` class (or equivalent) for corner-handle resize. Researcher confirms the exact tool name and whether it ships in the MPL-2.0 core or only JointJS+ (paid).

### Architectural constraint
- `CLAUDE.md` §"Overriding Django admin CSS from JavaScript" — the inspector port-list lives inside admin templates. DOM-style writes from JS MUST use `el.style.setProperty(prop, value, 'important')`. JointJS SVG inside `#sfd-paper` (port circles, port labels, resize handles) is in its own namespace and is unaffected.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **Phase 10's autocomplete combobox** (`signal_flow_editor.js:1775-1935`) — the entire control lifts and re-attaches to a new input (the inspector port-label field). The `data-label-autocomplete-url` attribute pattern from Phase 10 already supplies the endpoint without per-shape coupling.
- **JointJS port API** — `element.addPort()`, `element.removePort()`, `element.getPorts()`, `port.attrs` for per-port label SVG. JointJS-native path; no abstraction layer needed unless researcher finds a serialization issue with the `canvas_state` JSON.
- **Inspector node-mode** (Phase 9) — already shows "Re-link equipment" + "Delete shape". Phase 11 just adds port-authoring sections to the same panel.
- **Phase 9 toast pattern** (`.sfd-toast`) — reuse as-is for D-11 "Shape resized to fit ports."

### Established Patterns

- **Append CSS sections to the end** of `signal_flow.css` (Sections 1–13 exist; Phase 11 adds 14/15/16). Comment block at the top of the file enumerates sections.
- **Per-shape attrs override the standard pattern** — each shape class extends `joint.dia.Element.extend()` with its own `attrs` block. Phase 11's per-shape resize + per-shape port authoring can be implemented as a shared mixin or as additions inside each shape's class — researcher picks.
- **`magnet: 'passive'` = inbound, `magnet: true` = outbound** is the v2.2 convention. Researcher must answer: are engineer-authored ports direction-aware (engineer picks in/out), or direction-inferred from edge (Top/Left=in, Bottom/Right=out)?

### Integration Points

- **`_enrich_nodes` (Phase 9 server-side enrichment)** does NOT need to read or write per-port labels — they're engineer-authored strings stored in `canvas_state.cells[N].ports.items[M].label` (or wherever researcher pins them). They survive renames of the linked equipment record because they're never derived from it.
- **Autosave** is touched once per port-edit / resize via the existing `scheduleAutosave()` debounce — no new endpoint, no new payload shape (canvas_state is opaque JSON to the server).
- **PORT-05 connector-survival** — the JointJS `link:disconnect` event fires when a port is removed mid-flow. Plan should hook this and re-anchor the connector endpoint to the shape's edge midpoint (D-12).

</code_context>

<specifics>
## Specific Ideas

- **Reuse over reinvent.** Phase 10 just shipped a polished autocomplete combobox; PORT-03 must use that exact widget, not a new one. Same for the Phase 9 toast.
- **"This shape is yours now" mental model (D-13).** Once an engineer adds a custom port to a shape, the v2.2 generic ports stop existing on that shape — clean break. No mixed "some-generic-some-custom" state.
- **REQUIREMENTS PORT-01 amendment (D-01)** is a real requirements edit, not just a CONTEXT.md clarification. The planner should update REQUIREMENTS.md as one of its plan tasks so verifier + future audits see the corrected text.

</specifics>

<deferred>
## Deferred Ideas

- **Manual port-position dragging** — REQUIREMENTS PORT-MANUAL-01 is already deferred to v2.4+ pending engineer feedback on equal-spacing.
- **Shift-to-constrain aspect ratio on resize** — not in v2.3; revisit if engineers ask for it in beta.
- **Canvas-hover ✕ for port removal** (Area-1 Option 3) — only the inspector trash icon in v2.3; add the canvas affordance later if discoverability proves to be an issue.
- **Per-port direction picker in inspector** — pending research outcome. If "infer from edge" is unambiguous, no UI; if engineers want explicit control, that becomes a v2.4+ inspector control.
- **Port re-ordering within an edge** — drag-to-reorder ports inside the inspector list is a v2.4+ polish item if engineers ask for it. Phase 11 ships add/remove only; order is insertion order.

</deferred>

---

*Phase: 11-ports-and-resize*
*Context gathered: 2026-05-24*
