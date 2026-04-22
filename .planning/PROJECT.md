# ShowStack Network Health Monitor

## What This Is

A real-time network monitoring module for ShowStack that gives live audio engineers a single dashboard to monitor all show-critical networks — Dante, L'Acoustics LA Network (Milan/AVB), and entertainment switches. Runs from any laptop on the show network with ShowStack open in the browser.

## Core Value

An engineer can look at one screen and know instantly whether every network on the show is healthy, and get alerted immediately when something goes wrong.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Dante device discovery and connectivity monitoring (IP addresses, reachability)
- [ ] Dante clock status monitoring (master/slave, lock state, latency)
- [ ] LA Network device connectivity confirmation (amplifier reachability)
- [ ] Switch monitoring via SNMP (port status, link speed, error counters)
- [ ] At-a-glance dashboard with green/yellow/red status indicators
- [ ] Active alerts with notifications for critical issues (device drops, clock failures)
- [ ] Session history — timeline of network state changes during a show day
- [ ] Works from any laptop on the show network running ShowStack in a browser
- [ ] Integration with existing ShowStack project-scoping (session-based multi-tenancy)

### Out of Scope

- Remote/cloud-based monitoring of on-site networks — requires direct network access from the browser/laptop
- Dante subscription management — the frozen Dante Subscription Planner module handles that domain
- Amplifier DSP control or configuration — LA Network Manager handles that; this module only monitors connectivity
- VLAN configuration or switch provisioning — read-only monitoring, not management

## Context

ShowStack is an existing Django 5.x multi-tenant SaaS platform for live audio production management. The Network Health Monitor is a new module being added to the existing codebase. It must follow ShowStack's established patterns:

- Session-based project scoping via `CurrentProjectMiddleware`
- Custom admin site (`showstack_admin_site`)
- Role-based permissions (superuser, premium owner, editor, viewer)
- Railway deployment for the web app, but monitoring requires local network access

**Key architectural decision:** The monitoring runs from a laptop on the show network. There is no separate agent or service — the engineer opens ShowStack in a browser on a machine connected to the Dante/LANet/switch networks. The backend (Django running locally or the browser itself) polls devices directly.

**Target networks on a typical large-format show:**
- **Dante** — mDNS-discoverable, well-documented control protocol, Python libraries available for discovery and status queries
- **LA Network (Milan/AVB)** — L'Acoustics amplifiers with IP addresses, reachability confirmable via ping/ARP, no public API for deep telemetry
- **Entertainment switches** — Luminex, Cisco, Netgear — SNMP v2c/v3 for port status, error counters, bandwidth, PoE

**Prior work:** The CLAUDE.md references a Network Health Monitor section (§7b) as the current active development focus. Some early design thinking exists but no code has been written yet.

## Constraints

- **Existing codebase:** Must integrate with ShowStack's Django architecture, not be a standalone tool
- **Network access:** Monitoring requires the laptop running ShowStack to be physically on the show networks
- **Protocol limitations:** LA Network has no public API — connectivity confirmation only (ping/ARP), not deep amp telemetry
- **Browser security:** Direct SNMP/mDNS from the browser is not possible — backend Django process must handle network polling
- **Multi-network:** Show networks are often VLANed (Dante on one VLAN, control on another) — the monitoring laptop may need access to multiple VLANs

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Local agent model (laptop on network) | ShowStack runs on Railway but show networks are local; engineer's laptop bridges the gap | — Pending |
| Active alerts, not passive status | Engineers need to be notified of problems during a show, not just check periodically | — Pending |
| Session history for show day | Post-show troubleshooting and documentation require knowing when things went down/up | — Pending |
| LA Network = connectivity only | No public API for deep telemetry; reachability is still valuable | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-21 after initialization*
