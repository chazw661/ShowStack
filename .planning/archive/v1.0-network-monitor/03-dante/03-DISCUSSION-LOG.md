# Phase 3: Dante - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-25
**Phase:** 03-dante
**Areas discussed:** Discovery & Device Matching, Clock Status Display, Pre-Show Health Check, Dante Section Layout

---

## Discovery & Device Matching

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-match by name | Compare mDNS device name against project device labels. Unmatched show as "Unrecognized" | ✓ |
| Manual assignment only | All discovered devices appear, engineer manually links to project records | |
| Discovery only, no linking | Devices appear with mDNS name/IP, no connection to project records | |

**User's choice:** Auto-match by name
**Notes:** None

### Follow-up: Unmatched Dante devices

| Option | Description | Selected |
|--------|-------------|----------|
| Show in Dante section as "Unrecognized" | Appear with visual distinction in Dante cards | |
| Show in Unassigned section | Route to existing Unassigned domain section | ✓ |
| Show in both | Appear in Dante section with tag + flagged in health check | |

**User's choice:** Show in Unassigned section

### Follow-up: Missing project devices

| Option | Description | Selected |
|--------|-------------|----------|
| Ghost card in Dante section | Show card with "not discovered" state | |
| Pre-show health check only | Don't show in section, flag in health check report | |
| Both | Ghost card in section AND flagged in health check | ✓ |

**User's choice:** Both — ghost cards plus health check flag

---

## Clock Status Display

### Prominence

| Option | Description | Selected |
|--------|-------------|----------|
| Primary info | Prominent on card, same weight as status dot, advisory subtitle | ✓ |
| Secondary info | Inside expanded card detail only, clock icon hint on collapsed | |
| Badge approach | Clock master gets badge/icon, lock shown as indicator | |

**User's choice:** Primary info

### Advisory label

| Option | Description | Selected |
|--------|-------------|----------|
| Static text | Always shows "Advisory" next to clock status per card | |
| Contextual label | "Verified" when fresh, "Advisory" when stale | |
| Footnote style | Single note at top of Dante section, no per-card labels | ✓ |

**User's choice:** Footnote style — section-level note

### Multiple masters

| Option | Description | Selected |
|--------|-------------|----------|
| Single master expected | Mark one, warn if multiple | |
| Show whatever netaudio reports | Show all claimed masters, no interpretation | ✓ |

**User's choice:** Show whatever netaudio reports

---

## Pre-Show Health Check

### Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Manual button | "Run Health Check" button, engineer clicks when ready | |
| Automatic on page load | Runs every time dashboard loads | |
| Both | Auto-run on load + manual "Re-check" button | ✓ |

**User's choice:** Both — auto-run plus manual re-check

### Results display

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in Dante section | Summary bar at top: "12/14 found — 2 missing" | |
| Modal/overlay | Full results panel, dismissable | |
| Expandable panel | Collapsible panel, auto-expands on issues | ✓ |

**User's choice:** Expandable panel — auto-opens on problems

### Match criteria

| Option | Description | Selected |
|--------|-------------|----------|
| Only matched devices count | Strict project record linking required | |
| Presence is enough | Any Dante device counts, compare names loosely | ✓ |

**User's choice:** Presence-based matching

---

## Dante Section Layout

### Collapsed card info

| Option | Description | Selected |
|--------|-------------|----------|
| Name + IP + Clock | Device name, IP, clock role, status dot | |
| Name + IP + Latency | Same as LA Network cards | |
| Name + Clock + Channel Count | Device name, clock role, channel count from mDNS | ✓ |

**User's choice:** Name + Clock + Channel Count

### Ghost card appearance

| Option | Description | Selected |
|--------|-------------|----------|
| Dimmed card | Lower opacity, grey text, "unreachable" style | ✓ |
| Outlined/dashed border | Dashed border, "Not Discovered" text | |
| Red accent | Red left border or red indicator | |

**User's choice:** Dimmed card — consistent with unreachable pattern

---

## Claude's Discretion

- Health check panel layout and styling
- Channel count display format
- Clock role icon/text presentation
- Ghost card exact opacity and styling
- Re-check button placement
- Auto-match partial vs exact name handling

## Deferred Ideas

None
