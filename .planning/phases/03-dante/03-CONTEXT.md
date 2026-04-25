# Phase 3: Dante - Context

**Gathered:** 2026-04-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 adds Dante device auto-discovery via mDNS, clock master/lock status display, and a pre-show health check that compares discovered devices against the project device list. This builds on the Phase 1 ICMP pipeline and Phase 2 SNMP/show mode infrastructure. The agent uses netaudio for mDNS discovery; ICMP remains the authoritative reachability signal. Clock status is advisory (LOW protocol confidence — see blocker in STATE.md).

</domain>

<decisions>
## Implementation Decisions

### Dante Discovery & Device Matching
- **D-01:** Auto-match by name — mDNS device names are compared against project device labels/names. Matched devices are linked automatically. Unmatched devices are not shown in the Dante section.
- **D-02:** Unmatched Dante devices (discovered on mDNS but not matching any project record) go to the Unassigned section, same as unknown devices from Phase 1 ping sweep.
- **D-03:** Missing project devices (expected but not discovered on mDNS) show as ghost cards in the Dante section AND are flagged in the pre-show health check. Dual visibility.

### Clock Status Display
- **D-04:** Clock status is primary info — displayed prominently on the collapsed Dante card, same visual weight as the reachability status dot.
- **D-05:** Section-level advisory footnote — a single note at the top of the Dante section: "Clock status is advisory — verify on hardware before showtime." No per-card advisory labels.
- **D-06:** Show whatever netaudio reports — if multiple devices claim clock master, show them all as master. No warning or interpretation. The engineer knows what it means.

### Pre-Show Health Check
- **D-07:** Auto-run on page load with manual re-check button — health check runs every time the dashboard loads and there's a "Re-check" button for manual trigger.
- **D-08:** Expandable panel in Dante section — results appear in a collapsible panel that auto-expands when issues are found (missing or unexpected devices), stays collapsed when everything matches.
- **D-09:** Presence-based matching — any Dante device on the network counts. The health check compares names and flags mismatches, but doesn't require strict project record linking. Less strict than the auto-match in D-01.

### Dante Section Layout
- **D-10:** Collapsed Dante cards show: device name (from mDNS), clock role (Master/Locked/Unlocked), and Dante channel count (if available from mDNS service data). IP address in expanded view.
- **D-11:** Ghost cards (missing project devices) are dimmed — lower opacity, grey text, "unreachable" style status dot. Consistent with existing unreachable device visual pattern.

### Claude's Discretion
- Health check panel layout and styling
- Channel count display format
- Clock role icon/text presentation
- Ghost card exact opacity and styling
- Re-check button placement (section header vs inline)
- How auto-match handles partial name matches vs exact matches

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `CLAUDE.md` §7b — Network Health Monitor design notes and constraints
- `.planning/PROJECT.md` — Project vision, core value, constraints
- `.planning/REQUIREMENTS.md` — Phase 3 requirements: MON-01, MON-04, DAN-01, DAN-02

### Prior Phase Foundation
- `.planning/phases/02-switch-snmp/02-CONTEXT.md` — Phase 2 decisions (show mode, SNMP credentials, expandable cards, bandwidth thresholds)
- `planner/models.py` — DiscoveredDevice, MonitorSession, DeviceEvent, ProjectSNMPConfig, SwitchPortSnapshot
- `planner/views_monitor.py` — Monitor views: status endpoint, agent APIs, dashboard mutation endpoints
- `templates/planner/network_monitor.html` — Dashboard template with Dante section placeholder
- `planner/management/commands/run_monitor.py` — Agent with ICMPPoller + SNMPPoller dual threads

### Research
- `.planning/research/STACK.md` — Technology recommendations (netaudio for mDNS)
- `.planning/research/PITFALLS.md` — netaudio clock status LOW confidence, link-local ARP discovery

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DiscoveredDevice` model with `domain` field — Dante devices can use `domain='dante'`
- Dashboard Dante section placeholder exists in `network_monitor.html` — ready to populate
- Device card pattern (`nhm-card` with status dot, expandable detail) — reuse for Dante cards
- `_authenticate_agent` pattern in views_monitor.py — reuse for new agent endpoints
- AJAX polling already consumes `data.devices` — extend for Dante-specific fields

### Established Patterns
- Agent pushes results via HTTP POST, Django stores them, dashboard polls via AJAX
- Link-local (169.254.x.x) Dante devices need ARP cache discovery, not /24 ping sweep
- netaudio for mDNS discovery only — ICMP is authoritative reachability signal
- Expandable device cards with status dots (Phase 1 pattern, extended in Phase 2)

### Integration Points
- New Dante polling thread in `run_monitor.py` (alongside ICMPPoller and SNMPPoller)
- New mDNS discovery results pushed to Django API (new endpoint)
- Clock status stored per device (new field or model)
- Health check comparison logic (server-side, consumed by dashboard JS)
- Dante section in `network_monitor.html` — replace placeholder with real cards

</code_context>

<specifics>
## Specific Ideas

- On show networks, Dante devices use link-local addressing (169.254.x.x) via auto-IP. The agent needs to discover these via ARP cache or mDNS service records, not by scanning the /16 range.
- The pre-show health check is the "did everything show up?" sanity check before doors open. It should be quick and obvious — green checkmark when all clear, red flags when something's missing.
- Channel count from mDNS service data helps the engineer confirm they're looking at the right device (e.g., "RIO3224-2" should have 32x24 channels).

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-dante*
*Context gathered: 2026-04-25*
