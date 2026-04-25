---
phase: 03-dante
plan: "02"
subsystem: network-health-monitor
tags: [dante, api, views, urls, health-check]
dependency_graph:
  requires: [03-01]
  provides: [agent_dante_results, health_check_view, dante_data_in_poll]
  affects: [planner/views_monitor.py, planner/urls.py]
tech_stack:
  added: []
  patterns: [bearer-token-agent-auth, login-required-dashboard, update-or-create-device, case-insensitive-name-matching]
key_files:
  created: []
  modified:
    - planner/views_monitor.py
    - planner/urls.py
decisions:
  - "health_check_view queries Console, Device, and Amp (all project device types) per RESEARCH.md A4 — not just Dante-flagged devices"
  - "DANTE_LOST fires only when dante_device_name is set and last_known_state == 'online' to avoid noise on never-seen devices"
  - "dante_data included inline in monitor_status_view response to avoid a separate AJAX round-trip for dashboard rendering"
metrics:
  duration: "~5 minutes"
  completed: "2026-04-25T21:37:32Z"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 3 Plan 02: Dante API Endpoints Summary

Django API endpoints for Dante discovery ingestion and pre-show health check, with Dante data extended into the existing poll response.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add agent_dante_results, health_check_view, extend monitor_status_view | 1908b9a | planner/views_monitor.py |
| 2 | Add URL routes for Dante endpoints | 57bec48 | planner/urls.py |

## What Was Built

### agent_dante_results (POST /audiopatch/network-monitor/api/dante-results/)
- Bearer token auth via existing `_authenticate_agent` helper
- Validates JSON body: checks `results` is a list, rejects entries without IP
- Validates `clock_role` against allowed values (`master`, `locked`, `unlocked`, `unknown`) — falls back to `unknown` per T-03-04
- `update_or_create` DiscoveredDevice with `domain='dante'` and all six Dante fields
- Creates `DANTE_DISCOVERED` event for newly-seen devices
- Creates `DANTE_LOST` event for stale Dante devices not in current discovery cycle (only when previously online)

### health_check_view (GET /audiopatch/network-monitor/api/health-check/)
- Session auth via `@login_required`; project-scoped via `request.current_project` (no cross-project leakage)
- Queries `DiscoveredDevice` for `domain='dante', is_active=True` dante_device_names
- Queries `Console`, `Device`, and `Amp` for all project device names
- Case-insensitive name matching per D-09 / RESEARCH.md Pitfall 5
- Returns `missing` (expected not found), `unexpected` (found not expected), counts, and status string

### monitor_status_view extension
- Added `dante_data` dict to poll response alongside existing `switch_ports`
- Keys are device PKs; values include `dante_device_name`, `clock_role`, `tx_channels`, `rx_channels`
- Only populated for `domain='dante'` devices; avoids separate dashboard request

### URL routes (planner/urls.py)
- `network-monitor/api/health-check/` -> `health_check_view` (Phase 3: Dante dashboard)
- `network-monitor/api/dante-results/` -> `agent_dante_results` (Phase 3: Dante agent)
- Follows Phase 2 SNMP comment and grouping pattern exactly

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. The Dante fields (`dante_device_name`, `clock_role`, etc.) referenced in views_monitor.py are added to `DiscoveredDevice` by Plan 01 (parallel worktree). These will be present after merge. No stub data flows to UI rendering.

## Threat Flags

No new threat surface beyond what is in the plan's threat model. All mitigations from T-03-04 and T-03-05 are implemented:
- T-03-04: JSON validated (list check, IP required, clock_role allowlist)
- T-03-05: `@login_required` on health_check_view, project-scoped queries

## Self-Check: PASSED

- `planner/views_monitor.py`: FOUND — 152 lines added, `agent_dante_results` and `health_check_view` confirmed via AST parse
- `planner/urls.py`: FOUND — `health_check` and `agent_dante_results` URL names confirmed via string check
- Commit `1908b9a`: FOUND
- Commit `57bec48`: FOUND
