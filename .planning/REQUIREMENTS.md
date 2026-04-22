# Requirements: ShowStack Network Health Monitor

**Defined:** 2026-04-21
**Core Value:** An engineer can look at one screen and know instantly whether every network on the show is healthy, and get alerted immediately when something goes wrong.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Device Monitoring

- [ ] **MON-01**: Dante devices auto-discovered on the network via mDNS without manual IP entry
- [ ] **MON-02**: All project devices show up/down reachability status via ICMP ping
- [ ] **MON-03**: Monitor targets pull IP addresses from existing ShowStack device records (Console, Device, Amp) via FK
- [ ] **MON-04**: Pre-show health check compares discovered devices against project-defined device list

### Dante

- [ ] **DAN-01**: Dashboard identifies the Dante clock master device on the network
- [ ] **DAN-02**: Per-device clock lock/unlock status displayed (advisory — depends on netaudio protocol confidence)

### Switch Monitoring

- [ ] **SW-01**: Switch port up/down status and link speed displayed via SNMP polling
- [ ] **SW-02**: Per-project SNMP credential configuration (community string for v2c, auth/priv for v3)
- [ ] **SW-03**: Port error counter tracking over time
- [ ] **SW-04**: Bandwidth utilization warnings at configurable thresholds (default 70%/90%)

### Dashboard & Alerts

- [ ] **DASH-01**: At-a-glance green/yellow/red status indicators per network domain
- [ ] **DASH-02**: Critical alerts for device offline and clock loss with confirm-before-firing (N=3 consecutive failures)
- [ ] **DASH-03**: Session history timeline showing state changes with timestamps during show day
- [ ] **DASH-04**: Show mode toggle (Setup / Show / Wrap) suppresses non-critical alerts during load-in/out

### Infrastructure

- [ ] **INFRA-01**: `run_monitor` management command runs background polling with daemon threads per protocol
- [ ] **INFRA-02**: SSE push delivers live status updates to dashboard without page refresh
- [ ] **INFRA-03**: Local network prerequisite detection with clear messaging when not on show network

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Mobile & Export

- **MOBILE-01**: Mobile-optimized status view at `/m/` for A2s on phones
- **EXPORT-01**: Session history export as PDF/CSV for post-show documentation
- **EXPORT-02**: Pre-show health check report export

### Advanced Monitoring

- **ADV-01**: Cross-domain event correlation (multiple devices on same switch port = one grouped alert)
- **ADV-02**: Dante multicast bandwidth monitoring
- **ADV-03**: EEE detection on switch ports carrying Dante traffic

## Out of Scope

| Feature | Reason |
|---------|--------|
| Remote/cloud monitoring of on-site networks | Monitoring requires direct local network access from the laptop |
| Dante subscription management | Frozen Dante Subscription Planner module handles that domain |
| Amplifier DSP control or configuration | LA Network Manager handles that; this module monitors connectivity only |
| VLAN configuration or switch provisioning | Read-only monitoring, not management |
| Django Channels / WebSockets | SSE via StreamingHttpResponse is simpler and sufficient for one-directional push |
| Redis / Celery | Runs locally on laptop; APScheduler or management command handles background polling |
| TimescaleDB | Event volumes at show scale don't justify a separate time-series database |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MON-01 | Phase 3 | Pending |
| MON-02 | Phase 1 | Pending |
| MON-03 | Phase 1 | Pending |
| MON-04 | Phase 3 | Pending |
| DAN-01 | Phase 3 | Pending |
| DAN-02 | Phase 3 | Pending |
| SW-01 | Phase 2 | Pending |
| SW-02 | Phase 2 | Pending |
| SW-03 | Phase 2 | Pending |
| SW-04 | Phase 2 | Pending |
| DASH-01 | Phase 1 | Pending |
| DASH-02 | Phase 1 | Pending |
| DASH-03 | Phase 1 | Pending |
| DASH-04 | Phase 2 | Pending |
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0

---
*Requirements defined: 2026-04-21*
*Last updated: 2026-04-21 after roadmap creation*
