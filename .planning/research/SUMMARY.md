# Project Research Summary

**Project:** ShowStack Network Health Monitor
**Domain:** Live audio network monitoring (Dante/mDNS, SNMP switches, LA Network/ICMP)
**Researched:** 2026-04-21
**Confidence:** MEDIUM-HIGH

## Executive Summary

The Network Health Monitor is a locally-executed Django module that monitors three parallel show networks — Dante audio networking (mDNS discovery), L'Acoustics amplification (ICMP reachability), and entertainment switches (SNMP) — and presents a unified status dashboard to the A1 engineer. No competing product aggregates all three domains. The recommended approach is a two-process local model: `python manage.py runserver` for the web layer plus `python manage.py run_monitor` as a long-running background poller, communicating through PostgreSQL and pushing updates to the browser via Server-Sent Events. The entire system runs on the engineer's laptop on the show network; the Railway deployment is not involved in monitoring.

The core stack is conservative and dependency-light by design: `zeroconf` and `netaudio` for Dante mDNS discovery, `pysnmp` (LeXtudio maintained fork) for SNMP, `icmplib` for ping reachability, plain Django `StreamingHttpResponse` for SSE, and native PostgreSQL for event storage. No Redis, no Celery, no TimescaleDB, no Django Channels. This keeps the tool installable in minutes on a show laptop — a non-negotiable UX constraint given the deployment context.

The highest-risk area is the Dante integration: `netaudio` is reverse-engineered, explicitly described by its author as "guesswork," and can cause devices to behave unexpectedly. Clock monitoring via mDNS/protocol is LOW confidence. The safe strategy is to use mDNS discovery for presence detection only and ICMP ping as the authoritative reachability signal, treating all other Dante protocol data as advisory. A second critical risk is the "local network required" precondition, which is invisible to engineers opening the dashboard from a cloud URL — onboarding UX must surface this immediately.

---

## Key Findings

### Recommended Stack

The stack prioritizes zero-infrastructure-overhead for local laptop deployment. Every library is pure Python where possible to avoid native C build issues on macOS arm64 at show site.

**Core technologies:**
- `zeroconf >=0.148.0`: mDNS listener for Dante service type enumeration — actively maintained, asyncio-native
- `netaudio 0.2.4`: Dante-specific mDNS service type constants and device query wrappers — use for read-only discovery only
- `pysnmp >=7.0,<8.0` (LeXtudio fork): SNMP v1/v2c/v3 for switch port status and counters — pure Python, v7.1.24 released April 2026
- `icmplib >=3.0`: ICMP ping for amp and Dante device reachability — pure Python, unprivileged on macOS, async multiping support
- Django `StreamingHttpResponse` (built-in): SSE push to browser — no additional infrastructure
- Native Django ORM + PostgreSQL: event and poll result storage — plain indexed model, no TimescaleDB needed at show-day event volumes

**Architecture:** Two-process model — `run_monitor` management command (daemon threads per protocol) + `runserver` (web layer reads from DB only). SSE via StreamingHttpResponse + HTMX SSE extension for live dashboard updates.

### Expected Features

No competing tool unifies Dante, LA Network, and switch monitoring. Engineers currently maintain three separate app windows with no persistent history.

**Must have (table stakes):**
- Dante device auto-discovery and per-device up/down status
- Dante clock master identification and lock/unlocked status per device
- Switch SNMP port status (up/down) per configured switch
- LA Network amp reachability via ICMP ping
- At-a-glance dashboard with green/yellow/red rollup per domain
- Critical alerts on device offline or clock loss with confirm-before-firing (N=3 consecutive failures)
- Session history: append-only state-change timeline with timestamps
- Integration with existing ShowStack device records as FK sources for IP addresses

**Should have (differentiators):**
- Pre-show network health check comparing discovered vs project-defined device list
- Cross-domain event correlation (multiple devices on same switch port = one grouped alert)
- Switch bandwidth utilization warnings (70%/90% thresholds)
- Show mode toggle (Setup / Show / Wrap) suppressing alerts during load-in/load-out
- Export session history as PDF/CSV

**Defer (v2+):**
- Dante multicast bandwidth monitoring
- Mobile status view at `/m/`
- EEE detection on switch ports carrying Dante traffic

### Critical Pitfalls

1. **netaudio is reverse-engineered and unreliable for protocol commands** — use mDNS enumeration only; ICMP ping is the authoritative reachability signal
2. **mDNS silently returns empty across VLAN boundaries** — show diagnostic state rather than empty discovery; offer manual IP entry fallback
3. **Dante clock loss and device offline are distinct failure modes** — model clock status separately from reachability
4. **Luminex GigaCore SNMP disabled by default** — detect SNMP non-response vs auth failure vs timeout distinctly; provide in-app setup guide
5. **Alert fatigue during load-in destroys engineer trust** — implement show mode toggle; N=3 consecutive failures before critical alert
6. **Browser tab throttling kills WebSocket/SSE heartbeats** — Web Worker-based heartbeat or Page Visibility API refresh on tab foreground

---

## Implications for Roadmap

### Phase 1: Foundation — Data Models, ICMP Pipeline, and SSE Dashboard

Proves the full poll→DB→SSE pipeline with the simplest protocol. Delivers LA Network amp reachability, at-a-glance dashboard, session history, and `run_monitor` management command. Locks architecture decisions: GenericFK to existing device models, two-table data model, management command lifecycle, SSE approach, N=3 confirm-before-firing.

### Phase 2: Switch SNMP Integration and Alert Design

Adds switch port monitoring with SNMP, per-project credential config (v2c and v3), show mode toggle (Setup/Show/Wrap), and in-app Luminex SNMP setup guide. SNMP against real show networks is when alert fatigue first surfaces — show mode belongs here.

### Phase 3: Dante mDNS Discovery and Clock Monitoring

Highest protocol uncertainty — built last so ICMP and SNMP dashboards already deliver value. Adds Dante auto-discovery via zeroconf, per-device mDNS presence + ICMP reachability, clock master/lock status (advisory), NIC/VLAN selection UI, and manual IP entry fallback. Clock status requires hardware validation — treat as stretch goal.

### Phase 4: Correlation, Pre-Show Check, and Export

Differentiating features requiring all three pollers running: cross-domain correlation, pre-show health check report, session history export as PDF/CSV, switch bandwidth utilization warnings, mobile status view at `/m/`.

### Research Flags

- **Phase 3 (Dante):** Clock status via netaudio needs hardware validation. LOW confidence. Flag clock monitoring as stretch with explicit fallback.
- **Phase 2 (SNMP):** pysnmp on macOS arm64 needs benchmarking against real switch hardware.
- **Phase 1 (ICMP + SSE):** HIGH confidence, standard patterns. No additional research needed.
- **Phase 4 (Export):** Solved problem in ShowStack context. No additional research needed.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | pysnmp and icmplib HIGH; netaudio LOW (author disclaims reliability) |
| Features | HIGH | Table stakes verified against official Audinate, L-Acoustics, and Luminex docs |
| Architecture | HIGH | Component boundaries, data model, SSE approach well-sourced |
| Pitfalls | HIGH | Critical pitfalls sourced from official Audinate documentation and RFC standards |

### Gaps to Address

- Dante clock status via netaudio: LOW confidence, hardware validation required
- icmplib unprivileged mode on macOS arm64: MEDIUM, needs Phase 1 smoke test
- SNMP library build on macOS arm64: MEDIUM, needs Phase 1 benchmark
- Local-only deployment model UX: prerequisite-check UI must ship with Phase 1

---
*Research completed: 2026-04-21*
*Ready for roadmap: yes*
