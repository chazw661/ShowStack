---
phase: 02-switch-snmp
plan: "01"
subsystem: network-health-monitor
tags: [django, snmp, models, api, admin]
dependency_graph:
  requires: []
  provides:
    - ProjectSNMPConfig model (SNMP v2c community string per project)
    - SwitchPortSnapshot model (per-port SNMP data, update_or_create pattern)
    - MonitorSession.show_mode field (setup/show/wrap alert suppression)
    - DeviceEvent.EVENT_CHOICES extended (PORT_DOWN, PORT_UP, BW_WARNING, BW_CRITICAL)
    - agent_snmp_settings endpoint (GET, Bearer auth)
    - agent_snmp_results endpoint (POST, Bearer auth, show mode suppression)
    - dashboard_snmp_settings endpoint (POST, login_required)
    - dashboard_add_switch endpoint (POST, login_required, IP validation)
    - dashboard_set_show_mode endpoint (POST, login_required)
    - monitor_status_view extended (show_mode, switch_ports, snmp_configured keys)
  affects:
    - planner/models.py
    - planner/views_monitor.py
    - planner/urls.py
    - planner/admin.py
    - planner/admin_ordering.py
tech_stack:
  added: []
  patterns:
    - OneToOneField per-project config (ProjectSNMPConfig)
    - update_or_create per-port snapshot (SwitchPortSnapshot)
    - Bearer token agent auth (_authenticate_agent pattern)
    - Show mode alert suppression (suppress_non_critical flag)
    - IP validation via ipaddress.ip_address()
key_files:
  created:
    - planner/migrations/0150_monitorsession_show_mode_and_more.py
  modified:
    - planner/models.py
    - planner/views_monitor.py
    - planner/urls.py
    - planner/admin.py
    - planner/admin_ordering.py
decisions:
  - SwitchPortSnapshot uses update_or_create (device, session, port_index) — one row per port replaced each cycle, not appended
  - agent_snmp_settings is GET (not POST) since it only reads config, following agent_device_list precedent
  - switch_ports dict keyed by device.pk (as string) for easy JS lookup
  - snmp_configured bool added to both monitor_status_view JSON and network_monitor_view template context
metrics:
  duration_minutes: 4
  completed_date: "2026-04-25"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 5
  files_created: 1
---

# Phase 2 Plan 01: Django Backend for SNMP Switch Monitoring Summary

**One-liner:** Django data layer + API surface for SNMP switch monitoring — two new models, five new endpoints, show mode alert suppression, admin registration.

## What Was Built

### Task 1: Models + Migration
- `MonitorSession.show_mode` field added (CharField, choices: setup/show/wrap, default='show')
- `DeviceEvent.EVENT_CHOICES` extended with PORT_DOWN, PORT_UP, BW_WARNING, BW_CRITICAL
- `ProjectSNMPConfig` model: OneToOneField to Project, stores SNMP v2c community string per project
- `SwitchPortSnapshot` model: per-port SNMP data (oper_status, speed_mbps, bandwidth_pct, error_count), update_or_create keyed by (device, session, port_index)
- Migration `0150_monitorsession_show_mode_and_more.py` generated

### Task 2: API Endpoints + Admin
- `agent_snmp_settings` (GET, Bearer auth): returns community string + switch IP list to agent
- `agent_snmp_results` (POST, Bearer auth): stores SwitchPortSnapshot rows per port, fires PORT_UP/PORT_DOWN/BW_WARNING/BW_CRITICAL events, suppresses non-critical events when show_mode is setup or wrap
- `dashboard_snmp_settings` (POST, login_required): saves community string with non-empty + max-255 validation
- `dashboard_add_switch` (POST, login_required): manually adds switch IP with ipaddress.ip_address() validation and duplicate handling
- `dashboard_set_show_mode` (POST, login_required): sets show_mode on active session with whitelist validation
- `monitor_status_view` extended: now returns show_mode, switch_ports (per-device port data), snmp_configured
- `network_monitor_view` context extended: snmp_configured and show_mode injected for template first-render
- 5 new URL patterns registered in planner/urls.py
- `ProjectSNMPConfigAdmin` and `SwitchPortSnapshotAdmin` registered on showstack_admin_site
- admin_ordering.py updated: projectsnmpconfig=40, switchportsnapshot=41; switchportsnapshot added to child_models

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | cc25e24 | feat(02-01): add ProjectSNMPConfig, SwitchPortSnapshot models and show_mode field |
| 2 | ffbfc17 | feat(02-01): add 5 SNMP API endpoints, extend monitor_status_view, register admin |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all endpoints are fully implemented. The agent (Plan 02) and dashboard UI (Plan 03) will wire up to these endpoints.

## Threat Surface Scan

All endpoints follow the threat model dispositions from the plan:
- T-02-01 (Spoofing): both agent endpoints use `_authenticate_agent()` Bearer token check
- T-02-02 (Tampering): dashboard_add_switch validates IP via `ipaddress.ip_address()` and scopes to current_project
- T-02-04 (Tampering): dashboard_snmp_settings validates non-empty + max 255 chars, login_required + CSRF
- T-02-05 (EoP): dashboard_set_show_mode validates mode against whitelist, login_required

No new threat surface beyond what is in the plan's threat model.

## Self-Check

**Files exist:**
- planner/migrations/0150_monitorsession_show_mode_and_more.py: FOUND
- planner/models.py: FOUND (ProjectSNMPConfig, SwitchPortSnapshot, show_mode)
- planner/views_monitor.py: FOUND (5 new endpoints)
- planner/urls.py: FOUND (5 new URL patterns)
- planner/admin.py: FOUND (ProjectSNMPConfigAdmin, SwitchPortSnapshotAdmin)
- planner/admin_ordering.py: FOUND (positions 40-41, switchportsnapshot in child_models)

**Commits exist:**
- cc25e24: FOUND
- ffbfc17: FOUND

**`python manage.py check`:** Passed (0 issues)

## Self-Check: PASSED
