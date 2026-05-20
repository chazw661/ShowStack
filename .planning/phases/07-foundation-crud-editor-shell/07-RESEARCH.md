# Phase 7: Foundation, CRUD & Editor Shell — Research

**Researched:** 2026-05-19
**Domain:** Django model + admin + CRUD views + HTML shell for JointJS-based diagrammer
**Confidence:** HIGH — all findings grounded in direct codebase inspection and verified prior research

---

<user_constraints>
## User Constraints (from STATE.md / locked v2.2 decisions)

### Locked Decisions
1. `@joint/core` 4.2.4 (MPL-2.0) is the canvas library — vendored as unmodified UMD bundle; `THIRD_PARTY_LICENSES.txt` required at project root.
2. `html-to-image` 1.11.11 (MIT) for PNG export — `format.toPNG()` is JointJS+ (paid) only, must not be used.
3. Single `JSONField` blob on `SignalFlowDiagram` — no `DiagramNode`/`DiagramEdge` tables.
4. GFK-in-JSON for equipment linking (`content_type_id`, `object_id` inside `canvas_state.cells[]`).
5. HTML shell + `GET .../state/` JSON endpoint — no inline JSON in editor template; enables future v2.3 mobile viewer.
6. System fonts only on shape/connector labels — cross-origin webfonts taint PNG export canvas.
7. No new Python dependencies. `models.JSONField` and `django.contrib.contenttypes` are built into Django 5.x.
8. Additive migrations only — single new `SignalFlowDiagram` migration; no edits to existing tables.

### Claude's Discretion
- Template styling approach (extend admin/base_site.html, match existing planner module CSS conventions)
- Exact empty-state copy
- Whether `signal_flow_list` uses `@staff_member_required` or `@login_required` (follow multitrack precedent: page renders use `@staff_member_required`)

### Deferred Ideas (OUT OF SCOPE for Phase 7)
- Canvas rendering (JointJS graph/paper init) — Phase 8
- Smart shapes and connectors — Phase 8
- Autosave logic and save-status indicator — Phase 9
- `_enrich_nodes()` orphan rendering — Phase 9
- Actual keepalive fetch behavior — Phase 9 (URL stub only in Phase 7)
- Circuit-label autocomplete endpoint logic — Phase 10
- PNG export — Phase 10
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DGM-01 | User can see all signal-flow diagrams for the current project on a list page, with create / rename / delete actions | `signal_flow_list` view + `list.html` template; multitrack dashboard is the direct analog |
| DGM-02 | User can create a new diagram by entering a name; diagram is scoped to the current project via `CurrentProjectMiddleware` | `signal_flow_create` POST view; mirrors `multitrack_create_view` stripped of form/console FK |
| DGM-03 | User can rename a diagram from the list page; name is unique per project | `signal_flow_rename` POST view; `unique_together = [('project', 'name')]` on model; mirrors `multitrack_rename` exactly |
| DGM-04 | User can delete a diagram from the list page; deletion removes the canvas state and all node/connector references | `signal_flow_delete` POST view; CASCADE on `project FK` handles cleanup (single-table, no child rows); mirrors `multitrack_delete` |
| DGM-05 | All diagram views enforce `.filter(project=request.current_project)` on every lookup; cross-project access returns 404 | IDOR guard: every queryset chains `filter(id=diagram_id, project=project)`; mirrors `_get_track_for_request` pattern; 404 not redirect per DGM-05 |
| DGM-08 | Closing the tab or navigating away triggers a `keepalive: true` final save if there are unsaved changes | Phase 7 delivers: URL stub (`signal_flow_autosave`) and keepalive URL injected into editor shell as `data-autosave-url`; actual fetch behavior ships in Phase 9 |
</phase_requirements>

---

## Summary

Phase 7 establishes the complete Django scaffolding for the Signal Flow Diagrammer module. The deliverables are: the `SignalFlowDiagram` model with its migration, the admin registration, all 9 URL stubs, four CRUD view functions (list/create/rename/delete), five stub view functions (editor shell, state, autosave, autocomplete, export-PNG), the `list.html` template, the `editor.html` HTML shell, vendored `joint.min.js` and `html-to-image.min.js`, `THIRD_PARTY_LICENSES.txt`, and a "Signal Flow" link on the dashboard and admin index.

**Every pattern in this phase has a direct analog in the existing codebase.** The `MultitrackSession` module (v2.0) is the precise template: model FK to Project, `unique_together` on `(project, name)`, `@staff_member_required` page renders, `@login_required @require_POST` AJAX endpoints, `_viewer_block`-style role check, `filter(id=..., project=current_project)` IDOR pattern, templates extending `admin/base_site.html`, `admin_ordering.py` dual update (`order_map` + `always_hidden`), and `showstack_admin_site` registration. No new patterns need to be invented.

**Phase 7 does not wire the canvas.** `signal_flow_editor.js` is a stub that logs "JointJS ready" to the console. The autosave, state, autocomplete, and export-PNG views are also stubs that return `JsonResponse({'ok': True})` or an appropriate empty payload. Phase 8 fills the canvas; Phase 9 fills autosave; Phase 10 fills autocomplete and export.

**Primary recommendation:** Build in four atomic task groups: (1) model + migration + admin + admin_ordering + license files, (2) all 9 URLs + four CRUD views + five stub views, (3) `list.html` template + dashboard/admin-index nav link, (4) `editor.html` shell + vendor JS download + stub JS.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Diagram data persistence | Database / Django ORM | — | Single `JSONField` blob on `SignalFlowDiagram`; no client-side storage |
| Project scoping / IDOR enforcement | API / Backend (Django views) | — | Every queryset chains `filter(project=request.current_project)` |
| CRUD operations (create/rename/delete) | API / Backend (AJAX views) | Browser / Client (JS fetch) | Server owns truth; JS owns optimistic UI update |
| Editor HTML shell render | Frontend Server (Django template render) | — | `signal_flow_editor` renders `editor.html` with `data-*` constants; no canvas yet |
| Vendor JS serving | CDN / Static (Whitenoise) | — | `joint.min.js` + `html-to-image.min.js` served as static files after `collectstatic` |
| Admin inspection | API / Backend (Django admin) | — | `SignalFlowDiagramAdmin` on `showstack_admin_site`; always-hidden from sidebar |

---

## Standard Stack

### Core (no new dependencies — all built-in)

| Component | Version/Source | Purpose | Why Standard |
|-----------|---------------|---------|--------------|
| `models.JSONField` | Django 5.x built-in | `canvas_state` and `viewport` fields | Native PostgreSQL `jsonb`; no third-party dep needed |
| `django.contrib.contenttypes` | Django 5.x built-in, already in `INSTALLED_APPS` | Future GFK resolution in `_enrich_nodes()` | Already installed; zero migration cost |
| `JsonResponse` | Django built-in | All AJAX endpoint responses | Consistent with all existing AJAX endpoints in `planner/views.py` |
| `@login_required` + `@require_POST` | Django built-in | Decorator stack on AJAX mutate views | Matches every existing AJAX endpoint in multitrack module |
| `@staff_member_required` | Django built-in | Decorator on page-render views | Matches `multitrack_dashboard`, `multitrack_editor`, all multitrack page renders |

### Vendored JS (new files, no npm)

| File | Source URL | License | Purpose |
|------|-----------|---------|---------|
| `joint.min.js` | `https://cdn.jsdelivr.net/npm/@joint/core@4.2.4/dist/joint.min.js` | MPL-2.0 | JointJS canvas engine — exposes `joint` global on `window` |
| `html-to-image.min.js` | `https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js` | MIT | PNG export helper — Phase 10; vendored now alongside JointJS |

**Download command (run once, commit the files):**
```bash
curl -L "https://cdn.jsdelivr.net/npm/@joint/core@4.2.4/dist/joint.min.js" \
     -o planner/static/planner/js/vendor/joint.min.js

curl -L "https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js" \
     -o planner/static/planner/js/vendor/html-to-image.min.js
```

No `npm install`, no `package.json`, no build step. Consistent with the `Sortable.min.js` precedent at `planner/static/planner/js/vendor/Sortable.min.js`.

**Verify no CSS url() references:**
```bash
# joint.min.js is a JS file, not CSS — no url() asset paths. No joint.min.css required.
# @joint/core 4.x does NOT require a CSS file (confirmed in STACK.md).
# Safe to vendor the .js file alone.
```

### No Additions to requirements.txt

`[VERIFIED: codebase inspection + STACK.md]` — all server-side needs are met by Django 5.x built-ins.

---

## Architecture Patterns

### System Architecture Diagram

```
Browser
  |
  GET /audiopatch/signal-flow/           → signal_flow_list view
  |     renders list.html (all diagrams for current_project)
  |
  POST /audiopatch/signal-flow/create/   → signal_flow_create view
  |     creates SignalFlowDiagram, returns {ok, redirect_url}
  |     JS navigates to editor
  |
  POST /audiopatch/signal-flow/<id>/rename/  → signal_flow_rename
  POST /audiopatch/signal-flow/<id>/delete/  → signal_flow_delete
  |
  GET /audiopatch/signal-flow/<id>/      → signal_flow_editor view
  |     renders editor.html (HTML shell: canvas div + data-* constants)
  |     joint.min.js loaded → stub JS logs "JointJS ready"
  |
  GET /audiopatch/signal-flow/<id>/state/     → signal_flow_state stub
  POST /audiopatch/signal-flow/<id>/save/     → signal_flow_autosave stub
  POST /audiopatch/signal-flow/<id>/rename/   ↑ (same URL as above)
  POST /audiopatch/signal-flow/<id>/delete/   ↑ (same URL as above)
  GET /audiopatch/signal-flow/autocomplete/   → signal_flow_autocomplete stub
  GET /audiopatch/signal-flow/<id>/export.png/ → signal_flow_export_png stub
  |
  CurrentProjectMiddleware
  └── request.current_project (all diagram queries chain filter(project=...))
```

### Recommended Project Structure (new files only)

```
planner/
├── models.py                          # +SignalFlowDiagram class (append after MultitrackTemplate)
├── views.py                           # +9 view functions (append at bottom)
├── urls.py                            # +9 url patterns (append in signal-flow/ block)
├── admin.py                           # +SignalFlowDiagramAdmin class
├── admin_ordering.py                  # +order_map entry + always_hidden entry
├── migrations/
│   └── 0158_signalflowdiagram.py      # NEW — single migration
├── templates/planner/signal_flow/     # NEW directory
│   ├── list.html
│   └── editor.html
└── static/planner/js/
    ├── signal_flow_editor.js          # NEW — stub only in Phase 7
    └── vendor/
        ├── Sortable.min.js            # existing
        ├── joint.min.js               # NEW (@joint/core 4.2.4)
        └── html-to-image.min.js       # NEW (html-to-image 1.11.11)

# Project root:
THIRD_PARTY_LICENSES.txt              # NEW
.planning/PROJECT.md                  # MODIFIED — correct "MIT" → "MPL-2.0"
```

### Pattern 1: SignalFlowDiagram Model

**What:** Single-table diagram model with project FK, name, JSONField blob, and two fields that Phase 8/9 need but that must exist now to avoid a second migration.

**When to use:** Always — this is the only model for v2.2.

```python
# planner/models.py — append after MultitrackTemplate
# Source: ARCHITECTURE.md model definition + PITFALLS.md viewport/version fields

class SignalFlowDiagram(models.Model):
    project = models.ForeignKey(
        'Project', on_delete=models.CASCADE, related_name='signal_flow_diagrams'
    )
    name = models.CharField(max_length=200)
    canvas_state = models.JSONField(default=dict, blank=True)
    viewport = models.JSONField(default=dict, blank=True)   # Phase 8 uses this; must exist now
    version = models.IntegerField(default=1)                # Phase 9 uses this; must exist now
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

**Why `viewport` and `version` must exist in Phase 7:**
- `viewport`: The Phase 8 canvas controller persists pan/zoom to this field. Adding it in Phase 8 requires a second migration for a field that was always planned.
- `version`: The Phase 9 autosave view uses `WHERE version=expected_version` for optimistic locking. Same reason — adding it later requires an unnecessary migration.

**Migration number:** `0158_signalflowdiagram.py` — next after `0157_crew_crewmember_crewprojectadd.py`.

### Pattern 2: IDOR-Safe Diagram Lookup (DGM-05)

**What:** Every view that takes a `diagram_id` must verify ownership via `filter(id=diagram_id, project=project)`. Never use bare `.get(id=diagram_id)`.

**When to use:** All 9 view functions.

```python
# Source: planner/views.py:6042 (multitrack_editor) + _get_track_for_request pattern
# Inline helper for diagram-owning views:

def _get_diagram_for_request(request, diagram_id):
    """Return SignalFlowDiagram iff it belongs to request.current_project.

    IDOR-safe lookup. Returns None when diagram doesn't exist or belongs to
    a different project. Mirrors _get_track_for_request (views.py:6328).
    """
    project = getattr(request, 'current_project', None)
    if not project:
        return None
    return SignalFlowDiagram.objects.filter(
        id=diagram_id, project=project
    ).first()
```

**DGM-05 requirement:** Cross-project access returns 404. All diagram views that call `_get_diagram_for_request` and get `None` back should return `JsonResponse({'error': 'Not found'}, status=404)` for AJAX endpoints or `redirect('planner:signal_flow_list')` for page renders.

### Pattern 3: Viewer-Role Block

**What:** AJAX mutate endpoints (create, rename, delete, save) must reject Viewer-role users with 403 before touching the database. Page renders (list, editor) allow viewers to see but not edit.

**When to use:** All POST/mutate endpoints.

```python
# Source: planner/views.py:6315-6325 (_multitrack_viewer_block)

def _signal_flow_viewer_block(request):
    """Return JsonResponse 403 iff user is in Viewer group; else None.

    Mirrors _multitrack_viewer_block (views.py:6315). Centralised so every
    signal-flow mutate endpoint applies the same check.
    """
    if request.user.groups.filter(name='Viewer').exists():
        return JsonResponse({'error': 'Read-only access.'}, status=403)
    return None
```

### Pattern 4: CRUD View Skeleton

**What:** POST endpoint pattern for create/rename/delete. Consistent with multitrack module.

```python
# Source: planner/views.py:6217-6259 (multitrack_rename) + 6262-6290 (multitrack_delete)

@login_required
@require_POST
def signal_flow_rename(request, diagram_id):
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        project = getattr(request, 'current_project', None)
        if not project:
            return JsonResponse({'error': 'No active project'}, status=400)

        diagram = _get_diagram_for_request(request, diagram_id)
        if not diagram:
            return JsonResponse({'error': 'Not found'}, status=404)

        data = json.loads(request.body or '{}')
        new_name = (data.get('name') or '').strip()
        if not new_name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(new_name) > 200:
            return JsonResponse({'error': 'Name must be 200 characters or fewer.'}, status=400)

        if SignalFlowDiagram.objects.filter(
            project=project, name=new_name
        ).exclude(pk=diagram.pk).exists():
            return JsonResponse({
                'error': f'A diagram named "{new_name}" already exists in this project.',
            }, status=409)

        diagram.name = new_name
        diagram.save(update_fields=['name', 'updated_at'])
        return JsonResponse({'ok': True, 'name': new_name})
    except Exception:
        _signal_flow_logger.exception('signal_flow_rename failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

### Pattern 5: create view — returns redirect_url

**What:** `signal_flow_create` returns `{ok, redirect_url}` so JS can navigate to the new editor. Mirrors `multitrack_duplicate` return shape.

```python
# Source: planner/views.py:6210 (multitrack_duplicate redirect_url pattern)

@login_required
@require_POST
def signal_flow_create(request):
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        project = getattr(request, 'current_project', None)
        if not project:
            return JsonResponse({'error': 'No active project'}, status=400)

        data = json.loads(request.body or '{}')
        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(name) > 200:
            return JsonResponse({'error': 'Name must be 200 characters or fewer.'}, status=400)

        if SignalFlowDiagram.objects.filter(project=project, name=name).exists():
            return JsonResponse({
                'error': f'A diagram named "{name}" already exists in this project.',
            }, status=409)

        diagram = SignalFlowDiagram.objects.create(project=project, name=name)
        return JsonResponse({
            'ok': True,
            'redirect_url': reverse('planner:signal_flow_editor', args=[diagram.id]),
        })
    except Exception:
        _signal_flow_logger.exception('signal_flow_create failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

### Pattern 6: Stub Views (state, autosave, autocomplete, export-PNG)

**What:** Phase 7 stubs that return valid empty responses so the editor shell can reference them without errors. Filled in Phases 8-10.

```python
# signal_flow_state — GET, returns empty canvas_state for now
@staff_member_required
def signal_flow_state(request, diagram_id):
    diagram = _get_diagram_for_request(request, diagram_id)
    if not diagram:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse({'canvas_state': diagram.canvas_state, 'version': diagram.version})

# signal_flow_autosave — POST stub; URL must exist for DGM-08 data-* injection
@login_required
@require_POST
def signal_flow_autosave(request, diagram_id):
    return JsonResponse({'ok': True, 'stub': True})

# signal_flow_autocomplete — GET stub
@staff_member_required
def signal_flow_autocomplete(request):
    return JsonResponse({'results': []})

# signal_flow_export_png — GET stub
@staff_member_required
def signal_flow_export_png(request, diagram_id):
    return JsonResponse({'error': 'Not yet implemented'}, status=501)
```

### Pattern 7: editor.html Shell — data-* attribute injection

**What:** The editor renders with no inline JSON. JS constants are injected as `data-*` attributes so the stub JS (and later Phase 8-9 full JS) can read them without parsing HTML.

```html
{# planner/templates/planner/signal_flow/editor.html #}
{# Source: ARCHITECTURE.md "HTML shell + JSON hydration" pattern #}

{% extends "admin/base_site.html" %}
{% load static %}

{% block title %}{{ diagram.name }} — Signal Flow | ShowStack{% endblock %}

{% block extrahead %}
{{ block.super }}
{# No CSS needed for @joint/core 4.x #}
{% endblock %}

{% block content %}
<div id="sfd-container"
     data-diagram-id="{{ diagram.id }}"
     data-diagram-name="{{ diagram.name|escapejs }}"
     data-state-url="{% url 'planner:signal_flow_state' diagram.id %}"
     data-autosave-url="{% url 'planner:signal_flow_autosave' diagram.id %}"
     data-autocomplete-url="{% url 'planner:signal_flow_autocomplete' %}"
     data-export-png-url="{% url 'planner:signal_flow_export_png' diagram.id %}">

  <div id="sfd-canvas-container">
    {# JointJS paper mounts here in Phase 8 #}
    <div id="sfd-paper" style="background: #fff; width: 100%; height: 100%;"></div>
  </div>
</div>

{# CSRF cookie available for all AJAX POST calls #}
<form style="display:none">{% csrf_token %}</form>

{# Vendor bundles — load order matters: joint first, then html-to-image, then app JS #}
<script src="{% static 'planner/js/vendor/joint.min.js' %}"></script>
<script src="{% static 'planner/js/vendor/html-to-image.min.js' %}"></script>
<script src="{% static 'planner/js/signal_flow_editor.js' %}" defer></script>
{% endblock %}
```

**Why `html-to-image.min.js` is loaded in Phase 7:** The vendored file is committed now (PNG export is scheduled). Loading it in the shell from day one means Phase 10 only writes JS, not template changes.

**Why `readOnly` is not yet wired:** The v2.3 mobile viewer will pass `data-read-only="1"` from its own template. Phase 7 does not need to implement the guard — just ensure the container `div` has an ID the JS can read.

### Pattern 8: URL Block in planner/urls.py

**What:** All 9 signal-flow patterns appended to `planner/urls.py`, following the same ordering rule as multitrack: static paths before `<int:diagram_id>` paths.

```python
# Source: planner/urls.py:99-140 (multitrack block structure + comment style)
# IMPORTANT: signal-flow/create/ and signal-flow/autocomplete/ MUST come
# BEFORE signal-flow/<int:diagram_id>/ — the int converter matches only digits,
# but ordering-before is the explicit convention in this codebase (urls.py:109-115 comment).

    # ── Signal Flow Diagrammer (v2.2) ─────────────────────────────
    path('signal-flow/', views.signal_flow_list, name='signal_flow_list'),
    path('signal-flow/create/', views.signal_flow_create, name='signal_flow_create'),
    path('signal-flow/autocomplete/', views.signal_flow_autocomplete, name='signal_flow_autocomplete'),
    path('signal-flow/<int:diagram_id>/', views.signal_flow_editor, name='signal_flow_editor'),
    path('signal-flow/<int:diagram_id>/state/', views.signal_flow_state, name='signal_flow_state'),
    path('signal-flow/<int:diagram_id>/save/', views.signal_flow_autosave, name='signal_flow_autosave'),
    path('signal-flow/<int:diagram_id>/rename/', views.signal_flow_rename, name='signal_flow_rename'),
    path('signal-flow/<int:diagram_id>/delete/', views.signal_flow_delete, name='signal_flow_delete'),
    path('signal-flow/<int:diagram_id>/export.png/', views.signal_flow_export_png, name='signal_flow_export_png'),
```

### Pattern 9: admin.py Registration

**What:** `SignalFlowDiagramAdmin` on `showstack_admin_site` with `BaseEquipmentAdmin`. Changelist bounces to the module's list page (matching `MultitrackSessionAdmin.changelist_view`). `canvas_state` is excluded from default fields and shown as a collapsible JSON display.

```python
# Source: planner/admin.py:5906-5942 (MultitrackSessionAdmin)
# + ARCHITECTURE.md admin definition

@admin.register(SignalFlowDiagram, site=showstack_admin_site)
class SignalFlowDiagramAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'project', 'updated_at']
    list_filter = ['project']
    readonly_fields = ['canvas_state_display', 'version', 'created_at', 'updated_at']
    exclude = ['canvas_state', 'viewport']

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        return redirect('planner:signal_flow_list')

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

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_delete_permission(request, obj)
```

### Pattern 10: admin_ordering.py — Two Changes Required

**What:** Both the `order_map` entry AND the `always_hidden` entry must be added in the same commit. Missing either causes problems.

```python
# Source: planner/admin_ordering.py:73-91 (always_hidden) + 169-170 (order_map)

# In always_hidden set — add:
'signalflowdiagram',   # editor lives at /audiopatch/signal-flow/; admin changelist
                        # is for superuser inspection only, not end-user navigation.
                        # Same pattern as multitracksession / multitracktemplate.

# In order_map dict — add:
'signalflowdiagram': 52,   # after multitracktemplate: 51
```

**Why both are required:** `always_hidden` prevents the model from appearing in the sidebar. `order_map` sets the sort position in case `always_hidden` is ever removed. CLAUDE.md: "Update `admin_ordering.py` whenever a new admin-registered model is added."

### Pattern 11: signal_flow_editor.js — Phase 7 Stub

**What:** Minimal JS that confirms JointJS loaded and reads `data-*` constants. No canvas init.

```javascript
// planner/static/planner/js/signal_flow_editor.js
// Phase 7 stub — confirms vendor JS loaded; canvas init in Phase 8.

(function () {
  'use strict';

  const container = document.getElementById('sfd-container');
  if (!container) return;

  const diagramId = container.dataset.diagramId;
  const stateUrl = container.dataset.stateUrl;
  const autosaveUrl = container.dataset.autosaveUrl;

  // Confirm JointJS UMD bundle loaded and exposes `joint` global.
  if (typeof joint === 'undefined') {
    console.error('[SFD] joint is not defined — check vendor/joint.min.js load');
    return;
  }

  console.log('[SFD] JointJS ready — version', joint.version,
              '— diagram', diagramId);
  // Phase 8 wires: graph + paper init, graph.fromJSON(stateUrl), shape picker.
  // Phase 9 wires: autosave debounce, keepalive on visibilitychange.
})();
```

### Pattern 12: THIRD_PARTY_LICENSES.txt

**What:** Required by MPL-2.0 terms for `joint.min.js`. Created at project root.

```
# Third-Party Licenses
# ShowStack — Lawson Design & Engineering

## @joint/core 4.2.4
License: Mozilla Public License 2.0 (MPL-2.0)
Source: https://github.com/clientIO/joint
Vendored as: planner/static/planner/js/vendor/joint.min.js
Modifications: None. File vendored unmodified.

## html-to-image 1.11.11
License: MIT
Source: https://github.com/bubkoo/html-to-image
Vendored as: planner/static/planner/js/vendor/html-to-image.min.js
Modifications: None. File vendored unmodified.

## Sortable.js (existing)
License: MIT
Source: https://github.com/SortableJS/Sortable
Vendored as: planner/static/planner/js/vendor/Sortable.min.js
Modifications: None. File vendored unmodified.
```

### Anti-Patterns to Avoid

- **Registering on `admin.site` instead of `showstack_admin_site`:** CLAUDE.md: "Always register models on `showstack_admin_site`, NOT `admin.site`."
- **Updating only `order_map` without `always_hidden` (or vice versa):** Both required per CLAUDE.md and the Crew module precedent.
- **Adding `version` or `viewport` to a later migration:** Both fields are trivial to add now. Adding them in Phase 8 or 9 creates an extra migration with no benefit.
- **Using `element.style.color = value` in admin-adjacent JS:** CLAUDE.md: "Use `element.style.setProperty('color', value, 'important')`." Applies to any HTML elements near the Django admin DOM. JointJS SVG canvas is unaffected.
- **Embedding `canvas_state` as inline JSON in `editor.html`:** The locked decision (STATE.md #5) requires a separate `GET .../state/` endpoint. Phase 7's stub `signal_flow_state` view returns the (empty) JSON. The HTML shell stays clean.
- **`@csrf_exempt` on any stub view:** All existing AJAX views in the codebase avoid `@csrf_exempt`. The editor shell includes `<form style="display:none">{% csrf_token %}</form>` so the CSRF cookie is set.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Canvas rendering | Custom SVG/canvas system | JointJS (already decided) | Vetted in prior research phases |
| PNG export | Canvas API manually | `html-to-image` (Phase 10) | Font tainting, scroll offset edge cases |
| Project-scoping middleware | URL-based project ID param | `CurrentProjectMiddleware` + `request.current_project` | CLAUDE.md convention; IDOR-safe |
| JSON serialization of canvas | Custom format | `graph.toJSON()` / `graph.fromJSON()` | JointJS standard; `cellNamespace` registration in Phase 8 |
| Vendor JS serving | CDN in prod | Whitenoise static files | No CDN dependency at runtime; consistent with Sortable.min.js |

**Key insight:** Phase 7 contains zero novel patterns. Every piece maps directly to an existing module's code.

---

## Common Pitfalls

### Pitfall 1: `admin_ordering.py` Missing Update
**What goes wrong:** `SignalFlowDiagramAdmin` is registered but `admin_ordering.py` is not updated. The model appears at sort position 999 in the sidebar (or at a random position if Django's default sort changes).
**Why it happens:** Developers remember admin.py but forget admin_ordering.py.
**How to avoid:** Same commit. One plan task covers both `admin.py` and `admin_ordering.py` changes.
**Warning signs:** Sidebar has a misplaced "Signal Flow Diagrams" entry after deploy.

### Pitfall 2: `version` and `viewport` Fields Added Later
**What goes wrong:** Phase 8 or 9 needs these fields and has to create a second migration.
**Why it happens:** Deferred field addition seems safe, but both fields are part of the Phase 7 model spec.
**How to avoid:** Include both in `0158_signalflowdiagram.py`. Zero cost in Phase 7; avoids a wasted migration later.

### Pitfall 3: collectstatic Failure on Vendor JS
**What goes wrong:** `joint.min.js` or `html-to-image.min.js` have a `url()` reference (CSS-style) that Whitenoise's `CompressedManifestStaticFilesStorage` cannot resolve. Railway deploy blocks.
**Why it happens:** `@joint/core` 4.x does NOT require a CSS file, so `joint.min.js` has no `url()` references. But this must be verified locally before pushing.
**How to avoid:** After downloading vendor files, run `python manage.py collectstatic --noinput` locally. Success = safe to push. This is listed as a Phase 7 success criterion.
**Warning signs:** Railway deploy shows old code after push (Procfile collectstatic step failed silently).

### Pitfall 4: IDOR via Missing `project` Filter
**What goes wrong:** A view uses `SignalFlowDiagram.objects.get(id=diagram_id)` without `project=request.current_project`. Any authenticated user can read or modify any diagram across all projects.
**Why it happens:** Django admin pattern (`get_object_or_404`) is convenient but does not scope to project.
**How to avoid:** Use `_get_diagram_for_request(request, diagram_id)` for every diagram lookup. Never a bare `.get()` or `get_object_or_404` without a project filter.

### Pitfall 5: Viewer Can Reach Mutate Endpoints
**What goes wrong:** A Viewer-role user sends a POST to `signal_flow_create` and creates a diagram.
**Why it happens:** `@login_required` only checks authentication, not role.
**How to avoid:** Every POST/mutate view calls `_signal_flow_viewer_block(request)` as the first check. `@login_required` alone is not sufficient.

### Pitfall 6: PROJECT.md License Correction Missed
**What goes wrong:** `PROJECT.md` line 51 says "JointJS core (MIT)" and line 100 says "JointJS core (MIT)". These are factually wrong. If left uncorrected, future developers may rely on the MIT claim.
**Why it happens:** The license was mis-stated in PROJECT.md during v2.2 scope definition.
**How to avoid:** Phase 7 plan includes a task to correct both occurrences of "MIT" → "MPL-2.0" in `.planning/PROJECT.md`. `THIRD_PARTY_LICENSES.txt` creation happens in the same task.

---

## Code Examples

### List View (verified pattern)
```python
# Source: planner/views.py:5806-5839 (multitrack_dashboard) — adapted

@staff_member_required
def signal_flow_list(request):
    """List view of SignalFlowDiagrams for the current project (DGM-01)."""
    current_project = getattr(request, 'current_project', None)
    diagrams = (
        SignalFlowDiagram.objects.filter(project=current_project)
        .order_by('-updated_at')
        if current_project else SignalFlowDiagram.objects.none()
    )
    return render(request, 'planner/signal_flow/list.html', {
        'diagrams': diagrams,
        'current_project': current_project,
    })
```

### Editor Shell View
```python
# Source: planner/views.py:6031-6053 (multitrack_editor) — adapted

@staff_member_required
def signal_flow_editor(request, diagram_id):
    """Render the HTML editor shell (DGM-05).
    Canvas state is fetched separately via signal_flow_state.
    """
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    diagram = SignalFlowDiagram.objects.filter(
        id=diagram_id, project=current_project
    ).first()
    if not diagram:
        return redirect('planner:signal_flow_list')

    return render(request, 'planner/signal_flow/editor.html', {
        'diagram': diagram,
    })
```

### Delete View (CASCADE cleans up)
```python
# Source: planner/views.py:6262-6290 (multitrack_delete) — adapted
# No child table to worry about: SignalFlowDiagram is a single table.
# canvas_state (JSONField) is deleted atomically with the row.

@login_required
@require_POST
def signal_flow_delete(request, diagram_id):
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        project = getattr(request, 'current_project', None)
        if not project:
            return JsonResponse({'error': 'No active project'}, status=400)

        diagram = _get_diagram_for_request(request, diagram_id)
        if not diagram:
            return JsonResponse({'error': 'Not found'}, status=404)

        diagram.delete()
        return JsonResponse({
            'ok': True,
            'redirect_url': reverse('planner:signal_flow_list'),
        })
    except Exception:
        _signal_flow_logger.exception('signal_flow_delete failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JointJS v3 (Backbone + jQuery + lodash deps) | `@joint/core` 4.2.4 (zero deps, UMD bundle) | Feb 2024 (v4.0) | No `<script>` tags for Backbone/jQuery; single file vendor |
| `django-jsonfield` (third-party) | `models.JSONField` (Django built-in) | Django 3.1 (2020) | Remove third-party dep; native PostgreSQL `jsonb` |
| `dom-to-image` | `html-to-image` 1.11.11 | 2019 fork | `dom-to-image` unmaintained; `html-to-image` is the active maintained fork |

**Deprecated/outdated:**
- `jointjs` (npm package name): Renamed to `@joint/core` in v4.0 (Feb 2024). Do not use the old package name.
- `joint.css` with JointJS 4.x: CSS file is no longer required for `@joint/core`. Only needed for JointJS+.

---

## Runtime State Inventory

> Phase 7 is a greenfield module addition with no rename/refactor component. No runtime state exists for SignalFlowDiagram because the model does not exist yet.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — `SignalFlowDiagram` table does not yet exist | None |
| Live service config | None | None |
| OS-registered state | None | None |
| Secrets/env vars | None | None |
| Build artifacts | None | None |

**`THIRD_PARTY_LICENSES.txt`:** Does not exist yet. Phase 7 creates it. `[VERIFIED: ls project root]`

---

## Open Questions

1. **Dashboard / admin index nav link placement**
   - What we know: The main dashboard (`templates/planner/dashboard.html:318`) has a `quick-action` block with Multitrack Sessions. The admin index (`templates/admin/index.html:191`) has a `ss-node` card for Multitrack.
   - What's unclear: Whether Signal Flow Diagrammer should appear in both locations, or only one of them, and whether to add it to the existing flow-chain in the admin index SVG diagram.
   - Recommendation: Add to both, matching the Multitrack entry style. For the admin index, append a new `ss-node` card in the signal-chain section. The planner can decide exact position; this does not affect Phase 7 correctness.

2. **`signal_flow_list` URL — `/audiopatch/signal-flow/` or `/audiopatch/signal-flow/list/`**
   - What we know: Multitrack uses `/audiopatch/multitrack/` (no trailing `list/`) for its dashboard.
   - Recommendation: Use `/audiopatch/signal-flow/` (no `list/`) to match the multitrack convention.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Django 5.x | All views, model | ✓ | 5.x (Railway + local) | — |
| PostgreSQL | `JSONField` as `jsonb` | ✓ | Railway-managed | SQLite (local dev; JSONField stored as text, works) |
| Whitenoise | Static file serving | ✓ | 6.x | — |
| `curl` | Vendor file download | ✓ | macOS built-in | `wget` or direct browser download |
| `python manage.py collectstatic` | Gate test for vendor files | ✓ | Via `python manage.py` | — |

No missing dependencies.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + Django test runner (existing) |
| Config file | No pytest.ini detected — tests run via `python manage.py test` |
| Quick run command | `python manage.py test planner.tests.test_signal_flow_foundation --verbosity=2` |
| Full suite command | `python manage.py test planner` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DGM-01 | List page renders diagrams for current project | Integration | `python manage.py test planner.tests.test_signal_flow_foundation.SignalFlowListTests` | ❌ Wave 0 |
| DGM-02 | Create scopes diagram to current_project | Integration | `python manage.py test planner.tests.test_signal_flow_foundation.SignalFlowCreateTests` | ❌ Wave 0 |
| DGM-03 | Rename enforces unique_together | Integration | `python manage.py test planner.tests.test_signal_flow_foundation.SignalFlowRenameTests` | ❌ Wave 0 |
| DGM-04 | Delete removes diagram row | Integration | `python manage.py test planner.tests.test_signal_flow_foundation.SignalFlowDeleteTests` | ❌ Wave 0 |
| DGM-05 | Cross-project access returns 404 | Integration (security) | `python manage.py test planner.tests.test_signal_flow_foundation.SignalFlowIDORTests` | ❌ Wave 0 |
| DGM-08 | editor.html has data-autosave-url attribute | Unit | `python manage.py test planner.tests.test_signal_flow_foundation.SignalFlowEditorShellTests` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python manage.py test planner.tests.test_signal_flow_foundation -x`
- **Per wave merge:** `python manage.py test planner`
- **Phase gate:** Full `planner` suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `planner/tests/test_signal_flow_foundation.py` — covers DGM-01 through DGM-05 + DGM-08 editor shell
- [ ] Test fixtures: two `Project` instances (owner + another), one `User` per project, `Viewer` group

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `@login_required` + `@staff_member_required` on all views |
| V3 Session Management | yes (inherit) | Django session middleware — no new session logic |
| V4 Access Control | yes — critical | `_signal_flow_viewer_block` + `filter(project=request.current_project)` IDOR guard |
| V5 Input Validation | yes | `name` length check (≤ 200 chars), `strip()`, unique-together enforcement server-side |
| V6 Cryptography | no | No new cryptographic operations |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-project diagram read/write (IDOR) | Information Disclosure + Tampering | `filter(id=..., project=request.current_project)` on every queryset — `_get_diagram_for_request` helper |
| Viewer-role user creating/modifying diagrams | Elevation of Privilege | `_signal_flow_viewer_block` on all POST/mutate endpoints |
| CSRF on create/rename/delete POST | Tampering | `@login_required` + standard Django CSRF middleware; `{% csrf_token %}` in hidden form in editor shell |
| XSS via `diagram.name` in template | XSS | Django template auto-escaping; `|escapejs` for JS `data-diagram-name` attribute |
| SQL injection via name input | Tampering | Django ORM parameterized queries; no raw SQL |

---

## Project Constraints (from CLAUDE.md)

| Directive | Applies to Phase 7 |
|-----------|-------------------|
| Always register on `showstack_admin_site`, NOT `admin.site` | Yes — `SignalFlowDiagramAdmin` |
| Update `admin_ordering.py` whenever a new admin-registered model is added | Yes — `order_map: 52` + `always_hidden` entry |
| Additive migrations only | Yes — single `0158_signalflowdiagram.py`, no edits to existing tables |
| No new Python dependencies | Yes — confirmed; all built-in |
| Do not run destructive SQL against Railway without confirming with Charlie | Not applicable to Phase 7 (additive only) |
| Do not commit `.env`, API keys, Railway tokens | Not applicable |
| Session-based project resolution (`CurrentProjectMiddleware`) | Yes — all views use `getattr(request, 'current_project', None)` |
| Never URL-route project IDs | Yes — URLs use `diagram_id` only; project scoping is via middleware |
| Railway uses `railway.json` startCommand, NOT Procfile | Not modified in Phase 7 |
| Defence-in-depth at AJAX boundary | Yes — server-side role check + IDOR guard on all mutate endpoints |
| Django admin CSS `!important` override: use `element.style.setProperty` | Applies if Phase 7 JS modifies admin DOM elements (editor shell HTML is not admin-themed DOM, but keep in mind) |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `0158_signalflowdiagram.py` is the correct next migration number | Standard Stack / Model | Conflict with another migration; `makemigrations` will auto-detect and choose next available number, so risk is naming only |
| A2 | `html-to-image.min.js` CDN URL at cdnjs `1.11.11` is still accessible | Standard Stack | Download fails; fallback: use jsDelivr CDN `https://cdn.jsdelivr.net/npm/html-to-image@1.11.11/dist/html-to-image.min.js` |
| A3 | The admin index (`templates/admin/index.html`) is the correct file to add a Signal Flow nav node | Open Questions | Wrong template patched; discoverable by inspecting the admin index in the browser |

**All other claims in this research were verified via direct codebase inspection or cited from prior research phases (STACK.md, ARCHITECTURE.md, PITFALLS.md, all 2026-05-19).**

---

## Sources

### Primary (HIGH confidence)
- `planner/models.py` — direct inspection: `MultitrackSession` model structure (lines 1111-1161)
- `planner/views.py` — direct inspection: `multitrack_dashboard` (5806), `multitrack_create_view` (6057), `multitrack_editor` (6031), `multitrack_rename` (6219), `multitrack_delete` (6264), `_get_track_for_request` (6328), `_multitrack_viewer_block` (6315)
- `planner/urls.py` — direct inspection: multitrack URL block (lines 99-140), `app_name = 'planner'` (line 25)
- `planner/admin.py` — direct inspection: `MultitrackSessionAdmin` (5906-5942)
- `planner/admin_ordering.py` — direct inspection: `always_hidden` set (73-91), `order_map` (94-171), `multitracksession: 50`, `multitracktemplate: 51`
- `planner/templates/planner/multitrack/dashboard.html` — direct inspection: template structure, extends `admin/base_site.html`, CSRF hidden form pattern
- `planner/templates/planner/multitrack/editor.html` — direct inspection: `data-mts-session-id` attribute injection pattern
- `planner/static/planner/js/vendor/` — direct inspection: `Sortable.min.js` exists; `joint.min.js` does not yet exist
- `planner/migrations/` — direct inspection: last migration is `0157_crew_crewmember_crewprojectadd.py`; next is `0158`
- `THIRD_PARTY_LICENSES.txt` — direct inspection: does not exist at project root
- `.planning/research/STACK.md` (2026-05-19) — JointJS 4.2.4 MPL-2.0, html-to-image 1.11.11 MIT, vendor download URLs
- `.planning/research/ARCHITECTURE.md` (2026-05-19) — model definition, URL table, admin pattern, build order
- `.planning/research/PITFALLS.md` (2026-05-19) — IDOR, MPL-2.0 compliance, version/viewport fields, cellNamespace
- `.planning/research/SUMMARY.md` (2026-05-19) — executive summary, locked decisions
- `CLAUDE.md` (2026-05-19) — admin site convention, admin_ordering rule, Railway deploy, CSRF convention, !important CSS rule

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` (2026-05-19) — DGM-01..DGM-08 requirement text, traceability table
- `.planning/ROADMAP.md` (2026-05-19) — Phase 7 success criteria

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — no new dependencies; all patterns from existing codebase
- Architecture: HIGH — direct code inspection; multitrack is a verified analog
- Pitfalls: HIGH — verified against existing code + prior PITFALLS.md research
- Security: HIGH — IDOR pattern verified at views.py:6328-6342; viewer block at views.py:6315-6325

**Research date:** 2026-05-19
**Valid until:** Stable — Django 5.x + JointJS 4.2.4 pinned; 90-day validity
