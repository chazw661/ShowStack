# Roadmap: ShowStack Network Health Monitor

## Overview

Three phases build the monitor from the ground up. Phase 1 proves the full poll-to-dashboard pipeline using ICMP — the simplest protocol — and delivers a working dashboard with LA Network amp reachability, live SSE updates, session history, and alerts. Phase 2 adds switch SNMP monitoring and the show mode toggle. Phase 3 completes the Dante domain with mDNS auto-discovery, clock status, and the pre-show health check. All three phases run locally from the engineer's laptop on the show network.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - ICMP pipeline, SSE dashboard, session history, and alert system
- [ ] **Phase 2: Switch SNMP** - SNMP switch port monitoring, credentials, bandwidth warnings, and show mode
- [ ] **Phase 3: Dante** - mDNS discovery, clock status, and pre-show health check

## Phase Details

### Phase 1: Foundation
**Goal**: Engineer can see live reachability status for all LA Network amps on a single dashboard, with alerts on device offline and a session history timeline
**Depends on**: Nothing (first phase)
**Requirements**: MON-02, MON-03, DASH-01, DASH-02, DASH-03, INFRA-01, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. Engineer opens the dashboard and sees green/yellow/red reachability status for each amp, updating live without a page refresh
  2. If an amp goes offline for 3 consecutive polls, a critical alert fires; no alert fires on a single flap
  3. The session history timeline shows each up/down state change with a timestamp for the current show day
  4. Running `python manage.py run_monitor` starts background ICMP polling; stopping it halts all polling cleanly
  5. When the laptop is not on the show network, the dashboard shows a clear "not connected to show network" message rather than silent empty status
**Plans:** 3 plans
Plans:
- [x] 01-01-PLAN.md — Models, migration, admin, run_monitor command
- [x] 01-02-PLAN.md — Views (SSE, scan, device management) and URL wiring
- [x] 01-03-PLAN.md — Dashboard template (HTML/CSS/JS)
**UI hint**: yes

### Phase 2: Switch SNMP
**Goal**: Engineer can monitor switch port status, link speed, and bandwidth utilization via SNMP, and suppress non-critical alerts during load-in and load-out
**Depends on**: Phase 1
**Requirements**: SW-01, SW-02, SW-03, SW-04, DASH-04
**Success Criteria** (what must be TRUE):
  1. Each configured switch shows per-port up/down status and link speed on the dashboard
  2. Engineer can enter SNMP credentials (v2c community string or v3 auth/priv) per project and have them persist
  3. Port error counters accumulate over time and are visible per port
  4. A bandwidth warning indicator appears on a port when utilization exceeds the configured threshold (default 70%/90%)
  5. Show mode toggle (Setup / Show / Wrap) suppresses non-critical alerts when set to Setup or Wrap
**Plans:** 3 plans
Plans:
- [x] 02-01-PLAN.md — Models, migration, admin, API endpoints, URL wiring
- [x] 02-02-PLAN.md — Agent SNMP thread restructure and pysnmp integration
- [x] 02-03-PLAN.md — Dashboard template (settings panel, show mode, switch cards, port tables)
**UI hint**: yes

### Phase 3: Dante
**Goal**: Dante devices auto-discover on the network, show reachability and clock status, and the engineer can run a pre-show health check comparing discovered devices against the project device list
**Depends on**: Phase 2
**Requirements**: MON-01, MON-04, DAN-01, DAN-02
**Success Criteria** (what must be TRUE):
  1. Dante devices appear on the dashboard automatically via mDNS without the engineer entering IP addresses manually
  2. The dashboard identifies which Dante device is the clock master
  3. Per-device clock lock/unlock status is displayed with an advisory label indicating confidence level
  4. Pre-show health check compares discovered Dante devices against the project-defined device list and flags any missing or unexpected devices
**Plans:** 3 plans
Plans:
- [ ] 03-01-PLAN.md — Dante model fields, migration, DantePoller agent thread
- [ ] 03-02-PLAN.md — Agent Dante results endpoint, health check endpoint, status view extension
- [ ] 03-03-PLAN.md — Dashboard Dante UI (cards, ghost cards, advisory, health check panel)
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete | - |
| 2. Switch SNMP | 0/3 | Planning complete | - |
| 3. Dante | 0/3 | Planning complete | - |
