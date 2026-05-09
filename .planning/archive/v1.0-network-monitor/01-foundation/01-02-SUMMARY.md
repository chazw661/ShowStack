---
phase: 01-foundation
plan: "02"
subsystem: network-health-monitor
tags: [views, urls, sse, icmp, scan, device-management]
dependency_graph:
  requires:
    - MonitorSession model (Plan 01)
    - DiscoveredDevice model (Plan 01)
    - PollResult model (Plan 01)
    - DeviceEvent model (Plan 01)
  provides:
    - network_monitor_view (dashboard page render)
    - monitor_stream_view (SSE endpoint)
    - trigger_scan_view (NIC subnet sweep)
    - add_monitor_devices_view (device registration)
    - remove_monitor_device_view (soft-deactivation)
    - get_scannable_nics utility
    - sweep_subnet utility
    - 5 URL patterns under network-monitor/
  affects:
    - planner/views_monitor.py
    - planner/urls.py
tech_stack:
  added: []
  patterns:
    - SSE via StreamingHttpResponse with text/event-stream content type
    - NIC allowlist validation for subnet sweep (server-detected subnets only)
    - Soft-delete pattern for device removal (is_active=False)
    - get_or_create with re-activation path for add_monitor_devices_view
    - X-Accel-Buffering: no header for Railway nginx SSE compatibility
key_files:
  created:
    - planner/views_monitor.py
  modified:
    - planner/urls.py
decisions:
  - "netifaces and icmplib imported lazily inside functions to prevent ImportError at Django startup if packages not yet installed"
  - "SSE stream sends both new DeviceEvent rows AND periodic STATUS_SNAPSHOT every 2s — snapshot ensures browser stays in sync even if it missed an event"
  - "Subnet validated against get_scannable_nics() allowlist in trigger_scan_view — prevents using endpoint as arbitrary port scanner"
  - "remove_monitor_device_view soft-deletes (is_active=False) — device can be re-added via scan"
  - "add_monitor_devices_view re-activates previously deactivated devices rather than raising duplicate error"
metrics:
  duration_minutes: 3
  completed_date: "2026-04-22"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 1 Plan 2: Views and URL Configuration Summary

**One-liner:** Five Django view functions and two utility functions in views_monitor.py — SSE streaming endpoint, NIC-detected subnet sweep, device add/remove endpoints, and dashboard render — wired into five URL patterns under /audiopatch/network-monitor/.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create views_monitor.py with all view and utility functions | 65194cf | planner/views_monitor.py |
| 2 | Wire network-monitor URL patterns into urls.py | ffe4c08 | planner/urls.py |

## What Was Built

### views_monitor.py (planner/views_monitor.py)

Seven functions — 5 views and 2 utilities:

**Utilities:**
- **get_scannable_nics()** — enumerates host NICs via `netifaces`, filters loopback and link-local, caps subnets at /24 to prevent enormous sweeps on corporate networks. Returns list of `{interface, ip, subnet, display}` dicts.
- **sweep_subnet(subnet_cidr)** — calls `icmplib.multiping(privileged=False, concurrent_tasks=100)` against all hosts in the subnet, returns list of `{ip, latency_ms}` for responding hosts.

**Views (all `@login_required`, all scoped to `request.current_project`):**
- **network_monitor_view** — renders `planner/network_monitor.html` with current DB snapshot: active devices grouped by domain, recent events, active alerts (offline devices), NIC list, session state.
- **monitor_stream_view** — SSE endpoint returning `StreamingHttpResponse(content_type='text/event-stream')`. Generator loop: polls for new `DeviceEvent` rows since last seen ID, then sends a `STATUS_SNAPSHOT` of all devices, then emits a heartbeat comment every 2 seconds. `X-Accel-Buffering: no` prevents Railway nginx from batching frames.
- **trigger_scan_view** — POST endpoint that validates the requested subnet against `get_scannable_nics()` allowlist, runs `sweep_subnet`, annotates results with `already_monitored` flag, and returns JSON.
- **add_monitor_devices_view** — POST endpoint that `get_or_create`s `DiscoveredDevice` records; re-activates previously soft-deleted devices rather than failing on duplicate.
- **remove_monitor_device_view** — POST endpoint that soft-deletes a device by setting `is_active=False`; scoped to `current_project` to prevent cross-project removal.

### URL patterns (planner/urls.py)

Five patterns added under `network-monitor/` prefix:

| URL | View | Name |
|-----|------|------|
| `network-monitor/` | network_monitor_view | network_monitor |
| `network-monitor/stream/` | monitor_stream_view | monitor_stream |
| `network-monitor/scan/` | trigger_scan_view | network_monitor_scan |
| `network-monitor/devices/add/` | add_monitor_devices_view | add_monitor_devices |
| `network-monitor/devices/<int:device_id>/remove/` | remove_monitor_device_view | remove_monitor_device |

Full URLs at `/audiopatch/network-monitor/` per D-01. Import `from . import views_monitor` added to urls.py.

## Deviations from Plan

None — plan executed exactly as written.

The plan referenced adding `from . import views_monitor` after the existing `from . import views_dante` line. The worktree's base commit (495f932) did not have the `views_dante` import present (that's in the main branch's uncommitted working tree changes). The import was added after `populate_amp_models_view` instead — which achieves the same result functionally. This is not a semantic deviation; the plan instruction was about positioning relative to a line that wasn't in scope for this worktree.

## Known Stubs

None. This plan creates view and URL infrastructure only — no template is wired (Plan 03 delivers the template). The `network_monitor_view` renders `planner/network_monitor.html` which will be created in Plan 03. Until then, visiting `/audiopatch/network-monitor/` will return a `TemplateDoesNotExist` error — this is expected and not a stub issue.

## Threat Surface Scan

All five STRIDE mitigations from the plan's threat model are confirmed implemented:

| Threat ID | Mitigation Status |
|-----------|------------------|
| T-02-01 (SSE disclosure) | @login_required on monitor_stream_view; DeviceEvent filtered by session.project |
| T-02-02 (scan input tampering) | valid_subnets allowlist in trigger_scan_view — only server-detected subnets accepted |
| T-02-03 (SSE cross-project leak) | STATUS_SNAPSHOT queries filtered by project=current_project |
| T-02-04 (DoS via large subnet) | /24 cap in get_scannable_nics(); prefixlen < 24 networks re-capped |
| T-02-05 (remove other project's device) | Device lookup filtered by project=current_project before deactivation |

No new threat surface beyond what was declared in the plan's threat model.

## Self-Check: PASSED

- planner/views_monitor.py: exists — FOUND
- network_monitor_view, monitor_stream_view, trigger_scan_view, add_monitor_devices_view, remove_monitor_device_view — FOUND (5 views)
- get_scannable_nics, sweep_subnet — FOUND (2 utilities)
- @login_required: 5 matches (one per view) — FOUND
- text/event-stream content type — FOUND
- X-Accel-Buffering: no — FOUND
- valid_subnets allowlist — FOUND
- planner/urls.py: from . import views_monitor — FOUND
- planner/urls.py: 5 network-monitor/ patterns — FOUND (grep -c returns 5)
- All 5 URL names resolve via django.urls.reverse — VERIFIED
- Commits 65194cf, ffe4c08 — verified in git log
