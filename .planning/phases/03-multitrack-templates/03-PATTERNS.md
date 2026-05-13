# Phase 3: Multitrack Templates — Pattern Map

**Mapped:** 2026-05-13
**Files analyzed:** 11 (4 created/appended, 7 modified)
**Analogs found:** 11 / 11

This map is the pattern source-of-truth for Phase 3. It is derived from the locked CONTEXT decisions (D-01..D-16), the RESEARCH document's architecture map, and direct reads of the closest shipped analogs in this repo. Planner copies from these snippets verbatim, then swaps:

- `current_project` → `request.user` (every template view — D-05)
- `AudioChecklist*` → `MultitrackTemplate*` (model + endpoint names)
- `(session, ...)` → `(template, ...)` where appropriate (slot rows mirror tracks)

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `planner/models.py` (append `MultitrackTemplate` + `MultitrackTemplateSlot`) | model | persistent owner-scoped + per-row child | `AudioChecklistTemplate` + `AudioChecklistTemplateTask` (`planner/models.py:3860-3911`) | exact (separate parent + child slot table) |
| `planner/admin.py` (append `MultitrackTemplateAdmin` + inline) | admin / config | request-response (admin) | `MultitrackSessionAdmin` (`planner/admin.py:5905-5940`) + `ConsoleImportAdmin` readonly pattern (`planner/admin.py:5943-5975`) | exact |
| `planner/admin_ordering.py` (add 1 entry) | config | n/a | existing `order_map` entry `multitracksession: 50` (`planner/admin_ordering.py:163-164`) | exact |
| `planner/migrations/0154_multitrack_template.py` | migration | DDL CreateModel only | `0152_multitrack_session_track.py` (Phase 1, two CreateModel ops) | exact |
| `planner/views.py` (append `multitrack_template_save`) | controller | request-response (JSON POST, write) | `audio_checklist_save_template` (`planner/views.py:4955-4995`) | role+flow match (with overwrite-on-conflict CHANGE — see Anti-Patterns) |
| `planner/views.py` (append `multitrack_template_rename`) | controller | request-response (JSON POST, write) | `multitrack_rename` (`planner/views.py:6115-6157`) | exact |
| `planner/views.py` (append `multitrack_template_delete`) | controller | request-response (JSON POST, write) | `multitrack_delete` (`planner/views.py:6160-6188`) + `audio_checklist_delete_template` (`planner/views.py:5063-5077`) | exact |
| `planner/views.py` (modify `multitrack_create_view`) | controller | request-response (form POST, write + bulk insert) | `multitrack_duplicate` (`planner/views.py:6043-6112`) — create new session + `bulk_create` tracks | exact |
| `planner/views.py` (modify `multitrack_dashboard`) | controller | request-response (page render, read) | existing `multitrack_dashboard` (`planner/views.py:5752-5774`) — extend its render context | exact (same view) |
| `planner/forms.py` (modify `MultitrackSessionForm`) | model | form validation + queryset scoping | `MultitrackSessionForm` existing `console` queryset scoping (`planner/forms.py:1155-1165`) | exact |
| `planner/urls.py` (append 3 routes) | config | n/a | existing multitrack URL block (`planner/urls.py:103-129`) | exact |
| `planner/templates/planner/multitrack/editor.html` (modify action bar) | template | n/a | existing `.mts-editor-actions` block (`editor.html:24-26`) | exact |
| `planner/templates/planner/multitrack/dashboard.html` (modify — add Templates section) | template | n/a | existing sessions section (`dashboard.html:34-49`) | exact (clone the structure, swap data) |
| `planner/templates/planner/multitrack/_template_card.html` (NEW partial) | template | n/a | `_session_card.html` (full file, 24 lines) | exact (rename + drop fields) |
| `planner/templates/planner/multitrack/new_session.html` (modify — add dropdown + JS) | template | n/a | existing form-row blocks (`new_session.html:29-98`) + inline `{% csrf_token %}` script pattern (`editor.html:102-117`) | role match (form row) |
| `planner/static/planner/js/multitrack_editor.js` (append 4 functions) | utility / component | event-driven (DOM click → AJAX) | `mtsDuplicateSession` / `mtsRenameSession` / `mtsDeleteSession` (`multitrack_editor.js:551-601`) | exact |

---

## Pattern Assignments

### 1. `planner/models.py` — `MultitrackTemplate` + `MultitrackTemplateSlot`

**Analog:** `AudioChecklistTemplate` + `AudioChecklistTemplateTask` at `planner/models.py:3860-3911`. Same shape: parent template + child rows via FK with CASCADE + `related_name='tasks'` (Phase 3 uses `related_name='slots'`).

**Parent-model pattern** (`planner/models.py:3860-3878`):

```python
class AudioChecklistTemplate(models.Model):
    """A saved checklist template that can be loaded into any project."""
    project = models.ForeignKey('Project', on_delete=models.CASCADE, related_name='checklist_templates')
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='checklist_templates'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Checklist Template"
        verbose_name_plural = "Checklist Templates"
        ordering = ['name']
        unique_together = ['project', 'name']

    def __str__(self):
        return self.name
```

**Phase 3 changes to copy-and-modify:**
- Drop `project = ForeignKey('Project', ...)` (D-05 — owner-scoped, not project-scoped).
- Promote `created_by` from `SET_NULL` / `null=True` to **required**, `on_delete=CASCADE`. Templates belong to a user; if the user is deleted the templates go with them.
- Add metadata fields: `target_daw`, `feed_source`, `track_order_mode`, `recorder_capacity`, `notes` (reuse `MultitrackSession.*_CHOICES` verbatim — see `planner/models.py:978-991`).
- Change `unique_together` to `[('created_by', 'name')]`.
- Add `indexes = [models.Index(fields=['created_by'], name='mtt_owner_idx')]`.
- Bump `name` max_length to 200 (CONTEXT consolidated block).

**Child-model pattern** (`planner/models.py:3881-3911`):

```python
class AudioChecklistTemplateTask(models.Model):
    """A single task stored in a checklist template."""
    TASK_TYPE_CHOICES = [...]
    SECTION_CHOICES = [...]
    STAGE_CHOICES = [...]

    template = models.ForeignKey(AudioChecklistTemplate, on_delete=models.CASCADE, related_name='tasks')
    task = models.CharField(max_length=255)
    section = models.CharField(max_length=10, choices=SECTION_CHOICES, default='FOH')
    task_type = models.CharField(max_length=10, choices=TASK_TYPE_CHOICES, default='setup')
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='', blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Template Task"
        verbose_name_plural = "Template Tasks"
        ordering = ['template', 'section', 'task_type', 'sort_order']
```

**Phase 3 changes:**
- FK to `MultitrackTemplate` with `related_name='slots'`.
- Reuse `MultitrackTrack.SOURCE_TYPE_CHOICES` verbatim (`planner/models.py:1041-1047`) — do NOT redefine.
- Fields per CONTEXT D-03: `position`, `source_type`, `source_number` (CharField, max_length=10 to match `ConsoleInput.input_ch` / `ConsoleAuxOutput.aux_number` / etc.), `label_override`, `color_override`. **Drop `notes`** per Discretion + Assumption A5.
- `unique_together = [('template', 'position')]` + `indexes = [models.Index(fields=['template', 'position'], name='mtt_slot_pos_idx')]`.

**Reuse-verbatim from Phase 1** (do not redefine):

- `MultitrackSession.TARGET_DAW_CHOICES` (`planner/models.py:978-981`)
- `MultitrackSession.FEED_SOURCE_CHOICES` (`planner/models.py:982-986`)
- `MultitrackSession.TRACK_ORDER_MODE_CHOICES` (`planner/models.py:987-991`)
- `MultitrackTrack.SOURCE_TYPE_CHOICES` (`planner/models.py:1041-1047`)
- `_source_model_for(source_type)` dispatch helper (`planner/models.py:1024-1035`) — used by `apply_to_session`.

**Placement guidance:** append both classes after `MultitrackTrack` class at `planner/models.py:1119` and BEFORE the comment block `# planner/models.py` / `from django.db import models` at line 1122-1124. (There's an unfortunate stray re-import there — append above it to keep all multitrack models contiguous.)

**`apply_to_session(self, session)` method** — see Pattern Assignment 5 below (it's the algorithm centerpiece). RESEARCH recommends placing it as an instance method on `MultitrackTemplate` for clean test surface (A7).

---

### 2. `planner/admin.py` — `MultitrackTemplateAdmin` + readonly inline

**Analog A (overall admin class shape):** `MultitrackSessionAdmin` at `planner/admin.py:5905-5940`.

```python
class MultitrackSessionAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'console', 'target_daw', 'feed_source', 'updated_at']
    list_filter = ['target_daw', 'feed_source', 'track_order_mode']
    search_fields = ['name', 'console__name']
    fieldsets = (
        ('Session', {
            'fields': ('name', 'console', 'target_daw', 'feed_source',
                       'track_order_mode', 'recorder_capacity', 'notes'),
        }),
    )

    def changelist_view(self, request, extra_context=None):
        """Bounce admin changelist to the custom UI (matches CommConfigAdmin)."""
        from django.shortcuts import redirect
        return redirect('planner:multitrack_dashboard')

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        if request.user.groups.filter(name='Viewer').exists():
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser: return True
        if request.user.groups.filter(name='Viewer').exists(): return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser: return True
        if request.user.groups.filter(name='Viewer').exists(): return False
        return super().has_delete_permission(request, obj)
```

**Analog B (readonly-inline pattern for the slot child rows):** `ConsoleImportAdmin` at `planner/admin.py:5943-5975` (the "immutable audit history" pattern — every field readonly, `has_add_permission` False, viewer block on all three permission methods).

**Phase 3 admin (synthesis):**
- Subclass `BaseEquipmentAdmin` (matches `MultitrackSessionAdmin`).
- `list_display` includes a `slot_count` callable (see RESEARCH § "Admin registration").
- `inlines = [MultitrackTemplateSlotInline]` — `TabularInline` with **every field readonly**, `extra=0`, `can_delete=False`, `has_add_permission=False`. Slot rows MUST NOT be editable from admin (CONTEXT specifics line 195).
- Copy the three viewer-block permission methods verbatim from `MultitrackSessionAdmin`.
- Optional: `changelist_view` bounces to the multitrack dashboard (matches `MultitrackSessionAdmin:5916-5919`). Recommended.

**Registration block** — `planner/admin.py:5978-5984` shows the existing pattern:

```python
    # ==================== REGISTER ALL MODELS ====================
from planner.admin_site import showstack_admin_site

# Register all equipment admin classes
showstack_admin_site.register(Console, ConsoleAdmin)
showstack_admin_site.register(MultitrackSession, MultitrackSessionAdmin)
showstack_admin_site.register(ConsoleImport, ConsoleImportAdmin)
```

Append to this block: `showstack_admin_site.register(MultitrackTemplate, MultitrackTemplateAdmin)`. Do **NOT** separately register `MultitrackTemplateSlot` — it lives only as an inline (matches Phase 1: `MultitrackTrack` is also not registered separately).

---

### 3. `planner/admin_ordering.py` — order_map entry

**Analog:** existing trailing entries at `planner/admin_ordering.py:162-164`:

```python
        # Multitrack Session Builder (50 — bottom of sidebar)
        'multitracksession': 50,
        'consoleimport': 51,
```

**Phase 3 change:** insert one new entry. RESEARCH recommends keeping multitrack-related models grouped:

```python
        # Multitrack Session Builder (50 — bottom of sidebar)
        'multitracksession': 50,
        'multitracktemplate': 51,        # NEW — Phase 3
        'consoleimport': 52,             # bumped from 51 to keep grouping order
```

`MultitrackTemplateSlot` is NOT separately registered, so no `order_map` entry needed. If the planner reverses that decision, add `'multitracktemplateslot': 53` AND add `multitracktemplateslot` to the `always_hidden` set at line 73-86 (it's a child, not a top-level concept) — same treatment as `pollresult`, `deviceevent`, etc.

**Non-negotiable per CLAUDE.md:** *"Update `planner/admin_ordering.py` whenever a new admin-registered model is added, otherwise the sidebar grouping will be wrong."*

---

### 4. `planner/migrations/0154_multitrack_template.py` — additive CreateModel migration

**Analog:** `planner/migrations/0152_multitrack_session_track.py` — Phase 1's two-CreateModel migration. Same shape.

**Imports + dependencies pattern** (`0152_multitrack_session_track.py:1-11`):

```python
# Generated by Django 5.2.4 on 2026-05-10 22:57

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0151_discovereddevice_clock_role_and_more'),
    ]
```

**Phase 3 changes:**
- Dependency: `('planner', '0153_console_color_and_consoleimport')`.
- Also add `migrations.swappable_dependency(settings.AUTH_USER_MODEL)` (User FK on `MultitrackTemplate.created_by`); import `from django.conf import settings`.
- Two `migrations.CreateModel` ops, in order: `MultitrackTemplate` first (so `MultitrackTemplateSlot.template` FK can reference it).
- `auto_created=True, primary_key=True, serialize=False, verbose_name='ID'` on the `id` field — mirror `0152` exactly.
- **Zero `ALTER TABLE` operations** — CLAUDE.md and CONTEXT both require additive-only migrations against beta-tester data.
- Recommend running `python manage.py makemigrations planner` and committing the generated file rather than hand-writing — Django's migration autodetector produces the canonical form.

The complete spelled-out shape lives in `03-RESEARCH.md` Code Examples § "Migration shape" (lines 716-775).

---

### 5. `planner/views.py` — `multitrack_template_save` (JSON POST endpoint)

**Analog:** `audio_checklist_save_template` at `planner/views.py:4955-4995`. **Same shape**, with two important DIVERGENCES the planner must respect (see Anti-Patterns).

**Imports pattern** (use what's already imported at the top of views.py): `json` (as `_json` in some places, plain `json` in multitrack block per `views.py:6066`), `JsonResponse`, `require_POST`, `login_required`, plus `_multitrack_viewer_block` (`planner/views.py:6213-6223`) and the new model imports.

**Existing analog body** (`planner/views.py:4955-4995`):

```python
def audio_checklist_save_template(request):
    """Save current checklist as a named template."""
    try:
        data = _json.loads(request.body)
        name = data.get('name', '').strip()
        current_project = getattr(request, 'current_project', None)
        if not name or not current_project:
            return JsonResponse({'error': 'Missing name or project'}, status=400)

        # Delete existing template with same name in this project
        AudioChecklistTemplate.objects.filter(project=current_project, name=name).delete()

        # Create new template
        template = AudioChecklistTemplate.objects.create(
            project=current_project,
            name=name,
            created_by=request.user,
        )

        # Copy all tasks from current checklists ... [iterates source rows]
        for checklist in AudioChecklist.objects.filter(project=current_project):
            ...
            for task in checklist.tasks.all().order_by('task_type', 'sort_order'):
                AudioChecklistTemplateTask.objects.create(
                    template=template,
                    task=task.task,
                    section=section,
                    task_type=task.task_type,
                    stage=task.stage,
                    sort_order=sort_order,
                )
                sort_order += 1

        return JsonResponse({'ok': True, 'template_id': template.id, 'name': template.name})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
```

**Phase 3 changes — copy then modify:**
1. Add decorators (analog lacks these — most Phase 1 mutate endpoints have them, copy from `multitrack_duplicate:6043-6044`):
   ```python
   @login_required
   @require_POST
   def multitrack_template_save(request):
   ```
2. Add viewer block immediately after the decorators (copy from `multitrack_duplicate:6052-6054`):
   ```python
   viewer_block = _multitrack_viewer_block(request)
   if viewer_block is not None:
       return viewer_block
   ```
3. Read `name` AND `session_id` from JSON body. IDOR-guard the session lookup against `current_project` (templates are owner-scoped, but the *source session* still belongs to a project — copy IDOR pattern from `multitrack_duplicate:6060-6064`).
4. **CRITICAL DIVERGENCE — do NOT copy the silent overwrite at analog line 4965** (`.filter(...).delete()`). Instead, return HTTP 409 on name conflict. See Anti-Patterns + RESEARCH Pitfall 1. The 409-on-conflict pattern is already in this codebase at `multitrack_duplicate:6070-6076` and `multitrack_rename:6144-6150`:
   ```python
   if MultitrackSession.objects.filter(
       project=current_project, name=new_name
   ).exists():
       return JsonResponse({
           'error': f'A session named "{new_name}" already exists in this project. '
                    f'Pick a different name.',
       }, status=409)
   ```
   Phase 3 version (swap `project=current_project` → `created_by=request.user`):
   ```python
   if MultitrackTemplate.objects.filter(
       created_by=request.user, name=name
   ).exists():
       return JsonResponse({
           'error': f'A template named "{name}" already exists. Pick a different name.',
       }, status=409)
   ```
5. Snapshot loop — walk `session.tracks.filter(enabled=True).order_by('track_number')` (RESEARCH Pitfall 7 / Open Question 1: enabled-only at save time), resolve each track's channel-number via `_source_model_for(track.source_type)` lookup of `track.source_id`, build a list of `MultitrackTemplateSlot(...)` instances, then **`bulk_create`** them (matches `multitrack_duplicate:6090-6103`, never one-at-a-time `.objects.create` in a loop).
6. Replace the bare `except Exception as e: return ...str(e)...` (security smell — leaks stack traces) with the multitrack pattern at `multitrack_duplicate:6110-6112`:
   ```python
   except Exception:
       _multitrack_logger.exception('multitrack_template_save failed')
       return JsonResponse({'error': 'Server error.'}, status=500)
   ```
   Plus an explicit `except IntegrityError:` clause that mirrors the 409 message (defends against the race between `.exists()` and `.create()`).
7. Return `{'ok': True, 'template_id': template.id, 'name': template.name, 'slot_count': len(slots)}`.

Full spelled-out version lives in `03-RESEARCH.md` Pattern 1 (lines 252-343).

---

### 6. `planner/views.py` — `multitrack_template_rename`

**Analog:** `multitrack_rename` at `planner/views.py:6115-6157` (exact shape match — the rename pattern needs identical IDOR-guard + uniqueness check structure).

**Verbatim copy-and-rename target** (`planner/views.py:6115-6157`):

```python
@login_required
@require_POST
def multitrack_rename(request, session_id):
    """POST: rename a session (MTS-02).

    Body: JSON {name: '...'}. Returns {ok, name} or {error, status: 409} on
    unique-together conflict.
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        session = MultitrackSession.objects.filter(
            id=session_id, project=current_project
        ).first()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        data = json.loads(request.body or '{}')
        new_name = (data.get('name') or '').strip()
        if not new_name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(new_name) > 100:
            return JsonResponse({'error': 'Name must be 100 characters or fewer.'}, status=400)

        if MultitrackSession.objects.filter(
            project=current_project, name=new_name
        ).exclude(pk=session.pk).exists():
            return JsonResponse({
                'error': f'A session named "{new_name}" already exists in this project. '
                         f'Pick a different name.',
            }, status=409)

        session.name = new_name
        session.save(update_fields=['name', 'updated_at'])
        return JsonResponse({'ok': True, 'name': new_name})
    except Exception:
        _multitrack_logger.exception('multitrack_rename failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

**Phase 3 substitutions:**
- Function name → `multitrack_template_rename(request, template_id)`.
- Body key → `new_name` (RESEARCH § "Rename / Delete endpoint shape"); JS will post `{new_name: ...}` (see Pattern 11).
- Swap `MultitrackSession.objects.filter(id=..., project=current_project)` → `MultitrackTemplate.objects.filter(id=template_id, created_by=request.user)`. **DROP** the `current_project` lookup entirely (D-05). Drop the "No active project" 400 — irrelevant.
- Length cap: 200 (matches `MultitrackTemplate.name` max_length per CONTEXT model shape) instead of 100.
- Uniqueness check: `MultitrackTemplate.objects.filter(created_by=request.user, name=new_name).exclude(pk=template.pk).exists()`.
- Log tag: `'multitrack_template_rename failed'`.

**Add a one-line D-05 comment** above the queryset filter (RESEARCH Pitfall 2):
```python
# D-05: owner-scoped via request.user. Templates intentionally cross all of this user's projects.
```

---

### 7. `planner/views.py` — `multitrack_template_delete`

**Analog:** `multitrack_delete` at `planner/views.py:6160-6188`.

```python
@login_required
@require_POST
def multitrack_delete(request, session_id):
    """POST: delete a session and (via CASCADE) all its tracks (MTS-05).

    Returns JSON {ok, redirect_url} so the JS can navigate after success.
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        session = MultitrackSession.objects.filter(
            id=session_id, project=current_project
        ).first()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        session.delete()   # CASCADE on MultitrackTrack.session FK handles tracks
        return JsonResponse({
            'ok': True,
            'redirect_url': reverse('planner:multitrack_dashboard'),
        })
    except Exception:
        _multitrack_logger.exception('multitrack_delete failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

**Phase 3 substitutions:**
- Function → `multitrack_template_delete(request, template_id)`.
- Queryset → `MultitrackTemplate.objects.filter(id=template_id, created_by=request.user).first()`. Drop the `current_project` check (D-05).
- CASCADE handles slots (slot FK declares `on_delete=models.CASCADE`).
- Don't return `redirect_url` — the JS calls `window.location.reload()` after delete (matches RESEARCH § "Editor Save as Template button + JS" line 1083); just return `{'ok': True}`.

---

### 8. `planner/views.py` — modify `multitrack_create_view` to apply selected template

**Analog A (existing view):** `multitrack_create_view` at `planner/views.py:5991-6009` (current Phase 1 shape).

```python
@staff_member_required
def multitrack_create_view(request):
    """GET: render new-session form. POST: create + redirect to editor (MTS-01, D-12)."""
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    if request.method == 'POST':
        form = MultitrackSessionForm(request.POST, request=request)
        if form.is_valid():
            session = form.save()
            return redirect('planner:multitrack_editor', session_id=session.id)
    else:
        form = MultitrackSessionForm(request=request)

    return render(request, 'planner/multitrack/new_session.html', {
        'form': form,
        'mode': 'create',
    })
```

**Analog B (bulk_create + new session pattern):** `multitrack_duplicate` at `planner/views.py:6043-6112` — specifically the bulk-track-creation block at 6089-6103:

```python
new_tracks = [
    MultitrackTrack(
        session=new_session,
        track_number=t.track_number,
        source_type=t.source_type,
        source_id=t.source_id,
        label_override=t.label_override,
        color_override=t.color_override,
        enabled=t.enabled,
        notes=t.notes,
    )
    for t in source.tracks.all().order_by('track_number')
]
MultitrackTrack.objects.bulk_create(new_tracks)
```

**Phase 3 changes to `multitrack_create_view`:**
- After `session = form.save()`, read `template = form.cleaned_data.get('template')`. If not None, call `template.apply_to_session(session)` and surface the result via `messages.info(...)` (banner appears on the editor page via `dashboard.html:14-19` pattern, which `editor.html` inherits — verified RESEARCH Assumption A3).
- The `apply_to_session(self, session)` method on `MultitrackTemplate` is the core algorithm. Pattern:
  - Walk `self.slots.all().order_by('position')`.
  - For each slot, resolve a channel row via `_source_model_for(slot.source_type).objects.filter(console=session.console, <number_field>=slot.source_number).first()`, where `<number_field>` is `input_ch` / `aux_number` / `matrix_number` / `stereo_type` (see RESEARCH Pattern 2).
  - For `source_type == 'manual'`, no resolution — always materialise.
  - Skip slots that resolve to `None`; collect `(source_type, source_number)` tuples for the banner.
  - Build a list of `MultitrackTrack(...)` instances with `track_number = position-in-output-list`, then `MultitrackTrack.objects.bulk_create(new_tracks)`.
  - Return `(mapped_count, skipped_count, skipped_summary_str)`.
- Banner wording from D-10 (mapped+skipped) and D-13 (zero-slot template) — see RESEARCH Pattern 2 caller block at lines 424-468 for the exact `messages.info(...)` strings.

**Anti-pattern flag:** the existing `audio_checklist_load_template` (`planner/views.py:5013-5060`) calls `MultitrackTrack.objects.create(...)` in a loop. **Do not copy that loop**. Use `bulk_create` (matches `multitrack_duplicate` analog).

---

### 9. `planner/views.py` — modify `multitrack_dashboard` to pass `templates` queryset

**Analog:** existing `multitrack_dashboard` at `planner/views.py:5752-5774` (full body shown above in research read).

```python
@staff_member_required
def multitrack_dashboard(request):
    """List view of MultitrackSessions for the current project (MTS-03)."""
    current_project = getattr(request, 'current_project', None)
    sessions = (
        MultitrackSession.objects.filter(project=current_project)
        .select_related('console')
        .order_by('-updated_at')
        if current_project else MultitrackSession.objects.none()
    )
    can_import_console_csv = (
        request.user.is_authenticated
        and not request.user.groups.filter(name='Viewer').exists()
    )
    return render(request, 'planner/multitrack/dashboard.html', {
        'sessions': sessions,
        'current_project': current_project,
        'can_import_console_csv': can_import_console_csv,
    })
```

**Phase 3 change:** add a `templates` queryset and pass it in the render context. **DO NOT** scope by `current_project` (D-05):

```python
# D-05: templates are OWNER-scoped, NOT project-scoped. They follow the
# engineer across all their projects.
templates = (
    MultitrackTemplate.objects.filter(created_by=request.user)
    .order_by('name')
    if request.user.is_authenticated else MultitrackTemplate.objects.none()
)
```

Add `'templates': templates,` to the render context dict.

---

### 10. `planner/forms.py` — modify `MultitrackSessionForm` to add `template` field

**Analog:** existing `MultitrackSessionForm` at `planner/forms.py:1130-1225`. Specifically the `console` queryset scoping pattern at lines 1155-1165:

```python
def __init__(self, *args, request=None, **kwargs):
    self.request = request
    super().__init__(*args, **kwargs)

    # D-13: scope console queryset to current_project
    if request is not None and getattr(request, 'current_project', None):
        self.fields['console'].queryset = Console.objects.filter(
            project=request.current_project
        )
    else:
        self.fields['console'].queryset = Console.objects.none()
```

**Phase 3 changes:**
- Add a `template` **non-model** `ModelChoiceField` at class level (NOT in `Meta.fields` — there's no `template` FK on `MultitrackSession`):
  ```python
  template = forms.ModelChoiceField(
      queryset=MultitrackTemplate.objects.none(),   # set in __init__
      required=False,
      empty_label='— None —',
      label='Start from template (optional)',
      help_text='Picking a template pre-fills the fields below.',
  )
  ```
- In `__init__`, after the existing `console` scoping block, add an analogous owner-scoped block for `template` (RESEARCH Pitfall 6 — without this the form is an IDOR vector):
  ```python
  # D-05: owner-scoped template queryset. Templates intentionally
  # cross all of this user's projects.
  if request is not None and request.user.is_authenticated:
      self.fields['template'].queryset = MultitrackTemplate.objects.filter(
          created_by=request.user
      ).order_by('name')
  else:
      self.fields['template'].queryset = MultitrackTemplate.objects.none()
  ```
- `save()` (forms.py:1218-1225) and `clean_name()` (forms.py:1194-1216) need NO changes — the `template` field is consumed by `multitrack_create_view` after `form.save()` returns the new session (Pattern 8).

---

### 11. `planner/urls.py` — append 3 new routes

**Analog:** existing multitrack URL block at `planner/urls.py:103-129`. Specifically the per-session mutate route triplet (lines 114-116):

```python
path('multitrack/<int:session_id>/duplicate/', views.multitrack_duplicate, name='multitrack_duplicate'),
path('multitrack/<int:session_id>/rename/', views.multitrack_rename, name='multitrack_rename'),
path('multitrack/<int:session_id>/delete/', views.multitrack_delete, name='multitrack_delete'),
```

**Phase 3 routes (insert after line 129, before line 131's `# Dashboard` block):**

```python
# Phase 3 — Multitrack Templates (TPL-01..TPL-04)
# All endpoints OWNER-scoped (request.user), NOT project-scoped (D-05).
path('multitrack/templates/save/', views.multitrack_template_save, name='multitrack_template_save'),
path('multitrack/templates/<int:template_id>/rename/', views.multitrack_template_rename, name='multitrack_template_rename'),
path('multitrack/templates/<int:template_id>/delete/', views.multitrack_template_delete, name='multitrack_template_delete'),
```

**No `/list/` endpoint** — the dashboard renders templates server-side via the queryset added in Pattern 9 (matches `_session_card.html` rendering pattern). RESEARCH § "URL routes" line 868 confirms.

---

### 12. `planner/templates/planner/multitrack/editor.html` — add "Save as Template" button

**Analog:** existing action bar at `editor.html:24-26`:

```django
<div class="mts-editor-actions">
  <a class="mts-btn-tertiary" href="{% url 'planner:multitrack_edit' session.id %}">Edit session metadata</a>
</div>
```

**Phase 3 change:** insert a second action button after the "Edit session metadata" link. Use `mts-btn-tertiary` to match the existing button class:

```django
<div class="mts-editor-actions">
  <a class="mts-btn-tertiary" href="{% url 'planner:multitrack_edit' session.id %}">Edit session metadata</a>
  <button type="button" class="mts-btn-tertiary"
          onclick="mtsSaveAsTemplate({{ session.id }}, '{{ session.name|escapejs }}')">Save as Template</button>
</div>
```

CSRF source is already present in this file at line 105 (`<form style="display:none">{% csrf_token %}</form>`), so the JS's `csrfToken()` helper picks it up — no template change needed for that.

Per RESEARCH Open Question 3: always show the button regardless of track count (D-04 allows zero-track templates).

---

### 13. `planner/templates/planner/multitrack/dashboard.html` — add Templates section

**Analog:** existing sessions section at `dashboard.html:34-49`:

```django
{% if sessions %}
  <div class="mts-grid">
    {% for session in sessions %}
      {% include "planner/multitrack/_session_card.html" with session=session %}
    {% endfor %}
  </div>
{% else %}
  <div class="mts-empty-state">
    <h2 class="mts-empty-heading">No sessions yet</h2>
    ...
  </div>
{% endif %}
```

**Phase 3 change:** clone the structure for templates and insert after line 49 (between the sessions block and the closing `</div>` of `.mts-container`). Visual treatment: a section divider + h2 heading + grid (mirrors RESEARCH § "Dashboard Templates section markup" lines 928-952).

Place the Templates section **below** the sessions grid (RESEARCH Open Question 4 recommendation — sessions are the engineer's current focus, templates are reference).

---

### 14. `planner/templates/planner/multitrack/_template_card.html` — NEW partial

**Analog:** `planner/templates/planner/multitrack/_session_card.html` (full file, 24 lines):

```django
{% load humanize %}
<div class="mts-card" data-session-id="{{ session.id }}">
  <a class="mts-card-link" href="{% url 'planner:multitrack_editor' session.id %}">
    <div class="mts-card-title">{{ session.name }}</div>
    <div class="mts-card-meta">
      {{ session.tracks.count }} track{{ session.tracks.count|pluralize }} ·
      {{ session.get_target_daw_display }} ·
      updated {{ session.updated_at|timesince }} ago
    </div>
  </a>
  <div class="mts-card-actions">
    <button type="button" class="mts-card-menu-trigger"
            aria-label="Session actions"
            onclick="mtsToggleCardMenu(this, {{ session.id }})">⋯</button>
    <div class="mts-dropdown-menu" id="mts-card-menu-{{ session.id }}">
      <button type="button" class="mts-dropdown-item"
              onclick="mtsDuplicateSession({{ session.id }}, '{{ session.name|escapejs }}')">Duplicate</button>
      <button type="button" class="mts-dropdown-item"
              onclick="mtsRenameSession({{ session.id }}, '{{ session.name|escapejs }}')">Rename</button>
      <button type="button" class="mts-dropdown-item mts-dropdown-item--danger"
              onclick="mtsDeleteSession({{ session.id }}, '{{ session.name|escapejs }}', {{ session.tracks.count }})">Delete</button>
    </div>
  </div>
</div>
```

**Phase 3 changes for the new `_template_card.html`:**
- Rename `data-session-id` → `data-template-id`.
- Drop the `<a class="mts-card-link" href=...>` wrapper — templates have no detail page in v3.0. Render the title + meta as plain divs.
- Meta line: `{{ template.slots.count }} slot{{ ...|pluralize }} · {{ template.get_target_daw_display }} · updated {{ template.updated_at|timesince }} ago`.
- Drop the "Duplicate" dropdown item — out of scope per CONTEXT deferred list.
- Keep "Rename" and "Delete" — wire to `mtsRenameTemplate` / `mtsDeleteTemplate` (Pattern 16).
- The `mts-card-menu-` ID needs a `tmpl-` prefix to avoid collisions with session card IDs on the same page: `id="mts-card-menu-tmpl-{{ template.id }}"`. The JS toggle helper handles this via the second `mtsToggleCardMenu` argument.

Full version at RESEARCH § "Dashboard Templates section markup" lines 955-976.

---

### 15. `planner/templates/planner/multitrack/new_session.html` — add template dropdown + inline JS

**Analog A (form-row markup):** existing `new_session.html:87-92` — the `recorder_capacity` form row:

```django
<div class="mts-form-row">
  <label for="{{ form.recorder_capacity.id_for_label }}">Recorder capacity (optional)</label>
  {{ form.recorder_capacity }}
  <p class="mts-help-text">Drives the over-capacity warning bar in the editor.</p>
  {% if form.recorder_capacity.errors %}<div class="mts-field-error">{{ form.recorder_capacity.errors }}</div>{% endif %}
</div>
```

**Analog B (inline JS pattern):** the `auto_open_picker` block at `editor.html:110-117`:

```django
{% if auto_open_picker %}
  <script>
    document.addEventListener('DOMContentLoaded', function () {
      if (typeof mtsOpenPicker === 'function') mtsOpenPicker('inputs');
    });
  </script>
{% endif %}
```

**Phase 3 changes:**
- Insert a new `<div class="mts-form-row">` **at the top of the form**, immediately after the `{% if form.errors %}` block (line 27) and before the Name row at line 29.
- The dropdown uses `data-*` attributes per `<option>` carrying template metadata so vanilla JS can auto-populate the form without a round-trip (RESEARCH Pattern 3 lines 470-498).
- Add a `<script>` block at the end of `{% block content %}` (mirror editor.html:110-117). The script only needs to expose the global `mtsApplyTemplateToForm(selectEl)` — defined in `multitrack_editor.js` (Pattern 16) — and bind to `onchange`. Since `multitrack_editor.js` is NOT currently loaded on `new_session.html` (verified RESEARCH Assumption A4), the planner adds a `<script src="{% static 'planner/js/multitrack_editor.js' %}" defer></script>` line.

Full markup at RESEARCH § "Pattern 3: Dropdown auto-populate" lines 475-498.

---

### 16. `planner/static/planner/js/multitrack_editor.js` — append 4 functions

**Analog:** dashboard card menu functions at `multitrack_editor.js:551-601` (`mtsToggleCardMenu`, `mtsDuplicateSession`, `mtsRenameSession`, `mtsDeleteSession`).

**Existing helpers to reuse (NOT redefine):**
- `csrfToken()` (`multitrack_editor.js:33-36`) — reads the hidden `[name=csrfmiddlewaretoken]` input.
- `postJSON(url, body)` (`multitrack_editor.js:38-47`) — POSTs JSON with CSRF header, returns `Promise<{status, data}>`.
- `getJSON(url)` (`multitrack_editor.js:49-52`) — GETs JSON.
- `showToast(message, level)` (`multitrack_editor.js:55-62`) — passive notification.

**mtsRenameSession analog** (`multitrack_editor.js:573-584`):

```javascript
window.mtsRenameSession = function (sessionId, oldName) {
  const newName = window.prompt('Rename session:', oldName);
  if (newName === null || newName.trim() === '') return;
  postJSON('/audiopatch/multitrack/' + sessionId + '/rename/', { name: newName })
    .then(function (resp) {
      if (resp.status === 200 && resp.data.ok) {
        window.location.reload();
      } else {
        showToast(resp.data.error || 'Rename failed.', 'error');
      }
    });
};
```

**Phase 3 four new functions (copy-and-adapt):**

1. **`window.mtsSaveAsTemplate(sessionId, sessionName)`** — modeled on `mtsRenameSession`. Default name: `sessionName + ' template'`. Posts to `/audiopatch/multitrack/templates/save/` with `{name, session_id: sessionId}`. On `resp.status === 200 && resp.data.ok`, show success toast including `slot_count` from the response. On 409, the toast surfaces the friendly conflict message — engineer can re-click the button. (RESEARCH Assumption A6 notes the 409-re-prompt could be a follow-up polish; v3.0 ships with a plain toast.)

2. **`window.mtsRenameTemplate(templateId, oldName)`** — verbatim clone of `mtsRenameSession` with URL `'/audiopatch/multitrack/templates/' + templateId + '/rename/'` and body `{new_name: newName.trim()}` (key is `new_name`, not `name` — matches the endpoint, Pattern 6).

3. **`window.mtsDeleteTemplate(templateId, name)`** — clone of `mtsDeleteSession` (`multitrack_editor.js:586-601`) with adjusted confirmation copy:
   > *"Delete template '{name}'?\n\nThis will permanently delete the template and all its slots. Sessions previously created from this template are not affected."*
   URL: `'/audiopatch/multitrack/templates/' + templateId + '/delete/'`. On success: `window.location.reload()` (do not navigate — the dashboard is already the right destination).

4. **`window.mtsApplyTemplateToForm(selectEl)`** — DOM-only, no AJAX. Reads `selectEl.options[selectEl.selectedIndex]`, returns early if value is empty. Sets radio buttons for `target_daw` / `feed_source` / `track_order_mode` (matches the radio widgets at `new_session.html:43-83`) and direct input values for `recorder_capacity` (input) and `notes` (textarea). Full implementation at RESEARCH lines 500-523.

**Placement:** append all four after the existing dashboard card menu block (`multitrack_editor.js:601`), inside the outer `(function () { 'use strict'; ...` IIFE that begins at line 23. Add a comment banner header:

```javascript
// ──────────────────────────────────────────────────────────────
// Template save / rename / delete (Phase 3 / v3.0)
// All endpoints are OWNER-scoped (created_by=request.user) per D-05.
// ──────────────────────────────────────────────────────────────
```

Match the existing banner style (see lines 26-28, 64-66, 548-549).

---

## Shared Patterns

### S1. Viewer-role gate on every mutate endpoint

**Source:** `_multitrack_viewer_block` at `planner/views.py:6213-6223`:

```python
def _multitrack_viewer_block(request):
    """Return a JsonResponse 403 iff the user is in the 'Viewer' group; else None."""
    if request.user.groups.filter(name='Viewer').exists():
        return JsonResponse({'error': 'Read-only access.'}, status=403)
    return None
```

**Apply to:** every Phase 3 endpoint that mutates state (`multitrack_template_save`, `multitrack_template_rename`, `multitrack_template_delete`). Call IMMEDIATELY after the decorators, before any other logic:

```python
viewer_block = _multitrack_viewer_block(request)
if viewer_block is not None:
    return viewer_block
```

Reuse verbatim. Do NOT hand-roll `if user.groups.filter(name='Viewer').exists():` checks.

### S2. CSRF + AJAX wire-up

**Source:** the existing hidden CSRF form in `dashboard.html:53` and `editor.html:105`:

```django
<form style="display:none">{% csrf_token %}</form>
```

**Apply to:** `new_session.html` already has `{% csrf_token %}` inside its real form, so no change needed there. The dashboard and editor already have the hidden form. The `csrfToken()` helper in `multitrack_editor.js:33-36` reads from the first `[name=csrfmiddlewaretoken]` it finds — works for either source.

### S3. Login + role-decoration on JSON endpoints

**Source:** existing per-endpoint pattern, e.g. `multitrack_rename:6115-6118`:

```python
@login_required
@require_POST
def multitrack_rename(request, session_id):
    """POST: ..."""
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
```

**Apply to:** all three Phase 3 JSON endpoints (`save`, `rename`, `delete`).

### S4. Generic 500 logger (don't leak stack traces)

**Source:** module-level logger at `planner/views.py:6206`:

```python
_multitrack_logger = logging.getLogger(__name__)
```

**Apply to:** every Phase 3 endpoint's `except` clause:

```python
except Exception:
    _multitrack_logger.exception('multitrack_template_<action> failed')
    return JsonResponse({'error': 'Server error.'}, status=500)
```

Reuses the existing logger — DO NOT instantiate a new one.

### S5. CharField channel-number lookup contract

**Source:** `_source_model_for(source_type)` at `planner/models.py:1024-1035` + the four channel-number CharField definitions (`ConsoleInput.input_ch`, `ConsoleAuxOutput.aux_number`, `ConsoleMatrixOutput.matrix_number`, `ConsoleStereoOutput.stereo_type`).

**Apply to:** `MultitrackTemplate.apply_to_session()`. The dispatch table maps `source_type` → channel-number field name:

```python
number_field = {
    'input': 'input_ch',
    'aux': 'aux_number',
    'matrix': 'matrix_number',
    'stereo': 'stereo_type',
}
model = _source_model_for(slot.source_type)
channel = model.objects.filter(
    console=session.console,
    **{number_field[slot.source_type]: slot.source_number},
).first()
```

**Watch out for:** zero-padding mismatches (RESEARCH Pitfall 3 — `'1' != '01'`). The planner should add a one-off inspection of `console_import_upload` to confirm what string form Phase 2 CSV imports persist; if zero-padded, normalise both sides with `.lstrip('0') or '0'` before comparison.

### S6. Bulk row creation (single INSERT)

**Source:** `multitrack_duplicate:6090-6103` — build a list of model instances, then call `.objects.bulk_create(...)`.

**Apply to:**
- `multitrack_template_save` — slot rows are built into a list, then `MultitrackTemplateSlot.objects.bulk_create(slots)` (one INSERT).
- `apply_to_session` — new tracks are built into a list, then `MultitrackTrack.objects.bulk_create(new_tracks)` (one INSERT).

**Anti-pattern (do NOT copy):** `audio_checklist_save_template:4983-4991` and `audio_checklist_load_template:5046-5054` both call `.objects.create(...)` in a loop. That pattern works but does N round-trips. The multitrack module standard is bulk_create.

### S7. D-05 owner-scoping comment on every template queryset

**Source:** RESEARCH Pitfall 2 mitigation.

**Apply to:** every `MultitrackTemplate.objects.filter(...)` call in views.py and forms.py. Add a comment one line above:

```python
# D-05: owner-scoped via request.user. Templates intentionally cross all of this user's projects.
```

This is a defensive comment, not a behavior change — `request.current_project` is the project's standard scoping pattern, so future-Charlie's autopilot will try to add it. The comment stops the autopilot.

---

## Anti-Patterns (do NOT copy from analogs)

### A1. Silent overwrite on name conflict

**Source of the bad pattern:** `audio_checklist_save_template:4965`:
```python
AudioChecklistTemplate.objects.filter(project=current_project, name=name).delete()
```

**Why it's bad here:** Audio checklists are project-scoped and re-saving "FOH Pre-Show" with the same name to update it is the typical UX. Multitrack templates are reusable across many sessions; silent overwrite destroys work the engineer didn't realise was still in use. CONTEXT and RESEARCH both call out 409-on-conflict instead.

**Correct pattern:** return HTTP 409 with a friendly error message, force engineer to pick a different name (mirrors `multitrack_duplicate:6070-6076`).

### A2. `except Exception as e: ... str(e) ...`

**Source of the bad pattern:** `audio_checklist_save_template:4994-4995` and the other three Audio Checklist endpoints:
```python
except Exception as e:
    return JsonResponse({'error': str(e)}, status=500)
```

**Why it's bad:** `str(e)` can leak stack-trace fragments / database internals to the client.

**Correct pattern:** use `_multitrack_logger.exception('...failed')` + generic `{'error': 'Server error.'}` message (see S4).

### A3. Reflexive `current_project` filter on template queries

**Why it's tempting:** every other planner view scopes by `request.current_project`. The mental autopilot is to do the same here.

**Why it's wrong:** D-05 makes templates owner-scoped, not project-scoped. Adding `project=current_project` to any `MultitrackTemplate.objects.filter(...)` defeats the entire phase boundary.

**Mitigation:** S7 comment + grep audit (`grep -n "MultitrackTemplate.objects" planner/` — every filter must use `created_by=request.user` and only that).

### A4. Discriminator-on-same-model approach for templates

**Source of the bad pattern:** `CommConfig.is_template + template_name` at `planner/models.py:3963-3964`. Comm Config uses a single table with a `is_template` boolean discriminator.

**Why it's wrong here:** CONTEXT D-06 explicitly rejects this approach. Adding a discriminator pollutes every multitrack query with `.filter(is_template=False)`. Phase 3 uses the Audio Checklist approach: dedicated `MultitrackTemplate` + `MultitrackTemplateSlot` tables.

### A5. One-at-a-time `.objects.create` in a loop

See S6 above. The Audio Checklist save endpoint does this; the multitrack standard is bulk_create.

### A6. Storing `source_id` on slots (instead of `source_number`)

**Why it's tempting:** `MultitrackTrack` uses `source_id` (FK to channel-model row). Easiest copy-paste from `multitrack_duplicate` is to clone the same shape.

**Why it's wrong:** Templates need to be portable across consoles (CONTEXT D-02). `source_id` is a database PK; it changes between consoles. `source_number` (the engineer-meaningful channel label like `'1'` or `'L'`) is what makes templates portable.

**Mitigation:** Pattern Assignment 1 spells out the slot schema — `source_number` is a CharField, `source_id` is not present at all.

---

## No Analog Found

| File | Role | Data Flow | Reason / Recommendation |
|------|------|-----------|-------------------------|
| (none) | | | Every Phase 3 file has at least one close analog in the codebase. The two creative pieces — slot keying scheme (D-02) and apply-time skip-and-summarise (D-10) — are locked in CONTEXT, not free-form design. |

---

## Metadata

**Analog search scope:**
- `planner/models.py` (multitrack + audio_checklist + comm_config blocks)
- `planner/views.py` (audio_checklist endpoints, multitrack page views + AJAX endpoints, comm_config endpoints, `_multitrack_viewer_block`)
- `planner/admin.py` (MultitrackSessionAdmin, ConsoleImportAdmin, register block)
- `planner/admin_ordering.py` (full file)
- `planner/forms.py` (MultitrackSessionForm)
- `planner/urls.py` (multitrack route block)
- `planner/migrations/0152_multitrack_session_track.py` (Phase 1 migration shape)
- `planner/static/planner/js/multitrack_editor.js` (helpers + dashboard card menu)
- `planner/templates/planner/multitrack/*.html` (all 6 files in the multitrack template dir)

**Files scanned:** 11 (read in full or in relevant ranges)

**Pattern extraction date:** 2026-05-13

## PATTERN MAPPING COMPLETE
