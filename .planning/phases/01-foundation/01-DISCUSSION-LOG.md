# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-22
**Phase:** 01-foundation
**Areas discussed:** Dashboard layout, Device discovery

---

## Dashboard Layout

| Option | Description | Selected |
|--------|-------------|----------|
| Grouped by domain | Sections for Dante, LA Network, Switches — each with device cards inside | ✓ |
| Grouped by location | Sections by Location (Stage Left, FOH, etc.) — matches existing Location model | |
| Single flat list | All devices in one view with color-coded badges for network type | |
| You decide | Claude picks the best approach | |

**User's choice:** Grouped by domain
**Notes:** Matches how an A1 thinks about show networks.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal | Device name + green/yellow/red dot. Click to expand. | ✓ |
| Info-dense | Name, IP, status, latency, last-seen all visible | |
| Hybrid | Name + dot normally. Hover shows details. | |

**User's choice:** Minimal
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone page | Own URL at /audiopatch/network-monitor/ | ✓ |
| Admin changelist | Registered on showstack_admin_site | |
| Both | Admin for config, standalone for live dashboard | |

**User's choice:** Standalone page
**Notes:** Consistent with other ShowStack modules (mic-tracker, comm-config).

---

| Option | Description | Selected |
|--------|-------------|----------|
| Domain rollup bar | Top bar: Dante 12/12 ✅ LA Network 8/8 ✅ Switches 3/3 ✅ | ✓ |
| Alert count only | Top bar shows only active alert count | |
| You decide | Claude picks | |

**User's choice:** Domain rollup bar
**Notes:** None

---

## Device Discovery

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-import all | Poll every project device with an IP | |
| Selective import | Engineer picks which devices to monitor | |
| Auto + override | Auto-import, engineer can disable/add manual IPs | |

**User's choice:** Other — "Discover devices on network. Disregard what devices are in the project in other modules. We will need a way to select a network adapter per device type."
**Notes:** Major shift from original plan. Monitor discovers what's on the network directly, not from ShowStack project data.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Network scan | Ping sweep subnet, show everything that responds | |
| Manual IP entry | Engineer enters IPs or ranges manually | |
| Scan + filter | Scan subnet, show all, let engineer select which to keep | ✓ |

**User's choice:** Scan + filter
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| Per-domain NIC | Settings page: Dante=en0, LA Network=en1, etc. | |
| Auto-detect | Detect all active NICs, let engineer pick per scan | ✓ |
| You decide | Claude picks | |

**User's choice:** Auto-detect
**Notes:** More flexible than permanent assignment.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Monitor all IPs | Each IP is a separate target | |
| Primary only | Only monitor primary_ip_address | ✓ |
| You decide | Claude picks | |

**User's choice:** Primary only
**Notes:** None

## Claude's Discretion

- Alert presentation style (banner, toast, badge)
- Session history timeline visual design
- "Not on show network" detection and messaging approach

## Deferred Ideas

None — discussion stayed within phase scope
