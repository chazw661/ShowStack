---
phase: 07
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - planner/models.py
  - planner/migrations/0158_signalflowdiagram.py
  - planner/admin.py
  - planner/admin_ordering.py
autonomous: true
requirements:
  - DGM-02
  - DGM-03
  - DGM-04
user_setup: []

must_haves:
  truths:
    - "SignalFlowDiagram model exists in planner/models.py with project FK, name, canvas_state, viewport, version, created_at, updated_at fields"
    - "Migration 0158_signalflowdiagram.py creates the signalflowdiagram table with unique_together (project, name)"
    - "SignalFlowDiagramAdmin is registered on showstack_admin_site (NOT admin.site)"
    - "admin_ordering.py has both 'signalflowdiagram': 52 in order_map AND 'signalflowdiagram' in always_hidden set"
    - "python manage.py migrate succeeds locally; new table is present"
  artifacts:
    - path: "planner/models.py"
      provides: "SignalFlowDiagram model class with all 7 fields and Meta.unique_together"
      contains: "class SignalFlowDiagram(models.Model):"
    - path: "planner/migrations/0158_signalflowdiagram.py"
      provides: "CreateModel migration for SignalFlowDiagram"
      contains: "name='SignalFlowDiagram'"
    - path: "planner/admin.py"
      provides: "SignalFlowDiagramAdmin class registered on showstack_admin_site"
      contains: "class SignalFlowDiagramAdmin(BaseEquipmentAdmin):"
    - path: "planner/admin_ordering.py"
      provides: "order_map and always_hidden entries for signalflowdiagram"
      contains: "'signalflowdiagram': 52"
  key_links:
    - from: "planner/models.py SignalFlowDiagram"
      to: "planner.Project"
      via: "ForeignKey with on_delete=CASCADE related_name='signal_flow_diagrams'"
      pattern: "ForeignKey.*Project.*signal_flow_diagrams"
    - from: "planner/admin.py SignalFlowDiagramAdmin"
      to: "showstack_admin_site"
      via: "@admin.register(SignalFlowDiagram, site=showstack_admin_site)"
      pattern: "site=showstack_admin_site"
    - from: "planner/admin_ordering.py always_hidden set"
      to: "SignalFlowDiagram model name"
      via: "lowercase model name 'signalflowdiagram' added to set"
      pattern: "'signalflowdiagram'"
---

<objective>
Establish the Django foundation for the Signal Flow Diagrammer: the `SignalFlowDiagram` model with project scoping, the single additive migration, the admin registration on `showstack_admin_site`, and both required `admin_ordering.py` updates. This is the precondition for every other plan in Phase 7 — views/URLs (Plan 03) and templates (Plan 04) cannot exist without the model class.

Purpose: DGM-02/03/04 (create / rename / delete) require the model to exist with `unique_together=(project, name)` enforced at the DB layer. The `viewport` and `version` fields are added now (per locked decision in research) so Phases 8 and 9 do not require additional migrations.

Output: One new model class, one new migration file (0158), one new admin class, two targeted edits to `admin_ordering.py`. Local `migrate` runs clean; admin changelist at `/admin/planner/signalflowdiagram/` redirects to `/audiopatch/signal-flow/`.
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
<!-- Existing project model — referenced by SignalFlowDiagram.project FK -->
From planner/models.py (existing — DO NOT modify):
```python
class Project(models.Model):
    # ... existing fields ...
    # related_name 'signal_flow_diagrams' will be added via the new FK below
```

<!-- Existing admin infrastructure — reused, not modified -->
From planner/admin_site.py:
```python
showstack_admin_site  # custom AdminSite instance — register all planner models here
```

From planner/admin.py (existing base class — DO NOT modify):
```python
class BaseEquipmentAdmin(admin.ModelAdmin):
    # Role-based permission filtering for premium-owner / editor / viewer groups
```

<!-- Last migration in chain — new migration depends on this -->
From planner/migrations/:
```
0157_crew_crewmember_crewprojectadd.py  # <- new 0158 will depend on this
```

<!-- Existing admin_ordering structure — both edits go inside this file -->
From planner/admin_ordering.py:
```python
always_hidden = {
    'ampmodel', 'micgroup', 'monitorsession', 'discovereddevice',
    'pollresult', 'deviceevent', 'projectsnmpconfig',
    'switchportsnapshot', 'consoleimport',
    # NEW: 'signalflowdiagram' will be appended here
}

order_map = {
    # ... existing entries ...
    'multitracksession': 50,
    'multitracktemplate': 51,
    # NEW: 'signalflowdiagram': 52 will be appended here
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Add SignalFlowDiagram model + register admin (single commit)</name>
  <files>planner/models.py, planner/admin.py, planner/admin_ordering.py</files>
  <read_first>
    - .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md (sections: "planner/models.py — add SignalFlowDiagram class", "planner/admin.py — add SignalFlowDiagramAdmin", "planner/admin_ordering.py — two targeted edits")
    - planner/models.py — locate `class MultitrackTemplate(models.Model):` to identify the insertion point (append immediately after that class block)
    - planner/admin.py — read lines 5906-5942 to see `MultitrackSessionAdmin` analog and locate the imports block (top of file) where `SignalFlowDiagram` import must be added
    - planner/admin_ordering.py — read lines 73-91 (always_hidden set) and lines 168-171 (order_map tail) to find the exact insertion points
    - CLAUDE.md sections: "Custom admin site" (always register on showstack_admin_site), "Coding Conventions & Gotchas"
  </read_first>

  <behavior>
    - SignalFlowDiagram model is importable from planner.models with all 7 fields
    - Model has `unique_together = [('project', 'name')]` enforced at DB layer
    - SignalFlowDiagramAdmin is registered on showstack_admin_site (verifiable via `from planner.admin_site import showstack_admin_site; showstack_admin_site._registry` containing SignalFlowDiagram)
    - admin_ordering.py contains both `'signalflowdiagram': 52` in order_map AND `'signalflowdiagram'` in always_hidden set
    - Django system check (`python manage.py check`) passes with no errors
  </behavior>

  <action>
**Step A — Add SignalFlowDiagram class to planner/models.py:**

Open `planner/models.py`. Locate the `class MultitrackTemplate(models.Model):` block (use grep: `grep -n "class MultitrackTemplate" planner/models.py`). After the closing of that class block (after its `class Meta:` and any methods), append the following verbatim:

```python


class SignalFlowDiagram(models.Model):
    """Signal Flow Diagrammer canvas (v2.2). Single-blob persistence model.

    canvas_state stores the full JointJS `graph.toJSON()` output as a JSON blob.
    viewport stores pan/zoom state (Phase 8 wires this).
    version is the optimistic-locking token (Phase 9 wires this).
    """

    project = models.ForeignKey(
        'Project', on_delete=models.CASCADE, related_name='signal_flow_diagrams'
    )
    name = models.CharField(max_length=200)
    canvas_state = models.JSONField(default=dict, blank=True)
    viewport = models.JSONField(default=dict, blank=True)
    version = models.IntegerField(default=1)
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

Rationale per locked decisions (research SUMMARY.md item 3 and PITFALLS.md Pitfall 13):
- `viewport` and `version` are added in Phase 7 (not Phase 8/9) to keep migrations additive and minimize migration count.
- `max_length=200` on name (richer than multitrack's 100) per RESEARCH.md model definition.
- `default=dict` on JSONFields so existing-row insertions never see `null`.

**Step B — Add SignalFlowDiagramAdmin to planner/admin.py:**

1. Locate the imports block near the top of `planner/admin.py` (where other planner models are imported — grep for `from .models import` lines). Add to one of those import statements (or add a new line in the same block):

```python
from .models import SignalFlowDiagram
```

If `SignalFlowDiagram` is being added to an existing multi-import line, append it; if added on its own line, place it adjacent to `MultitrackSession` / `MultitrackTemplate` imports.

2. Locate the end of `MultitrackSessionAdmin` class block (around line 5942). After that class (and after any related `showstack_admin_site.register(...)` calls in the area), append the following verbatim:

```python


@admin.register(SignalFlowDiagram, site=showstack_admin_site)
class SignalFlowDiagramAdmin(BaseEquipmentAdmin):
    """Signal Flow Diagram admin — superuser inspection only.

    Changelist redirects to the user-facing list page at /audiopatch/signal-flow/.
    canvas_state is shown as a collapsible JSON display (read-only).
    Always hidden from the sidebar (see admin_ordering.py always_hidden).
    """

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

CRITICAL: The `@admin.register(SignalFlowDiagram, site=showstack_admin_site)` decorator MUST include `site=showstack_admin_site` — registering on `admin.site` is a CLAUDE.md violation. Note `changelist_view` redirects to `planner:signal_flow_list` (this URL name will be created in Plan 03; the import is lazy via Django URL resolver so it's safe to add the decorator now even before the URL exists).

**Step C — Update planner/admin_ordering.py with BOTH edits:**

1. Locate the `always_hidden = {` block (around lines 73-91). Inside the set, after the last existing entry (`'consoleimport',`), add:

```python
        # Signal Flow Diagrammer — editor lives at /audiopatch/signal-flow/;
        # admin changelist is for superuser inspection only, not end-user navigation.
        # Same pattern as multitracksession / multitracktemplate.
        'signalflowdiagram',
```

2. Locate the `order_map = {` dict tail (around lines 168-171). After the existing `'multitracktemplate': 51,` line, add:

```python
        'signalflowdiagram': 52,   # Phase 7 — Signal Flow Diagrammer (v2.2)
```

CRITICAL: Both edits are required in the same commit. CLAUDE.md: "admin_ordering.py must be updated with both order_map entry and always_hidden entry for every new admin-registered model." Missing either causes either a sidebar position 999 (if order_map missing) or unexpected sidebar entry (if always_hidden missing).

**Step D — Verify Django can import everything:**

Run `python manage.py check` from the project root. The output must contain `System check identified no issues (0 silenced).` If any error references SignalFlowDiagram, fix the offending file before continuing.
  </action>

  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch &amp;&amp; python manage.py check 2&gt;&amp;1 | grep -E "System check identified no issues|ERRORS"</automated>
  </verify>

  <acceptance_criteria>
    - `grep -c "class SignalFlowDiagram(models.Model):" planner/models.py` returns 1
    - `grep -c "related_name='signal_flow_diagrams'" planner/models.py` returns 1
    - `grep -c "unique_together = \[('project', 'name')\]" planner/models.py` returns at least 1 (the SignalFlowDiagram Meta)
    - `grep -c "viewport = models.JSONField" planner/models.py` returns 1
    - `grep -c "version = models.IntegerField(default=1)" planner/models.py` returns 1
    - `grep -c "class SignalFlowDiagramAdmin(BaseEquipmentAdmin):" planner/admin.py` returns 1
    - `grep -c "site=showstack_admin_site" planner/admin.py` returns at least 1 occurrence (and the SignalFlowDiagram decorator line MUST include this)
    - `grep -c "'signalflowdiagram': 52" planner/admin_ordering.py` returns 1
    - `grep -c "'signalflowdiagram'," planner/admin_ordering.py` returns 1 (the always_hidden entry)
    - `python manage.py check` exits 0 and prints `System check identified no issues (0 silenced).`
  </acceptance_criteria>

  <done>
    SignalFlowDiagram class is defined in planner/models.py with all 7 fields and Meta.unique_together. SignalFlowDiagramAdmin is in planner/admin.py with `@admin.register(SignalFlowDiagram, site=showstack_admin_site)`. admin_ordering.py contains both the order_map entry (`'signalflowdiagram': 52`) and the always_hidden entry. `python manage.py check` passes cleanly with no errors.
  </done>
</task>

<task type="auto" tdd="false">
  <name>Task 2: Generate migration 0158, run local migrate, verify table</name>
  <files>planner/migrations/0158_signalflowdiagram.py</files>
  <read_first>
    - .planning/phases/07-foundation-crud-editor-shell/07-PATTERNS.md (section: "planner/migrations/0158_signalflowdiagram.py")
    - planner/migrations/0157_crew_crewmember_crewprojectadd.py — reference for migration file header and CreateModel formatting
    - $HOME/.claude/projects/-Users-charlielawsonmacair-DjangoProjects-audiopatch/memory/MEMORY.md — MEMORY rule "Run local migrate after makemigrations" (apply new migrations to local SQLite before marking complete; CLAUDE.md's "ask first" rule is Railway-only)
    - CLAUDE.md section "When in Doubt" (ask before Railway destructive ops — local migrate is fine and required)
  </read_first>

  <behavior>
    - `python manage.py makemigrations planner` produces a file named `0158_signalflowdiagram.py` (or similar — Django auto-numbering) under `planner/migrations/`
    - The migration has `dependencies = [('planner', '0157_crew_crewmember_crewprojectadd')]`
    - The migration has exactly one `migrations.CreateModel` operation for `SignalFlowDiagram`
    - All 7 fields are present in the CreateModel: id, project, name, canvas_state, viewport, version, created_at, updated_at
    - The CreateModel options include `unique_together: {('project', 'name')}`
    - `python manage.py migrate` (local SQLite) succeeds
    - `python manage.py makemigrations --dry-run --check` exits 0 (no further changes detected after the new migration is in place)
  </behavior>

  <action>
**Step A — Generate the migration:**

From the project root run:

```bash
python manage.py makemigrations planner
```

Django will inspect the newly-added `SignalFlowDiagram` model and create a migration file. The expected filename is `planner/migrations/0158_signalflowdiagram.py` (Django auto-numbers and auto-names based on changes; the next number after `0157_crew_crewmember_crewprojectadd.py` is `0158`).

If Django chooses a different name (e.g. it bundles unrelated changes), STOP — investigate why. Only the SignalFlowDiagram CreateModel should be in this migration. If the file ends up named something other than `0158_signalflowdiagram.py`, rename it to `0158_signalflowdiagram.py` (and update its docstring / no other references need to change because dependencies are by tuple `('planner', '0158_signalflowdiagram')` not filename string at import time — but the convention is to keep filename matching the migration name).

**Step B — Inspect the generated file:**

Open the new file at `planner/migrations/0158_signalflowdiagram.py`. Verify it matches the expected shape:

```python
# Generated by Django 5.x on 2026-05-19  (header — exact text may differ)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planner', '0157_crew_crewmember_crewprojectadd'),
    ]

    operations = [
        migrations.CreateModel(
            name='SignalFlowDiagram',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('canvas_state', models.JSONField(blank=True, default=dict)),
                ('viewport', models.JSONField(blank=True, default=dict)),
                ('version', models.IntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('project', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='signal_flow_diagrams',
                    to='planner.project',
                )),
            ],
            options={
                'verbose_name': 'Signal Flow Diagram',
                'verbose_name_plural': 'Signal Flow Diagrams',
                'ordering': ['-updated_at', 'name'],
                'unique_together': {('project', 'name')},
            },
        ),
    ]
```

Field order or exact attribute ordering may differ slightly from Django's generator — that is acceptable. What MUST be true:
- `dependencies` includes `('planner', '0157_crew_crewmember_crewprojectadd')`
- Exactly one `migrations.CreateModel` operation for `SignalFlowDiagram`
- All 7 fields present (plus the auto-generated `id`)
- `unique_together={('project', 'name')}` in options
- `project` field uses `on_delete=django.db.models.deletion.CASCADE` and `related_name='signal_flow_diagrams'`

If the generated migration contains ANY other operations (modifications to existing tables, unrelated model changes), STOP — additive-migrations rule (CLAUDE.md) violated. Investigate which model edit triggered the unexpected operation and undo it before regenerating.

**Step C — Apply the migration locally:**

Per MEMORY.md rule (local migrate after makemigrations):

```bash
python manage.py migrate planner
```

Expected output includes a line like:
```
Applying planner.0158_signalflowdiagram... OK
```

This applies the migration to the local SQLite database. CLAUDE.md's "ask before destructive Railway ops" rule does NOT apply here — local migrations are safe and required.

**Step D — Verify no further changes detected:**

```bash
python manage.py makemigrations --dry-run --check planner
```

Expected output: `No changes detected in app 'planner'` and exit code 0. If exit code is non-zero, the model and migration are out of sync — investigate.

**Step E — Verify table creation via Django ORM:**

Quick smoke-test (single line in shell):

```bash
python manage.py shell -c "from planner.models import SignalFlowDiagram; print('Table OK; count=', SignalFlowDiagram.objects.count())"
```

Expected output: `Table OK; count= 0`. Any exception (especially `OperationalError: no such table: planner_signalflowdiagram`) means the migration did not apply.

**DO NOT** run `migrate` against Railway production from this task. The migration will be applied automatically when the next deploy hits Railway (via `railway.json` startCommand which runs `migrate`). The local migrate is required only for development verification.
  </action>

  <verify>
    <automated>cd /Users/charlielawsonmacair/DjangoProjects/audiopatch &amp;&amp; ls planner/migrations/0158_signalflowdiagram.py &amp;&amp; python manage.py makemigrations --dry-run --check planner 2&gt;&amp;1 | grep -E "No changes detected|Migrations for"</automated>
  </verify>

  <acceptance_criteria>
    - File `planner/migrations/0158_signalflowdiagram.py` exists
    - `grep -c "name='SignalFlowDiagram'" planner/migrations/0158_signalflowdiagram.py` returns 1
    - `grep -c "'planner', '0157_crew_crewmember_crewprojectadd'" planner/migrations/0158_signalflowdiagram.py` returns 1
    - `grep -c "unique_together" planner/migrations/0158_signalflowdiagram.py` returns 1
    - `grep -c "related_name='signal_flow_diagrams'" planner/migrations/0158_signalflowdiagram.py` returns 1
    - `python manage.py makemigrations --dry-run --check planner` exits 0 and outputs `No changes detected`
    - `python manage.py shell -c "from planner.models import SignalFlowDiagram; SignalFlowDiagram.objects.count()"` exits 0 (table exists locally)
  </acceptance_criteria>

  <done>
    Migration 0158_signalflowdiagram.py is present, depends on 0157, contains exactly one CreateModel for SignalFlowDiagram with all 7 fields and the unique_together constraint. Local SQLite migration applied successfully. `makemigrations --dry-run --check` reports no further changes. SignalFlowDiagram.objects.count() returns 0 without error.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client/admin → planner.models | Authenticated admin/staff user posts via Django admin or future AJAX; data crosses into ORM-managed storage |
| Django admin → SignalFlowDiagram changelist | Superuser/staff inspecting; sidebar visibility is the only access control surface here |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-01 | Tampering | SignalFlowDiagram.canvas_state JSONField (admin form) | mitigate | `exclude = ['canvas_state', 'viewport']` in SignalFlowDiagramAdmin prevents direct admin form edit; the canvas_state_display readonly method renders the JSON for inspection only. AJAX edit path (Phase 7 Plan 03 + Phase 9) is the only mutation route, gated by IDOR-safe `_get_diagram_for_request`. |
| T-07-02 | Elevation of Privilege | SignalFlowDiagramAdmin add/change/delete | mitigate | `has_add_permission`, `has_change_permission`, `has_delete_permission` overrides return False for users in the 'Viewer' group (matches MultitrackSessionAdmin pattern at planner/admin.py:5906). Superusers retain full access. |
| T-07-03 | Information Disclosure | SignalFlowDiagram in admin sidebar / changelist | mitigate | `always_hidden` set in admin_ordering.py contains 'signalflowdiagram' — sidebar entry is hidden from non-superusers per the multitracksession precedent. Changelist redirects via `changelist_view` to `planner:signal_flow_list` which Plan 03 will project-scope. |
| T-07-04 | Repudiation | SignalFlowDiagram row creation/modification audit | accept | Django admin LogEntry auto-captures admin actions; AJAX endpoint audit is out of scope for Phase 7 (no AJAX yet — those views land in Plan 03). The model carries `created_at` and `updated_at` timestamps for forensic baseline. |
| T-07-05 | Denial of Service | Migration on Railway Postgres | mitigate | Additive single-table migration (CreateModel only — no ALTER TABLE on existing tables). No data backfill. Per CLAUDE.md the migration runs automatically in `railway.json` startCommand on next deploy. Zero downtime expected for CREATE TABLE on a brand-new model. |

## Non-Security Compliance Note

The MPL-2.0 license compliance for `joint.min.js` is addressed in Plan 02, not here — this plan does not vendor any third-party files.
</threat_model>

<verification>
After both tasks complete, verify the full foundation:

```bash
cd /Users/charlielawsonmacair/DjangoProjects/audiopatch
python manage.py check                                          # exits 0
python manage.py makemigrations --dry-run --check planner       # "No changes detected"
python manage.py shell -c "from planner.models import SignalFlowDiagram; print(SignalFlowDiagram._meta.unique_together)"   # prints (('project', 'name'),)
python manage.py shell -c "from planner.admin_site import showstack_admin_site; from planner.models import SignalFlowDiagram; print(SignalFlowDiagram in showstack_admin_site._registry)"  # prints True
grep -c "'signalflowdiagram'" planner/admin_ordering.py         # returns 2 (always_hidden + order_map)
```
</verification>

<success_criteria>
- SignalFlowDiagram class exists in planner/models.py with project FK, name (max_length=200), canvas_state (JSONField default=dict), viewport (JSONField default=dict), version (IntegerField default=1), created_at, updated_at
- Meta.unique_together = [('project', 'name')] enforced
- Migration 0158_signalflowdiagram.py exists, depends on 0157, applies cleanly to local SQLite
- SignalFlowDiagramAdmin is registered on showstack_admin_site (NOT admin.site)
- Admin viewer-role guards (has_add/change/delete_permission) return False for Viewer group
- admin_ordering.py contains BOTH 'signalflowdiagram': 52 in order_map AND 'signalflowdiagram' in always_hidden
- `python manage.py check` passes
- `python manage.py makemigrations --dry-run --check planner` reports no changes
- No edits to existing tables (additive-only migration rule satisfied)
</success_criteria>

<output>
After completion, create `.planning/phases/07-foundation-crud-editor-shell/07-01-SUMMARY.md` documenting:
- Exact migration filename produced
- Verification of admin registration (registry inspection output)
- Confirmation both admin_ordering.py edits landed in same commit
- Local migrate result (timestamp / "Applying ... OK" line)
</output>
