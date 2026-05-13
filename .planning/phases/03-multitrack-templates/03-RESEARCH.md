# Phase 3: Multitrack Templates — Research

**Researched:** 2026-05-13
**Domain:** Django 5.x ModelForm + JSON-endpoint UX layer (template save/list/rename/delete) on top of an existing multitrack module
**Confidence:** HIGH (codebase is the authoritative source; CONTEXT.md decisions are locked; analog patterns are already shipped in the repo)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01 Hybrid template content.** Every template carries metadata; the track-list snapshot is optional. One save flow handles zero-slot and N-slot templates uniformly.
- **D-02 Cross-console portable slot keys.** Each `MultitrackTemplateSlot` is keyed by `(source_type, source_number)` (the channel-number/type pair), NOT by `source_id`. Apply matches the pair against the target console's `ConsoleInput.input_ch` / `ConsoleAuxOutput.aux_number` / `ConsoleMatrixOutput.matrix_number` / `ConsoleStereoOutput.stereo_type`.
- **D-03 Slot payload:** `position`, `source_type`, `source_number`, `label_override`, `color_override`, optional `notes`. No `enabled` field.
- **D-04 Save-with-zero-tracks is allowed.** Metadata-only templates are valid; apply seeds metadata, drops into the picker (matches Phase 1 D-12).
- **D-05 OWNER-scoped templates — NOT project-scoped.** `MultitrackTemplate.created_by = FK(User)`. No `project` FK. Visible to that user across all their projects. This is a deliberate divergence from `CurrentProjectMiddleware` — the one place Phase 3 diverges from the project's standard scoping.
- **D-06 Separate `MultitrackTemplate` + `MultitrackTemplateSlot` models.** Not a discriminator on `MultitrackSession`.
- **D-07 Save button lives on the session editor only** (`editor.html` action bar). No dashboard-card-menu duplication.
- **D-08 Apply UX = "Start from template (optional)" dropdown inside the existing New Session form.** Picking a template auto-populates the other fields client-side. One form, one place to learn.
- **D-09 Templates landing surface on the multitrack dashboard.** A "Templates" section listing templates with rename + delete actions.
- **D-10 Unmappable slots are skipped with a summary banner.** Banner: *"Applied template '{name}' — {mapped} of {total} slots mapped; {skipped} skipped ({reason})."*
- **D-11 Template metadata pre-fills the form when picked** via vanilla-JS `change` handler.
- **D-12 Apply is new-session-only.** No "Re-apply Template" action.
- **D-13 Empty-track-list templates** use the same apply flow — metadata seeded, picker auto-opens on Inputs. Banner: *"Applied template '{name}' — metadata seeded; no tracks in template."*
- **D-14/D-15/D-16 SPEC DEVIATIONS — do not implement:** `include_aux`/`include_matrix`/`include_groups` flags, `color_scheme` JSONField, `naming_pattern` format-string field. Each is dropped because per-slot data already encodes the information.

### Claude's Discretion

- Exact UI markup for the Templates section on the dashboard (second grid under sessions vs separate tab — match Phase 1 session-card pattern).
- Modal vs full-page for "Rename template" (Comm Config uses modals, Audio Checklist uses inline). Phase 1 already uses `window.prompt()` for `mtsRenameSession` (the lightest-footprint pattern).
- JS for the new-session-form template dropdown auto-population (vanilla JS, match `multitrack_editor.js` style).
- Whether `MultitrackTemplateSlot.notes` is stored at all — drop if judged useless.
- Whether to include `MultitrackTemplate.recorder_capacity` in D-11's auto-populate set.
- Index choices on `MultitrackTemplateSlot(template, position)` and `MultitrackTemplate(created_by)`.

### Deferred Ideas (OUT OF SCOPE)

- Re-apply template on existing sessions with replace/append choice (deferred).
- Editing a template's slot list after creation (v3.0 supports rename + delete only).
- Template duplication.
- `include_aux` / `include_matrix` / `include_groups` flags (D-14, dropped).
- `color_scheme` JSON map (D-15, dropped).
- `naming_pattern` format-string (D-16, dropped).
- Promote-to-shared / project-team-scoped sharing.
- Template versioning / edit history.
- POL-01 `default_record` boolean — Phase 5 work, not Phase 3.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TPL-01 | User can save the current session's structure as a named `MultitrackTemplate`. CONTEXT D-14/D-15/D-16 override the original wording — "structure" means metadata (target_daw, feed_source, track_order_mode, recorder_capacity, notes) + per-slot (source_type, source_number, label_override, color_override). | Save endpoint pattern from `audio_checklist_save_template` (views.py:4955); model shape from CONTEXT consolidated block. Editor `<button>` slots into existing action bar `editor.html:24-26`. |
| TPL-02 | User can apply a template to a new session, seeding the track list and metadata; per-track values can still be overridden afterward. | Apply happens inside `multitrack_create_view` POST handler after `form.save()`. Algorithm: walk `template.slots.all()` in `position` order, resolve `(source_type, source_number)` against target console's channel models, create `MultitrackTrack` rows. Skip unresolvable slots. |
| TPL-03 | User can list, rename, and delete templates from the module landing page. | `multitrack_dashboard` view passes `templates` queryset filtered by `created_by=request.user`; section rendered server-side under the session grid (matches `_session_card.html` pattern). Rename/delete via JSON endpoints + `window.prompt()` / `window.confirm()` (Phase 1 pattern, multitrack_editor.js:573-601). |
| TPL-04 | Save/load buttons, placement, modal behavior visually and behaviorally match existing ShowStack template patterns (Comm Config, Mic Tracker). | Audio Checklist save/list/load/delete (views.py:4955-5077) is the closest analog and uses the **same JSON-endpoint shape** Phase 3 will use. Comm Config (5347-5440) is the secondary reference but uses the discriminator-on-same-model approach Phase 3 does NOT copy. |
</phase_requirements>

## Summary

Phase 3 is a contained Django CRUD layer on top of the already-shipped Phase 1 multitrack module. It adds two new tables (`MultitrackTemplate`, `MultitrackTemplateSlot`), four new JSON endpoints (save / list / rename / delete), and three template touch-points (editor "Save as Template" button + modal, dashboard "Templates" section, new-session form template dropdown). All four success criteria are achievable with patterns that already exist in the repo:

- **Save / list / delete** mirror `audio_checklist_save_template` / `audio_checklist_list_templates` / `audio_checklist_delete_template` (views.py:4955-5077) verbatim, swapping `current_project` for `request.user` per D-05.
- **Apply** mirrors `multitrack_duplicate` (views.py:6045-6112) — same "create new session + bulk_create tracks in one transaction" shape, with the slot-resolution dispatch reusing `_source_model_for(source_type)` from models.py:1025.
- **Rename UX** matches the existing `mtsRenameSession` flow (multitrack_editor.js:573) — a `window.prompt()` call, no modal.
- **Editor button + modal** slots cleanly into the existing action bar at editor.html:24-26 (between "Edit session metadata" and the export buttons).

The one architectural divergence: templates are scoped to `request.user`, not `request.current_project` — a deliberate D-05 decision that needs a one-line comment on every template endpoint so future-Charlie doesn't reflexively add a `current_project` filter.

**Primary recommendation:** Build Phase 3 as five plans in two waves — Wave 1 = models/migration/admin/admin_ordering (foundation); Wave 2 = endpoints + form integration + apply logic + JS + templates (parallel-safe). The Audio Checklist analog is so close that most plan tasks can be literal copy-paste-and-rename from views.py:4955-5077.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Template model + slot rows | Database | — | `MultitrackTemplate` + `MultitrackTemplateSlot` are persistent records. Owner-scoped via `created_by` FK; no `project` FK. |
| Save current session → template (TPL-01) | Backend (Django view) | Browser (modal name input) | Editor "Save as Template" button opens a name-input modal; modal POSTs JSON `{name, session_id}` to a JsonResponse endpoint. Backend snapshots `session.tracks` into `template.slots`. |
| Apply template → seed new session (TPL-02) | Backend (Django view) | — | `multitrack_create_view` POST handler reads `template` field from form, then walks slots and creates `MultitrackTrack` rows after the `MultitrackSession` is created. Pure server-side. |
| Auto-populate form fields from template (D-11) | Browser (vanilla JS) | Backend (`data-*` attrs in HTML) | Template metadata serialized as `data-*` attributes on each `<option>` in the dropdown; `change` handler reads them and sets sibling field values. No round-trip to backend. |
| List templates on dashboard (TPL-03) | Backend (Django view → template render) | — | `multitrack_dashboard` queryset extended; partial renders the Templates section. Server-side render, matching the session card grid pattern. |
| Rename / delete templates (TPL-03) | Browser (window.prompt/confirm) → Backend (JsonResponse) | — | Matches Phase 1's `mtsRenameSession` / `mtsDeleteSession` exactly (multitrack_editor.js:573-601). |
| Admin browse + delete (back-office) | Backend (Django admin) | — | Both new models register on `showstack_admin_site`. Slots as read-only `TabularInline` on the template admin per CONTEXT specifics. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Django | 5.x | Models, ModelForm, JSON endpoints, admin, migrations | Project-wide stack; everything Phase 3 needs is already in Django stdlib. |
| Vanilla JS | — | Template dropdown auto-populate + rename/delete prompts | Phase 1's `multitrack_editor.js` is plain ES5-style vanilla JS with no framework. Match it. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `django.db.models` | (stdlib) | `ForeignKey(User)`, `unique_together`, indexes | All model definitions. |
| `django.contrib.auth.models.User` | (stdlib) | `created_by` FK target | Owner-scoping per D-05. |
| `django.http.JsonResponse` | (stdlib) | All four template endpoints | Same shape as `audio_checklist_save_template` and friends. |
| `django.views.decorators.http.require_POST` / `require_GET` | (stdlib) | Endpoint method gating | Existing pattern at views.py:18. |
| `@login_required` | (stdlib) | Auth gate on all template endpoints | Existing pattern. |
| `@staff_member_required` | (stdlib) | Page-render views (dashboard, new_session) | Existing pattern — see `multitrack_editor` (views.py:5965), `multitrack_create_view` (5992). |
| `_multitrack_viewer_block(request)` | project-local helper | Viewer role 403 on mutate endpoints | Defined at views.py:6213. Reuse verbatim. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Server-side dropdown auto-populate | Separate `GET /templates/<id>/json/` endpoint | One extra round-trip per dropdown change. With ≤ 50 templates the data inline as `data-*` attrs is trivial (< 1KB) and matches `picker_data_json` pattern in editor.html:102. |
| Modal for "Save as Template" name input | Full inline form on editor page | Adds visual clutter on a busy editor screen. A small modal (or `window.prompt`) is lighter. Phase 1 already proved `window.prompt` is acceptable for `mtsRenameSession`. Save-as-template may justify a real modal for the "name conflict" feedback loop — see Common Pitfalls. |
| Editing template slot list in admin | Read-only `TabularInline` on `MultitrackTemplateAdmin` | CONTEXT specifics line 195: engineers should rename/delete from the multitrack module, not edit slot lists in admin. Mirrors `ConsoleImportAdmin`'s readonly approach (admin.py:5943-5975). |

**Installation:** No new packages — everything is Django stdlib or already in the project.

**Version verification:**
```bash
python -c "import django; print(django.__version__)"  # confirms Django 5.x
```
`[VERIFIED: codebase grep — migration 0152 generated by Django 5.2.4]`

## Architecture Patterns

### System Architecture Diagram

```
                       BROWSER                                  SERVER (Django)                              DATABASE
                       ───────                                  ─────────────                                ────────
                                                                                                            
  Engineer on session editor                                                                                
  /audiopatch/multitrack/<id>/                                                                              
         │                                                                                                  
         │ clicks "Save as Template"                                                                        
         │                                                                                                  
         ▼                                                                                                  
  Modal opens, asks for name                                                                                
         │                                                                                                  
         │ POST {name, session_id}                                                                          
         │ /audiopatch/multitrack/templates/save/                                                           
         ├──────────────────────────────────────► multitrack_template_save                                  
         │                                          • @login_required + viewer_block                       
         │                                          • snapshot session metadata                            
         │                                          • walk session.tracks → build slots                     
         │                                          • catch IntegrityError on name conflict ──► INSERT MultitrackTemplate
         │                                                                                  └─► bulk_create MultitrackTemplateSlot
         │ ◄──── JSON {ok, template_id, name}                                                               
         │                                                                                                  
                                                                                                            
  Engineer on multitrack dashboard                                                                          
  /audiopatch/multitrack/                                                                                   
         │                                                                                                  
         │ GET                                                                                              
         ├──────────────────────────────────────► multitrack_dashboard                                      
         │                                          • sessions = filter(project=current_project)            
         │                                          • templates = filter(created_by=request.user) ◄── SELECT MultitrackTemplate
         │                                            └─ NOT scoped to current_project (D-05)               
         │ ◄──── HTML (sessions grid + templates section)                                                    
         │                                                                                                  
         │ clicks "Rename" on a template                                                                    
         │ window.prompt for new name                                                                       
         │ POST {template_id, new_name}                                                                     
         │ /audiopatch/multitrack/templates/<id>/rename/                                                    
         ├──────────────────────────────────────► multitrack_template_rename                                
         │                                          • verify template.created_by == request.user            
         │                                          • UPDATE name ──────────────────────────► UPDATE MultitrackTemplate
         │ ◄──── JSON {ok, name}                                                                            
         │                                                                                                  
                                                                                                            
  Engineer creates new session                                                                              
  /audiopatch/multitrack/new/                                                                               
         │                                                                                                  
         │ GET                                                                                              
         ├──────────────────────────────────────► multitrack_create_view (GET)                              
         │                                          • form = MultitrackSessionForm(request=request)         
         │                                          • templates queryset                  ◄── SELECT MultitrackTemplate
         │                                            filter(created_by=request.user)                       
         │ ◄──── HTML (form with template dropdown,                                                         
         │       each <option> carries data-* attrs                                                         
         │       with template metadata)                                                                    
         │                                                                                                  
         │ User picks template → JS `change` handler                                                        
         │   reads data-* attrs → sets target_daw,                                                          
         │   feed_source, track_order_mode,                                                                 
         │   recorder_capacity, notes form fields                                                           
         │                                                                                                  
         │ User submits form                                                                                
         │ POST {name, console, target_daw, ..., template_id}                                               
         ├──────────────────────────────────────► multitrack_create_view (POST)                             
         │                                          • form.is_valid()                                       
         │                                          • session = form.save()                ──► INSERT MultitrackSession
         │                                          • if cleaned_data['template']:                          
         │                                            └─ apply_template(template, session)                  
         │                                              ├─ walk slots in position order                     
         │                                              ├─ for each: _source_model_for(source_type)         
         │                                              │     .objects.filter(console=session.console,      
         │                                              │                     <number-field>=source_number) 
         │                                              ├─ create MultitrackTrack(source_type, source_id)   
         │                                              │   for resolved; skip for unresolved               
         │                                              └─ collect mapped/skipped counts                    
         │                                          • messages.info(banner text) ──┐                        
         │                                          • redirect to editor           │                        
         │ ◄──── HTTP 302 to /audiopatch/multitrack/<new_id>/ with messages cookie  │                        
         │                                                                          │                       
         │ GET                                                                      │                       
         ├──────────────────────────────────────► multitrack_editor renders ◄───────┘                       
         │ ◄──── HTML with banner: "Applied template 'X' — N of M slots mapped"                             
                                                                                                            
```

### Component Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| `MultitrackTemplate` model | `planner/models.py` (append after MultitrackTrack ~line 1120) | Persistent owner-scoped template metadata. `created_by` FK, `unique_together = [('created_by', 'name')]`. |
| `MultitrackTemplateSlot` model | `planner/models.py` (same block) | Per-slot child rows. FK to template with CASCADE. `unique_together = [('template', 'position')]`. |
| `apply_template_to_session(template, session)` helper | `planner/models.py` or `planner/views.py` | Pure function: takes a saved template + a newly-created session, walks slots, creates tracks, returns `(mapped_count, skipped_count, skipped_reasons)`. Recommend placing on `MultitrackTemplate` as an instance method for clean test surface. |
| `multitrack_template_save` view | `planner/views.py` | POST endpoint. Reads `{name, session_id}`. Snapshots metadata + slots. Handles `IntegrityError` (name conflict). Returns JSON. |
| `multitrack_template_list` view | (likely NOT needed) | The dashboard renders templates server-side; no separate JSON endpoint required. |
| `multitrack_template_rename` view | `planner/views.py` | POST `{template_id, new_name}`. Verifies `template.created_by == request.user`. Returns JSON. |
| `multitrack_template_delete` view | `planner/views.py` | POST `{template_id}`. Same ownership check. Returns JSON. |
| `multitrack_create_view` (modified) | `planner/views.py:5992` | Add template-dropdown field to form; POST handler calls `apply_template_to_session` after `form.save()`; `messages.info(banner)`. |
| `MultitrackSessionForm` (modified) | `planner/forms.py:1130` | Add `template = ModelChoiceField(queryset=MultitrackTemplate.objects.filter(created_by=request.user), required=False)`. |
| `MultitrackTemplateAdmin` | `planner/admin.py` | Read-mostly admin on `showstack_admin_site`. Slots as readonly `TabularInline`. Viewer-blocked on mutate. |
| `admin_ordering.py` order_map | `planner/admin_ordering.py:163-164` | Add `multitracktemplate: 52` and `multitracktemplateslot: 53` after the existing `multitracksession: 50` / `consoleimport: 51`. |
| Editor "Save as Template" button + modal | `planner/templates/planner/multitrack/editor.html:24-26` | New button in `.mts-editor-actions` div, modal markup elsewhere in the file (or as a partial). |
| Dashboard Templates section | `planner/templates/planner/multitrack/dashboard.html` (after line 49 — i.e., after the sessions grid) | New section with second grid; reuse `.mts-grid` / `.mts-card` CSS classes. |
| New-session form template dropdown + JS | `planner/templates/planner/multitrack/new_session.html` | New form row at the top of the form; inline `<script>` block with `change` handler. |
| `multitrack_editor.js` additions | `planner/static/planner/js/multitrack_editor.js` | `mtsSaveAsTemplate(sessionId)`, `mtsRenameTemplate(templateId, oldName)`, `mtsDeleteTemplate(templateId, name)`, `mtsApplyTemplateToForm(selectEl)` helpers. |

### Recommended Project Structure

No new directories. All changes land in existing files:

```
planner/
├── models.py                                # APPEND MultitrackTemplate + MultitrackTemplateSlot
├── admin.py                                 # APPEND MultitrackTemplateAdmin + register
├── admin_ordering.py                        # ADD 2 entries to order_map
├── forms.py                                 # MODIFY MultitrackSessionForm: + template ModelChoiceField
├── urls.py                                  # APPEND 4 routes under /audiopatch/multitrack/templates/...
├── views.py                                 # APPEND 3 template endpoints; MODIFY multitrack_create_view; MODIFY multitrack_dashboard
├── migrations/
│   └── 0154_multitrack_template.py          # NEW additive migration (next number after 0153)
├── static/planner/js/
│   └── multitrack_editor.js                 # APPEND 4 functions
└── templates/planner/multitrack/
    ├── dashboard.html                       # MODIFY: add Templates section
    ├── editor.html                          # MODIFY: add Save-as-Template button + modal
    └── new_session.html                     # MODIFY: add template dropdown + inline JS
```

### Pattern 1: Save endpoint shape (Audio Checklist analog)

**What:** JSON-body POST endpoint that snapshots the current session into a new template, deleting any same-named template owned by the user first (no "are you sure?" silent overwrite — Phase 3 follows this same convention).
**When to use:** All four template endpoints follow the same shape.

```python
# Source: planner/views.py:4955-4995 (audio_checklist_save_template) — verbatim shape

@login_required
@require_POST
def multitrack_template_save(request):
    """Save a session's structure as an owner-scoped template (TPL-01).

    Body: JSON {name: str, session_id: int}
    Returns: JsonResponse {ok, template_id, name} or {error, status: 4xx}

    OWNER-SCOPED per CONTEXT D-05 — uses request.user, NOT request.current_project.
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        data = json.loads(request.body or '{}')
        name = (data.get('name') or '').strip()
        session_id = data.get('session_id')
        if not name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(name) > 200:
            return JsonResponse({'error': 'Name must be 200 characters or fewer.'}, status=400)

        # IDOR guard: session must belong to user's current project
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)
        session = MultitrackSession.objects.filter(
            id=session_id, project=current_project,
        ).select_related('console').first()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        # Name conflict — friendly error, do NOT silently overwrite (departs from
        # audio_checklist_save_template's overwrite behaviour because templates
        # are reusable across many sessions and silent overwrite is destructive).
        if MultitrackTemplate.objects.filter(
            created_by=request.user, name=name,
        ).exists():
            return JsonResponse({
                'error': f'A template named "{name}" already exists. Pick a different name.',
            }, status=409)

        template = MultitrackTemplate.objects.create(
            created_by=request.user,
            name=name,
            target_daw=session.target_daw,
            feed_source=session.feed_source,
            track_order_mode=session.track_order_mode,
            recorder_capacity=session.recorder_capacity,
            notes=session.notes,
        )

        # Snapshot slots from session.tracks. Resolve each track's (source_type, source_number)
        # from the live channel-model row at save time.
        slots = []
        for position, track in enumerate(
            session.tracks.all().order_by('track_number'), start=1
        ):
            source_number = _resolve_source_number(track)   # helper below
            slots.append(MultitrackTemplateSlot(
                template=template,
                position=position,
                source_type=track.source_type,
                source_number=source_number,
                label_override=track.label_override,
                color_override=track.color_override,
            ))
        MultitrackTemplateSlot.objects.bulk_create(slots)

        return JsonResponse({
            'ok': True,
            'template_id': template.id,
            'name': template.name,
            'slot_count': len(slots),
        })
    except IntegrityError:
        # Defensive — race condition between the .exists() check and the .create()
        return JsonResponse({
            'error': f'A template named "{name}" already exists. Pick a different name.',
        }, status=409)
    except Exception:
        _multitrack_logger.exception('multitrack_template_save failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

### Pattern 2: Apply logic (helper + caller in `multitrack_create_view`)

**What:** A pure function that takes a template + a newly-created session and creates `MultitrackTrack` rows, resolving slot keys against the target console's channel-number fields.
**When to use:** Called from `multitrack_create_view` POST handler immediately after `session = form.save()`.

```python
# RECOMMENDED: place on MultitrackTemplate as an instance method for clean test surface.

class MultitrackTemplate(models.Model):
    # ... fields ...

    def apply_to_session(self, session):
        """Resolve slots → MultitrackTracks against the session's console.

        Returns (mapped, skipped, skipped_summary) where:
          - mapped: int count of slots that resolved to a channel row
          - skipped: int count of slots that could not be resolved
          - skipped_summary: str human description like
            "matrix 9-12 not present on this console"
            (empty when skipped == 0; collapses adjacent missing numbers
            into ranges for the banner).

        Order: walks template.slots.all() in position order. New track_numbers
        are assigned 1..N as rows are created (no pre-existing tracks on a
        brand-new session per Phase 1 D-12).
        """
        from .models import _source_model_for, MultitrackTrack
        # Channel-number field on each source-type model:
        number_field = {
            'input': 'input_ch',
            'aux': 'aux_number',
            'matrix': 'matrix_number',
            'stereo': 'stereo_type',
        }
        new_tracks = []
        mapped = 0
        skipped = []  # list of (source_type, source_number) tuples
        for slot in self.slots.all().order_by('position'):
            track_number = len(new_tracks) + 1
            if slot.source_type == 'manual':
                # Manual slots always materialise — no channel resolution needed.
                new_tracks.append(MultitrackTrack(
                    session=session,
                    track_number=track_number,
                    source_type='manual',
                    source_id=None,
                    label_override=slot.label_override,
                    color_override=slot.color_override,
                ))
                mapped += 1
                continue

            model = _source_model_for(slot.source_type)
            if model is None:
                skipped.append((slot.source_type, slot.source_number))
                continue
            field = number_field[slot.source_type]
            channel = model.objects.filter(
                console=session.console,
                **{field: slot.source_number},
            ).first()
            if channel is None:
                skipped.append((slot.source_type, slot.source_number))
                continue
            new_tracks.append(MultitrackTrack(
                session=session,
                track_number=track_number,
                source_type=slot.source_type,
                source_id=channel.id,
                label_override=slot.label_override,
                color_override=slot.color_override,
            ))
            mapped += 1

        MultitrackTrack.objects.bulk_create(new_tracks)
        skipped_summary = _summarise_skipped_slots(skipped)
        return mapped, len(skipped), skipped_summary
```

The caller in `multitrack_create_view`:

```python
# Modified planner/views.py:5992
@staff_member_required
def multitrack_create_view(request):
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')

    if request.method == 'POST':
        form = MultitrackSessionForm(request.POST, request=request)
        if form.is_valid():
            session = form.save()
            template = form.cleaned_data.get('template')   # NEW
            if template is not None:                       # NEW
                mapped, skipped, summary = template.apply_to_session(session)
                total = mapped + skipped
                if total == 0:
                    messages.info(
                        request,
                        f'Applied template "{template.name}" — metadata seeded; '
                        f'no tracks in template.',
                    )
                elif skipped == 0:
                    messages.info(
                        request,
                        f'Applied template "{template.name}" — '
                        f'{mapped} of {total} slots mapped.',
                    )
                else:
                    messages.info(
                        request,
                        f'Applied template "{template.name}" — {mapped} of {total} '
                        f'slots mapped; {skipped} skipped ({summary}).',
                    )
            return redirect('planner:multitrack_editor', session_id=session.id)
    else:
        form = MultitrackSessionForm(request=request)

    return render(request, 'planner/multitrack/new_session.html', {
        'form': form,
        'mode': 'create',
    })
```

### Pattern 3: Dropdown auto-populate via `data-*` attributes

**What:** Inline template metadata as `data-*` attributes on each `<option>` so the JS `change` handler can read them without any AJAX round-trip.
**When to use:** Lighter than a separate JSON endpoint; matches the `picker_data_json` server-rendered pattern at `editor.html:102`.

```django
{# Source: planner/templates/planner/multitrack/new_session.html — NEW form row #}

<div class="mts-form-row" data-template-dropdown>
  <label for="{{ form.template.id_for_label }}">Start from template (optional)</label>
  <select name="template" id="{{ form.template.id_for_label }}" onchange="mtsApplyTemplateToForm(this)">
    <option value="">— None —</option>
    {% for tmpl in form.template.field.queryset %}
      <option value="{{ tmpl.id }}"
              data-target-daw="{{ tmpl.target_daw }}"
              data-feed-source="{{ tmpl.feed_source }}"
              data-track-order-mode="{{ tmpl.track_order_mode }}"
              data-recorder-capacity="{{ tmpl.recorder_capacity|default:'' }}"
              data-notes="{{ tmpl.notes|escapejs }}"
              data-slot-count="{{ tmpl.slots.count }}">
        {{ tmpl.name }} ({{ tmpl.slots.count }} slot{{ tmpl.slots.count|pluralize }})
      </option>
    {% endfor %}
  </select>
  <p class="mts-help-text">
    Picking a template pre-fills the fields below. You can still change anything before submitting.
  </p>
</div>
```

```javascript
// APPEND to planner/static/planner/js/multitrack_editor.js

window.mtsApplyTemplateToForm = function (selectEl) {
  const opt = selectEl.options[selectEl.selectedIndex];
  if (!opt || !opt.value) return;   // "— None —" picked, leave form alone

  // Radio sets: target_daw, feed_source, track_order_mode
  function setRadio(name, value) {
    const radio = document.querySelector(
      'input[type=radio][name="' + name + '"][value="' + value + '"]'
    );
    if (radio) radio.checked = true;
  }
  setRadio('target_daw', opt.dataset.targetDaw || '');
  setRadio('feed_source', opt.dataset.feedSource || '');
  setRadio('track_order_mode', opt.dataset.trackOrderMode || '');

  // Plain inputs: recorder_capacity, notes
  const capInput = document.querySelector('input[name="recorder_capacity"]');
  if (capInput) capInput.value = opt.dataset.recorderCapacity || '';
  const notesInput = document.querySelector('textarea[name="notes"]');
  if (notesInput) notesInput.value = opt.dataset.notes || '';
};
```

### Anti-Patterns to Avoid

- **DON'T scope `MultitrackTemplate` querysets to `request.current_project`.** D-05 is explicit: templates belong to `request.user`, period. Add a comment on every endpoint: `# D-05: owner-scoped (request.user), NOT project-scoped.`
- **DON'T copy `audio_checklist_save_template`'s silent overwrite** (views.py:4965 deletes any same-named template first). For multitrack templates, name conflicts must produce a 409 with a friendly error so the engineer can pick a different name. Templates are reusable across many sessions; silent overwrite would silently destroy work.
- **DON'T add `MultitrackTrack`-style discriminator-by-`source_id`** to slots. Slots use `(source_type, source_number)` — the channel *number*, not the channel *row ID* — so templates port across consoles. Source CONTEXT D-02.
- **DON'T forget to register `MultitrackTemplate` on `showstack_admin_site`** (not `admin.site`) and add its entry to `admin_ordering.py` order_map. Both are CLAUDE.md non-negotiables.
- **DON'T register slots as a standalone admin if you also have them as an inline.** Pick one. CONTEXT specifics line 195 recommends the inline-only approach with readonly inline (mirrors `ConsoleImportAdmin`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slot ↔ channel-model dispatch | Custom `if source_type == 'input': ...` ladder | `_source_model_for(source_type)` at `planner/models.py:1025` | Already exists, already shipped, already tested. The dispatch table needs one helper for the channel-number field per source type — see Pattern 2. |
| Viewer-role gating on mutate endpoints | Hand-rolled `if user.groups.filter(name='Viewer').exists()` | `_multitrack_viewer_block(request)` at `planner/views.py:6213` | Centralised so every endpoint applies the same check (planner/views.py:6218 comment). |
| Track-creation bulk insert | One-track-at-a-time `MultitrackTrack.objects.create(...)` in a loop | `MultitrackTrack.objects.bulk_create(new_rows)` | Phase 1 already uses this (views.py:6414, 6103). Single INSERT round-trip. |
| CSRF in AJAX endpoints | Hand-rolled token shuffling | `{% csrf_token %}` hidden form (already present at `dashboard.html:53` and `editor.html:105`) + `csrfToken()` helper in `multitrack_editor.js:33` | Already wired through `postJSON` (multitrack_editor.js:38-47). |
| Dashboard "Templates" section card markup | New card template from scratch | Clone `_session_card.html` structure into a new `_template_card.html` partial | Visual consistency with the session grid is a TPL-04 success criterion. Same CSS classes, fewer fields. |
| Rename / delete confirmation flow | Custom modal | `window.prompt()` / `window.confirm()` (multitrack_editor.js:561, 574, 587) | Phase 1 already proved this UX is acceptable for `mtsRenameSession` and `mtsDeleteSession`. |
| "How does the JS know the CSRF token?" | Mutating cookies | Same `<form style="display:none">{% csrf_token %}</form>` pattern used in dashboard.html:53 and editor.html:105 | Already idiomatic in this codebase. |

**Key insight:** This phase has very few "build from scratch" moments. The Audio Checklist save/list/delete trio (views.py:4955-5077) plus the `multitrack_duplicate` view (views.py:6045-6112) together provide a near-complete template for everything Phase 3 needs. The two creative pieces are (a) the slot-keying scheme (D-02 — already locked in CONTEXT) and (b) the apply-time skip-and-summarise banner (D-10 — also locked). Everything else is "copy, rename, swap `current_project` for `request.user`."

## Common Pitfalls

### Pitfall 1: Silent name-conflict overwrite

**What goes wrong:** Engineer hits "Save as Template" with name "Drum Kit", overwrites an existing "Drum Kit" template from last week without warning.

**Why it happens:** `audio_checklist_save_template` (views.py:4965) literally does `.filter(...).delete()` before `.create(...)`. Copying that pattern verbatim creates the bug.

**How to avoid:** Make Phase 3's save endpoint return HTTP 409 on name conflict. The modal-name-input client UI surfaces the error and prompts for a different name. Do not silently delete.

**Warning signs:** No unique_together constraint at the DB level, save endpoint that deletes-before-create. Mitigation: enforce `unique_together = [('created_by', 'name')]` at the model level (already in CONTEXT consolidated block) and wrap the `.create()` in `try/except IntegrityError`.

### Pitfall 2: Forgetting D-05 owner-scoping; reflexively adding `current_project` filter

**What goes wrong:** Future-Charlie copies the rename endpoint and adds `.filter(project=current_project)` because every other planner view does that. Result: a template created on Project A is invisible when the user is currently active on Project B, defeating the whole point of owner-scoping.

**Why it happens:** `request.current_project` is the universal scoping pattern in this codebase. The mental autopilot is to filter by it.

**How to avoid:** Add a one-line comment on every template view: `# D-05: owner-scoped via request.user. Templates intentionally cross all of this user's projects.`

**Warning signs:** Grep for `MultitrackTemplate.objects` — every queryset must use `created_by=request.user` (and only that). No `project=current_project` references.

### Pitfall 3: ConsoleInput.input_ch is a CharField — "1" != "01"

**What goes wrong:** Template saved on a CL5 stores `('input', '1')`. Engineer imports a Rivage CSV that stores Inputs as zero-padded `('input', '01')`. Apply finds zero matches even though channel 1 exists.

**Why it happens:** All four channel-number fields are `CharField`:
- `ConsoleInput.input_ch` — `CharField(max_length=10)` (`[VERIFIED: planner/models.py:797]`)
- `ConsoleAuxOutput.aux_number` — `CharField(max_length=10)` (`[VERIFIED: planner/models.py:867]`)
- `ConsoleMatrixOutput.matrix_number` — `CharField(max_length=10)` (`[VERIFIED: planner/models.py:892]`)
- `ConsoleStereoOutput.stereo_type` — `CharField(max_length=2)`, values L/R/M (`[VERIFIED: planner/models.py:914]`)

String equality is exact; "1" != "01".

**How to avoid:** Inspect the Phase 2 CSV import code path (planner/views.py — `console_import_upload`) to confirm what string form it persists. If imports zero-pad, normalise both sides before comparison: `source_number.lstrip('0') or '0'`. If imports don't pad, store templates with whatever the source session has and accept that templates won't port between zero-padded and unpadded consoles.

**Warning signs:** Apply returns 0 mapped on a console that visually has the channels. Mitigation test: create a CL5 session with input_ch="1", save template, create a session on a console whose channels were imported as "01", apply. Document the behavior either way.

### Pitfall 4: Slot rows orphaned by source_type='input' → channel renumbered to a different ID

**What goes wrong:** Phase 1 D-04 has a `post_delete` signal that converts orphaned tracks to `source_type='manual'`. Templates have NO such relationship — they don't reference channel rows by ID, they reference them by `(source_type, source_number)`. So they're naturally immune to channel-row deletions.

**Why this is actually fine, not a pitfall:** Document explicitly: templates persist `source_number` (the engineer-meaningful channel label, e.g. "1", "Aux 3"), not `source_id` (the database row PK). Deleting and recreating a console channel with the same number reapplies cleanly.

**Implication:** No new signal needed for Phase 3. Slot rows live as long as the parent `MultitrackTemplate` lives.

### Pitfall 5: Dashboard layout breaks responsive design when Templates section is added

**What goes wrong:** Engineer with 12 sessions and 8 templates sees a wall of cards that overflows the viewport on mobile.

**Why it happens:** `dashboard.html:35-39` uses `.mts-grid` (likely a CSS grid with `auto-fill`/`minmax`). Adding a second `.mts-grid` directly underneath just doubles the row count.

**How to avoid:** Wrap each section in a labelled block with a heading (`<h2>Sessions</h2>` and `<h2>Templates</h2>`) and add a horizontal divider. Confirm the existing `multitrack.css` has classes for section headings (`.mts-section-header` or similar) — if not, the planner adds the CSS. The simplest treatment: two visually-distinct sections stacked, with `.mts-empty-state` rendering inside the Templates section when the user has none.

**Warning signs:** Beta tester reports "I can't tell my sessions apart from my templates."

### Pitfall 6: Form template field queryset isn't user-scoped → IDOR

**What goes wrong:** `MultitrackSessionForm.template` queryset defaults to `MultitrackTemplate.objects.all()`. Engineer A submits the form with `template=<engineer_B's_template_id>`. Engineer B's template gets applied to engineer A's new session — slot labels and metadata leak across tenants.

**Why it happens:** Forms don't auto-scope. The `ModelChoiceField` accepts any PK in the queryset.

**How to avoid:** In `MultitrackSessionForm.__init__`, after `super().__init__`, set:
```python
self.fields['template'].queryset = MultitrackTemplate.objects.filter(
    created_by=request.user
) if request else MultitrackTemplate.objects.none()
```
Mirrors the existing pattern at `forms.py:1160-1165` for the `console` field.

**Warning signs:** No `queryset` override in the form `__init__`. Mitigation test: log in as user A, manually submit a form POST with user B's template_id in the body, assert 400/422 (form validation fails).

### Pitfall 7: Tracks are saved at `enabled=True` default — slot doesn't have an enabled field

**What goes wrong:** Engineer creates a session, disables 8 tracks (enabled=False), saves as template. Applies template to a new session — all 8 tracks come back enabled.

**Why this is intentional, not a bug:** CONTEXT D-03 explicitly drops the `enabled` field from `MultitrackTemplateSlot`: *"every slot is an opt-in-by-design row."* If you didn't want it in the template, you wouldn't save it.

**How to handle:** Add a one-sentence note in the save endpoint docstring explaining this: *"Disabled tracks are NOT saved into the template — only enabled tracks become slots. To exclude a track from a future template, delete it before saving."* Recommend the planner filter `session.tracks.filter(enabled=True)` at save time.

**Warning signs:** Engineer complains "my disabled tracks came back enabled." Resolution: this is the spec, not a bug.

## Code Examples

### Model definitions (full)

```python
# APPEND to planner/models.py, after MultitrackTrack (~line 1120, before the # ─── separator at 1121)
# Source: CONTEXT consolidated block lines 73-100, with Discretion items resolved.

class MultitrackTemplate(models.Model):
    """Owner-scoped (NOT project-scoped) reusable session structure (Phase 3, v3.0).

    D-05 divergence: this model has NO `project` FK. Templates belong to the
    creating engineer and are visible across all of that engineer's projects
    via created_by=request.user filters in the views.
    """
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.CASCADE,
        related_name='multitrack_templates',
    )
    name = models.CharField(max_length=200)
    target_daw = models.CharField(
        max_length=20, choices=MultitrackSession.TARGET_DAW_CHOICES,
    )
    feed_source = models.CharField(
        max_length=20, choices=MultitrackSession.FEED_SOURCE_CHOICES,
    )
    track_order_mode = models.CharField(
        max_length=10, choices=MultitrackSession.TRACK_ORDER_MODE_CHOICES,
    )
    recorder_capacity = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Multitrack Template"
        verbose_name_plural = "Multitrack Templates"
        ordering = ['name']
        unique_together = [('created_by', 'name')]
        indexes = [
            models.Index(fields=['created_by'], name='mtt_owner_idx'),
        ]

    def __str__(self):
        return self.name

    # apply_to_session: see Pattern 2 above.


class MultitrackTemplateSlot(models.Model):
    """One row in a template's slot list (Phase 3, v3.0).

    Cross-console portable: keyed by (source_type, source_number) per D-02.
    Apply resolves these against the target console's channel-number CharFields:
      input -> ConsoleInput.input_ch
      aux -> ConsoleAuxOutput.aux_number
      matrix -> ConsoleMatrixOutput.matrix_number
      stereo -> ConsoleStereoOutput.stereo_type ('L'/'R'/'M')
      manual -> no channel resolution; new track materialises with label/color only
    """
    template = models.ForeignKey(
        MultitrackTemplate, on_delete=models.CASCADE, related_name='slots',
    )
    position = models.PositiveIntegerField(default=1)
    source_type = models.CharField(
        max_length=10, choices=MultitrackTrack.SOURCE_TYPE_CHOICES,
    )
    source_number = models.CharField(max_length=10, blank=True, default='')
    label_override = models.CharField(max_length=100, blank=True, default='')
    color_override = models.CharField(max_length=7, blank=True, default='')

    class Meta:
        verbose_name = "Multitrack Template Slot"
        verbose_name_plural = "Multitrack Template Slots"
        ordering = ['position']
        unique_together = [('template', 'position')]
        indexes = [
            models.Index(fields=['template', 'position'], name='mtt_slot_pos_idx'),
        ]

    def __str__(self):
        return f'#{self.position} {self.source_type} {self.source_number}'
```

### Migration shape

```python
# planner/migrations/0154_multitrack_template.py
# Generated by `python manage.py makemigrations planner` against the new models.

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0153_console_color_and_consoleimport'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MultitrackTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('target_daw', models.CharField(choices=[('reaper', 'Reaper'), ('nuendo_live', 'Nuendo Live')], max_length=20)),
                ('feed_source', models.CharField(choices=[('console_dante', 'Console Dante card'), ('rio_direct', 'RIO direct'), ('custom', 'Custom')], max_length=20)),
                ('track_order_mode', models.CharField(choices=[('console', 'Console channel order'), ('dante', 'Dante stream order'), ('custom', 'Custom (drag order)')], max_length=10)),
                ('recorder_capacity', models.PositiveIntegerField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='multitrack_templates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Multitrack Template',
                'verbose_name_plural': 'Multitrack Templates',
                'ordering': ['name'],
                'unique_together': {('created_by', 'name')},
                'indexes': [models.Index(fields=['created_by'], name='mtt_owner_idx')],
            },
        ),
        migrations.CreateModel(
            name='MultitrackTemplateSlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveIntegerField(default=1)),
                ('source_type', models.CharField(choices=[('input', 'Input'), ('aux', 'Aux Output'), ('matrix', 'Matrix Output'), ('stereo', 'Stereo Output'), ('manual', 'Manual')], max_length=10)),
                ('source_number', models.CharField(blank=True, default='', max_length=10)),
                ('label_override', models.CharField(blank=True, default='', max_length=100)),
                ('color_override', models.CharField(blank=True, default='', max_length=7)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='slots', to='planner.multitracktemplate')),
            ],
            options={
                'verbose_name': 'Multitrack Template Slot',
                'verbose_name_plural': 'Multitrack Template Slots',
                'ordering': ['position'],
                'unique_together': {('template', 'position')},
                'indexes': [models.Index(fields=['template', 'position'], name='mtt_slot_pos_idx')],
            },
        ),
    ]
```

Zero `ALTER TABLE` on existing tables. Two `CreateModel` operations only.
**Migration filename:** `0154_multitrack_template.py` (next sequential number after `0153_console_color_and_consoleimport.py`). `[VERIFIED: ls planner/migrations/ tail]`

### Admin registration

```python
# APPEND to planner/admin.py, after the existing ConsoleImportAdmin block (~line 5975).

class MultitrackTemplateSlotInline(admin.TabularInline):
    """Read-only inline for slots on the MultitrackTemplate admin.

    Per CONTEXT specifics line 195: engineers should NOT edit slot lists from
    Django admin. The multitrack module is the source of truth. Mirrors
    ConsoleImportAdmin's readonly approach (admin.py:5943-5975).
    """
    model = MultitrackTemplateSlot
    extra = 0
    can_delete = False
    fields = ('position', 'source_type', 'source_number', 'label_override', 'color_override')
    readonly_fields = ('position', 'source_type', 'source_number', 'label_override', 'color_override')

    def has_add_permission(self, request, obj=None):
        return False


class MultitrackTemplateAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'created_by', 'target_daw', 'feed_source', 'slot_count', 'updated_at']
    list_filter = ['target_daw', 'feed_source', 'track_order_mode']
    search_fields = ['name', 'created_by__username']
    readonly_fields = ('created_at', 'updated_at')
    inlines = [MultitrackTemplateSlotInline]

    def slot_count(self, obj):
        return obj.slots.count()
    slot_count.short_description = 'Slots'

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


# Append to the register block (~line 5983).
# IMPORTANT: only the parent model is registered; the slot model lives only as
# an inline. (Matches Phase 1's pattern — MultitrackTrack is NOT separately
# registered.)
showstack_admin_site.register(MultitrackTemplate, MultitrackTemplateAdmin)
```

### admin_ordering.py entry

```python
# planner/admin_ordering.py — modify order_map dict.
# Existing trailing entries (lines 162-165 in CURRENT file):
#   'multitracksession': 50,
#   'consoleimport': 51,

# REPLACE with:
'multitracksession': 50,
'multitracktemplate': 51,        # NEW — Phase 3
'consoleimport': 52,             # bumped from 51 to keep grouping order
```

`MultitrackTemplateSlot` is NOT registered standalone, so it doesn't need an order_map entry. If the planner decides to register it separately for some reason, append `'multitracktemplateslot': 53` after the slot model and add to the `always_hidden` set (it's a child, not a top-level concept).

### URL routes

```python
# APPEND to planner/urls.py after the existing multitrack route block (~line 130).

# Phase 3 — Multitrack Templates (TPL-01..TPL-04)
# All endpoints OWNER-scoped (request.user), NOT project-scoped (D-05).
path('multitrack/templates/save/', views.multitrack_template_save, name='multitrack_template_save'),
path('multitrack/templates/<int:template_id>/rename/', views.multitrack_template_rename, name='multitrack_template_rename'),
path('multitrack/templates/<int:template_id>/delete/', views.multitrack_template_delete, name='multitrack_template_delete'),
# NOTE: no /list/ endpoint — the dashboard renders templates server-side (Pattern 1 above).
```

### Form modification

```python
# Modify planner/forms.py:1130 — MultitrackSessionForm

class MultitrackSessionForm(forms.ModelForm):
    """ModelForm for creating / editing MultitrackSession (MTS-01, MTS-04, TPL-02).

    The `request` kwarg is REQUIRED — used to scope both the console queryset
    to the current project AND the template queryset to the current user.
    """
    # NEW: Phase 3 template dropdown — not a model field (templates have no
    # session FK), so it's a plain ModelChoiceField. Form's POST handler in
    # multitrack_create_view reads cleaned_data['template'] and applies it.
    template = forms.ModelChoiceField(
        queryset=MultitrackTemplate.objects.none(),   # set in __init__
        required=False,
        empty_label='— None —',
        label='Start from template (optional)',
        help_text='Picking a template pre-fills the fields below.',
    )

    class Meta:
        model = MultitrackSession
        fields = [
            'name', 'console', 'target_daw', 'feed_source',
            'track_order_mode', 'recorder_capacity', 'notes',
        ]
        # ... existing widgets ...

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

        # Existing console scoping (forms.py:1160-1165) — unchanged.
        if request is not None and getattr(request, 'current_project', None):
            self.fields['console'].queryset = Console.objects.filter(
                project=request.current_project
            )
        else:
            self.fields['console'].queryset = Console.objects.none()

        # NEW: D-05 owner-scoped template queryset. Templates intentionally
        # cross all of this user's projects.
        if request is not None and request.user.is_authenticated:
            self.fields['template'].queryset = MultitrackTemplate.objects.filter(
                created_by=request.user
            ).order_by('name')
        else:
            self.fields['template'].queryset = MultitrackTemplate.objects.none()

        # ... rest of __init__ unchanged ...
```

### Dashboard Templates section markup

```django
{# planner/templates/planner/multitrack/dashboard.html — APPEND after line 49 (after the sessions block) #}

<div class="mts-section-divider"></div>

<div class="mts-section">
  <div class="mts-section-header">
    <h2 class="mts-h2">Templates</h2>
    <p class="mts-caption">
      Reusable session structures. Saved templates apply to new sessions on any console.
    </p>
  </div>

  {% if templates %}
    <div class="mts-grid">
      {% for template in templates %}
        {% include "planner/multitrack/_template_card.html" with template=template %}
      {% endfor %}
    </div>
  {% else %}
    <p class="mts-empty-state mts-empty-state--inline">
      No templates yet. Open a session and click "Save as Template" to create one.
    </p>
  {% endif %}
</div>
```

```django
{# NEW partial: planner/templates/planner/multitrack/_template_card.html #}
{% load humanize %}
<div class="mts-card mts-card--template" data-template-id="{{ template.id }}">
  <div class="mts-card-title">{{ template.name }}</div>
  <div class="mts-card-meta">
    {{ template.slots.count }} slot{{ template.slots.count|pluralize }} ·
    {{ template.get_target_daw_display }} ·
    updated {{ template.updated_at|timesince }} ago
  </div>
  <div class="mts-card-actions">
    <button type="button" class="mts-card-menu-trigger"
            aria-label="Template actions"
            onclick="mtsToggleCardMenu(this, 'tmpl-{{ template.id }}')">⋯</button>
    <div class="mts-dropdown-menu" id="mts-card-menu-tmpl-{{ template.id }}">
      <button type="button" class="mts-dropdown-item"
              onclick="mtsRenameTemplate({{ template.id }}, '{{ template.name|escapejs }}')">Rename</button>
      <button type="button" class="mts-dropdown-item mts-dropdown-item--danger"
              onclick="mtsDeleteTemplate({{ template.id }}, '{{ template.name|escapejs }}')">Delete</button>
    </div>
  </div>
</div>
```

`multitrack_dashboard` view modification:

```python
# Modify planner/views.py:5753 — multitrack_dashboard

@login_required   # Add if not already present — it's currently not gated
def multitrack_dashboard(request):
    current_project = getattr(request, 'current_project', None)
    sessions = (
        MultitrackSession.objects.filter(project=current_project)
        .select_related('console')
        .order_by('-updated_at')
        if current_project else MultitrackSession.objects.none()
    )
    # D-05: templates are OWNER-scoped, not project-scoped. They follow the
    # engineer across all their projects.
    templates = (
        MultitrackTemplate.objects.filter(created_by=request.user)
        .order_by('name')
        if request.user.is_authenticated else MultitrackTemplate.objects.none()
    )
    can_import_console_csv = (
        request.user.is_authenticated
        and not request.user.groups.filter(name='Viewer').exists()
    )
    return render(request, 'planner/multitrack/dashboard.html', {
        'sessions': sessions,
        'templates': templates,         # NEW
        'current_project': current_project,
        'can_import_console_csv': can_import_console_csv,
    })
```

### Editor "Save as Template" button + JS

```django
{# planner/templates/planner/multitrack/editor.html:24-26 — modify .mts-editor-actions #}

<div class="mts-editor-actions">
  <a class="mts-btn-tertiary" href="{% url 'planner:multitrack_edit' session.id %}">Edit session metadata</a>
  <button type="button" class="mts-btn-tertiary"
          onclick="mtsSaveAsTemplate({{ session.id }}, '{{ session.name|escapejs }}')">Save as Template</button>
</div>
```

```javascript
// APPEND to multitrack_editor.js

// ──────────────────────────────────────────────────────────────
// Template save / rename / delete (Phase 3 / v3.0)
// All endpoints are OWNER-scoped (created_by=request.user) per D-05.
// ──────────────────────────────────────────────────────────────

window.mtsSaveAsTemplate = function (sessionId, sessionName) {
  const defaultName = sessionName ? sessionName + ' template' : '';
  const name = window.prompt(
    'Save current session as a reusable template.\n' +
    'Templates are visible across all your projects.\n\n' +
    'Template name:',
    defaultName
  );
  if (name === null || name.trim() === '') return;
  postJSON('/audiopatch/multitrack/templates/save/', {
    name: name.trim(),
    session_id: sessionId,
  }).then(function (resp) {
    if (resp.status === 200 && resp.data.ok) {
      showToast(
        'Template "' + resp.data.name + '" saved (' +
        resp.data.slot_count + ' slot' + (resp.data.slot_count === 1 ? '' : 's') + ').',
        'success'
      );
    } else {
      showToast(resp.data.error || 'Save failed.', 'error');
    }
  });
};

window.mtsRenameTemplate = function (templateId, oldName) {
  const newName = window.prompt('Rename template:', oldName);
  if (newName === null || newName.trim() === '') return;
  postJSON('/audiopatch/multitrack/templates/' + templateId + '/rename/', {
    new_name: newName.trim(),
  }).then(function (resp) {
    if (resp.status === 200 && resp.data.ok) {
      window.location.reload();
    } else {
      showToast(resp.data.error || 'Rename failed.', 'error');
    }
  });
};

window.mtsDeleteTemplate = function (templateId, name) {
  const ok = window.confirm(
    'Delete template "' + name + '"?\n\n' +
    'This will permanently delete the template and all its slots. ' +
    'Sessions previously created from this template are not affected.'
  );
  if (!ok) return;
  postJSON('/audiopatch/multitrack/templates/' + templateId + '/delete/', {})
    .then(function (resp) {
      if (resp.status === 200 && resp.data.ok) {
        window.location.reload();
      } else {
        showToast(resp.data.error || 'Delete failed.', 'error');
      }
    });
};
```

### Rename / Delete endpoint shape

```python
# planner/views.py — APPEND

@login_required
@require_POST
def multitrack_template_rename(request, template_id):
    """POST: rename an owner-scoped template (TPL-03).

    Body: JSON {new_name: str}
    Returns: JsonResponse {ok, name} or {error, status: 4xx}

    D-05: owner-scoped via request.user. NOT project-scoped.
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        # IDOR / ownership guard: created_by=request.user combined filter.
        template = MultitrackTemplate.objects.filter(
            id=template_id, created_by=request.user,
        ).first()
        if not template:
            return JsonResponse({'error': 'Template not found'}, status=404)

        data = json.loads(request.body or '{}')
        new_name = (data.get('new_name') or '').strip()
        if not new_name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(new_name) > 200:
            return JsonResponse({'error': 'Name must be 200 characters or fewer.'}, status=400)

        if MultitrackTemplate.objects.filter(
            created_by=request.user, name=new_name,
        ).exclude(pk=template.pk).exists():
            return JsonResponse({
                'error': f'A template named "{new_name}" already exists. Pick a different name.',
            }, status=409)

        template.name = new_name
        template.save(update_fields=['name', 'updated_at'])
        return JsonResponse({'ok': True, 'name': new_name})
    except Exception:
        _multitrack_logger.exception('multitrack_template_rename failed')
        return JsonResponse({'error': 'Server error.'}, status=500)


@login_required
@require_POST
def multitrack_template_delete(request, template_id):
    """POST: delete an owner-scoped template + (via CASCADE) all its slots (TPL-03).

    D-05: owner-scoped via request.user. NOT project-scoped.
    """
    viewer_block = _multitrack_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        template = MultitrackTemplate.objects.filter(
            id=template_id, created_by=request.user,
        ).first()
        if not template:
            return JsonResponse({'error': 'Template not found'}, status=404)
        template.delete()
        return JsonResponse({'ok': True})
    except Exception:
        _multitrack_logger.exception('multitrack_template_delete failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Spec proposed `MultitrackTemplate(project=FK)` with `include_aux`/`include_matrix`/`include_groups` BooleanFields, `color_scheme` JSONField, `naming_pattern` CharField | CONTEXT D-05/D-14/D-15/D-16 → owner-scoped (`created_by=FK(User)`), no boolean inclusion flags (slot list encodes it), no color_scheme map (per-slot color_override does it), no naming_pattern (per-slot label_override does it) | CONTEXT 2026-05-13 | Smaller, more honest model. Spec proposed two-sources-of-truth (boolean flags + slot list) and engineering tax (format-string parser). All dropped. |
| Comm Config template approach: discriminator on same model (`CommConfig.is_template + template_name`, planner/models.py:3750) | Separate `MultitrackTemplate` model with slot child table (Audio Checklist analog) | CONTEXT D-06 | Avoids `.filter(is_template=False)` polluting every multitrack query. |
| Audio Checklist save endpoint: silent overwrite on name conflict (views.py:4965 — `.delete()` before `.create()`) | Phase 3: 409 error + friendly message, force engineer to pick a different name | This research | Prevents destructive silent-overwrite of templates the engineer doesn't realise are still in use. |
| Phase 1 New Session form: 6 fields (name, console, target_daw, feed_source, track_order_mode, recorder_capacity, notes) | Phase 3 New Session form: 7 fields, +`template` (optional ModelChoiceField at top of form) | This phase | Minimal additive form change. Phase 1 form pattern preserved. |

**Deprecated/outdated:**
- The spec's `naming_pattern = "{channel_name}"` format-string convention — dropped per D-16. Engineers can hand-edit each label_override; this is what they actually do, per the discussion.
- `MultitrackTemplate.project = FK(Project)` per spec line 98 — replaced with `created_by = FK(User)` per D-05.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "ConsoleAuxOutput.aux_number stores the same string format on both manually-created and CSV-imported consoles" | Common Pitfalls — Pitfall 3 | If CSV import zero-pads ("01") and admin entry doesn't ("1"), templates ported across won't resolve. Mitigation: planner does a one-off inspection of `console_import_upload` to confirm the persisted format. `[ASSUMED]` |
| A2 | "`window.prompt` + `window.confirm` are acceptable UX for v3.0 rename/delete" | Pattern 3 / Common Pitfalls | If Charlie wants a real modal for visual consistency with Comm Config, the planner will need to add modal markup + open/close JS. Phase 1 already proved `window.prompt` is acceptable for session rename (`mtsRenameSession`, multitrack_editor.js:573) — extending the same pattern is the conservative choice. `[VERIFIED: codebase — pattern already in use]` |
| A3 | "`messages.info(banner)` is the right surface for D-10's apply-result banner" | Pattern 2 — apply caller | If the dashboard's existing `mts-banners` block doesn't render `info`-level messages (only `success`/`error`), the planner adds CSS. `dashboard.html:14-19` shows banners for messages of any level using `mts-banner-{{ message.level_tag }}` — should JustWork. `[VERIFIED: dashboard.html:14-19]` |
| A4 | "The new-session form template doesn't currently have a `<script>` block, so adding inline JS is additive without breaking anything" | Pattern 3 | `new_session.html` is 109 lines, no script tag. Adding one is safe. `[VERIFIED: full file read]` |
| A5 | "The slot `notes` field from D-03's optional payload is NOT worth carrying — engineers re-key tracks in a fresh session and notes are session-level concerns" | CONTEXT Discretion + model definitions | If engineers later complain, add it in a follow-up migration. No data loss. `[ASSUMED]` based on D-03 explicitly marking it optional and the CONTEXT Discretion guidance suggesting it can be dropped. |
| A6 | "Modal vs `window.prompt` for Save-as-Template should be `window.prompt` for v3.0, with the caveat that 409 name-conflict needs a re-prompt loop" | Pattern 1 / Common Pitfalls 1 | If Charlie wants modal UX from day one, the planner adds modal markup. `window.prompt` doesn't have a great "show error and re-prompt" loop, so a follow-up sequence on 409 can call `prompt(error_message + '\nTry a different name:', ...)` recursively. `[ASSUMED]` |
| A7 | "`apply_to_session` belongs on the `MultitrackTemplate` model as a method, not as a standalone helper in views" | Pattern 2 | Cleaner test surface (`template.apply_to_session(session)` is easier to unit-test than reaching into a view). If the planner prefers a free function, that's fine too — no architectural cost. `[ASSUMED]` |
| A8 | "Disabled tracks are NOT saved into the template — only enabled tracks become slots" | Common Pitfalls 7 | If engineers want disabled tracks captured (so the template's "shape" is preserved), the planner reverses this default. Recommend going with enabled-only and documenting in the save endpoint docstring. `[ASSUMED]` |

## Project Constraints (from CLAUDE.md)

Directives the planner MUST honor:

1. **Register admin on `showstack_admin_site`, NOT `admin.site`.** (CLAUDE.md "Custom admin site")
2. **Update `planner/admin_ordering.py` when a new admin-registered model is added.** Non-negotiable. (CLAUDE.md "Custom admin site")
3. **Additive migrations only against beta-tester data — zero `ALTER TABLE` of existing fields.** (CLAUDE.md "Architecture" + Phase 1/2 CONTEXT)
4. **`CurrentProjectMiddleware` is the standard scoping pattern** — but Phase 3 deliberately diverges per D-05 (owner-scoped templates). Document this clearly on every template endpoint with a `# D-05` comment.
5. **All planner views scope to `request.current_project`** except where explicitly stated otherwise (templates, in this phase).
6. **Role gates (CLAUDE.md):** `superuser` / `premium owner` / `editor` can mutate; `viewer` is read-only. Apply via `_multitrack_viewer_block(request)` on all mutate endpoints.
7. **Two template directories** (`templates/` and `planner/templates/`) — Phase 3 templates go in `planner/templates/planner/multitrack/` alongside existing multitrack templates.
8. **CSS `!important` override rule** — irrelevant to Phase 3 (no admin JS overrides).
9. **Don't commit `.env`, Resend keys, Railway tokens.** Phase 3 doesn't touch any of these.
10. **Don't touch factory pouchdb / COMM Config logic.** Phase 3 doesn't.
11. **`collectstatic` runs in Procfile.** Any new static assets (none in Phase 3 — only edits to existing `multitrack_editor.js`) get picked up automatically.

## Validation Architecture

> `workflow.nyquist_validation: false` in `.planning/config.json`. Section omitted.

## Open Questions

1. **Should disabled tracks be filtered out at save time, or included as slots?**
   - What we know: D-03 explicitly drops the `enabled` field from slots. The team values "every slot is an opt-in-by-design row."
   - What's unclear: Does "opt-in" mean "the engineer affirmatively enabled it when saving" (filter at save) or "the engineer will affirmatively pick it next time" (include everything, force engineer to disable on the new session)?
   - Recommendation: Filter at save time (`session.tracks.filter(enabled=True)`). Engineers who disabled a track on the source session were saying "not this time" — a fresh session shouldn't re-enable it. Document in save endpoint docstring.

2. **Is `recorder_capacity` part of D-11's auto-populate set?**
   - What we know: D-11 says "the other form fields (target_daw, feed_source, track_order_mode, recorder_capacity, notes) auto-populate." So yes, planned.
   - What's unclear: Whether `recorder_capacity` blank on the template should leave the form field unchanged or actively clear it (set to empty).
   - Recommendation: Active clear. If the engineer set capacity on the template (or left it blank), respect both signals literally.

3. **Should the editor's "Save as Template" button be hidden when the session has zero tracks, or always shown?**
   - What we know: D-04 explicitly allows zero-track templates.
   - What's unclear: Whether the UX should encourage zero-track templates by always showing the button, or surface a friendly "save metadata-only template?" prompt when zero tracks exist.
   - Recommendation: Always show. D-04 makes zero-track templates a first-class concept; the button doesn't need special-casing.

4. **Where on the dashboard does the Templates section sit relative to the sessions grid — above or below?**
   - What we know: CONTEXT specifics line 195 and D-09 say "under or alongside the session grid."
   - What's unclear: Below feels right (sessions are the engineer's current focus; templates are reference). Above feels right if the engineer is on the dashboard mainly to start a new session from a template.
   - Recommendation: Below, with a `mts-section-divider`. Engineers on the dashboard usually want to resume work on an existing session; templates are a secondary affordance.

## Sources

### Primary (HIGH confidence)
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/phases/03-multitrack-templates/03-CONTEXT.md` — locked decisions (D-01 through D-16)
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/REQUIREMENTS.md` — TPL-01..04 source
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/ROADMAP.md` — Phase 3 success criteria
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/CLAUDE.md` — project conventions (admin site, additive migrations, role gating)
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/models.py:971-1119` — Phase 1 `MultitrackSession` + `MultitrackTrack` shipped definitions
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/models.py:1024-1035` — `_source_model_for` dispatch helper
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/models.py:3860-3911` — `AudioChecklistTemplate` + `AudioChecklistTemplateTask` — closest model analog
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/views.py:4955-5077` — Audio Checklist save / list / load / delete — closest endpoint analog
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/views.py:5347-5440` — Comm Config save / list / load — secondary endpoint analog
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/views.py:5753-6010` — Phase 1 multitrack page-render views (`multitrack_dashboard`, `multitrack_editor`, `multitrack_create_view`)
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/views.py:6045-6112` — `multitrack_duplicate` — closest "create new session + bulk_create tracks" analog
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/views.py:6213-6223` — `_multitrack_viewer_block` helper
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/forms.py:1130-1225` — `MultitrackSessionForm`
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/admin.py:5905-5984` — `MultitrackSessionAdmin` + `ConsoleImportAdmin` registration patterns
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/admin_ordering.py` — order_map; current trailing entries `multitracksession: 50`, `consoleimport: 51`
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/static/planner/js/multitrack_editor.js:551-601` — Phase 1 dashboard card menu functions (`mtsToggleCardMenu`, `mtsDuplicateSession`, `mtsRenameSession`, `mtsDeleteSession`) — direct UX precedent
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/templates/planner/multitrack/dashboard.html` — full template, integration target for Templates section
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/templates/planner/multitrack/editor.html:24-26` — action bar, integration target for "Save as Template" button
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/templates/planner/multitrack/_session_card.html` — pattern for `_template_card.html`
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/templates/planner/multitrack/new_session.html` — form template, integration target for template dropdown
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/migrations/0152_multitrack_session_track.py` — Phase 1 migration shape; `/0153_console_color_and_consoleimport.py` — most recent migration
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/urls.py:97-129` — multitrack URL block; integration target for new template routes
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/tests/test_console_csv_import_views.py` — existing Django `TestCase`-style test pattern; uses `Client`, `force_login`, session cookie for `current_project_id`

### Secondary (MEDIUM confidence)
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/multitrack_session_builder_spec.md:92-114` — spec proposal that CONTEXT D-05/D-14/D-15/D-16 deviate from
- `/Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/phases/01-core-sessions-track-editor-reaper-export/01-CONTEXT.md` — Phase 1 locked decisions (informs source_type contract, `_source_model_for` helper)

### Tertiary (LOW confidence)
- None — every claim in this research is backed by either CONTEXT.md, the codebase, or an existing shipped pattern.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library used is Django stdlib, already in the project, already in use in similar shipped code
- Architecture: HIGH — CONTEXT.md locks all major decisions; only minor UX polish is open
- Apply algorithm: HIGH — direct dispatch via existing `_source_model_for` helper; channel-number CharField semantics verified against model definitions
- Common pitfalls: MEDIUM — pitfall 3 (zero-padding) is `[ASSUMED]` pending one inspection of Phase 2 CSV import behavior; everything else verified
- Test surface: HIGH — pattern is `planner/tests/test_console_csv_import_views.py` style (Django `TestCase` + `Client` + `force_login` + session cookie). No new framework needed.

**Research date:** 2026-05-13
**Valid until:** 2026-06-13 (30 days — Phase 1 just shipped, code is fresh, no external dependencies likely to drift)

## RESEARCH COMPLETE
