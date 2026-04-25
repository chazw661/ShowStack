---
phase: 02-switch-snmp
plan: "03"
subsystem: network-health-monitor
tags: [dashboard, ui, snmp, show-mode, settings-panel]
dependency_graph:
  requires:
    - Plan 01 (models, API endpoints)
    - Plan 02 (agent SNMP polling)
  provides:
    - Settings panel with SNMP community string input
    - Show mode toggle (Setup/Show/Wrap) with amber suppression banner
    - Switch card port summary and expandable port tables
    - Bandwidth color-coding (green/amber/red at 70/90 thresholds)
    - SNMP not-configured and unreachable state prompts
    - AJAX polling consumption of show_mode and switch_ports
  affects:
    - templates/planner/network_monitor.html
tech_stack:
  added: []
  patterns:
    - Settings panel slide-out with backdrop
    - Show mode localStorage + server sync
    - Dynamic port table rendering via JS DOM manipulation
    - Bandwidth threshold color-coding (70/90)
key_files:
  created: []
  modified:
    - templates/planner/network_monitor.html
decisions:
  - "Removed manual switch entry from settings panel — switches are added via the existing Add Device bar to avoid UX duplication"
  - "Settings panel contains only SNMP community string input — focused, single-purpose"
  - "Port table uses textContent for user-provided values (XSS mitigation per T-02-11)"
  - "Show mode toggle uses aria-pressed for accessibility"
  - "Bandwidth cells include sr-only span for screen reader context"
metrics:
  duration_minutes: 15
  completed_date: "2026-04-25"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 1
  files_created: 0
---

# Phase 2 Plan 03: Dashboard UI for SNMP Switch Monitoring Summary

**One-liner:** Complete dashboard frontend — settings panel for SNMP credentials, show mode toggle with alert suppression banner, expandable switch cards with per-port tables and bandwidth color-coding.

## What Was Built

### Task 1: Phase 2 CSS
- Show mode toggle (`.nhm-mode-toggle`, `.nhm-mode-btn--active-show/amber`)
- Mode banner (`.nhm-mode-banner` with amber left border)
- Settings panel (`.nhm-settings-panel` slide-out with backdrop overlay)
- Port table (`.nhm-port-table` with alternating row backgrounds)
- Bandwidth color-coding (`.nhm-bw--ok/warn/crit` at 70/90 thresholds)
- SNMP state prompts (`.nhm-port-table--unconfigured`)
- Accessibility (`.sr-only` screen reader utility)

### Task 2: HTML + JavaScript
- Gear icon button in header with `aria-label="Open monitor settings"`
- Settings panel with SNMP community string input and Save button
- Show mode toggle (Setup/Show/Wrap) in rollup bar with `role="group"`
- Amber mode banner with `role="status"` for Setup/Wrap modes
- `setShowMode()` / `updateShowModeUI()` — toggle + localStorage + server POST
- `openSettings()` / `closeSettings()` — panel open/close with Escape key support
- `saveSettings()` — POST community string with validation and success flash
- `updateSwitchCards()` — renders port summary, port table, SNMP state prompts
- Extended `pollStatus()` — consumes `data.show_mode` and `data.switch_ports`
- Show mode initialized from server state on page load

### Task 3: Visual Verification
- Human approved all UI elements: gear icon, settings panel, show mode toggle, amber banner, switch cards

## Deviations from Plan

- **Manual switch entry removed from settings panel** — per user feedback, switches are added via the existing "Add Device" bar. Settings panel now only contains SNMP community string. This eliminated `addSwitch()`, `refreshSwitchList()`, `removeSwitch()` JS functions and associated HTML/CSS.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | bc66bae | feat(02-03): add Phase 2 CSS — show mode toggle, settings panel, port table, bandwidth colors |
| 2 | d32f26d | feat(02-03): add settings panel, show mode toggle, switch port tables, and SNMP state UI |
| 2b | 2d65712 | refactor(02-03): remove manual switch entry from settings panel |

## Known Stubs

None — all UI components are fully wired to the Plan 01 API endpoints and update via AJAX polling.

## Threat Surface Scan

- T-02-09 (CSRF): All POST fetch calls include `X-CSRFToken: csrfToken` header
- T-02-10 (Info Disclosure): Community string input not pre-populated from server
- T-02-11 (XSS): Port table uses `textContent` for user-provided values; switch list rendering uses DOM creation (not innerHTML with user data)

## Self-Check

- [x] `templates/planner/network_monitor.html` modified
- [x] Settings panel with `role="dialog"` and `aria-modal="true"`
- [x] Show mode toggle with `aria-pressed` attributes
- [x] Mode banner with `role="status"`
- [x] Bandwidth color-coding classes `.nhm-bw--ok/warn/crit`
- [x] `style.setProperty()` used for all inline style overrides (per CLAUDE.md)
- [x] All POST requests include `X-CSRFToken` header
- [x] `pollStatus()` consumes `data.show_mode` and `data.switch_ports`
- [x] `localStorage` persistence for show mode
- [x] Human visual verification: APPROVED
- [x] `python manage.py check`: 0 issues

## Self-Check: PASSED
