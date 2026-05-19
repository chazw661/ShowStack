# Project Research Summary

**Project:** ShowStack v2.2 Signal Flow Diagrammer
**Domain:** Vanilla-JS diagramming module added to existing Django 5.x SaaS (additive planner module)
**Researched:** 2026-05-19
**Confidence:** HIGH

---

## Executive Summary

The Signal Flow Diagrammer is a specialized diagramming tool built inside the existing `planner` Django app. The implementation approach is well-defined: `@joint/core` 4.2.4 (MPL-2.0) is the canvas engine — dependency-free since v4.0, vendored as a pre-built UMD bundle alongside the existing `Sortable.min.js` precedent. PNG export uses `html-to-image` 1.11.11 (MIT) rather than JointJS+ `format.toPNG()` which is restricted to the paid tier and unavailable in `@joint/core`. Diagram state is stored as a single `JSONField` blob on a new `SignalFlowDiagram` model using `graph.toJSON()` as the serialization format. No new Python dependencies are required.

The core competitive differentiation over Visio and Lucidchart is ShowStack's existing data: smart shapes link to live `Console`, `Device`, `SpeakerArray`, and `CommBeltPack` records via `GenericForeignKey` inside the JSON blob, connector labels autocomplete from `DeviceInput.signal_name` and `DeviceOutput.signal_name` scoped to the current project, and signal-type connector variants (Analog / AES / Dante / MADI / Intercom) are first-class properties rather than manual style workarounds. Auto-layout of nodes is intentionally excluded — live-audio signal-flow diagrams encode physical topology (stage left, FOH center, monitor world stage right) that algorithmic reordering destroys.

The highest-risk implementation areas are `cellNamespace` registration before `graph.fromJSON()` (silent blank canvas on load if missed), the autosave race-condition and IDOR surface (cross-project diagram writes are possible unless every view chains `.filter(project=request.current_project)`), and PNG export correctness (cross-origin font resources taint the canvas and produce a SecurityError). All three are preventable with patterns that are either already established in the codebase or documented precisely in the pitfalls research.

---

## Key Findings

### Recommended Stack

No additions to `requirements.txt`. The only new files are two vendored JS bundles (`joint.min.js`, `html-to-image.min.js`) placed in `planner/static/planner/js/vendor/` alongside `Sortable.min.js`, and a `THIRD_PARTY_LICENSES.txt` at project root. All server-side needs are met by built-in Django primitives: `models.JSONField` for the canvas blob, `django.contrib.contenttypes` for GFK linking (already in `INSTALLED_APPS`), and `JsonResponse` views for autosave.

**CORRECTION TO CARRY INTO ALL DOWNSTREAM DOCS:** `@joint/core` is licensed **MPL-2.0**, not MIT. PROJECT.md and STATE.md currently state "MIT" — this must be corrected before any phase plan or requirements doc is written. Vendoring the unmodified `joint.min.js` is fully compliant with MPL-2.0 (file-level copyleft applies only to modifications of the library source itself). A `THIRD_PARTY_LICENSES.txt` at project root is required. Do not patch `joint.min.js` directly; use the public JointJS API for any workarounds.

**Core technologies:**
- `@joint/core` 4.2.4: diagram canvas (nodes, edges, drag-drop, serialization) — dependency-free UMD bundle, no CSS required, `joint` global on window; **MPL-2.0** (not MIT)
- `html-to-image` 1.11.11: PNG export (SVG to canvas to data URL) — maintained fork of dom-to-image; MIT; `format.toPNG()` is JointJS+ (paid) only and must not be used
- `models.JSONField`: canvas state persistence as PostgreSQL `jsonb` — built into Django 3.1+, no third-party dep
- `django.contrib.contenttypes` GenericForeignKey: equipment record linking — already installed, zero migration cost to use

**What NOT to add:** React/Vue/Svelte, any build toolchain (webpack/vite), `dom-to-image` (unmaintained), `django-jsonfield` (redundant), JointJS+ (`@joint/plus`), Celery/Redis, `django-csp`.

### Expected Features

Feature research was grounded in direct codebase inspection and live-audio production documentation practice. Engineers currently rebuild five recurring diagram types (full system block, Dante network, intercom architecture, amp/PA zone, broadcast output map) from scratch in Visio or Lucidchart on every show because no tool knows their gear list. ShowStack holds the underlying data for all five types.

**Must have for v2.2 (table stakes — missing any makes the tool feel broken):**
- Drag-and-drop canvas with smart shapes: Console / Device / SpeakerArray / CommBeltPack / Generic
- ShowStack record linking with label propagation on rename + soft-fail render with `saved_label` on delete
- Orthogonal connectors with five line-style variants: Analog / AES / Dante / MADI / Intercom
- Connector direction property (source-to-target / bidirectional) for intercom partyline notation
- Circuit-label autocomplete from `DeviceInput.signal_name`, `DeviceOutput.signal_name`, `ConsoleInput.source` scoped to current project
- Undo / redo (JointJS CommandManager — must be wired before first graph mutation)
- Multi-select and rubber-band selection
- Keyboard delete (Delete / Backspace)
- Snap-to-grid
- Port-to-port connector snapping (connectors originate from and terminate at defined ports, not arbitrary shape boundaries)
- Midpoint waypoints (vertex drag on connectors)
- Zoom in / out / zoom-to-fit
- JSON autosave (debounced 2-3 s, `keepalive: true` on page unload)
- PNG export with white background via `html-to-image`
- Many diagrams per project (list page, name, delete)

**Should have — competitive differentiators in v2.2:**
- Circuit-label autocomplete is the primary differentiator (no other diagrammer knows this engineer's patch)
- Signal-type connector vocabulary as first-class property (not manual style overrides)
- Smart shapes that update labels from live equipment records (rename propagation)

**Defer to v2.3:**
- PDF export (ReportLab pattern proven; trigger: engineers report PNG insufficient for printed show documentation)
- IP address annotation as secondary node label (data already in `Console.primary_ip_address`, `Device.primary_ip_address`)
- COMM Config auto-generate intercom diagram (trigger: FSII port swap fix ships and COMM Config is stable)
- PA Cable Schedule visualization overlay (trigger: beta testers report manual duplication)
- Group / ungroup nodes by location
- Alignment guides (smart snap lines)
- Mobile `/m/` viewer (JointJS supports mobile Chrome/Safari but requires PaperScroller or custom pointer event handling)
- Copy / paste nodes (only if JointJS Clipboard is in core; defer if JointJS+ only)

**Anti-features — do not build:**
- Auto-layout that reorders nodes by hierarchy: destroys physical topology; most-cited Lucidchart complaint from AV engineers
- Real-time multi-user collaborative editing: last-write-wins autosave is correct for solo A1
- SVG export: creates a secondary copy outside ShowStack, defeating source-of-truth model
- Pictographic rack-unit SVG faceplates per model: maintenance burden; label carries semantic weight, not icon

### Architecture Approach

The diagrammer is a fully additive module inside `planner` — no new app, no new Python dependencies, no deviation from established conventions. The canvas state is a single `JSONField` blob (no normalized `DiagramNode`/`DiagramEdge` tables). GFK references (`content_type_id`, `object_id`) live inside the JSON nodes; equipment is resolved server-side on the `state/` endpoint via `_enrich_nodes()`. The editor page uses an HTML shell + separate `GET .../state/` JSON endpoint (not inline JSON), enabling the v2.3 mobile viewer to consume the same endpoint.

**Major components:**
1. `SignalFlowDiagram` model — `project FK`, `name`, `canvas_state JSONField`, `viewport JSONField`, `version IntegerField`, `created_at`, `updated_at`
2. 9 view functions in `planner/views.py` — list, create, editor shell, state (GET JSON), autosave (POST), rename, delete, autocomplete, export PNG
3. `signal_flow_editor.js` — JointJS graph+paper init, custom shape definitions with `cellNamespace`, autosave debounce + dirty flag + in-flight guard, PNG export via `html-to-image`, `readOnly` flag guard for future mobile viewer
4. `list.html` / `editor.html` extending `admin/base_site.html`
5. `SignalFlowDiagramAdmin` on `showstack_admin_site` with `always_hidden` + `order_map: 52` in `admin_ordering.py`

**Build order:** Layer 1 (model + migration + admin) → Layer 2 (CRUD views + URLs + list template) → Layer 3 (editor HTML shell + vendor JS) → Layer 4 (JointJS canvas init) → Layers 5+6 in parallel (smart shapes / connector types) → Layer 7 (autocomplete) → Layer 8 (autosave + orphan rendering) → Layer 9 (PNG export)

### Critical Pitfalls

1. **`cellNamespace` not passed to `Graph` constructor before `fromJSON()`** — JointJS v4 removed the implicit `joint.shapes` global lookup. Symptom: silent blank canvas on reload. Prevention: smoke-test save + reload with each shape type before closing the canvas phase.

2. **Autosave race condition and page-unload data loss** — Three concurrent-write hazards: simultaneous debounced + manual save, two tabs on the same diagram, `fetch` cancelled on tab close. Prevention: `version IntegerField` on model; `select_for_update()` + `atomic()` with `WHERE version=expected_version` (HTTP 409 on mismatch); `saveInProgress` + `pendingSave` JS flags; `fetch(..., { keepalive: true })` on `visibilitychange`/`pagehide` — NOT `navigator.sendBeacon` (64 KB limit silently drops large diagram JSON).

3. **IDOR on autosave endpoint + equipment reference validation** — Prevention: `.filter(project=request.current_project)` in every diagram lookup (replicate `_get_track_for_request` pattern); walk canvas JSON on every save and reject with HTTP 422 if any `object_id`'s project != current project.

4. **PNG export: cross-origin fonts taint the canvas** — Prevention: system fonts only on shape labels; native JointJS SVG `<text>` elements for all node labels (no `<foreignObject>`); `useComputedStyles: true` in the export call.

5. **SVG-coordinate vs. page-coordinate confusion after scroll or zoom** — Prevention: always use `paper.clientToLocalPoint({ x: event.clientX, y: event.clientY })` for all pointer event conversions.

6. **MPL-2.0 license compliance** — `joint.min.js` must be vendored unmodified; `THIRD_PARTY_LICENSES.txt` required; use public JointJS API for any workarounds rather than patching the source.

---

## Implications for Roadmap

### Phase 1: Foundation — Model, Migration, Admin Wiring
**Rationale:** Model exists before anything else can be built. `version`, `viewport`, and `saved_label` decisions are cheapest here. License correction happens before any code ships.
**Delivers:** `SignalFlowDiagram` model with `canvas_state JSONField`, `viewport JSONField`, `version IntegerField`; migration; `SignalFlowDiagramAdmin` on `showstack_admin_site`; `admin_ordering.py` update; `THIRD_PARTY_LICENSES.txt`; correction of "MIT" to "MPL-2.0" in PROJECT.md and STATE.md.

### Phase 2: CRUD Views, URL Patterns, and List Page
**Rationale:** List/create/rename/delete and all 9 URL patterns must exist before the editor shell can link to a diagram.
**Delivers:** All 9 view stubs + URL patterns; `list.html`; dashboard link; autocomplete stub for Phase 7 testing.

### Phase 3: Editor HTML Shell and Vendor JS
**Rationale:** Vendor files must be committed and `collectstatic` verified before any JointJS code runs.
**Delivers:** `signal_flow_editor` view; `editor.html`; `joint.min.js` + `html-to-image.min.js` in `vendor/`; stub JS; white background on paper container div.
**Gate:** `collectstatic --noinput` passes locally.

### Phase 4: JointJS Canvas Initialization
**Rationale:** `cellNamespace`, coordinate system, and state-separation discipline must be structural foundations before shapes are defined.
**Delivers:** `graph` + `paper` init; `graph.fromJSON()` on `STATE_URL`; blank canvas + pan/zoom; `viewport` restore; `readOnly` guard structure.
**Gate:** Scroll 300px down, drag-drop a shape — it must land under the cursor.

### Phase 5: Smart Shapes and Connector Types (parallel workstreams)
**Rationale:** Shapes and connectors have no mutual dependency. Both gate autosave (Phase 6) and autocomplete (Phase 7).
**Delivers (shapes):** Five shape classes registered in `cellNamespace`; shape picker sidebar; equipment picker modal; node payload with `content_type_id`, `object_id`, `equipment_type`, `label_override`, `port_overrides`.
**Delivers (connectors):** Link draw tool; five `signal_type` variants; direction property; port-to-port snapping; midpoint waypoints.
**Research flag:** Verify JointJS `Clipboard` and `CommandManager` availability in `@joint/core` 4.2.4 vs JointJS+ before finalizing copy/paste and undo/redo plans.

### Phase 6: Autosave and Orphan Rendering
**Rationale:** Race condition, IDOR, and CSRF tests require real canvas content to be meaningful.
**Delivers:** 2.5 s debounced POST with guards; `version` token; `keepalive: true` on unload; `_enrich_nodes()` for orphan rendering; save status indicator; error banner.

### Phase 7: Circuit-Label Autocomplete
**Rationale:** Requires connectors (Phase 5).
**Delivers:** Autocomplete endpoint querying all signal-name fields filtered to `request.current_project`; JS autocomplete widget on connector label field.

### Phase 8: PNG Export
**Rationale:** Requires a fully populated canvas.
**Delivers:** "Export PNG" button; `htmlToImage.toPng(paperEl)` with white background; correct rendering after scroll.

### Research Flags
**Phases needing deeper research during planning:**
- **Phase 5:** Verify JointJS `Clipboard` and `CommandManager` availability in `@joint/core` 4.2.4 vs JointJS+.

**Phases with standard patterns (no research-phase needed):** 1, 2, 3, 4, 6, 7, 8.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | `@joint/core` 4.2.4 npm + MPL-2.0 verified; `html-to-image` CDN confirmed; no new Python deps |
| Features | HIGH (practice), MEDIUM (formal standards) | Engineer workflow verified; connector line-style conventions de facto |
| Architecture | HIGH | Direct codebase inspection; multitrack module is a proven precedent |
| Pitfalls | HIGH (JointJS, Django/permission), MEDIUM (PNG internals, Railway limits) | JointJS docs + ShowStack codebase verified |

**Overall confidence:** HIGH

### Gaps to Address
- JointJS `Clipboard` and `CommandManager` in `@joint/core` 4.2.4 — resolve during Phase 5 planning.
- `navigator.sendBeacon` 64 KB limit at Railway — verify Railway does not also block large `keepalive` requests.
- Connector line-style conventions — validate with beta tester feedback before v2.3 PDF export locks the visual language.

---

## Sources

### Primary (HIGH confidence)
- `@joint/core` on npm — version 4.2.4, MPL-2.0 license
- JointJS v4.0 announcement (dependency-free)
- JointJS v4.2 JavaScript integration docs (UMD)
- JointJS Raster export docs (confirms `format.toPNG` is JointJS+ only)
- JointJS license page (MPL-2.0)
- Mozilla MPL-2.0 FAQ
- `html-to-image` on npm (v1.11.11, MIT)
- Direct codebase inspection: `planner/models.py`, `planner/views.py`, `planner/urls.py`, `planner/admin_ordering.py`, `planner/middleware.py` (2026-05-19)
- JointJS GitHub issues #964, #1502; discussions #2235, #2566
- MDN Navigator.sendBeacon (64 KB limit)
- ShowStack `planner/views.py:6328` — `_get_track_for_request` IDOR-safe pattern
- ShowStack `templates/planner/mic_tracker.html:1212` — `getCsrfToken()` pattern

### Secondary (MEDIUM confidence)
- ProSoundWeb community threads — engineer diagramming workflow
- AVIXA AV drawing symbols (architectural floor-plan, not block-diagram connectors)
- pganalyze — JSONB TOAST performance

### Tertiary (LOW confidence)
- Connector line-style conventions — de facto, not formally standardized

---

*Research completed: 2026-05-19*
*Ready for roadmap: yes*
