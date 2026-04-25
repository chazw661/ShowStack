# Phase 3: Dante - Pattern Map

**Mapped:** 2026-04-25
**Files analyzed:** 6 modifications (no new files)
**Analogs found:** 6 / 6

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `planner/models.py` (add Dante fields to DiscoveredDevice) | model | CRUD | `SwitchPortSnapshot` model (line 4696) | exact |
| `planner/views_monitor.py` (add `agent_dante_results`, `health_check_view`) | controller | request-response | `agent_snmp_results` (line 553) | exact |
| `planner/management/commands/run_monitor.py` (add DantePoller thread) | service | streaming | `_snmp_loop` method (line 310) | exact |
| `planner/urls.py` (add Dante API + health check routes) | route | config | Phase 2 SNMP URL block (lines 267-274) | exact |
| `planner/admin.py` + `planner/admin_ordering.py` (no new models expected) | config | config | N/A -- fields added to existing model, no new admin registration needed | N/A |
| `templates/planner/network_monitor.html` (Dante cards + health panel) | component | event-driven | `updateSwitchCards` JS function (line 2400) + Dante placeholder (line 1368) | exact |

## Pattern Assignments

### `planner/models.py` -- Add Dante fields to DiscoveredDevice

**Analog:** `SwitchPortSnapshot` model definition (lines 4696-4726) shows the Phase 2 pattern for adding domain-specific data models to the monitor.

**Existing DiscoveredDevice model** (lines 4570-4621) -- fields to extend:
```python
class DiscoveredDevice(models.Model):
    DOMAIN_CHOICES = [
        ('la_network', 'LA Network'),
        ('dante', 'Dante'),
        ('switch', 'Switch'),
        ('unknown', 'Unknown'),
    ]
    # ... existing fields ...
    project = models.ForeignKey('Project', on_delete=models.CASCADE,
                                related_name='discovered_devices')
    label = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField()
    domain = models.CharField(max_length=20, choices=DOMAIN_CHOICES, default='unknown')
    is_active = models.BooleanField(default=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_known_state = models.CharField(max_length=10, choices=STATE_CHOICES, default='unknown')
    last_seen = models.DateTimeField(null=True, blank=True)
    discovered_at = models.DateTimeField(auto_now_add=True)
```

**as_status_dict pattern** (lines 4612-4621) -- extend for Dante fields:
```python
def as_status_dict(self):
    return {
        'device_id': self.pk,
        'label': self.label or self.ip_address,
        'ip': self.ip_address,
        'domain': self.domain,
        'status': self.status(),
        'consecutive_failures': self.consecutive_failures,
        'last_seen': self.last_seen.isoformat() if self.last_seen else None,
    }
```

**New Dante fields should follow the nullable/blank pattern from SwitchPortSnapshot** (lines 4707-4717):
```python
# SwitchPortSnapshot field pattern -- nullable optional fields with defaults
port_description = models.CharField(max_length=100, blank=True)
speed_mbps = models.PositiveIntegerField(null=True, blank=True)
bandwidth_pct = models.FloatField(null=True, blank=True)
error_count = models.PositiveBigIntegerField(default=0)
polled_at = models.DateTimeField(auto_now=True)
```

**DeviceEvent EVENT_CHOICES extension pattern** (lines 4644-4654) -- add Dante event types:
```python
EVENT_CHOICES = [
    ('ONLINE', 'Came online'),
    ('OFFLINE', 'Went offline'),
    ('SCAN_STARTED', 'Network scan started'),
    ('MONITOR_STARTED', 'Monitor started'),
    ('PORT_DOWN', 'Switch port went down'),
    ('PORT_UP', 'Switch port came up'),
    ('BW_WARNING', 'Bandwidth threshold exceeded'),
    ('BW_CRITICAL', 'Bandwidth critical threshold exceeded'),
]
```

---

### `planner/views_monitor.py` -- Agent Dante results + Health check endpoints

**Analog:** `agent_snmp_results` (lines 552-638) -- exact pattern for agent push endpoint.

**Agent auth pattern** (lines 37-50):
```python
def _authenticate_agent(request):
    """Authenticate agent via Bearer token (project agent_api_key).
    Returns (project, None) on success or (None, JsonResponse) on failure.
    """
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

**Agent POST endpoint pattern** (lines 552-638) -- `agent_snmp_results`:
```python
@csrf_exempt
@require_POST
def agent_snmp_results(request):
    """Agent pushes SNMP port data for switches.
    POST /audiopatch/network-monitor/api/snmp-results/
    """
    project, err = _authenticate_agent(request)
    if err:
        return err

    session = MonitorSession.objects.filter(project=project, ended_at__isnull=True).first()
    if not session:
        return JsonResponse({'error': 'No active session.'}, status=400)

    data = json.loads(request.body)
    results = data.get('results', [])
    # ... process results, update_or_create snapshots, create events ...
    return JsonResponse({'ok': True, 'events': events_created})
```

**Dashboard GET endpoint pattern** (lines 132-190) -- `monitor_status_view`:
```python
@login_required
def monitor_status_view(request):
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return JsonResponse({'ok': False, 'error': 'No project'})
    # ... query DB, build JSON response ...
    return JsonResponse({
        'ok': True,
        'monitor_running': session is not None,
        'devices': [d.as_status_dict() for d in devices],
        # ...
    })
```

**Status view switch_ports extension pattern** (lines 171-189) -- how Phase 2 added domain-specific data to the poll response:
```python
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
} if session else {},
```

---

### `planner/management/commands/run_monitor.py` -- DantePoller thread

**Analog:** `_snmp_loop` method (lines 310-399) -- exact pattern.

**Thread creation pattern** (lines 234-248):
```python
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
```

**Thread join pattern** (lines 254-258):
```python
icmp_thread.join(timeout=5)
snmp_thread.join(timeout=5)
```

**SNMP loop pattern** (lines 310-399) -- the exact template for DantePoller:
```python
def _snmp_loop(self, stop_event, base_url, headers):
    """SNMP polling thread -- polls switch-domain devices every 30 seconds."""
    if not PYSNMP_AVAILABLE:
        self.stderr.write(self.style.WARNING(
            'pysnmp not installed -- SNMP polling disabled. Install: pip install "pysnmp>=7.1,<8.0"'
        ))
        return

    SNMP_INTERVAL = 30

    while not stop_event.is_set():
        # ... fetch settings from API ...
        # ... poll via asyncio.run() ...
        # ... push results to API ...
        stop_event.wait(timeout=SNMP_INTERVAL)
```

**Import availability check pattern** (lines 31-38):
```python
try:
    from pysnmp.hlapi.asyncio import (
        SnmpEngine, CommunityData, UdpTransportTarget,
        ContextData, ObjectType, ObjectIdentity, walk_cmd,
    )
    PYSNMP_AVAILABLE = True
except ImportError:
    PYSNMP_AVAILABLE = False
```

**asyncio.run from thread pattern** (lines 333-338):
```python
# Poll all switches via asyncio.run (safe -- this thread has no event loop)
try:
    raw_results = asyncio.run(_async_poll_all_switches(switches, community))
except Exception as e:
    self.stderr.write(self.style.WARNING(f'[SNMP] Poll error: {e}'))
    stop_event.wait(timeout=SNMP_INTERVAL)
    continue
```

**Push results helper pattern** (lines 414-439):
```python
def _push_snmp_results(self, base_url, headers, results):
    """POST /api/snmp-results/ -- push port data for all switches."""
    try:
        resp = http_requests.post(
            f'{base_url}/snmp-results/',
            headers=headers,
            json={'results': results},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            events = data.get('events', [])
            for ev in events:
                # ... log events to stdout/stderr ...
        else:
            self.stderr.write(self.style.WARNING(f'[SNMP] Push failed ({resp.status_code})'))
    except http_requests.ConnectionError:
        self.stderr.write(self.style.WARNING('[SNMP] Lost connection. Retrying next cycle...'))
    except Exception as e:
        self.stderr.write(self.style.WARNING(f'[SNMP] Push error: {e}'))
```

---

### `planner/urls.py` -- Dante API routes

**Analog:** Phase 2 SNMP URL block (lines 267-274).

**Dashboard endpoint URL pattern** (lines 267-271):
```python
# Network Health Monitor -- Phase 2: SNMP (dashboard)
path('network-monitor/snmp-settings/', views_monitor.dashboard_snmp_settings, name='dashboard_snmp_settings'),
path('network-monitor/add-switch/', views_monitor.dashboard_add_switch, name='dashboard_add_switch'),
path('network-monitor/show-mode/', views_monitor.dashboard_set_show_mode, name='dashboard_set_show_mode'),
```

**Agent endpoint URL pattern** (lines 273-274):
```python
# Network Health Monitor -- Phase 2: SNMP (agent)
path('network-monitor/api/snmp-settings/', views_monitor.agent_snmp_settings, name='agent_snmp_settings'),
path('network-monitor/api/snmp-results/', views_monitor.agent_snmp_results, name='agent_snmp_results'),
```

---

### `templates/planner/network_monitor.html` -- Dante section UI

**Analog:** Dante placeholder section (lines 1368-1423) + `updateSwitchCards` JS function (lines 2400-2493).

**Device card HTML pattern** (lines 1315-1360 from LA Network section):
```html
<div class="nhm-card" id="nhm-device-{{ device.id }}"
     data-domain="{{ device.domain }}"
     data-status="{{ device.last_known_state }}"
     onclick="toggleCard({{ device.id }})"
     tabindex="0" role="button"
     aria-expanded="false"
     onkeydown="if(event.key==='Enter'||event.key===' '){toggleCard({{ device.id }});}">
  <div class="nhm-card-header">
    <span class="nhm-dot nhm-dot--{{ device.last_known_state|default:'unknown' }}"
          aria-label="{{ device.label }}: {{ device.last_known_state|default:'unknown' }}"></span>
    <span class="nhm-card-name">{{ device.label|default:device.ip_address }}</span>
    <span class="nhm-card-latency">
      {% if device.last_latency_ms %}{{ device.last_latency_ms|floatformat:1 }} ms{% else %}&mdash;{% endif %}
    </span>
  </div>
  <div class="nhm-card-detail">
    <div class="nhm-card-detail-inner">
      <!-- detail rows -->
    </div>
  </div>
</div>
```

**Domain section header pattern** (lines 1300-1311):
```html
<div class="nhm-domain" id="nhm-domain-la-network" data-domain="la_network">
  <div class="nhm-domain-header" tabindex="0" role="button"
       aria-expanded="true" aria-controls="nhm-domain-body-la-network"
       onclick="toggleDomain('la-network', this)"
       onkeydown="if(event.key==='Enter'||event.key===' '){toggleDomain('la-network', this);}">
    <span class="nhm-domain-name">LA Network</span>
    <span class="nhm-domain-badge" id="nhm-badge-la-network">
      {{ domain_counts.la_network.total|default:0 }} device{{ domain_counts.la_network.total|default:0|pluralize }}
    </span>
    <span class="nhm-domain-toggle" aria-hidden="true" id="nhm-toggle-la-network">&#9650;</span>
  </div>
```

**JS dynamic card update pattern** -- `updateSwitchCards` (lines 2400-2493) shows how to:
1. Select cards by `data-domain` attribute
2. Inject summary text into card header
3. Build expanded detail content dynamically (tables for switches; for Dante: clock role, channels, IP)
4. Create elements if they don't exist, update in-place if they do

**AJAX poll consumption pattern** (lines 1650-1674):
```javascript
function pollStatus() {
    fetch('/audiopatch/network-monitor/status/?last_event_id=' + lastEventId)
    .then(r => r.json())
    .then(data => {
        if (!data.ok) return;
        // Update all device status dots
        if (data.devices) {
            data.devices.forEach(function(dev) {
                updateStatusDot(dev.device_id, dev.status, dev.latency_ms);
            });
            updateRollupBar();
        }
        // Phase 2: switch port data
        if (data.switch_ports !== undefined) {
            updateSwitchCards(data.switch_ports, data.snmp_configured !== undefined ? data.snmp_configured : snmpConfigured);
        }
        // Phase 3: add dante_data consumption here, similar to switch_ports
    });
}
```

**Rollup bar update pattern** (lines 1789-1791):
```javascript
const danteEl = document.getElementById('nhm-rollup-dante');
if (danteEl) danteEl.textContent = domains.dante.online + '/' + domains.dante.total;
updatePillColor('nhm-pill-dante', 'nhm-rollup-dot-dante', domains.dante);
```

---

## Shared Patterns

### Agent Authentication
**Source:** `planner/views_monitor.py` lines 37-50
**Apply to:** `agent_dante_results` endpoint
```python
project, err = _authenticate_agent(request)
if err:
    return err
```

### Session Validation
**Source:** `planner/views_monitor.py` lines 563-565 (from `agent_snmp_results`)
**Apply to:** `agent_dante_results` endpoint
```python
session = MonitorSession.objects.filter(project=project, ended_at__isnull=True).first()
if not session:
    return JsonResponse({'error': 'No active session.'}, status=400)
```

### Project Scoping (Dashboard Views)
**Source:** `planner/views_monitor.py` lines 133-140 (from `monitor_status_view`)
**Apply to:** `health_check_view` endpoint
```python
current_project = getattr(request, 'current_project', None)
if not current_project:
    return JsonResponse({'ok': False, 'error': 'No project'})
```

### Error Handling in Agent Threads
**Source:** `planner/management/commands/run_monitor.py` lines 333-339
**Apply to:** DantePoller thread
```python
try:
    raw_results = asyncio.run(...)
except Exception as e:
    self.stderr.write(self.style.WARNING(f'[Dante] Error: {e}'))
    stop_event.wait(timeout=INTERVAL)
    continue
```

### CSS Override Convention
**Source:** `CLAUDE.md` -- Coding Conventions & Gotchas
**Apply to:** All dynamic DOM updates in `network_monitor.html`
```javascript
// Django admin CSS uses !important -- must use setProperty
element.style.setProperty('color', 'red', 'important');
// NOT: element.style.color = 'red';
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| Health check panel UI | component | request-response | No existing collapsible health check panel in the dashboard; however, the expandable card detail pattern (`nhm-card-detail`) provides a close structural analog for expand/collapse behavior |

The health check panel (D-07, D-08) is a new UI concept in this dashboard -- no existing analog for a "compare expected vs discovered" results panel. The planner should use the card expand/collapse pattern for the panel's auto-expand behavior, and the `nhm-domain-empty` placeholder pattern for the "all clear" state.

## Metadata

**Analog search scope:** `planner/models.py`, `planner/views_monitor.py`, `planner/management/commands/run_monitor.py`, `planner/urls.py`, `planner/admin.py`, `planner/admin_ordering.py`, `templates/planner/network_monitor.html`
**Files scanned:** 7
**Pattern extraction date:** 2026-04-25
