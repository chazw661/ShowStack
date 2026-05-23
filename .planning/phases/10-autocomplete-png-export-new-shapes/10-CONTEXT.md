# Phase 10: Autocomplete, PNG Export & New Shape Types — Context

**Gathered:** 2026-05-22
**Status:** Ready for planning
**Milestone:** v2.3 (Signal Flow Diagrammer — Export & Enhancements)
**Driver:** Issue #14 + v2.2 carried scope

<domain>
## Phase Boundary

Phase 10 ships:

- **LBL-01..03** — Circuit-label autocomplete on connectors. Sources: all project signal-name fields from Device + Console + Amp + 3 Processor models. Project-scoped via existing IDOR pattern. Free-text override always accepted.
- **EXP-01** — One-click PNG export of the current diagram via the already-vendored `html-to-image` (Phase 7).
- **SHP-10** — Processor smart shape (covers `SystemProcessor`, `P1Processor`, `GalaxyProcessor`).
- **SHP-11** — Amp smart shape (covers `Amp` model at `planner/models.py:1658`).

**Out of phase scope** — these are explicitly NOT in Phase 10:
- Per-shape labeled ports (PORT-01..06) → Phase 11
- Resizable shapes (SHP-RESIZE-01..03) → Phase 11
- Boundary draw lines (DRAW-01..04) → Phase 12
- Text annotations (TXT-01..03) → Phase 12
- Migration on `SignalFlowDiagram` model → none expected; state stays in `canvas_state` JSONField

</domain>

<decisions>
## Implementation Decisions

### A. Autocomplete behavior

- **D-01:** Trigger threshold — autocomplete dropdown appears after **1 character typed** with a **200 ms debounce**. Matches existing project autocomplete conventions.
- **D-02:** Result display format — each suggestion shows `<label text> — <source tag>` (e.g., `FOH Lead — Device Input`). Source tag prevents ambiguity when the same label exists across modules.
- **D-03:** Result count + sort — show at most **8 results, alphabetical by label**. (Not relevance-based; not by source — keeps the algorithm simple and predictable.)
- **D-04:** Wiring — Phase 10 wires the autocomplete to the connector circuit-label field only. The same endpoint + JS widget will be reused by Phase 11's PORT-03 custom-label dropdown without re-implementation.
- **D-05:** `SystemProcessor` autocomplete source — **research output required.** Unlike `P1Processor` (has `P1Input`/`P1Output` companion models) and `GalaxyProcessor` (has `GalaxyInput`/`GalaxyOutput`), `SystemProcessor` (`planner/models.py:1898`) has no `*Input`/`*Output` companion model. The phase-researcher must investigate which field on `SystemProcessor` itself (or a related model) is the canonical channel/label field, OR conclude that the model lacks one and document the exclusion with a code comment. Default behavior pending research: exclude `SystemProcessor` from autocomplete; only `P1Processor` and `GalaxyProcessor` I/O records contribute.

### B. PNG Export behavior

- **D-06:** Filename — `<diagram-slug>-<YYYYMMDD>.png` (e.g., `foh-festival-2026-2026-05-22.png`). Falls back to `signal-flow-<YYYYMMDD>.png` if the diagram's name is empty or only whitespace. Slug rules match the existing `slugify()` conventions used elsewhere in `planner/views.py`.
- **D-07:** Resolution — **2x device pixel ratio** (`html-to-image` `pixelRatio: 2`). Retina-quality for printed riders and Slack screenshots; modest file-size growth vs 1x.
- **D-08:** Canvas-as-seen — the PNG captures exactly what the engineer sees on the canvas, **including any ghosted orphan shapes** (Phase 9 dashed-grey ghosts come through `html-to-image` as rendered). Excludes the JointJS chrome (toolbar, sidebar, inspector, conflict banner) — only the `#sfd-paper` canvas region. No "clean export" mode.
- **D-09:** Background — white (`#ffffff`), per EXP-01 requirement. Engineers print to riders and embed in Slack; white maximizes legibility.

### C. Smart shape sidebar layout

- **D-10:** Processor presentation — **one sidebar tile labeled "Processor"**. The picker modal shows a combined list across all 3 Django models (`SystemProcessor` + `P1Processor` + `GalaxyProcessor`) with a model-type badge next to each entry: `Lake LM-44 (P1)`, `BSS BLU-DAN (System)`, etc. Engineers pick from one list; on selection, the GFK `content_type_id` resolves to the correct table.
- **D-11:** Sidebar ordering — **signal-flow order**: `Console → Device → Processor → Amp → SpeakerArray → CommBeltPack → Generic` (7 tiles total).
- **D-12:** Visual differentiation — Processor and Amp shapes each get their own SVG glyph + color accent, continuing the Phase 8 pattern (Console gets the mixer-fader icon, Device gets a rack-strip, etc.). Specific glyph designs are a UI-spec deliverable but the pattern is locked: never reuse the same icon across two shape types.

### D. Toolbar / Inspector integration

- **D-13:** Export button placement — **new right-side toolbar button group** containing just the "Export PNG" button initially. Group scaffold (not just a single button) so future PDF / SVG export buttons can land in the same group in v2.4+ without rearranging the toolbar.
- **D-14:** Inspector touch — no new inspector controls in Phase 10. Autocomplete wires into the existing connector inspector circuit-label `<input>` element from Phase 8 (the inspector DOM doesn't change; only the JS attached to the input grows). Phase 11 will add new inspector controls for ports.

### Claude's Discretion

- Exact SVG glyph designs for Processor + Amp shape icons (D-12 establishes the pattern; design is implementation work).
- Specific HTML structure of the autocomplete dropdown (popover positioning, ARIA roles, focus management) — follow accessible-combobox conventions.
- Internal naming of the new view function for autocomplete (`signal_flow_autocomplete` was claimed by Phase 8 for equipment-picker queries; planner may use `signal_flow_label_autocomplete` or extend the existing view with a `?source=labels` parameter — planner picks the cleaner option).
- Whether the PNG export goes through a transient `<a download>` click or `URL.createObjectURL` + revoke. Both work; planner picks based on browser-compat needs.

</decisions>

<specifics>
## Specific Ideas

- The PNG export is **product-defining**: engineers paste these into Slack the moment a diagram is ready. The 2x pixel ratio + white background is non-negotiable for readability when scaled down to thumbnail size in chat.
- Autocomplete source-tag pattern (D-02) is borrowed from VS Code's IntelliSense: showing the origin of each suggestion (`From: Module X`) is more useful than label-only when one label may exist in multiple places.
- One-tile Processor (D-10) matches how the engineer thinks: "I need a processor in this rack" — they pick the brand at the equipment-picker step, not the canvas-tile step.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope
- `.planning/REQUIREMENTS.md` §LBL, §EXP, §SHP — locks requirement IDs LBL-01..03, EXP-01, SHP-10, SHP-11
- `.planning/ROADMAP.md` "Phase 10" entry — defines goal and dependency on v2.2

### v2.2 patterns (extend, don't reinvent)
- `.planning/milestones/v2.2-ROADMAP.md` — Phase 8 equipment-picker pattern (`signal_flow_autocomplete` per-type dispatch with `prediction__project` IDOR special-case for SpeakerArray); Phase 9 autosave conventions
- `planner/views.py` — `signal_flow_autocomplete` (Phase 8 ancestor for the new label autocomplete view), `_enrich_nodes` (Phase 9 — Processor/Amp need to be added to the enrichment ContentType list for orphan rendering to work on the new shape types)
- `planner/static/planner/js/signal_flow_editor.js` — `joint.shapes.showstack.*` namespace (Phase 8 — add `Processor` + `Amp` classes alongside existing 5); equipment picker modal flow; autosave IIFE for new toolbar button binding
- `planner/static/planner/css/signal_flow.css` — Sections 1–11 already exist (Phase 8 + Phase 9); Phase 10 appends Section 12 (autocomplete dropdown) and Section 13 (export button group) per the established "append-at-end" convention

### Model fields
- `planner/models.py:1516` — `DeviceInput.signal_name`
- `planner/models.py:1549` — `DeviceOutput.signal_name`
- `planner/models.py:894` — `ConsoleInput.source`
- `planner/models.py:974` — `ConsoleAuxOutput.name`
- `planner/models.py:1658` — `Amp` model (SHP-11 GFK target)
- `planner/models.py:1841` — `AmpChannel` (label field for autocomplete — research required to confirm canonical field name)
- `planner/models.py:1898` — `SystemProcessor` (SHP-10 GFK target option 1) — **autocomplete source is research-output per D-05**
- `planner/models.py:1939` — `P1Processor` (SHP-10 GFK target option 2)
- `planner/models.py:2028` — `P1Input.signal_name`
- `planner/models.py:2067` — `P1Output.signal_name`
- `planner/models.py:2097` — `GalaxyProcessor` (SHP-10 GFK target option 3)
- `planner/models.py:2128` — `GalaxyInput.signal_name`
- `planner/models.py:2163` — `GalaxyOutput.signal_name`

### Vendored libraries (already in `planner/static/planner/js/vendor/` from Phase 7)
- `joint.min.js` 4.2.4 — JointJS core (MPL-2.0)
- `html-to-image.min.js` 1.11.11 — PNG export library (MIT)
- `THIRD_PARTY_LICENSES.txt` — license attribution

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`signal_flow_autocomplete` view** (Phase 8, `planner/views.py`) — already handles project-scoped per-type equipment dispatch with the `prediction__project` SpeakerArray special-case. Phase 10's label-autocomplete endpoint extends this pattern — either as a new sibling view (`signal_flow_label_autocomplete`) or as a `?source=labels` mode on the existing one (planner picks the cleaner option).
- **`joint.shapes.showstack` namespace** (Phase 8, `signal_flow_editor.js`) — existing 5 shape classes (Console, Device, SpeakerArray, CommBeltPack, Generic) all derive from a common pattern with `attrs`, ports (4 generic), and the equipment-picker modal flow. Processor + Amp follow the same pattern; the only novelty is Processor's multi-model-type picker.
- **Equipment picker modal** (`planner/templates/planner/signal_flow/_equipment_picker_modal.html`, Phase 8) — generic across all shape types via `data-shape-type` attribute. Processor picker reuses the same modal; the view-layer dispatch resolves the type-aware query (3 models for Processor, 1 model for Amp).
- **`_enrich_nodes()`** (Phase 9, `planner/views.py:7529`) — must be extended with `Processor` and `Amp` ContentType lookups so orphan rendering works on the new shape types automatically once the canvas state contains them.
- **Autosave IIFE** (`signal_flow_editor.js`) — new toolbar export button + autocomplete event handlers attach inside the same IIFE; closure-scoped state (`conflicted`, `graph`, etc.) is available without exports.

### Established Patterns

- **Inspector field listener convention** (Phase 9 PASS D) — any inspector field that mutates a cell calls `scheduleAutosave()` after the mutation. Autocomplete-driven label changes follow this rule unchanged.
- **Smart shape registration** — each shape class is registered on the `joint.shapes.showstack` namespace and listed in the sidebar `data-shape-type` attribute. Adding Processor + Amp is two-line additions in two places (registration + sidebar HTML).
- **CSS section convention** — `signal_flow.css` is organized as numbered sections; new functionality appends a new section rather than editing existing ones. Phase 10 adds Section 12 (autocomplete) + Section 13 (export button group).
- **Test pattern** — `planner/tests/test_signal_flow_phase9.py` is the latest test file template. Phase 10 tests live in a new `test_signal_flow_phase10.py` if the surface is large (autocomplete + export are both testable), or extend phase9.py if small.

### Integration Points

- **`signal_flow_state` GET response** (Phase 9 — `_enrich_nodes` runs here) — must enrich Processor and Amp cells with `data.label` + `data.isOrphan`. Without this, orphan rendering and label propagation (SHP-06/07 from v2.2) silently break for the new shape types.
- **`signal_flow_autosave` POST IDOR validation** (Phase 9 — line 7702 was just refactored for the WR-04 allowlist fix) — the explicit allowlist `('Console', 'Device', 'CommBeltPack')` must be extended to `('Console', 'Device', 'CommBeltPack', 'Amp', 'SystemProcessor', 'P1Processor', 'GalaxyProcessor')` to avoid 422 rejections when a Processor or Amp cell is saved. **Forgetting this is the most likely silent bug in Phase 10.**
- **Toolbar HTML** (`planner/templates/planner/signal_flow/editor.html`) — new right-side button group inserted before `#sfd-canvas-container` (similar pattern to how the Phase 9 conflict banner was inserted).
- **Sidebar shape picker HTML** (`editor.html`) — 5 existing tiles get 2 new siblings; the tile order in HTML drives the visual order per D-11.

</code_context>

<deferred>
## Deferred Ideas

Captured during analysis but explicitly out of Phase 10 scope:

- **"Clean mode" PNG export** (skip orphans / hide chrome) — rejected per D-08; defer to v2.4 if engineers ask for it.
- **PDF export** — separate format, separate library research. PDF-01 in REQUIREMENTS.md future list.
- **SVG export** — explicitly excluded at the project level (creates source-of-truth-drift).
- **Three sidebar tiles for Processor brands** — rejected per D-10; defer to v2.4 only if engineers report the unified picker is confusing.
- **Manual port positioning** (PORT-MANUAL-01) — already deferred at the milestone level; not Phase 10 concern.
- **Per-keystroke autocomplete on PORT-03** — Phase 11 concern, but the Phase 10 endpoint will support it without changes (D-04 locked the reuse).

</deferred>

---

*Phase: 10-autocomplete-png-export-new-shapes*
