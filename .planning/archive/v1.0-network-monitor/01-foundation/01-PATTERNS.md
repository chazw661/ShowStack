# Phase 1: Foundation - Pattern Map

**Mapped:** 2026-04-22
**Files analyzed:** 7 new/modified files
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `planner/models.py` (add 4 new models) | model | CRUD | `planner/models.py` — `PowerDistributionPlan` + `AmplifierAssignment` | exact |
| `planner/management/commands/run_monitor.py` | utility (management command) | event-driven / daemon | `planner/management/commands/setup_user_groups.py` (structure) + RESEARCH.md Pattern 2 | role-match |
| `planner/views_monitor.py` (new separate file) | controller | request-response + streaming | `planner/views_dante.py` (separate views module) + `planner/views.py` — `comm_config_view`, `power_distribution_calculator` | exact |
| `planner/urls.py` (add new paths) | config | request-response | `planner/urls.py` — existing comm-config and power-distribution blocks | exact |
| `templates/planner/network_monitor.html` | component | request-response | `templates/planner/mic_tracker.html` | exact |
| `planner/admin_ordering.py` (update order_map) | config | — | `planner/admin_ordering.py` — existing order_map | exact |
| `planner/admin.py` (register new models) | config | — | `planner/admin.py` lines 5899–5920 (showstack_admin_site.register block) | exact |

---

## Pattern Assignments

### `planner/models.py` — add MonitorSession, DiscoveredDevice, PollResult, DeviceEvent

**Analog:** `planner/models.py` — `PowerDistributionPlan` (lines 2939–3000), `Project` FK pattern (lines 20–46), `GenericIPAddressField` usages (lines 762, 927, 1099, 1347, 2142, 3880)

**Imports pattern** (lines 1–16 of models.py — already present, no new imports needed):
```python
from django.db import models
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
import uuid
```
All four new models use only types already imported. Append them at the end of the file, after the last existing model.

**Project FK pattern** (lines 2941, 2980–2983 — PowerDistributionPlan):
```python
class PowerDistributionPlan(models.Model):
    project = models.ForeignKey('Project', on_delete=models.CASCADE)
    ...
    class Meta:
        ordering = ['-created_at']
    def __str__(self):
        return f"{self.venue_name} Power Plan" if self.venue_name else f"Power Plan {self.pk}"
```
Copy this exact FK declaration form for `MonitorSession.project`, `DiscoveredDevice.project`, etc. Use string `'Project'` (not imported class) to avoid circular import issues — consistent with every other FK to Project in this file.

**GenericIPAddressField pattern** (line 1099):
```python
ip_address = models.GenericIPAddressField(blank=True, null=True)
```
For `DiscoveredDevice.ip_address`, use `models.GenericIPAddressField()` — NOT blank/null since an IP is required for a discovered device. This is the field type mandated by CLAUDE.md §8 and used across all existing module models.

**choices + default pattern** (lines 2945–2952 — PowerDistributionPlan.SERVICE_TYPES):
```python
SERVICE_TYPES = [
    ('3phase_4wire_208', '3-Phase 4-Wire 208V'),
    ...
]
service_type = models.CharField(max_length=50, choices=SERVICE_TYPES, default='3phase_4wire_208')
```
Copy this inline-choices pattern for `DiscoveredDevice.DOMAIN_CHOICES` and `STATE_CHOICES`.

**JSONField usage** — `DeviceEvent.details = models.JSONField(default=dict)` is consistent with existing JSON usage in this codebase. Django 5.x ships JSONField for PostgreSQL; no extra package needed.

**Index pattern** — `PollResult` and `DeviceEvent` require explicit indexes. Use:
```python
class Meta:
    indexes = [
        models.Index(fields=['device', 'polled_at']),
    ]
```
This pattern is not yet used in models.py (existing models rely on implicit PK indexes) but is the correct Django ORM syntax — no analog needed, use as specified in RESEARCH.md.

---

### `planner/management/commands/run_monitor.py` (new file)

**Analog:** `planner/management/commands/setup_user_groups.py` (command class structure, lines 1–97)

**Command class skeleton** (lines 1–14 of setup_user_groups.py):
```python
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = 'Creates Editor and Viewer permission groups for ShowStack'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up user groups...'))
```
Copy this exact skeleton. `run_monitor` differs in that it adds `add_arguments` and spawns a daemon thread — but the import, class name, `help`, and `self.stdout.write(self.style.SUCCESS(...))` patterns are identical.

**stdout patterns** (lines 20–28 of setup_user_groups.py):
```python
self.stdout.write(self.style.SUCCESS('✓ Created Editor group'))
self.stdout.write('  Editor group already exists')
self.stdout.write(self.style.WARNING(f'  Model not found: {model_name}'))
```
Use `self.style.SUCCESS` for normal status, `self.style.WARNING` for non-fatal issues, bare `self.stdout.write` for informational lines.

**No `add_arguments` analog in existing commands** — all 7 existing commands are one-shot with no arguments. The `add_arguments` pattern for `--project-id` and `--interval` comes directly from RESEARCH.md Pattern 2 (verified against Django 5.x docs). Use it verbatim.

**Daemon thread + stop_event pattern** — no existing analog. Use RESEARCH.md Pattern 2 exactly:
```python
import threading
stop_event = threading.Event()
t = threading.Thread(target=icmp_poller, daemon=True, name='ICMPPoller')
t.start()
try:
    stop_event.wait()
except KeyboardInterrupt:
    self.stdout.write('\nShutting down...')
    stop_event.set()
```

**Critical: `close_old_connections()` at top of every poll iteration** — no existing analog. Must be the first line inside the `while not stop_event.is_set():` loop:
```python
from django.db import close_old_connections
close_old_connections()
```
Omitting this causes `OperationalError: SSL connection has been closed unexpectedly` on the second poll cycle (Railway PostgreSQL drops idle connections).

---

### `planner/views_monitor.py` (new separate views file)

**Analog for file structure:** `planner/views_dante.py` (lines 1–17)

**Module header + imports pattern** (lines 1–17 of views_dante.py):
```python
# planner/views_dante.py

from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q

import json

from .models import (
    Project, Console, Device,
    DanteConsoleConfig, DanteDeviceConfig, DanteSubscription,
)
```
Copy this structure for `views_monitor.py`. Change comment header to `# planner/views_monitor.py`. Add `from django.http import StreamingHttpResponse` and `import time` to the stdlib block.

**Analog for standalone page view (GET):** `planner/views.py` — `power_distribution_calculator` (lines 1986–2049)

**Standalone page view pattern** (lines 1985–2049 of views.py):
```python
@login_required
def power_distribution_calculator(request, plan_id=None):
    """Main power distribution calculator view"""
    ...
    context = {
        'plan': plan,
        'amplifier_profiles': amplifier_profiles,
        ...
    }
    return render(request, 'planner/power_distribution_calculator.html', context)
```
`network_monitor_view` follows this same pattern: `@login_required`, read `request.current_project`, build context dict from DB queries scoped to project, return `render(request, 'planner/network_monitor.html', context)`.

**Analog for POST JSON endpoint:** `planner/views.py` — `comm_config_create` (lines 3754–3777)

**POST JSON endpoint pattern** (lines 3754–3777 of views.py):
```python
def comm_config_create(request):
    try:
        data = _json.loads(request.body)
        ...
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)
        ...
        return JsonResponse({'ok': True, 'config_id': config.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
```
Copy this try/except + project guard structure for `trigger_scan_view` and `add_monitor_devices_view`. Use `getattr(request, 'current_project', None)` — this is how all POST endpoints access the session-scoped project.

**SSE streaming view** — no existing analog in codebase. Use RESEARCH.md Pattern 1 exactly:
```python
@login_required
def monitor_stream_view(request):
    project = request.current_project

    def event_generator():
        last_id = 0
        while True:
            events = DeviceEvent.objects.filter(
                session__project=project,
                id__gt=last_id,
            ).order_by('id').select_related('device')[:50]
            for ev in events:
                last_id = ev.id
                yield f"data: {json.dumps(ev.as_sse_dict())}\n\n"
            yield ": heartbeat\n\n"
            time.sleep(2)

    response = StreamingHttpResponse(event_generator(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
```
The `X-Accel-Buffering: no` header is required to prevent Railway's nginx from batching SSE frames.

---

### `planner/urls.py` — add network-monitor paths

**Analog:** `planner/urls.py` — comm-config block (lines 61–95) and power-distribution block (lines 154–167)

**URL registration pattern** (lines 61–64, 154–155 of urls.py):
```python
path('comm-config/', views.comm_config_view, name='comm_config'),
path('comm-config/<int:config_id>/', views.comm_config_view, name='comm_config_editor'),
path('comm-config/create/', views.comm_config_create, name='comm_config_create'),
...
path('power-distribution/', views.power_distribution_calculator, name='power_distribution_calculator'),
```
For `views_monitor.py`, import it at the top of `urls.py` alongside the existing `views_dante` import:
```python
from . import views_monitor
```
Then register paths using `views_monitor.` prefix, mirroring `views_dante.` usage in lines 251–261.

**Import block pattern** (lines 1–9 of urls.py):
```python
from django.urls import path
from . import views
from django.contrib import admin
...
from . import views_dante
```
Add `from . import views_monitor` immediately after `from . import views_dante` on line 9.

**Path naming convention:** Use underscores in `name=` values (e.g., `name='network_monitor'`, `name='monitor_stream'`, `name='network_monitor_scan'`). Consistent with all existing names.

---

### `templates/planner/network_monitor.html` (new template)

**Analog:** `templates/planner/mic_tracker.html` (1464 lines)

**Template header pattern** (lines 1–13 of mic_tracker.html):
```django
{% extends "admin/base_site.html" %}
{% load static %}

{% block title %}Mic Tracker - {{ show_info.show_name|default:"Audio Patch" }}{% endblock %}

{% block breadcrumbs %}
<div class="breadcrumbs">
    <a href="{% url 'admin:index' %}">Home</a>
    &rsaquo; <a href="/admin/planner/showday/">Show Days</a>
    &rsaquo;
</div>
{% endblock %}
```
`network_monitor.html` uses the identical `{% extends "admin/base_site.html" %}` + `{% load static %}` header. Note: templates in this project extend `admin/base_site.html`, NOT `planner/base.html` — RESEARCH.md's mention of `base.html` is incorrect based on actual template inspection.

**CSS variables + root scope pattern** (lines 16–42 of mic_tracker.html):
```css
{% block extrastyle %}
    {{ block.super }}
    <style>
    :root {
        --bg-base:       #0f0f1a;
        --bg-card:       #181828;
        --bg-raised:     #1e1e32;
        --bg-input:      #252540;
        --border:        #2a2a45;
        --border-bright: #3a3a60;
        --accent-blue:   #4a9eff;
        --accent-green:  #00e676;
        --accent-amber:  #ffab00;
        --accent-red:    #ff5252;
        --text-primary:  #e8e8f0;
        --text-secondary:#9090b0;
        --text-dim:      #505070;
    }
    #mic-tracker-root * { box-sizing: border-box; }
    #mic-tracker-root { ... }
```
Copy these exact CSS variable names. The design system is consistent across modules — `--accent-green` = online, `--accent-amber` = flapping, `--accent-red` = offline, `--accent-blue` = header accent. Use `#nhm-root` as the root scope ID (NHM = Network Health Monitor) instead of `#mic-tracker-root`.

**JavaScript block placement** (mic_tracker.html lines 1440–1463 — `<script>` at bottom before `</body>`):
```html
<script>
// All JS inline at bottom of template
// Uses localStorage for UI state persistence (collapse/expand)
document.querySelectorAll('[data-session-id]').forEach(function(session) {
    const sessionId = session.dataset.sessionId;
    const savedTab = localStorage.getItem('sessionTab-' + sessionId);
    ...
});
</script>
```
All JavaScript goes in a single `<script>` block at the bottom of the template (before `{% endblock %}`). No external JS files — consistent with the CSS-in-template, JS-in-template pattern used by every existing module. `localStorage` is used for collapse state and scroll position persistence — copy this pattern for NHM domain-section collapse state.

**No `{% block content %}` — uses `{% block extrahead %}` and inline content** — look at how mic_tracker.html structures its main content block and replicate for network_monitor.html.

---

### `planner/admin_ordering.py` — update order_map and child_models

**Analog:** `planner/admin_ordering.py` — existing `order_map` dict (lines 76–140) and `child_models` set (lines 48–67)

**order_map extension pattern** (lines 122–128 of admin_ordering.py):
```python
# Standalone Models (28-29)
'audiochecklist': 29,

# P1 & Galaxy Processors (30-35)
'p1processor': 30,
```
Add monitor models after position 29 (audiochecklist), before P1/Galaxy block. Assign:
```python
# Network Health Monitor (28.1-28.4)
'monitorsession': 28.1,
'discovereddevice': 28.2,
'pollresult': 28.3,
'deviceevent': 28.4,
```

**child_models set pattern** (lines 48–67 of admin_ordering.py):
```python
child_models = {
    'pafanout',
    'commposition',
    ...
    'amplifierprofile',   # Child of Amplifier Profiles
}
```
Add `'pollresult'` and `'deviceevent'` to `child_models` — these are child records not useful as top-level admin list views. `'monitorsession'` and `'discovereddevice'` should remain visible (they are the parent-level objects the engineer interacts with).

---

### `planner/admin.py` — register new models

**Analog:** `planner/admin.py` lines 5899–5920 (showstack_admin_site.register block)

**Registration pattern** (lines 5899–5920 of admin.py):
```python
showstack_admin_site.register(Console, ConsoleAdmin)
showstack_admin_site.register(Device, DeviceAdmin)
showstack_admin_site.register(ShowDay, ShowDayAdmin)
showstack_admin_site.register(MicSession, MicSessionAdmin)
```
Add at the end of the register block:
```python
showstack_admin_site.register(MonitorSession, MonitorSessionAdmin)
showstack_admin_site.register(DiscoveredDevice, DiscoveredDeviceAdmin)
showstack_admin_site.register(PollResult, PollResultAdmin)
showstack_admin_site.register(DeviceEvent, DeviceEventAdmin)
```
Each requires a corresponding `ModelAdmin` subclass defined earlier in `admin.py`. Minimal admin classes are sufficient for Phase 1 — `list_display`, `list_filter`, `readonly_fields` for append-only tables (`PollResult`, `DeviceEvent`).

---

## Shared Patterns

### Session-based project scoping
**Source:** `planner/views.py` — `comm_config_view` line 1887, `comm_config_create` line 3758
**Apply to:** All views in `views_monitor.py`
```python
current_project = getattr(request, 'current_project', None)
if not current_project:
    return JsonResponse({'error': 'No active project'}, status=400)
```
This is the canonical pattern from `CurrentProjectMiddleware`. Never read project from URL; always from `request.current_project` (set by middleware) or `getattr(request, 'current_project', None)` for safety. All querysets must be scoped with `.filter(project=current_project)`.

### Login decoration
**Source:** `planner/views.py` lines 1985, 557 context
**Apply to:** All views in `views_monitor.py`
```python
@login_required
def network_monitor_view(request):
```
Use `@login_required` (not `@staff_member_required`) — consistent with `power_distribution_calculator`. `@staff_member_required` is used for destructive write operations in mic tracker. For the monitor's read-heavy views, `@login_required` is correct.

### JSON POST endpoint error handling
**Source:** `planner/views.py` — `comm_config_create` lines 3754–3777
**Apply to:** `trigger_scan_view`, `add_monitor_devices_view`, `remove_monitor_device_view`
```python
try:
    data = json.loads(request.body)
    ...
    return JsonResponse({'ok': True})
except Exception as e:
    return JsonResponse({'error': str(e)}, status=500)
```
All POST JSON endpoints use this bare try/except pattern. No custom exception classes exist in this codebase.

### Admin registration on showstack_admin_site
**Source:** `planner/admin.py` lines 5899–5920
**Apply to:** `MonitorSession`, `DiscoveredDevice`, `PollResult`, `DeviceEvent`
```python
from planner.admin_site import showstack_admin_site
showstack_admin_site.register(MyModel, MyModelAdmin)
```
Never use `admin.site.register()`. CLAUDE.md §4 explicitly requires `showstack_admin_site`.

### CSS design token system
**Source:** `templates/planner/mic_tracker.html` lines 17–33
**Apply to:** `templates/planner/network_monitor.html`
Use the existing `:root` CSS variables verbatim. The color mapping for status dots:
- Online → `--accent-green` (`#00e676`)
- Flapping (1–2 failures) → `--accent-amber` (`#ffab00`)
- Offline (3+ failures) → `--accent-red` (`#ff5252`)
- Unknown → `--text-dim` (`#505070`)

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `planner/management/commands/run_monitor.py` — daemon thread portion | utility | event-driven / daemon | All 7 existing management commands are one-shot (no daemon threads, no `add_arguments`, no `threading.Event`). Daemon pattern comes from RESEARCH.md Pattern 2. |
| SSE endpoint (`monitor_stream_view`) | controller | streaming | No `StreamingHttpResponse` usage exists anywhere in the codebase. Pattern comes from RESEARCH.md Pattern 1 (verified against Django 5.2.4). |

---

## Metadata

**Analog search scope:** `planner/`, `templates/planner/`
**Files scanned:** 12 source files (views.py, views_dante.py, urls.py, models.py, admin.py, admin_site.py, admin_ordering.py, 7 management commands, mic_tracker.html, comm_config.html)
**Pattern extraction date:** 2026-04-22

**Key observations for planner:**
1. Templates extend `admin/base_site.html` (NOT `planner/base.html` as mentioned in RESEARCH.md — confirmed by direct inspection of mic_tracker.html and comm_config.html)
2. All CSS and JS lives inline in the template — no separate static files for module-specific code
3. `views_dante.py` establishes the pattern for a separate views file imported in `urls.py` — use `views_monitor.py` with the same import style
4. The project is scoped via `request.current_project` (set by middleware) — `getattr(request, 'current_project', None)` is the safe accessor in POST endpoints
5. New models append to the end of `models.py` — no separate app, no separate models file
