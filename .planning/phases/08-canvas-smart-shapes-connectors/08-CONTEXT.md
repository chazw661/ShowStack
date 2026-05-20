# Phase 8: Canvas, Smart Shapes & Connectors — Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 8 turns the Phase 7 editor shell into a live JointJS canvas. The engineer can:
- Drag any of 5 smart shape types (Console / Device / SpeakerArray / CommBeltPack / Generic) from a left sidebar picker onto the canvas; typed shapes open an equipment picker modal at the drop site to bind to a project record (Generic skips the picker)
- Connect shapes via orthogonal connectors with port-to-port snapping
- Set each connector's signal type (analog / AES / Dante / MADI / intercom), direction (source→target / bidirectional), and circuit-label string
- Pan (space+drag, middle-click), zoom (in / out / fit), toggle snap-to-grid, undo / redo, shift- and rubber-band-multi-select, delete via Delete / Backspace
- See the viewport (pan position + zoom) persist across reloads

Phase 8 does NOT cover: server-side state enrichment (SHP-06 label propagation, SHP-07 ghosted orphans → Phase 9), autosave (DGM-06/07/08 → Phase 9), circuit-label autocomplete behavior (LBL → Phase 10), PNG export (EXP-01 → Phase 10). All of these are downstream of Phase 8 and out of scope here.

The single source of truth for diagram state remains the `SignalFlowDiagram.canvas_state` JSONField (Phase 7). Phase 8 builds the in-browser editor that produces that JSON; persistence happens on a manual save trigger for now (Phase 9 wires real autosave).

</domain>

<decisions>
## Implementation Decisions

### Shape Style + Sidebar Picker
- **D-01:** Distinct geometry per shape type. Console = wide rectangle, Device = standard rectangle, SpeakerArray = trapezoid/parallelogram, CommBeltPack = pill / rounded-rect, Generic = dashed-border rectangle. Geometry encodes role at a glance — matches live-audio engineer parsing patterns.
- **D-02:** Subtle color band per type (Console = teal, Device = slate, SpeakerArray = orange, CommBeltPack = purple, Generic = grey). Band sits on the top or left edge; body stays white. Avoids fighting connector signal-type colors for visual attention. Exact hex values are Claude's discretion (default to ShowStack admin theme tokens where possible).
- **D-03:** Left vertical sidebar holding 5 stacked tiles (icon + type label). Sits between the back-link area and the paper. Matches Lucidchart / draw.io convention engineers already know. Keeps the top toolbar reserved for canvas actions.
- **D-04:** Drag-to-canvas drop at cursor. Shape lands at the exact drop coords accounting for scroll + zoom via `paper.clientToLocalPoint({ x: event.clientX, y: event.clientY })` per pitfalls research (CNV-01 acceptance criterion).

### Toolbar + Connector Inspector
- **D-05:** Floating right-side inspector panel holds connector properties (signal-type dropdown, direction toggle, circuit-label text input). Same panel pattern can later host node-specific properties (v2.3+).
- **D-06:** Top toolbar = canvas controls only. Buttons in order: zoom-out / zoom-in / zoom-to-fit / snap-to-grid toggle / undo / redo. Save status indicator is a placeholder for Phase 9 (`<span id="sfd-save-status">` rendered but inert). Toolbar lives inside the existing `#sfd-toolbar` div from `editor.html` (Phase 7 locked).
- **D-07:** Inspector auto-shows on connector select; auto-hides when selection clears or moves to a node / empty canvas. Zero manual toggle.
- **D-08:** Selection style = 2px accent-color border on selected element + dashed bounding-box around multi-select group. JointJS default tool handles (resize) suppressed for now — node sizing stays auto from text width.

### Equipment Picker Modal
- **D-09:** Drop-first flow. Shape lands at cursor (placeholder render); equipment picker modal opens immediately at drop site (or screen-centered for simpler positioning). After pick, label seeds from equipment name and the shape JSON gains `content_type_id` + `object_id` + `saved_label` (snapshot for Phase 9 ghosting).
- **D-10:** Cancelling the picker removes the placeholder shape entirely. No half-built / unassigned-state nodes in canvas JSON. Engineers who want a freeform shape use the **Generic** type (SHP-05), which skips the picker entirely.
- **D-11:** Instant text search across name + key fields. Modal renders a search input at top + scrollable result list filtered as the user types. Match against: `name` always, plus per-type secondary fields (Console: `name + DSP mixer / channel count`; Device: `name + model + serial`; SpeakerArray: `name + cabinet count`; CommBeltPack: `name + beltpack ID`).
- **D-12:** Reuse Django admin modal pattern. Match styling used in `templates/includes/_help_modal.html` and existing admin themes (django-admin-interface + colorfield CSS variables). Dark backdrop, centered light card. No new CSS file — extend `custom_admin.css` if needed.

### Canvas + Signal-Type Visual Conventions
- **D-13:** Snap-to-grid ON by default, **20px grid**. Visible as light dotted grid lines on the white paper. Toolbar toggle persists in the `viewport` JSONField alongside pan/zoom (key: `snapEnabled: bool`).
- **D-14:** Finite canvas bounds **4000 × 3000 px**. Stays inside `@joint/core`'s standard finite-paper model — no PaperScroller dependency (which is JointJS+ paid). Viewport state stores `{ x, y, scale, snapEnabled }`.
- **D-15:** Initial viewport (fallback when `SignalFlowDiagram.viewport` is `{}`) = **100% zoom, paper origin centered on screen**. CNV-08 viewport persistence applies on every subsequent open.
- **D-16:** Signal-type line recipe (5 distinct visually + grayscale-distinguishable via dash):

  | Type | Color | Stroke width | Dash pattern (SVG `stroke-dasharray`) |
  |------|-------|--------------|----------------------------------------|
  | analog | `#1a1a1a` (near-black) | 2 | none (solid) |
  | AES | `#1565c0` (royal blue) | 2 | none (solid) |
  | Dante | `#00bcd4` (cyan) | 2 | `6 4` |
  | MADI | `#ef6c00` (orange) | 2.5 | `10 3 3 3` |
  | intercom | `#7b1fa2` (purple) | 2 | `2 4` |

  Color + dash combine — REQUIREMENTS constraint says "color is not the only differentiator" because grayscale print must remain readable. Dash patterns alone discriminate all 5 types if color is stripped.

### Claude's Discretion
- **Connector creation UX:** Drag from port handle (matches CON-01 wording: "dragging from an output port to an input port"). JointJS port-snapping default behavior applies. Pre-connection magnet validation rejects mid-shape drops (CON-03).
- **Port visual style:** Hover-revealed ports — port dots appear when the cursor is over a node or a connection is mid-drag, hidden otherwise. Keeps the canvas visually clean at rest.
- **Default values on new connectors:** signal type = `analog`, direction = `source→target`, circuit-label = empty string. Engineer edits in the inspector immediately after creation.
- **Exact accent / theme colors** for shape color bands, selection borders, sidebar tiles, inspector panel: pull from existing `django-admin-interface` theme variables and `custom_admin.css` tokens to stay coherent with the rest of ShowStack.
- **Sidebar tile icons:** lucide / material icon set already used in templates. Specific glyphs (mixer, rack, speaker, headset, square-dashed) are Claude's pick.
- **Save trigger for Phase 8 verification:** A manual "Save" button on the toolbar that POSTs `canvas_state` to the autosave URL is acceptable as a Phase 8 verification path. Real debounced autosave + version-conflict handling is Phase 9 scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project + Phase Scope
- `.planning/ROADMAP.md` §"Phase 8: Canvas, Smart Shapes & Connectors" — Goal, success criteria, requirement IDs, research flag (CommandManager / Clipboard availability)
- `.planning/REQUIREMENTS.md` §"Canvas (CNV)", §"Smart Shapes (SHP)", §"Connectors (CON)", §"Constraints", §"Traceability" — All 21 requirement IDs in Phase 8 scope plus locked constraints (MPL-2.0, system fonts only, IDOR scoping)

### Research (research-grounded basis for v2.2)
- `.planning/research/SUMMARY.md` — Locked technology stack, build-order, critical pitfalls
- `.planning/research/PITFALLS.md` — `cellNamespace` lookup, `clientToLocalPoint` pointer math, IDOR patterns
- `.planning/research/STACK.md` — `@joint/core` 4.2.4 (MPL-2.0) vendoring rules
- `.planning/research/FEATURES.md` — v2.2 must-haves, defers, anti-features (auto-layout, real-time collab, SVG export)
- `.planning/research/ARCHITECTURE.md` — Build-order; smart shape `cellNamespace` requirement before `graph.fromJSON()`

### Phase 7 Foundation (read so we don't re-decide what's locked)
- `.planning/phases/07-foundation-crud-editor-shell/07-01-SUMMARY.md` — `SignalFlowDiagram` model: `canvas_state JSONField`, `viewport JSONField`, `version IntegerField` already migrated (0158); `unique_together=(project, name)`
- `.planning/phases/07-foundation-crud-editor-shell/07-02-SUMMARY.md` — Vendor JS bundles (`joint.min.js`, `html-to-image.min.js`) live at `planner/static/planner/js/vendor/`; `THIRD_PARTY_LICENSES.txt` at project root; MPL-2.0 compliance
- `.planning/phases/07-foundation-crud-editor-shell/07-03-SUMMARY.md` — 9 URL patterns under `planner:signal_flow_*`; state/autosave/autocomplete/export-png URL names locked
- `.planning/phases/07-foundation-crud-editor-shell/07-04-SUMMARY.md` — `editor.html` shell: `#sfd-container` + 5 `data-*` URL attrs; `#sfd-toolbar` + `#sfd-paper` layout locked; vendor JS load order: `joint.min.js` → `html-to-image.min.js` → `signal_flow_editor.js` (deferred)

### Code-Level References
- `planner/templates/planner/signal_flow/editor.html` — The DOM shell Phase 8 fills in (#sfd-toolbar + #sfd-paper)
- `planner/static/planner/js/signal_flow_editor.js` — Phase 7 stub IIFE; Phase 8 extends this file (no second JS file)
- `planner/static/planner/js/vendor/joint.min.js` — Vendored 4.2.4 UMD bundle; do not modify (MPL-2.0 file-level copyleft)
- `planner/views.py:6328` `_get_track_for_request` — IDOR pattern to replicate inside the signal-flow views (state endpoint, picker autocomplete)
- `planner/models.py` `SignalFlowDiagram` model — schema fields all in place; no new migration in Phase 8
- `templates/includes/_help_modal.html` — Existing admin modal pattern to reuse for the equipment picker
- `CLAUDE.md` §"Overriding Django admin CSS from JavaScript" — All toolbar / modal HTML DOM style writes MUST use `el.style.setProperty(prop, value, 'important')` because the toolbar lives inside admin templates. JointJS-managed SVG inside `#sfd-paper` is unaffected.

### Research Flag To Resolve in Plan-Phase Research Step
- Verify `@joint/core` 4.2.4 ships `CommandManager` and `Clipboard`. CNV-05 (undo/redo) depends on `CommandManager`. If only available in JointJS+, plans must roll a custom undo stack from `graph` events. Confirm before locking CNV-05 task list. Clipboard is for COPY-01 (deferred to v2.3) but useful to know now.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `editor.html` shell with `#sfd-container`, `#sfd-toolbar`, `#sfd-canvas-container`, `#sfd-paper` — Phase 7 locked; Phase 8 fills in toolbar contents + initialises JointJS on `#sfd-paper`
- `signal_flow_editor.js` stub IIFE — reads `dataset.diagramId`, `dataset.stateUrl`, `dataset.autosaveUrl`, etc.; Phase 8 extends the IIFE (no new JS file)
- `joint.min.js` (vendored, 4.2.4) — already present; exposes `joint` global on window
- `html-to-image.min.js` (vendored) — present for Phase 10; Phase 8 ignores
- `templates/includes/_help_modal.html` — Admin modal pattern (dark backdrop + centered card) to reuse for equipment picker
- `custom_admin.css` — Project-wide admin theme stylesheet; extend for sidebar + inspector + grid styles if needed
- `_get_track_for_request` (planner/views.py:6328) — IDOR pattern to replicate for the equipment-picker autocomplete (project-scoped queryset)

### Established Patterns
- **Session-based project scoping** (`CurrentProjectMiddleware`) — every model lookup in Phase 8 views uses `request.current_project`, never URL params
- **Custom admin site** (`showstack_admin_site`) — `SignalFlowDiagramAdmin` already registered (Phase 7); no new admin work in Phase 8
- **Whitenoise / collectstatic** — every new static file (none expected in Phase 8) must pass `collectstatic --noinput`
- **DOM style writes through admin templates use `setProperty('important')`** — toolbar buttons, modal styles. JointJS-managed SVG inside `#sfd-paper` is in its own namespace and is unaffected.
- **JSON `canvas_state` is the single source of truth** — no normalized DiagramNode / DiagramEdge tables. Smart-shape equipment refs live as `{ contentTypeId, objectId, savedLabel }` inside the node JSON.

### Integration Points
- `#sfd-toolbar` div (Phase 7 locked) — Phase 8 appends button group(s) for canvas controls
- `#sfd-canvas-container` (Phase 7 locked) — Phase 8 mounts a left-side `#sfd-sidebar` (shape picker) and a right-side `#sfd-inspector` panel as siblings of `#sfd-paper`
- `dataset.stateUrl` / `dataset.autosaveUrl` — Phase 8 reads diagram state on load (via the stateUrl endpoint that exists from Phase 7 as a stub); writes back on manual Save trigger (autosave behavior is Phase 9)
- `joint.shapes` namespace — Phase 8 registers 5 custom shape classes (Console, Device, SpeakerArray, CommBeltPack, Generic) into `joint.shapes.showstack` namespace and passes that as `cellNamespace` to the Graph constructor before any `fromJSON()` call (pitfalls research mitigation)

</code_context>

<specifics>
## Specific Ideas

### Signal-Type Line Recipe (locked from discussion)

| Type | Color | Stroke width | SVG `stroke-dasharray` |
|------|-------|--------------|------------------------|
| analog | `#1a1a1a` | 2 | none |
| AES | `#1565c0` | 2 | none |
| Dante | `#00bcd4` | 2 | `6 4` |
| MADI | `#ef6c00` | 2.5 | `10 3 3 3` |
| intercom | `#7b1fa2` | 2 | `2 4` |

### Shape Type-to-Color Band Mapping

| Type | Color band |
|------|-----------|
| Console | teal |
| Device | slate |
| SpeakerArray | orange |
| CommBeltPack | purple |
| Generic | grey |

### Sidebar Picker Tile Structure
- 5 tiles, stacked vertically, top → bottom: Console, Device, SpeakerArray, CommBeltPack, Generic
- Each tile = icon (left) + label (right), `draggable="true"`
- Drag start sets `dataTransfer` payload `{ shapeType: '<one of 5>' }`
- Drop handler on `#sfd-paper` reads payload, converts client coords to paper coords via `paper.clientToLocalPoint()`, opens picker modal (typed shapes) or drops Generic directly

### Equipment Picker Modal Structure
- Title: `"Pick a <Type>"` (e.g., "Pick a Device")
- Search input at top (auto-focus on open)
- Scrollable list below: each row = `<equipment name (bold)>` + `<secondary detail line>` + click-to-select
- Empty state: `"No <Type> records in this project — add equipment in Admin"` with link to the relevant admin changelist
- Cancel button + Escape key both remove the placeholder shape and close the modal

### Canvas Paper Configuration
- `width: 4000`, `height: 3000`
- `gridSize: 20`
- `drawGrid: true` when snap is ON (per D-13); `drawGrid: false` when toggled OFF
- `cellNamespace: joint.shapes.showstack` (custom shape namespace registered before paper init)
- `defaultLink` returns an orthogonal-router connector with the default signal-type styling

</specifics>

<deferred>
## Deferred Ideas

### Phase 9
- SHP-06 (label propagation from renamed equipment via server-side `_enrich_nodes()`)
- SHP-07 (ghosted-orphan rendering for deleted-equipment refs)
- DGM-06, DGM-07, DGM-08 (debounced autosave, HTTP 409 version-conflict banner, keepalive on tab close)

### Phase 10
- LBL-01/02/03 (circuit-label autocomplete from `DeviceInput.signal_name` / `DeviceOutput.signal_name` / `ConsoleInput.source`)
- EXP-01 (PNG export via `html-to-image` with white background)

### v2.3 +
- COPY-01 (copy / paste of selected nodes — gated on `@joint/core` Clipboard availability; surfaces from the research flag noted above)
- Per-channel ports on shapes (SHP-08 ships per-side single port only)
- SVG faceplates for racks
- Group / ungroup nodes by location
- Alignment guides (smart snap lines)
- Mobile `/m/` viewer
- IP address as secondary node label

### Ideas Surfaced But Not Pursued in Discussion
- Connector creation alternative UX (click-port-then-click-port) — defaulted to drag-from-port-handle per CON-01 wording
- Port visual style alternatives (always-visible vs on-select) — defaulted to hover-revealed for canvas cleanliness
- Connector right-click context menu — not in scope; inspector covers all 3 connector properties

</deferred>

---

*Phase: 08-canvas-smart-shapes-connectors*
*Context gathered: 2026-05-20*
