# Phase 1: Core Sessions, Track Editor & Reaper Export — Pattern Map

**Mapped:** 2026-05-09
**Files analyzed:** 17 new files + 5 append-targets = 22
**Analogs found:** 22 / 22

> Codebase analogs come from a single Django project (`planner` app). Every new
> file in Phase 1 has at least one strong existing analog in the codebase.
> Phase 1 introduces NO new architectural patterns — it threads the existing
> `comm_config_view` + `BaseEquipmentAdmin` + `showstack_admin_site` +
> `CurrentProjectMiddleware` + `yamaha_export.py` patterns onto two new tables.

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `planner/models.py` (append `MultitrackSession`, `MultitrackTrack` near line 911) | model | CRUD | `Console` (`planner/models.py:754`) + `AudioChecklistTemplate` (`planner/models.py:3647`) | exact |
| `planner/migrations/00XX_multitrack_session_track.py` | migration | schema-create | (every existing migration in `planner/migrations/`) — additive new tables only | exact (new-tables-only convention) |
| `planner/admin.py` (append `MultitrackSessionAdmin`, `MultitrackTrackAdmin`) | admin | CRUD via Django admin | `ConsoleAdmin` (`planner/admin.py:781`) for editor admin; `CommConfigAdmin` (`planner/admin.py:5932`) for "redirect-to-custom-page" admin | exact (two complementary patterns) |
| `planner/admin_ordering.py` (add `multitracksession` entry) | config | (n/a) | the existing `order_map` block (`planner/admin_ordering.py:79-151`) | exact |
| `planner/views.py` (append `multitrack_dashboard`, `multitrack_editor`, `multitrack_create_view`, `multitrack_duplicate`, `multitrack_rename`, `multitrack_delete`, `multitrack_reorder`, `multitrack_add_tracks`, `multitrack_set_color`, `multitrack_set_label`, `multitrack_remove_track`, `multitrack_export_rpp`, `multitrack_export_rtracktemplate`, `multitrack_capacity_check`) | view (mixed) | `comm_config_view` (`planner/views.py:1882`) for list+editor dual mode; `comm_config_create` (`planner/views.py:3754`) for AJAX mutate; `comm_config_update_lan` (`planner/views.py:5316`) for PATCH-style endpoint | exact |
| `planner/urls.py` (append `/audiopatch/multitrack/...` routes) | route | (n/a) | the existing comm-config block (`planner/urls.py:60-95`) | exact |
| `planner/signals.py` (append four `post_delete` receivers + `_convert_orphans_to_manual`) | signal handler | event-driven | `ensure_user_profile` `post_save` (`planner/signals.py:8-27`) | role-match (post_save → post_delete; identical try/except idempotency idiom) |
| `planner/forms.py` (append `MultitrackSessionForm`) | form | request-response | `ConsoleInputForm` (`planner/forms.py:50-105`) | role-match (ModelForm w/ widget styling) |
| `planner/utils/reaper_export.py` (NEW) | utility (export) | file-I/O / streaming | `planner/utils/yamaha_export.py:1-30` (export_yamaha_csvs) | exact (file-download utility shape) |
| `planner/templates/planner/multitrack/dashboard.html` (NEW) | template | server-rendered | `templates/planner/comm_config.html:1-130` (header + cc-grid card list) | exact |
| `planner/templates/planner/multitrack/editor.html` (NEW) | template | server-rendered | `templates/planner/comm_config.html:665-693` (editor header + tab bar) | exact |
| `planner/templates/planner/multitrack/new_session.html` (NEW) | template | form-render | `templates/planner/comm_config.html` (modal-style form sections) — closest is the new-config flow inside dashboard; also use Django admin change_form fallback shape | role-match |
| `planner/templates/planner/multitrack/_picker_modal.html` (NEW partial) | template (partial) | server-rendered modal | `templates/admin/base_site.html:138-170` (help-modal overlay) — UI-SPEC explicitly cites this | exact |
| `planner/templates/planner/multitrack/_track_row.html` (NEW partial) | template (partial) | server-rendered row | `templates/planner/comm_config.html:697-720` (cc-pl-card per-row partial pattern, inline) | role-match |
| `planner/templates/planner/multitrack/_color_picker.html` (NEW partial) | template (partial) | server-rendered popover | (no exact analog — vanilla CSS popover; cite `comm_config.html` modal styling) | partial-match |
| `planner/templates/planner/multitrack/_session_card.html` (NEW partial) | template (partial) | server-rendered card | `templates/planner/comm_config.html:634-654` (cc-card grid item) | exact |
| `planner/static/planner/js/multitrack_editor.js` (NEW) | JS | client mutate + AJAX | `templates/planner/comm_config.html:1149-1212` (inline JS — fetch w/ CSRF, modal open/close, helper fns) — closest because `comm_admin.js` (29 lines) is a tiny color-row coloring shim, not a module-controller pattern | role-match (extract idioms; new file is much larger) |
| `planner/static/planner/js/multitrack_picker.js` (NEW — OPTIONAL; merge into editor.js if small) | JS | client mutate + AJAX | same as above | role-match |
| `planner/static/planner/css/multitrack.css` (NEW — `mts-` prefix) | CSS | (n/a) | `templates/planner/comm_config.html:10-300` inline style block (`cc-` prefix) — extract the same dark-shell tokens | exact (mirror prefix and tokens) |
| `planner/static/planner/js/vendor/Sortable.min.js` (NEW vendored) | JS (vendor) | (n/a) | (no existing vendored JS in the repo — first one) | no-analog (vendor file, not a pattern) |

---

## Pattern Assignments

### `planner/models.py` append (`MultitrackSession`, `MultitrackTrack`)

**Role:** model · **Data flow:** CRUD · **REQ:** MTS-01..06, TRK-01..10

**Primary analog:** `Console` (`planner/models.py:754-774`) — establishes the
`project = ForeignKey('Project', on_delete=CASCADE)` shape that
`BaseEquipmentAdmin.save_model` (admin.py:98) auto-fills from
`request.current_project`.

**Secondary analog:** `AudioChecklistTemplate` (`planner/models.py:3647-3665`)
— establishes the `unique_together = [('project', 'name')]` constraint and
`updated_at = DateTimeField(auto_now=True)` audit fields that the dashboard
"updated {time_ago}" line in UI-SPEC requires.

**Concrete excerpt — project-scoped equipment header** (`planner/models.py:754-774`):

```python
class Console(models.Model):
    project = models.ForeignKey('Project', on_delete=models.CASCADE, null=True, blank=True)
    location = models.ForeignKey('Location', on_delete=models.SET_NULL, null=True, blank=True, related_name='consoles')
    name = models.CharField(max_length=100)
    is_template = models.BooleanField(
        default=False,
        help_text="Mark this console as a template for creating new consoles"
    )
    primary_ip_address = models.GenericIPAddressField(blank=True, null=True, ...)
    secondary_ip_address = models.GenericIPAddressField(blank=True, null=True, ...)

    def __str__(self):
        template_prefix = "[TEMPLATE] " if self.is_template else ""
        return f"{template_prefix}{self.name}"

    class Meta:
        verbose_name = "Console"
        verbose_name_plural = "Consoles"
        ordering = ['-is_template', 'name']
```

**Concrete excerpt — template-style audit + uniqueness** (`planner/models.py:3647-3665`):

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
```

**Deviations for new files:**
- Use `MultitrackSession` (NOT `Console`) and `MultitrackTrack` (NOT `ConsoleInput`).
- `MultitrackSession.console = ForeignKey('Console', on_delete=CASCADE)` per
  **D-13** — NOT `Device(category='console')`.
- `MultitrackTrack` does NOT have an FK to channel models per **D-01** — uses
  `source_type` (CharField choices) + `source_id` (PositiveIntegerField,
  nullable) discriminator instead. No FK = no CASCADE risk to beta data.
- Add the four resolver helpers per **D-14** as `@property` methods:
  `resolved_source`, `resolved_label`, `resolved_color`,
  `resolved_dante_number`. Map source_type → model via a module-level
  `SOURCE_TYPE_MODEL_MAP` dict (per RESEARCH § "Don't Hand-Roll").
- `unique_together = [('project', 'name')]` on `MultitrackSession` (mirrors
  `AudioChecklistTemplate`) — required for MTS-02 rename uniqueness error
  copy in UI-SPEC § "Error / Validation Strings".
- `Meta.ordering = ['track_number']` on `MultitrackTrack` per RESEARCH §
  "Track Order Modes Explained" (custom mode = stored order).
- Add DB index on `MultitrackTrack(source_type, source_id)` per CONTEXT D-04
  / RESEARCH § "Don't Hand-Roll" — speeds the orphan-conversion signal.
- **Append location:** insert after `ConsoleStereoOutput` ends at line 905 and
  before the orphan `Device` class at line 913 (per CONTEXT § Integration
  Points).

**⚠ Codebase quirk to be aware of (do NOT fix in Phase 1):**
`planner/models.py:781-782` defines `source = models.CharField(...)` twice —
harmless redefinition, flagged in RESEARCH but explicitly out of scope.

**Cross-refs:** D-01, D-02, D-03, D-13, D-14; UI-SPEC § "Editor" track-row
column order.

---

### `planner/migrations/00XX_multitrack_session_track.py`

**Role:** migration · **Data flow:** schema-create · **REQ:** MTS-01

**Analog:** Standard Django auto-generated migration from
`makemigrations planner` after appending the two model classes.

**Concrete pattern:** Run `python manage.py makemigrations planner` after the
model append; the generator emits exactly the right shape. Do NOT hand-write
this migration.

**Deviations / constraints (binding):**
- Migration MUST be additive only — two `migrations.CreateModel(...)` ops, no
  `migrations.AlterField`/`migrations.RemoveField` against the four existing
  channel models. (CLAUDE.md § Beta-safe migrations; CONTEXT.md § Code
  Context > Integration Points.)
- Verify before commit: the generated migration's `dependencies` references
  the latest `planner` migration only, not any auth/contenttype migrations
  beyond what stock Django emits.
- Add the `Index('source_type', 'source_id')` per CONTEXT.md § Claude's
  Discretion (last bullet) — declare it on `MultitrackTrack.Meta.indexes` and
  let `makemigrations` generate it.

**Cross-refs:** CLAUDE.md § "Do not run destructive SQL"; CONTEXT D-02.

---

### `planner/admin.py` append (`MultitrackSessionAdmin`)

**Role:** admin · **Data flow:** CRUD via Django admin · **REQ:** MTS-04 (edit metadata via admin change form)

**Primary analog:** `ConsoleAdmin` (`planner/admin.py:781-823`) — registered on
`showstack_admin_site` (line 5900), subclasses `BaseEquipmentAdmin`, exposes
role-based add/change/delete permission gates.

**Secondary analog:** `CommConfigAdmin` (`planner/admin.py:5932-5969`) —
"redirect-to-custom-page" pattern: admin URL bounces to the custom
`/audiopatch/...` page instead of rendering Django's generic changelist.
**This is the closer analog** for `MultitrackSessionAdmin` because the
multitrack module's primary UI lives at `/audiopatch/multitrack/`, not in the
Django admin.

**Concrete excerpt — `ConsoleAdmin` role-permission gates** (`planner/admin.py:781-823`):

```python
class ConsoleAdmin(BaseEquipmentAdmin):
    list_display = ['name', 'location', 'primary_ip_address', 'secondary_ip_address', 'is_template', 'export_buttons']
    list_filter = ['is_template', 'location']

    fieldsets = (
        ('Console Information', {
            'fields': ('name', 'location', 'primary_ip_address', 'secondary_ip_address', 'is_template')
        }),
    )

    inlines = [ConsoleInputInline, ConsoleAuxOutputInline, ConsoleMatrixOutputInline, ConsoleStereoOutputInline, DanteConsoleConfigInline]
    actions = ['export_yamaha_rivage_csvs',]

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
        ...
```

**Concrete excerpt — `CommConfigAdmin` redirect-to-custom-page pattern** (`planner/admin.py:5932-5969`):

```python
class CommConfigAdmin(admin.ModelAdmin):
    def has_module_perms(self, request):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff
    # has_add_permission, has_delete_permission identical

    def get_urls(self):
        from django.urls import path as urlpath
        urls = super().get_urls()
        custom_urls = [
            urlpath(
                'comm-config/',
                self.admin_site.admin_view(self.comm_config_redirect),
                name='planner_commconfig_redirect',
            ),
        ]
        return custom_urls + urls

    def comm_config_redirect(self, request):
        from django.shortcuts import redirect
        return redirect('planner:comm_config')

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        return redirect('planner:comm_config')

showstack_admin_site.register(CommConfig, CommConfigAdmin)
```

**Concrete excerpt — `BaseEquipmentAdmin.save_model` auto-project assignment**
(`planner/admin.py:98-111`) — applies automatically when subclassing:

```python
def save_model(self, request, obj, form, change):
    """Auto-assign current project to new equipment"""
    if not change:  # Only for new objects
        if hasattr(request, 'current_project') and request.current_project:
            from planner.models import Project
            try:
                if isinstance(request.current_project, Project):
                    obj.project = request.current_project
                else:
                    obj.project = Project.objects.get(id=request.current_project)
            except Project.DoesNotExist:
                pass
    super().save_model(request, obj, form, change)
```

**Registration line precedent (planner/admin.py:5900):**
```python
showstack_admin_site.register(Console, ConsoleAdmin)
```

**Deviations for new file:**
- Subclass `BaseEquipmentAdmin` (NOT plain `admin.ModelAdmin`) so the
  project auto-assignment, project-scoped queryset, and viewer-role gating
  come for free.
- Adopt the `CommConfigAdmin.changelist_view` redirect pattern — bounce
  `/admin/planner/multitracksession/` to `/audiopatch/multitrack/` so users
  always land in the custom UI.
- Register on `showstack_admin_site`, **not** `admin.site`. (CLAUDE.md
  non-negotiable; verified by `planner/admin.py:5900`.)
- `MultitrackTrackAdmin`: register only if Charlie wants direct access to the
  tracks table for debugging. The default Phase 1 design has tracks edited
  exclusively through the custom editor page, so a `MultitrackTrackAdmin` is
  optional. If registered, mark `has_module_permission` False so it doesn't
  show in the sidebar (precedent: `MicGroup` in `planner/admin_ordering.py:74`).

**Cross-refs:** CLAUDE.md § "Custom admin site"; PROJECT.md
non-negotiables; UI-SPEC § "Editor" → "Edit metadata" tertiary action.

---

### `planner/admin_ordering.py` (add `multitracksession` entry)

**Role:** config · **Data flow:** (n/a) · **REQ:** (sidebar grouping non-negotiable)

**Analog:** the existing `order_map` dict (`planner/admin_ordering.py:79-151`).

**Concrete excerpt** (`planner/admin_ordering.py:104-117`):

```python
# Communications (12-15)
'commbeltpack': 12,
'commconfig': 12.5,
'commposition': 13,
'commcrewname': 14,
'commchannel': 15,

# Show Mic Tracker (16-20)
'showday': 16,
'micsession': 17,
```

**Deviations:**
- Add `'multitracksession': 12.7` between `'commconfig': 12.5` and
  `'showday': 16` per RESEARCH § "Common Pitfalls > Pitfall 1" recommendation.
  Position is cosmetic — Charlie's call.
- If `MultitrackTrackAdmin` is registered, also add it to the `child_models`
  set at line 48-70 (so viewers don't see tracks in the sidebar) and to
  `always_hidden` at line 73-76 (so it's accessible only via direct URL —
  precedent: `'ampmodel'`, `'micgroup'`).

**Cross-refs:** CLAUDE.md § "Update `admin_ordering.py` whenever a new
admin-registered model is added"; RESEARCH § "Common Pitfalls > Pitfall 1".

---

### `planner/views.py` append (multiple view functions)

**Role:** view · **Data flow:** request-response (page render) + AJAX mutate
**REQ:** MTS-01..06, TRK-01..10, RPP-01..05

**Primary analog:** `comm_config_view` (`planner/views.py:1882-1980`) —
list-and-editor dual-mode pattern.

**Secondary analog:** `comm_config_create` (`planner/views.py:3754-3777`) —
AJAX mutate JSON-in / JSON-out POST endpoint.

**Tertiary analog:** `comm_config_update_lan` (`planner/views.py:5316-5329`) —
patch-style "update one field" endpoint (matches the JS swatch-picker save).

**Concrete excerpt — list-and-editor dual mode** (`planner/views.py:1881-1908`):

```python
@staff_member_required
def comm_config_view(request, config_id=None):
    """
    COMM Config module — list view and editor view.
    Mirrors the mic_tracker_view pattern.
    """
    current_project = getattr(request, 'current_project', None)

    # List of configs for this project
    configs = CommConfig.objects.filter(
        project=current_project
    ).order_by('created_at') if current_project else CommConfig.objects.none()

    config = None
    partylines = []
    # ... per-record state initialization ...

    if config_id:
        config = CommConfig.objects.filter(id=config_id, project=current_project).first()
        if not config:
            from django.shortcuts import redirect
            return redirect("planner:comm_config")
        partylines = config.partylines.all().order_by('channel_number')
        # ... load related rows ...
```

**Concrete excerpt — AJAX mutate** (`planner/views.py:3753-3777`):

```python
@require_POST
def comm_config_create(request):
    try:
        data = _json.loads(request.body)
        device_type = data.get('device_type', 'arcadia')
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        name = data.get('name', '').strip() or f"New {device_type.title()} Config"
        config = CommConfig.objects.create(
            project=current_project,
            name=name,
            device_type=device_type,
        )
        # Seed factory defaults
        if config.device_type == 'freespeak':
            _seed_freespeak_defaults(config)
        else:
            _seed_factory_defaults(config)
        return JsonResponse({'ok': True, 'config_id': config.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
```

**Concrete excerpt — single-field patch** (`planner/views.py:5316-5329`):

```python
@login_required
def comm_config_update_lan(request):
    import json
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    data = json.loads(request.body)
    from planner.models import CommConfigNetworkPort
    lan = CommConfigNetworkPort.objects.get(id=data['lan_id'])
    allowed = {'mode', 'static_ip', 'netmask', 'gateway', 'dns1', 'dns2',
               'traffic_type', 'ptp_follower_mode', 'dante_redundancy'}
    for field, value in data.items():
        if field in allowed:
            setattr(lan, field, value)
    lan.save()
    return JsonResponse({'ok': True})
```

**Mapping new view functions to analogs:**

| New view | Analog | Notes |
|----------|--------|-------|
| `multitrack_dashboard(request)` | `comm_config_view` (no `config_id`) | List sessions for current_project; render dashboard.html |
| `multitrack_editor(request, session_id)` | `comm_config_view` with `config_id` | Render editor.html + embed JSON for the picker |
| `multitrack_create_view(request)` | `comm_config_create` (full Django form, not AJAX) | UI-SPEC locks single Django form, NOT AJAX modal — render new_session.html on GET, validate + create + redirect on POST. Defensive `if not request.current_project: return redirect('/')` per RESEARCH § Pitfall 3. |
| `multitrack_duplicate(request, session_id)` | `comm_config_save_as_template` (`planner/views.py:5334`) | Iterates source tracks and copies them with new session FK |
| `multitrack_rename(request)` | `comm_config_update_lan` | Single-field patch — JSON in, JSON out |
| `multitrack_delete(request)` | `comm_config_delete` (search planner/views.py for it) | DELETE-by-POST; cascades to tracks via `MultitrackTrack.session = FK(CASCADE)` |
| `multitrack_reorder(request, session_id)` | `comm_config_update_lan` | POST `{ordered_ids: [...]}`; server reassigns dense `track_number = 1..N` via `bulk_update`; returns `{ok: true}` |
| `multitrack_add_tracks(request, session_id)` | `comm_config_create` | POST `{selections: [...], manuals: [...]}`; appends in D-10 order; returns `{ok, created_count, redirect_url}` |
| `multitrack_set_color(request)` | `comm_config_update_lan` | Single-field patch on `MultitrackTrack.color_override` |
| `multitrack_set_label(request)` | `comm_config_update_lan` | Single-field patch on `MultitrackTrack.label_override` |
| `multitrack_remove_track(request)` | `comm_config_delete` | One-click no-confirm delete |
| `multitrack_export_rpp(request, session_id)` | (see Reaper export section below) | File download |
| `multitrack_export_rtracktemplate(request, session_id)` | (see Reaper export section below) | File download |
| `multitrack_capacity_check(request, session_id)` | `comm_config_update_lan` | GET; returns `{count, capacity, over}` for editor's live capacity bar |

**Deviations for new file:**
- All views must defensively check `if not request.current_project:` per
  RESEARCH § "Common Pitfalls > Pitfall 3" and redirect to `/` (or `/dashboard/`).
- Combined `filter(id=session_id, project=request.current_project).first()` to
  prevent IDOR — never bare `.get(pk=session_id)`.
- Use `redirect("planner:multitrack_dashboard")` (not 404) when a session is
  missing from the current project — matches `comm_config_view`'s graceful
  degrade.
- All AJAX mutate endpoints decorated with `@require_POST` (precedent at
  `planner/views.py:3753`).
- All page-render views decorated with `@staff_member_required` (precedent at
  `planner/views.py:1881`).

**Cross-refs:** CONTEXT D-12; UI-SPEC § "Drag-Reorder Behavior";
RESEARCH § "Pattern 1" + "Pattern 2".

---

### `planner/urls.py` append

**Role:** route · **Data flow:** (n/a) · **REQ:** (URL contract for `/audiopatch/multitrack/...`)

**Analog:** the existing comm-config block (`planner/urls.py:60-95`).

**Concrete excerpt** (`planner/urls.py:60-78`):

```python
# COMM Config
path('comm-config/', views.comm_config_view, name='comm_config'),
path('comm-config/<int:config_id>/', views.comm_config_view, name='comm_config_editor'),
path('comm-config/create/', views.comm_config_create, name='comm_config_create'),
path('comm-config/partyline/update/', views.comm_config_update_partyline, name='comm_config_update_partyline'),
path('comm-config/partyline/add/', views.comm_config_add_partyline, name='comm_config_add_partyline'),
# ... ~30 endpoints follow the same naming pattern ...
path('comm-config/<int:config_id>/export-freespeak/', views.comm_config_export_freespeak, name='comm_config_export_freespeak'),
path('comm-config/template/save/', views.comm_config_save_as_template, name='comm_config_save_as_template'),
```

**Recommended new routes** (note: URLs map to project root because `audiopatch/urls.py` mounts `planner.urls` at `/audiopatch/`, so `multitrack/...` here becomes `/audiopatch/multitrack/...`):

```python
# Multitrack Sessions
path('multitrack/', views.multitrack_dashboard, name='multitrack_dashboard'),
path('multitrack/new/', views.multitrack_create_view, name='multitrack_create'),
path('multitrack/<int:session_id>/', views.multitrack_editor, name='multitrack_editor'),
path('multitrack/<int:session_id>/duplicate/', views.multitrack_duplicate, name='multitrack_duplicate'),
path('multitrack/<int:session_id>/rename/', views.multitrack_rename, name='multitrack_rename'),
path('multitrack/<int:session_id>/delete/', views.multitrack_delete, name='multitrack_delete'),
path('multitrack/<int:session_id>/reorder/', views.multitrack_reorder, name='multitrack_reorder'),
path('multitrack/<int:session_id>/add-tracks/', views.multitrack_add_tracks, name='multitrack_add_tracks'),
path('multitrack/<int:session_id>/capacity/', views.multitrack_capacity_check, name='multitrack_capacity_check'),
path('multitrack/track/set-color/', views.multitrack_set_color, name='multitrack_set_color'),
path('multitrack/track/set-label/', views.multitrack_set_label, name='multitrack_set_label'),
path('multitrack/track/remove/', views.multitrack_remove_track, name='multitrack_remove_track'),
path('multitrack/<int:session_id>/export.rpp/', views.multitrack_export_rpp, name='multitrack_export_rpp'),
path('multitrack/<int:session_id>/export.rtracktemplate/', views.multitrack_export_rtracktemplate, name='multitrack_export_rtracktemplate'),
```

**Deviations:**
- Insert the block grouped by visual cohesion (between the comm-config block
  and the dashboard/admin block). Match the `# Multitrack Sessions` header
  comment style used by every other module.
- URL namespace `planner:multitrack_*` — never include a project ID in the
  URL (CLAUDE.md non-negotiable: project comes from `CurrentProjectMiddleware`).

**Cross-refs:** CLAUDE.md § "Architecture > Session-based project resolution";
RESEARCH § "Anti-Patterns > URL-based project IDs".

---

### `planner/signals.py` append (`post_delete` receivers + helper)

**Role:** signal handler · **Data flow:** event-driven · **REQ:** D-04 orphan-to-manual conversion

**Analog:** `ensure_user_profile` `post_save` receiver (`planner/signals.py:8-27`).

**Concrete excerpt** (`planner/signals.py:1-27`):

```python
from django.db import IntegrityError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """
    Ensure UserProfile exists for every user.
    Uses try/except to handle race conditions when Django admin
    saves the User object multiple times during creation.
    """
    try:
        # Try to get existing profile
        profile = UserProfile.objects.get(user=instance)
    except UserProfile.DoesNotExist:
        # Profile doesn't exist, try to create it
        try:
            profile = UserProfile.objects.create(
                user=instance,
                account_type='free',
                can_create_projects=False
            )
        except IntegrityError:
            # Another signal fired first and created it - just fetch it
            profile = UserProfile.objects.get(user=instance)
```

**Pattern points to copy:**
- Single decorator `@receiver(<signal>, sender=<Model>)`.
- Module-level function (not nested).
- File is imported automatically — `planner/apps.py:13` already imports
  `planner.signals` from `ready()`. No registration step required.
- Idempotent body — handles repeated/race-condition fires.

**Concrete pattern (RESEARCH-prescribed) for D-04:**

```python
# planner/signals.py — append after existing receiver
from django.db.models.signals import post_delete

def _convert_orphans_to_manual(source_type, source_id, snapshot_label, snapshot_color=''):
    """D-04: Convert orphan MultitrackTracks to manual on channel deletion."""
    # Local import avoids circular import at module load
    from .models import MultitrackTrack
    orphans = MultitrackTrack.objects.filter(source_type=source_type, source_id=source_id)
    for track in orphans:
        track.label_override = track.label_override or snapshot_label
        track.color_override = track.color_override or snapshot_color
        track.source_type = 'manual'
        track.source_id = None
        track.save(update_fields=['label_override', 'color_override', 'source_type', 'source_id'])

@receiver(post_delete, sender=ConsoleInput)
def consoleinput_to_manual(sender, instance, **kwargs):
    label = instance.source or instance.input_ch or instance.dante_number or '(deleted input)'
    _convert_orphans_to_manual('input', instance.pk, label)

@receiver(post_delete, sender=ConsoleAuxOutput)
def consoleauxoutput_to_manual(sender, instance, **kwargs):
    label = instance.name or f'Aux {instance.aux_number}'
    _convert_orphans_to_manual('aux', instance.pk, label)

@receiver(post_delete, sender=ConsoleMatrixOutput)
def consolematrixoutput_to_manual(sender, instance, **kwargs):
    label = instance.name or f'Matrix {instance.matrix_number}'
    _convert_orphans_to_manual('matrix', instance.pk, label)

@receiver(post_delete, sender=ConsoleStereoOutput)
def consolestereooutput_to_manual(sender, instance, **kwargs):
    label = instance.name or instance.get_stereo_type_display()
    _convert_orphans_to_manual('stereo', instance.pk, label)
```

**Deviations from analog:**
- `post_delete` instead of `post_save`. Same `@receiver` shape; same module
  scope; same `sender, instance, **kwargs` signature.
- Use one helper function (`_convert_orphans_to_manual`) shared by all four
  receivers — DRY per RESEARCH § "Don't Hand-Roll" (one canonical source of
  the discriminator → snapshot logic).
- `try/except` not strictly needed for `post_delete` (no race condition on
  delete), but keeping the body short and bulk-update-style is the
  performance equivalent — see RESEARCH § Pitfall 7.
- Imports for the four channel models can be added to the existing top-of-file
  import block. **`MultitrackTrack` import must be local to the helper** to
  avoid circular import (signals → models → apps → signals).

**Cross-refs:** CONTEXT D-04, D-02; RESEARCH § "Pattern 4" + "Pitfall 7".

---

### `planner/forms.py` append (`MultitrackSessionForm`)

**Role:** form · **Data flow:** request-response · **REQ:** MTS-01

**Analog:** `ConsoleInputForm` (`planner/forms.py:50-105`) — establishes the
`forms.ModelForm` + `Meta.fields` + `__init__` widget-styling shape.

**Concrete excerpt** (`planner/forms.py:50-80`):

```python
class ConsoleInputForm(forms.ModelForm):
    class Meta:
        model = ConsoleInput
        fields = [
            'dante_number',
            'input_ch',
            'source',
            'source_hardware',
            'group',
            'dca',
            'mute',
            'direct_out',
            'omni_in',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['dante_number'].widget.attrs.update({
            'style': 'width: 40px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
        })
        self.fields['input_ch'].widget.attrs.update({
            'style': 'width: 100px; text-align: center;',
            'class': 'bg-white text-black rounded-sm',
        })
        # ... etc
```

**Deviations for new file:**
- `MultitrackSessionForm` is a `ModelForm` for `MultitrackSession` with fields
  matching UI-SPEC § "+ New Session" Flow:
  `name`, `console`, `target_daw`, `feed_source`, `track_order_mode`,
  `recorder_capacity`, `notes`.
- `console` queryset filtered to `request.current_project` — pass the request
  into `__init__(*args, request=None, **kwargs)` and override
  `self.fields['console'].queryset = Console.objects.filter(project=request.current_project)`.
- `target_daw`: use `forms.RadioSelect` widget with `choices` including a
  disabled `nuendo_live` option (per UI-SPEC § "+ New Session" Flow:
  "Nuendo Live (coming v2.0)").
- `clean_name`: validate uniqueness against
  `MultitrackSession.objects.filter(project=..., name=...).exclude(pk=...)`
  and raise `forms.ValidationError` with the exact UI-SPEC error string:
  `A session named "{name}" already exists in this project. Pick a different name.`

**Cross-refs:** UI-SPEC § "+ New Session" Flow; D-12; D-13.

---

### `planner/utils/reaper_export.py` (NEW)

**Role:** utility (export) · **Data flow:** file-I/O · **REQ:** RPP-01..05

**Analog:** `planner/utils/yamaha_export.py:1-30` — the file-download shape
(StringIO/BytesIO body + `HttpResponse` + `Content-Disposition: attachment`).

**Concrete excerpt** (`planner/utils/yamaha_export.py:1-30`):

```python
# planner/utils/yamaha_export.py
from io import StringIO, BytesIO
from django.http import HttpResponse
import zipfile


def export_yamaha_csvs(console):
    """Export all Yamaha Rivage CSV files"""
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr('InName.csv', generate_input_csv(console))
        zip_file.writestr('MixName.csv', generate_mix_csv(console))
        # ... 11 files total ...

    zip_buffer.seek(0)
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{console.name}_Yamaha_Rivage.zip"'
    return response


def generate_input_csv(console):
    """Generate InName.csv - 288 inputs"""
    output = StringIO()
    output.write('[Information]\n')
    output.write('CS-R3\n')
    # ...
    return output.getvalue()
```

**Deviations for new file** (full pattern in RESEARCH § "Code Examples"):

- The Reaper exporter does NOT bundle a zip — it returns a single `.RPP` (or
  `.RTrackTemplate`) text file. So drop `zipfile` and `BytesIO`; keep
  `StringIO` for body assembly.
- Two builders: `build_rpp(session) -> str` and
  `build_rtracktemplate(session) -> str`. Both consume an iterable of
  ordered enabled tracks; the `.RTrackTemplate` skips the
  `<REAPER_PROJECT ...>` wrapper.
- One helper: `hex_to_peakcol(hex_color: str) -> int` that returns
  `0x01000000 | (B<<16) | (G<<8) | R` for set colors and `16576` (Reaper's
  "no custom color" sentinel) for empty/None inputs.
- One helper: `_sanitize_name(name: str) -> str` that replaces `"` with `'`
  and trims (per RESEARCH § Pitfall 8).
- One helper: `_ordered_enabled_tracks(session) -> list[MultitrackTrack]`
  that reads `session.track_order_mode` and applies the dispatch table per
  RESEARCH § "Track Order Modes Explained".
- A module-level `YAMAHA_TO_HEX` constant per RESEARCH (lands in Phase 1 even
  though the conversion path activates in Phase 2 / Phase 5).
- Length budget: keep this as a single file. RESEARCH § "Alternatives
  Considered" justifies file vs submodule (yamaha_export.py is the precedent
  for single-file exporters; pdf_exports/ is the precedent for multi-file
  ones; Reaper exporter is small enough to be single-file).

**Companion view excerpt for download response** (RESEARCH § Code Examples):

```python
@staff_member_required
def multitrack_export_rpp(request, session_id):
    session = get_object_or_404(
        MultitrackSession,
        id=session_id,
        project=request.current_project,
    )
    body = build_rpp(session)
    response = HttpResponse(body, content_type='text/plain; charset=utf-8')
    safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in session.name)
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.RPP"'
    return response
```

**Cross-refs:** RESEARCH § "Reaper `.RPP` Format Facts", § "Pitfall 5/6/8",
§ "Don't Hand-Roll".

---

### `planner/templates/planner/multitrack/dashboard.html` (NEW)

**Role:** template · **Data flow:** server-rendered list page · **REQ:** MTS-03

**Analog:** `templates/planner/comm_config.html` (lines 1-130 for header/CSS,
lines 632-662 for the card grid + empty state, lines 564-628 for the new-config
dropdown).

**Concrete excerpt — extends + extrahead + base CSS** (`templates/planner/comm_config.html:1-15`):

```django
{% extends "admin/base_site.html" %}
{% load static %}
{% load custom_tags %}

{% block title %}COMM Config | ShowStack{% endblock %}

{% block extrahead %}
{{ block.super }}
<link rel="stylesheet" href="{% static 'admin/css/custom_admin.css' %}">
<style>
  /* ── Layout ── */
  .cc-container {
    padding: 20px;
    max-width: 1400px;
  }
  /* ── Header bar ── */
  .cc-header { ... }
  /* ── Buttons ── */
  .cc-btn { ... }
  .cc-btn-primary { background: #4a9eff; color: #fff; }
  .cc-btn-success { background: #28a745; color: #fff !important; }
  .cc-btn-danger  { background: #dc3545; color: #fff; }
  /* ── List view cards ── */
  .cc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; ... }
  .cc-card { background: #12122a; border: 1px solid #2a2a4a; border-radius: 10px; padding: 18px; cursor: pointer; ... }
  .cc-card:hover { border-color: #4a9eff; transform: translateY(-2px); }
  ...
</style>
```

**Concrete excerpt — card grid + empty state** (`templates/planner/comm_config.html:633-662`):

```django
{% if configs %}
<div class="cc-grid">
  {% for cfg in configs %}
  <a class="cc-card" href="{% url 'planner:comm_config_editor' cfg.id %}">
    <div class="cc-card-title">{{ cfg.name }}</div>
    <div class="cc-card-meta">Created {{ cfg.created_at|date:"M j, Y" }}</div>
    <div class="cc-card-stats">
      <div class="cc-stat">
        <span class="cc-stat-val">{{ cfg.partylines.count }}</span>
        <span class="cc-stat-label">Lines</span>
      </div>
      ...
    </div>
  </a>
  {% endfor %}
</div>
{% else %}
<div class="cc-empty-state">
  <div class="cc-empty-icon">📡</div>
  <p>No configurations yet for this project.</p>
  <p style="font-size:0.85rem">Click <strong>+ New Configuration</strong> to create your first Arcadia config.</p>
</div>
{% endif %}
```

**Deviations for new file:**
- Replace `cc-` prefix with `mts-` prefix everywhere (UI-SPEC § Design System).
- Move the inline `<style>` block out to `planner/static/planner/css/multitrack.css`
  for cleanliness — extend the dark token set defined in UI-SPEC § Color.
- Empty-state copy: use UI-SPEC § "Dashboard" empty-state strings verbatim:
  - heading `No sessions yet` (display 28px/600)
  - body `Create your first multitrack session...` (body 14px, max 480px)
  - CTA `+ New Session` (primary `#4a9eff`)
- Per-card meta line: `{N} tracks · {target_daw_label} · updated {time_ago}`
  per UI-SPEC § Dashboard.
- Per-card dropdown (Duplicate / Rename / Delete) — reuse the
  `cc-dropdown-menu` styling (`comm_config.html:130-162`) but rename to
  `mts-dropdown-menu`.
- CTA link: `{% url 'planner:multitrack_create' %}` for `+ New Session`
  (NOT a dropdown like comm_config — UI-SPEC says single primary button
  per § "Dashboard").

**Cross-refs:** UI-SPEC § "Dashboard"; D-12.

---

### `planner/templates/planner/multitrack/editor.html` (NEW)

**Role:** template · **Data flow:** server-rendered editor page · **REQ:** TRK-01..10, RPP-01..05, MTS-03..05

**Analog:** `templates/planner/comm_config.html:665-693` (editor header + tab
bar + back link).

**Concrete excerpt — editor header + back button** (`templates/planner/comm_config.html:667-684`):

```django
<div class="cc-editor-header">
  <a class="cc-back-btn" href="{% url 'planner:comm_config' %}">← All Configs</a>
  <h2 class="cc-editor-title">
    {{ config.name }}
    <span style="color:#5555aa;font-weight:400;font-size:1rem">/ {{ config.system_id|default:"—" }}</span>
  </h2>
  <div style="display:flex;gap:8px;">
    <a class="cc-btn cc-btn-secondary" href="/admin/planner/commcrewname/" target="_blank" style="text-decoration:none;">👥 Crew Names</a>
    <button class="cc-btn cc-btn-secondary" onclick="openSaveTemplateModal({{ config.id }})">💾 Save as Template</button>
    {% if config.device_type == 'freespeak' %}
    <button class="cc-btn cc-btn-success" onclick="window.location.href='{% url 'planner:comm_config_export_freespeak' config.id %}'">⬇ Export .cca</button>
    {% else %}
    <button class="cc-btn cc-btn-success" onclick="exportCca({{ config.id }})">⬇ Export .cca</button>
    {% endif %}
    <button class="cc-btn cc-btn-danger" onclick="deleteConfig({{ config.id }})">🗑 Delete</button>
  </div>
</div>
```

**Deviations for new file:**
- Replace `cc-editor-header` with `mts-editor-header`, etc.
- Header structure per UI-SPEC § "Editor":
  - back link `← Multitrack Sessions` → `{% url 'planner:multitrack_dashboard' %}`
  - h1: `{{ session.name }} — Multitrack Session` (browser tab uses same)
  - subtitle (caption #8888aa): `Console: {{ session.console.name }} · {{ session.get_target_daw_display }} · {{ session.get_feed_source_display }}`
  - "Edit metadata" tertiary plain link → `{% url 'planner:multitrack_create' %}` (re-use the form template) or a separate edit URL
- Toolbar buttons:
  - primary `Export to Reaper` (`#00ff88` success) → triggers download via
    `window.location.href = '{% url 'planner:multitrack_export_rpp' session.id %}'`
  - secondary `Export Track Template (.RTrackTemplate)` → same pattern with
    `multitrack_export_rtracktemplate`
- Capacity bar between header and track list: `<div class="mts-capacity">`
  with class modifiers `.mts-capacity--under | .mts-capacity--at | .mts-capacity--over`
  driven by server-side render of `{{ session.recorder_capacity }}` and
  `{{ session.tracks.count }}`.
- Track list section: `<div class="mts-track-list" data-session-id="{{ session.id }}">`
  with `{% for track in tracks %}{% include "planner/multitrack/_track_row.html" %}{% endfor %}`
- Below the list: include the picker modal partial:
  `{% include "planner/multitrack/_picker_modal.html" %}`
- Embed channel data as JSON for the picker (so it doesn't need an XHR on
  open):
  `<script id="mts-picker-data" type="application/json">{{ picker_data_json|safe }}</script>`
  matches the comm_config.html idiom of seeding JS state from the Django
  context.
- D-12 auto-open hook at end of body:
  `<script>if ({{ session.tracks.count }} === 0) openPicker('inputs');</script>`

**Cross-refs:** UI-SPEC § "Editor"; D-12; TRK-05.

---

### `planner/templates/planner/multitrack/new_session.html` (NEW)

**Role:** template · **Data flow:** form-render · **REQ:** MTS-01

**Analog:** No exact pre-existing analog for a single-form planner page (the
existing modules use modals for create). Closest match: the `cc-editor-header`
+ a single Django form wrapper. Use Django's standard `{{ form.as_p }}` for
the body shell, but wrap in the `mts-container` and `mts-header` from the
multitrack CSS file.

**Concrete pattern (composed from comm_config.html and Django defaults):**

```django
{% extends "admin/base_site.html" %}
{% load static %}
{% block title %}New Multitrack Session | ShowStack{% endblock %}
{% block extrahead %}
  {{ block.super }}
  <link rel="stylesheet" href="{% static 'planner/css/multitrack.css' %}">
{% endblock %}
{% block content %}
<div class="mts-container">
  <a class="mts-back-btn" href="{% url 'planner:multitrack_dashboard' %}">← Multitrack Sessions</a>
  <h1>New Multitrack Session</h1>
  <form method="post" class="mts-form">
    {% csrf_token %}
    {{ form.non_field_errors }}
    {% for field in form %}
      <div class="mts-form-row">
        <label for="{{ field.id_for_label }}">{{ field.label }}{% if field.field.required %} *{% endif %}</label>
        {{ field }}
        {% if field.help_text %}<p class="mts-help-text">{{ field.help_text }}</p>{% endif %}
        {{ field.errors }}
      </div>
    {% endfor %}
    <div class="mts-form-actions">
      <button type="submit" class="mts-btn mts-btn-primary">Create session</button>
      <a class="mts-btn mts-btn-secondary" href="{% url 'planner:multitrack_dashboard' %}">Cancel</a>
    </div>
  </form>
</div>
{% endblock %}
```

**Deviations:**
- Apply UI-SPEC § "+ New Session" Flow field order, labels, and required
  asterisks verbatim.
- The `target_daw` `nuendo_live` choice should render with caption
  `(coming v2.0)` and `disabled` attribute — use a custom widget render or
  template `{% if %}` block. Caption color `#8888aa`.
- On successful POST, redirect to
  `{% url 'planner:multitrack_editor' session.id %}` so the picker auto-opens
  per D-12.

**Cross-refs:** UI-SPEC § "+ New Session" Flow; D-12.

---

### `planner/templates/planner/multitrack/_picker_modal.html` (NEW partial)

**Role:** template (partial) · **Data flow:** server-rendered modal +
client-driven · **REQ:** TRK-06, TRK-07, TRK-09

**Analog:** `templates/admin/base_site.html:138-170` (the help-modal overlay),
explicitly cited by UI-SPEC § "Channel Picker Modal".

**Concrete excerpt** (`templates/admin/base_site.html:138-170`):

```html
<!-- Help Modal -->
<div id="help-overlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:99999;align-items:center;justify-content:center;">
  <div style="background:#1a1a1a;border:1px solid #333;border-radius:10px;width:780px;max-width:95vw;max-height:85vh;display:flex;flex-direction:column;overflow:hidden;">

    <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid #2e2e2e;">
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="color:#888;font-size:12px;">You are on:</span>
        <select id="help-module-select" onchange="helpSwitchModule(this.value)" ...>
          ...
        </select>
      </div>
      <button onclick="helpClose()" style="background:none;border:none;color:#888;font-size:18px;cursor:pointer;...">&#x2715;</button>
    </div>

    <div style="display:flex;flex:1;min-height:0;overflow:hidden;">
      <div id="help-fn-list" style="width:200px;flex-shrink:0;border-right:1px solid #2e2e2e;padding:10px 0;overflow-y:auto;background:#111;"></div>
      <div id="help-steps-pane" style="flex:1;padding:20px 24px;overflow-y:auto;background:#1a1a1a;"></div>
    </div>

  </div>
</div>
```

**Open / close pattern** (`templates/admin/base_site.html:534-547`):

```javascript
function helpOpen(){
  helpCurrentFn=0;
  document.getElementById('help-module-select').value=helpCurrentModule;
  document.getElementById('help-overlay').style.display='flex';
  helpRenderFnList();
  helpRenderSteps();
}
function helpClose(){document.getElementById('help-overlay').style.display='none';}

document.addEventListener('DOMContentLoaded',function(){
  document.getElementById('help-overlay').addEventListener('click',function(e){if(e.target===this)helpClose();});
  document.addEventListener('keydown',function(e){if(e.key==='Escape')helpClose();});
});
```

**Secondary analog (in-app modal style):** `templates/planner/comm_config.html:1747-1762` (Save Template Modal):

```html
<div id="saveTemplateModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:1000;align-items:center;justify-content:center;">
  <div style="background:#12122a;border:1px solid #3a3a5a;border-radius:12px;padding:28px;min-width:360px;max-width:440px;width:90%;">
    <h3 style="color:#e0e0e0;margin:0 0 20px;font-size:1.1rem;">⭐ Save as Template</h3>
    ...
    <div style="display:flex;gap:10px;justify-content:flex-end;">
      <button class="cc-btn cc-btn-secondary" onclick="document.getElementById('saveTemplateModal').style.display='none'">Cancel</button>
      <button class="cc-btn cc-btn-success" onclick="submitSaveTemplate()">Save Template</button>
    </div>
  </div>
</div>
```

**Deviations for new file:**
- ID: `mts-picker-overlay`. Panel width `720px` (UI-SPEC); panel height
  `max-height: 85vh`.
- Tab bar, filter input, per-tab body, footer commit/cancel — markup follows
  UI-SPEC § "Channel Picker Modal" ASCII layout VERBATIM.
- Five tabs (Inputs, Aux, Matrix, Stereo, Manual) with active-tab underline
  `border-bottom: 2px solid #4a9eff` (UI-SPEC color contract).
- Tab content rendered as a single `<div class="mts-tab-panel">` per tab; only
  one panel `display: block` at a time (analog: `comm_config.html` lines
  214-215).
- Manual tab body matches UI-SPEC § "Manual tab content" — repeating
  `mts-manual-row` cards with a `+ Add another` button.
- Escape key closes — copy the `helpClose` pattern from `base_site.html:546`.
- Backdrop click closes — copy `base_site.html:545`.

**Cross-refs:** UI-SPEC § "Channel Picker Modal"; D-07, D-08, D-09, D-10, D-11.

---

### `planner/templates/planner/multitrack/_track_row.html` (NEW partial)

**Role:** template (partial) · **Data flow:** server-rendered row · **REQ:** TRK-01..04, TRK-08

**Analog:** `templates/planner/comm_config.html:697-720` (cc-pl-card per-row).

**Concrete excerpt — partyline card per-row** (`templates/planner/comm_config.html:697-720`):

```django
{% for pl in partylines %}
<div class="cc-pl-card" data-pl-id="{{ pl.id }}">
  <div class="cc-pl-channel">CH {{ pl.channel_number }}</div>
  <div class="cc-pl-name">{{ pl.label }}</div>
  ...
</div>
{% endfor %}
```

**Deviations:**
- Phase 1 row layout per UI-SPEC § "Editor → Track-row column order"
  (drag handle → enable checkbox → track # → source-type badge →
  resolved label → swatch → notes pencil → remove button).
- `data-track-id="{{ track.id }}"` for Sortable.js (analog uses
  `data-pl-id`).
- Renders `track.resolved_label`, `track.resolved_color`,
  `track.get_source_type_display`, `track.track_number` — all sourced from
  the D-14 helpers on the model.
- `class="mts-track-row"` and `class="mts-drag"` on the handle (for
  Sortable.js `handle: '.mts-drag'`).
- Source-type badge: `<span class="mts-badge mts-badge--{{ track.source_type }}">{{ track.get_source_type_display|upper|truncate:6 }}</span>`
  with class-driven colors per UI-SPEC § "Track-source-type badge color
  coding".

**Cross-refs:** UI-SPEC § "Editor → Track-row column order"; TRK-04, TRK-08.

---

### `planner/templates/planner/multitrack/_color_picker.html` (NEW partial)

**Role:** template (partial) · **Data flow:** server-rendered popover ·
**REQ:** TRK-04

**Analog:** No exact pre-existing analog — vanilla popover. Closest CSS
references: the `cc-dropdown-menu` (`templates/planner/comm_config.html:130-162`)
for popover positioning + dark surface tokens.

**Concrete excerpt — dropdown menu styling** (`templates/planner/comm_config.html:130-162`):

```css
.cc-dropdown-menu {
  display: none;
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  background: #1e1e3a;
  border: 1px solid #3a3a5a;
  border-radius: 8px;
  min-width: 200px;
  z-index: 100;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.cc-dropdown-menu.open { display: block; }
.cc-dropdown-item {
  padding: 10px 16px;
  font-size: 0.85rem;
  color: #c0c0c0;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: background 0.15s;
}
.cc-dropdown-item:hover:not(.cc-dropdown-item--disabled) { background: #2a2a4a; }
```

**Deviations:**
- New shape: 6×2 grid of 20px swatches + custom-hex input + "Clear color"
  link, per UI-SPEC § "Inline Color Picker".
- 12-color palette from UI-SPEC verbatim (Red, Orange, Yellow, Green, Sky
  Blue, Blue, Purple, Pink, White, Grey, Brown, Black with their hex codes).
- Right-click on swatch clears `color_override = ''` — implement as
  `oncontextmenu="clearColorOverride(...)"` with `e.preventDefault()`.
- Use `el.style.setProperty('background-color', value, 'important')` per
  CLAUDE.md § "Coding Conventions" / RESEARCH § "Pitfall 4".

**Cross-refs:** UI-SPEC § "Inline Color Picker"; CLAUDE.md § "Overriding Django
admin CSS from JavaScript".

---

### `planner/templates/planner/multitrack/_session_card.html` (NEW partial)

**Role:** template (partial) · **Data flow:** server-rendered card · **REQ:** MTS-03

**Analog:** `templates/planner/comm_config.html:634-654` — the `cc-card` grid item.

(Full excerpt above in dashboard.html section.)

**Deviations:**
- Replace `cc-card-stats` content (which shows `partylines.count`/`roles.count`)
  with the UI-SPEC dashboard meta:
  `{N} tracks · {target_daw_label} · updated {time_ago}` rendered as a single
  `mts-card-meta` line.
- Add the per-card dropdown trigger (`[⋯]`) in the bottom-right per UI-SPEC
  dashboard layout — adapt the `cc-dropdown` pattern from
  `comm_config.html:128-162`.
- Dropdown items: `Duplicate` / `Rename` / `Delete` with the destructive
  Delete action triggering the confirmation modal copy from UI-SPEC §
  "Destructive Confirmations".

**Cross-refs:** UI-SPEC § "Dashboard"; MTS-03, MTS-05, MTS-06.

---

### `planner/static/planner/js/multitrack_editor.js` (NEW)

**Role:** JS · **Data flow:** client mutate + AJAX · **REQ:** TRK-04, TRK-05, TRK-06, TRK-08

**Primary analog:** Inline JS in `templates/planner/comm_config.html:1110-1280`
— jQuery-flavored module-init pattern with `fetch` + CSRF + modal open/close.

**Secondary analog:** `planner/static/planner/js/pa_cable_calculations.js:1-30`
— defensive jQuery wrapper.

**Concrete excerpt — fetch with CSRF + modal open/close** (`templates/planner/comm_config.html:1149-1212`):

```javascript
const CSRF = document.querySelector('[name=csrfmiddlewaretoken]').value;
// ... or for endpoints that use the cookie:
function saveLanField(lanId, field, value) {
  const payload = { lan_id: lanId };
  payload[field] = value;
  fetch('{% url "planner:comm_config_update_lan" %}', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
    body: JSON.stringify(payload),
  });
}

// Modal open/close
function openSaveTemplateModal(configId) {
  document.getElementById('saveTemplateConfigId').value = configId;
  document.getElementById('saveTemplateNameInput').value = '';
  document.getElementById('saveTemplateModal').style.display = 'flex';
  setTimeout(() => document.getElementById('saveTemplateNameInput').focus(), 100);
}
function submitSaveTemplate() {
  const name = document.getElementById('saveTemplateNameInput').value.trim();
  const configId = document.getElementById('saveTemplateConfigId').value;
  if (!name) { alert('Please enter a template name.'); return; }
  fetch('{% url "planner:comm_config_save_as_template" %}', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
    body: JSON.stringify({config_id: configId, template_name: name}),
  }).then(r => r.json()).then(data => {
    if (data.ok) {
      document.getElementById('saveTemplateModal').style.display = 'none';
      alert('Template "' + data.template_name + '" saved!');
    } else alert('Error: ' + (data.error || 'Unknown'));
  });
}
```

**Concrete excerpt — defensive jQuery wrapper** (`planner/static/planner/js/pa_cable_calculations.js:1-7`):

```javascript
// planner/static/planner/js/pa_cable_calculations.js

// Defensive jQuery loading
window.addEventListener('load', function() {
    (function($) {
        'use strict';
        ...
```

**Concrete excerpt — Sortable wiring (RESEARCH § Code Examples):**

```javascript
function initSortable() {
  const list = document.querySelector('.mts-track-list');
  if (!list) return;
  Sortable.create(list, {
    handle: '.mts-drag',
    animation: 150,
    onEnd: function(evt) {
      const ids = Array.from(list.querySelectorAll('[data-track-id]'))
                       .map(el => parseInt(el.dataset.trackId, 10));
      const sessionId = list.dataset.sessionId;
      fetch(`/audiopatch/multitrack/${sessionId}/reorder/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ ordered_ids: ids }),
      }).then(r => r.json()).then(data => {
        if (!data.ok) {
          showToast('Couldn\'t save track order. Check your connection and reload the page.', 'error');
        } else {
          list.querySelectorAll('.mts-track-num').forEach((el, idx) => {
            el.textContent = '#' + (idx + 1);
          });
        }
      });
    },
  });
}
document.addEventListener('DOMContentLoaded', initSortable);
```

**Deviations for new file:**
- Pull the inline `<script>` block out of the template into this dedicated
  static file. Reference via `<script src="{% static 'planner/js/multitrack_editor.js' %}" defer></script>`.
- Two CSRF idioms in this codebase — use either:
  1. `const CSRF = document.querySelector('[name=csrfmiddlewaretoken]').value;` (`comm_config.html:1113`), or
  2. `getCookie('csrftoken')` helper (`comm_config.html:1154`)

  **Recommendation:** Use the `[name=csrfmiddlewaretoken]` form because the
  editor template already includes a `{% csrf_token %}` for the session form;
  the cookie helper is not guaranteed to be available at template scope —
  RESEARCH § "Environment Availability" flagged this.
- All inline-style writes that override admin CSS MUST use
  `el.style.setProperty(prop, value, 'important')` per CLAUDE.md / RESEARCH
  Pitfall 4.
- All four DOM-mutation flows ship as named functions on `window` so the
  template can call them via `onclick="..."` (matches comm_config.html idiom):
  `openPicker()`, `closePicker()`, `commitPickerSelection()`, `addManualRow()`,
  `selectAllTab()`, `clearTab()`, `setTrackColor(trackId, hex)`, `clearTrackColor(trackId)`,
  `removeTrack(trackId)`, `renameSession(sessionId)`, `duplicateSession(sessionId)`,
  `deleteSession(sessionId)`.
- Drag-reorder uses Sortable.js `onEnd` only (NOT `onUpdate`) per RESEARCH §
  Pitfall 9.
- Sortable.js loaded BEFORE this file in the template:
  `<script src="{% static 'planner/js/vendor/Sortable.min.js' %}"></script>`
  (precedent: vendored libraries always before the consumer). Per UI-SPEC §
  "Registry Safety", do NOT use a CDN script tag.

**Cross-refs:** UI-SPEC § "Drag-Reorder Behavior", § "Channel Picker Modal";
RESEARCH § "Code Examples > Sortable.js wiring".

---

### `planner/static/planner/js/vendor/Sortable.min.js` (NEW vendored)

**Role:** JS (vendor) · **Data flow:** (n/a) · **REQ:** TRK-05

**Analog:** None — first vendored JS file in the repo. RESEARCH §
"Installation" provides the canonical bring-in command:

```bash
curl -L "https://registry.npmjs.org/sortablejs/-/sortablejs-1.15.7.tgz" -o /tmp/sortable.tgz
tar -xzf /tmp/sortable.tgz -C /tmp
cp /tmp/package/Sortable.min.js planner/static/planner/js/vendor/Sortable.min.js
git add planner/static/planner/js/vendor/Sortable.min.js
```

**Deviations:** N/A — pinned to 1.15.7 (MIT). UI-SPEC § "Registry Safety"
explicitly forbids a CDN script tag. Whitenoise serves the file at
`/static/planner/js/vendor/Sortable.min.js`.

**Cross-refs:** UI-SPEC § "Registry Safety"; RESEARCH § "Standard Stack > Core".

---

### `planner/static/planner/css/multitrack.css` (NEW — `mts-` prefix)

**Role:** CSS · **Data flow:** (n/a) · **REQ:** (UI-SPEC compliance)

**Analog:** Inline `<style>` block in `templates/planner/comm_config.html:10-560`
— a long monolithic stylesheet with `cc-` prefix, dark theme tokens.

**Concrete excerpt — color tokens** (`templates/planner/comm_config.html:38-67`):

```css
/* ── Buttons ── */
.cc-btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: background 0.2s, opacity 0.2s;
  display: inline-block;
  line-height: normal;
  box-sizing: border-box;
}
.cc-btn-primary { background: #4a9eff; color: #fff; }
.cc-btn-primary:hover { background: #3a8eef; }
.cc-btn-secondary { background: #2a2a4a; color: #c0c0c0; border: 1px solid #3a3a5a; }
.cc-btn-secondary:hover { background: #3a3a5a; }
.cc-btn-success { background: #28a745; color: #fff !important; }
.cc-btn-success:hover { background: #218838; }
.cc-btn-danger { background: #dc3545; color: #fff; }
.cc-btn-danger:hover { background: #c82333; }
.cc-btn-disabled { opacity: 0.4; cursor: not-allowed; }

/* ── List view cards ── */
.cc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  margin-top: 16px;
}
.cc-card {
  background: #12122a;
  border: 1px solid #2a2a4a;
  border-radius: 10px;
  padding: 18px;
  cursor: pointer;
  transition: border-color 0.2s, transform 0.1s;
}
.cc-card:hover {
  border-color: #4a9eff;
  transform: translateY(-2px);
}
```

**Deviations:**
- Move out to its own file (better than inline `<style>` for a module of this
  size).
- Replace `cc-` prefix with `mts-` prefix throughout.
- Use `#00ff88` (UI-SPEC success color) instead of `#28a745` for
  `mts-btn-success` — UI-SPEC explicitly locks `#00ff88` as the success
  color.
- Add the new component classes from UI-SPEC: `mts-track-row`,
  `mts-track-list`, `mts-drag`, `mts-badge`, `mts-badge--input`,
  `mts-badge--aux`, `mts-badge--matrix`, `mts-badge--stereo`,
  `mts-badge--manual`, `mts-capacity`, `mts-capacity__bar`,
  `mts-capacity--under|--at|--over`, `mts-pick-row`, `mts-tabs`, `mts-tab`,
  `mts-modal-overlay`, `mts-modal-panel`.
- Source colors / spacing tokens directly from UI-SPEC § Color and § Spacing
  Scale tables.

**Cross-refs:** UI-SPEC § Design System, § Color, § Spacing Scale, § Typography.

---

## Shared Patterns

### Authentication / Permission

**Source:** `BaseEquipmentAdmin` (`planner/admin.py:77-200`) and
`@staff_member_required` decorator (Django stdlib).

**Apply to:** All new admin classes (subclass `BaseEquipmentAdmin`); all new
view functions (decorate with `@staff_member_required` for page renders,
`@require_POST` for AJAX mutate endpoints).

**Concrete excerpt — staff_member_required + project defensive check** (`planner/views.py:1881-1893` + `planner/views.py:3758-3760`):

```python
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST

@staff_member_required
def comm_config_view(request, config_id=None):
    current_project = getattr(request, 'current_project', None)
    configs = CommConfig.objects.filter(
        project=current_project
    ).order_by('created_at') if current_project else CommConfig.objects.none()
    ...

@require_POST
def comm_config_create(request):
    try:
        data = _json.loads(request.body)
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)
        ...
```

**Concrete excerpt — BaseEquipmentAdmin save_model auto-assigns project** (`planner/admin.py:98-111`):

(See ConsoleAdmin section above for the full excerpt.)

---

### Project Scoping

**Source:** `CurrentProjectMiddleware` (`planner/middleware.py`) — already in
the middleware chain; no install step.

**Apply to:** Every new view, every new admin queryset, every new form.
Project comes from `request.current_project`, NEVER from a URL parameter
(CLAUDE.md non-negotiable).

**Concrete excerpt — middleware sets `request.current_project`** (`planner/middleware.py:20-21, 44-66`):

```python
def __call__(self, request):
    request.current_project = None

    if request.user.is_authenticated:
        is_superuser = request.user.is_superuser
        is_owner = Project.objects.filter(owner=request.user).exists()
        is_invited = ProjectMember.objects.filter(user=request.user).exists()

        if is_superuser or is_owner:
            project_id = request.session.get('current_project_id')
            if project_id:
                try:
                    project = Project.objects.get(id=project_id)
                    if is_superuser:
                        request.current_project = project
                    elif project.owner == request.user:
                        request.current_project = project
                    elif ProjectMember.objects.filter(user=request.user, project=project).exists():
                        request.current_project = project
                except Project.DoesNotExist:
                    pass
            ...
```

**Apply to all new views:**

```python
current_project = getattr(request, 'current_project', None)
if not current_project:
    return redirect('/')  # or return JsonResponse({'error': 'No active project'}, status=400)

session = MultitrackSession.objects.filter(
    id=session_id,
    project=current_project,  # always combined with the ID — IDOR prevention
).first()
if not session:
    return redirect('planner:multitrack_dashboard')
```

---

### Error Handling

**Source:** `comm_config_create` (`planner/views.py:3754-3777`) — try/except wrapping the entire body, returning `JsonResponse({'error': str(e)}, status=500)`.

**Apply to:** Every AJAX mutate view. Page-render views may let exceptions
propagate (Django's debug page handles them in dev; production uses standard
500 page).

**Concrete excerpt** (already shown in views.py section above).

**JS-side toast for failed AJAX** (UI-SPEC § "Toasts" + RESEARCH § "Code Examples"):

```javascript
.then(r => r.json()).then(data => {
  if (!data.ok) {
    showToast(data.error || 'Couldn\'t save. Check your connection and reload the page.', 'error');
  }
});
```

`showToast(message, level)` is a small helper to define in
`multitrack_editor.js`. Existing modules use bare `alert(...)` calls (see
`comm_config.html:1209` `alert('Template "..." saved!')`); UI-SPEC upgrades
this to passive toasts for the multitrack module — concrete styling in
UI-SPEC § "Toasts / Passive Confirmations".

---

### CSRF Handling

**Source:** Two idioms in the existing codebase, both in `comm_config.html`:

1. **Form-input CSRF token** (`templates/planner/comm_config.html:1113`):
   ```javascript
   const CSRF = document.querySelector('[name=csrfmiddlewaretoken]').value;
   // ...later...
   headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
   ```

2. **Cookie-based** (`templates/planner/comm_config.html:1154`):
   ```javascript
   headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
   ```

**Apply to:** All AJAX mutate calls. Use idiom #1 because the editor template
includes a `{% csrf_token %}` element (the session-create form lives on the
new_session.html page and the editor.html will need to embed a hidden
`{% csrf_token %}` for AJAX to grab the value from). The `getCookie` helper
is NOT defined globally in this project (RESEARCH § "Environment Availability"
flagged this) — define it locally in `multitrack_editor.js` if you choose
idiom #2.

---

### Validation

**Source:** Server-side in views (`comm_config_create:3756-3760`); form-level in
`forms.py` (`ConsoleInputForm`).

**Apply to:**
- Session name uniqueness — `MultitrackSessionForm.clean_name` raises
  `ValidationError` with the UI-SPEC § "Error / Validation Strings" string.
- Manual track label required — checked in `multitrack_add_tracks` view; emits
  `JsonResponse({'error': 'Label is required for manual tracks.'}, status=400)`
  with the UI-SPEC string verbatim.
- Manual track label length — `CharField(max_length=100)` enforces; the
  matching UI-SPEC error string fires only on form-bound submission.

---

### Static Asset Loading

**Source:** Whitenoise + `collectstatic` runs in `railway.json` on every
deploy (CLAUDE.md § "Tech Stack").

**Apply to:** New JS and CSS files. Reference via `{% load static %}` and
`{% static 'planner/js/...' %}` / `{% static 'planner/css/...' %}`.
**No CDN script tags for vendored JS.** (UI-SPEC § "Registry Safety" + RESEARCH § "Anti-Patterns".)

---

### Signal Registration

**Source:** `planner/apps.py:13` — `import planner.signals` from `ready()`.

**Apply to:** New signal receivers in `planner/signals.py` are
auto-registered. No code change needed in `apps.py`.

---

## No Analog Found

Every new file in Phase 1 has at least a partial-match analog. The single
borderline case:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `planner/templates/planner/multitrack/_color_picker.html` | template (partial) | server-rendered popover | No 12-color swatch palette popover exists in the codebase. Use the `cc-dropdown-menu` (`templates/planner/comm_config.html:130-162`) for surface tokens (`#1e1e3a` background, `#3a3a5a` border, 8px radius, `box-shadow: 0 8px 24px rgba(0,0,0,0.4)`); compose the swatch grid per UI-SPEC § "Inline Color Picker". |
| `planner/static/planner/js/vendor/Sortable.min.js` | JS (vendor) | n/a | First vendored third-party JS in the repo. Vendor per RESEARCH § "Installation". No pattern to copy — the file IS the dependency. |

---

## Key Cross-Cutting Insights

1. **The closest UX precedent for the entire module is the Comm Config module
   stack.** Same dark shell, same dual list/editor pattern, same modal idioms,
   same project scoping, same admin redirect-to-custom-page model. New files
   should mirror Comm Config's shape and replace `cc-` with `mts-`.

2. **Two complementary admin patterns are in play.** `BaseEquipmentAdmin`
   subclasses (e.g. `ConsoleAdmin`) use Django's standard changelist for
   simple equipment models. `CommConfigAdmin` uses
   `changelist_view → redirect` to bounce users to a custom `/audiopatch/...`
   page when the model is too rich for Django's auto-generated UI.
   `MultitrackSessionAdmin` should adopt the latter — but still subclass
   `BaseEquipmentAdmin` (NOT bare `admin.ModelAdmin` like `CommConfigAdmin`)
   so the project auto-assignment / role-permission gating come for free.

3. **Project scoping is non-URL.** `request.current_project` (set by
   `CurrentProjectMiddleware`) is the only correct source. Every
   project-scoped queryset uses
   `filter(id=session_id, project=request.current_project)` to combine
   IDOR-prevention and ownership-check in one filter — RESEARCH § Pattern 1.

4. **Signal idempotency idiom is a try/except, not a transaction.** Existing
   `ensure_user_profile` signal receiver uses two-level try/except for race
   conditions. New `post_delete` receivers don't have the race issue but
   should still use a shared helper (`_convert_orphans_to_manual`) to
   centralize the discriminator → snapshot logic — RESEARCH § "Don't Hand-Roll".

5. **The Reaper exporter pattern is `yamaha_export.py`, not `pdf_exports/`.**
   Single-file utility (StringIO body + HttpResponse + Content-Disposition)
   with the same shape that `export_yamaha_csvs` uses — the only differences
   are: no zip wrapping, body content type `text/plain`, file extension
   `.RPP` / `.RTrackTemplate`. The Yamaha→Reaper color table lands in
   `reaper_export.py` in Phase 1 even though Phase 2 / 5 activate it (per
   RESEARCH).

6. **CSS prefix discipline is binding.** The UI-SPEC requires `mts-` for
   every new class. Mirroring the `cc-` prefix means the codebase has a clean
   grep target for module-scoped styles, and there is zero risk of clobbering
   existing module CSS.

7. **`!important` everywhere.** Django admin's CSS uses `!important`
   pervasively. JS DOM mutations that change color/background MUST use
   `el.style.setProperty(prop, value, 'important')` — Pitfall 4 in RESEARCH.
   This applies to: track-row swatch updates, capacity bar fill changes,
   active-tab underline, drag-handle hover state.

---

## Metadata

**Analog search scope:**
- `planner/models.py` (lines 750-916, 3640-3700, 3700-3800)
- `planner/admin.py` (lines 1-200, 775-860, 5928-5970, 5900-5925)
- `planner/views.py` (lines 1875-1980, 3740-3810, 5310-5340)
- `planner/forms.py` (lines 1-110)
- `planner/signals.py` (entire file, 28 lines)
- `planner/middleware.py` (entire file, 95 lines)
- `planner/admin_site.py` (entire file, 210 lines)
- `planner/admin_ordering.py` (entire file, 173 lines)
- `planner/apps.py` (entire file, 14 lines)
- `planner/urls.py` (lines 1-100)
- `planner/utils/yamaha_export.py` (lines 1-80)
- `planner/utils/` directory listing (incl. pdf_exports/)
- `planner/static/planner/js/comm_admin.js` (entire file, 29 lines)
- `planner/static/planner/js/pa_cable_calculations.js` (lines 1-75)
- `templates/planner/comm_config.html` (lines 1-200, 625-720, 1110-1280, 1740-1775)
- `templates/admin/base_site.html` (lines 130-200, 530-555)

**Files scanned:** 16 directly read; ~10 grep'd for structural patterns.

**Pattern extraction date:** 2026-05-09

**Phase:** 01-core-sessions-track-editor-reaper-export
