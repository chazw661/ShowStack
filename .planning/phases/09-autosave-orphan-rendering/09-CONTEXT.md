# Phase 9: Autosave & Orphan Rendering — Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 9 makes the Signal Flow Diagrammer save itself and stay coherent with the rest of ShowStack:

- Replace the Phase 8 manual `Save` button with idle-debounced autosave (≤2.5 s after last edit), retaining the three-state `Saved / Saving… / Failed — retry` status indicator
- Add HTTP 409 last-write-wins conflict detection via `If-Match: <version>` header + atomic version-checked UPDATE, surfaced as a non-dismissable full-width banner that locks the canvas until reload
- Add `keepalive: true` fetch on `visibilitychange` (hidden) AND `pagehide` to flush a dirty buffer before unload (no `sendBeacon` — 64 KB cap drops 100 KB diagrams)
- Add server-side `_enrich_nodes()` that runs on the state GET endpoint to (a) refresh the displayed label from the live equipment record (SHP-06) and (b) flag missing equipment refs as orphans (SHP-07)
- Render orphans in the editor with a dashed grey border + 50% opacity + faded fill, exposing a `Re-link equipment` / `Delete shape` affordance through the existing right-side inspector

Phase 9 does NOT cover: circuit-label autocomplete behavior (LBL-01/02/03 → Phase 10), PNG export (EXP-01 → Phase 10), per-channel ports, copy/paste, mobile viewer, IP-address annotations (all v2.3+).

The `SignalFlowDiagram` model schema (`canvas_state`, `viewport`, `version` IntegerField) is unchanged. No new migration. No new Python dependencies.

</domain>

<decisions>
## Implementation Decisions

### Autosave Triggers & Debounce
- **D-01:** Listen to **structural + label events only** — `add`, `remove`, `change:source`/`change:target` (connection completion), node `change:position` debounced on `pointerup` only (not per-pixel during drag), and inspector `change:prop` events for signal-type / direction / circuit-label. Mid-drag position events do **not** trigger autosave. Mitigates PITFALLS.md §6 "autosave flooding".
- **D-02:** **1500 ms** trailing debounce floor. Comfortably under the 2.5 s DGM-06 ceiling and matches PITFALLS.md §6 recommendation. Implemented via a single `setTimeout` reset on every qualifying event + a `diagramDirty` boolean. Debounce only fires the POST if `diagramDirty === true`; the flag clears on the 200 response.
- **D-03:** **Remove the Phase 8 manual `Save` button entirely**; keep the `#sfd-save-status` span and let it carry the three states. When the state is `Failed — retry`, the span itself becomes clickable to force a retry of the last pending save. No Cmd/Ctrl+S shortcut in Phase 9 (deferred — not in spec).
- **D-04:** **Three status states, exact copy:** `All changes saved.` / `Saving…` / `Save failed — retry`. The `Failed` state persists until the next successful save (clearing only on a 200 response, not on subsequent edits). Matches DGM-06 wording.

### Conflict Detection & 409 Banner
- **D-05:** **Transport: `If-Match: <version>` request header** on every full canvas-state autosave POST (not on `?viewport_only=1` writes — those remain last-write-wins per Phase 8). Body carries `canvas_state` + `viewport` only. Missing/mismatched header → 409.
- **D-06:** **Server detection: `transaction.atomic()` + version-pinned UPDATE.** Replace the current unconditional `diagram.save()` with `SignalFlowDiagram.objects.filter(id=diagram_id, version=loaded_version).update(canvas_state=..., viewport=..., version=F('version')+1, updated_at=now())` inside `transaction.atomic()`. If `rowcount == 0`, return `JsonResponse({'error': 'version_conflict'}, status=409)`. Avoids the row-lock duration of `select_for_update()`. Mitigates PITFALLS.md §3.
- **D-07:** **409 banner UX: full-width red bar pinned below `#sfd-toolbar`**, above `#sfd-paper`. Non-dismissable (no `×` button). Exact copy locked by DGM-07: `Diagram was modified elsewhere — reload to see latest.` Single `Reload` button on the right end that calls `window.location.reload()`.
- **D-08:** **Conflict lockout:** When 409 fires, set a `conflicted` flag in the JS controller. Cancel any pending debounce. Set `pointer-events: none` on `#sfd-paper` and ignore canvas keyboard shortcuts (Ctrl+Z/Y, Delete/Backspace). Edits attempted between failure and reload are lost regardless — surfacing that via the lockout prevents false expectations. Toolbar buttons (zoom/pan/snap) remain active for safety/inspection.

### Keepalive on Unload
- **D-09:** **Listen to BOTH `visibilitychange` (when `document.visibilityState === 'hidden'`) AND `pagehide`** with an idempotent flush function. Covers tab-hide, tab-close, navigation, and iOS Safari quirks. **Do not** listen to `beforeunload` (browser cancels the fetch — PITFALLS.md §3).
- **D-10:** **Flush only when dirty.** If `diagramDirty === false`, no fetch. If dirty, cancel any pending debounce timer, build the standard autosave payload (`canvas_state` + `viewport` + `If-Match`), and `fetch(autosaveUrl, { method: 'POST', body, headers, keepalive: true })`. **No `navigator.sendBeacon`** — 64 KB cap silently drops typical diagrams (PITFALLS.md §6).
- **D-11:** **Skip the flush if a save is already in flight or if the conflict banner is showing.** The in-flight save's success will mark dirty=false; the banner means further saves are locked. Skipping avoids self-collision 409s on the next tab open.

### Server-Side Enrichment (`_enrich_nodes()`)
- **D-12:** **Location: helper function in `planner/views.py`** alongside `_get_diagram_for_request` and `_signal_flow_viewer_block`. Signature: `_enrich_nodes(canvas_state: dict, project) -> dict`. Returns the canvas_state with cells mutated in place (deep-copy first). Runs on **GET state path only** (`signal_flow_state` view) — the autosave POST keeps the raw blob the client sent (still IDOR-validated as today). Save responses do **not** re-enrich; the client reloads cells from the GET response only when it explicitly re-fetches.
- **D-13:** **Bulk-fetch strategy.** Walk `canvas_state.cells`, group `(contentTypeId, objectId)` pairs by `content_type_id`, then per content type perform a single `Model.objects.filter(id__in=ids, <project-scope>).values('id', 'name')` query (SpeakerArray scopes via `prediction__project`, others via `project`; same predicate as the current save-time IDOR walk in `views.py:7587-7620`). Result is a `(ct_id, obj_id) → name` dict. Walk cells a second time, writing the resolved name into `cell.attrs.label.text` and refreshing `cell.showstack.savedLabel` for live records; setting `cell.showstack.isOrphan = true` and leaving `savedLabel` untouched for missing records.
- **D-14:** **Orphan flag schema:** `cell.showstack.isOrphan = true` is the canonical orphan marker. `cell.showstack.savedLabel` is preserved as the last-known name (already snapshotted at pick time per Phase 8 `signal_flow_editor.js:500`). `contentTypeId` and `objectId` remain on the cell (not nulled) so a future "restore equipment" flow could in principle re-link — though re-linking via the inspector picker is the only Phase 9 affordance. Live cells get `isOrphan = false` (explicitly written, not just absent — keeps the property stable across saves).

### Orphan Visual & Re-link UX
- **D-15:** **Ghost visual recipe** applied client-side on render when `cell.showstack.isOrphan === true`:
  | Property | Value |
  |----------|-------|
  | Body stroke | `#888` |
  | Body `stroke-dasharray` | `4 3` |
  | Body fill-opacity | `0.4` |
  | Label color | `#555` |
  | Connectors attached to ghost | `opacity: 0.5` |

  Geometry stays the shape-type default (Console = wide rect, etc., per Phase 8 D-01) so the engineer still recognizes the role.
- **D-16:** **Re-link affordance: inspector reopens picker.** Selecting an orphan node shows the existing right-side inspector panel with a `Re-link equipment` button + a `Delete shape` button. `Re-link` opens the existing equipment picker modal (`openEquipmentPicker` already exposed on `window.__sfd`) scoped to the shape's type. On pick, write the new `(contentTypeId, objectId, savedLabel)` and clear `isOrphan`. Selecting a live node also shows the same inspector (with the same `Re-link equipment` button — useful for swapping a Device assignment without redrawing the shape) plus the existing connector inspector when a connector is selected. Reuses Phase 8 plumbing — no new modal.

### Claude's Discretion
- **Exact CSS values for the 409 banner** (font weight, padding, exact red hex) — match the `error` toast styling from `signal_flow.css` where possible; default to a strong red (≈ `#c0392b` family) on a near-white text foreground.
- **Retry policy on transient failures** (network errors, 500s): single immediate retry on the click of `Save failed — retry`. No automatic background retry loop — autosave naturally re-fires on the next edit, and the engineer can click the status span to force one. Don't build exponential backoff in Phase 9.
- **Logging.** Pipe autosave save-failures through the existing `_signal_flow_logger` (`planner/views.py:7359`) the same way `signal_flow_autosave` already does on `except Exception`. Do not add a new logger.
- **Telemetry / analytics on autosave success rate** — out of scope. Solo-developer codebase; Railway logs are enough.
- **Where the inspector lives when a node is selected** — extend the existing right-side panel from Phase 8 D-05 (`#sfd-inspector`). One panel, mode-switches between connector and node based on selection type. Exact node-inspector layout is Claude's pick.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase + Milestone Scope
- `.planning/ROADMAP.md` §"Phase 9: Autosave & Orphan Rendering" — Goal, success criteria, requirement IDs (DGM-06/07/08, SHP-06/07), DGM-08 overlap note from Phase 7
- `.planning/REQUIREMENTS.md` §"Diagram Management (DGM)" lines 18–20, §"Smart Shapes (SHP)" lines 40–41, §"Constraints" lines 88–94, §"Traceability" lines 105–122 — exact requirement wording + locked phrasing for the 409 banner

### Research (research-grounded basis for v2.2)
- `.planning/research/PITFALLS.md` §3 (race conditions + `If-Match`/atomic version recipe + `keepalive: true` guidance), §4 (project IDOR scope on autosave), §6 (debounce floor + sendBeacon 64 KB cap)
- `.planning/research/STACK.md` — Zero new Python deps constraint; Django 5.x `JSONField` + `transaction.atomic()` are sufficient
- `.planning/research/SUMMARY.md` — Locked technology stack
- `.planning/research/ARCHITECTURE.md` — `SignalFlowDiagram.version` field already wired in Phase 7 schema; build order

### Phase 7 / 8 Foundations (do not re-decide what's locked)
- `.planning/phases/07-foundation-crud-editor-shell/07-RESEARCH.md` — state/autosave URL stubs locked; `version IntegerField` already migrated (0158)
- `.planning/phases/08-canvas-smart-shapes-connectors/08-CONTEXT.md` §"Save trigger for Phase 8 verification" + D-06 (toolbar layout) + D-09 (savedLabel snapshot at pick time) — Phase 8 hand-off baseline
- `.planning/phases/08-canvas-smart-shapes-connectors/08-RESEARCH.md` §19 — manual-Save view stub, Phase 9 expansion path
- `.planning/phases/08-canvas-smart-shapes-connectors/08-PLAN-01.md` (autosave view) and `08-PLAN-06.md` (manual save JS) — current behavior we're extending

### Code-Level References
- `planner/views.py:7359` `_signal_flow_logger` — existing logger; reuse, do not add another
- `planner/views.py:7362-7370` `_signal_flow_viewer_block` — 403 helper used by autosave + autocomplete; reuse on the enriched state GET if viewer enforcement is needed
- `planner/views.py:7374-7388` `_get_diagram_for_request` — IDOR pattern for fetching the diagram; same usage in Phase 9
- `planner/views.py:7528-7542` `signal_flow_state` — current stub; Phase 9 wires `_enrich_nodes()` here on the GET path before returning the response
- `planner/views.py:7545-7637` `signal_flow_autosave` — current view; Phase 9 swaps the `diagram.save()` block for `transaction.atomic() + filter(...).update(...)` and reads the `If-Match` header. The existing IDOR walk at lines 7587–7624 stays
- `planner/views.py:6328` `_get_track_for_request` — IDOR pattern reference
- `planner/static/planner/js/signal_flow_editor.js:492-504` — `savedLabel` snapshot at equipment-pick time (already in place)
- `planner/static/planner/js/signal_flow_editor.js:549-580` — viewport-only debounced POST pattern; mirror its debounce shape for the autosave debounce
- `planner/static/planner/js/signal_flow_editor.js:1306-1435` — current manual Save + status + handoff seams; Phase 9 replaces the click handler with debounced autosave wiring and removes the visible button
- `planner/templates/planner/signal_flow/editor.html:31-56` — `#sfd-toolbar`, `#sfd-save`, `#sfd-save-status` — Phase 9 removes the `#sfd-save` button element, retains `#sfd-save-status`, and adds a new banner element below the toolbar
- `planner/static/planner/css/signal_flow.css` — extend for the new banner styles + orphan ghost styles (no new CSS file)
- `CLAUDE.md` §"Overriding Django admin CSS from JavaScript" — all toolbar/banner inline style writes from JS must use `el.style.setProperty(prop, value, 'important')` (JointJS-managed SVG inside `#sfd-paper` is in its own namespace and is unaffected)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_signal_flow_viewer_block` (planner/views.py:7362) — 403 helper for autosave; reuse on enriched state GET if needed
- `_get_diagram_for_request` (planner/views.py:7374) — IDOR-safe diagram lookup
- `signal_flow_autosave` view (planner/views.py:7545) — already does IDOR + equipment-ref validation; Phase 9 only changes the save block + adds If-Match read
- `signal_flow_state` view (planner/views.py:7528) — already returns `{canvas_state, viewport, version}`; Phase 9 adds the `_enrich_nodes()` call before returning
- `openEquipmentPicker` (signal_flow_editor.js, exposed on `window.__sfd`) — reusable from the orphan re-link affordance, no new modal
- `savedLabel` GFK snapshot (signal_flow_editor.js:500) — already populated on every linked shape at pick time
- Viewport-only debounce pattern (signal_flow_editor.js:549-580) — template for the autosave debounce structure
- `_signal_flow_logger` (planner/views.py:7359) — existing logger for save failures
- `signal_flow.css` — existing stylesheet to extend for banner + ghost styles
- `showToast` helper (signal_flow_editor.js, in helpers handoff) — keep using for transient error toasts; the 409 banner is separate

### Established Patterns
- **Session-based project scoping via `CurrentProjectMiddleware`** — every model lookup uses `request.current_project`, including the bulk-fetch inside `_enrich_nodes()`
- **`SpeakerArray` uses `prediction__project` IDOR scope** (no direct project FK) — already handled in the save-time IDOR walk at `planner/views.py:7609-7612`; mirror in `_enrich_nodes()`
- **JSON `canvas_state` is the single source of truth** — `_enrich_nodes()` mutates a deep-copy of the GET response, never the persisted blob
- **`csrf_exempt` is forbidden on save endpoints** — current view uses `@login_required + @require_POST` correctly; Phase 9 keeps that
- **DOM style writes through admin templates** must use `setProperty('important')` (toolbar + banner + status span); JointJS-managed SVG inside `#sfd-paper` is unaffected
- **`@joint/core` 4.2.4 vendored UMD bundle is MPL-2.0** — do not modify; all autosave wiring lives in `signal_flow_editor.js` only

### Integration Points
- `signal_flow_state` (planner/views.py:7528) — wrap canvas_state through `_enrich_nodes()` before returning
- `signal_flow_autosave` (planner/views.py:7545) — read `If-Match` header → loaded_version int → atomic `filter(version=loaded).update(...)` → check rowcount → 409 or 200; the existing IDOR walk at 7587-7624 stays unchanged
- `#sfd-save-status` span (editor.html:54) — three-state target for autosave indicator + clickable in the `Failed — retry` state
- `#sfd-save` button (editor.html:53) — REMOVE in Phase 9
- New banner element — append a single `<div id="sfd-conflict-banner" hidden>` between `#sfd-toolbar` and `#sfd-canvas-container` in `editor.html`; JS unhides on 409 and locks the canvas
- `signal_flow_editor.js:1306-1435` — replace the manual-save IIFE block with the autosave debounce + dirty-flag controller; keep the `window.__sfd.save` handoff (now points at the force-flush)
- `joint` graph events on `window.__sfd.graph` — wire D-01 listeners on `add`, `remove`, `change:source`, `change:target`, `change:position` (pointerup-gated), and inspector `change:prop`
- `joint` `cell:pointerup` event on `paper` — gate position-change debounce restart on drag-end only
- `_enrich_nodes()` new helper — sits above `signal_flow_state` in `planner/views.py`, returns a deep-copied + mutated canvas_state dict

</code_context>

<specifics>
## Specific Ideas

### Autosave Debounce Recipe
```
on graph event (filtered per D-01):
  diagramDirty = true
  clearTimeout(autosaveTimer)
  autosaveTimer = setTimeout(flush, 1500)

on debounce fire (flush):
  if !diagramDirty: return
  if savingNow:    return       // skip; will re-arm when in-flight resolves
  if conflicted:   return       // banner is showing; locked
  savingNow = true
  set status 'Saving…'
  POST autosaveUrl
    headers: { 'X-CSRFToken': ..., 'If-Match': String(currentVersion) }
    body:    { canvas_state, viewport }
  on 200:
    currentVersion = resp.version
    diagramDirty   = false      // only if no event fired during the request
    savingNow      = false
    set status 'All changes saved.'
  on 409:
    show banner, lock canvas, set conflicted=true
  on other failure:
    savingNow = false
    set status 'Save failed — retry'  // clickable
```

### 409 Conflict Banner Markup
```html
<div id="sfd-conflict-banner" role="alert" hidden>
  <span class="sfd-conflict-msg">Diagram was modified elsewhere — reload to see latest.</span>
  <button type="button" id="sfd-conflict-reload">Reload</button>
</div>
```
Pinned full-width below `#sfd-toolbar`; CSS gives it a red background + white text + bold. Reveal via removing `hidden` (NOT `display:none` on the element directly). Reload handler: `window.location.reload()`.

### Server-Side `_enrich_nodes()` Behavior
- Input: `canvas_state` (dict) + `project` (Project instance)
- Output: a deep-copy with every linked cell mutated:
  - Live ref → `cell.showstack.isOrphan = false`, `cell.showstack.savedLabel = <live name>`, `cell.attrs.label.text = <live name>`
  - Missing ref → `cell.showstack.isOrphan = true`, `savedLabel` and `attrs.label.text` left as-is
  - Non-linked cells (e.g. Generic shape or any connector) untouched
- Single bulk SELECT per content type; SpeakerArray scopes via `prediction__project`; others via `project`
- Never raises on missing content types — treats unknown CT as an orphan

### Orphan Ghost CSS (in signal_flow.css)
```css
[joint-orphan="true"] rect,
[joint-orphan="true"] polygon { stroke: #888 !important; stroke-dasharray: 4 3 !important; fill-opacity: 0.4 !important; }
[joint-orphan="true"] text { fill: #555 !important; }
.joint-link[joint-orphan-attached="true"] { opacity: 0.5 !important; }
```
Client toggles the `joint-orphan` attribute on the cell's root SVG element on render and on re-link.

### Inspector for Node Selection
- Re-link button → `window.__sfd.openEquipmentPicker(node, node.get('type').split('.').pop())` (or equivalent — Phase 8 already exposes this seam)
- Delete button → calls existing delete flow (Phase 8 keyboard-delete handler), preserves undo
- Only shown when selection is a single node; multi-select hides all inspectors

### `If-Match` Header Format
- Plain integer string: `If-Match: 7`
- Missing header → 409 with body `{ "error": "version_required" }`
- Mismatch → 409 with body `{ "error": "version_conflict", "current_version": <int> }`

</specifics>

<deferred>
## Deferred Ideas

### Phase 10
- LBL-01/02/03 (circuit-label autocomplete from `DeviceInput.signal_name` / `DeviceOutput.signal_name` / `ConsoleInput.source` / `ConsoleAuxOutput.name`)
- EXP-01 (PNG export via `html-to-image` with white background)

### v2.3+
- Cmd/Ctrl+S keyboard shortcut to force-flush autosave (not in DGM-06 scope)
- Exponential backoff / auto-retry on transient network failures (manual click-to-retry is the Phase 9 baseline)
- Restore-from-trash flow for deleted equipment (would re-resolve `isOrphan` cells once equipment is undeleted)
- Real-time collaborative editing (explicitly out of scope per REQUIREMENTS.md line 82)
- Conflict-merge UI (out of scope — DGM-07 mandates last-write-wins)
- Telemetry / analytics on autosave success rate
- Save-failed-toast aggregation when offline for a sustained period

### Ideas Surfaced But Not Pursued in Discussion
- `sendBeacon`-based unload flush — explicitly rejected (64 KB cap; PITFALLS.md §6)
- `beforeunload` autosave — explicitly rejected (browser cancels the fetch)
- `select_for_update()` row-lock conflict detection — rejected in favor of the cheaper `UPDATE ... WHERE version=?` recipe
- Server re-enriching the autosave POST response — rejected to keep the save path lean and avoid double the work
- Nulling `contentTypeId`/`objectId` on orphans — rejected to keep the option of a future "restore equipment" flow

</deferred>

---

*Phase: 09-autosave-orphan-rendering*
*Context gathered: 2026-05-21*
