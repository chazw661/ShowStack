---
phase: 02-switch-snmp
verified: 2026-04-25T19:46:14Z
status: human_needed
score: 5/5
overrides_applied: 0
gaps: []
human_verification:
  - test: "Open the Network Monitor dashboard and verify switch cards render with per-port tables"
    expected: "Each switch device card shows a port summary when collapsed, and expands to reveal a table with #, Status (dot), Speed, Bandwidth columns"
    why_human: "UI rendering, layout, and visual correctness cannot be verified programmatically"
  - test: "Click gear icon, enter community string, save; add a switch IP via Add Device bar"
    expected: "Settings panel slides open, community string saves with green flash on gear icon, switch appears in device list"
    why_human: "Visual feedback (panel animation, flash) and form UX require human observation"
  - test: "Toggle show mode through Setup / Show / Wrap"
    expected: "Setup and Wrap show amber banner 'X mode -- non-critical alerts suppressed'; Show hides banner; mode persists after page refresh"
    why_human: "Visual state changes, banner appearance, and localStorage persistence need human confirmation"
  - test: "With monitor agent running against a real switch, verify bandwidth color-coding"
    expected: "Bandwidth % is green below 70%, amber 70-90%, red above 90%"
    why_human: "Requires real SNMP data flowing through the system to verify color thresholds visually"
---

# Phase 2: Switch SNMP Verification Report

**Phase Goal:** Engineer can monitor switch port status, link speed, and bandwidth utilization via SNMP, and suppress non-critical alerts during load-in and load-out
**Verified:** 2026-04-25T19:46:14Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

Truths are derived from ROADMAP Success Criteria for Phase 2 and merged with PLAN frontmatter must-haves.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Each configured switch shows per-port up/down status and link speed on the dashboard | VERIFIED | `monitor_status_view` returns `switch_ports` dict keyed by device PK with `oper_status`, `speed_mbps` per port (views_monitor.py:172-186). Template `updateSwitchCards()` renders port table with status dots and speed column (network_monitor.html:2400+). |
| 2 | Engineer can enter SNMP credentials (v2c community string) per project and have them persist | VERIFIED | `ProjectSNMPConfig` model with `OneToOneField` to Project (models.py:4680). `dashboard_snmp_settings` endpoint saves community string (views_monitor.py:643). Settings panel in template with `saveSettings()` JS function (network_monitor.html:2365). D-03 explicitly defers v3 to future work. |
| 3 | Port error counters accumulate over time and are visible per port | VERIFIED | `SwitchPortSnapshot.error_count` field (models.py:4716). Agent pushes `error_count` per port from IF-MIB `ifInErrors` (run_monitor.py IF_MIB_ROOTS). Error count shown in port row tooltip: `row.title = 'Errors: ' + (p.error_count || 0)` (network_monitor.html:2454). |
| 4 | A bandwidth warning indicator appears on a port when utilization exceeds threshold (default 70%/90%) | VERIFIED | Server-side: `BW_WARNING` event at >70%, `BW_CRITICAL` at >90% (views_monitor.py:623-636). Agent: `_compute_bandwidth_pct` computes RFC 2863 bandwidth from counter deltas (run_monitor.py:130). Template: `nhm-bw--ok/warn/crit` CSS classes applied at 70/90 thresholds (network_monitor.html:2468-2470). |
| 5 | Show mode toggle (Setup/Show/Wrap) suppresses non-critical alerts when set to Setup or Wrap | VERIFIED | `MonitorSession.show_mode` field with setup/show/wrap choices (models.py:4557). Server suppression: `suppress_non_critical = session.show_mode in ('setup', 'wrap')` gates PORT_UP/DOWN/BW events (views_monitor.py:570,614). UI toggle with amber banner (network_monitor.html:1254-1267). `dashboard_set_show_mode` endpoint (views_monitor.py:701). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `planner/models.py` | ProjectSNMPConfig, SwitchPortSnapshot, MonitorSession.show_mode | VERIFIED | All three model additions present at lines 4557, 4680, 4696 |
| `planner/views_monitor.py` | 5 new endpoints + extended monitor_status_view | VERIFIED | agent_snmp_settings (524), agent_snmp_results (553), dashboard_snmp_settings (643), dashboard_add_switch (664), dashboard_set_show_mode (701). monitor_status_view returns show_mode (171) and switch_ports (172). |
| `planner/urls.py` | 5 new URL patterns | VERIFIED | All 5 paths registered at lines 268-274 |
| `planner/admin.py` | Admin registration for both new models | VERIFIED | ProjectSNMPConfigAdmin (6012), SwitchPortSnapshotAdmin (6018), both registered on showstack_admin_site (6030-6031) |
| `planner/admin_ordering.py` | Sidebar ordering + child_models | VERIFIED | projectsnmpconfig=40, switchportsnapshot=41 (lines 149-150); switchportsnapshot in child_models (line 68) |
| `planner/management/commands/run_monitor.py` | Dual-thread agent with SNMP polling | VERIFIED | ICMPPoller + SNMPPoller daemon threads (lines 235-243), stop_event pattern, walk_cmd with IF_MIB_ROOTS, _compute_bandwidth_pct |
| `requirements.txt` | pysnmp dependency | VERIFIED | `pysnmp>=7.1,<8.0` at line 24 |
| `planner/migrations/0150_monitorsession_show_mode_and_more.py` | Migration for new models + field | VERIFIED | File exists |
| `templates/planner/network_monitor.html` | Settings panel, show mode toggle, switch cards, port tables | VERIFIED | nhm-settings-panel (1593), nhm-mode-toggle (1254), updateSwitchCards (2400), nhm-bw--ok/warn/crit (1129-1131) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| views_monitor.py | models.py | ORM queries on ProjectSNMPConfig | WIRED | `ProjectSNMPConfig.objects.get(project=project)` in agent_snmp_settings; `update_or_create` in agent_snmp_results |
| urls.py | views_monitor.py | path() wiring | WIRED | All 5 new paths reference views_monitor functions at lines 268-274 |
| views_monitor.py agent_snmp_results | show_mode suppression | suppress_non_critical flag | WIRED | `suppress_non_critical = session.show_mode in ('setup', 'wrap')` at line 570, gates event creation at line 614 |
| run_monitor.py _snmp_loop | /api/snmp-settings/ | HTTP GET via _fetch_snmp_settings | WIRED | `_fetch_snmp_settings` calls `base_url + '/snmp-settings/'` at line 322/404 |
| run_monitor.py _snmp_loop | /api/snmp-results/ | HTTP POST via _push_snmp_results | WIRED | `_push_snmp_results` calls `base_url + '/snmp-results/'` at line 397/415 |
| run_monitor.py _snmp_loop | pysnmp walk_cmd | asyncio.run from daemon thread | WIRED | `asyncio.run(_async_poll_all_switches(...))` at line 335; walk_cmd import at line 34 |
| template JS | /snmp-settings/ | fetch POST with CSRF | WIRED | `saveSettings()` POSTs to `/audiopatch/network-monitor/snmp-settings/` at line 2374 |
| template JS | /show-mode/ | fetch POST with CSRF | WIRED | `setShowMode()` POSTs to `/audiopatch/network-monitor/show-mode/` at line 2317 |
| template JS pollStatus() | switch_ports data | AJAX consumption | WIRED | `data.switch_ports` consumed at line 1671, passed to `updateSwitchCards()` at line 1672 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| network_monitor.html | switch_ports | monitor_status_view -> SwitchPortSnapshot.objects.filter(session=session) | Yes -- ORM query on SwitchPortSnapshot table, populated by agent_snmp_results | FLOWING |
| network_monitor.html | show_mode | monitor_status_view -> session.show_mode | Yes -- reads from MonitorSession field | FLOWING |
| network_monitor.html | snmp_configured | monitor_status_view -> ProjectSNMPConfig.objects.filter().exists() | Yes -- ORM existence check | FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED (requires running server + SNMP agent against real switch hardware; no runnable entry points for static verification)

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SW-01 | 01, 02, 03 | Switch port up/down status and link speed displayed via SNMP polling | SATISFIED | SwitchPortSnapshot stores oper_status + speed_mbps; agent polls via IF-MIB; template renders port table with status dots and speed column |
| SW-02 | 01 | Per-project SNMP credential configuration (community string for v2c) | SATISFIED | ProjectSNMPConfig OneToOneField to Project; dashboard_snmp_settings endpoint; settings panel UI. v3 auth/priv explicitly deferred per D-03 |
| SW-03 | 01, 02 | Port error counter tracking over time | SATISFIED | SwitchPortSnapshot.error_count field; agent reads ifInErrors via SNMP; visible in port row tooltip |
| SW-04 | 01, 02, 03 | Bandwidth utilization warnings at 70%/90% thresholds | SATISFIED | Agent computes bandwidth via _compute_bandwidth_pct (RFC 2863); server fires BW_WARNING/BW_CRITICAL events; template color-codes green/amber/red |
| DASH-04 | 01, 03 | Show mode toggle suppresses non-critical alerts during load-in/out | SATISFIED | MonitorSession.show_mode field; suppress_non_critical flag in agent_snmp_results; UI toggle with amber banner |

No orphaned requirements found -- all 5 requirement IDs from REQUIREMENTS.md Phase 2 mapping (SW-01, SW-02, SW-03, SW-04, DASH-04) are covered.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| templates/planner/network_monitor.html | 1368 | "Dante section (Phase 2 placeholder)" comment | Info | Expected -- Dante is Phase 3 scope |
| templates/planner/network_monitor.html | 1425 | "Switches section (Phase 2 placeholder)" comment | Info | Misleading comment label (section now has real switch cards); cosmetic only |

No blockers or warnings found. All "placeholder" grep hits are CSS class names (`nhm-pill--placeholder` for unknown-state styling), HTML `placeholder` attributes on input fields, or Phase 3 Dante section comments -- none are stub implementations.

### Human Verification Required

### 1. Switch Card Port Table Rendering

**Test:** Open Network Monitor dashboard with a switch device present. Verify switch cards show port summary when collapsed and expand to per-port table.
**Expected:** Collapsed card shows "N ports -- M up -- K err". Expanded card shows table with #, Status (colored dot), Speed (1G/100M/etc), Bandwidth (color-coded %).
**Why human:** Visual rendering of dynamic DOM-constructed table cannot be verified programmatically.

### 2. Settings Panel Interaction

**Test:** Click gear icon in header. Enter community string. Click Save Settings.
**Expected:** Panel slides in from right with backdrop overlay. Save closes panel with brief green flash on gear icon. Escape key also closes panel.
**Why human:** Panel animation, backdrop overlay, and visual feedback require human observation.

### 3. Show Mode Toggle and Banner

**Test:** Click Setup, Show, Wrap buttons in rollup bar. Observe banner behavior and mode persistence.
**Expected:** Setup/Wrap activate amber styling and show amber banner "X mode -- non-critical alerts suppressed". Show activates green styling and hides banner. Mode persists after page refresh (localStorage + server sync).
**Why human:** Visual state transitions, color changes, and persistence across refresh need human verification.

### 4. Bandwidth Color-Coding with Live Data

**Test:** Run monitor agent against a real switch. Observe bandwidth values in port table.
**Expected:** Green text below 70%, amber 70-90%, red above 90%. Screen reader text "(ok)", "(warning)", "(critical)" present.
**Why human:** Requires real SNMP data flowing through the full pipeline; cannot be tested statically.

### Gaps Summary

No blocking gaps found. All 5 ROADMAP Success Criteria are satisfied by the implementation. The SNMP v3 auth/priv mentioned in the ROADMAP SC wording ("v2c community string or v3 auth/priv") is explicitly deferred per design decision D-03 -- the implementation correctly supports v2c which covers the target switch brands (Luminex, Netgear, Ubiquiti). This is a scope reduction decision, not a missing feature.

All three plans (01: backend, 02: agent, 03: UI) are fully executed with complete wiring between layers. The data pipeline flows from SNMP switches through the agent (pysnmp walk_cmd), to Django API endpoints, to SwitchPortSnapshot storage, through monitor_status_view JSON, and into the template's updateSwitchCards() rendering function.

Plan 03 has one deviation: manual switch entry was removed from the settings panel per user feedback (switches are added via the existing Add Device bar). This is documented in the 02-03-SUMMARY.md and does not affect goal achievement -- the capability exists, just through a different UI path.

---

_Verified: 2026-04-25T19:46:14Z_
_Verifier: Claude (gsd-verifier)_
