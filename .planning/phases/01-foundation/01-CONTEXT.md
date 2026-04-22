# Phase 1: Foundation - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 delivers the core monitoring pipeline: network device discovery via ICMP ping sweep, a live SSE-powered dashboard showing device reachability with green/yellow/red status, critical alerts with N=3 confirm-before-firing, and session history tracking state changes. This phase proves the full poll→DB→SSE→browser pipeline using ICMP — the simplest protocol — before SNMP and Dante layers are added in later phases.

</domain>

<decisions>
## Implementation Decisions

### Dashboard Layout
- **D-01:** Dashboard is a standalone page at `/audiopatch/network-monitor/` — consistent with mic-tracker, comm-config, and power-distribution as full-page standalone views (not admin changeform)
- **D-02:** Devices are grouped by network domain (Dante, LA Network, Switches) — matches how an A1 thinks about show networks
- **D-03:** Minimal device cards — device name + green/yellow/red status dot. Click to expand for details (IP, latency, last seen)
- **D-04:** Domain rollup summary bar at top: "Dante: 12/12 ✅ | LA Network: 8/8 ✅ | Switches: 3/3 ✅" — instant health glance before scrolling

### Device Discovery
- **D-05:** Devices are discovered by scanning the network directly — NOT pulled from existing ShowStack device models (Console, Device, Amp, etc.). The monitor discovers what's actually on the network, independent of project data.
- **D-06:** Discovery method: scan the selected NIC's subnet via ping sweep, show all responding devices, let engineer select which ones to keep monitoring. Unselected devices are hidden but can be re-shown.
- **D-07:** NIC selection: auto-detect all active network interfaces and let engineer pick which NIC to scan. No permanent per-domain NIC assignment — flexible per-scan selection.
- **D-08:** For devices with multiple IPs (e.g., consoles with primary + secondary), monitor primary IP only.

### Alert Behavior
- **D-09:** N=3 confirm-before-firing — device must fail 3 consecutive polls before a critical alert fires. No single-flap false positives.

### Claude's Discretion
- Alert presentation (banner, toast, badge) — Claude picks the right approach for a live show monitoring context
- Session history timeline visual design — Claude decides layout (event log table, timeline, etc.)
- "Not on show network" detection and messaging approach

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `CLAUDE.md` §7b — Network Health Monitor design notes and constraints
- `.planning/PROJECT.md` — Project vision, core value, constraints
- `.planning/REQUIREMENTS.md` — Phase 1 requirements: MON-02, MON-03, DASH-01, DASH-02, DASH-03, INFRA-01, INFRA-02, INFRA-03

### Research
- `.planning/research/STACK.md` — Technology recommendations (icmplib, zeroconf, pysnmp, SSE approach)
- `.planning/research/ARCHITECTURE.md` — Two-process model, management command, SSE via StreamingHttpResponse
- `.planning/research/PITFALLS.md` — mDNS VLAN boundaries, alert fatigue, browser tab throttling, N=3 polling

### Existing Codebase Patterns
- `planner/management/commands/` — Existing management command pattern (7 commands, all one-shot)
- `planner/middleware.py` — CurrentProjectMiddleware (session-based project scoping)
- `planner/admin_site.py` — showstack_admin_site registration pattern
- `planner/views.py` — Standalone page view patterns (mic_tracker_view, comm_config_view, power_distribution_calculator)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Management command infrastructure: `planner/management/commands/` has 7 existing commands — established pattern for `run_monitor`
- GenericForeignKey already used in models.py (line 982-989) for console output routing — pattern available but D-05 decision means we're NOT using FK to existing models
- Standalone page templates: `templates/planner/mic_tracker.html`, `templates/planner/comm_config.html`, `templates/planner/power_distribution_calculator.html` — follow these patterns for the dashboard

### Established Patterns
- All standalone views use session-based project scoping via `request.current_project` from `CurrentProjectMiddleware`
- Views are registered in `planner/urls.py` under the `audiopatch/` prefix
- Templates extend `templates/planner/base.html`
- IP addresses use `models.GenericIPAddressField` across all existing models

### Integration Points
- URL registration in `planner/urls.py` for the dashboard view
- New models in `planner/models.py` for monitor targets, poll results, and events
- New management command in `planner/management/commands/run_monitor.py`
- New template at `templates/planner/network_monitor.html`
- `admin_ordering.py` must be updated if any models are registered on showstack_admin_site

</code_context>

<specifics>
## Specific Ideas

- Discovery is network-centric (scan what's on the wire), not project-centric (look up what's in the database). This is a deliberate design choice — the monitor should show the real network state, not what the engineer thinks should be there.
- The domain rollup bar acts as the "one-screen answer" to the core value: engineer glances at the bar and knows if the show is healthy.
- Phase 1 groups by domain even though only ICMP is implemented — the dashboard structure anticipates Phases 2 and 3 adding SNMP and Dante domains.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-04-22*
