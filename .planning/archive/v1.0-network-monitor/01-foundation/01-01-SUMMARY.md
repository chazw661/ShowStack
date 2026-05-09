---
phase: 01-foundation
plan: "01"
subsystem: network-health-monitor
tags: [models, migration, management-command, icmp, admin, polling]
dependency_graph:
  requires: []
  provides:
    - MonitorSession model
    - DiscoveredDevice model
    - PollResult model
    - DeviceEvent model
    - run_monitor management command
    - Admin registration for all 4 models
  affects:
    - planner/models.py
    - planner/migrations/
    - planner/admin.py
    - planner/admin_ordering.py
tech_stack:
  added:
    - icmplib>=3.0,<4.0
    - netifaces>=0.11
  patterns:
    - Django management command with daemon thread
    - N=3 consecutive failure state machine on model
    - ICMP multiping with privileged=False (SOCK_DGRAM, no root)
    - Append-only admin (has_add_permission=False, has_change_permission=False)
key_files:
  created:
    - planner/management/commands/run_monitor.py
    - planner/migrations/0148_discovereddevice_monitorsession_deviceevent_and_more.py
  modified:
    - planner/models.py
    - planner/admin.py
    - planner/admin_ordering.py
    - requirements.txt
decisions:
  - "DiscoveredDevice has no FK to Console/Device/Amp — D-05 (discover from network scan) overrides MON-03 (pull from existing records)"
  - "_record_poll is a nested function inside handle() to share session context without globals"
  - "privileged=False always — SOCK_DGRAM ICMP verified working on macOS arm64 without root"
metrics:
  duration_minutes: 2
  completed_date: "2026-04-22"
  tasks_completed: 3
  tasks_total: 3
---

# Phase 1 Plan 1: Backend Data Layer and Polling Engine Summary

**One-liner:** Four Django ORM models (MonitorSession, DiscoveredDevice, PollResult, DeviceEvent) with migration, a `run_monitor` management command implementing ICMP multiping daemon thread with N=3 state machine, and admin registration on `showstack_admin_site` with sidebar ordering at positions 36–39.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create monitor models and migration | 2afbf19 | planner/models.py, migration 0148, requirements.txt |
| 2 | Create run_monitor management command | 7bac923 | planner/management/commands/run_monitor.py |
| 3 | Register monitor models in admin and update sidebar ordering | 5d365d6 | planner/admin.py, planner/admin_ordering.py |

## What Was Built

### Models (planner/models.py)

Four models appended at end of file:

- **MonitorSession** — tracks a single `run_monitor` invocation; `ended_at` set on clean shutdown; active session = `ended_at__isnull=True`
- **DiscoveredDevice** — project-scoped device from subnet scan; `consecutive_failures` + `last_known_state` drive N=3 state machine; `as_status_dict()` for SSE payloads; `unique_together` on `(project, ip_address)`
- **PollResult** — raw append-only poll log; DB indexes on `(device, polled_at)` and `(session, polled_at)` for efficient time-range queries
- **DeviceEvent** — state transitions only (ONLINE/OFFLINE/SCAN_STARTED/MONITOR_STARTED); `as_sse_dict()` for SSE delivery; read-only in admin

### run_monitor Command (planner/management/commands/run_monitor.py)

- `--project-id` (required) and `--interval` (default 10s) arguments
- Creates or resumes an open MonitorSession on start; writes `MONITOR_STARTED` DeviceEvent
- Daemon thread `ICMPPoller` runs `icmplib.multiping(privileged=False, concurrent_tasks=50)` every interval seconds
- `close_old_connections()` called at top of every poll cycle (prevents Railway PostgreSQL SSL errors in long-running threads)
- `stop_event.wait(timeout=interval)` instead of `time.sleep` — clean shutdown without waiting for sleep
- N=3 state machine: `consecutive_failures` increments on each failure, resets to 0 on success; OFFLINE event fires at exactly `== 3`, not on subsequent failures; ONLINE event fires when device returns from any non-online state
- `session.ended_at` set on `KeyboardInterrupt` for clean lifecycle tracking

### Admin Registration (planner/admin.py, planner/admin_ordering.py)

- All 4 models registered on `showstack_admin_site` (not `admin.site`)
- PollResultAdmin and DeviceEventAdmin are fully read-only: `has_add_permission=False`, `has_change_permission=False`
- Sidebar positions 36–39: MonitorSession(36), DiscoveredDevice(37), PollResult(38), DeviceEvent(39)
- PollResult and DeviceEvent added to `child_models` set — hidden from viewer-role sidebar

## Deviations from Plan

None — plan executed exactly as written.

The MON-03 note in the plan (DiscoveredDevice has no FK to existing module models, D-05 takes precedence) was honored. No structural deviations were needed.

## Known Stubs

None. This plan creates backend infrastructure only — no UI templates or data-wired components.

## Threat Surface Scan

T-01-02 mitigation (append-only admin for PollResult/DeviceEvent) confirmed implemented via `has_add_permission=False` and `has_change_permission=False` on both admin classes.

No new threat surface beyond what was declared in the plan's threat model.

## Self-Check: PASSED

- planner/models.py: MonitorSession, DiscoveredDevice, PollResult, DeviceEvent — FOUND
- planner/migrations/0148_discovereddevice_monitorsession_deviceevent_and_more.py — FOUND
- planner/management/commands/run_monitor.py — FOUND
- planner/admin.py: 4 admin registrations — FOUND
- planner/admin_ordering.py: positions 36-39, pollresult/deviceevent in child_models — FOUND
- requirements.txt: icmplib, netifaces — FOUND
- Commits 2afbf19, 7bac923, 5d365d6 — verified in git log
