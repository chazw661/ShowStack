---
phase: 03-dante
plan: "03"
subsystem: network-health-monitor
tags: [dante, ui, clock-badges, ghost-cards, health-check, dashboard]
dependency_graph:
  requires: [03-01, 03-02]
  provides: [dante-dashboard-ui, dante-clock-badges, ghost-cards, health-check-panel, dante-rollup-pill]
  affects: [templates/planner/network_monitor.html]
tech_stack:
  added: []
  patterns: [ajax-poll-update, css-class-swap, dynamic-dom-creation, escapeHtml-xss-guard, setProperty-important-override]
key_files:
  created: []
  modified:
    - templates/planner/network_monitor.html
decisions:
  - "escapeHtml() helper used for all dynamically-inserted device names to satisfy T-03-08 XSS mitigation"
  - "Advisory footnote hidden via JS (display:none initially, shown when dante devices present) — not dismissible per D-05/advisory-honesty principle"
  - "Health check panel hidden until Dante data arrives to avoid empty panel flash on page load"
  - "Ghost cards re-rendered on every runHealthCheck() call — simpler than diffing missing list"
  - "healthCheckManualOverride flag prevents auto-expand from fighting user's manual toggle"
  - "setTimeout(runHealthCheck, 1000) gives first poll cycle time to populate device data before health check fires"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-25T22:09:10Z"
  tasks_completed: 2
  tasks_total: 3
  note: "Task 3 is checkpoint:human-verify — paused awaiting visual verification"
---

# Phase 3 Plan 03: Dante Dashboard UI Summary

Dante dashboard UI built on top of Plans 01 and 02: live device cards with clock role badges (MASTER/LOCKED/UNLOCKED/UNKNOWN), channel count display, ghost cards for missing project devices, advisory footnote, collapsible health check panel with auto-expand on issues, and live rollup pill counts replacing the Phase 2 placeholder.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add Dante CSS classes and replace placeholder HTML | 8f26126 | templates/planner/network_monitor.html |
| 2 | Add Dante JS functions for AJAX poll, health check, and ghost cards | 99353a8 | templates/planner/network_monitor.html |

## Task 3 Status

**Paused at checkpoint:human-verify** — awaiting visual verification of the Dante dashboard UI.

## What Was Built

### Task 1 — CSS + HTML

**New CSS classes added** (appended to existing `<style>` block, scoped to `.nhm-root`):
- `nhm-clock-badge` + `--master` / `--locked` / `--unlocked` / `--unknown` — inline badge variants per UI-SPEC status indicator contract
- `nhm-card-channels` — mono 12px channel count display
- `nhm-card--ghost` / `.nhm-card--ghost .nhm-card-expand-arrow` — dimmed 45% opacity, pointer-events:none, hidden expand arrow
- `nhm-dante-advisory` — 14px advisory footnote with top/bottom border
- `nhm-healthcheck`, `nhm-healthcheck-header`, `nhm-healthcheck-body` (with `--expanded` max-height transition), `nhm-healthcheck-title`, `nhm-healthcheck-icon` (with `--ok` / `--issues`)
- `nhm-healthcheck-summary`, `nhm-healthcheck-summary--ok`
- `nhm-hc-row`, `nhm-hc-dot`, `nhm-hc-dot--missing`, `nhm-hc-dot--unexpected`, `nhm-hc-name`, `nhm-hc-desc`
- `nhm-btn--recheck` — 28px ghost button for re-check action

**HTML replacement:** Phase 2 Dante placeholder replaced with full Phase 3 section:
- Advisory footnote (`role="note"`, `display:none` initially)
- Health check panel (`display:none` initially) with header row: icon + title + re-check button + toggle arrow
- Card grid with Django template loop for `domain='dante'` devices — each card has clock badge + channel count in header, Clock/Channels detail rows in expanded view
- Empty state message for when agent is not running

### Task 2 — JavaScript

**`updateDanteCards(danteData, devices)`** — called from `pollStatus()` on every 2s poll when `data.dante_data` is present:
- Shows/hides advisory, health check panel, and empty message based on whether Dante devices exist
- Updates clock badge class + text + aria-label from `dd.clock_role`
- Updates channel count (collapsed `32x24` format) and detail row (`TX: 32 / RX: 24` format)
- Colors clock detail text to match badge (green for master/locked, amber for unlocked, dim for unknown)
- Removes cards for devices that left the Dante domain

**`createDanteCard(dev, dd)`** — dynamically creates a Dante card element when a new device arrives mid-session (not in initial server-rendered HTML)

**`runHealthCheck()`** — fetches `GET /audiopatch/network-monitor/api/health-check/`:
- Disables re-check button during request, shows "Checking..."
- Calls `renderHealthCheckResults()` and `renderGhostCards()` on success
- Auto-expands/collapses panel based on status, respecting `healthCheckManualOverride`

**`renderHealthCheckResults(data)`** — populates health check panel:
- All-clear: green "All N Dante devices present."
- Issues: rows for missing (red dot) and unexpected (amber dot) devices, each with `escapeHtml()` for XSS safety

**`toggleHealthCheck()` / `expandHealthCheck(expand)`** — collapsible panel with aria-expanded and arrow toggle

**`escapeHtml(text)`** — XSS-safe helper via `createTextNode` (satisfies T-03-08)

**`renderGhostCards(missingNames)`** — inserts dimmed ghost cards at end of Dante grid for missing project devices; clears and re-renders on each health check

**pollStatus wiring:** `dante_data` branch added after `switch_ports` branch

**updateRollupBar additions:**
- Dante pill placeholder class removed when `total > 0`
- Domain badge (`nhm-badge-dante`) updated with `online/total` live count

**DOMContentLoaded:** `setTimeout(runHealthCheck, 1000)` auto-runs health check 1s after page load

## Deviations from Plan

None — plan executed exactly as written. All must_have truths satisfied by the implementation.

## Known Stubs

None. All data flows from live API endpoints (poll + health-check) implemented in Plans 01 and 02. No hardcoded placeholder values render in the UI. Advisory footnote is intentionally static copy, not stub data.

## Threat Flags

No new threat surface beyond plan's threat model. T-03-08 (XSS via device names) is fully mitigated: `escapeHtml()` used in all dynamic card creation paths (`createDanteCard`, `renderGhostCards`, `renderHealthCheckResults`). Django template auto-escaping covers server-rendered cards.

## Self-Check: PASSED

- `templates/planner/network_monitor.html`: FOUND
- CSS classes confirmed: `nhm-clock-badge`, `nhm-card--ghost`, `nhm-dante-advisory`, `nhm-healthcheck`, `nhm-hc-dot--missing` — all present
- JS functions confirmed: `updateDanteCards`, `createDanteCard`, `runHealthCheck`, `renderHealthCheckResults`, `renderGhostCards`, `toggleHealthCheck`, `expandHealthCheck` — all present
- `health-check` URL reference confirmed present
- `python manage.py check` passes (0 issues)
- Commit `8f26126`: FOUND
- Commit `99353a8`: FOUND
