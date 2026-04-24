# Phase 2: Switch SNMP - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 adds SNMP-based switch port monitoring to the existing Network Health Monitor dashboard. Engineers can enter SNMP v2c credentials, see per-port status/speed/bandwidth for each switch, get bandwidth utilization warnings, and suppress non-critical alerts during load-in/out via a show mode toggle. This builds on the Phase 1 ICMP pipeline, SSE dashboard, and agent-based architecture.

</domain>

<decisions>
## Implementation Decisions

### SNMP Credentials
- **D-01:** Credentials entered via the dashboard — a settings panel accessible from a gear icon in the dashboard header. No admin panel entry required.
- **D-02:** Per-project credentials — one SNMP v2c community string shared by all switches in the project. No per-switch override.
- **D-03:** SNMP v2c only — community string authentication. Covers the target switch brands: Luminex, Netgear, and Ubiquiti entertainment switches. No v3 support in this phase.

### Switch Discovery & Display
- **D-04:** Both auto-detect and manual entry — devices assigned to the Switch domain from the Phase 1 ping sweep automatically get SNMP-polled, AND engineers can manually add switch IPs via the settings panel. Unassigned devices remain in the Unassigned section until reassigned.
- **D-05:** Expandable switch cards — collapsed view shows switch name, IP, port count summary (e.g., "24 ports - 22 up - 0 err"). Click to expand reveals a per-port table.
- **D-06:** Per-port table columns: port number, up/down status dot, link speed (100M/1G/10G), bandwidth utilization %. Error counters accessible on click/hover as secondary detail, not inline in the table.

### Show Mode Toggle
- **D-07:** Three-state toggle (Setup / Show / Wrap) in the dashboard header bar, next to the domain rollup pills. Always visible regardless of scroll.
- **D-08:** Only device-offline (N=3 consecutive failures) is critical and always fires in any mode. All other alerts — port status changes, bandwidth warnings, error counter spikes, link speed changes — are non-critical and suppressed in Setup and Wrap modes.
- **D-09:** Subtle amber banner appears below the header when in Setup or Wrap mode: "Setup mode — non-critical alerts suppressed". Banner disappears in Show mode.

### Bandwidth Warnings
- **D-10:** Bandwidth utilization displayed as a color-coded percentage per port: green (<70%), amber (70-90%), red (>90%).
- **D-11:** Thresholds are fixed at 70%/90% — not configurable by the engineer. Standard network monitoring thresholds.

### Claude's Discretion
- Settings panel layout and styling
- Error counter detail display (tooltip vs expandable row vs modal)
- SNMP polling interval (within reasonable bounds for entertainment switches)
- How manual switch IP entry UI works within the settings panel
- Show mode toggle visual design (segmented control, radio buttons, etc.)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `CLAUDE.md` §7b — Network Health Monitor design notes and constraints
- `.planning/PROJECT.md` — Project vision, core value, constraints
- `.planning/REQUIREMENTS.md` — Phase 2 requirements: SW-01, SW-02, SW-03, SW-04, DASH-04

### Phase 1 Foundation
- `.planning/phases/01-foundation/01-CONTEXT.md` — Phase 1 decisions (dashboard layout, agent architecture, device discovery, alert behavior)
- `.planning/phases/01-foundation/01-UI-SPEC.md` — Phase 1 UI spec (dashboard layout, card design, domain sections)

### Existing Implementation
- `planner/models.py` — Network Health Monitor models: MonitorSession, DiscoveredDevice, PollResult, DeviceEvent (lines 4549-4665)
- `planner/views_monitor.py` — Monitor views: SSE, scan results, poll results, device management APIs
- `templates/planner/network_monitor.html` — Dashboard template with Switch section placeholder (line 1160+)
- `planner/management/commands/run_monitor.py` — Local agent management command

### Research
- `.planning/research/STACK.md` — Technology recommendations (pysnmp for SNMP polling)
- `.planning/research/PITFALLS.md` — Known pitfalls including pysnmp build on macOS arm64

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DiscoveredDevice` model already has `domain` field with `switch` choice — devices can be assigned to Switch domain
- Dashboard template already has a Switch domain section with Phase 2 placeholder (line 1160-1211 in network_monitor.html)
- Domain rollup pills already compute switch counts (`domains.switch.online/total`)
- Device reassign API (`/api/reassign-device/`) already supports changing domain to `switch`
- SSE event push infrastructure from Phase 1 — reusable for SNMP poll results

### Established Patterns
- Agent-based architecture: local `run_monitor` command polls devices, pushes results to Django via HTTP API
- AJAX polling every 3 seconds refreshes device status on dashboard (not SSE for status — SSE for events)
- Device cards use `nhm-card` CSS class with status dot coloring
- Domain sections use collapsible `nhm-domain` containers

### Integration Points
- New SNMP polling logic in `run_monitor` command (or a parallel SNMP polling thread)
- New API endpoints for SNMP-specific data (port status, bandwidth)
- New model(s) for switch port data and SNMP credentials
- Extend `DiscoveredDevice.as_status_dict()` to include port summary for switch-domain devices
- Settings gear + panel added to dashboard header
- Show mode toggle added to dashboard header
- Show mode state stored per MonitorSession or per Project

</code_context>

<specifics>
## Specific Ideas

- On some show networks the switches are DHCP servers, so they'll naturally appear in the ping sweep scan. The dual discovery approach (auto-detect from scan + manual IP entry) handles both cases.
- Target switch brands are Luminex, Netgear, and Ubiquiti — all well-supported by SNMP v2c with standard MIBs (IF-MIB for port status/speed/bandwidth, IF-MIB counters for errors).
- The expandable switch card pattern mirrors Phase 1's click-to-expand device cards but with a table instead of simple details.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-switch-snmp*
*Context gathered: 2026-04-24*
