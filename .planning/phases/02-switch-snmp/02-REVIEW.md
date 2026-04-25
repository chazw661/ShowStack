---
phase: 02-switch-snmp
reviewed: 2026-04-25T19:45:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - planner/models.py
  - planner/views_monitor.py
  - planner/urls.py
  - planner/admin.py
  - planner/admin_ordering.py
  - planner/management/commands/run_monitor.py
  - templates/planner/network_monitor.html
findings:
  critical: 2
  warning: 5
  info: 3
  total: 10
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-25T19:45:00Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed the Network Health Monitor module across models, views, URLs, admin, admin ordering, management command, and dashboard template. The Phase 1 architecture (agent-based ICMP polling, cloud-side state machine, AJAX dashboard) is well-structured. However, the Phase 2 SNMP switch monitoring UI has been scaffolded in the template (settings panel, port table rendering, show-mode toggle, `saveSettings()`, `setShowMode()`) but the corresponding backend endpoints (`/snmp-settings/`, `/show-mode/`) and models (`ProjectSNMPConfig`, `SwitchPortSnapshot`) do not yet exist. This creates two critical issues: the frontend calls endpoints that return 404s, and the API key is exposed in the browser page source.

## Critical Issues

### CR-01: API Key Exposed in Browser-Side JavaScript

**File:** `templates/planner/network_monitor.html:1965`
**Issue:** The `addManualDevice()` function sends the project `agent_api_key` directly from the browser via a `Bearer` authorization header. This key is rendered into the page source at line 1965 (`'Authorization': 'Bearer {{ agent_api_key }}'`) and is visible to any authenticated user who can access the dashboard -- including `viewer`-role users. The agent API key is meant for machine-to-machine auth from the local agent, not browser-side use. Any user with dashboard access can extract the key and impersonate the agent (push fake scan results, trigger state changes, stop the session).
**Fix:** The `addManualDevice()` function should POST to a new session-authenticated dashboard endpoint (like the existing `dashboard_remove_device` and `dashboard_reassign_device` patterns) instead of calling the agent API endpoint with a bearer token. For example:

```python
# views_monitor.py
@login_required
@require_POST
def dashboard_add_device(request):
    """Add a device manually from the dashboard (session auth)."""
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)

    data = json.loads(request.body)
    devices_data = data.get('devices', [])
    # ... same logic as agent_scan_results but scoped to current_project ...
```

Then update the JS to use CSRF-authenticated fetch instead of Bearer token.

### CR-02: Frontend Calls Non-Existent Backend Endpoints (404 Errors)

**File:** `templates/planner/network_monitor.html:2317-2321` and `templates/planner/network_monitor.html:2374`
**Issue:** The `setShowMode()` function POSTs to `/audiopatch/network-monitor/show-mode/` (line 2317) and `saveSettings()` POSTs to `/audiopatch/network-monitor/snmp-settings/` (line 2374). Neither endpoint exists in `planner/urls.py` or `planner/views_monitor.py`. Users clicking "Save Settings" or toggling show mode will get silent 404 failures. The `saveSettings()` catch block shows a generic error, but `setShowMode()` only logs to console -- the user sees no feedback that their mode change was not persisted server-side.
**Fix:** Either implement the backend endpoints before shipping, or remove/disable the UI elements until the backend is ready. At minimum, add the two view functions and URL routes:

```python
# urls.py - add these routes
path('network-monitor/snmp-settings/', views_monitor.snmp_settings_view, name='snmp_settings'),
path('network-monitor/show-mode/', views_monitor.show_mode_view, name='show_mode'),
```

## Warnings

### WR-01: No Authorization Check on Dashboard Views (Viewer Role Can Modify)

**File:** `planner/views_monitor.py:176-237`
**Issue:** The `dashboard_remove_device`, `dashboard_reassign_device`, and `dashboard_request_scan` views only check `@login_required` and verify the user has a `current_project`. They do not check the user's role. Per CLAUDE.md, viewers should have read-only access, but any authenticated user with the project in session can remove devices, reassign domains, and trigger re-scans.
**Fix:** Add role checking consistent with the `BaseEquipmentAdmin._get_user_role_for_project` pattern:

```python
def _require_editor(request):
    """Return JsonResponse error if user is not editor+ for current project, else None."""
    project = getattr(request, 'current_project', None)
    if not project:
        return JsonResponse({'error': 'No active project'}, status=400)
    if project.owner == request.user:
        return None
    try:
        member = ProjectMember.objects.get(user=request.user, project=project)
        if member.role == 'viewer':
            return JsonResponse({'error': 'Permission denied'}, status=403)
    except ProjectMember.DoesNotExist:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    return None
```

### WR-02: Unhandled JSON Parse Error on Agent API Endpoints

**File:** `planner/views_monitor.py:207`, `309`, `379`, `461`
**Issue:** Multiple agent API endpoints call `json.loads(request.body)` without a try/except. If the agent sends malformed JSON (network corruption, bug, or malicious request), this raises an unhandled `json.JSONDecodeError` resulting in a 500 error. The `dashboard_reassign_device` view (line 207) has the same issue for session-authenticated requests.
**Fix:** Wrap JSON parsing in try/except:

```python
try:
    data = json.loads(request.body)
except json.JSONDecodeError:
    return JsonResponse({'error': 'Invalid JSON'}, status=400)
```

### WR-03: agent_device_list Endpoint Accepts Any HTTP Method

**File:** `planner/views_monitor.py:476-493`
**Issue:** The `agent_device_list` view at line 476 is decorated with `@csrf_exempt` but not `@require_POST` or any method restriction. The function is designed for GET requests (fetching device list), but it will also accept POST, PUT, DELETE, etc. While not a direct vulnerability (it only reads data), this is inconsistent with the other agent endpoints and violates the principle of least privilege.
**Fix:** Add `require_GET` decorator or use `require_http_methods(['GET'])`:

```python
from django.views.decorators.http import require_GET

@csrf_exempt
@require_GET
def agent_device_list(request):
```

### WR-04: Template References `snmp_configured` Variable Not Passed by View

**File:** `templates/planner/network_monitor.html:2398`
**Issue:** Line 2398 uses `{{ snmp_configured|yesno:"true,false" }}` to initialize a JavaScript variable, but `network_monitor_view` in `views_monitor.py` does not include `snmp_configured` in the template context. Django will render this as an empty string, causing the `yesno` filter to output `"false"` (falsy default), which happens to be correct for now but is fragile. When the SNMP backend is implemented, forgetting to add this context variable will silently leave SNMP features disabled.
**Fix:** Add `snmp_configured` to the view context now (defaulting to `False`), so the template contract is explicit:

```python
context = {
    ...
    'snmp_configured': False,  # TODO: check ProjectSNMPConfig when model exists
}
```

### WR-05: `show_mode` Context Variable Referenced but Not Passed

**File:** `templates/planner/network_monitor.html:1255-1260`, `1265-1268`, `2311`
**Issue:** The template references `{{ show_mode }}` in multiple places (mode toggle buttons, mode banner, JS initialization) but `network_monitor_view` does not pass `show_mode` in the context dict. Django renders undefined variables as empty string, so the mode toggle defaults to "show" mode due to the `{% if show_mode == 'show' or not show_mode %}` fallback -- this works accidentally but is brittle.
**Fix:** Pass `show_mode` explicitly in the view context (defaulting to `'show'`).

## Info

### IN-01: Debug Print Statements in admin_ordering.py

**File:** `planner/admin_ordering.py:8-9`, `21`, `45`
**Issue:** Lines 8-9 print `"ADMIN_ORDERING.PY LOADED"` on every import, line 21 prints `"*** FUNCTION CALLED ***"` on every admin page load, and line 45 prints user/viewer debug info. These produce noise in production logs on every request.
**Fix:** Remove the print statements or convert to `logging.debug()`:

```python
import logging
logger = logging.getLogger(__name__)
# Replace: print("*** FUNCTION CALLED ***")
# With:    logger.debug("ordered_get_app_list called for %s", request.user)
```

### IN-02: Duplicate URL Patterns in urls.py

**File:** `planner/urls.py:156-159`, `165-167`, `187-188`
**Issue:** Several URL patterns are duplicated:
- `power-distribution/assignment/<id>/` and `update/` appear twice (lines 156-159)
- `update_amplifier_assignment` is registered three times (lines 157, 159, 166)
- `all_devices_pdf_export` is registered twice (lines 187-188)

These are not Phase 2 changes but are worth noting. Django uses the first match, so the duplicates are dead code.
**Fix:** Remove the duplicate entries.

### IN-03: Stale "Phase 2" Placeholder Text in Template

**File:** `templates/planner/network_monitor.html:1419`, `1475`
**Issue:** The Dante and Switches domain sections contain placeholder text saying "coming in Phase 2" (lines 1419 and 1475), but Phase 2 work is now underway. These placeholders will confuse users if the switch port table JS (which is already implemented client-side) starts rendering data alongside text saying "coming in Phase 2."
**Fix:** Update or remove the placeholder text. For switches, the `nhm-switches-placeholder` div should be hidden when port data is available (the `updateSwitchCards` JS function already replaces the detail inner content, but does not hide this separate placeholder element).

---

_Reviewed: 2026-04-25T19:45:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
