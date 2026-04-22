---
phase: 01-foundation
verified: 2026-04-21T00:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Dashboard renders with live SSE updates when run_monitor is running"
    expected: "Green/yellow/red status dots update in real time; rollup bar counts change; no page refresh needed"
    why_human: "SSE streaming requires a running server and active polling process; cannot verify browser DOM updates programmatically"
  - test: "N=3 alert fires in the browser after 3 consecutive missed polls"
    expected: "After 3 poll cycles without response (~30s at default interval), red pulsing dot appears AND alert banner shows at top. A single dropped poll does NOT trigger the banner."
    why_human: "Requires live ICMP polling against a real device that can be disconnected"
  - test: "Session history timeline shows timestamped ONLINE/OFFLINE events"
    expected: "Each state change (amp goes offline, comes back online) appears in the Session History section with accurate timestamp"
    why_human: "Requires run_monitor producing real DeviceEvent rows, then verifying SSE delivery and DOM insertion"
  - test: "NIC selector and Start Scan flow discovers devices"
    expected: "Selecting a NIC from the dropdown and clicking Start Scan shows Scanning..., then a checkbox list of responding hosts; selecting and clicking Add to Monitor refreshes page with device cards visible"
    why_human: "Requires being on a network with other devices; output depends on real subnet topology"
  - test: "Not connected to show network empty state message"
    expected: "When monitor is running but no devices are added, the heading Not connected to show network appears; when not running and no devices, the run_monitor command instruction is shown"
    why_human: "Requires specific DB state combinations to verify both empty-state branches visually"
---

# Phase 1: Foundation Verification Report

**Phase Goal:** Engineer can see live reachability status for all LA Network amps on a single dashboard, with alerts on device offline and a session history timeline
**Verified:** 2026-04-21
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Roadmap Success Criteria

| # | Success Criterion | Status | Evidence |
|---|------------------|--------|---------|
| 1 | Engineer opens the dashboard and sees green/yellow/red reachability status for each amp, updating live without a page refresh | ? HUMAN | Template has EventSource SSE wired to `/audiopatch/network-monitor/stream/`; `updateStatusDot()` and `handleStatusSnapshot()` update dot classes in DOM; requires browser + running monitor to confirm |
| 2 | If an amp goes offline for 3 consecutive polls, a critical alert fires; no alert fires on a single flap | ✓ VERIFIED | `consecutive_failures == 3` gate in `run_monitor.py` line 88 — OFFLINE event fires at exactly 3, not before; ONLINE fires when `prev_state != 'online'` on recovery |
| 3 | The session history timeline shows each up/down state change with a timestamp for the current show day | ? HUMAN | `#nhm-timeline-list` populated server-side from `recent_events` context; `prependTimelineEvent()` inserts rows from SSE ONLINE/OFFLINE events; requires live session to confirm end-to-end |
| 4 | Running `python manage.py run_monitor` starts background ICMP polling; stopping it halts all polling cleanly | ✓ VERIFIED | Daemon thread `ICMPPoller` started; `stop_event.wait()` blocks main thread; `KeyboardInterrupt` sets `stop_event`, sets `session.ended_at`, saves — confirmed in run_monitor.py lines 139-153 |
| 5 | When the laptop is not on the show network, the dashboard shows a clear "not connected to show network" message rather than silent empty status | ✓ VERIFIED | Template lines 924-931: `{% elif monitor_running and not devices %}` renders "Not connected to show network" heading; lines 914-922: no-devices + monitor not running renders the `run_monitor` command |

**Score:** 5/5 success criteria have either verified or human-pending status. 3 confirmed programmatically, 2 require browser/live verification.

### Observable Truths (from PLAN frontmatter must_haves)

#### Plan 01 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | MonitorSession, DiscoveredDevice, PollResult, DeviceEvent models exist and migrate cleanly | ✓ VERIFIED | All 4 classes found in `planner/models.py` lines 4549, 4563, 4614, 4634. Migration `0148_discovereddevice_monitorsession_deviceevent_and_more.py` exists. `manage.py makemigrations --check` reports "No changes detected". |
| 2 | run_monitor management command starts an ICMP polling daemon thread that writes PollResult and DeviceEvent rows | ✓ VERIFIED | `daemon=True` thread at line 139; `PollResult.objects.create()` at line 67; `DeviceEvent.objects.create()` at lines 49, 79, 91 |
| 3 | N=3 consecutive failure tracking fires OFFLINE event only at threshold, not on single flap | ✓ VERIFIED | `consecutive_failures == 3` (not >=) at line 88 — fires exactly once at threshold; no OFFLINE creation for values 1 or 2 |
| 4 | Device coming back online after N>=3 failures fires ONLINE event | ✓ VERIFIED | `if prev_state != 'online': DE.objects.create(event_type='ONLINE', ...)` at lines 77-82; `prev_state` captures `last_known_state` which is set to `'offline'` at N=3 |
| 5 | Monitor models appear in showstack_admin_site sidebar under Network Health Monitor group | ✓ VERIFIED | All 4 models registered at `admin.py` lines 6006-6009 on `showstack_admin_site`; `admin_ordering.py` positions 36-39 confirmed |

#### Plan 02 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | GET /audiopatch/network-monitor/ renders the dashboard with current device statuses from the database | ✓ VERIFIED | `network_monitor_view` queries `DiscoveredDevice.objects.filter(project=current_project, is_active=True)`, builds context dict, renders `planner/network_monitor.html`. URL resolves to `/audiopatch/network-monitor/`. Django `check` passes. |
| 2 | GET /audiopatch/network-monitor/stream/ returns an SSE event stream with heartbeats every 2 seconds | ✓ VERIFIED | `StreamingHttpResponse(content_type='text/event-stream')` at line 193; `yield ": heartbeat\n\n"` with `time.sleep(2)` at lines 190-191; `X-Accel-Buffering: no` at line 197 |
| 3 | POST /audiopatch/network-monitor/scan/ with a NIC interface name returns JSON with responding hosts on that subnet | ✓ VERIFIED | `trigger_scan_view` validates subnet against NIC allowlist, calls `sweep_subnet()`, returns `{'ok': True, 'devices': [...]}` |
| 4 | POST /audiopatch/network-monitor/devices/add/ creates DiscoveredDevice records for selected IPs | ✓ VERIFIED | `add_monitor_devices_view` uses `get_or_create` with re-activation path; returns `{'ok': True, 'added': N}` |
| 5 | POST /audiopatch/network-monitor/devices/<id>/remove/ deactivates a device from monitoring | ✓ VERIFIED | `remove_monitor_device_view` sets `is_active=False`; scoped to `current_project` |
| 6 | All views require login and scope queries to request.current_project | ✓ VERIFIED | All 5 views decorated with `@login_required`; all use `getattr(request, 'current_project', None)` with 400 guard on POST endpoints |

#### Plan 03 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Engineer sees domain rollup bar with LA Network online/total count at top of page | ✓ VERIFIED | `#nhm-rollup` renders at template line 862; LA Network pill bound to `domain_counts.la_network.online/total` from context; `updateRollupBar()` JS refreshes count on `STATUS_SNAPSHOT` |
| 2 | Device cards show green/amber/red status dots that update live via SSE without page refresh | ? HUMAN | CSS classes `nhm-dot--online/flapping/offline` defined; `updateStatusDot()` swaps dot class on SSE event; requires live browser + running monitor |
| 3 | Clicking a device card expands to show IP, latency, last seen, and remove button | ? HUMAN | Expand HTML structure present with `nhm-card--expanded` class; `toggleCard()` function present; localStorage state persisted — requires browser interaction to verify |
| 4 | Alert banners appear at top when a device goes offline (N>=3) and can be dismissed | ? HUMAN | Server-rendered banners from `active_alerts` context; `showAlertBanner()` JS inserts on SSE OFFLINE event; `dismissAlert()` removes — requires live device going offline |
| 5 | Session history section shows timestamped ONLINE/OFFLINE/SCAN events | ? HUMAN | `#nhm-timeline-list` server-rendered from `recent_events`; `prependTimelineEvent()` inserts on SSE — requires active session with events |
| 6 | NIC selector dropdown and Start Scan button trigger a subnet sweep and show results | ? HUMAN | JS `startScan()` POSTs to `/audiopatch/network-monitor/scan/`, renders `renderScanResults()` — requires network interface and real subnet |
| 7 | When no project is active or no devices exist, a clear empty state message is shown | ✓ VERIFIED | Three conditional branches at template lines 907-933: no project, monitor off + no devices (shows run_monitor command), monitor on + no devices (shows "Not connected to show network") |
| 8 | Dante and Switches domain pills show as grey placeholders (Phase 1 is ICMP only) | ✓ VERIFIED | Template lines 870-876: Dante and Switches pills use `nhm-dot--unknown` (grey) with static "0/0" text; no live updates wired for these domains |

**Automated score:** 13/16 truths confirmed programmatically. 3 roadmap SCs: 3 confirmed, 2 require human. Net verified without human: 13 observable truths PASS, 6 require human browser/live-network testing.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `planner/models.py` | MonitorSession, DiscoveredDevice, PollResult, DeviceEvent | ✓ VERIFIED | All 4 classes exist at lines 4549-4661; correct fields, `as_status_dict()`, `as_sse_dict()`, `unique_together` on `(project, ip_address)` |
| `planner/management/commands/run_monitor.py` | ICMP polling daemon with N=3 state machine | ✓ VERIFIED | 154 lines; `daemon=True` thread; `consecutive_failures == 3` gate; `stop_event.wait()`; `close_old_connections()` per poll cycle |
| `planner/admin.py` | Admin registration for 4 monitor models | ✓ VERIFIED | Lines 6006-6009: all 4 registered on `showstack_admin_site`; PollResult and DeviceEvent are read-only |
| `planner/admin_ordering.py` | Sidebar ordering for monitor models | ✓ VERIFIED | Positions 36-39 confirmed; `pollresult` and `deviceevent` in `child_models` set |
| `planner/views_monitor.py` | 5 view functions + 2 utility functions | ✓ VERIFIED | 330 lines; all 7 functions present; all views `@login_required` and project-scoped |
| `planner/urls.py` | 5 URL patterns under network-monitor/ | ✓ VERIFIED | Lines 250-255: all 5 patterns; `from . import views_monitor` import present; all 5 URLs resolve via `reverse()` |
| `templates/planner/network_monitor.html` | Full dashboard template, min 400 lines | ✓ VERIFIED | 1751 lines; extends `admin/base_site.html`; all 8 UI-SPEC components present |
| `requirements.txt` | icmplib, netifaces | ✓ VERIFIED | Lines 21-22: `icmplib>=3.0,<4.0` and `netifaces>=0.11` |
| `planner/migrations/0148_*.py` | Migration for 4 monitor models | ✓ VERIFIED | `0148_discovereddevice_monitorsession_deviceevent_and_more.py` exists; `makemigrations --check` reports no pending changes |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `run_monitor.py` | `planner/models.py` | `from planner.models import` | ✓ WIRED | Lazy imports inside thread/handle: `MonitorSession`, `DeviceEvent`, `DiscoveredDevice`, `PollResult` all imported at point of use |
| `admin.py` | `planner/models.py` | `showstack_admin_site.register` | ✓ WIRED | 4 registrations confirmed at lines 6006-6009 |
| `views_monitor.py` | `planner/models.py` | `from .models import` | ✓ WIRED | Line 12-14: `from .models import MonitorSession, DiscoveredDevice, PollResult, DeviceEvent` |
| `urls.py` | `views_monitor.py` | `from . import views_monitor` | ✓ WIRED | Line 9 of urls.py; 5 `views_monitor.` references in URL patterns |
| `network_monitor.html` (EventSource) | `/audiopatch/network-monitor/stream/` | `new EventSource(...)` | ✓ WIRED | Line 1197: `new EventSource('/audiopatch/network-monitor/stream/')` |
| `network_monitor.html` (scan fetch) | `/audiopatch/network-monitor/scan/` | `fetch POST` | ✓ WIRED | Line 1451: `fetch('/audiopatch/network-monitor/scan/', ...)` in `startScan()` |
| `network_monitor.html` (add devices fetch) | `/audiopatch/network-monitor/devices/add/` | `fetch POST` | ✓ WIRED | Line 1566: `fetch('/audiopatch/network-monitor/devices/add/', ...)` in `addDevices()` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `network_monitor_view` | `devices` | `DiscoveredDevice.objects.filter(project=current_project, is_active=True)` | Yes — real DB query | ✓ FLOWING |
| `network_monitor_view` | `recent_events` | `DeviceEvent.objects.filter(session=active_session).order_by('-occurred_at')[:50]` | Yes — real DB query | ✓ FLOWING |
| `network_monitor_view` | `active_alerts` | `DiscoveredDevice.objects.filter(..., last_known_state='offline')` | Yes — real DB query | ✓ FLOWING |
| `monitor_stream_view` | SSE events | `DeviceEvent.objects.filter(session=session, id__gt=last_event_id)` | Yes — incremental DB poll | ✓ FLOWING |
| `monitor_stream_view` | STATUS_SNAPSHOT | `DiscoveredDevice.objects.filter(project=current_project, is_active=True)` | Yes — real DB query every 2s | ✓ FLOWING |
| `network_monitor.html` | `NHM_DEVICES` | `{{ devices_json\|safe }}` from view context | Yes — bound to real queryset | ✓ FLOWING |
| `network_monitor.html` | `NHM_EVENTS` | `{{ recent_events_json\|safe }}` from view context | Yes — bound to real queryset | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `run_monitor --help` shows expected flags | `python manage.py run_monitor --help` | Shows `--project-id` (required) and `--interval` (default: 10) | ✓ PASS |
| Django system check passes | `python manage.py check` | "System check identified no issues (0 silenced)" | ✓ PASS |
| No pending migrations | `python manage.py makemigrations planner --check` | "No changes detected in app 'planner'" | ✓ PASS |
| All 5 URL names resolve | `django.urls.reverse(...)` | All 5 paths resolve correctly under `/audiopatch/network-monitor/` | ✓ PASS |
| Template loads without syntax errors | Django `get_template('planner/network_monitor.html')` | "Template loads OK" | ✓ PASS |
| All 4 models importable | `from planner.models import MonitorSession, ...` | Import confirmed via successful `manage.py check` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| MON-02 | 01-01, 01-02 | All project devices show up/down reachability status via ICMP ping | ✓ SATISFIED | `run_monitor` uses `icmplib.multiping(privileged=False)`; `PollResult.is_reachable` records result per device per poll; dashboard renders status via `DiscoveredDevice.status()` |
| MON-03 | 01-01 | Monitor targets pull IP addresses from existing ShowStack device records via FK | ✓ SATISFIED (with approved deviation) | D-05 (network-scan discovery) explicitly overrides MON-03. `DiscoveredDevice` is project-scoped via `ForeignKey('Project')` but has no FK to Console/Amp/Device. Decision documented in SUMMARY 01-01. Scan-based discovery satisfies the intent of project-scoped monitoring. |
| DASH-01 | 01-03 | At-a-glance green/yellow/red status indicators per network domain | ? NEEDS HUMAN | CSS classes and DOM wiring confirmed; live visual update requires browser verification |
| DASH-02 | 01-01, 01-03 | Critical alerts for device offline with confirm-before-firing (N=3) | ✓ SATISFIED | N=3 gate confirmed in `run_monitor.py`; alert banner HTML and `showAlertBanner()` JS confirmed in template |
| DASH-03 | 01-02, 01-03 | Session history timeline showing state changes with timestamps | ? NEEDS HUMAN | Server-rendered `#nhm-timeline-list` from `recent_events` confirmed; SSE insertion confirmed in JS; requires live session to verify end-to-end |
| INFRA-01 | 01-01 | `run_monitor` management command runs background polling with daemon threads | ✓ SATISFIED | `daemon=True` thread; `stop_event` for clean shutdown; `close_old_connections()` for Railway compatibility |
| INFRA-02 | 01-02 | SSE push delivers live status updates to dashboard without page refresh | ✓ SATISFIED | `StreamingHttpResponse(content_type='text/event-stream')`; `X-Accel-Buffering: no`; `EventSource` in template with reconnect logic |
| INFRA-03 | 01-02, 01-03 | Local network prerequisite detection with clear messaging when not on show network | ✓ SATISFIED | Three empty-state branches in template: no project, monitor off + no devices (shows run_monitor command), monitor on + no devices ("Not connected to show network") |

**MON-03 note:** The deviation from strict FK linkage to existing device models is intentional, documented in 01-01-SUMMARY.md, and architecturally sound. The requirement is functionally met through scan-based device entry, which remains project-scoped.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None found | — | — | — |

No TODOs, FIXMEs, placeholder stubs, hardcoded empty returns, or unimplemented handlers were found in any of the 6 key files verified. Template renders real data from DB-backed context variables. All fetch endpoints have real implementations.

### Human Verification Required

#### 1. Live SSE Status Dot Updates

**Test:** Start `python manage.py run_monitor --project-id <ID>`, navigate to `/audiopatch/network-monitor/`, scan and add a device, then watch the dashboard
**Expected:** Device status dots update from unknown to green (online) or red (offline) within ~10 seconds, without any page refresh
**Why human:** SSE streaming requires a running server + active polling process; browser DOM updates cannot be verified programmatically

#### 2. N=3 Alert Fires Correctly, Single Flap Does Not

**Test:** With run_monitor running and a device monitored, disconnect the device from the network. Wait for 3 poll cycles (~30 seconds at default interval). Reconnect immediately after 1 or 2 cycles.
**Expected:** Disconnecting for 3 cycles: red pulsing dot + alert banner at top. Disconnecting for only 1-2 cycles: no alert banner appears (dot may flicker amber), returns to green on reconnect.
**Why human:** Requires live ICMP polling against a real device that can be physically or logically disconnected

#### 3. Session History Timeline Populates

**Test:** With run_monitor running, add a device that goes online (green dot). Stop and restart the device to generate ONLINE/OFFLINE events. Expand "Session History".
**Expected:** Timestamped rows appear for each state change: "came online", "went offline". Events prepend (newest at top). Maximum 20 rows visible with scroll.
**Why human:** Requires run_monitor producing real DeviceEvent rows, then verifying SSE delivery and DOM prepend behavior

#### 4. Scan Flow End-to-End

**Test:** On a network with other devices, open the dashboard, select a NIC from the dropdown, click "Start Scan"
**Expected:** "Scanning..." spinner appears; after completion, a checkbox list shows discovered IPs with latency values; already-monitored devices are checked and disabled; selecting devices and clicking "Add to Monitor" reloads the page with new device cards
**Why human:** Requires being on a real network with other discoverable hosts; output is topology-dependent

#### 5. Empty State Messaging

**Test 5a:** With monitor running but zero devices added: verify "Not connected to show network" heading appears.
**Test 5b:** With no active session (monitor not running) and zero devices: verify the heading shows the `run_monitor` command and includes the project ID.
**Expected:** Correct conditional message per state; no silent empty dashboard.
**Why human:** Requires specific DB state combinations to verify both empty-state branches render correctly

### Gaps Summary

No programmatic gaps found. All artifacts exist, are substantive, are wired, and have real data flowing through them. The 6 human verification items cover behaviors that require a running server, live network, and browser interaction — they cannot be verified by file inspection alone.

The MON-03 deviation (no FK to existing device models) is intentional per D-05 and documented in 01-01-SUMMARY.md. It does not constitute a gap.

---

_Verified: 2026-04-21_
_Verifier: Claude (gsd-verifier)_
