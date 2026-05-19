# Architecture Patterns: ShowStack v2.2 Signal Flow Diagrammer

**Domain:** Diagrammer module added to existing monolithic Django SaaS
**Researched:** 2026-05-19
**Confidence:** HIGH — based on direct code inspection of the existing codebase

---

## Recommended Architecture

The diagrammer is an additive module inside `planner`. It follows the same conventions
as every prior module (session-scoped project, `showstack_admin_site`, `BaseEquipmentAdmin`,
`@login_required` + `@require_POST` for AJAX, no URL-routed project IDs). It does not
require a new app.

### High-level component map

```
Browser
  |
  +-- GET /audiopatch/signal-flow/            -> signal_flow_list (HTML)
  +-- GET /audiopatch/signal-flow/<id>/       -> signal_flow_editor (HTML shell)
  +-- POST /audiopatch/signal-flow/create/    -> signal_flow_create (JSON)
  +-- POST /audiopatch/signal-flow/<id>/save/ -> signal_flow_autosave (JSON)
  +-- POST /audiopatch/signal-flow/<id>/delete/ -> signal_flow_delete (JSON)
  +-- GET  /audiopatch/signal-flow/<id>/png/  -> signal_flow_png_export (file download)
  +-- GET  /audiopatch/signal-flow/autocomplete/ -> signal_flow_autocomplete (JSON)
  +-- GET  /audiopatch/signal-flow/<id>/state/   -> signal_flow_state (JSON)

Django middleware stack
  |
  +-- CurrentProjectMiddleware -> request.current_project (no change)

planner/models.py
  +-- SignalFlowDiagram (new model, project-scoped)

planner/views.py
  +-- ~9 new view functions appended at bottom

planner/urls.py
  +-- ~9 new url patterns appended

planner/admin.py
  +-- SignalFlowDiagramAdmin (new class, registered on showstack_admin_site)

planner/admin_ordering.py
  +-- 'signalflowdiagram': 52 added to order_map
  +-- 'signalflowdiagram' added to always_hidden set

planner/templates/planner/signal_flow/
  +-- list.html
  +-- editor.html

planner/static/planner/js/
  +-- signal_flow_editor.js (JointJS canvas, autosave, PNG export)

planner/static/planner/js/vendor/
  +-- joint.min.js (JointJS core library)
```

---

## Decision: Model Design — Single Blob vs Normalized Tables

**Decision: Single `SignalFlowDiagram` row with `JSONField canvas_state`.**

Do not split into `Diagram + DiagramNode + DiagramEdge` tables.

Rationale:

- JointJS `graph.toJSON()` is the canonical, complete representation of the canvas.
  Splitting it into rows would require bidirectional serialization/deserialization on
  every save and load — double maintenance with no benefit.
- The diagram blob is ~10-50 KB for a typical signal flow. A full-blob POST every 2-3 s
  is ~5 DB writes per minute, well within PostgreSQL write capacity for a solo-user
  SaaS. No write-throughput concern at ShowStack's scale.
- Query-ability on node data (e.g., "which diagrams contain Console 4?") is not a
  v2.2 requirement. If it becomes one in a future milestone, add a
  `SignalFlowDiagramNode` denormalization table then, backed by a post-save signal.
- Normalized tables would duplicate layout state (positions, sizes, port offsets) which
  is already stored in the JointJS JSON. Two sources of truth for layout will drift.

The `canvas_state` blob stores whatever `graph.toJSON()` returns. The only server-side
contract is that `canvas_state` is valid JSON. Django `JSONField` (PostgreSQL `jsonb`)
handles this natively with no extra packages.

---

## Decision: Equipment Linking — GFK vs Separate Nullable FKs

**Decision: Django `ContentTypes` GenericForeignKey, stored inside the `canvas_state`
JSON nodes. No separate FK columns on `SignalFlowDiagram` or a sibling table.**

The node payload inside the JSON blob carries:

```json
{
  "id": "jointjs-cell-uuid",
  "type": "showstack.SmartShape",
  "equipment": {
    "content_type_id": 12,
    "object_id": 7,
    "equipment_type": "console",
    "label_override": "",
    "port_overrides": {
      "in_1": "Wless 1 Analogue",
      "out_2": ""
    }
  },
  "position": {"x": 240, "y": 160},
  "size": {"width": 160, "height": 80},
  "attrs": {
    "label": {"text": "FOH Console"}
  },
  "ports": {"items": []},
  "z": 1
}
```

`content_type_id` is the PK of the Django `ContentType` row (stable within a
deployment). `object_id` is the PK of the linked equipment record.

Why GFK-in-JSON rather than separate FK columns on a `DiagramNode` table:

- v2.2 scope covers four equipment types: `Console`, `Device`, `SpeakerArray`,
  `CommBeltPack`. Adding a fifth type (e.g., `Amp`) in v2.3 requires zero migration.
- The render path already loads the full JSON blob; resolving GFKs is a post-load
  enrichment step on the server (see Render Path section).
- Separate nullable FK columns (`console_fk`, `device_fk`, ...) on a node table
  would require a migration and a code change for every new shape type.
- The un-typed nature of GFK is acceptable here because the canvas JavaScript layer
  is already aware of equipment type (it sets `equipment_type: "console"` itself).
  Type safety is enforced at the shape-picker UI level, not the DB level.

The tradeoff is that cross-diagram equipment queries require a jsonb containment
query and a GIN index. For v2.2 that query is never needed. If needed later, add
`GinIndex(fields=['canvas_state'])` to the model `Meta`.

---

## Decision: Soft-Delete on Linked Equipment

**Decision: validate-on-load (enrich at `signal_flow_state` response time), not a
sweep job and not `on_delete=PROTECT`.**

When the editor loads (`GET /audiopatch/signal-flow/<id>/state/`), the server-side
view enriches each node's equipment reference:

```python
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist

def _enrich_nodes(canvas_state, project):
    """Resolve GFKs in canvas_state nodes; mark missing records as orphaned."""
    for cell in canvas_state.get('cells', []):
        eq = cell.get('equipment')
        if not eq:
            continue
        ct_id = eq.get('content_type_id')
        obj_id = eq.get('object_id')
        if ct_id and obj_id:
            try:
                ct = ContentType.objects.get_for_id(ct_id)
                obj = ct.get_object_for_this_type(pk=obj_id)
                eq['label'] = str(obj)
                eq['orphaned'] = False
            except (ContentType.DoesNotExist, ObjectDoesNotExist):
                eq['label'] = '[Deleted]'
                eq['orphaned'] = True
    return canvas_state
```

The client receives `orphaned: true` on affected nodes and renders them with a
"ghost" style (dashed border, muted color, "Deleted" badge) without crashing the
canvas. The JSON blob on disk is never modified by this enrichment — it retains
the original IDs so the link can be repaired if the equipment is restored.

Why not `on_delete=SET_NULL` on FK columns: there are no FK columns on the diagram
table. The reference lives inside the JSON blob.

Why not a periodic sweep job: adds operational infrastructure (Celery beat or a
management-command cron) for a UI-only display concern. Validate-on-load has zero
operational overhead and is correct for a planning tool where diagrams are loaded
infrequently, not queried at scale.

---

## Decision: Autosave Protocol

**Decision: 2-3 s debounced POST of the full JSON blob. Standard CSRF via
`X-CSRFToken` header. No diff/patch protocol.**

Pattern mirrors the existing multitrack AJAX endpoints exactly:

```python
@login_required
@require_POST
def signal_flow_autosave(request, diagram_id):
    project = getattr(request, 'current_project', None)
    if not project:
        return JsonResponse({'error': 'No active project'}, status=400)
    diagram = SignalFlowDiagram.objects.filter(
        id=diagram_id, project=project
    ).first()
    if not diagram:
        return JsonResponse({'error': 'Not found'}, status=404)
    if _is_viewer(request):
        return JsonResponse({'error': 'Read-only'}, status=403)
    try:
        data = json.loads(request.body)
        diagram.canvas_state = data['canvas_state']
        diagram.save(update_fields=['canvas_state', 'updated_at'])
        return JsonResponse({'ok': True})
    except Exception:
        logger.exception('signal_flow_autosave failed')
        return JsonResponse({'error': 'Server error'}, status=500)
```

The JavaScript side uses the same CSRF cookie pattern as all other AJAX endpoints
in the codebase:

```js
let autosaveTimer;
graph.on('change add remove', () => {
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(doAutosave, 2500);
});

function doAutosave() {
  fetch(AUTOSAVE_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken(),  // reads csrftoken cookie
    },
    body: JSON.stringify({ canvas_state: graph.toJSON() }),
  });
}
```

No `@csrf_exempt` needed or wanted. The multitrack module explicitly documents:
"All POST endpoints rely on Django CSRF middleware — no `@csrf_exempt` decorators."
(views.py line 6298-6299). Follow the same rule here.

Full-blob is correct: at ~20-50 KB per save with a 2.5 s debounce, the write rate
during active editing is at most ~24 writes/minute. PostgreSQL handles this trivially.

---

## URL Routing

Mount inside the existing `planner/urls.py` alongside `multitrack/`. All paths are
under `/audiopatch/` (the mount point for `planner.urls`).

```
Pattern (planner namespace)                  Method  View                      URL name
────────────────────────────────────────────────────────────────────────────────────────
signal-flow/                                 GET     signal_flow_list          signal_flow_list
signal-flow/create/                          POST    signal_flow_create        signal_flow_create
signal-flow/autocomplete/                    GET     signal_flow_autocomplete  signal_flow_autocomplete
signal-flow/<int:diagram_id>/                GET     signal_flow_editor        signal_flow_editor
signal-flow/<int:diagram_id>/state/          GET     signal_flow_state         signal_flow_state
signal-flow/<int:diagram_id>/save/           POST    signal_flow_autosave      signal_flow_autosave
signal-flow/<int:diagram_id>/rename/         POST    signal_flow_rename        signal_flow_rename
signal-flow/<int:diagram_id>/delete/         POST    signal_flow_delete        signal_flow_delete
signal-flow/<int:diagram_id>/export.png/     GET     signal_flow_export_png    signal_flow_export_png
```

Notes:

- `signal-flow/autocomplete/` and `signal-flow/create/` must appear BEFORE
  `signal-flow/<int:diagram_id>/` in `urlpatterns` — the int converter only matches
  digits, so "create" and "autocomplete" would not be captured as a `diagram_id`,
  but ordering-before is the explicit convention in this codebase (see multitrack
  template routes comment at urls.py line 110-115).
- `signal_flow_create` returns `{ok, redirect_url}` — same pattern as
  `multitrack_duplicate`.
- `signal_flow_state` is a dedicated GET endpoint so the editor HTML shell can be
  a static template with no inline JSON, and so the future v2.3 mobile viewer can
  consume the same endpoint without parsing an HTML page.
- PNG export: the client renders the canvas via `paper.el.querySelector('svg')`,
  converts to PNG via canvas, and posts the base64 data URI to
  `signal_flow_export_png`, which streams it back as a file download. No
  Playwright/Puppeteer dependency.

---

## View Rendering: HTML Shell + JSON Hydration

**Decision: HTML shell rendered server-side; canvas state fetched via `signal_flow_state`
on page load. Not server-side canvas rendering.**

```
GET /audiopatch/signal-flow/<id>/
  -> Django renders editor.html with:
      - diagram.name, diagram.id (for JS constants)
      - AUTOSAVE_URL, STATE_URL, AUTOCOMPLETE_URL injected as data-* attributes
      - JointJS loaded from planner/static/planner/js/vendor/joint.min.js
      - signal_flow_editor.js loaded

Page load sequence:
  1. HTML shell renders instantly (no canvas data in initial page)
  2. JS calls GET /audiopatch/signal-flow/<id>/state/ -> JSON (enriched)
  3. graph.fromJSON(state.canvas_state) hydrates the canvas
  4. Nodes with orphaned=true receive ghost styling
```

Why not embed `canvas_state` in the initial render: avoids a large inline JSON blob
in the HTML, and gives the v2.3 mobile viewer a clean JSON endpoint without needing
to parse an HTML page.

The mobile viewer (v2.3+) will:
1. GET `/audiopatch/signal-flow/<id>/state/` — same endpoint
2. Initialize JointJS with `paper.setInteractivity(false)` (read-only mode)
3. Apply ghost styles for orphaned nodes

This constraint is met from day one because the `state/` endpoint is a separate URL.

---

## Model Definition

```python
# planner/models.py — append after MultitrackTemplate

class SignalFlowDiagram(models.Model):
    project = models.ForeignKey(
        'Project', on_delete=models.CASCADE, related_name='signal_flow_diagrams'
    )
    name = models.CharField(max_length=200)
    canvas_state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Signal Flow Diagram"
        verbose_name_plural = "Signal Flow Diagrams"
        ordering = ['-updated_at', 'name']
        unique_together = [('project', 'name')]

    def __str__(self):
        return self.name
```

No additional models for v2.2. `canvas_state` is the complete JointJS
`graph.toJSON()` output — Django writes and reads it atomically as a jsonb blob.

---

## Node Payload Shape

Each JointJS cell representing a linked ShowStack record carries this shape inside
`canvas_state.cells[]`:

```json
{
  "id": "a3f2c1d0-...",
  "type": "showstack.SmartShape",
  "equipment": {
    "content_type_id": 12,
    "object_id": 7,
    "equipment_type": "console",
    "label_override": "",
    "port_overrides": {
      "in_1": "Wless 1 Analogue",
      "out_2": ""
    }
  },
  "position": {"x": 240, "y": 160},
  "size": {"width": 160, "height": 80},
  "attrs": {
    "label": {"text": "FOH Console"},
    "body": {"fill": "#2a2a2a"}
  },
  "ports": {"items": []},
  "z": 1
}
```

Field semantics:

| Field | Type | Meaning |
|-------|------|---------|
| `equipment.content_type_id` | int | Django ContentType PK; resolved server-side on `state/` load |
| `equipment.object_id` | int | PK of the linked `Console`, `Device`, `SpeakerArray`, or `CommBeltPack` |
| `equipment.equipment_type` | string | One of `"console"`, `"device"`, `"speaker_array"`, `"comm_beltpack"`, `"generic"` |
| `equipment.label_override` | string | Empty = use `str(linked_obj)`; non-empty = user-typed custom label |
| `equipment.port_overrides` | object | Port ID -> signal name; overrides autocomplete-resolved label per port |
| `position`, `size`, `attrs`, `ports`, `z` | standard | JointJS cell fields; stored as-is from `graph.toJSON()` |

Connector (edge) cells carry:

```json
{
  "id": "...",
  "type": "showstack.Connector",
  "signal_type": "dante",
  "source": {"id": "cell-uuid", "port": "out_1"},
  "target": {"id": "cell-uuid", "port": "in_1"},
  "attrs": {
    "line": {"stroke": "#00bcd4", "strokeDasharray": "none"}
  }
}
```

`signal_type` is one of `"analog"`, `"aes"`, `"dante"`, `"madi"`, `"intercom"`.
The client maps this to a line style; the server stores and returns it without
interpretation.

---

## Autocomplete: Models and Fields to Query

The `signal_flow_autocomplete` view (`GET ?q=<term>`) returns signal name
suggestions for connector labeling. It queries the following, all filtered to
`request.current_project`:

```
Model               Filter path                Field(s)
─────────────────────────────────────────────────────────────────────
ConsoleInput        console__project=project   source   (channel label, e.g. "Wless 1 Analogue")
                                               input_ch (channel number string)
ConsoleAuxOutput    console__project=project   name
ConsoleMatrixOutput console__project=project   name
ConsoleStereoOutput console__project=project   name
DeviceInput         device__project=project    signal_name
DeviceOutput        device__project=project    signal_name
```

Notes:
- `ConsoleInput` has no `signal_name` field. The correct field is `source` (the
  label describing what feeds that input). Confirmed by direct model inspection.
- `SpeakerArray` has no signal-name field. Its node label comes from
  `SpeakerArray.source_name` or `SpeakerArray.array_base_name`, sourced at
  shape-drop time, not from the autocomplete endpoint.
- `CommBeltPack` has no signal-name field. Its node label comes from
  `CommBeltPack.__str__()` (e.g., "W-BP 3: FOH").
- Deduplicate across sources before returning. Return as
  `[{"label": "Wless 1 Analogue", "source": "DeviceInput"}, ...]`.
- Limit to 20 results on `?q=` prefix match. No index needed at ShowStack scale.

---

## Admin Site Integration

**New code in `planner/admin.py`:**

```python
@admin.register(SignalFlowDiagram, site=showstack_admin_site)
class SignalFlowDiagramAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'project', 'updated_at']
    list_filter = ['project']
    readonly_fields = ['canvas_state_display', 'created_at', 'updated_at']
    exclude = ['canvas_state']

    def canvas_state_display(self, obj):
        import json
        from django.utils.html import format_html
        pretty = json.dumps(obj.canvas_state, indent=2)
        cell_count = len(obj.canvas_state.get('cells', []))
        return format_html(
            '<details><summary>{} cells</summary>'
            '<pre style="max-height:400px;overflow:auto">{}</pre></details>',
            cell_count, pretty
        )
    canvas_state_display.short_description = 'Canvas State'
```

`BaseEquipmentAdmin` handles role-based permission filtering — viewers see the list
but cannot edit. No extra permission logic needed.

**Modified code in `planner/admin_ordering.py`:**

Two changes:

1. Add `'signalflowdiagram'` to the `always_hidden` set. The diagram editor lives
   at `/audiopatch/signal-flow/`; the admin changelist is for superuser inspection
   only, not end-user navigation. This matches the `multitracksession` and
   `multitracktemplate` pattern (hidden from sidebar, accessible via direct URL).

   ```python
   always_hidden = {
       # ...existing entries...
       'signalflowdiagram',
   }
   ```

   If a sidebar link is later desired, remove from `always_hidden` and rely on the
   `order_map` entry instead.

2. Add to `order_map` (required whether hidden or not, to avoid 999/random sort
   position if the item is ever un-hidden):

   ```python
   'signalflowdiagram': 52,   # after multitracktemplate: 51
   ```

---

## Component Boundaries

| Component | Responsibility | Code location | New or Modified |
|-----------|---------------|---------------|-----------------|
| `SignalFlowDiagram` model | Persist name + JSON blob + project FK | `planner/models.py` | NEW |
| Migration | Schema: one new table | `planner/migrations/` | NEW |
| `signal_flow_list` view | List diagrams for current project | `planner/views.py` | NEW |
| `signal_flow_editor` view | Render HTML shell; inject JS constants | `planner/views.py` | NEW |
| `signal_flow_state` view | GET JSON: canvas_state enriched with orphan flags | `planner/views.py` | NEW |
| `signal_flow_autosave` view | POST full blob; project-scoped IDOR check | `planner/views.py` | NEW |
| `signal_flow_create` view | POST; create diagram + return redirect_url | `planner/views.py` | NEW |
| `signal_flow_rename` view | POST; rename diagram | `planner/views.py` | NEW |
| `signal_flow_delete` view | POST; delete diagram | `planner/views.py` | NEW |
| `signal_flow_autocomplete` view | GET ?q=; queries signal-name fields | `planner/views.py` | NEW |
| `signal_flow_export_png` view | Receive PNG from client; stream as download | `planner/views.py` | NEW |
| URL patterns | 9 new entries in `signal-flow/` namespace | `planner/urls.py` | MODIFIED |
| `SignalFlowDiagramAdmin` | Admin inspection; readonly JSON display | `planner/admin.py` | NEW |
| `admin_ordering.py` | `order_map` entry + `always_hidden` entry | `planner/admin_ordering.py` | MODIFIED |
| `list.html` | Diagram list; create/rename/delete modals | `planner/templates/planner/signal_flow/` | NEW |
| `editor.html` | HTML shell: canvas div + data-* attributes | `planner/templates/planner/signal_flow/` | NEW |
| `signal_flow_editor.js` | JointJS init, shapes, autosave, PNG export | `planner/static/planner/js/` | NEW |
| `joint.min.js` | JointJS core vendor bundle | `planner/static/planner/js/vendor/` | NEW |

---

## CurrentProjectMiddleware Integration Points

No changes to `CurrentProjectMiddleware` itself. All diagrammer views follow the
established pattern:

```python
project = getattr(request, 'current_project', None)
if not project:
    return redirect('/')  # or JsonResponse({'error': 'No active project'}, status=400)

diagram = SignalFlowDiagram.objects.filter(
    id=diagram_id, project=project
).first()
if not diagram:
    return JsonResponse({'error': 'Not found'}, status=404)
```

The `project=project` filter in every queryset is the IDOR guard, identical to the
multitrack module's `filter(id=session_id, project=current_project)` pattern.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: URL-routed project ID
**What:** `/audiopatch/project/7/signal-flow/3/`
**Why bad:** Violates the established session-based project scoping convention.
Introduces IDOR risk if a user crafts a URL with another project's ID.
**Instead:** `/audiopatch/signal-flow/<diagram_id>/` with `project=request.current_project`
filter in every queryset.

### Anti-Pattern 2: DiagramNode normalization table alongside the JSON blob
**What:** A separate `DiagramNode(diagram, content_type, object_id, x, y)` table
alongside `canvas_state`.
**Why bad:** Two sources of truth for node position and equipment identity. They will
drift on every save. Adds write amplification with no v2.2 query benefit.
**Instead:** GFK references live inside `canvas_state` JSON. Add a `DiagramNode`
denormalization table in a future milestone only if cross-diagram equipment queries
become a product requirement.

### Anti-Pattern 3: `@csrf_exempt` on autosave
**What:** Exempting the autosave endpoint from CSRF because it is "just AJAX."
**Why bad:** XSS-induced CSRF is a real attack vector. The multitrack module
explicitly documents "all POST endpoints rely on Django CSRF middleware — no
`@csrf_exempt` decorators." (views.py line 6298-6299).
**Instead:** Send `X-CSRFToken` header from JS using the `csrftoken` cookie read.

### Anti-Pattern 4: Registering on `admin.site`
**What:** `@admin.register(SignalFlowDiagram)` without `site=showstack_admin_site`.
**Why bad:** `admin.site` is Django's default admin; it is not the ShowStack admin.
**Instead:** Always `site=showstack_admin_site`.

### Anti-Pattern 5: Skipping `admin_ordering.py` update
**What:** Adding `SignalFlowDiagramAdmin` to `planner/admin.py` without updating
`admin_ordering.py`.
**Why bad:** The new model lands at sort position 999 and appears at an arbitrary
position in the sidebar. CLAUDE.md explicitly documents: "Update `admin_ordering.py`
whenever a new admin-registered model is added."
**Instead:** Add `'signalflowdiagram': 52` to `order_map` and add it to
`always_hidden` in the same commit.

### Anti-Pattern 6: `element.style.color = value` in admin-adjacent JS
**What:** Standard JS style assignment to override element appearance.
**Why bad:** Django admin uses `!important` pervasively. This is documented in
CLAUDE.md and has broken prior work.
**Instead:** `element.style.setProperty('color', value, 'important')`.
Note: JointJS canvas SVG elements are not in the admin DOM and are unaffected by
this rule. It applies to any HTML elements rendered by Django admin templates.

---

## Build Order

The following layers define minimum-dependency ordering. Each layer is a prerequisite
for the next, except where noted as parallel.

```
Layer 1 — Model + Migration
  No other layer depends on anything before this.
  - SignalFlowDiagram in planner/models.py
  - makemigrations + migrate (local SQLite)
  - SignalFlowDiagramAdmin in planner/admin.py (registered on showstack_admin_site)
  - admin_ordering.py: order_map entry + always_hidden entry
  GATE: `python manage.py migrate` succeeds; admin changelist loads at /admin/planner/signalflowdiagram/

Layer 2 — CRUD Views + URL Patterns
  Depends on Layer 1 (model must exist).
  - signal_flow_list, signal_flow_create, signal_flow_rename, signal_flow_delete
  - signal_flow_state (returns diagram.canvas_state as-is, no enrichment yet)
  - URL patterns in planner/urls.py (all 9)
  - list.html template
  - Dashboard link
  GATE: List page renders; create/rename/delete round-trip via forms or Postman.

Layer 3 — Editor HTML Shell
  Depends on Layer 2 (signal_flow_editor view must exist).
  - signal_flow_editor view (returns editor.html with data-* constants)
  - editor.html template (canvas div, script tags)
  - joint.min.js in vendor/
  - signal_flow_editor.js stub (logs "JointJS ready")
  GATE: /audiopatch/signal-flow/<id>/ loads; browser console shows "JointJS ready";
        no 404 on JS/CSS assets.

Layer 4 — JointJS Canvas Init
  Depends on Layer 3 (HTML shell must load JointJS).
  - graph + paper initialization in signal_flow_editor.js
  - graph.fromJSON() call on STATE_URL response
  - Blank canvas renders; pan/zoom works
  GATE: Blank canvas renders; graph.toJSON() in console returns valid JointJS structure.

Layer 5 — Smart Shapes
  Depends on Layer 4 (canvas must be working).
  (Can be developed in parallel with Layer 6 — no dependency between shapes and connectors.)
  - Custom JointJS shape definitions: ShowstackConsole, ShowstackDevice,
    ShowstackSpeakerArray, ShowstackCommBeltPack, ShowstackGeneric
  - Shape picker sidebar panel
  - Equipment picker modal (lists project equipment by type via inline JSON in editor.html
    or a dedicated AJAX endpoint)
  - Node payload written on drop: content_type_id, object_id, equipment_type, label_override
  GATE: Console shape dropped; node saved in autosave payload with correct content_type_id/object_id.

Layer 6 — Connector Types
  Depends on Layer 4 (canvas must be working).
  (Parallel with Layer 5.)
  - Link tool: draw connections between shape ports
  - Line style variants: analog / AES / Dante / MADI / intercom
  - signal_type stored in link cell attrs on creation/change
  GATE: Connector drawn; signal_type visible in graph.toJSON() output.

Layer 7 — Autocomplete
  Depends on Layer 2 (signal_flow_autocomplete view endpoint must exist).
  Can be developed and tested against the stub endpoint from Layer 2 onward.
  - signal_flow_autocomplete view queries all signal-name fields
  - JS autocomplete input widget on connector label field
  GATE: ?q=wless returns ConsoleInput/DeviceInput results from the project.

Layer 8 — Autosave + Orphan Rendering
  Depends on Layers 4-6 (canvas must be populated to test saves).
  - signal_flow_autosave view (full blob POST)
  - _enrich_nodes() in signal_flow_state view
  - 2.5 s debounce in signal_flow_editor.js
  - Save indicator (spinner / "Saved" badge)
  - Ghost styling for orphaned nodes (orphaned=true from state/ response)
  GATE: Edit a node; network tab shows POST to save/ 2.5 s after last change.
        Delete a linked equipment record; reload diagram; node shows ghost style.

Layer 9 — PNG Export
  Depends on Layer 4 (canvas must render).
  - signal_flow_export_png view (receive base64 PNG; stream as file download)
  - JS: SVG-to-canvas conversion; POST to export.png/
  GATE: "Export PNG" button downloads a valid PNG of the canvas.
```

Layers 5 and 6 can run in parallel — shapes and connectors have no dependency on
each other at the model or view level. Layer 7 can be built and tested against a
stub endpoint immediately after Layer 2 ships.

---

## Scalability Considerations

Not concerns for v2.2 but noted for future phases.

| Concern | At current scale | At 10x scale | At 100x scale |
|---------|-----------------|--------------|---------------|
| JSON blob size | 10-50 KB; trivial | Still trivial | Consider JSONB compression or blob archival if >1 MB |
| Autosave write rate | ~24/min per active editor | No concern | Increase debounce to 5 s |
| Cross-diagram equipment queries | Not needed (v2.2) | Add `DiagramNode` denormalization + GIN index | Standard JSONB query optimization |
| Concurrent editing | Not in scope (v2.2) | Last-write-wins is acceptable for solo SaaS | Add `etag`/optimistic lock if multi-user editing added |

---

## Sources

- Direct code inspection: `planner/models.py`, `planner/views.py`, `planner/urls.py`,
  `planner/middleware.py`, `planner/admin_ordering.py` (2026-05-19)
- CLAUDE.md: session scoping convention, admin site registration, CSRF pattern,
  CSS `!important` override rule
- `.planning/PROJECT.md`: v2.2 scope definition, JointJS core library decision
- Existing multitrack module: `MultitrackSession` blob-free model pattern,
  `@login_required` + `@require_POST` decorator stack, IDOR-safe combined queryset
  filter, `X-CSRFToken` header pattern
- JointJS core: `graph.toJSON()` / `graph.fromJSON()` API (HIGH confidence;
  standard JointJS API, stable across core versions)
