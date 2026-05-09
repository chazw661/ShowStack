# Phase 2: Switch SNMP - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 02-switch-snmp
**Areas discussed:** SNMP credentials, Switch port display, Show mode toggle, Bandwidth warnings

---

## SNMP Credentials

| Option | Description | Selected |
|--------|-------------|----------|
| Dashboard inline | Settings/config panel accessible from the network monitor dashboard | ✓ |
| Django admin panel | SNMP credentials managed via the ShowStack admin | |
| Both | Primary entry via dashboard, also viewable/editable in admin | |

**User's choice:** Dashboard inline
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| Per-project | One community string for the whole project | ✓ |
| Per-switch | Each switch gets its own credentials | |
| Per-project with per-switch override | Default credentials at project level with optional override | |

**User's choice:** Per-project
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| v2c only | Community string only — covers majority of entertainment switches | ✓ |
| v2c and v3 | Support both from day one | |
| v2c now, v3 later | Ship v2c, add v3 as follow-up | |

**User's choice:** v2c — targeting Luminex, Netgear, and Ubiquiti entertainment switches
**Notes:** User specifically called out Ubiquiti support alongside Netgear and Luminex. All three brands support SNMP v2c.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Settings gear in header | Gear icon opens settings panel/modal | ✓ |
| Inline on first switch scan | Prompt for credentials when switches first found | |
| Dedicated config section | Always-visible SNMP Config section on dashboard | |

**User's choice:** Settings gear in header
**Notes:** None

---

## Switch Port Display

| Option | Description | Selected |
|--------|-------------|----------|
| Expandable switch card | Collapsed shows summary, click to expand per-port table | ✓ |
| Always-visible port grid | Compact grid of colored dots like a physical switch face plate | |
| Full port table always shown | Full table always visible, no collapsing | |

**User's choice:** Expandable switch card
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| Status + Speed + BW% | Port number, status dot, link speed, bandwidth %. Errors on click/hover. | ✓ |
| Status + Speed + BW% + Errors | All above plus inline error counter columns | |
| Status + Speed only | Minimal — bandwidth and errors via separate detail view | |

**User's choice:** Status + Speed + BW%
**Notes:** Error counters accessible as secondary detail (click/hover), not inline.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Manual IP entry | Engineer types switch IPs into settings panel | |
| Auto-discover from scan | Ping sweep devices assigned to Switch domain get SNMP-polled | |
| Both | Auto-detect from scan AND manual IP entry | ✓ |

**User's choice:** Both — auto-detect plus manual entry
**Notes:** User noted that on some show networks switches are DHCP servers so they naturally appear in scan. Unassigned devices stay in their own category until reassigned.

---

## Show Mode Toggle

| Option | Description | Selected |
|--------|-------------|----------|
| Dashboard header bar | Prominent toggle in top header, always visible | ✓ |
| Settings panel (gear icon) | Inside settings panel — less prominent | |
| Floating/sticky widget | Small floating pill in corner | |

**User's choice:** Dashboard header bar
**Notes:** None

---

| Option | Description | Selected |
|--------|-------------|----------|
| Only device-offline is critical | Device offline (N=3) always fires. Everything else suppressed in Setup/Wrap. | ✓ |
| Device-offline + bandwidth critical | Both device-offline AND bandwidth threshold always fire | |
| Nothing suppressed in Setup | Only Wrap mode suppresses | |

**User's choice:** Only device-offline is critical
**Notes:** Port status changes, bandwidth warnings, error counter spikes, and link speed changes are all non-critical.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Subtle banner | Amber banner below header: "Setup mode — non-critical alerts suppressed" | ✓ |
| No visual change | Just the toggle state itself | |
| Color theme shift | Header/border color changes per mode | |

**User's choice:** Subtle banner
**Notes:** Banner disappears when mode set to Show.

---

## Bandwidth Warnings

| Option | Description | Selected |
|--------|-------------|----------|
| Percentage with color coding | BW% colored green/amber/red at thresholds | ✓ |
| Mini progress bar | Horizontal bar per port, color shifts at thresholds | |
| Percentage text only | Plain number, warnings only as alert events | |

**User's choice:** Percentage with color coding
**Notes:** Green <70%, amber 70-90%, red >90%.

---

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed defaults, not configurable | 70% amber, 90% red — hardcoded | ✓ |
| Configurable per-project | Custom thresholds in settings panel | |
| Configurable per-port | Individual port thresholds | |

**User's choice:** Fixed defaults, not configurable
**Notes:** Standard network monitoring thresholds. Can add configurability later if requested.

---

## Claude's Discretion

- Settings panel layout and styling
- Error counter detail display format
- SNMP polling interval
- Manual switch IP entry UI design
- Show mode toggle visual design (segmented control, radio buttons, etc.)

## Deferred Ideas

None — discussion stayed within phase scope
