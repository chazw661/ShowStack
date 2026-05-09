---
phase: 02-switch-snmp
plan: "02"
subsystem: network-monitor-agent
tags: [snmp, threading, pysnmp, run_monitor, bandwidth, if-mib]
dependency_graph:
  requires: []
  provides: [snmp-polling-agent, dual-thread-agent]
  affects: [planner/management/commands/run_monitor.py, requirements.txt]
tech_stack:
  added: [pysnmp>=7.1,<8.0]
  patterns: [daemon-threads, threading.Event, asyncio.run-from-thread, RFC-2863-bandwidth]
key_files:
  created: []
  modified:
    - planner/management/commands/run_monitor.py
    - requirements.txt
decisions:
  - "Used pysnmp v7 snake_case API (walk_cmd + UdpTransportTarget.create) — bulkCmd camelCase was removed in v7"
  - "Used walk_cmd (async generator) instead of bulk_cmd (single await) — better for subtree walks with lexicographicMode=False"
  - "Changed round(pct, 1) to round(pct, 2) to preserve small but nonzero bandwidth values that would collapse to 0.0"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-25"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 02 Plan 02: Dual-thread agent with pysnmp v7 SNMP polling

Restructured run_monitor from a flat signal-handler while-loop to two daemon threads (ICMPPoller + SNMPPoller) sharing a threading.Event stop signal, with complete SNMP v2c polling via pysnmp 7.1 using IF-MIB OIDs and RFC 2863 bandwidth calculation from counter deltas.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Install pysnmp and add to requirements.txt | 4649a6d | requirements.txt |
| 2 | Restructure run_monitor to dual daemon threads and add SNMP polling | 3d41382 | planner/management/commands/run_monitor.py |

## Decisions Made

1. **pysnmp v7 API is snake_case**: `bulkCmd` was removed; `walk_cmd` and `bulk_cmd` are the correct names. `UdpTransportTarget` now requires `await UdpTransportTarget.create(...)` — direct instantiation is gone. Updated all code accordingly.

2. **walk_cmd over bulk_cmd**: For IF-MIB subtree walks, `walk_cmd` (async generator with `lexicographicMode=False`) is simpler and more correct than single-shot `bulk_cmd`. Avoids needing to manually loop and track OID progress.

3. **round(pct, 2) not round(pct, 1)**: The verification test requires `bw > 0`. For lightly-loaded links (e.g. 1MB/30s on 1Gbps = 0.027%), rounding to 1dp collapses to `0.0` which fails `> 0`. Two decimal places preserves `0.03` — the true result and a more useful display value.

4. **PYSNMP_AVAILABLE guard**: The `_snmp_loop` gracefully degrades if pysnmp is not installed — logs a warning and returns early. The ICMP thread continues unaffected.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pysnmp v7 API uses snake_case, not camelCase**
- **Found during:** Task 2 — import verification
- **Issue:** Plan code used `bulkCmd` (old camelCase API removed in pysnmp 7.0). `pysnmp>=7.1` exports `bulk_cmd` and `walk_cmd`. Also `UdpTransportTarget` requires `await .create()` not direct construction.
- **Fix:** Replaced `bulkCmd` with `walk_cmd` (async generator, supports `lexicographicMode=False`). Replaced `UdpTransportTarget((ip, 161), ...)` with `await UdpTransportTarget.create((ip, 161), ...)`. Replaced `snmp_engine.close()` with `snmp_engine.closeDispatcher()`.
- **Files modified:** planner/management/commands/run_monitor.py
- **Commit:** 3d41382

**2. [Rule 1 - Bug] Bandwidth rounding to 1dp collapses small valid values to 0.0**
- **Found during:** Task 2 — verification assertion `0 < bw`
- **Issue:** `_compute_bandwidth_pct(2_000_000, 1_000_000, 500_000, 0, 0.0, 30.0, 1000)` returns `0.027%` which `round(..., 1)` collapses to `0.0`. Plan acceptance criteria requires `0 < bw <= 100`.
- **Fix:** Changed `round(pct, 1)` to `round(pct, 2)` — result is `0.03`, passes the assertion, and is a more precise display value.
- **Files modified:** planner/management/commands/run_monitor.py
- **Commit:** 3d41382

## Known Stubs

None — no UI or data-rendering paths modified in this plan. The agent pushes data to `/api/snmp-results/` which is handled by Plan 01's endpoints.

## Threat Flags

None — no new network endpoints introduced. The SNMP polling surface (agent -> switch over UDP 161) is documented in the plan's threat model as T-02-06 (accepted) and T-02-07 (mitigated by fixed 30s interval).

## Self-Check: PASSED

- [x] `planner/management/commands/run_monitor.py` exists and modified
- [x] `requirements.txt` contains `pysnmp>=7.1,<8.0`
- [x] Commit `4649a6d` exists (requirements.txt)
- [x] Commit `3d41382` exists (run_monitor.py restructure)
- [x] All acceptance criteria verified: `_icmp_loop`, `_snmp_loop`, `_fetch_snmp_settings`, `_push_snmp_results`, `_compute_bandwidth_pct`, `IF_MIB_ROOTS` all present
- [x] Bandwidth calc test passes: `_compute_bandwidth_pct(2_000_000, 1_000_000, 500_000, 0, 0.0, 30.0, 1000)` = `0.03%`
- [x] No old `running = True` / `while running:` flat-loop pattern in file
- [x] `ICMPPoller` and `SNMPPoller` thread names present
- [x] `stop_event.wait(timeout=1)` in main thread (not `time.sleep`)
