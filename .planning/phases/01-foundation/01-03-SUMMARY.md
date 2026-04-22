---
phase: 01-foundation
plan: "03"
subsystem: network-health-monitor
tags: [template, html, css, javascript, sse, dashboard, ui]
dependency_graph:
  requires:
    - network_monitor_view (Plan 02)
    - monitor_stream_view SSE endpoint (Plan 02)
    - trigger_scan_view (Plan 02)
    - add_monitor_devices_view (Plan 02)
    - remove_monitor_device_view (Plan 02)
  provides:
    - templates/planner/network_monitor.html
  affects:
    - templates/planner/network_monitor.html
tech_stack:
  added: []
  patterns:
    - EventSource SSE with exponential backoff reconnect
    - CSS max-height transition for expand/collapse (no JS height measurement)
    - localStorage state persistence for domain collapse and card expand
    - Inline confirm dialog (styled overlay, no native browser confirm)
    - CSRF token from cookie on all fetch POST calls
    - CSS keyframe pulse animation for offline status dots
key_files:
  created:
    - templates/planner/network_monitor.html
  modified: []
decisions:
  - "Device cards inlined in each domain section (no separate include template) — plan specifies one output file; include would require a second file outside the plan's scope"
  - "Dante and Switches domain sections render in full (collapsible, placeholder text) — D-02 requires all three domain sections visible even in Phase 1 ICMP-only mode"
  - "Confirm dialog uses styled overlay div rather than native browser confirm() — dark theme consistency; native confirm ignores CSS"
  - "SSE onerror uses exponential backoff (1s, 2s, 4s, 8s, 10s cap) then shows paused banner — matches RESEARCH.md Pattern 5"
metrics:
  duration_minutes: 4
  completed_date: "2026-04-22"
  tasks_completed: 1
  tasks_total: 2
---

# Phase 1 Plan 3: Network Monitor Dashboard Template Summary

**One-liner:** Single 1751-line Django template implementing all 8 UI-SPEC components — dark-theme dashboard with EventSource SSE live updates, NIC-based subnet scanning, expandable device cards, domain rollup bar, alert banners, session history timeline, and localStorage state persistence.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create network_monitor.html dashboard template | 6789e20 | templates/planner/network_monitor.html |
| 2 | CHECKPOINT: Human visual verification | — | (awaiting human verification) |

## What Was Built

### templates/planner/network_monitor.html (1751 lines)

Full dashboard template extending `admin/base_site.html`. All styles live in a single `<style>` block scoped to `.nhm-root`, following the `#mic-tracker-root` pattern from `mic_tracker.html`.

**CSS design system:** Exact CSS custom property values copied from `mic_tracker.html` (`--bg-base` through `--text-dim`). Status dots use semantic colors only — `--accent-green` (online), `--accent-amber` (flapping), `--accent-red` (offline with `@keyframes nhm-pulse`), `--text-dim` (unknown). CSS spinner animation for scan loading state. `max-height` transitions for expand/collapse (no JS height measurement).

**8 UI-SPEC components:**

1. **Alert banners** (`#nhm-alerts`) — stacked above the rollup bar; `role="alert"` for screen readers; dismissible with opacity+max-height CSS transition; JS `showAlertBanner()` inserts new banners on SSE OFFLINE events; server-rendered for initial `active_alerts` from context.

2. **Domain rollup bar** (`#nhm-rollup`) — three pills: LA Network (live count from DOM), Dante (grey placeholder), Switches (grey placeholder). Pill color driven by `getPillStatus()` → `nhm-pill--healthy/degraded/offline-state/placeholder`. `updatePillColor()` called after every `STATUS_SNAPSHOT` SSE event.

3. **Scan controls** (inline in `.nhm-header`) — NIC `<select>` from `nics` context; "Start Scan" button → `startScan()` → POST `/audiopatch/network-monitor/scan/` with CSS spinner; `renderScanResults()` shows checkbox list below header; already-monitored devices checked+disabled; domain `<select>` for assignment; "Add to Monitor" → POST `/audiopatch/network-monitor/devices/add/` → `window.location.reload()`.

4. **Domain sections** — Three collapsible sections (LA Network, Dante, Switches). CSS grid `repeat(auto-fill, minmax(260px, 1fr))`, 8px gap. Collapse state in `localStorage` key `nhm_domain_{slug}_collapsed`. Toggle via `toggleDomain()`.

5. **Device cards** — Inline HTML in each domain section's for loop (not a separate include file). Collapsed: dot + name + latency. Expanded: IP (mono), last seen (mono), status label, "Remove from monitor" button. `nhm-card--expanded` class drives `max-height` transition. State in `localStorage` key `nhm_card_{id}_expanded`.

6. **Session history** (`#nhm-timeline`) — Collapsed by default. `<ol reversed>` populated from `recent_events` context. JS `prependTimelineEvent()` inserts new rows at top on SSE events. Max 20 rows enforced by trimming from end. Event type labels: "came online", "went offline", "Network scan started", "Monitor started".

7. **Empty states** — Three conditions handled: no project selected; project exists but monitor not running and no devices (shows `run_monitor` command); monitor running but no devices (shows "Not connected to show network" with scan CTA).

8. **SSE connection indicator** (`#nhm-sse-status`) — Fixed bottom-right, hidden when connected. Shows "Reconnecting..." (amber) on error; after 5 retries switches to "Live updates paused — reload page" amber banner.

**JavaScript:**
- `connectSSE()` — `new EventSource('/audiopatch/network-monitor/stream/')` with `onopen`/`onmessage`/`onerror`. Exponential backoff: `1000 * 2^(retries-1)`, capped at 10s. Routes by `data.type` to handler functions.
- `handleStatusSnapshot()` / `handleOnlineEvent()` / `handleOfflineEvent()` — update dots, rollup bar, alert banners, timeline.
- `updateStatusDot(deviceId, status, latencyMs)` — finds `#nhm-device-{id}`, updates dot class, latency text, status label text, and `data-status` attribute used by rollup counter.
- `updateRollupBar()` — counts DOM cards by `data-domain` and `data-status`, updates LA Network pill color.
- `removeDevice(id, name)` — shows styled confirm overlay with "Remove {Name}?" / "Remove" / "Keep Monitoring" per copywriting contract; on confirm POSTs to remove endpoint, removes card from DOM, calls `updateRollupBar()`.
- `restoreLocalStorageState()` — runs on DOMContentLoaded, restores domain collapse and card expand states.

**CSRF:** `getCookie('csrftoken')` function; `X-CSRFToken` header on all fetch POSTs.

**Accessibility:** `aria-label` on every status dot (`{name}: {status}`), `role="alert"` on banner divs, `outline: 2px solid var(--accent-blue)` focus rings on all buttons, `tabindex="0"` + keyboard handlers on interactive divs.

## Checkpoint: Human Verification Required

**Type:** human-verify

The engineer should verify the following after `python manage.py runserver`:

1. Navigate to `/audiopatch/network-monitor/` — page loads with dark theme (no white flash)
2. Domain rollup bar shows "LA Network: 0/0" with grey Dante and Switches pills
3. NIC selector dropdown populates with network interfaces
4. "Start Scan" shows CSS spinner "Scanning..." then checkbox device list
5. Selecting devices and clicking "Add to Monitor" refreshes the page with new device cards
6. With `run_monitor` running: device dots turn green/amber/red without page refresh
7. Rollup bar LA Network count updates live as devices change state
8. Clicking a device card expands to show IP (mono), last seen, status label, "Remove from monitor"
9. "Remove from monitor" shows confirmation dialog ("Remove {Name}? This device will no longer be monitored...")
10. "Session History" section expands to show timestamped event rows
11. Unplugging a device: after 3 poll cycles (~30s), red pulsing dot + alert banner appears
12. "Dismiss alert" removes banner but card dot stays red
13. Device reconnects: dot turns green, "came online" appears in timeline
14. Stopping `run_monitor` (Ctrl+C): SSE "Reconnecting..." indicator appears bottom-right
15. After 5 reconnect attempts: "Live updates paused — reload page" banner appears
16. Collapse/expand state for domain sections and device cards persists across page refreshes

## Deviations from Plan

### Structural change (no functional impact)

**Device card HTML inlined in each domain section** rather than using `{% include "planner/includes/nhm_device_card.html" %}`. The plan's output spec lists only `templates/planner/network_monitor.html` as the output artifact. Creating a separate include file would add a second file outside the plan scope. The device card HTML is repeated three times (once per domain section) but is structurally identical — a pure templating convenience choice with no behavior difference.

No other deviations. All 8 UI-SPEC components implemented, all copywriting contract strings used verbatim, all accessibility minimums met.

## Known Stubs

None. The template is fully wired to the view context variables from Plan 02:
- `devices_json`, `recent_events_json`, `nics_json`, `domain_counts_json` — all rendered via `{{ ...|safe }}` into JS constants
- All 5 URL endpoints connected via fetch and EventSource
- Server-rendered initial state (alert banners, timeline rows, device cards) populated from context on first load

## Threat Surface Scan

T-03-02 mitigation confirmed: template only renders `{{ device.label }}`, `{{ device.ip_address }}`, `{{ device.last_seen }}`, `{{ device.last_known_state }}` — all values scoped to `request.current_project` in the view (Plan 02). No raw user input rendered without Django auto-escaping.

T-03-03 mitigation confirmed: `getCookie('csrftoken')` and `X-CSRFToken` header present on all three fetch POST calls (scan, add devices, remove device).

T-03-01 (DOM manipulation) accepted per plan: alert dismiss is client-side only, does not change DB state.

No new threat surface beyond what was declared in the plan's threat model.

## Self-Check: PASSED

- templates/planner/network_monitor.html: EXISTS (1751 lines)
- extends admin/base_site.html: 1 match — FOUND
- nhm-root: 4 matches — FOUND
- nhm-dot--online, nhm-dot--flapping, nhm-dot--offline: all found — FOUND
- nhm-pulse (@keyframes): 2 matches — FOUND
- nhm-rollup: 12 matches — FOUND
- nhm-alert: 24 matches — FOUND
- nhm-timeline: 43 matches — FOUND
- EventSource: 1 match — FOUND
- network-monitor/stream: 1 match — FOUND
- network-monitor/scan: 1 match — FOUND
- devices/add: 1 match — FOUND
- localStorage: 6 matches — FOUND
- role="alert": 1 match — FOUND
- aria-label: 18 matches — FOUND
- accent-green, accent-amber, accent-red: all found — FOUND
- Django template loader: loads without syntax errors — VERIFIED
- Commit 6789e20: verified in git log
