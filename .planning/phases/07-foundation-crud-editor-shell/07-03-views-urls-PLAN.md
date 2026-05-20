---
phase: 07
plan: 03
type: execute
wave: 2
depends_on:
  - "07-01"
files_modified:
  - planner/views.py
  - planner/urls.py
autonomous: true
requirements:
  - DGM-01
  - DGM-02
  - DGM-03
  - DGM-04
  - DGM-05
  - DGM-08
user_setup: []

must_haves:
  truths:
    - "GET /audiopatch/signal-flow/ renders the list page with diagrams scoped to request.current_project"
    - "POST /audiopatch/signal-flow/create/ creates a SignalFlowDiagram in the current project and returns {ok, redirect_url}"
    - "POST /audiopatch/signal-flow/<id>/rename/ enforces unique-per-project name; duplicate returns HTTP 409"
    - "POST /audiopatch/signal-flow/<id>/delete/ removes the diagram and returns {ok, redirect_url}"
    - "Cross-project access (diagram_id from another project) returns 404, not 200 or redirect-with-data-leak"
    - "All 9 URL names resolvable via reverse(): signal_flow_list, signal_flow_create, signal_flow_editor, signal_flow_state, signal_flow_autosave, signal_flow_rename, signal_flow_delete, signal_flow_autocomplete, signal_flow_export_png"
    - "Viewer-role users get HTTP 403 from create/rename/delete/autosave endpoints"
    - "signal_flow_autosave stub returns 200 {ok: true, stub: true} so Plan 04 editor.html data-autosave-url URL resolution succeeds (DGM-08 stub satisfied)"
  artifacts:
    - path: "planner/views.py"
      provides: "9 signal_flow view functions + 2 helpers (_signal_flow_viewer_block, _get_diagram_for_request)"
      contains: "def signal_flow_list"
    - path: "planner/urls.py"
      provides: "9 URL patterns for the signal-flow namespace"
      contains: "signal-flow/"
  key_links:
    - from: "planner/views.py signal_flow_create"
      to: "planner.models.SignalFlowDiagram"
      via: "SignalFlowDiagram.objects.create(project=project, name=name)"
      pattern: "SignalFlowDiagram.objects.create"
    - from: "planner/views.py _get_diagram_for_request"
      to: "request.current_project (IDOR guard)"
      via: "filter(id=diagram_id, project=project)"
      pattern: "filter\\(id=diagram_id, project=project\\)"
    - from: "planner/urls.py signal-flow URL block"
      to: "planner.views signal_flow_* functions"
      via: "path('signal-flow/...', views.signal_flow_*, name='signal_flow_*')"
      pattern: "name='signal_flow_"
---

<objective>
Add the complete view layer (9 functions + 2 helpers) and the 9 URL patterns for the Signal Flow Diagrammer. This plan delivers DGM-01 through DGM-05 fully (list/create/rename/delete/IDOR guard) and the URL stub portion of DGM-08 (autosave URL must exist so editor.html `{% url 'planner:signal_flow_autosave' diagram.id %}` resolves in Plan 04). The remaining state, autocomplete, and export-png endpoints are stubs that Phases 9 and 10 will fill — they exist now only so the editor.html shell's `data-*` URL attributes resolve cleanly.

Purpose: The model from Plan 01 must be paired with HTTP endpoints before any UI can be built. Without this plan, Plan 04 templates cannot reverse() URL names and the editor shell cannot load.

Output: ~280 lines of new code in planner/views.py (appended at the bottom), 9 new path entries in planner/urls.py inside the existing planner namespace. Every endpoint exercises the IDOR-safe `_get_diagram_for_request` helper and the Viewer-role block.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/07-foundation-crud-editor-shell/07-RESEARCH.md
@.planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md
@CLAUDE.md

<interfaces>
<!-- The model from Plan 01 — required by every view here -->
From planner/models.py (created by Plan 07-01):
- class SignalFlowDiagram(models.Model)
  - project = ForeignKey(Project, on_delete=CASCADE, related_name='signal_flow_diagrams')
  - name = CharField(max_length=200)
  - canvas_state = JSONField(default=dict)
  - viewport = JSONField(default=dict)
  - version = IntegerField(default=1)
  - created_at, updated_at = DateTimeField
  - Meta.unique_together = [('project', 'name')]

<!-- Existing helper analog at views.py:6315 — copy pattern -->
From planner/views.py:6315-6325:
- def _multitrack_viewer_block(request):  # returns JsonResponse 403 if user in Viewer group else None

<!-- Existing helper analog at views.py:6328 — IDOR-safe lookup -->
From planner/views.py:6328-6342:
- def _get_track_for_request(request, track_id):
    project = getattr(request, 'current_project', None)
    if not project: return None
    return MultitrackTrack.objects.filter(id=track_id, session__project=project).first()

<!-- Existing CurrentProjectMiddleware -->
From planner/middleware.py:
- Sets request.current_project from session — access via getattr(request, 'current_project', None)

<!-- Existing urls.py pattern -->
From planner/urls.py:
- app_name = 'planner' (line 25)
- multitrack URL block at lines 99-140 — analog for the new signal-flow block
- Mount point: /audiopatch/ (audiopatch/urls.py mounts planner.urls)

<!-- Existing imports in views.py (already present, do NOT re-import) -->
From planner/views.py:1-30:
- from django.shortcuts import render, get_object_or_404, redirect
- from django.http import JsonResponse, HttpResponse
- from django.contrib.admin.views.decorators import staff_member_required
- from django.contrib.auth.decorators import login_required
- from django.views.decorators.http import require_POST
- import json
- from django.urls import reverse
- import logging
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Append 9 view functions + 2 helpers to planner/views.py</name>
  <files>planner/views.py</files>
  <read_first>
    - .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md (section: "planner/views.py — add 9 view functions" — entire section; the analog code at lines 6217-6342 of views.py is reproduced verbatim there)
    - .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md (sections: "Authentication", "Viewer-Role Guard", "IDOR-Safe Diagram Lookup", "Error Handling")
    - planner/views.py lines 6217-6342 — the multitrack rename/delete/duplicate/viewer-block/get-track helper analog code (read directly to confirm exact decorator and try/except style)
    - planner/views.py lines 5807-5839 — multitrack_dashboard analog (list view pattern)
    - planner/views.py lines 6030-6053 — multitrack_editor analog (page-render shell pattern)
    - .planning/phases/07-foundation-crud-editor-shell/07-RESEARCH.md (Pattern 1-7 — copy verbatim for each view)
    - CLAUDE.md "Session-based project resolution" (request.current_project; no URL-routed project IDs)
  </read_first>

  <behavior>
    - Two module-level helpers added: `_signal_flow_viewer_block(request)` returns 403 JSON for Viewer group else None; `_get_diagram_for_request(request, diagram_id)` returns SignalFlowDiagram filtered by project or None
    - 9 view functions added: signal_flow_list, signal_flow_create, signal_flow_editor, signal_flow_state, signal_flow_autosave, signal_flow_rename, signal_flow_delete, signal_flow_autocomplete, signal_flow_export_png
    - Every diagram_id-accepting view calls `_get_diagram_for_request` — never a bare .get() or get_object_or_404 without project filter
    - Every POST mutate view calls `_signal_flow_viewer_block(request)` as the first line of its body
    - signal_flow_list and signal_flow_editor use @staff_member_required; signal_flow_state/autocomplete/export_png use @staff_member_required (read-only); signal_flow_create/rename/delete/autosave use @login_required + @require_POST
    - signal_flow_autosave is a Phase 7 stub returning {ok: true, stub: true} — Phase 9 will replace with full implementation
    - signal_flow_autocomplete is a Phase 7 stub returning {results: []} — Phase 10 will replace
    - signal_flow_export_png is a Phase 7 stub returning HTTP 501 — Phase 10 will replace
    - SignalFlowDiagram model imported from .models at the top-of-file imports block
    - `python manage.py check` passes after the edit
  </behavior>

  <action>
**Step A — Add SignalFlowDiagram to the model import block:**

Open `planner/views.py`. Locate the top-of-file imports — specifically the existing line(s) that import planner models. Add `SignalFlowDiagram`. If there's already an existing `from .models import (... MultitrackSession, MultitrackTrack ...)` block, add `SignalFlowDiagram` to it (alphabetically near the M-prefixed entries is fine). If models are imported on a dedicated line, add a new line:

    from .models import SignalFlowDiagram

Place it adjacent to the MultitrackSession import for grep-ability.

**Step B — Append helpers + 9 views at the bottom of planner/views.py:**

Scroll to the end of `planner/views.py` (after the last existing function, likely a multitrack-related view). Append the following section verbatim (this includes a clearly-labeled header banner so future maintainers can find the block):

    # ──────────────────────────────────────────────────────────────────────────────
    # Signal Flow Diagrammer (v2.2) — DGM-01..DGM-05 + DGM-08 stub
    #
    # All views follow the multitrack module pattern. See
    # .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md for analogs.
    #
    # Helpers:
    #   _signal_flow_viewer_block — 403 for Viewer group (mirrors _multitrack_viewer_block at views.py:6315)
    #   _get_diagram_for_request  — IDOR-safe lookup (mirrors _get_track_for_request at views.py:6328)
    # ──────────────────────────────────────────────────────────────────────────────

    _signal_flow_logger = logging.getLogger(__name__)


    def _signal_flow_viewer_block(request):
        """Return JsonResponse 403 iff user is in Viewer group; else None.

        Mirrors _multitrack_viewer_block (views.py:6315). Centralised so every
        signal-flow mutate endpoint applies the same check.
        """
        if request.user.groups.filter(name='Viewer').exists():
            return JsonResponse({'error': 'Read-only access.'}, status=403)
        return None


    def _get_diagram_for_request(request, diagram_id):
        """Return SignalFlowDiagram iff it belongs to request.current_project.

        IDOR-safe lookup. Returns None when the diagram doesn't exist or belongs
        to a different project. Mirrors _get_track_for_request (views.py:6328).

        Enforces DGM-05: cross-project access yields None -> caller returns 404.
        """
        project = getattr(request, 'current_project', None)
        if not project:
            return None
        return SignalFlowDiagram.objects.filter(
            id=diagram_id, project=project
        ).first()


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


    @login_required
    @require_POST
    def signal_flow_create(request):
        """Create a new SignalFlowDiagram in the current project (DGM-02).

        POST body: {"name": "<diagram name>"}
        Returns: {"ok": true, "redirect_url": "/audiopatch/signal-flow/<id>/"}
        """
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


    @staff_member_required
    def signal_flow_editor(request, diagram_id):
        """Render the HTML editor shell (DGM-05).

        Canvas state is fetched separately via signal_flow_state — the shell
        does not embed inline JSON. Cross-project diagram_id returns the user
        to the list page (404-equivalent for a page render — no leak).
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


    @login_required
    @require_POST
    def signal_flow_rename(request, diagram_id):
        """Rename a diagram (DGM-03). Enforces unique-per-project name.

        POST body: {"name": "<new name>"}
        Returns: {"ok": true, "name": "<new name>"} or {"error": ...} with
        400/404/409/500 as appropriate.
        """
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


    @login_required
    @require_POST
    def signal_flow_delete(request, diagram_id):
        """Delete a diagram (DGM-04). CASCADE handles single-table cleanup.

        Returns: {"ok": true, "redirect_url": "/audiopatch/signal-flow/"}
        """
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


    # ── Stub endpoints (filled in Phase 8-10) ──────────────────────────────────

    @staff_member_required
    def signal_flow_state(request, diagram_id):
        """GET — return canvas_state JSON (Phase 7 stub; no _enrich_nodes yet).

        Phase 9 will enrich nodes for orphan rendering. Today this returns the
        raw blob plus the optimistic-locking version token.
        """
        diagram = _get_diagram_for_request(request, diagram_id)
        if not diagram:
            return JsonResponse({'error': 'Not found'}, status=404)
        return JsonResponse({
            'canvas_state': diagram.canvas_state,
            'viewport': diagram.viewport,
            'version': diagram.version,
        })


    @login_required
    @require_POST
    def signal_flow_autosave(request, diagram_id):
        """POST stub for DGM-08 (URL must exist for editor.html data-autosave-url).

        Phase 9 implements: optimistic locking via version field, equipment GFK
        validation, _enrich_nodes-aware save, HTTP 409 on conflict. For now the
        endpoint exists so {% url 'planner:signal_flow_autosave' diagram.id %}
        resolves in editor.html — the actual fetch behavior ships in Phase 9.
        """
        return JsonResponse({'ok': True, 'stub': True})


    @staff_member_required
    def signal_flow_autocomplete(request):
        """GET stub for circuit-label autocomplete (Phase 10 fills).

        URL must exist now so editor.html data-autocomplete-url resolves.
        """
        return JsonResponse({'results': []})


    @staff_member_required
    def signal_flow_export_png(request, diagram_id):
        """GET stub for PNG export (Phase 10 fills via html-to-image).

        URL must exist now so editor.html data-export-png-url resolves.
        """
        return JsonResponse({'error': 'Not yet implemented'}, status=501)

CRITICAL details:
- Decorator stack on AJAX mutate views MUST be exactly `@login_required` THEN `@require_POST` (top-down). Reversing them is a known foot-gun.
- Page-render views (`signal_flow_list`, `signal_flow_editor`) use `@staff_member_required` per multitrack precedent. Read-only stub endpoints (`state`, `autocomplete`, `export_png`) use `@staff_member_required` because Phase 10 will use them to read project data and the staff gate is appropriate.
- `signal_flow_autosave` MUST NOT include `@csrf_exempt` — the editor shell's hidden `{% csrf_token %}` form (Plan 04) sets the cookie; the AJAX client sends `X-CSRFToken` header (Phase 9).
- All five POST mutate / read endpoints accepting `diagram_id` route through `_get_diagram_for_request` (signal_flow_rename, signal_flow_delete, signal_flow_state, signal_flow_autosave is the stub-pass-through and does NOT need the check today but Phase 9 will add it). `signal_flow_editor` uses an inline filter (matches multitrack_editor analog) since it's a page render that needs `redirect()` not JsonResponse.
- The `_signal_flow_logger` is `logging.getLogger(__name__)` — same module-level pattern as the existing `_multitrack_logger`. If `logging` is not already imported in views.py near the top, add `import logging` to the imports block (a quick grep will confirm).

**Step C — Verify imports + check:**

Run:

    python manage.py check

Output must contain `System check identified no issues (0 silenced).` and no `ImportError` referencing SignalFlowDiagram.

Then verify the new helpers and views are reachable via Python import:

    python manage.py shell -c "from planner.views import signal_flow_list, signal_flow_create, signal_flow_editor, signal_flow_state, signal_flow_autosave, signal_flow_rename, signal_flow_delete, signal_flow_autocomplete, signal_flow_export_png, _signal_flow_viewer_block, _get_diagram_for_request; print('All 11 symbols imported')"

Must print `All 11 symbols imported`.
  </action>

  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && python manage.py check && python manage.py shell -c "from planner.views import signal_flow_list, signal_flow_create, signal_flow_editor, signal_flow_state, signal_flow_autosave, signal_flow_rename, signal_flow_delete, signal_flow_autocomplete, signal_flow_export_png, _signal_flow_viewer_block, _get_diagram_for_request; print('All 11 symbols imported')"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "def signal_flow_list" planner/views.py` returns 1
    - `grep -c "def signal_flow_create" planner/views.py` returns 1
    - `grep -c "def signal_flow_editor" planner/views.py` returns 1
    - `grep -c "def signal_flow_state" planner/views.py` returns 1
    - `grep -c "def signal_flow_autosave" planner/views.py` returns 1
    - `grep -c "def signal_flow_rename" planner/views.py` returns 1
    - `grep -c "def signal_flow_delete" planner/views.py` returns 1
    - `grep -c "def signal_flow_autocomplete" planner/views.py` returns 1
    - `grep -c "def signal_flow_export_png" planner/views.py` returns 1
    - `grep -c "def _signal_flow_viewer_block" planner/views.py` returns 1
    - `grep -c "def _get_diagram_for_request" planner/views.py` returns 1
    - `grep -c "filter(id=diagram_id, project=project)" planner/views.py` returns at least 1 (inside _get_diagram_for_request)
    - `grep -c "filter(id=diagram_id, project=current_project)" planner/views.py` returns at least 1 (inside signal_flow_editor)
    - `grep -c "@csrf_exempt" planner/views.py` returns the same value as before this task (no new @csrf_exempt added — capture baseline before editing if needed)
    - `python manage.py check` exits 0
    - `python manage.py shell -c "from planner.views import signal_flow_list, signal_flow_create, _get_diagram_for_request; print('OK')"` prints `OK`
  </acceptance_criteria>

  <done>
    All 9 view functions and 2 helpers are present in planner/views.py at the bottom, properly decorated, and importable. SignalFlowDiagram is imported in the views.py imports block. `python manage.py check` passes cleanly.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Append 9 URL patterns to planner/urls.py</name>
  <files>planner/urls.py</files>
  <read_first>
    - .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md (section: "planner/urls.py — add 9 URL patterns")
    - planner/urls.py lines 99-140 — the multitrack URL block; exact comment/format style for the new block to mirror
    - planner/urls.py line 25 — confirm `app_name = 'planner'` (URL names will be reversed as 'planner:signal_flow_*')
    - .planning/phases/07-foundation-crud-editor-shell/07-RESEARCH.md (Pattern 8: URL Block)
  </read_first>

  <behavior>
    - 9 new path() entries added to urlpatterns list in planner/urls.py
    - Static paths (`signal-flow/`, `signal-flow/create/`, `signal-flow/autocomplete/`) come BEFORE `signal-flow/<int:diagram_id>/...` patterns (convention from multitrack block at lines 109-115)
    - All 9 URL names follow the convention `signal_flow_*` (underscore-separated, matching view function names exactly)
    - The block has a clearly-labeled header comment marking it as the v2.2 Signal Flow block
    - All 9 URLs reverse cleanly via `reverse('planner:<name>')` (with appropriate args for diagram_id-based names)
    - `python manage.py check` passes
  </behavior>

  <action>
**Step A — Locate the insertion point in planner/urls.py:**

Open `planner/urls.py`. Find the multitrack URL block (lines ~99-140). The block ends at a line containing the last multitrack path (e.g. `path('multitrack/<int:session_id>/export.nlpr/', ...)` or similar). Identify the closing `]` of `urlpatterns = [...]` if it's nearby.

The new signal-flow block should be appended AFTER the entire multitrack block, BEFORE the closing `]` of `urlpatterns`. If there are other unrelated blocks after multitrack (e.g. crew, COMM config), place the signal-flow block at the end — adjacent to the closing `]`.

**Step B — Insert the URL block verbatim:**

Add the following lines inside `urlpatterns = [...]`:

        # ── Signal Flow Diagrammer (v2.2) ─────────────────────────────────────────
        # DGM-01..DGM-05 + DGM-08 (autosave URL stub).
        #
        # IMPORTANT: signal-flow/create/ and signal-flow/autocomplete/ MUST come
        # BEFORE signal-flow/<int:diagram_id>/ — the int converter matches only \d+,
        # so "create" / "autocomplete" would not be captured as diagram_id, but
        # static-paths-before-param-paths is the explicit convention in this
        # codebase (see urls.py multitrack block at lines 109-115).
        path('signal-flow/', views.signal_flow_list, name='signal_flow_list'),
        path('signal-flow/create/', views.signal_flow_create, name='signal_flow_create'),
        path('signal-flow/autocomplete/', views.signal_flow_autocomplete, name='signal_flow_autocomplete'),
        path('signal-flow/<int:diagram_id>/', views.signal_flow_editor, name='signal_flow_editor'),
        path('signal-flow/<int:diagram_id>/state/', views.signal_flow_state, name='signal_flow_state'),
        path('signal-flow/<int:diagram_id>/save/', views.signal_flow_autosave, name='signal_flow_autosave'),
        path('signal-flow/<int:diagram_id>/rename/', views.signal_flow_rename, name='signal_flow_rename'),
        path('signal-flow/<int:diagram_id>/delete/', views.signal_flow_delete, name='signal_flow_delete'),
        path('signal-flow/<int:diagram_id>/export.png/', views.signal_flow_export_png, name='signal_flow_export_png'),

Match the indentation of existing path() entries (typically 4 spaces — inspect surrounding lines).

URL name -> view function mapping (must match exactly):
- `signal_flow_list` -> views.signal_flow_list
- `signal_flow_create` -> views.signal_flow_create
- `signal_flow_autocomplete` -> views.signal_flow_autocomplete
- `signal_flow_editor` -> views.signal_flow_editor
- `signal_flow_state` -> views.signal_flow_state
- `signal_flow_autosave` -> views.signal_flow_autosave
- `signal_flow_rename` -> views.signal_flow_rename
- `signal_flow_delete` -> views.signal_flow_delete
- `signal_flow_export_png` -> views.signal_flow_export_png

URL kwargs mapping (must match view signatures):
- `signal_flow_list`, `signal_flow_create`, `signal_flow_autocomplete`: no args
- `signal_flow_editor`, `signal_flow_state`, `signal_flow_autosave`, `signal_flow_rename`, `signal_flow_delete`, `signal_flow_export_png`: `diagram_id` (int)

**Step C — Verify URL resolution:**

Run system check:

    python manage.py check

Output must contain `System check identified no issues (0 silenced).`

Then resolve every URL name to confirm they reverse correctly:

    python manage.py shell -c "from django.urls import reverse; print(reverse('planner:signal_flow_list')); print(reverse('planner:signal_flow_create')); print(reverse('planner:signal_flow_autocomplete')); print(reverse('planner:signal_flow_editor', args=[1])); print(reverse('planner:signal_flow_state', args=[1])); print(reverse('planner:signal_flow_autosave', args=[1])); print(reverse('planner:signal_flow_rename', args=[1])); print(reverse('planner:signal_flow_delete', args=[1])); print(reverse('planner:signal_flow_export_png', args=[1]))"

Expected output (one per line, in order):

    /audiopatch/signal-flow/
    /audiopatch/signal-flow/create/
    /audiopatch/signal-flow/autocomplete/
    /audiopatch/signal-flow/1/
    /audiopatch/signal-flow/1/state/
    /audiopatch/signal-flow/1/save/
    /audiopatch/signal-flow/1/rename/
    /audiopatch/signal-flow/1/delete/
    /audiopatch/signal-flow/1/export.png/

Any `NoReverseMatch` exception means a URL name is misspelled or a view function signature doesn't match the path() converters.
  </action>

  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && python manage.py check && python manage.py shell -c "from django.urls import reverse; names=['signal_flow_list','signal_flow_create','signal_flow_autocomplete']; [print(reverse('planner:'+n)) for n in names]; id_names=['signal_flow_editor','signal_flow_state','signal_flow_autosave','signal_flow_rename','signal_flow_delete','signal_flow_export_png']; [print(reverse('planner:'+n, args=[1])) for n in id_names]"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "name='signal_flow_list'" planner/urls.py` returns 1
    - `grep -c "name='signal_flow_create'" planner/urls.py` returns 1
    - `grep -c "name='signal_flow_autocomplete'" planner/urls.py` returns 1
    - `grep -c "name='signal_flow_editor'" planner/urls.py` returns 1
    - `grep -c "name='signal_flow_state'" planner/urls.py` returns 1
    - `grep -c "name='signal_flow_autosave'" planner/urls.py` returns 1
    - `grep -c "name='signal_flow_rename'" planner/urls.py` returns 1
    - `grep -c "name='signal_flow_delete'" planner/urls.py` returns 1
    - `grep -c "name='signal_flow_export_png'" planner/urls.py` returns 1
    - Total grep count for `name='signal_flow_` = 9
    - `python manage.py check` exits 0
    - `python manage.py shell` reverse() commands print 9 URL paths matching the expected list above
  </acceptance_criteria>

  <done>
    All 9 path() entries are present in planner/urls.py inside the existing urlpatterns list, ordered with static paths before <int:diagram_id> paths. Every URL name reverses correctly via `reverse('planner:<name>')`. `python manage.py check` passes.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 3: Functional smoke test — create, rename, delete, IDOR isolation via test client</name>
  <files>planner/views.py, planner/urls.py</files>
  <read_first>
    - .planning/phases/07-foundation-crud-editor-shell/07-RESEARCH.md (section: "Phase Requirements -> Test Map" and "Security Domain")
    - planner/tests/ (read the directory listing to see how existing planner tests structure imports and Project/User fixtures — `ls planner/tests/`)
    - Outputs of Tasks 1 and 2 in this plan — verify the helpers and URL names exist before running smoke tests
  </read_first>

  <behavior>
    - Anonymous request to /audiopatch/signal-flow/ redirects to login (staff_member_required is enforced)
    - Authenticated staff user with no active project on /audiopatch/signal-flow/ gets a sensible response (200 with empty diagram list, NOT 500)
    - POST to /audiopatch/signal-flow/create/ with {"name": "Smoke Test"} returns 200 with ok=true (when authenticated as a staff user with a current_project; depends on the test client's session middleware)
    - The IDOR guard returns 404 (not 200) when an authenticated user from Project A requests a diagram_id belonging to Project B
    - No 500 errors anywhere — only 4xx for expected reject paths
  </behavior>

  <action>
This task performs an end-to-end smoke test via Django's test client to validate that the views from Task 1 and URL patterns from Task 2 actually wire together correctly. It does NOT add a permanent test file — that work belongs to a future test plan. This is a one-time validation run via `manage.py shell`.

**Step A — Anonymous access check (staff_member_required enforcement):**

    python manage.py shell -c "from django.test import Client; c = Client(); r = c.get('/audiopatch/signal-flow/'); print('list anon status', r.status_code, 'redirect_to' if 300 <= r.status_code < 400 else '', r.get('Location', ''))"

Expected: status 302 (or 301) redirecting to a login URL. Status 200 means staff_member_required is broken; status 500 means an unhandled exception.

**Step B — URL resolution sanity (already covered by Task 2 acceptance, but reconfirm):**

    python manage.py shell -c "from django.urls import reverse; print(reverse('planner:signal_flow_autosave', args=[42]))"

Expected output: `/audiopatch/signal-flow/42/save/` (or similar — confirms DGM-08 URL stub is reachable for Plan 04's editor.html data-autosave-url).

**Step C — Cross-project IDOR isolation:**

This requires two projects, two staff users, and a diagram. The full setup is verbose for a smoke check, so use this minimal-fixture approach:

    python manage.py shell <<'PYEOF'
    from django.contrib.auth import get_user_model
    from django.test import Client
    from planner.models import Project, SignalFlowDiagram

    User = get_user_model()

    # Use existing Projects if any exist; otherwise create two for the test
    projects = list(Project.objects.all()[:2])
    if len(projects) < 2:
        print("SKIP IDOR smoke: fewer than 2 projects in DB. Create test data manually if needed.")
    else:
        pA, pB = projects[0], projects[1]
        # Create a diagram on Project B
        d = SignalFlowDiagram.objects.create(project=pB, name='IDOR-smoke-test')
        # Simulate a request for that diagram via _get_diagram_for_request directly
        from planner.views import _get_diagram_for_request
        class FakeReq: pass
        req = FakeReq()
        req.current_project = pA   # User is in Project A
        diag = _get_diagram_for_request(req, d.id)
        if diag is None:
            print("IDOR guard OK: Project A cannot see Project B diagram")
        else:
            print("IDOR guard FAILED: Project A could read Project B diagram", d.id)
        # Clean up
        d.delete()
    PYEOF

Expected output line: `IDOR guard OK: Project A cannot see Project B diagram` — or `SKIP IDOR smoke: ...` if the DB has fewer than 2 projects.

If `IDOR guard FAILED` appears, STOP — the `_get_diagram_for_request` helper has a bug. The most likely cause is a missing `project=project` term in the filter() call.

**Step D — Confirm signal_flow_autosave returns 200 (DGM-08 stub):**

    python manage.py shell <<'PYEOF'
    from django.test import RequestFactory
    from django.contrib.auth import get_user_model
    from planner.views import signal_flow_autosave

    User = get_user_model()
    user = User.objects.filter(is_staff=True).first()
    if user is None:
        print("SKIP autosave stub: no staff user in DB")
    else:
        rf = RequestFactory()
        req = rf.post('/audiopatch/signal-flow/1/save/', data='{}', content_type='application/json')
        req.user = user
        resp = signal_flow_autosave(req, 1)
        print("autosave stub status", resp.status_code, "body", resp.content[:80])
    PYEOF

Expected: `autosave stub status 200 body b'{"ok": true, "stub": true}'` (or similar JSON serialization). 403 would mean the user is in the Viewer group (need a non-Viewer staff user); 500 would mean a coding error.

**Step E — Commit smoke results to the plan SUMMARY (not the codebase):**

This task does not change source files. Its purpose is to validate the views from Task 1 and URLs from Task 2 actually work end-to-end before Plan 04 templates reference them. Record the exact shell outputs in `.planning/phases/07-foundation-crud-editor-shell/07-03-SUMMARY.md` (per the `<output>` block of this plan).

If ANY of Steps A-D produced a 500 status, an unhandled exception traceback, or a `NoReverseMatch`, return to Task 1 or Task 2, fix the offending code, and rerun this task. Plan 04 cannot proceed until smoke-test status is green.
  </action>

  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch && python manage.py check && python manage.py shell -c "from django.test import Client; c = Client(); r = c.get('/audiopatch/signal-flow/'); assert r.status_code in (301, 302), f'expected redirect, got {r.status_code}'; print('list anon redirect OK')"</automated>
  </verify>

  <acceptance_criteria>
    - Anonymous GET /audiopatch/signal-flow/ returns 301 or 302 (staff_member_required redirects to login)
    - `reverse('planner:signal_flow_autosave', args=[42])` returns `/audiopatch/signal-flow/42/save/`
    - `_get_diagram_for_request` rejects cross-project lookups (returns None when project mismatch) — verified via shell smoke test in Step C
    - signal_flow_autosave stub returns status 200 with JSON body containing `"ok": true` and `"stub": true` (Step D)
    - No 500 status codes or unhandled exception tracebacks in any smoke-test step
    - `python manage.py check` exits 0
  </acceptance_criteria>

  <done>
    End-to-end smoke tests confirm: anonymous access is blocked, URL reversal works for all 9 names, the IDOR guard rejects cross-project lookups, and the autosave stub returns the expected 200 response. Smoke-test outputs recorded in the plan SUMMARY for auditability.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Authenticated browser -> Django views | All 9 signal_flow_* endpoints sit at this boundary; untrusted form/JSON input crosses here |
| Cross-project authenticated user -> SignalFlowDiagram rows | The IDOR boundary — request.current_project must scope every diagram lookup |
| Viewer-role user -> mutate endpoints | The privilege-escalation boundary — Viewer must not reach create/rename/delete/autosave |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-11 | Information Disclosure + Tampering (IDOR) | signal_flow_editor, signal_flow_state, signal_flow_rename, signal_flow_delete, signal_flow_autosave | mitigate | `_get_diagram_for_request` helper applies `filter(id=diagram_id, project=project)` on every diagram lookup (mirrors `_get_track_for_request` at planner/views.py:6328). signal_flow_editor uses the inline equivalent. Cross-project access returns None -> 404 for AJAX endpoints, redirect to list for page renders. Per DGM-05. |
| T-07-12 | Elevation of Privilege | signal_flow_create, signal_flow_rename, signal_flow_delete, signal_flow_autosave | mitigate | `_signal_flow_viewer_block(request)` is called as the FIRST line of every mutate view body. Viewer group returns HTTP 403 before any DB write. Mirrors `_multitrack_viewer_block` at views.py:6315. |
| T-07-13 | Tampering (CSRF) | signal_flow_create, signal_flow_rename, signal_flow_delete, signal_flow_autosave | mitigate | All POST mutate views use `@login_required` + `@require_POST` decorators only; no `@csrf_exempt`. Django CSRF middleware (already active project-wide) enforces token verification. Plan 04 editor.html includes `<form style="display:none">{% csrf_token %}</form>` so the cookie is set; AJAX client (Phase 9) sends `X-CSRFToken` header. |
| T-07-14 | Tampering (input validation) | signal_flow_create, signal_flow_rename — name field | mitigate | `name` is `.strip()`ed, length-checked (1..200 chars), and uniqueness is enforced both at the DB layer (unique_together from Plan 01) and in the view (HTTP 409 with explicit error message on duplicate). |
| T-07-15 | Information Disclosure (debug error leakage) | All 9 views — Exception handler | mitigate | All AJAX views wrap their body in try/except returning generic `{'error': 'Server error.'}` with 500. Exception details are logged via `_signal_flow_logger.exception(...)` to Django logs only, never returned to the client. |
| T-07-16 | Repudiation (audit) | Create / rename / delete events | accept | Django doesn't ship an out-of-the-box AJAX audit log for this surface. The model carries `updated_at` for forensic baseline. Beyond-MVP audit logging (e.g. `django-simple-history` or `django-audit-log`) is out of scope for v2.2. |
| T-07-17 | Information Disclosure | signal_flow_state stub returns canvas_state as-is (no enrichment yet) | accept | Phase 7 stub returns raw canvas_state which may be empty `{}` (newly-created diagrams) or whatever client previously stored. No PII is in this blob — only diagram cell layout. Phase 9 will add `_enrich_nodes()` to resolve GFKs for orphan rendering. |

## Non-Security Compliance Notes

- All endpoints follow CLAUDE.md "Defence-in-depth at AJAX boundary" rule: even though CSRF middleware is project-wide, every mutate view also performs server-side input validation (name length, presence, uniqueness).
- No URL routes carry a project ID — all project scoping is via `request.current_project` (CLAUDE.md "Session-based project resolution").
</threat_model>

<verification>
After all three tasks complete, verify the full view + URL layer:

    cd /Users/charlielawsonmacair/DjangoProjects/audiopatch
    python manage.py check                                                                   # exits 0
    grep -c "def signal_flow_" planner/views.py                                              # returns at least 9
    grep -c "name='signal_flow_" planner/urls.py                                             # returns 9
    grep -c "_get_diagram_for_request" planner/views.py                                      # returns at least 5 (1 def + 4 callers in rename/delete/state and helpers)
    grep -c "_signal_flow_viewer_block" planner/views.py                                     # returns at least 5 (1 def + 4 callers in create/rename/delete/autosave)
    python manage.py shell -c "from django.urls import reverse; reverse('planner:signal_flow_list'); reverse('planner:signal_flow_autosave', args=[1]); print('URLs OK')"
    # Anonymous redirect on list endpoint
    python manage.py shell -c "from django.test import Client; assert Client().get('/audiopatch/signal-flow/').status_code in (301, 302), 'list should redirect anon to login'; print('Anon-block OK')"
</verification>

<success_criteria>
- 9 view functions exist in planner/views.py with correct decorators, IDOR guards, viewer-blocks, and try/except handling
- 2 helpers (`_signal_flow_viewer_block`, `_get_diagram_for_request`) exist and are used by every mutate/lookup endpoint
- 9 URL patterns exist in planner/urls.py with correct static-before-param ordering
- All 9 URL names reverse correctly via `reverse('planner:signal_flow_*')`
- Anonymous GET to /audiopatch/signal-flow/ is redirected by staff_member_required
- IDOR isolation verified end-to-end via shell smoke test (cross-project diagram_id returns None from helper)
- signal_flow_autosave stub returns 200 {ok: true, stub: true} for DGM-08 URL existence
- `python manage.py check` passes
- No `@csrf_exempt` decorators were added to any new view
</success_criteria>

<output>
After completion, create `.planning/phases/07-foundation-crud-editor-shell/07-03-SUMMARY.md` documenting:
- Exact byte offsets / line range where the signal-flow view block landed in planner/views.py
- Exact byte offsets / line range where the signal-flow URL block landed in planner/urls.py
- Shell outputs from Task 3 smoke tests (anon redirect, IDOR isolation, autosave stub status)
- Confirmation that no @csrf_exempt was introduced
</output>
