---
phase: 03-dante
plan: "01"
subsystem: network-monitor
tags: [dante, mdns, model, agent, poller]
dependency_graph:
  requires: []
  provides: [dante-model-fields, dante-poller-thread]
  affects: [planner/models.py, planner/management/commands/run_monitor.py]
tech_stack:
  added: [netaudio (optional import guard)]
  patterns: [import-guard, async-coroutine-via-asyncio-run, push-thread-pattern]
key_files:
  created:
    - planner/migrations/0151_discovereddevice_clock_role_and_more.py
  modified:
    - planner/models.py
    - planner/management/commands/run_monitor.py
decisions:
  - "NETAUDIO_AVAILABLE import guard mirrors PYSNMP_AVAILABLE pattern — missing dependency disables feature with warning, no crash"
  - "PTP role mapping: Leader->master, Follower->locked, else->unknown (advisory per D-05/D-06)"
  - "DantePoller only runs when devices found (no-op push avoided)"
metrics:
  duration: "~8 minutes"
  completed: "2026-04-25T21:38:01Z"
  tasks_completed: 2
  files_changed: 3
---

# Phase 3 Plan 01: Dante Model Fields and DantePoller Agent Thread Summary

Dante device discovery infrastructure: 6 new fields on DiscoveredDevice for mDNS-sourced device data (name, clock role, channel counts, model ID, MAC), plus a DantePoller thread in run_monitor.py that uses netaudio's DanteBrowser to discover devices every 30 seconds and POST results to /api/dante-results/.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add Dante fields to DiscoveredDevice model | e01f1fe | planner/models.py, planner/migrations/0151_* |
| 2 | Add DantePoller thread to run_monitor agent | 8b834b4 | planner/management/commands/run_monitor.py |

## What Was Built

**Task 1 — DiscoveredDevice Dante fields:**
- Added `CLOCK_ROLE_CHOICES` class constant: master, locked, unlocked, unknown
- Added 6 fields after `discovered_at`: `dante_device_name`, `clock_role`, `tx_channel_count`, `rx_channel_count`, `dante_model_id`, `dante_mac_address`
- Extended `as_status_dict()` to include dante_device_name, clock_role, tx_channels, rx_channels when `domain == 'dante'`
- Added `DANTE_DISCOVERED` and `DANTE_LOST` to `DeviceEvent.EVENT_CHOICES`
- Generated migration 0151 (verified: `makemigrations --check --dry-run` returns no changes)

**Task 2 — DantePoller thread:**
- `NETAUDIO_AVAILABLE` import guard at module level (matches `PYSNMP_AVAILABLE` pattern)
- `_async_discover_dante(timeout=3.0)` module-level coroutine using `DanteBrowser.get_devices()`
- PTP role mapping: `ptp_v1_role == 'Leader'` -> master, `'Follower'` -> locked, else -> unknown
- `_dante_loop()` method: checks import guard, runs every 30s via `asyncio.run()`, calls `_push_dante_results()` only when devices found
- `_push_dante_results()` method: POSTs to `/api/dante-results/`, logs DANTE_DISCOVERED/DANTE_LOST events from response
- `DantePoller` thread wired in `handle()` alongside ICMPPoller and SNMPPoller
- Startup message updated to include "Dante every 30s"

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - no UI wiring in this plan. The `/api/dante-results/` endpoint is implemented in Plan 02.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: unauthenticated-input | run_monitor.py | mDNS results from DanteBrowser are unauthenticated (T-03-01 accepted - show networks are physically controlled). Payload validation at /api/dante-results/ is Plan 02's responsibility (T-03-02 mitigate). |

## Self-Check: PASSED

- planner/models.py: Dante fields confirmed via `DiscoveredDevice._meta.get_fields()` - 6 fields present
- planner/migrations/0151_discovereddevice_clock_role_and_more.py: file exists, `makemigrations --check` returns no pending changes
- run_monitor.py: `from planner.management.commands.run_monitor import Command` imports OK
- DantePoller thread: `_dante_loop`, `_push_dante_results` methods confirmed on Command instance
- `_async_discover_dante` confirmed as coroutine function
- Commits e01f1fe and 8b834b4 exist in git log
