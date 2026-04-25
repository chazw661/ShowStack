# Phase 2: Switch SNMP - Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 7 (2 new, 5 modified)
**Analogs found:** 7 / 7

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `planner/models.py` (append 2 models + 1 field) | model | CRUD | `planner/models.py` lines 4549–4666 (Phase 1 NHM models) | exact |
| `planner/views_monitor.py` (add 5 endpoints + extend 1) | controller | request-response | `planner/views_monitor.py` existing endpoints | exact |
| `planner/management/commands/run_monitor.py` (add SNMP thread) | utility / agent | event-driven | `run_monitor.py` existing `handle()` + `_poll_devices()` | exact |
| `planner/urls.py` (add 5 paths) | config | request-response | `planner/urls.py` lines 251–265 | exact |
| `planner/admin.py` (register 2 new models) | config | CRUD | `planner/admin.py` lines 5974–6009 | exact |
| `planner/admin_ordering.py` (add 2 entries) | config | — | `planner/admin_ordering.py` lines 143–147 | exact |
| `templates/planner/network_monitor.html` (add settings panel, show mode toggle, switch card expansion, port table) | component | request-response | `network_monitor.html` existing header, domain sections, AJAX polling JS | exact |

---

## Pattern Assignments

### `planner/models.py` — append `ProjectSNMPConfig`, `SwitchPortSnapshot`, extend `MonitorSession`

**Analog:** `planner/models.py` lines 4549–4666

**Model definition pattern** (lines 4619–4636, `PollResult` as template for `SwitchPortSnapshot`):
```python
class PollResult(models.Model):
    device = models.ForeignKey(DiscoveredDevice, on_delete=models.CASCADE,
                               related_name='poll_results')
    session = models.ForeignKey(MonitorSession, on_delete=models.CASCADE,
                                related_name='poll_results')
    polled_at = models.DateTimeField(auto_now_add=True)
    is_reachable = models.BooleanField()
    latency_ms = models.FloatField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['device', 'polled_at']),
            models.Index(fields=['session', 'polled_at']),
        ]

    def __str__(self):
        state = 'up' if self.is_reachable else 'down'
        return f"{self.device} {state} @ {self.polled_at:%H:%M:%S}"
```

**OneToOne FK pattern** (lines 4552–4562, `MonitorSession` → `Project` as template for `ProjectSNMPConfig`):
```python
class MonitorSession(models.Model):
    project = models.ForeignKey('Project', on_delete=models.CASCADE,
                                related_name='monitor_sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Session {self.pk} — {self.project} ({self.started_at:%Y-%m-%d %H:%M})"
```

**Choices field pattern** (lines 4566–4581, `DiscoveredDevice`):
```python
DOMAIN_CHOICES = [
    ('la_network', 'LA Network'),
    ('dante', 'Dante'),
    ('switch', 'Switch'),
    ('unknown', 'Unknown'),
]
# ... used as:
domain = models.CharField(max_length=20, choices=DOMAIN_CHOICES, default='unknown')
```

**What to write** (append after line 4666):
```python
# ── Phase 2 models ──────────────────────────────────────────────────────────

class ProjectSNMPConfig(models.Model):
    """Per-project SNMP v2c community string. One row per project."""
    project = models.OneToOneField(
        'Project', on_delete=models.CASCADE,
        related_name='snmp_config',
    )
    community_string = models.CharField(
        max_length=255, default='public',
        help_text="SNMP v2c community string for all switches in this project.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SNMP config for {self.project}"


class SwitchPortSnapshot(models.Model):
    """Latest port-level data per SNMP poll cycle.
    update_or_create(device, session, port_index) — one row per port, replaced each cycle."""
    device = models.ForeignKey(
        'DiscoveredDevice', on_delete=models.CASCADE,
        related_name='port_snapshots',
    )
    session = models.ForeignKey(
        'MonitorSession', on_delete=models.CASCADE,
        related_name='port_snapshots',
    )
    port_index = models.PositiveIntegerField()
    port_description = models.CharField(max_length=100, blank=True)
    oper_status = models.CharField(
        max_length=10,
        choices=[('up', 'Up'), ('down', 'Down'), ('unknown', 'Unknown')],
        default='unknown',
    )
    speed_mbps = models.PositiveIntegerField(null=True, blank=True)  # 100, 1000, 10000
    bandwidth_pct = models.FloatField(null=True, blank=True)         # 0.0–100.0
    error_count = models.PositiveBigIntegerField(default=0)          # cumulative since session start
    polled_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('device', 'session', 'port_index')]
        indexes = [
            models.Index(fields=['device', 'session']),
        ]

    def __str__(self):
        return f"{self.device} port {self.port_index} ({self.oper_status})"
```

**`MonitorSession` field addition** — add after `notes = models.TextField(blank=True)` at line 4556:
```python
show_mode = models.CharField(
    max_length=10,
    choices=[('setup', 'Setup'), ('show', 'Show'), ('wrap', 'Wrap')],
    default='show',
)
```

---

### `planner/views_monitor.py` — 5 new endpoints + extend `monitor_status_view`

**Analog:** `planner/views_monitor.py` (the whole file — all patterns are here)

**Import block** (lines 15–28):
```python
import json
import time

from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import close_old_connections
from django.utils import timezone

from .models import (
    Project, MonitorSession, DiscoveredDevice, PollResult, DeviceEvent,
)
```
Phase 2 adds `ProjectSNMPConfig, SwitchPortSnapshot` to this import.

**Agent auth pattern** (lines 35–48 — apply to both new agent endpoints):
```python
def _authenticate_agent(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, JsonResponse({'error': 'Missing Authorization header'}, status=401)
    token = auth_header[7:].strip()
    try:
        project = Project.objects.get(agent_api_key=token)
        return project, None
    except Project.DoesNotExist:
        return None, JsonResponse({'error': 'Invalid API key'}, status=403)
```

**Agent endpoint pattern** (lines 278–295, `agent_stop` — minimal POST, csrf_exempt):
```python
@csrf_exempt
@require_POST
def agent_stop(request):
    project, err = _authenticate_agent(request)
    if err:
        return err
    # ... business logic ...
    return JsonResponse({'ok': True, 'status': 'stopped'})
```

**Dashboard endpoint pattern** (lines 193–215, `dashboard_reassign_device` — login_required, json.loads body):
```python
@login_required
@require_POST
def dashboard_reassign_device(request, device_id):
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'error': 'No active project'}, status=400)
    # ...
    data = json.loads(request.body)
    new_domain = data.get('domain', '')
    valid_domains = ['la_network', 'dante', 'switch', 'unknown']
    if new_domain not in valid_domains:
        return JsonResponse({'error': f'Invalid domain. Use: {valid_domains}'}, status=400)
    device.domain = new_domain
    device.save(update_fields=['domain'])
    return JsonResponse({'ok': True, 'device_id': device_id, 'domain': new_domain})
```

**Active session fetch pattern** (lines 373–377, used in `agent_poll_results`):
```python
session = MonitorSession.objects.filter(
    project=project, ended_at__isnull=True
).first()
if not session:
    return JsonResponse({'error': 'No active session. Call /api/heartbeat/ first.'}, status=400)
```

**`monitor_status_view` extension target** (lines 161–167 — extend this return):
```python
return JsonResponse({
    'ok': True,
    'monitor_running': session is not None,
    'devices': [d.as_status_dict() for d in devices],
    'events': new_events,
    'last_event_id': new_events[-1]['id'] if new_events else last_event_id,
    # Phase 2 additions:
    'show_mode': session.show_mode if session else 'show',
    'switch_ports': {
        str(device.pk): [
            {
                'port_index': snap.port_index,
                'port_description': snap.port_description,
                'oper_status': snap.oper_status,
                'speed_mbps': snap.speed_mbps,
                'bandwidth_pct': snap.bandwidth_pct,
                'error_count': snap.error_count,
            }
            for snap in device.port_snapshots.filter(session=session).order_by('port_index')
        ]
        for device in devices
        if device.domain == 'switch'
    },
})
```

**Show mode alert suppression pattern** (model: `agent_poll_results` lines 405–431 — copy this structure into `agent_snmp_results`):
```python
# Critical: always fires (N=3 offline)
if device.consecutive_failures == 3:
    device.last_known_state = 'offline'
    if device.last_seen is not None:  # never-seen stay 'unreachable' — no alert
        ev = DeviceEvent.objects.create(
            device=device, session=session,
            event_type='OFFLINE',
            details={'consecutive_failures': device.consecutive_failures},
        )
        events_created.append(ev.as_sse_dict())

# Non-critical: suppressed in setup/wrap
suppress_non_critical = session.show_mode in ('setup', 'wrap')
if not suppress_non_critical:
    DeviceEvent.objects.create(event_type='PORT_DOWN', ...)
```

**New endpoints to add** (follow agent/dashboard patterns above):
```
# Agent endpoints (csrf_exempt + require_POST + _authenticate_agent):
GET  /api/snmp-settings/  → returns community_string + switch IPs list
POST /api/snmp-results/   → agent pushes per-port data → SwitchPortSnapshot.update_or_create

# Dashboard endpoints (login_required + require_POST):
POST /snmp-settings/      → browser saves community string → ProjectSNMPConfig.get_or_create + save
POST /add-switch/         → browser adds manual IP → DiscoveredDevice(domain='switch')
POST /show-mode/          → browser changes mode → MonitorSession.show_mode save
```

---

### `planner/management/commands/run_monitor.py` — add SNMP daemon thread

**Analog:** `run_monitor.py` (the whole file — 337 lines, already read in full)

**Current `handle()` structure** (lines 43–188 — this is a flat while-loop, not threads):
```python
def handle(self, *args, **options):
    api_key = options['api_key']
    server = options['server'].rstrip('/')
    interval = options['interval']
    base_url = f'{server}/audiopatch/network-monitor/api'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    # ... heartbeat, scan ...

    running = True
    def handle_signal(sig, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    while running:
        poll_results = self._poll_devices(base_url, headers)
        if poll_results:
            try:
                resp = http_requests.post(
                    f'{base_url}/poll-results/',
                    headers=headers,
                    json={'results': poll_results},
                    timeout=15,
                )
                # ... handle response, scan_requested ...
            except http_requests.ConnectionError:
                self.stderr.write(self.style.WARNING('Lost connection...'))
            except Exception as e:
                self.stderr.write(self.style.WARNING(f'Error: {e}'))

        for _ in range(interval * 10):  # check running every 0.1s
            if not running:
                break
            time.sleep(0.1)
```

**HTTP push pattern** (lines 94–108 — copy for SNMP results push):
```python
resp = http_requests.post(
    f'{base_url}/scan-results/',
    headers=headers,
    json={'devices': discovered},
    timeout=30,
)
if resp.status_code == 200:
    result = resp.json()
    self.stdout.write(self.style.SUCCESS(
        f'Pushed to ShowStack: {result.get("added", 0)} new, '
        f'{result.get("updated", 0)} updated'
    ))
else:
    self.stderr.write(self.style.WARNING(f'Push failed: {resp.text}'))
```

**HTTP fetch pattern** (lines 309–318 — copy for `/api/snmp-settings/` fetch):
```python
try:
    resp = http_requests.get(
        f'{base_url}/devices/',
        headers=headers, timeout=10,
    )
    if resp.status_code != 200:
        return []
    device_ips = resp.json().get('devices', [])
except Exception:
    return []
```

**Restructure target** — Phase 2 converts the flat while-loop to two daemon threads. Add `import threading` and `import asyncio` at the top. New structure:
```python
import threading
import asyncio

def handle(self, *args, **options):
    # ... existing heartbeat + scan unchanged ...
    stop_event = threading.Event()

    icmp_thread = threading.Thread(
        target=self._icmp_loop,
        args=(stop_event, base_url, headers, interval),
        daemon=True, name='ICMPPoller',
    )
    snmp_thread = threading.Thread(
        target=self._snmp_loop,
        args=(stop_event, base_url, headers),
        daemon=True, name='SNMPPoller',
    )
    icmp_thread.start()
    snmp_thread.start()

    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=1)
    except KeyboardInterrupt:
        self.stdout.write('\nShutting down...')
        stop_event.set()

    icmp_thread.join(timeout=5)
    snmp_thread.join(timeout=5)

def _icmp_loop(self, stop_event, base_url, headers, interval):
    """Existing while running: loop, moved verbatim into this method."""
    # ... copy existing loop body here ...

def _snmp_loop(self, stop_event, base_url, headers):
    """Polls switch-domain devices via SNMP every 30 seconds."""
    SNMP_INTERVAL = 30
    prev_counters = {}  # {(ip, port_idx): {'in': N, 'out': N, 'ts': T}}
    snmp_settings = self._fetch_snmp_settings(base_url, headers)

    while not stop_event.is_set():
        if snmp_settings:
            results = asyncio.run(
                _async_poll_all_switches(
                    snmp_settings['switches'],
                    snmp_settings['community_string'],
                    prev_counters,
                )
            )
            if results:
                self._push_snmp_results(base_url, headers, results)
        snmp_settings = self._fetch_snmp_settings(base_url, headers)
        stop_event.wait(timeout=SNMP_INTERVAL)
```

**SNMP pysnmp module-level functions** (add at top of file, outside the `Command` class):
```python
# Module-level async functions — called via asyncio.run() from _snmp_loop daemon thread.
# Never called from Django views (no running event loop in daemon thread — safe).

from pysnmp.hlapi.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, bulkCmd,
)

IF_MIB_ROOTS = {
    'oper_status':  '1.3.6.1.2.1.2.2.1.8',
    'high_speed':   '1.3.6.1.2.1.31.1.1.1.15',
    'hc_in_octets': '1.3.6.1.2.1.31.1.1.1.6',
    'hc_out_octets':'1.3.6.1.2.1.31.1.1.1.10',
    'in_errors':    '1.3.6.1.2.1.2.2.1.14',
}

async def _async_walk_subtree(snmp_engine, community, ip, oid_root):
    """Walk one IF-MIB subtree. Returns {port_index: int_value} or None on error."""
    rows = {}
    async for (err, err_status, err_idx, var_binds) in bulkCmd(
        snmp_engine,
        CommunityData(community),
        UdpTransportTarget((ip, 161), timeout=5, retries=1),
        ContextData(),
        0, 25,
        ObjectType(ObjectIdentity(oid_root)),
        lexicographicMode=False,
    ):
        if err or err_status:
            return None
        for name, val in var_binds:
            port_idx = int(str(name).split('.')[-1])
            rows[port_idx] = int(val)
    return rows

def _compute_bandwidth_pct(curr_in, prev_in, curr_out, prev_out, prev_ts, curr_ts, speed_mbps):
    """RFC 2863 bandwidth utilization — returns 0.0–100.0 or None."""
    interval = curr_ts - prev_ts
    if interval <= 0 or not speed_mbps:
        return None
    delta_in  = (curr_in  - prev_in)  % (2 ** 64)
    delta_out = (curr_out - prev_out) % (2 ** 64)
    link_bps  = speed_mbps * 1_000_000
    pct = (max(delta_in, delta_out) * 8 / (link_bps * interval)) * 100
    return min(round(pct, 1), 100.0)
```

---

### `planner/urls.py` — add 5 paths

**Analog:** `planner/urls.py` lines 251–265

**Existing NHM URL pattern** (lines 251–265):
```python
from . import views_monitor

path('network-monitor/', views_monitor.network_monitor_view, name='network_monitor'),
path('network-monitor/status/', views_monitor.monitor_status_view, name='monitor_status'),
path('network-monitor/devices/<int:device_id>/remove/', views_monitor.dashboard_remove_device, name='dashboard_remove_device'),
path('network-monitor/devices/<int:device_id>/reassign/', views_monitor.dashboard_reassign_device, name='dashboard_reassign_device'),
path('network-monitor/request-scan/', views_monitor.dashboard_request_scan, name='dashboard_request_scan'),
path('network-monitor/api/heartbeat/', views_monitor.agent_heartbeat, name='agent_heartbeat'),
path('network-monitor/api/stop/', views_monitor.agent_stop, name='agent_stop'),
path('network-monitor/api/scan-results/', views_monitor.agent_scan_results, name='agent_scan_results'),
path('network-monitor/api/poll-results/', views_monitor.agent_poll_results, name='agent_poll_results'),
path('network-monitor/api/remove-device/', views_monitor.agent_remove_device, name='agent_remove_device'),
path('network-monitor/api/devices/', views_monitor.agent_device_list, name='agent_device_list'),
```

**New paths to add** (follow same naming scheme):
```python
# Dashboard endpoints (session auth)
path('network-monitor/snmp-settings/', views_monitor.dashboard_snmp_settings, name='dashboard_snmp_settings'),
path('network-monitor/add-switch/', views_monitor.dashboard_add_switch, name='dashboard_add_switch'),
path('network-monitor/show-mode/', views_monitor.dashboard_set_show_mode, name='dashboard_set_show_mode'),
# Agent endpoints (Bearer auth)
path('network-monitor/api/snmp-settings/', views_monitor.agent_snmp_settings, name='agent_snmp_settings'),
path('network-monitor/api/snmp-results/', views_monitor.agent_snmp_results, name='agent_snmp_results'),
```

---

### `planner/admin.py` — register `ProjectSNMPConfig`, `SwitchPortSnapshot`

**Analog:** `planner/admin.py` lines 5974–6009

**Import line to extend** (line 23 — add new models):
```python
from .models import MonitorSession, DiscoveredDevice, PollResult, DeviceEvent
# Phase 2: add ProjectSNMPConfig, SwitchPortSnapshot
```

**Append-only admin pattern** (lines 5984–5993, `PollResultAdmin` — use for `SwitchPortSnapshot`):
```python
class PollResultAdmin(admin.ModelAdmin):
    list_display = ('device', 'is_reachable', 'latency_ms', 'polled_at')
    list_filter = ('is_reachable', 'session')
    readonly_fields = ('device', 'session', 'polled_at', 'is_reachable', 'latency_ms')

    def has_add_permission(self, request):
        return False  # Append-only — created by run_monitor

    def has_change_permission(self, request, obj=None):
        return False
```

**Editable model admin pattern** (lines 5979–5982, `DiscoveredDeviceAdmin` — use for `ProjectSNMPConfig`):
```python
class DiscoveredDeviceAdmin(admin.ModelAdmin):
    list_display = ('label', 'ip_address', 'domain', 'last_known_state', 'consecutive_failures', 'is_active', 'project')
    list_filter = ('domain', 'last_known_state', 'is_active', 'project')
    search_fields = ('label', 'ip_address')
```

**Registration pattern** (lines 6006–6009):
```python
showstack_admin_site.register(MonitorSession, MonitorSessionAdmin)
showstack_admin_site.register(DiscoveredDevice, DiscoveredDeviceAdmin)
showstack_admin_site.register(PollResult, PollResultAdmin)
showstack_admin_site.register(DeviceEvent, DeviceEventAdmin)
# Phase 2 — append:
showstack_admin_site.register(ProjectSNMPConfig, ProjectSNMPConfigAdmin)
showstack_admin_site.register(SwitchPortSnapshot, SwitchPortSnapshotAdmin)
```

---

### `planner/admin_ordering.py` — add 2 entries

**Analog:** `planner/admin_ordering.py` lines 143–147

**Existing NHM block**:
```python
# Network Health Monitor (36-39)
'monitorsession': 36,
'discovereddevice': 37,
'pollresult': 38,
'deviceevent': 39,
```

**Phase 2 additions** — extend the block to 40–41:
```python
# Network Health Monitor (36-41)
'monitorsession': 36,
'discovereddevice': 37,
'pollresult': 38,
'deviceevent': 39,
'projectsnmpconfig': 40,
'switchportsnapshot': 41,
```

---

### `templates/planner/network_monitor.html` — settings panel, show mode toggle, switch card expansion

**Analog:** `templates/planner/network_monitor.html` (the whole file — all UI patterns present)

**CSS custom properties** (lines 16–31 — all Phase 2 UI must use these variables):
```css
:root {
    --bg-base:       #0f0f1a;
    --bg-card:       #181828;
    --bg-raised:     #1e1e32;
    --bg-input:      #252540;
    --border:        #2a2a45;
    --border-bright: #3a3a60;
    --accent-blue:   #4a9eff;
    --accent-green:  #00e676;
    --accent-amber:  #ffab00;
    --accent-red:    #ff5252;
    --text-primary:  #e8e8f0;
    --text-secondary:#9090b0;
    --text-dim:      #505070;
}
```

**Header layout pattern** (lines 46–80 — show mode toggle and gear icon slot into `.nhm-header-right`):
```html
<div class="nhm-header">
  <div class="nhm-header-left">
    <span class="nhm-title">Network Health Monitor</span>
    <span class="nhm-project-name">{{ current_project.name|default:"No project selected" }}</span>
  </div>
  <div class="nhm-header-right">
    <!-- domain rollup pills, agent indicator, action buttons -->
  </div>
</div>
```

**Rollup pill pattern** (lines 983–1001 — show mode toggle goes beside these, gear icon after):
```html
<div id="nhm-rollup">
  <span class="nhm-rollup-label">Status</span>
  <span class="nhm-pill nhm-pill--placeholder" id="nhm-pill-switches">
    <span class="nhm-dot nhm-dot--unknown" id="nhm-rollup-dot-switches"></span>
    Switches: <span id="nhm-rollup-switches">{{ domain_counts.switch.online|default:0 }}/{{ domain_counts.switch.total|default:0 }}</span>
  </span>
</div>
```

**Status dot class convention** (lines 91–95 — bandwidth color states follow same pattern):
```css
.nhm-dot--online     { background: var(--accent-green); }
.nhm-dot--flapping   { background: var(--accent-amber); }
.nhm-dot--offline    { background: var(--accent-red); animation: nhm-pulse 2s infinite; }
.nhm-dot--unknown    { background: var(--text-dim); }
.nhm-dot--unreachable{ background: var(--text-dim); opacity: 0.5; }
```
Phase 2 bandwidth CSS mirrors this: `nhm-bw--green`, `nhm-bw--amber`, `nhm-bw--red` using the same variables.

**Domain card expand pattern** (lines 1160–1214 — switch card currently shows Phase 1 inner detail; Phase 2 replaces the inner content with a port table):
```html
<div class="nhm-card" id="nhm-device-{{ device.id }}"
     data-domain="{{ device.domain }}"
     data-status="{{ device.last_known_state }}"
     onclick="toggleCard({{ device.id }})"
     tabindex="0" role="button" aria-expanded="false">
  <div class="nhm-card-header">
    <span class="nhm-dot nhm-dot--{{ device.last_known_state|default:'unknown' }}"></span>
    <span class="nhm-card-name">{{ device.label|default:device.ip_address }}</span>
    <span class="nhm-card-latency">...</span>
  </div>
  <div class="nhm-card-detail">
    <div class="nhm-card-detail-inner">
      <!-- Phase 2: replace with port count summary + port table -->
    </div>
  </div>
</div>
```

**AJAX polling pattern** (lines 1354–1418 — `pollStatus()` is where switch port data is consumed):
```js
const POLL_INTERVAL = 2000; // 2 seconds
let lastEventId = 0;

function pollStatus() {
    fetch('/audiopatch/network-monitor/status/?last_event_id=' + lastEventId)
    .then(r => r.json())
    .then(data => {
        if (!data.ok) return;
        data.devices.forEach(function(dev) {
            updateStatusDot(dev.device_id, dev.status, dev.latency_ms);
        });
        updateRollupBar();
        // Phase 2 additions here:
        // if (data.show_mode) updateShowModeToggle(data.show_mode);
        // if (data.switch_ports) updateSwitchPortTables(data.switch_ports);
        // ...
    })
    .catch(function(err) { console.warn('[NHM] Poll error:', err.message); });
}
```

**CSRF helper** (lines 1338–1352 — all dashboard POSTs use this):
```js
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
const csrfToken = getCookie('csrftoken');
```

**Inline style override rule** (CLAUDE.md — applies to any JS that sets colors):
```js
// Wrong:
element.style.color = 'red';
// Correct (Django admin uses !important pervasively):
element.style.setProperty('color', 'red', 'important');
```

---

## Shared Patterns

### Agent authentication
**Source:** `planner/views_monitor.py` lines 35–48
**Apply to:** All 2 new agent endpoints (`agent_snmp_settings`, `agent_snmp_results`)
```python
project, err = _authenticate_agent(request)
if err:
    return err
```

### Session-based project scoping
**Source:** `planner/views_monitor.py` lines 58, 134 (all dashboard views)
**Apply to:** All 3 new dashboard endpoints, `monitor_status_view` extension
```python
current_project = getattr(request, 'current_project', None)
if not current_project:
    return JsonResponse({'error': 'No active project'}, status=400)
```

### Active session fetch
**Source:** `planner/views_monitor.py` lines 373–377
**Apply to:** `agent_snmp_results`, `dashboard_set_show_mode`, `monitor_status_view`
```python
session = MonitorSession.objects.filter(
    project=project, ended_at__isnull=True
).first()
if not session:
    return JsonResponse({'error': 'No active session.'}, status=400)
```

### Admin registration on `showstack_admin_site`
**Source:** `planner/admin.py` lines 6006–6009
**Apply to:** Both new model admin classes — NEVER use `admin.site`

### `admin_ordering.py` update required
**Source:** `planner/admin_ordering.py` lines 143–147
**Apply to:** Both new models — must be added to `order_map` or the sidebar grouping breaks

### CSRF token for dashboard POSTs
**Source:** `templates/planner/network_monitor.html` lines 1338–1352
**Apply to:** All 3 new dashboard JS fetch calls (snmp-settings, add-switch, show-mode)

### Inline style override in JS
**Source:** CLAUDE.md coding conventions
**Apply to:** Any Phase 2 JS that sets colors (bandwidth %, show mode banner)
```js
element.style.setProperty('property', 'value', 'important');
```

---

## No Analog Found

None — all Phase 2 files have close or exact analogs in the existing codebase.

---

## Metadata

**Analog search scope:** `planner/models.py`, `planner/views_monitor.py`, `planner/management/commands/run_monitor.py`, `planner/urls.py`, `planner/admin.py`, `planner/admin_ordering.py`, `templates/planner/network_monitor.html`
**Files scanned:** 7 (all read in full or via targeted offset reads)
**Pattern extraction date:** 2026-04-24
