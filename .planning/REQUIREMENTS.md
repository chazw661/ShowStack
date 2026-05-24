# Milestone v2.3 Requirements — Signal Flow Diagrammer Export & Enhancements

**Defined:** 2026-05-22
**Driver:** GitHub issue #14 + carried scope from v2.2 Phase 10 (LBL + EXP)
**Core Value:** ShowStack knows your patch, your labels, and your gear; once entered, that data drives every export your show needs.

Source: Issue #14 + `.planning/milestones/v2.2-REQUIREMENTS.md` "deferred" section. Builds on top of the shipped v2.2 Signal Flow Diagrammer (Phases 7–9). Uses the same locked stack: `@joint/core` 4.2.4 (MPL-2.0), `html-to-image` 1.11.11 (MIT), zero new Python dependencies. State stays in the existing `SignalFlowDiagram.canvas_state` `JSONField` blob (per user decision 2026-05-22).

## v2.3 Requirements

### Per-Shape Labeled Ports — PORT

Supersedes v2.2's deferred PORT-01 (per-channel ports) with a richer model: engineer-authored points placed on any edge, labeled either from project signal-name fields OR custom text, with shapes resizable to accommodate any port count.

- [ ] **PORT-01**: User can add a labeled port to any smart shape via the inspector. Ports anchor to one of four edges per shape: **Top**, **Bottom**, **Left**, **Right**. The bottom edge is structurally free because all 7 shape classes left-anchor their body label inside the colored band (`refX: 16, refY: '50%'` in `signal_flow_editor.js`), so bottom-edge ports do not collide with the shape's own label.
- [ ] **PORT-02**: When the inspector adds a port to an edge, all ports on that edge auto-distribute to equal spacing (no manual port-position drag in v2.3).
- [x] **PORT-03
**: Each port can be labeled via one of two paths: (a) a dropdown that surfaces existing project signal-name fields scoped to `request.current_project` (see PORT-LBL-* below for sources), OR (b) a free-text custom label. The two paths are exclusive — picking from the dropdown sets the label; subsequent typing in the custom field overrides it.
- [x] **PORT-04
**: When a shape has at least one port on a given edge, that edge becomes a connector snap target — engineers drag connectors from/to any specific port, not the generic shape edge. The v2.2 single-port-per-edge behavior is preserved when the engineer hasn't added any custom ports yet (back-compat).
- [x] **PORT-05
**: User can remove a port via the inspector; remaining ports on that edge re-distribute to equal spacing. Any connector attached to a removed port detaches gracefully — the connector survives with its endpoint pinned to the shape's edge midpoint (not lost; not silently re-routed).
- [x] **PORT-06
**: Adding ports to a shape with no existing port edge expands the shape's height (vertical-axis edges) or width (top edge) so labels remain readable — width-to-port-count + height-to-port-count are managed automatically alongside SHP-RESIZE-* manual resizing.

### Shape Sizing — SHP-RESIZE

Companion to PORT — engineers need to grow or shrink shapes to accommodate ports or just to fit their canvas layout.

- [ ] **SHP-RESIZE-01**: User can resize ANY smart shape (Console, Device, SpeakerArray, CommBeltPack, Generic, plus the v2.3 Processor + Amp) by dragging a corner handle. Handle appears on selection.
- [x] **SHP-RESIZE-02
**: Shape resize is constrained to a per-type minimum size that always fits the longest label on each port edge plus the shape's own label, so the engineer cannot resize a shape into illegibility. (Specific min-size table is a phase-research output.)
- [ ] **SHP-RESIZE-03**: Resize lands in the autosave + undo path — Ctrl+Z reverses a resize gesture, autosave POSTs the new dimensions, 409 conflict applies same as any other edit.

### New Smart Shape Types — SHP

Adds the missing equipment categories to the sidebar shape picker (currently 5 types).

- [ ] **SHP-10**: User can drop a **Processor** shape from the sidebar and pick a project Processor record (`SystemProcessor`, `P1Processor`, or `GalaxyProcessor` per the existing model hierarchy at `planner/models.py:1898/1939/2097`). Picker modal lists records across all three processor types belonging to `request.current_project`.
- [ ] **SHP-11**: User can drop an **Amp** shape from the sidebar and pick a project Amp record (`Amp` model at `planner/models.py:1658`). Picker modal scoped to current project.

### Boundary Drawing — DRAW

Free-form decorative primitives used to mark zones (FOH, amp world, stage left/right, etc.). NOT connectors — boundaries don't attach to shapes and don't carry signal type.

- [ ] **DRAW-01**: User can enter a "draw boundary" mode via a toolbar button; in that mode, click+drag draws a freeform polyline on the canvas. Mode exits on a sentinel key (e.g., Escape) or on toolbar toggle.
- [ ] **DRAW-02**: Each boundary line carries an editable color (palette of at least 8: black, grey, red, orange, yellow, green, blue, purple — final palette is a UI-spec deliverable) and a line-style: solid, dashed, dotted, double.
- [ ] **DRAW-03**: User can select a boundary line and edit its color and style from the existing right-side inspector (boundary mode shares the inspector pattern from connectors).
- [ ] **DRAW-04**: User can drag boundary line vertices to reshape after placement; user can delete a boundary line with the same `Delete`/`Backspace` keyboard path as shape/connector deletion (selection rules and conflict-locked guards from v2.2 Phase 9 apply unchanged).

### Text Annotations — TXT

Freeform text on the canvas, decoupled from shapes and connectors. Used for "FOH", "Stage Left", labels-on-boundaries, etc.

- [ ] **TXT-01**: User can place a text label on the canvas via a toolbar button → click-to-position → type. The text element lives on the canvas as a JointJS element (not an HTML overlay).
- [ ] **TXT-02**: Text labels expose font-size (3 sizes: small / medium / large — final values are a UI-spec deliverable) and text color (same palette as DRAW-02 plus white for light-on-dark use).
- [ ] **TXT-03**: User can select, drag, edit, and delete a text label using the same selection + keyboard paths as shapes; text edits go through the standard autosave + undo path.

### Circuit-Label Autocomplete — LBL (carried forward from v2.2 Phase 10)

- [ ] **LBL-01**: Typing in a connector's circuit-label field OR in a port's custom-label field surfaces autocomplete suggestions sourced from existing project signal-name fields:
  - `DeviceInput.signal_name`
  - `DeviceOutput.signal_name`
  - `ConsoleInput.source`
  - `ConsoleAuxOutput.name`
  - **New for v2.3 (via SHP-10/SHP-11):** `AmpChannel.*` label fields (final field set is research output) plus the input/output models for the three processor types (`P1Input.signal_name`, `P1Output.signal_name`, `GalaxyInput.signal_name`, `GalaxyOutput.signal_name`, and equivalent fields on `SystemProcessor` — research will resolve which `SystemProcessor` field is canonical)
- [ ] **LBL-02**: Autocomplete results are scoped to `request.current_project`; cross-project signals never appear.
- [x] **LBL-03**: Engineer can override autocomplete and enter free-text; the field accepts any string. (Already works in connector labels today; v2.3 extends to PORT-03
 custom labels.)

### PNG Export — EXP (carried forward from v2.2 Phase 10)

- [ ] **EXP-01**: User can export the current diagram as a PNG file from a toolbar "Export PNG" button. The PNG renders with a white background, captures the full canvas (not just the visible viewport), matches on-screen label fonts (system fonts only — no cross-origin font taint), and includes all canvas elements: shapes, ports, connectors, boundary lines (DRAW), and text annotations (TXT).

## Future Requirements (deferred to v2.4+)

- **PORT-MANUAL-01**: Manual port position dragging (currently auto-equal-spacing only in v2.3). Add if engineers report equal-spacing is too restrictive.
- **DRAW-CURVE-01**: Curved boundary lines (Bezier). v2.3 ships polyline only.
- **DRAW-FILL-01**: Filled translucent zone shapes (vs lines). v2.3 ships line boundaries only.
- **PDF-01**: PDF export for printed riders.
- **MOB-01**: Mobile `/m/` read-only diagram viewer.
- **AUTO-01**: Obstacle-aware orthogonal auto-routing of connectors.
- **COPY-01**: Copy/paste of selected canvas elements (gated on JointJS+ `Clipboard` — still unavailable in `@joint/core` 4.2.4).
- **IP-01**: IP-address annotation on smart shapes (data already in `Console.primary_ip_address` / `Device.primary_ip_address`).
- **CMM-01**: COMM Config integration (auto-generate intercom diagram from `CommBeltPack` + `CommChannel`).
- **PAC-01**: PA Cable Schedule overlay.
- **ALIGN-01**: Smart alignment guides (snap lines between nodes).
- **SVG-01**: SVG faceplate icons for racks.

## Out of Scope (explicit exclusions for v2.3)

These were considered and deliberately excluded from v2.3. Reopening any of them needs a milestone-boundary decision.

- **Per-port routing intelligence**: ports are connector snap targets, not signal-typed (signal type still lives on the connector, not the port). Avoids re-modeling the signal-flow data model mid-arc.
- **Boundary lines as semantic zones**: DRAW lines are decorative — engineers cannot "put a shape inside a zone" with cascading style or behavior in v2.3. Adds analysis features the engineers haven't asked for yet.
- **Rich text formatting in TXT**: plain text only (font size + color, no bold/italic/multiline rich text). v2.4 candidate if engineers ask.
- **Per-shape SVG icons / faceplates**: still deferred from v2.2 (SVG-01).
- **Auto-layout / hierarchical layout**: still excluded (destroys physical topology — the most-cited Lucidchart complaint from the user research).
- **Real-time multi-user collaborative editing**: still last-write-wins + HTTP 409.

## Constraints (held from v2.2 unless noted)

- **No new Python dependencies.** Existing `models.JSONField` + `django.contrib.contenttypes` handle PORT/DRAW/TXT state.
- **State in `canvas_state` JSON blob** (per user 2026-05-22 decision). Ports, boundary lines, and text annotations are new top-level keys / cell types within the existing JSON — autosave + 409 conflict + keepalive + orphan-render code from v2.2 covers them automatically. No schema migration required for the diagram model itself.
- **`@joint/core` MPL-2.0** stays unmodified. Use the public API.
- **System fonts only on shape and connector labels** — same as v2.2. Applies to TXT and DRAW labels as well.
- **Additive migrations only** if any v2.3 work happens to touch model tables (no plans currently to — the Amp / Processor models already exist).
- **Project scoping enforced on every view.** SHP-10/11 picker dispatches go through the same IDOR pattern as Phase 8's `signal_flow_autocomplete`.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PORT-01 | TBD | Pending |
| PORT-02 | TBD | Pending |
| PORT-03 | TBD | Pending |
| PORT-04 | TBD | Pending |
| PORT-05 | TBD | Pending |
| PORT-06 | TBD | Pending |
| SHP-RESIZE-01 | TBD | Pending |
| SHP-RESIZE-02 | TBD | Pending |
| SHP-RESIZE-03 | TBD | Pending |
| SHP-10 | 10 | Done |
| SHP-11 | 10 | Done |
| DRAW-01 | TBD | Pending |
| DRAW-02 | TBD | Pending |
| DRAW-03 | TBD | Pending |
| DRAW-04 | TBD | Pending |
| TXT-01 | TBD | Pending |
| TXT-02 | TBD | Pending |
| TXT-03 | TBD | Pending |
| LBL-01 | 10 | Done |
| LBL-02 | 10 | Done |
| LBL-03 | 10 | Done |
| EXP-01 | 10 | Done |

**Coverage target:** 22 / 22 requirements mapped to exactly one phase by end of roadmapping.
