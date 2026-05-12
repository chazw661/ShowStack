# Phase 2: Console CSV Import — Pattern Map

**Mapped:** 2026-05-12
**Files analyzed:** 11 (4 NEW + 7 MODIFIED)
**Analogs found:** 11 / 11

> Every file in Phase 2 has at least one strong existing analog. Phase 2
> introduces NO new architectural patterns — it composes existing primitives
> (TextIOWrapper + csv.reader from `import_comm_crew_names_csv`,
> draft-then-commit lifecycle from `Prediction`, FileField+JSONField from
> `Prediction`, `_multitrack_viewer_block` role gate from Phase 1, the
> `MultitrackSessionAdmin` "redirect-to-custom-page" admin pattern, and the
> `yamaha_export.py` per-section CSV shape in reverse) onto a new model and
> three views.

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `planner/utils/console_csv_import.py` (NEW) | utility (parser) | file-I/O / transform | `planner/utils/yamaha_export.py:1-65` (inverse direction; same section names + INI block) + `planner/views.py:3196-3268` (`import_comm_crew_names_csv`; csv.reader + TextIOWrapper) | exact (two complementary references) |
| `planner/migrations/0153_console_color_and_consoleimport.py` (NEW) | migration | schema-create | `planner/migrations/0152_multitrack_session_track.py` | exact (additive-only precedent, Phase 1) |
| `planner/templates/planner/multitrack/import_upload.html` (NEW) | template | form-render | `planner/templates/planner/multitrack/new_session.html:1-110` | exact (same module; same `mts-*` shell) |
| `planner/templates/planner/multitrack/import_preview.html` (NEW) | template | server-rendered table + form | `planner/templates/planner/multitrack/dashboard.html:11-43` (mts container + grid) + `planner/templates/planner/multitrack/new_session.html` (form actions + CSRF) | role-match (composite of two templates) |
| `planner/models.py` (APPEND `ConsoleImport`, `YAMAHA_COLOR_CHOICES`, AddField `color` × 4) | model | CRUD + immutable snapshot | `Prediction` (`planner/models.py:3280-3297`) for FileField+JSONField+timestamps shape; `MultitrackSession` (`planner/models.py:915-965`) for project-scoped FK + ordering | exact (two complementary analogs) |
| `planner/views.py` (APPEND `console_import_upload`, `console_import_preview`, `console_import_commit`) | view | request-response (multi-step draft-then-commit) | `import_comm_crew_names_csv` (`views.py:3196-3268`) for upload-decode-loop pattern; `multitrack_create_view` (`views.py:5979-5997`) for GET/POST form view; `multitrack_dashboard` (`views.py:5745-5762`) for project-scoped list | exact |
| `planner/urls.py` (APPEND 4 routes under `/audiopatch/multitrack/import/`) | route | (n/a) | `planner/urls.py:103-108` (existing `multitrack/*` block from Phase 1) | exact |
| `planner/templates/planner/multitrack/dashboard.html` (MODIFY: add Import button) | template | server-rendered | `planner/templates/planner/multitrack/dashboard.html:13-19` (existing header + primary CTA) | exact (modify in place) |
| `planner/admin.py` (APPEND `ConsoleImportAdmin`) | admin | CRUD via Django admin | `MultitrackSessionAdmin` (`planner/admin.py:5904-5939`) — Phase 1's "redirect-to-custom-page + role gates" admin | exact |
| `planner/admin_ordering.py` (add `'consoleimport': 51`) | config | (n/a) | `planner/admin_ordering.py:89-164` (existing `order_map` dict) | exact |
| `planner/forms.py` (APPEND `ConsoleCsvUploadForm`) | form | request-response | `P1ImportForm` (`planner/forms.py:789-810`) for `FileField` + `clean_config_file` shape; `MultitrackSessionForm` (`planner/forms.py:1130-1183`) for `request=` kwarg + project-scoped console queryset | exact (two analogs) |

---

## Pattern Assignments

### `planner/utils/console_csv_import.py` (NEW)

**Role:** utility · **Data flow:** file-I/O / transform · **REQ:** CSV-01, CSV-02, CSV-04

**Primary analog:** `planner/utils/yamaha_export.py:1-65` — the inverse direction. Same per-file-per-section CSV shape, same `[Information]` block, same column-order `KEY,NAME,COLOR,ICON,`, same `consoleinput_set` / `consoleauxoutput_set` traversal idiom. Phase 2 reads what this file writes.

**Secondary analog:** `planner/views.py:3196-3268` (`import_comm_crew_names_csv`) — the existing csv-decode-loop idiom. Use the same `TextIOWrapper` + `csv.reader` + per-row try/except shape, but additionally pass `newline=''` (RESEARCH Pitfall 4 — Yamaha files are CRLF).

**Section names + column shape (from `yamaha_export.py:33-65`):**

```python
# planner/utils/yamaha_export.py — INVERSE reference for Phase 2 parser
def generate_input_csv(console):
    output.write('[Information]\n')
    output.write('CS-R3\n')
    output.write('DSP-RX\n')
    output.write('V6.60\n')
    output.write('[InName]\n')
    output.write('IN,NAME,COLOR,ICON,\n')
    # ...
    for i in range(1, 289):
        input_num = f"_{i:03d}"
        if i in inputs_dict and inputs_dict[i].source:
            name = inputs_dict[i].source.replace(',', ';')
        else:
            name = f"ch{i}"
        output.write(f'{input_num},{name},Blue,Dynamic,\n')
```

**Decode + csv.reader pattern** (`views.py:3216-3250`):

```python
# planner/views.py — `import_comm_crew_names_csv` (the pattern to copy)
if request.method == 'POST' and request.FILES.get('csv_file'):
    csv_file = request.FILES['csv_file']
    try:
        file_data = TextIOWrapper(csv_file.file, encoding='utf-8')   # NOTE: parser must add newline=''
        csv_reader = csv.reader(file_data)
        imported = 0
        skipped = 0
        errors = []
        for row_num, row in enumerate(csv_reader, start=1):
            if not row or not row[0].strip():
                continue
            name = row[0].strip()
            try:
                CommCrewName.objects.get_or_create(name=name, project=project)
                imported += 1
            except Exception as e:
                errors.append(f"Row {row_num}: {name} - {str(e)}")
                skipped += 1
    except Exception as e:
        messages.error(request, f"Error reading CSV file: {str(e)}")
```

**Deviations for new file:**
- This module is a **pure-function utility** (no DB writes, no Django imports beyond stdlib). The view calls into it. Mirror `reaper_export.py` which is also a pure string-builder utility.
- Use `TextIOWrapper(uploaded_file.file, encoding='utf-8', newline='')` — the `newline=''` arg is non-negotiable because the Yamaha fixtures are CRLF (RESEARCH Pitfall 4). The `import_comm_crew_names_csv` analog omits it but should not have; do NOT copy the omission.
- Slice `row[:4]` to handle the trailing-comma → 5-element list issue (RESEARCH Pitfall 3); the `import_comm_crew_names_csv` analog only reads `row[0]` so it never hit this.
- Per-row errors go in a returned `errors` list (CSV-04 — no aborting). RESEARCH § "Per-Row Error Catalog" enumerates the error codes (`E_BAD_KEY`, `E_KEY_OUT_OF_RANGE`, `E_UNKNOWN_COLOR`, `E_COLUMN_COUNT`, etc.). Each entry: `{'code': str, 'line': int, 'detail': str}`.
- Family detection function `detect_family(lines) → 'cl_ql' | 'rivage_pm' | 'unknown'` — RESEARCH § "Console Family Detection Rule" provides the exact algorithm. R-02 amends D-03: confirmation gate only, no hard block.
- Default-row detector — RESEARCH § "Per-Section Default-Row Rules" + § "Code Examples > Default-row detector for inputs" — `f'ch{n:>2d}'` for `n < 100` else `f'ch{n}'`.
- Zip iterator — R-04 (CONTEXT amendment): accept `.csv` or `.zip`. Use `zipfile.is_zipfile(uploaded_file)` to detect; iterate every `.csv` member of the archive; merge results. All files in the zip must report the same `[Information]` family or it's a parse error.
- DCA-section / `[StName]`-return rows are recognised but skipped silently per R-01 and R-03 — record under `summary.errors` with informational reason strings (`'no_target_model_v2.0'`, `'stereo_group_b_not_supported_v2.0'`).

**Cross-refs:** RESEARCH § "Per-Section Parsing Spec", § "Per-Row Error Catalog", § "Code Examples"; CONTEXT R-02, R-03, R-04.

---

### `planner/migrations/0153_console_color_and_consoleimport.py` (NEW)

**Role:** migration · **Data flow:** schema-create · **REQ:** CSV-03 (storage); D-07, D-08

**Analog:** `planner/migrations/0152_multitrack_session_track.py` — the Phase 1 additive-migration precedent. Same shape: pure `CreateModel` + `AddField` ops, no `AlterField` / `RemoveField` against existing rows.

**Concrete excerpt** (`planner/migrations/0152_multitrack_session_track.py:7-56`):

```python
class Migration(migrations.Migration):
    dependencies = [
        ('planner', '0151_discovereddevice_clock_role_and_more'),
    ]
    operations = [
        migrations.CreateModel(
            name='MultitrackSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                # ...
                ('console', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='multitrack_sessions', to='planner.console')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='multitrack_sessions', to='planner.project')),
            ],
            options={
                'verbose_name': 'Multitrack Session',
                'verbose_name_plural': 'Multitrack Sessions',
                'ordering': ['-updated_at', 'name'],
                'unique_together': {('project', 'name')},
            },
        ),
        # ...
    ]
```

**Deviations for new file:**
- DO NOT hand-write — run `python manage.py makemigrations planner` after the model changes are in `planner/models.py`. The generator emits the right shape.
- Verify before commit: the generated migration's `dependencies` references `('planner', '0152_multitrack_session_track')` (the latest one), not any auth/contenttype beyond what stock Django emits.
- Expected operations:
  - `migrations.CreateModel(name='ConsoleImport', ...)` — one op.
  - `migrations.AddField(model_name='consoleinput', name='color', ...)` — one op.
  - `migrations.AddField(model_name='consoleauxoutput', name='color', ...)` — one op.
  - `migrations.AddField(model_name='consolematrixoutput', name='color', ...)` — one op.
  - `migrations.AddField(model_name='consolestereooutput', name='color', ...)` — one op.
  - Total: 5 ops, all additive. No `AlterField` / `RemoveField` against the four channel models. CLAUDE.md § "Do not run destructive SQL"; CONTEXT D-07 ("purely additive").

**Cross-refs:** CLAUDE.md § "When in Doubt"; CONTEXT D-07, D-08.

---

### `planner/templates/planner/multitrack/import_upload.html` (NEW)

**Role:** template · **Data flow:** form-render · **REQ:** D-05 (upload form)

**Analog:** `planner/templates/planner/multitrack/new_session.html` — same module, same `mts-*` CSS shell, same `{% extends 'admin/base_site.html' %}` + `extrahead` + `block content` shape. Add `enctype="multipart/form-data"` on the form (the only delta from new_session.html).

**Concrete excerpt** (`planner/templates/planner/multitrack/new_session.html:1-50`):

```django
{% extends "admin/base_site.html" %}
{% load static %}

{% block title %}{% if mode == 'edit' %}Edit Session{% else %}New Multitrack Session{% endif %} | ShowStack{% endblock %}

{% block extrahead %}
{{ block.super }}
<link rel="stylesheet" href="{% static 'planner/css/multitrack.css' %}">
{% endblock %}

{% block content %}
<div class="mts-container">
  <a class="mts-back-btn" href="{% url 'planner:multitrack_dashboard' %}">← Multitrack Sessions</a>

  <h1 class="mts-h1">
    {% if mode == 'edit' %}Edit session metadata{% else %}New Multitrack Session{% endif %}
  </h1>

  <form method="post" class="mts-form" novalidate>
    {% csrf_token %}

    {% if form.errors %}
      <div class="mts-form-errors">
        Could not save — please fix the highlighted fields.
        {% if form.non_field_errors %}{{ form.non_field_errors }}{% endif %}
      </div>
    {% endif %}

    <div class="mts-form-row">
      <label for="{{ form.name.id_for_label }}">Name <span class="mts-required">*</span></label>
      {{ form.name }}
      {% if form.name.errors %}<div class="mts-field-error">{{ form.name.errors }}</div>{% endif %}
    </div>

    <div class="mts-form-row">
      <label for="{{ form.console.id_for_label }}">Console <span class="mts-required">*</span></label>
      {{ form.console }}
      {% if form.console.errors %}<div class="mts-field-error">{{ form.console.errors }}</div>{% endif %}
    </div>
```

**Form-actions footer** (`new_session.html:100-106`):

```django
<div class="mts-form-actions">
  <button type="submit" class="mts-btn mts-btn-primary">
    {% if mode == 'edit' %}Save changes{% else %}Create session{% endif %}
  </button>
  <a class="mts-btn mts-btn-secondary"
     href="{% if mode == 'edit' %}{% url 'planner:multitrack_editor' session.id %}{% else %}{% url 'planner:multitrack_dashboard' %}{% endif %}">Cancel</a>
</div>
```

**Deviations for new file:**
- Add `enctype="multipart/form-data"` on the `<form>` element — required because this form has a `FileField`. (`new_session.html` doesn't have one, so doesn't need it.)
- The form has only two fields: target-console dropdown + file input. The dropdown is a `ModelChoiceField(queryset=Console.objects.filter(project=request.current_project))` — see analog at `MultitrackSessionForm.__init__` (`forms.py:1158-1165`). The file input accepts `.csv,.zip` via `widget=forms.FileInput(attrs={'accept': '.csv,.zip'})`.
- Submit button label: `"Upload"`.
- Cancel link → `{% url 'planner:multitrack_dashboard' %}`.
- No `mode` template variable needed — this is a single-mode form.

**Cross-refs:** D-05 (upload UI); RESEARCH § "Standard Stack" (`request.FILES['csv_file']`); R-04 (accept `.csv` or `.zip`).

---

### `planner/templates/planner/multitrack/import_preview.html` (NEW)

**Role:** template · **Data flow:** server-rendered table + commit form · **REQ:** CSV-03, D-04

**Primary analog:** `planner/templates/planner/multitrack/dashboard.html` for the page shell (`mts-container`, `mts-header`, `mts-h1`). **Secondary analog:** `planner/templates/planner/multitrack/new_session.html:19-27` for the `<form method="post" class="mts-form">{% csrf_token %}` shape that wraps the commit button + per-row conflict checkboxes.

**Concrete excerpt — page shell** (`dashboard.html:11-37`):

```django
{% block content %}
<div class="mts-container">
  <div class="mts-header">
    <div>
      <h1 class="mts-h1">Multitrack Sessions</h1>
      <p class="mts-subtitle">Build recording-session track lists from your console channels.</p>
    </div>
    <a class="mts-btn mts-btn-primary" href="{% url 'planner:multitrack_create' %}">+ New Session</a>
  </div>

  {% if sessions %}
    <div class="mts-grid">
      {% for session in sessions %}
        {% include "planner/multitrack/_session_card.html" with session=session %}
      {% endfor %}
    </div>
  {% else %}
    <div class="mts-empty-state">
      <h2 class="mts-empty-heading">No sessions yet</h2>
```

**Deviations for new file:**
- Page layout:
  1. Header: `mts-back-btn` (← Multitrack Sessions) + `<h1>Import preview — {{ import.original_filename }}</h1>`.
  2. Family-confirmation banner (R-02): *"This CSV is from a `{{ detected_family }}` console. The selected target is `{{ console.name }}`. Importing will create N new channels (console has M today)."*
  3. Stats summary strip (D-04): `Created · Updated · Conflicts · Unchanged · Errors` — five count chips. Each chip is `<span class="mts-chip mts-chip-created">{{ stats.created }} created</span>` etc.
  4. Filter chips: `[ Show unchanged ] [ Errors only ]` — client-side JS toggle on `<tr class="...">` visibility (no AJAX).
  5. Diff table: columns `Channel · Section · Old name · New name · Old color · New color · Status · Keep ShowStack`. The `Keep ShowStack` cell is a `<input type="checkbox" name="keep_showstack" value="{{ row.target_ref }}">` for conflict rows only; default unchecked = CSV wins (D-02).
  6. Errors panel (collapsible): one row per `summary.errors` entry — section name, row line number, code, detail.
  7. Footer form-actions: `<form method="post" action="{% url 'planner:console_import_commit' import.id %}">` wrapping the checkbox table + a `Commit import` primary button + `Cancel` secondary link → `/audiopatch/multitrack/`.
- The commit form must include `{% csrf_token %}` (analog: `new_session.html:20`).
- All numeric counts come from a precomputed `stats` dict on the view (CSV-03).
- Table rows are pre-filtered to non-`Unchanged` by default — the JS toggle only re-shows unchanged rows. Rivage exports are 288 rows; filter to ~25 changed rows so the page is usable.

**Cross-refs:** D-04 (stats + filter), D-02 (conflict checkboxes), CSV-03; R-02 (family confirmation banner copy).

---

### `planner/models.py` (APPEND `ConsoleImport`, `YAMAHA_COLOR_CHOICES`, AddField `color`)

**Role:** model · **Data flow:** CRUD + immutable snapshot · **REQ:** CSV-03, D-07, D-08

**Primary analog (for `ConsoleImport`):** `Prediction` (`planner/models.py:3280-3297`) — the existing FileField + JSONField + audit-timestamps model. Same shape: project-related FK, `FileField(upload_to=...)`, `JSONField(default=dict, blank=True)`, `created_at`/`updated_at`.

**Concrete excerpt — `Prediction` (FileField + JSONField shape)** (`planner/models.py:3280-3297`):

```python
class Prediction(models.Model):
    """Main prediction file from L'Acoustics Soundvision"""
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    show_day = models.ForeignKey('ShowDay', on_delete=models.CASCADE, related_name='predictions')
    file_name = models.CharField(max_length=255)
    version = models.CharField(max_length=50, blank=True)
    date_generated = models.DateField(null=True, blank=True)
    pdf_file = models.FileField(upload_to='predictions/', blank=True, null=True)
    raw_data = models.JSONField(default=dict, blank=True)  # Store parsed data
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Soundvision Prediction"
        verbose_name_plural = "Soundvision Predictions"
```

**Secondary analog (for project-scoped FK shape + ordering):** `MultitrackSession` (`planner/models.py:915-965`).

```python
class MultitrackSession(models.Model):
    project = models.ForeignKey(
        'Project', on_delete=models.CASCADE, related_name='multitrack_sessions'
    )
    console = models.ForeignKey(
        'Console', on_delete=models.CASCADE, related_name='multitrack_sessions'
    )
    name = models.CharField(max_length=100)
    # ... fields ...
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Multitrack Session"
        verbose_name_plural = "Multitrack Sessions"
        ordering = ['-updated_at', 'name']
        unique_together = [('project', 'name')]
```

**Deviations for new model `ConsoleImport`:**
- Fields per D-08:
  - `console = ForeignKey(Console, on_delete=CASCADE, related_name='imports')`
  - `uploaded_by = ForeignKey('auth.User', on_delete=SET_NULL, null=True, blank=True, related_name='console_imports')` — SET_NULL so a user delete doesn't cascade-wipe audit history.
  - `uploaded_at = DateTimeField(auto_now_add=True)`
  - `original_filename = CharField(max_length=255)` — mirrors `Prediction.file_name`.
  - `raw_file = FileField(upload_to=_import_upload_to, blank=True, null=True)` — `upload_to` is a **callable** (RESEARCH Pitfall 6): `def _import_upload_to(instance, filename): return f'console_imports/{instance.console.project_id}/{instance.console_id}/{timezone.now():%Y%m%dT%H%M%S}-{os.path.basename(filename)}'`. The `os.path.basename` guard is the path-traversal mitigation from RESEARCH § "Security Domain".
  - `parsed_sections = JSONField(default=dict, blank=True)` — list-shaped under `{'sections': [...]}` so the default-`dict` constructor works.
  - `summary = JSONField(default=dict, blank=True)` — keys: `created`, `updated`, `conflicts_resolved`, `unchanged`, `errors`.
  - `committed = BooleanField(default=False)`.
- `Meta.ordering = ['-uploaded_at']` — newest first.
- `Meta.verbose_name = 'Console Import'`, `verbose_name_plural = 'Console Imports'`.
- NO `unique_together` constraint — re-uploading the same file is supported (CONTEXT § Claude's Discretion).
- `__str__` returns `f"{self.console.name} — {self.original_filename} ({self.uploaded_at:%Y-%m-%d %H:%M})"`.

**Deviations for `YAMAHA_COLOR_CHOICES` + `AddField color`:**
- Place `YAMAHA_COLOR_CHOICES` constant near the top of `models.py` (above the `Console` class at line 754). Order matches `YAMAHA_TO_HEX` in `reaper_export.py:26-37`:
  ```python
  YAMAHA_COLOR_CHOICES = [
      ('Off',      'Off'),
      ('Red',      'Red'),
      ('Orange',   'Orange'),
      ('Yellow',   'Yellow'),
      ('Green',    'Green'),
      ('Sky Blue', 'Sky Blue'),
      ('Blue',     'Blue'),
      ('Purple',   'Purple'),
      ('Pink',     'Pink'),
      ('White',    'White'),
  ]
  ```
- Add `color = models.CharField(max_length=20, choices=YAMAHA_COLOR_CHOICES, default='Blue', blank=True)` to **each** of: `ConsoleInput` (line 777), `ConsoleAuxOutput` (line 846), `ConsoleMatrixOutput` (line 870), `ConsoleStereoOutput` (line 888). RESEARCH § "Migration Check" confirms none currently have it.
- Place the `ConsoleImport` class **after** `ConsoleStereoOutput` (line 905) and **before** the `# Multitrack Session Builder (Phase 1 of v2.0)` comment block at line 908. Keeps console-related models contiguous.
- **Field-name watchout (CONTEXT R-04 footnote):** `ConsoleInput`'s name field is `source` (not `name`). The migration adds `color` to the same model, no conflict — but the parser/apply step must write `source` for inputs and `name` for the three output models.

**⚠ Codebase quirk to be aware of (do NOT fix in Phase 2):**
`planner/models.py:781-782` defines `source = models.CharField(...)` twice — harmless redefinition, flagged in Phase 1 PATTERNS.md as out of scope; remains out of scope here.

**Cross-refs:** D-07, D-08; RESEARCH § "Migration Check"; CONTEXT R-04 (field-name watchout).

---

### `planner/views.py` (APPEND `console_import_upload`, `console_import_preview`, `console_import_commit`)

**Role:** view · **Data flow:** multi-step draft-then-commit · **REQ:** CSV-01..CSV-05, D-04, D-05, D-06, D-09

**Primary analog:** `import_comm_crew_names_csv` (`views.py:3196-3268`) for the upload-decode-loop pattern (already excerpted above under the parser pattern).

**Secondary analog:** `multitrack_create_view` (`views.py:5979-5997`) for the **`@staff_member_required` + GET-renders-form / POST-redirects-to-next-step** lifecycle. The CSV import is structurally identical to "new session": form → save → redirect to next page.

**Concrete excerpt — GET/POST form view + redirect** (`views.py:5979-5997`):

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

**Tertiary analog — role gate** (`views.py:6201-6211`):

```python
def _multitrack_viewer_block(request):
    """Return a JsonResponse 403 iff the user is in the 'Viewer' group; else None.
    Mirrors the read-only role contract enforced by BaseEquipmentAdmin and the
    `request.user.groups.filter(name='Viewer').exists()` pattern used throughout
    `planner/admin.py`. Centralised so every mutate endpoint applies the same
    check (CR-01 / CR-02).
    """
    if request.user.groups.filter(name='Viewer').exists():
        return JsonResponse({'error': 'Read-only access.'}, status=403)
    return None
```

**Quaternary analog — atomic commit + success-banner redirect** (RESEARCH § Code Examples; mirrors Phase 1's `multitrack_duplicate` `transaction.atomic()` usage):

```python
# RESEARCH § Code Examples > Atomic apply with conflict-override resolution
@login_required
@require_POST
def console_csv_commit(request, import_id):
    if request.user.groups.filter(name='Viewer').exists():
        return HttpResponseForbidden('Read-only.')
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return HttpResponseBadRequest('No project selected.')

    keep_showstack_ids = set(request.POST.getlist('keep_showstack'))

    with transaction.atomic():
        snap = ConsoleImport.objects.select_for_update().select_related('console').get(
            pk=import_id, console__project=current_project,
        )
        if snap.committed:
            return HttpResponseBadRequest('Already committed.')
        summary = _apply_console_import(snap, keep_showstack_ids)
        snap.summary = summary
        snap.committed = True
        snap.save()

    messages.success(
        request,
        f"Import complete — {summary['created'] + summary['updated']} channels imported.",
        extra_tags='multitrack_import',
    )
    return redirect('planner:multitrack_dashboard')
```

**Deviations for the three new views:**

- **`console_import_upload(request)`** — GET renders `import_upload.html` with `ConsoleCsvUploadForm(request=request)`. POST decodes the file (zip-or-csv detection), invokes `console_csv_import.parse_upload(...)`, creates a draft `ConsoleImport(committed=False)` row with the parsed payload + raw_file, redirects to `console_import_preview`. On parse error (E_NO_INFORMATION, E_UNKNOWN_FAMILY, E_NO_SECTION), `messages.error(request, "Could not parse — <reason>")` + re-render the upload form (no `ConsoleImport` row created).
- **`console_import_preview(request, import_id)`** — GET only. IDOR-safe fetch: `ConsoleImport.objects.filter(pk=import_id, console__project=request.current_project).first()`. **Recomputes the diff against current console state** on every GET (RESEARCH § "Diff Preview Architecture > Race Conditions" recommendation 1 — no drift detection in v2.0; recompute fresh). Renders `import_preview.html` with: `import` object, `stats` dict, `diff_rows` list, `errors` list, `detected_family`, `current_count`, `new_count`.
- **`console_import_commit(request, import_id)`** — POST only. Per the RESEARCH § Code Examples excerpt above. Wraps the apply step in `transaction.atomic()` + `select_for_update()` (double-commit guard, RESEARCH § "Diff Preview Architecture > Race Conditions" point 2). On success, `messages.success(extra_tags='multitrack_import')` + redirect to `planner:multitrack_dashboard` (D-06).

**Project + role + IDOR conventions (apply to all three views):**
- `current_project = getattr(request, 'current_project', None)` — Phase 1 / CLAUDE.md project-scoping idiom.
- Role gate: at the top of `console_import_upload` and `console_import_commit`, call `_multitrack_viewer_block(request)` (or the equivalent for non-JSON HTML views — return `HttpResponseForbidden`). D-09.
- IDOR: every `ConsoleImport` fetch filters on `console__project=current_project`. Mirrors `_get_track_for_request` at `views.py:6214-6228`.
- `@staff_member_required` on GET views; `@login_required` + `@require_POST` on POST views (matches Phase 1 view-by-view convention).

**Cross-refs:** D-04 (stats + filter), D-05 (upload UI), D-06 (post-commit landing), D-09 (role gate); CSV-01..05; R-02 (family confirmation banner copy in preview view's context).

---

### `planner/urls.py` (APPEND 4 routes under `/audiopatch/multitrack/import/`)

**Role:** route · **Data flow:** (n/a) · **REQ:** D-05 (entry under `/audiopatch/multitrack/`)

**Analog:** the existing `multitrack/*` block from Phase 1 (`planner/urls.py:103-125`).

**Concrete excerpt** (`planner/urls.py:103-125`):

```python
# Page-render
path('multitrack/', views.multitrack_dashboard, name='multitrack_dashboard'),
path('multitrack/new/', views.multitrack_create_view, name='multitrack_create'),
path('multitrack/<int:session_id>/', views.multitrack_editor, name='multitrack_editor'),
path('multitrack/<int:session_id>/edit/', views.multitrack_edit_view, name='multitrack_edit'),

# AJAX mutate (this plan)
path('multitrack/<int:session_id>/duplicate/', views.multitrack_duplicate, name='multitrack_duplicate'),
# ...

# File downloads (Plan 04)
path('multitrack/<int:session_id>/export.rpp/', views.multitrack_export_rpp, name='multitrack_export_rpp'),
```

**Deviations for new routes:**
- Add **3** new path entries (the orchestrator brief says 4 but the actual route count is 3 — the upload view handles both GET form-render and POST upload at the same URL, mirroring `multitrack_create_view`):
  - `path('multitrack/import/', views.console_import_upload, name='console_import_upload')` — both GET and POST.
  - `path('multitrack/import/<int:import_id>/preview/', views.console_import_preview, name='console_import_preview')` — GET only.
  - `path('multitrack/import/<int:import_id>/commit/', views.console_import_commit, name='console_import_commit')` — POST only.
- Place the new block immediately after the existing `multitrack/<int:session_id>/edit/` line (`urls.py:107`) and before the `# AJAX mutate (this plan)` comment. Keeps page-render routes contiguous.
- URL names use the `console_import_*` prefix to avoid colliding with `multitrack_*` names. The template uses them as `{% url 'planner:console_import_preview' import.id %}`.

**Cross-refs:** D-05.

---

### `planner/templates/planner/multitrack/dashboard.html` (MODIFY: add Import button)

**Role:** template · **Data flow:** server-rendered · **REQ:** D-05

**Analog:** the existing header block in the same file (`dashboard.html:13-19`).

**Concrete excerpt** (`dashboard.html:13-19`):

```django
<div class="mts-header">
  <div>
    <h1 class="mts-h1">Multitrack Sessions</h1>
    <p class="mts-subtitle">Build recording-session track lists from your console channels.</p>
  </div>
  <a class="mts-btn mts-btn-primary" href="{% url 'planner:multitrack_create' %}">+ New Session</a>
</div>
```

**Deviations for the modification:**
- Add a second CTA inside `mts-header`, adjacent to `+ New Session`. Use a wrapper `<div class="mts-header-actions">` (or inline two `<a>` elements) so they sit side by side.
- New link: `<a class="mts-btn mts-btn-secondary" href="{% url 'planner:console_import_upload' %}">Import Console CSV</a>`.
- Use the `mts-btn-secondary` class (NOT `mts-btn-primary`) so visual hierarchy keeps "+ New Session" as the primary action.
- Banner rendering for D-06 success message: ensure `dashboard.html` renders Django's `messages` framework. RESEARCH § "Standard Stack" notes `extra_tags='multitrack_import'`. If the template doesn't already loop `messages`, add `{% if messages %}{% for message in messages %}<div class="mts-banner mts-banner-{{ message.tags }}">{{ message }}</div>{% endfor %}{% endif %}` near the top of `mts-container`, **above** the header.

**Cross-refs:** D-05, D-06.

---

### `planner/admin.py` (APPEND `ConsoleImportAdmin`)

**Role:** admin · **Data flow:** CRUD via Django admin · **REQ:** (audit access; CLAUDE.md non-negotiable)

**Analog:** `MultitrackSessionAdmin` (`planner/admin.py:5904-5939`) — the Phase 1 "redirect-to-custom-page + role-gates + `BaseEquipmentAdmin` subclass" admin.

**Concrete excerpt** (`planner/admin.py:5904-5939`):

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
        # ... identical shape ...

    def has_delete_permission(self, request, obj=None):
        # ... identical shape ...
```

**Registration line precedent** (`planner/admin.py:5946-5947`):

```python
showstack_admin_site.register(Console, ConsoleAdmin)
showstack_admin_site.register(MultitrackSession, MultitrackSessionAdmin)
```

**Deviations for new `ConsoleImportAdmin`:**
- Subclass `BaseEquipmentAdmin` (NOT plain `admin.ModelAdmin`) — gets project auto-assignment + viewer-role gating + project-scoped queryset for free.
- `list_display = ['console', 'original_filename', 'uploaded_by', 'uploaded_at', 'committed']`.
- `list_filter = ['committed', 'console']`.
- `search_fields = ['original_filename', 'console__name']`.
- `readonly_fields = ['raw_file', 'parsed_sections', 'summary', 'uploaded_by', 'uploaded_at', 'committed']` — `ConsoleImport` rows are immutable audit history (CONTEXT § Decisions: *"the import record stays as audit history and re-apply source"*). Admin is read-mostly.
- **DO NOT** add a `changelist_view` redirect to the custom UI — there is no custom list page for imports in v2.0; the admin changelist IS the audit-history view. This is the **one** deviation from the `MultitrackSessionAdmin` analog.
- Role gates (`has_add_permission`, `has_change_permission`, `has_delete_permission`): copy verbatim from `MultitrackSessionAdmin:5920-5939` (viewer → False; superuser → True; else super).
- Register on `showstack_admin_site` (CLAUDE.md non-negotiable; verified at `admin.py:5946`). Line goes near the bottom of `admin.py` alongside the other registrations, e.g.:
  ```python
  showstack_admin_site.register(ConsoleImport, ConsoleImportAdmin)
  ```
  Place it adjacent to `showstack_admin_site.register(MultitrackSession, MultitrackSessionAdmin)` (`admin.py:5947`).

**Cross-refs:** CLAUDE.md § "Custom admin site"; D-09 (role gates).

---

### `planner/admin_ordering.py` (add `'consoleimport': 51`)

**Role:** config · **Data flow:** (n/a) · **REQ:** (sidebar grouping non-negotiable per CLAUDE.md)

**Analog:** the existing `order_map` dict (`planner/admin_ordering.py:89-164`).

**Concrete excerpt** (`planner/admin_ordering.py:162-164`):

```python
# Multitrack Session Builder (50 — bottom of sidebar)
'multitracksession': 50,
```

**Deviations:**
- Add a single line to the `order_map` dict:
  ```python
  # Multitrack Session Builder (50 — bottom of sidebar)
  'multitracksession': 50,
  'consoleimport': 51,
  ```
- Position is cosmetic — `51` slots `ConsoleImport` immediately after `MultitrackSession`, keeping the v2.0 cluster contiguous at the bottom of the sidebar.
- Do **NOT** add `'consoleimport'` to `child_models` (line 48-70) — `ConsoleImport` is its own admin-visible model, not a child of any equipment model.
- Do **NOT** add it to `always_hidden` (line 73-86) — Charlie/owners should be able to browse import history from the admin sidebar.

**Cross-refs:** CLAUDE.md § "Update `admin_ordering.py` whenever a new admin-registered model is added".

---

### `planner/forms.py` (APPEND `ConsoleCsvUploadForm`)

**Role:** form · **Data flow:** request-response · **REQ:** D-05, R-04

**Primary analog (for `FileField` + extension + size validation):** `P1ImportForm` (`planner/forms.py:789-810`).

**Concrete excerpt** (`planner/forms.py:789-810`):

```python
class P1ImportForm(forms.Form):
    """Form for importing P1 configuration from L'Acoustics Network Manager"""
    config_file = forms.FileField(
        label="P1 Configuration File",
        help_text="Upload an exported P1 configuration file from L'Acoustics Network Manager (optional)",
        required=False,
        widget=forms.FileInput(attrs={'accept': '.xml,.json,.p1,.txt'})
    )

    def clean_config_file(self):
        file = self.cleaned_data.get('config_file')

        if file:
            # Validate file type
            if not file.name.endswith(('.xml', '.json', '.p1', '.txt')):
                raise forms.ValidationError("Invalid file format. Please upload a P1 configuration file.")

            # Check file size (limit to 10MB)
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError("File too large. Maximum size is 10MB.")

        return file
```

**Secondary analog (for `request=` kwarg + project-scoped queryset):** `MultitrackSessionForm` (`planner/forms.py:1130-1183`).

**Concrete excerpt** (`planner/forms.py:1155-1165`):

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

**Deviations for new form:**
- This is a `forms.Form` (NOT a `ModelForm`) — the upload form maps to two views (upload page + draft `ConsoleImport`), and `ConsoleImport.console` is the only "form-level" field; the file is handled separately.
- Two fields:
  - `console = forms.ModelChoiceField(queryset=Console.objects.none(), label='Target console', required=True)` — initial queryset set in `__init__` via the `request=` kwarg per the `MultitrackSessionForm` analog.
  - `csv_file = forms.FileField(label='CSV or zip', required=True, widget=forms.FileInput(attrs={'accept': '.csv,.zip'}))` — per R-04, accept both.
- `clean_csv_file` method (modeled on `P1ImportForm.clean_config_file:798-810`):
  - Reject if not ending in `.csv` or `.zip` (case-insensitive).
  - Reject if `file.size > 5 * 1024 * 1024` (5 MB) — RESEARCH § "Security Domain" zip-bomb mitigation: legitimate Editor exports are well under 300 KB.
- Keep the `request=` kwarg pattern from `MultitrackSessionForm.__init__` (`forms.py:1155-1156`) so the upload view passes `request` and the form scopes the console queryset.

**Cross-refs:** D-05; R-04 (accept `.csv` and `.zip`); RESEARCH § "Security Domain".

---

## Shared Patterns

Cross-cutting patterns that apply to multiple Phase 2 files.

### Authentication / role-gate

**Source:** `planner/views.py:6201-6211` (`_multitrack_viewer_block`).
**Apply to:** `console_import_upload`, `console_import_commit` (both mutate). `console_import_preview` is read-only; standard `@staff_member_required` suffices.

```python
def _multitrack_viewer_block(request):
    if request.user.groups.filter(name='Viewer').exists():
        return JsonResponse({'error': 'Read-only access.'}, status=403)
    return None
```

For the HTML upload view (non-JSON), return `HttpResponseForbidden('Read-only.')` instead of the JSON 403 — keeps the page response simple. Pattern source: same module, `views.py:6726` (`HttpResponseForbidden`).

Phase 2 may either (a) reuse `_multitrack_viewer_block` for the commit endpoint (it returns JSON, but the commit view can render that fine; the commit POST is form-submitted from the preview page, so a JSON 403 is acceptable as long as the form handles non-OK responses), or (b) add a small `_console_import_viewer_block` returning `HttpResponseForbidden`. Planner picks; b is slightly cleaner.

### IDOR / project-scoping

**Source:** `planner/views.py:5777-5780` (assert pattern in `_build_picker_data`) and `views.py:6214-6228` (`_get_track_for_request` filter-by-project).
**Apply to:** All `ConsoleImport.objects.*` fetches in the three new views.

```python
return (
    MultitrackTrack.objects
    .filter(id=track_id, session__project=current_project)
    .select_related('session')
    .first()
)
```

For `ConsoleImport`, mirror the pattern:

```python
snap = (
    ConsoleImport.objects
    .filter(pk=import_id, console__project=current_project)
    .select_related('console')
    .first()
)
```

### Error handling — per-row in CSV parser

**Source:** `planner/views.py:3228-3249` (`import_comm_crew_names_csv` per-row try/except).
**Apply to:** `console_csv_import.parse_section_file()` row loop, and the `_apply_console_import()` row loop in the commit view.

```python
for row_num, row in enumerate(csv_reader, start=1):
    if not row or not row[0].strip():
        continue
    # ... per-row work ...
    try:
        # ... DB / parse op ...
    except Exception as e:
        errors.append(f"Row {row_num}: {name} - {str(e)}")
        skipped += 1
```

For Phase 2, structured errors go in `summary.errors` as `{'code': '...', 'line': N, 'detail': '...'}` dicts (RESEARCH § "Per-Row Error Catalog"). Whole-import never aborts on a single bad row (CSV-04 / D-04).

### Atomic batch apply

**Source:** RESEARCH § Code Examples > Atomic apply; pattern verified at `views.py:6091` (`MultitrackTrack.objects.bulk_create`) and across the codebase wherever `transaction.atomic()` is used.
**Apply to:** `console_import_commit` view.

```python
with transaction.atomic():
    snap = ConsoleImport.objects.select_for_update().select_related('console').get(
        pk=import_id, console__project=current_project,
    )
    if snap.committed:
        return HttpResponseBadRequest('Already committed.')
    summary = _apply_console_import(snap, keep_showstack_ids)
    snap.summary = summary
    snap.committed = True
    snap.save()
```

`select_for_update()` is the double-commit guard (RESEARCH § "Diff Preview Architecture > Race Conditions").

### `messages` framework banner with extra_tags

**Source:** `planner/views.py:3258-3265` and RESEARCH § "Standard Stack".
**Apply to:** `console_import_commit` success path; `console_import_upload` parse-error path.

```python
messages.success(
    request,
    f"Import complete — {summary['created'] + summary['updated']} channels imported.",
    extra_tags='multitrack_import',
)
return redirect('planner:multitrack_dashboard')
```

The `extra_tags='multitrack_import'` lets `dashboard.html` distinguish import banners from other module banners.

### `BaseEquipmentAdmin` + `showstack_admin_site` + role gates

**Source:** `planner/admin.py:5904-5939` (`MultitrackSessionAdmin`) + `admin.py:5946-5947` (registration block).
**Apply to:** `ConsoleImportAdmin` registration.

Already excerpted in the `planner/admin.py` section above. Key non-negotiables:
- Subclass `BaseEquipmentAdmin`, not `admin.ModelAdmin`.
- Register on `showstack_admin_site`, never `admin.site` (CLAUDE.md).
- All three of `has_add_permission` / `has_change_permission` / `has_delete_permission` reject Viewer + permit Superuser.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | — | — | Every Phase 2 file has a strong existing analog. |

Phase 2 introduces zero new architectural patterns. It composes:
- the existing CSV-import idiom (`TextIOWrapper` + `csv.reader` from `import_comm_crew_names_csv`),
- the existing FileField + JSONField + audit-timestamps shape (`Prediction`),
- the existing project-scoped FK + ordering shape (`MultitrackSession`),
- the existing additive-migration precedent (`0152_multitrack_session_track`),
- the existing role-gate helper (`_multitrack_viewer_block`),
- the existing `mts-*` template shell (Phase 1 multitrack templates),
- the existing `BaseEquipmentAdmin` + `showstack_admin_site` + "redirect-to-custom-page" admin pattern (`MultitrackSessionAdmin`, `CommConfigAdmin`),
- the existing `order_map` config (`admin_ordering.py`),
- the existing `messages.<level>(... extra_tags='...')` banner convention,
- the inverse of the existing Yamaha CSV exporter (`yamaha_export.py`),
- the existing `YAMAHA_TO_HEX` palette (`reaper_export.py:26-37`).

## Metadata

**Analog search scope:**
- `planner/utils/` (yamaha_export.py, reaper_export.py)
- `planner/views.py` (import_comm_crew_names_csv at 3196; multitrack_* at 5740..6699)
- `planner/models.py` (ConsoleInput/Aux/Mtx/Stereo at 777..905; Prediction at 3280; MultitrackSession/Track at 915..)
- `planner/admin.py` (MultitrackSessionAdmin at 5904; registration block at 5946)
- `planner/admin_ordering.py` (order_map at 89..164)
- `planner/forms.py` (P1ImportForm at 789; MultitrackSessionForm at 1130)
- `planner/templates/planner/multitrack/*.html` (Phase 1 dashboard + new_session)
- `planner/migrations/0152_multitrack_session_track.py`

**Files scanned:** ~12 source files + 7 multitrack templates + 1 migration.

**Pattern extraction date:** 2026-05-12.

---

## PATTERN MAPPING COMPLETE

**Phase:** 02 — Console CSV Import
**Files classified:** 11
**Analogs found:** 11 / 11

### Coverage
- Files with exact analog: 11
- Files with role-match analog: 0
- Files with no analog: 0

### Key Patterns Identified
- Parser composes the **inverse of `yamaha_export.py`** (same section names, `[Information]` block, `KEY,NAME,COLOR,ICON,` columns) plus the **`TextIOWrapper(file.file, encoding='utf-8', newline='')` + `csv.reader` per-row try/except** idiom from `import_comm_crew_names_csv` (`views.py:3196-3268`).
- `ConsoleImport` mirrors **`Prediction`** (`models.py:3280-3297`) for `FileField(upload_to=callable) + JSONField + created_at` shape, and mirrors **`MultitrackSession`** (`models.py:915-965`) for project-scoped FK + ordering.
- Three views follow the **Phase 1 `multitrack_create_view` + `_multitrack_viewer_block` + `transaction.atomic() + select_for_update()`** lifecycle, with the post-commit `messages.success(..., extra_tags='multitrack_import')` + redirect-to-dashboard convention.
- Admin uses the **`MultitrackSessionAdmin` + `BaseEquipmentAdmin` + `showstack_admin_site`** pattern (CLAUDE.md non-negotiable), with `readonly_fields` on every field because `ConsoleImport` is immutable audit history.
- Migration follows the **`0152_multitrack_session_track` additive-only** precedent — one `CreateModel` + four `AddField` ops, no `AlterField` against beta-tester rows.

### File Created
`/Users/charlielawsonmacair/DjangoProjects/audiopatch/.planning/phases/02-console-csv-import/02-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files. Every Phase 2 file has a verified, line-number-anchored existing analog in the codebase.
