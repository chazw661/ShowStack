# Milestone v2.2 Requirements — Signal Flow Diagrammer

**Defined:** 2026-05-19
**Driver:** GitHub issue #13
**Core Value:** ShowStack knows your patch, your labels, and your gear; once entered, that data drives every export your show needs.

Source: `.planning/research/SUMMARY.md` (2026-05-19) is the research-grounded basis for this scope. The locked technology stack is `@joint/core` 4.2.4 (MPL-2.0) for the canvas, `html-to-image` 1.11.11 (MIT) for PNG export, zero new Python dependencies. The single source of truth for canvas state is a `JSONField` blob on a new `SignalFlowDiagram` model; smart-shape equipment references live inside the JSON via `GenericForeignKey` keys (`content_type_id`, `object_id`), enriched server-side on load.

## v2.2 Requirements

### Diagram Management — DGM

- [ ] **DGM-01**: User can see all signal-flow diagrams for the current project on a list page, with create / rename / delete actions.
- [ ] **DGM-02**: User can create a new diagram by entering a name; diagram is scoped to the current project via `CurrentProjectMiddleware`.
- [ ] **DGM-03**: User can rename a diagram from the list page; name is unique per project.
- [ ] **DGM-04**: User can delete a diagram from the list page; deletion removes the canvas state and all node/connector references.
- [ ] **DGM-05**: All diagram views enforce `.filter(project=request.current_project)` on every lookup; cross-project access returns 404.
- [ ] **DGM-06**: Canvas changes autosave on idle within 2.5 s; the editor shows a "Saved" / "Saving…" / "Failed — retry" status indicator.
- [ ] **DGM-07**: Concurrent edits from a second tab return HTTP 409 on save; the losing tab shows a non-dismissable banner: "Diagram was modified elsewhere — reload to see latest."
- [ ] **DGM-08**: Closing the tab or navigating away triggers a `keepalive: true` final save if there are unsaved changes.

### Canvas & Editor UX — CNV

- [ ] **CNV-01**: User can drag a shape from the sidebar shape picker onto the canvas; the shape lands at the cursor position (after scroll/zoom).
- [ ] **CNV-02**: User can pan the canvas via space-bar + drag or middle-click drag.
- [ ] **CNV-03**: User can zoom in, zoom out, and zoom-to-fit via toolbar buttons; current zoom level is persisted with the diagram.
- [ ] **CNV-04**: User can toggle snap-to-grid on/off via a toolbar button; when on, dragged shapes snap to the grid.
- [ ] **CNV-05**: User can undo and redo via Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z; the command stack is wired before the first graph mutation.
- [ ] **CNV-06**: User can select multiple nodes via shift-click and via rubber-band (drag empty canvas to draw selection rectangle).
- [ ] **CNV-07**: User can delete the current selection (single or multi) via the `Delete` or `Backspace` key.
- [ ] **CNV-08**: When the user reopens a diagram, the viewport (pan position + zoom level) restores to where they left off.

### Smart Shapes — SHP

- [ ] **SHP-01**: User can drop a **Console** shape and pick a project Console record via a modal; the node label seeds from the Console's name.
- [ ] **SHP-02**: User can drop a **Device** shape and pick a project Device record (Rio, Tio, RIO3224-D, AVB rack, etc.) via the same modal pattern.
- [ ] **SHP-03**: User can drop a **SpeakerArray** shape and pick a project SpeakerArray record.
- [ ] **SHP-04**: User can drop a **CommBeltPack** shape and pick a project CommBeltPack record.
- [ ] **SHP-05**: User can drop a **Generic** shape (no record link); the engineer types the label by hand. Used for gear not yet modeled in ShowStack.
- [ ] **SHP-06**: When linked equipment is renamed, the shape's label updates on the next diagram load (label propagation via server-side `_enrich_nodes()`).
- [ ] **SHP-07**: When linked equipment is deleted, the shape renders **ghosted** (muted style, dashed border) with its last-known label preserved from a snapshot stored on the node. Engineer chooses whether to delete or relink the node.
- [ ] **SHP-08**: Each shape exposes one generic "in" port per side and one generic "out" port per side, used as connector snap targets. (Per-channel ports deferred to v2.3.)
- [ ] **SHP-09**: The equipment picker modal lists only records belonging to `request.current_project`.

### Connectors — CON

- [ ] **CON-01**: User can draw a connector between two nodes by dragging from an output port to an input port; routing is orthogonal (right-angle).
- [ ] **CON-02**: User can set the connector's **signal type** from a 5-option dropdown: **analog**, **AES**, **Dante**, **MADI**, **intercom**. Each type renders with a distinct line style + color (color is not the only differentiator — line dash pattern carries the meaning too, for grayscale print).
- [ ] **CON-03**: Connectors snap to defined ports; mid-shape drops are rejected.
- [ ] **CON-04**: User can drag midpoint waypoints to route the connector around obstacles manually.
- [ ] **CON-05**: User can set the connector **direction** to *source-to-target* (default, arrow on target end) or *bidirectional* (no arrows; used for intercom partylines).
- [ ] **CON-06**: Each connector carries a **circuit-label** string field that renders along the line.

### Circuit-Label Autocomplete — LBL

- [ ] **LBL-01**: Typing in a connector's circuit-label field surfaces autocomplete suggestions sourced from existing project signal-name fields: `DeviceInput.signal_name`, `DeviceOutput.signal_name`, `ConsoleInput.source`, and `ConsoleAuxOutput.name`.
- [ ] **LBL-02**: Autocomplete results are scoped to `request.current_project`; cross-project signals never appear in results.
- [ ] **LBL-03**: Engineer can override autocomplete and enter free-text; the connector accepts any string.

### Export — EXP

- [ ] **EXP-01**: User can export the current diagram as a PNG file from a toolbar "Export PNG" button. The PNG renders with a white background, captures the full canvas (not just the visible viewport), and matches on-screen label fonts (system fonts only — no cross-origin font taint).

## Future Requirements (deferred to v2.3+)

- **PDF-01**: PDF export for printed technical riders. Trigger: beta engineers report PNG insufficient for show documentation.
- **MOB-01**: Mobile `/m/` read-only viewer using the same `state/` JSON endpoint. Pre-design preserved in v2.2 (HTML shell + JSON load + `readOnly` JS flag).
- **AUTO-01**: Obstacle-aware orthogonal auto-routing of connectors. v2.2 ships hand-roll routing with engineer-controlled waypoints.
- **PORT-01**: Per-channel ports on smart shapes (a Console exposes a port per input/output channel from its DB record). v2.2 ships generic-in/generic-out only.
- **COPY-01**: Copy / paste of selected nodes — gated on JointJS `Clipboard` availability in `@joint/core` 4.2.4 vs JointJS+ (research flag in Phase 5 planning).
- **IP-01**: Optional IP-address annotation on smart shapes (data already in `Console.primary_ip_address` / `Device.primary_ip_address`).
- **CMM-01**: COMM Config integration — auto-generate intercom diagram from `CommBeltPack` + `CommChannel` records. Unblocked by v2.2's CommBeltPack smart shape.
- **PAC-01**: PA Cable Schedule overlay — visualize cable runs from existing `PACableSchedule` records on top of the speaker-system portion of the diagram.
- **ALIGN-01**: Smart alignment guides (snap lines between nodes).
- **SVG-01**: SVG faceplate icons for racks. Deliberately deferred — engineers' default expectation is text labels.

## Out of Scope (explicit exclusions)

These were considered and deliberately excluded from v2.2. Reopening any of them needs a milestone-boundary decision.

- **Auto-layout** (hierarchical / force-directed): destroys physical topology (FOH center, stage left/right, monitor world stage right). The most-cited Lucidchart complaint from AV engineers.
- **Real-time multi-user collaborative editing**: last-write-wins autosave with HTTP 409 conflict is correct for solo A1 workflow.
- **SVG export as an artifact**: PNG covers embedding; PDF (v2.3) covers print. SVG would create a secondary copy outside ShowStack, defeating source-of-truth.
- **Pictographic rack-unit faceplates per model**: maintenance burden across hundreds of equipment models; labels carry the semantic weight.
- **Console families outside Yamaha CL/QL/Rivage PM**: already out of scope at the project level.
- **Network monitoring inside ShowStack**: already out of scope at the project level (v1.0 was scrapped).

## Constraints

- **No new Python dependencies.** `models.JSONField` and `django.contrib.contenttypes` are built into Django 5.x. Confirmed via STACK.md.
- **`@joint/core` is MPL-2.0** (not MIT as initially noted in PROJECT.md). Vendor the unmodified `joint.min.js`; ship `THIRD_PARTY_LICENSES.txt`; do not patch the JointJS source — use the public API for workarounds.
- **System fonts only on shape and connector labels.** Cross-origin webfonts taint the PNG export canvas with a `SecurityError`.
- **Additive migrations only.** Single `SignalFlowDiagram` migration; no edits to existing tables. Inherits project-level rule.
- **Project scoping enforced on every view.** Replicate the `_get_track_for_request` IDOR pattern from `planner/views.py:6328`; walk canvas JSON on every save to reject cross-project equipment references.

## Traceability

(Filled in by `gsd-roadmapper` after roadmap creation. Each REQ-ID maps to exactly one phase.)

| Requirement | Phase | Status |
|-------------|-------|--------|
| _to be populated_ | _phase_ | _pending_ |

**Coverage target:** 31 / 31 v2.2 requirements mapped to exactly one phase. No orphans.
