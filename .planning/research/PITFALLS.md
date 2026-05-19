# Domain Pitfalls: ShowStack v2.2 Signal Flow Diagrammer

**Domain:** JointJS-based diagram editor added to a Django 5.x + vanilla-JS server-rendered app
**Researched:** 2026-05-19
**Confidence:** HIGH for JointJS-specific issues (verified against official docs + GitHub tracker), HIGH for Django/permission patterns (verified against existing codebase), MEDIUM for PNG export internals (browser behavior varies), MEDIUM for Railway-specific limits (no published spec)

---

## Critical Pitfalls

Mistakes that cause rewrites, security holes, or data corruption.

---

### Pitfall 1: Custom Shape Types Not Registered in cellNamespace Before fromJSON()

**What goes wrong:** `graph.fromJSON()` looks up each cell's `type` string in the `cellNamespace` object passed to the `Graph` constructor. If ShowStack's custom shapes (`ShowStack.Console`, `ShowStack.Device`, `ShowStack.SpeakerArray`, `ShowStack.CommBeltPack`, `ShowStack.Generic`) are not registered there before the saved JSON is loaded, JointJS v4 throws `"dia.Graph: Could not find cell constructor for type 'ShowStack.Console'"` and the diagram loads blank — with no visual error shown to the user.

**Why it happens:** Developers define shapes at the top of the JS file, create the `Graph` instance, then load JSON from the server — but forget to pass the namespace to `Graph`. In v3 the `joint.shapes` global was the implicit fallback; v4 removed that implicit lookup and requires an explicit `cellNamespace` option.

**How to avoid:**
- Always construct the Graph with an explicit namespace: `new joint.dia.Graph({}, { cellNamespace: { ShowStack: { Console, Device, SpeakerArray, CommBeltPack, Generic }, ...joint.shapes } })`.
- Do not split shape definitions across multiple files loaded in different `<script>` tags unless you can guarantee load order; vendor the shape definitions in the same file or module as the canvas controller.
- Write a smoke-test fixture that saves one of each shape type to JSON, reloads the page, and calls `graph.fromJSON()` — confirm all shapes re-render correctly before shipping.

**Warning signs:** Diagram list page shows diagrams but the canvas is empty on load; no console error because JointJS swallows the type-lookup failure silently in some versions.

**Phase to address:** Canvas controller phase (the phase that introduces custom shape classes). This must be done correctly before the autosave phase connects to a real server endpoint — otherwise autosave will persist JSON that cannot be loaded back.

---

### Pitfall 2: SVG-Coordinate vs. Page-Coordinate Confusion After Scroll or Zoom

**What goes wrong:** JointJS's `Paper` lives inside a DOM container. If the page (or the container itself) is scrolled, the SVG's bounding box is offset from the viewport. Using raw `event.clientX/clientY` or `event.pageX/pageY` directly as JointJS paper coordinates produces elements that are placed far from where the user clicked — the offset equals the scroll position of all ancestor elements.

**Why it happens:** The paper exposes `clientToLocalPoint()` and `pageToLocalPoint()` for this conversion, but developers often bypass them when wiring custom drag-and-drop (e.g., dragging shapes from a sidebar toolbox onto the canvas), and instead compute a bounding-rect offset manually — then only account for the immediate container offset, not the full scroll chain.

**How to avoid:**
- Always use `paper.clientToLocalPoint({ x: event.clientX, y: event.clientY })` to convert any pointer event to paper-local coordinates. Never compute offsets manually.
- When implementing a shape palette / toolbox drag-drop, use `dragover` on the paper's DOM element and `paper.clientToLocalPoint` in the `drop` handler.
- If the paper container is inside a scrollable Django admin-style page (which ShowStack uses), verify coordinate translation by scrolling to the bottom of the page and attempting to place a shape — a common regression that only appears after the page is taller than the viewport.
- Account for `paper.translate()` (pan offset) and `paper.scale()` (zoom) — both affect local coordinates. Use the API methods, not manual math.

**Warning signs:** Elements land in the wrong position when the page is scrolled; drag-drop works at the top of the page but breaks when there is content above the canvas.

**Phase to address:** Canvas controller phase. Add an explicit scroll-regression test before closing the phase: scroll the page down 300px, drop a shape, confirm it appears under the cursor.

---

### Pitfall 3: Autosave Race Condition — Stale Writes and Multi-Tab Corruption

**What goes wrong:** Three concurrent-write scenarios all produce corrupt or lost data:

1. **Debounced autosave + manual save in flight simultaneously:** User edits diagram (debounce timer starts), then immediately clicks "Save". Two POSTs are in flight; whichever arrives second wins. If the debounced save carries older state (fired 0.5s before the manual save was triggered) and arrives second due to network jitter, the manual save is silently overwritten.

2. **Multiple browser tabs on the same diagram:** Tab A and Tab B both load the same `SignalFlowDiagram`. Tab A saves. Tab B (still holding stale JSON) saves 20 seconds later. Tab B's save wins and destroys Tab A's changes — no conflict detection.

3. **Autosave fires during page unload:** `beforeunload` triggers autosave; the request may be cancelled by the browser before it completes. Using `fetch` with no `keepalive: true` results in silent data loss on tab close.

**Why it happens:**
- Autosave implementations typically fire on `graph.on('change', ...)` and debounce at 1–2 seconds. The debounce is relative to the last change, not to the in-flight network request, so overlapping requests are structurally possible.
- Django's default view pattern (`get_object_or_404` → modify → `save()`) performs a blind overwrite with no version check.
- `beforeunload` fetch without `keepalive: true` is cancelled by the browser before the navigator hands off the tab.

**How to avoid:**
- **Version token:** Add a `version` IntegerField (default=1) to `SignalFlowDiagram`. The autosave endpoint receives the version the client last loaded (`expected_version`). In an atomic transaction: `UPDATE ... SET canvas_json=?, version=version+1 WHERE id=? AND version=?`. If no rows are updated, return HTTP 409. The client shows a "diagram changed elsewhere — reload?" banner. Use `select_for_update()` inside an `atomic()` block.
- **In-flight guard:** In the JS canvas controller, maintain a boolean `saveInProgress`. If `saveInProgress` is `true` when another save is triggered, discard the new trigger and set `pendingSave = true`. On save completion, fire one more save if `pendingSave` is true.
- **Page unload:** Use `fetch('/autosave/', { method: 'POST', keepalive: true, body: ... })` inside `document.addEventListener('visibilitychange', ...)` when `document.visibilityState === 'hidden'`. `visibilitychange` + `pagehide` are more reliable than `beforeunload`. `keepalive: true` bypasses the cancellation problem. Note: `navigator.sendBeacon` has a 64 KB payload limit — for a 100 KB diagram JSON blob this silently drops the request.

**Warning signs:** User reports "my diagram reverted"; "saves I made in one tab were lost"; diagram goes back to an old version on reload.

**Phase to address:** Autosave phase. Version token must be designed in the model phase (additive column from the start), enforced in the autosave view, and the in-flight guard coded in the canvas JS controller.

---

### Pitfall 4: Permission Boundary Leak — IDOR on Autosave Endpoint

**What goes wrong:** The autosave endpoint receives `{"diagram_id": 47, "canvas_json": {...}}`. A malicious POST with `diagram_id` belonging to a different project's diagram succeeds unless the view explicitly verifies that `SignalFlowDiagram.objects.get(id=47).project == request.current_project`. An authenticated ShowStack user from Project A can overwrite Project B's diagrams. Worse: the canvas JSON blob contains `(content_type_id, object_id)` pairs referencing equipment. If the server does not validate that each referenced object_id belongs to `request.current_project`, a user can plant references to another project's `Console` or `Device` rows, causing them to appear as linked nodes in their own diagram.

**Why it happens:**
- Session-based project scoping (via `CurrentProjectMiddleware`) sets `request.current_project` but views must actively use it — the middleware does not prevent access to other projects' objects.
- The existing pattern in `planner/views.py` for IDOR-safe lookup is `MultitrackTrack.objects.filter(id=track_id, session__project=current_project).first()` (see `_get_track_for_request`). This pattern must be replicated for diagrams.
- The JSON blob is opaque to the server — equipment references inside it are easy to overlook.

**How to avoid:**
- **Diagram ownership:** All diagram lookups must use `SignalFlowDiagram.objects.filter(id=diagram_id, project=request.current_project).first()`. Never a bare `.get(id=diagram_id)`.
- **Equipment reference validation:** On every autosave, walk the canvas JSON to extract all `(content_type_id, object_id)` node data. For each pair, confirm the referenced record's `project_id == request.current_project.id`. Reject the save with HTTP 422 and a descriptive error if any reference is out-of-project. This is O(nodes) and cheap for 50-node diagrams.
- **Viewer-role enforcement:** Viewer-role users must not reach the autosave endpoint at all. Add the same `BaseEquipmentAdmin`-style role check (or a `_require_editor_or_above` decorator) to the autosave view.
- Follow the exact pattern of `_get_track_for_request` from `planner/views.py` line 6328 for the diagram equivalent.

**Warning signs:** Any autosave endpoint that accepts `diagram_id` from the request body without a project check. Any equipment reference in the canvas JSON that is not validated server-side.

**Phase to address:** Model phase (design the lookup helper). Autosave view phase (enforce it). This must be in place before beta testers see the module.

---

### Pitfall 5: CSRF Token Not Threaded Into JointJS Event Handlers

**What goes wrong:** JointJS fires `graph.on('change', ...)` events deep inside the Backbone event system. If the autosave function that posts to Django is called from inside a JointJS event handler that was set up before the CSRF token was read, or if the token is read once at page load and the cookie is later rotated (e.g., after session re-authentication), POSTs return 403 Forbidden with no visible error, and autosave silently stops working.

**Why it happens:** The existing pattern in ShowStack is to read the CSRF token at call time from the cookie (`getCsrfToken()` in `mic_tracker.html` line 1212–1215: `document.cookie.split(';').find(x => x.trim().startsWith('csrftoken='))`). The trap is forgetting to call this function on every request and instead caching the value in a module-level variable set at page load.

**How to avoid:**
- Use the exact `getCsrfToken()` pattern already in the codebase — read the cookie fresh on every `fetch()` call, not at page-load time.
- Thread it through the autosave function: `headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() }`.
- The autosave view must use `@login_required` and `@require_POST`, NOT `@csrf_exempt`. The `@csrf_exempt` on `update_mic_assignment` (line 1174) was a workaround — do not repeat it.
- Test with `SESSION_COOKIE_AGE` reduced to 10 seconds in dev to verify the token is re-read correctly after session refresh.

**Warning signs:** 403 responses in the Network tab on autosave; autosave appears to work but diagram changes are not persisted; works fine on first page load but fails after the tab has been open for hours.

**Phase to address:** Canvas/autosave phase. CSRF must be correct before any real autosave wiring is done.

---

### Pitfall 6: PNG Export — CSS Not Inline-d, Fonts Missing, Background Blank

**What goes wrong:** JointJS's `paper.toPNG()` / `format.toPNG()` (MIT-tier) serializes the SVG to a canvas. The export process walks the DOM and inlines computed styles, but three categories of resources fail:

1. **External fonts (Google Fonts, system fonts):** CSS `@font-face` rules loaded from a CDN reference cross-origin URLs. When the SVG is rendered to an off-screen canvas via `drawImage`, the browser enforces CORS on the font resources. The canvas is "tainted" and `toDataURL()` throws a SecurityError. Even if the canvas is not tainted, the font simply may not load in time before the snapshot is taken.

2. **Paper background / grid CSS:** The paper's background color and grid lines are applied via CSS classes. If `useComputedStyles` is false (the default in older JointJS versions), these styles are stripped and the exported PNG has a transparent or white background with no grid.

3. **SVG `foreignObject` elements:** Any node that uses HTML inside an SVG `<foreignObject>` (e.g., rich text labels rendered as `<div>` elements) taints the canvas in all browsers when referenced via HTTP URL, making `toDataURL()` throw. The chromium flag to allow blob-URL foreignObject without taint does not help for HTTP-served SVGs.

**How to avoid:**
- Use JointJS's `useComputedStyles: true` option in `format.toPNG()` to inline all computed CSS at export time.
- Do not use `foreignObject` for node labels. Use JointJS's native SVG `<text>` elements (the `joint.dia.Element` `attrs.label.text` approach). This avoids the entire foreignObject-taint class of problems.
- For fonts: use system fonts only (no Google Fonts CDN), or embed the font as a base64 `@font-face` data URI in a `<style>` element and pass it to the export via the `stylesheet` option. Do not load fonts via CDN for any shape label.
- Set `paper.drawBackground({ color: '#1a1a2e' })` (or whatever the ShowStack dark theme color is) before calling `toPNG`. The background color will be included in `useComputedStyles` capture.
- Test PNG export with DevTools offline mode active — if fonts fail to load, the export will silently use a fallback font. The exported PNG should look identical to the on-screen diagram.

**Warning signs:** Exported PNG has white/transparent background; text labels use wrong font; `toDataURL()` throws SecurityError in console; PNG export button appears to work (no error) but the downloaded file has missing elements.

**Phase to address:** Export phase. PNG export should be treated as a distinct engineering task, not a "just call one API" step.

---

### Pitfall 7: JSON Blob Size Growth — Autosave Flooding and Railway Limits

**What goes wrong:** A 50-node, 100-edge diagram with per-node metadata (label, position, size, attrs, ports, linked content_type+object_id) and per-edge metadata (vertices, connector style, labels) produces approximately 80–150 KB of minified JSON. Several downstream problems:

1. **Autosave flooding:** If autosave fires on every `cell:change` event (which fires once per pixel of drag movement), a user dragging a node across the canvas produces hundreds of POSTs per second, each with a 100 KB body. This floods Django's workers, saturates Railway's internal network, and produces noisy Railway logs.

2. **Railway request body size:** Railway routes through a proxy. While Railway has no documented per-request body limit, PostgreSQL TOAST handles large JSON fine (TOAST threshold is ~2 KB; JSONB rows above that are transparently compressed on-disk, adding ~50 µs per access). The bottleneck is not the database — it's the HTTP request path. Very large payloads (>1 MB) have triggered 413 errors on Railway based on community reports.

3. **Browser `navigator.sendBeacon` limit:** 64 KB hard limit. A 150 KB diagram JSON silently drops on page close if sent via `sendBeacon`. See Pitfall 3 for the `keepalive: true` mitigation.

**How to avoid:**
- **Debounce aggressively:** Autosave should debounce at a minimum of 1500ms from the last `cell:change` event. Do not fire on every change. A 2-second trailing debounce means the user can drag for 30 seconds and only 1 save fires after they stop.
- **Dirty flag:** Maintain a `diagramDirty` boolean. Set it on `cell:change`. The debounce fires only if `diagramDirty` is true, then resets it. This prevents redundant saves when nothing has changed since the last save.
- **Compress the payload:** Use `JSON.stringify(graph.toJSON())` directly — do not add additional metadata wrappers that inflate the blob. The graph JSON already includes everything JointJS needs for `fromJSON`.
- **Do not store render-only state in the blob:** Do not save viewport translate/scale in the canvas JSON (save it separately or in `localStorage` for this tab only — it is per-user-session, not per-diagram).
- **Index on (project_id, updated_at)** for the diagram list page to avoid a full table scan.

**Warning signs:** Railway logs show dozens of 200 responses per second for the autosave endpoint; database `updated_at` changes many times per second per diagram row.

**Phase to address:** Autosave phase. The debounce and dirty-flag must be designed before wiring autosave to the real endpoint. The JSON size should be measured at the end of the canvas phase by loading a 50-node test fixture and printing `JSON.stringify(graph.toJSON()).length` to the console.

---

## Moderate Pitfalls

Significant rework or UX failures if not addressed, but not show-stopping.

---

### Pitfall 8: Paper Sizing Breaks When Container Has Percentage Width

**What goes wrong:** Setting `paper.width = '100%'` works for initial render, but calling `paper.scaleContentToFit()` or `paper.fitToContent()` immediately after produces an empty graph on the first call because `paper.el.getBoundingClientRect()` returns zero dimensions while the element is in the middle of a CSS layout reflow. The paper thinks it has zero available space and scales content to nothing.

There is a known GitHub issue (#964) for this exact scenario: `paper.scaleContentToFit not working when paper width is percentage`.

**How to avoid:**
- Use fixed pixel dimensions initially (`width: containerEl.offsetWidth, height: containerEl.offsetHeight`) and add a `ResizeObserver` on the container element to call `paper.setDimensions(entry.contentRect.width, entry.contentRect.height)` when the layout changes.
- Or: call `paper.fitToContent()` inside a `requestAnimationFrame()` callback to guarantee the browser has completed layout before the call.
- Do not put the canvas inside a container that has `display: none` at initialization time — JointJS cannot measure dimensions of hidden elements, and the paper renders at 0×0.

**Warning signs:** Canvas appears blank on first load even though the `graph.fromJSON()` call succeeds; canvas appears correctly only after a window resize.

**Phase to address:** Canvas controller phase. Size initialization is among the first things wired up.

---

### Pitfall 9: Model-vs-View Separation — Storing UI State in Graph JSON

**What goes wrong:** JointJS's `cell.prop()` stores arbitrary data on the Backbone model, and that data is included in `graph.toJSON()`. Developers often store UI-only transient state (selection highlight color, hover state, tooltip visibility, zoom level, current tool mode) using `cell.prop()` because it's convenient. This state then pollutes the persisted JSON blob, causing:
- The diagram to re-open with wrong visual state (e.g., a node still appears "selected" on next load)
- The autosave to fire on every mouse-hover event (because `cell:change` fires on any `prop()` change)
- The JSON blob to grow with data that is meaningless after the session ends

**How to avoid:**
- Use `cell.prop()` only for data that should survive a save/reload cycle: label text, linked equipment `content_type_id` + `object_id`, connector style, port configuration.
- Use DOM manipulation / CSS classes for purely visual/transient state: selected, hovered, error highlight.
- The JointJS distinction: `cell.attr()` is for SVG presentation attributes (they ARE serialized), `cell.prop()` is for custom business-logic attributes (they ARE serialized). Neither is a place for session-transient UI state.
- Keep a separate JS object (not on the model) for canvas-controller state: `{ selectedCellId, tool, isDirty, isSaving }`.

**Warning signs:** Autosave fires constantly even when the user is not editing; JSON blob grows unexpectedly; diagram reopens with stale visual state.

**Phase to address:** Canvas controller phase. Establish the state-separation rule before any node types are defined.

---

### Pitfall 10: GenericForeignKey — ContentType Wiped on App Rename, admin Display Broken

**What goes wrong:** `SignalFlowDiagramNode` will use `(content_type, object_id)` to link nodes to equipment. Three operational hazards:

1. **App rename:** Django's `ContentType` rows are keyed on `(app_label, model)`. If the `planner` app is ever renamed, all `ContentType` foreign keys from `SignalFlowDiagramNode` point to deleted rows (the old app_label). The GFK silently returns `None` for every previously linked node. This is not a theoretical concern — the `planner` app has already had models extracted/shuffled across previous milestones.

2. **Prefetch on GFKs requires explicit `Prefetch` objects:** `prefetch_related('nodes__content_object')` does NOT work for GenericForeignKey. You must use `prefetch_related_objects(nodes, 'content_object')` or the `GenericPrefetch` pattern from Django 4.2+ to avoid N+1 queries when rendering a diagram's node list.

3. **Admin display:** Any admin that lists `SignalFlowDiagramNode` must call `str(node.content_object)` to show the linked equipment name. If the linked model's `__str__` method is slow or if the GFK target is None (deleted equipment), the admin list blows up or shows empty cells.

**How to avoid:**
- Document in the model: "If `planner` is ever split into multiple apps, run `ContentType.objects.filter(app_label='planner').update(app_label='new_label')` before the rename migration."
- For the diagram detail view, implement explicit prefetch: load all nodes for the diagram, then batch-fetch equipment using `prefetch_related_objects`. The node queryset is small (50 nodes max at MVP), so N+1 is survivable but still wrong.
- Soft-fail render: if `content_object` is None (linked equipment was deleted), render the node with a "missing equipment" indicator — do not raise an exception. The node's label field should be a `saved_label` char field that stores the label at link time, providing display fallback.
- Ensure every equipment model that can be linked (`Console`, `Device`, `SpeakerArray`, `CommBeltPack`) has a meaningful `__str__` method — most already do in the existing codebase.

**Warning signs:** All linked nodes render as "unknown" after a deployment; admin list page throws `AttributeError: 'NoneType' object has no attribute 'name'`; N+1 queries in Django Debug Toolbar.

**Phase to address:** Model phase. The `saved_label` fallback field and soft-fail render must be designed before the canvas phase ships the node types.

---

### Pitfall 11: JointJS License Is MPL 2.0, Not MIT

**What goes wrong:** The PROJECT.md and milestone scope note state "JointJS core (MIT)". This is incorrect — the open-source JointJS core is licensed under **Mozilla Public License 2.0 (MPL 2.0)**, not MIT. MPL 2.0 is a "file-level copyleft" license. If ShowStack modifies any JointJS source file, those modifications must be disclosed under MPL 2.0. Vendoring the unmodified distribution file (joint.min.js) inside ShowStack's repo is permissible without any source disclosure obligation, as long as the file is not modified.

**Why it happens:** JointJS's marketing and README use the phrasing "open source" prominently. Several secondary sources (including the question prompt in this research) characterize it as MIT. The npm package metadata shows MPL 2.0.

**How to avoid:**
- Vendor the unmodified `joint.min.js` distribution file exactly as downloaded. Do not patch it.
- If any bug in JointJS requires a patch, the patched file must be made available under MPL 2.0. Safer approach: monkey-patch via the public JS API without modifying the source file.
- Note the license in a `THIRD_PARTY_LICENSES.txt` file in the repo. Lawson Design & Engineering's trademark filing is unaffected; this is a source-disclosure obligation, not a patent or trademark issue.
- JointJS+ (the commercial tier) is under a separate commercial license — not relevant unless the scope expands.

**Warning signs:** None at runtime — this is a legal/compliance issue, not a code issue. The warning sign is modifying `joint.min.js` to fix a bug rather than wrapping it via the public API.

**Phase to address:** Model phase (before any code is written). Note in the phase plan that the vendored file must not be patched.

---

### Pitfall 12: Whitenoise + JointJS CSS Asset Path Resolution

**What goes wrong:** The JointJS distribution includes a `joint.min.css` file. If that CSS file references any assets via relative `url()` paths (e.g., icon images, fonts shipped with the library), and the CSS file is placed at `/static/planner/vendor/joint/joint.min.css`, the relative URLs resolve relative to that path. If the referenced assets are not co-located in the same directory, they 404. Whitenoise's `CompressedManifestStaticFilesStorage` rewrites `url()` paths in CSS at `collectstatic` time — if it cannot find the referenced file, it raises `ValueError` and the entire `collectstatic` fails, blocking the Railway deploy.

**How to avoid:**
- Inspect the JointJS distribution for any `url()` references in `joint.min.css` before vendoring. The current open-source JointJS core CSS is minimal — it primarily sets SVG element styles without external asset references. Verify this before assuming it is safe.
- If `url()` references exist, place all JointJS distribution files (JS, CSS, and any assets) under one vendor subdirectory: `planner/static/planner/vendor/joint/`. The relative paths from the CSS file will then resolve correctly.
- Test `collectstatic` locally (`python manage.py collectstatic --noinput`) before pushing to Railway. A `ValueError` in `collectstatic` blocks the deploy silently (the Procfile step fails and the old code stays running).

**Warning signs:** Railway deploy appears to succeed but shows the previous version of the code; local `collectstatic` raises `ValueError: The file 'planner/vendor/joint/icons/...' could not be found`.

**Phase to address:** Canvas controller phase (when the vendor file is first checked in).

---

### Pitfall 13: Mobile Read-Only Viewer Pre-Design — Choices That Lock Us In

**What goes wrong (future):** The v2.3 plan defers the mobile `/m/` viewer for `SignalFlowDiagram`. However, two decisions made in v2.2 can make the v2.3 viewer significantly harder:

1. **No `paper_size` or `viewport` field on the model:** If the canvas controller stores pan/zoom state only in JS memory (never persisted), the v2.3 viewer cannot restore the user's last viewport. The viewer will always open at the default zoom, which may not show the signal path the engineer needs on a small screen.

2. **Backbone/JointJS event system loaded on mobile even in read-only mode:** If the canvas controller JS file bundles the full JointJS Paper with all interactive event handlers, the mobile viewer loads tens of KB of drag-and-drop code that serves no purpose and may interfere with touch scroll.

**How to avoid (decisions to make now, in v2.2):**
- Add a `viewport` JSONField to `SignalFlowDiagram` (default `{}`). The canvas controller saves `{ translate: { tx, ty }, scale }` to this field on autosave. The v2.3 viewer reads it and calls `paper.translate(tx, ty)` + `paper.scale(scale)` before rendering. This field is zero-cost in v2.2 and essential in v2.3.
- Structure the canvas controller JS so that interactive initialization (`paper.on('cell:pointerdown', ...)`, drag handlers, tool attachment) is conditional on a `readOnly` flag passed in from the template. The v2.3 viewer template passes `readOnly: true` and skips all event binding. This does not require two separate JS files — just an `if (!readOnly)` guard block.
- Use `paper.options.interactive = false` as the JointJS-native mechanism to disable all editing interactions in viewer mode. This is a single-line change that prevents all pointer events from modifying the graph.

**Warning signs:** v2.3 mobile viewer has to rewrite the canvas controller from scratch; pan/zoom state is lost every time the diagram is opened.

**Phase to address:** Canvas controller phase. The `viewport` field belongs in the model phase. The `readOnly` guard structure must be in the canvas controller before the autosave phase is closed.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Store viewport translate/scale only in JS memory, not persisted | Simpler autosave payload | v2.3 mobile viewer cannot restore position; users always open diagrams at default zoom | Never — `viewport` JSONField is trivial to add |
| `@csrf_exempt` on autosave endpoint | Avoids CSRF token plumbing | Security hole — any authenticated session can POST forged saves | Never |
| Bare `get_object_or_404(SignalFlowDiagram, id=diagram_id)` without project check | Simpler view code | IDOR vulnerability — any authenticated user can access any project's diagram | Never |
| Save UI-transient state (hover, selected) in `cell.prop()` | Convenient | Autosave floods, JSON blob inflates, diagram reopens with stale visual state | Never |
| No `saved_label` fallback on node model | Fewer fields | Deleted equipment causes node to render with no label | Never — add `saved_label` in model phase |
| Debounce autosave at 300ms | Feels more responsive | Hundreds of requests per drag operation, Railway worker saturation | Never — 1500ms minimum |
| Load full JointJS + all event handlers on the future mobile viewer | One JS file to maintain | Tens of KB wasted on mobile; touch scroll may conflict | Never — add `readOnly` flag guard now |
| Modify `joint.min.js` to fix a bug | Unblocked immediately | MPL 2.0 source disclosure obligation; breaks on next JointJS upgrade | Never — use public API monkey-patch |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| JointJS `graph.on('change', autosave)` | Fires on every pixel of drag — hundreds of calls per second | Debounce at 1500ms trailing; gate on `diagramDirty` flag |
| `paper.toPNG()` with external fonts | Font loads from CDN → canvas taint → SecurityError | Embed fonts as base64 data URI `@font-face`; use system fonts only on shape labels |
| Django `current_project` middleware | Middleware sets attribute but views must actively use it for every query | All diagram queries must chain `.filter(project=request.current_project)` |
| JointJS `fromJSON` custom shapes | Shapes not in `cellNamespace` → silent blank canvas | Pass explicit `cellNamespace` to `Graph` constructor before `fromJSON` |
| `navigator.sendBeacon` on unload | 64 KB limit silently drops large diagram JSON | Use `fetch(..., { keepalive: true })` via `visibilitychange` / `pagehide` events |
| `paper.scaleContentToFit()` on `%` width | Fires before layout reflow → empty graph | Use `requestAnimationFrame` wrapper or `ResizeObserver` |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| N+1 on diagram list page | Slow load when project has 20+ diagrams, each with many nodes | Annotate with `nodes__count` in list queryset; defer GFK resolution to detail view | At ~10 diagrams with node data |
| `graph.toJSON()` on every keystroke | CPU spike on large diagrams; Railway log flood | Debounce + dirty flag | At ~30 nodes + rapid editing |
| `cell:change` bound directly to autosave | Request storm on drag operations | Debounce 1500ms trailing | Immediately on first drag |
| No index on `(project_id, updated_at)` | List page slow as diagrams accumulate | Add `Meta.indexes` in model | At ~100 diagrams per project |
| `paper.fitToContent()` called synchronously | Race with layout reflow, returns zero bbox | Wrap in `requestAnimationFrame` | Every first page load |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Autosave endpoint accepts `diagram_id` without project check | IDOR: any authenticated user can overwrite any diagram | `filter(id=id, project=request.current_project)` — see `_get_track_for_request` pattern |
| Equipment `(content_type, object_id)` in JSON not validated server-side | User plants cross-project equipment references | Walk canvas JSON on every save; reject if any object_id's project != current project |
| Viewer role can POST to autosave | Viewer corrupts editor's work | `@require_editor_or_above` decorator (or equivalent role check) on autosave view |
| `@csrf_exempt` on autosave | CSRF attack can trigger saves from any page | Never exempt — use cookie-based CSRF token via `getCsrfToken()` pattern |
| Version token not validated atomically | TOCTOU race allows stale write to win | `UPDATE ... WHERE version=expected_version` in `select_for_update` atomic block |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No "saving..." / "saved" indicator | User doesn't know if changes are persisted; closes tab and loses work | Show a status indicator: "Unsaved changes", "Saving...", "Saved 2s ago" |
| Autosave fails silently (403, 409, network error) | User thinks diagram is saved; it isn't | On autosave failure, show a persistent banner: "Autosave failed — changes not saved" with a manual save button |
| Deleted equipment leaves node in error state with no label | Node appears broken with no explanation | Render with `saved_label` + a distinct "equipment deleted" indicator (red border, tooltip) |
| Diagram opens at default zoom every time | Engineer has to re-pan/zoom to the signal path they care about every session | Persist `viewport` (pan + zoom) in the `SignalFlowDiagram` model and restore on load |
| "Save" and "Export PNG" are the only exit points | Viewer-role users have no affordance because saving is not available to them | Hide / disable save controls based on role; read-only state is explicit |
| Link-tool buttons (vertex remove, segment move) capture clicks intended for the underlying link | Clicking near a link tool button selects the link but also activates a tool | Use JointJS `stopPropagation` option on link tools; test each link tool button in isolation |

---

## "Looks Done But Isn't" Checklist

- [ ] **Custom shapes load from saved JSON:** Save a diagram with one of each shape type, reload the page, confirm all shapes render. Blank canvas = `cellNamespace` registration missing.
- [ ] **IDOR protection:** POST to autosave endpoint with a `diagram_id` from a different project's user session. Should return 403, not 200.
- [ ] **Equipment reference validation:** POST canvas JSON containing a `(content_type_id, object_id)` that belongs to a different project. Should return 422.
- [ ] **Autosave + manual save race:** Trigger a cell change, immediately click manual save. Confirm the final persisted state matches the expected version (the later of the two operations).
- [ ] **Page-close save:** Make a change, close the tab immediately. Reload. Confirm the change was persisted (requires `keepalive: true` fetch on `visibilitychange`).
- [ ] **Multi-tab conflict:** Open same diagram in two tabs. Edit in Tab A, save. Edit in Tab B, save. Confirm Tab B receives a 409 and shows a conflict banner rather than silently overwriting Tab A's work.
- [ ] **PNG export font correctness:** Export PNG. Open in an image viewer. Confirm label fonts match the on-screen rendering.
- [ ] **PNG export with scroll:** Scroll the page down 200px. Export PNG. Confirm the exported diagram is not offset or clipped.
- [ ] **Viewer role cannot save:** Log in as a viewer-role user. Open a diagram. Confirm the autosave endpoint returns 403, no edits are accepted.
- [ ] **Deleted equipment soft-fail:** Delete a `Console` record that is linked to a diagram node. Reload the diagram. Confirm the node renders with `saved_label` and an error indicator, not a blank node or a 500.
- [ ] **`collectstatic` passes with JointJS vendor files present:** Run `python manage.py collectstatic --noinput` locally with the vendor files checked in. No `ValueError` for missing assets.
- [ ] **Coordinate correctness after scroll:** Add a shape via drag-drop while the page is scrolled to the bottom. Confirm the shape lands under the cursor, not offset by the scroll amount.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| `cellNamespace` missing → blank diagram on load | HIGH — diagrams appear broken for all users | Hotfix: add `cellNamespace` to `Graph` constructor; existing JSON data is intact and loads correctly once the fix deploys |
| Stale write wins (version token not enforced) | HIGH — corrupted diagram state may not be recoverable | If `updated_at` timestamps are kept, restore previous JSON from a DB backup within Railway's backup window; add version token in hotfix |
| IDOR exploit (cross-project save) | HIGH — requires security review of all affected diagrams | Audit `updated_at` on all diagrams; notify affected project owners; hotfix project check in view |
| PNG export produces blank PNG | LOW — no data loss | Hotfix: add `useComputedStyles: true` to export call; re-export |
| `collectstatic` fails due to JointJS CSS `url()` | MEDIUM — Railway deploy blocked | Fix: move CSS assets to correct directory alongside `joint.min.css`; redeploy |
| Page-close data loss (missing `keepalive`) | LOW per incident — one autosave missed | Hotfix: add `keepalive: true` to unload fetch; user must re-enter changes from memory |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| `cellNamespace` registration | Canvas controller phase | Smoke-test: save + reload with each shape type |
| SVG coordinate offset | Canvas controller phase | Manual test: drag-drop after page scroll |
| Autosave race condition (version token) | Model phase (add field) + autosave view phase (enforce) | Multi-tab race condition test |
| Autosave in-flight guard | Autosave JS phase | Simultaneous manual save + debounced autosave test |
| Page-unload data loss | Autosave JS phase | Close tab immediately after edit; verify on reload |
| IDOR on autosave endpoint | Autosave view phase | Cross-project POST test |
| Equipment reference validation | Autosave view phase | Cross-project object_id injection test |
| CSRF threading | Autosave JS phase | 403 regression: run with `SESSION_COOKIE_AGE=10` in dev |
| PNG export CSS/font | Export phase | Export with system font; compare to on-screen rendering |
| PNG export scroll offset | Export phase | Export after scrolling page to bottom |
| JSON blob size / autosave flood | Autosave JS phase | Measure `JSON.stringify(graph.toJSON()).length` at 50 nodes; confirm debounce fires at most once per 1500ms |
| Paper sizing on % container | Canvas controller phase | Blank-canvas regression: load diagram, do not resize window |
| Model-view state separation | Canvas controller phase | Autosave rate during hover-only mouse movement should be zero |
| GenericForeignKey deleted equipment | Model phase (saved_label) | Delete linked equipment; reload diagram |
| MPL 2.0 license compliance | Model/setup phase | Confirm `joint.min.js` is unmodified at ship |
| Whitenoise CSS asset paths | Canvas controller phase | `collectstatic --noinput` locally with vendor files present |
| Mobile viewer pre-design (`viewport` field) | Model phase (add field); Canvas phase (readOnly guard) | Field present in migration; `paper.options.interactive = false` wired to readOnly flag |

---

## Sources

- JointJS GitHub issue #964 — `paper.scaleContentToFit` with percentage width: https://github.com/clientIO/joint/issues/964
- JointJS GitHub issue #1133 — Serialization error: markup required: https://github.com/clientIO/joint/issues/1133
- JointJS GitHub issue #1221 — `graph.fromJSON` fails with dia.ElementView: markup required: https://github.com/clientIO/joint/issues/1221
- JointJS GitHub discussion #2566 — Migration to JointJS v4: Issue with `graph.fromJSON()`: https://github.com/clientIO/joint/discussions/2566
- JointJS docs — cellNamespace (v4.2): https://docs.jointjs.com/api/dia/Graph/
- JointJS docs — Export & Import (v4.1): https://docs.jointjs.com/learn/features/export-import/
- JointJS docs — Raster format / `toPNG` (v4.1): https://docs.jointjs.com/api/format/Raster/
- JointJS docs — Events (v4.1): https://docs.jointjs.com/learn/features/diagram-basics/events/
- JointJS GitHub discussion #2235 — Font change on PNG export: https://github.com/clientIO/joint/discussions/2235
- JointJS GitHub issue #1502 — Paper background image absent in export: https://github.com/clientIO/joint/issues/1502
- JointJS license page (MPL 2.0 confirmed): https://www.jointjs.com/license
- MDN — Navigator.sendBeacon: https://developer.mozilla.org/en-US/docs/Web/API/Navigator/sendBeacon
- Volument — sendBeacon is broken (64 KB limit): https://volument.com/blog/sendbeacon-is-broken/
- GitHub PR #32088 (dify) — replace sendBeacon with fetch keepalive for autosave: https://github.com/langgenius/dify/pull/32088
- Chromestatus — SVG foreignObject blob URL taint change: https://chromestatus.com/feature/5196074156032000
- WHATWG HTML issue #10641 — SVG-as-Image and Canvas origin-clean: https://github.com/whatwg/html/issues/10641
- Django docs — ContentType framework: https://docs.djangoproject.com/en/5.1/ref/contrib/contenttypes/
- Django ticket #16549 — Optimistic concurrency control: https://code.djangoproject.com/ticket/16549
- pganalyze — JSONB performance cliffs with TOAST: https://pganalyze.com/blog/5mins-postgres-jsonb-toast
- Railway Help Station — 413 on production: https://station.railway.com/questions/413-request-entity-too-large-on-producti-143078f3
- ShowStack planner/views.py line 6328 — `_get_track_for_request` IDOR-safe pattern (codebase)
- ShowStack templates/planner/mic_tracker.html line 1212 — `getCsrfToken()` cookie-read pattern (codebase)

---
*Pitfalls research for: JointJS diagram editor in Django 5.x server-rendered app (ShowStack v2.2 Signal Flow Diagrammer)*
*Researched: 2026-05-19*
