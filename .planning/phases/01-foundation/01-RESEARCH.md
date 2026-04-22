# Phase 1: Foundation - Research

**Researched:** 2026-04-22
**Domain:** Django 5.x ICMP monitoring, SSE streaming, management command daemons, NIC detection, network sweep
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Dashboard is a standalone page at `/audiopatch/network-monitor/` — consistent with mic-tracker, comm-config, and power-distribution as full-page standalone views (not admin changeform)
- **D-02:** Devices are grouped by network domain (Dante, LA Network, Switches) — matches how an A1 thinks about show networks
- **D-03:** Minimal device cards — device name + green/yellow/red status dot. Click to expand for details (IP, latency, last seen)
- **D-04:** Domain rollup summary bar at top: "Dante: 12/12 | LA Network: 8/8 | Switches: 3/3" — instant health glance before scrolling
- **D-05:** Devices are discovered by scanning the network directly — NOT pulled from existing ShowStack device models. The monitor discovers what's actually on the network, independent of project data.
- **D-06:** Discovery method: scan the selected NIC's subnet via ping sweep, show all responding devices, let engineer select which ones to keep monitoring. Unselected devices are hidden but can be re-shown.
- **D-07:** NIC selection: auto-detect all active network interfaces and let engineer pick which NIC to scan. No permanent per-domain NIC assignment — flexible per-scan selection.
- **D-08:** For devices with multiple IPs (e.g., consoles with primary + secondary), monitor primary IP only.
- **D-09:** N=3 confirm-before-firing — device must fail 3 consecutive polls before a critical alert fires. No single-flap false positives.

### Claude's Discretion

- Alert presentation (banner, toast, badge) — Claude picks the right approach for a live show monitoring context
- Session history timeline visual design — Claude decides layout (event log table, timeline, etc.)
- "Not on show network" detection and messaging approach

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MON-02 | All project devices show up/down reachability status via ICMP ping | icmplib 3.0.4 verified working on macOS arm64 with `privileged=False`; `multiping` and `async_multiping` confirmed for batch checks |
| MON-03 | Monitor targets pull IP addresses from existing ShowStack device records via FK | **Superseded by D-05**: D-05 locks discovery to network scanning, not existing device models. MON-03 as written in REQUIREMENTS.md predates the D-05 decision. Implementation should create `DiscoveredDevice` records from scan results, not FK to Console/Device/Amp models. |
| DASH-01 | At-a-glance green/yellow/red status indicators per network domain | UI-SPEC defines rollup bar with domain pills; status dot contract defined in color spec |
| DASH-02 | Critical alerts for device offline with N=3 confirm-before-firing | N=3 consecutive failure tracking via `consecutive_failures` field on model; alert fires at threshold |
| DASH-03 | Session history timeline showing state changes with timestamps | `DeviceEvent` append-only table; SSE delivers events to browser; timeline UI defined in UI-SPEC |
| INFRA-01 | `run_monitor` management command with daemon threads per protocol | Pattern: daemon thread + threading.Event stop signal; verified with existing 7 management commands |
| INFRA-02 | SSE push delivers live status updates without page refresh | Django 5.2.4 `StreamingHttpResponse` verified; runserver is threaded by default (--nothreading disables) |
| INFRA-03 | Local network prerequisite detection with clear messaging | NIC detection via netifaces 0.11.0 verified; "not on show network" UI state defined in UI-SPEC §7 |

</phase_requirements>

---

## Summary

Phase 1 delivers the complete poll→DB→SSE→browser pipeline using ICMP ping as the simplest protocol. The architecture is two-process: `run_monitor` (background daemon) pings devices and writes results to the database; `runserver` (web process) serves the dashboard and an SSE endpoint that streams state deltas to the browser. This separation is the foundational pattern that Phase 2 (SNMP) and Phase 3 (Dante/mDNS) will extend without changing the core structure.

All key technical questions for this phase have been verified against real code on this macOS arm64 machine: `icmplib 3.0.4` pings `localhost` successfully with `privileged=False` (SOCK_DGRAM ICMP is available without root); `netifaces 0.11.0` enumerates interface IPs and netmasks correctly; `ipaddress.IPv4Network` derives the correct subnet for ping sweeps; `StreamingHttpResponse` produces correct SSE headers; and Django's dev server is threaded by default (SSE connections do not block other requests).

One requirements conflict requires the planner's attention: MON-03 in REQUIREMENTS.md says to link monitor targets to existing Console/Device/Amp models via FK, but decision D-05 explicitly locks discovery to network scanning independent of project data. D-05 takes precedence. The data model should reflect D-05 — `DiscoveredDevice` records created from scan results with no FK to existing module models.

**Primary recommendation:** Build in this order — models + migration, then `run_monitor` command with daemon ICMP thread, then SSE endpoint, then dashboard template. Each step produces testable output before the next begins.

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 1 |
|-----------|-------------------|
| Custom admin site: `showstack_admin_site` not `admin.site` | Any admin-registered models use `showstack_admin_site.register()` |
| Update `admin_ordering.py` for new registered models | Must add monitor models to sidebar hierarchy |
| Session-based project scoping via `CurrentProjectMiddleware` | Dashboard view reads `request.current_project`; all querysets scoped to it |
| Views registered under `audiopatch/` prefix in `planner/urls.py` | New path: `path('network-monitor/', ...)` |
| Templates extend `templates/planner/base.html` | `network_monitor.html` uses `{% extends 'planner/base.html' %}` |
| IP addresses use `models.GenericIPAddressField` | `DiscoveredDevice.ip_address` must use this field type |
| Never run destructive ops against Railway Postgres without confirming with Charlie | `makemigrations` + `migrate` locally; prod deployment via git push |
| `collectstatic` runs on every Railway deploy | No special static file concerns — styles live in `<style>` block in template |
| Do not iterate on Dante Subscription Planner | Phase 1 creates new models/views with no deps on Dante module |
| Django Channels / WebSockets explicitly out of scope (REQUIREMENTS.md) | SSE via `StreamingHttpResponse` is the mandated approach |
| Redis / Celery explicitly out of scope | Background polling must use threads/management command only |

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ICMP ping sweep (subnet discovery) | Backend (run_monitor thread) | — | Network I/O must never run in a request handler; blocks WSGI worker |
| Consecutive-failure tracking (N=3) | Backend (run_monitor thread) | — | State machine lives in polling thread; no web-layer involvement |
| Alert generation (write DeviceEvent) | Backend (run_monitor thread) | — | Events written when state transitions are detected during polling |
| Poll result persistence | Backend (PostgreSQL via Django ORM) | — | run_monitor writes; SSE endpoint reads |
| SSE event stream | Django view (StreamingHttpResponse) | — | Web layer reads DB, yields SSE frames; no network I/O |
| Dashboard initial render | Django view (WSGI) | — | Renders current snapshot from DB on page load |
| NIC detection + scan trigger | Django view (POST endpoint) | — | Scan is a user-triggered action, not background |
| Device selection (add to monitor) | Django view (POST endpoint) | — | Engineer-driven action after scan results shown |
| Status dot update (live) | Browser (EventSource JS) | — | EventSource receives SSE frames, updates DOM in place |
| localStorage state (collapse/expand) | Browser | — | Card/section collapse state is client-local |
| Alert banner display + dismiss | Browser | — | Banner state is client-local; dismiss does not write to DB |
| Session history timeline | Django view + Browser | — | Timeline data served by view; rendered by browser |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard | Source |
|---------|---------|---------|--------------|--------|
| `icmplib` | 3.0.4 | ICMP ping — device reachability and subnet sweep | Pure Python, no root required on macOS (SOCK_DGRAM), `multiping` for batch | [VERIFIED: pip index; local test] |
| `netifaces` | 0.11.0 | NIC enumeration — get IP + netmask per interface | Returns `AF_INET` addr + netmask, works on macOS arm64 without root | [VERIFIED: local test] |
| Django 5.2.4 `StreamingHttpResponse` | built-in | SSE push to browser | No additional deps; works under threaded WSGI runserver | [VERIFIED: local test] |
| `ipaddress` (stdlib) | 3.x stdlib | Subnet calculation from NIC IP + netmask | Derive sweep range from `IPv4Network(f'{ip}/{netmask}', strict=False)` | [VERIFIED: local test] |
| Django ORM + PostgreSQL | Django 5.2.4 | Monitor models, poll results, event log | Existing database; no TimescaleDB needed at show-day event volumes | [VERIFIED: requirements.txt] |
| `threading` (stdlib) | 3.x stdlib | Daemon threads in `run_monitor` command | No external scheduler; stop via `threading.Event` | [VERIFIED: local test] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` (stdlib) | built-in | Serialize status payloads in SSE frames | SSE data field is always `data: {...}\n\n` |
| `time` (stdlib) | built-in | Poll interval sleep in daemon thread | `time.sleep(interval)` in polling loop |
| `socket` (stdlib) | built-in | Interface name enumeration fallback | `socket.if_nameindex()` gives interface names when netifaces unavailable |
| `ipaddress` (stdlib) | built-in | Generate IP list for subnet sweep | `list(network.hosts())` yields all pingable addresses |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `netifaces` | `psutil` | psutil is heavier (used for process/CPU monitoring); netifaces is purpose-built for NIC data |
| `netifaces` | `subprocess ifconfig` parsing | Fragile, macOS-only, brittle across OS versions |
| `icmplib` multiping | subprocess `ping -c 1` per host | Cannot parallelize; fragile output parsing; 100x slower for 254-host sweep |
| `StreamingHttpResponse` (sync generator) | `async` generator with `asyncio.sleep` | Async requires Daphne/ASGI; sync generator works under existing WSGI runserver with zero config change |
| `threading.Event` stop signal | `apscheduler` | APScheduler adds a dependency; threading.Event is stdlib and sufficient for this single-protocol phase |

**Installation (additions to requirements.txt):**

```bash
pip install "icmplib>=3.0,<4.0"
pip install "netifaces>=0.11"
```

**Version verification:** [VERIFIED: 2026-04-22]
- `icmplib`: 3.0.4 is latest stable on PyPI. Published ~2023. No newer version available.
- `netifaces`: 0.11.0 is latest stable. Note: package is minimally maintained but stable; no breaking changes expected.

---

## Architecture Patterns

### System Architecture Diagram

```
Engineer's laptop (on show network)
───────────────────────────────────────────────────────────────────
                                                                   
  Terminal 1: python manage.py runserver                           
  ┌─────────────────────────────────────────────────────────────┐  
  │  WSGI (threaded) — Django 5.2.4                             │  
  │                                                             │  
  │  GET /audiopatch/network-monitor/                           │  
  │    └─► network_monitor_view() ──► render initial snapshot   │  
  │                                                             │  
  │  POST /audiopatch/network-monitor/scan/                     │  
  │    └─► trigger_scan_view()                                  │  
  │          └─► netifaces: get IP+netmask for selected NIC     │  
  │          └─► icmplib.multiping(all subnet hosts)            │  
  │          └─► return JSON: [{ip, hostname, latency}]         │  
  │                                                             │  
  │  POST /audiopatch/network-monitor/devices/add/              │  
  │    └─► add_devices_view()                                   │  
  │          └─► create DiscoveredDevice records in DB          │  
  │                                                             │  
  │  GET /audiopatch/network-monitor/stream/                    │  
  │    └─► monitor_stream_view()                                │  
  │          └─► StreamingHttpResponse(event_generator())       │  
  │                event_generator():                           │  
  │                  loop forever:                              │  
  │                    SELECT DeviceEvent WHERE id > last_id    │  
  │                    yield "data: {...}\n\n"                  │  
  │                    time.sleep(2)                            │  
  └───────────────────────┬─────────────────────────────────────┘  
                          │ reads                                   
                          ▼                                         
                   ┌─────────────┐                                  
                   │ PostgreSQL  │                                   
                   │             │ DiscoveredDevice                  
                   │             │ PollResult (append-only)          
                   │             │ DeviceEvent (state transitions)   
                   │             │ MonitorSession                    
                   └──────┬──────┘                                  
                          │ writes                                   
  Terminal 2: python manage.py run_monitor --project-id N           
  ┌─────────────────────────────────────────────────────────────┐  
  │  Management command (OS process)                            │  
  │                                                             │  
  │  main thread: blocks on stop_event.wait()                   │  
  │  Ctrl+C ──► stop_event.set() ──► daemon threads die         │  
  │                                                             │  
  │  ICMPPoller (daemon thread):                                │  
  │    loop until stop_event:                                   │  
  │      targets = DiscoveredDevice.objects.filter(active=True) │  
  │      results = icmplib.multiping([t.ip for t in targets])   │  
  │      for each result:                                       │  
  │        write PollResult(is_reachable, latency_ms)          │  
  │        if state changed:                                    │  
  │          update DiscoveredDevice.consecutive_failures       │  
  │          if failures >= 3: write DeviceEvent('OFFLINE')     │  
  │          if came back: write DeviceEvent('ONLINE')          │  
  │      stop_event.wait(timeout=interval)  # default 10s       │  
  └─────────────────────────────────────────────────────────────┘  
                                                                   
  Browser (EventSource connected to /stream/):                      
    on message ──► parse JSON ──► update status dot DOM element     
    on OFFLINE event ──► show alert banner                          
    on ONLINE event ──► dismiss alert if one exists                 
    on EventSource error ──► show "Reconnecting…" indicator         
```

### Recommended Project Structure

```
planner/
├── models.py                          # Add MonitorSession, DiscoveredDevice,
│                                      # PollResult, DeviceEvent at end of file
├── views.py                           # Add network_monitor_view, monitor_stream_view,
│                                      # trigger_scan_view, add_devices_view
│                                      # (or views_monitor.py to avoid growing views.py further)
├── urls.py                            # Add network-monitor/* paths
├── admin_ordering.py                  # Add monitor models to sidebar
└── management/
    └── commands/
        └── run_monitor.py             # New management command

templates/planner/
└── network_monitor.html               # Extends base.html, scoped under .nhm-root
```

### Pattern 1: SSE Generator with DB Polling

The SSE endpoint uses a sync generator that polls the DB every 2 seconds for new `DeviceEvent` rows. Works under the existing WSGI runserver without ASGI.

```python
# Source: verified locally — Django 5.2.4 StreamingHttpResponse
import json, time
from django.http import StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from .models import DeviceEvent, MonitorSession

@login_required
def monitor_stream_view(request):
    project = request.current_project

    def event_generator():
        last_id = 0
        while True:
            events = DeviceEvent.objects.filter(
                session__project=project,
                id__gt=last_id,
            ).order_by('id').select_related('device')[:50]
            for ev in events:
                last_id = ev.id
                yield f"data: {json.dumps(ev.as_sse_dict())}\n\n"
            # Heartbeat to keep connection alive and detect browser disconnect
            yield ": heartbeat\n\n"
            time.sleep(2)

    response = StreamingHttpResponse(event_generator(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Prevent nginx buffering on Railway
    return response
```

**Critical:** The `yield ": heartbeat\n\n"` SSE comment line fires every 2 seconds even when there are no events. This keeps the TCP connection alive and lets the browser detect a stale/dead connection quickly. Without it, the browser may not detect server restart for 30–60 seconds.

### Pattern 2: Management Command with Daemon Threads

```python
# Source: verified locally — threading.Event pattern
import threading, time, signal
from django.core.management.base import BaseCommand
from django.db import close_old_connections

class Command(BaseCommand):
    help = 'Run the network health monitor polling engine'

    def add_arguments(self, parser):
        parser.add_argument('--project-id', type=int, required=True)
        parser.add_argument('--interval', type=int, default=10,
                            help='Poll interval in seconds (default: 10)')

    def handle(self, *args, **options):
        project_id = options['project_id']
        interval = options['interval']
        stop_event = threading.Event()

        def icmp_poller():
            from planner.models import DiscoveredDevice, PollResult, DeviceEvent
            while not stop_event.is_set():
                close_old_connections()  # Required: threads don't auto-close DB connections
                targets = list(
                    DiscoveredDevice.objects.filter(
                        project_id=project_id, is_active=True
                    )
                )
                if targets:
                    import icmplib
                    ips = [t.ip_address for t in targets]
                    results = icmplib.multiping(
                        ips, count=1, timeout=2,
                        privileged=False, concurrent_tasks=50
                    )
                    ip_map = {r.address: r for r in results}
                    for target in targets:
                        result = ip_map.get(target.ip_address)
                        is_up = result.is_alive if result else False
                        latency = result.avg_rtt if result and result.is_alive else None
                        _record_poll(target, is_up, latency, project_id)
                stop_event.wait(timeout=interval)

        t = threading.Thread(target=icmp_poller, daemon=True, name='ICMPPoller')
        t.start()
        self.stdout.write(f'Monitor started (project={project_id}, interval={interval}s)')

        try:
            stop_event.wait()  # Block main thread; Ctrl+C raises KeyboardInterrupt
        except KeyboardInterrupt:
            self.stdout.write('\nShutting down...')
            stop_event.set()
```

**Critical:** `close_old_connections()` must be called at the top of every polling iteration. Django's database connection pool is not thread-safe — threads that create DB connections must explicitly close them or they leak. `close_old_connections()` closes connections that have exceeded `CONN_MAX_AGE`.

### Pattern 3: ICMP Subnet Sweep

```python
# Source: verified locally — icmplib 3.0.4 + netifaces 0.11.0 + stdlib ipaddress
import icmplib, netifaces, ipaddress

def get_active_nics():
    """Return list of (interface_name, ip, subnet_cidr) for non-loopback IPv4 interfaces."""
    nics = []
    for iface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET not in addrs:
            continue
        for addr in addrs[netifaces.AF_INET]:
            ip = addr['addr']
            netmask = addr.get('netmask')
            if not netmask or ip.startswith('127.') or ip.startswith('169.254.'):
                continue
            network = ipaddress.IPv4Network(f'{ip}/{netmask}', strict=False)
            nics.append({
                'interface': iface,
                'ip': ip,
                'subnet': str(network),
                'host_count': network.num_addresses - 2,  # exclude network + broadcast
            })
    return nics

def sweep_subnet(subnet_cidr, privileged=False, timeout=1, concurrent_tasks=100):
    """Ping all hosts in a subnet. Returns list of responding hosts."""
    network = ipaddress.IPv4Network(subnet_cidr, strict=False)
    hosts = [str(h) for h in network.hosts()]
    results = icmplib.multiping(
        hosts,
        count=1,
        timeout=timeout,
        privileged=privileged,
        concurrent_tasks=concurrent_tasks,
    )
    return [
        {'ip': r.address, 'latency_ms': r.avg_rtt}
        for r in results
        if r.is_alive
    ]
```

**Scale note:** A /22 subnet (1022 hosts) with `concurrent_tasks=100` sweeps in approximately 2–5 seconds on a local network where most hosts are unresponsive. A /24 (254 hosts) completes in under 2 seconds. `timeout=1` means the total sweep time equals `ceil(host_count / concurrent_tasks) * timeout_seconds`.

### Pattern 4: N=3 State Machine

Implement consecutive failure tracking on `DiscoveredDevice` — no separate state table needed:

```python
def _record_poll(target, is_up, latency_ms, project_id):
    """Write PollResult and update consecutive_failures. Fire alert at N=3."""
    from planner.models import PollResult, DeviceEvent, MonitorSession
    import django.utils.timezone as tz

    # Get or create active session for this project
    session, _ = MonitorSession.objects.get_or_create(
        project_id=project_id, ended_at__isnull=True,
        defaults={'started_at': tz.now()}
    )

    PollResult.objects.create(
        device=target,
        session=session,
        is_reachable=is_up,
        latency_ms=latency_ms,
    )

    prev_state = target.last_known_state  # 'online' | 'offline' | 'unknown'

    if is_up:
        if prev_state != 'online':
            # Device came back
            DeviceEvent.objects.create(
                device=target, session=session,
                event_type='ONLINE',
                details={'latency_ms': latency_ms},
            )
        target.consecutive_failures = 0
        target.last_known_state = 'online'
        target.last_seen = tz.now()
    else:
        target.consecutive_failures = (target.consecutive_failures or 0) + 1
        if target.consecutive_failures == 3:
            # N=3: fire alert
            target.last_known_state = 'offline'
            DeviceEvent.objects.create(
                device=target, session=session,
                event_type='OFFLINE',
                details={'consecutive_failures': target.consecutive_failures},
            )
        elif target.consecutive_failures > 3:
            # Still offline — no duplicate alert
            pass
        # consecutive_failures 1 or 2: amber state, no alert

    target.save(update_fields=['consecutive_failures', 'last_known_state', 'last_seen'])
```

### Pattern 5: Browser-Side EventSource

Plain JavaScript — no npm dependency, no HTMX SSE extension required:

```javascript
// Source: MDN Web Docs EventSource API [CITED: developer.mozilla.org/en-US/docs/Web/API/EventSource]
(function() {
    const STREAM_URL = '/audiopatch/network-monitor/stream/';
    let es = null;
    let retries = 0;
    const MAX_RETRIES = 5;

    function connect() {
        es = new EventSource(STREAM_URL);

        es.onmessage = function(e) {
            retries = 0;
            const event = JSON.parse(e.data);
            handleMonitorEvent(event);
        };

        es.onerror = function() {
            es.close();
            retries++;
            if (retries <= MAX_RETRIES) {
                showReconnecting();
                setTimeout(connect, Math.min(1000 * retries, 10000));
            } else {
                showConnectionFailed();
            }
        };

        es.onopen = function() {
            retries = 0;
            hideReconnecting();
        };
    }

    function handleMonitorEvent(event) {
        // event.type: 'POLL_UPDATE' | 'ONLINE' | 'OFFLINE' | 'SCAN_COMPLETE'
        if (event.type === 'POLL_UPDATE') {
            updateStatusDot(event.device_id, event.status, event.latency_ms);
            updateRollupBar(event.domain);
        } else if (event.type === 'OFFLINE') {
            updateStatusDot(event.device_id, 'offline', null);
            showAlertBanner(event.device_name, event.occurred_at);
        } else if (event.type === 'ONLINE') {
            updateStatusDot(event.device_id, 'online', event.latency_ms);
        }
    }

    connect();
})();
```

**SSE vs HTMX SSE extension:** Use plain `EventSource` for this dashboard. HTMX's SSE extension expects the server to yield complete HTML fragments for `hx-swap`. For a live monitoring dashboard where many elements update from a single stream, manual DOM manipulation via `EventSource.onmessage` gives more precise control. The HTMX SSE extension is better suited when the server yields full DOM swap payloads per event — more complex to implement server-side.

### Anti-Patterns to Avoid

- **Polling in a view handler:** SNMP/ICMP in a Django view blocks the WSGI thread for the entire poll duration. All network I/O lives exclusively in `run_monitor` daemon threads. Views only read from the database.
- **AppConfig.ready() for polling:** `ready()` fires twice under `runserver` (auto-reloader) and once per Gunicorn worker. Spawning threads there causes duplicate pollers and data corruption.
- **Single `NetworkEvent` table:** Storing raw poll results (every 10s) and alert events in the same table bloats the event log immediately. Use two tables: `PollResult` (raw, prunable) and `DeviceEvent` (transitions only, permanent).
- **Hardcoding `privileged=True` in icmplib:** Raw sockets require root. `privileged=False` uses SOCK_DGRAM ICMP which works on macOS and most Linux distros without elevated privileges. Always use `privileged=False`.
- **Missing `close_old_connections()` in threads:** Daemon threads share the Django process but have their own DB connection lifecycle. Forgetting this causes `OperationalError: SSL connection has been closed unexpectedly` after the first poll cycle.
- **No `X-Accel-Buffering: no` header:** Without this, nginx (Railway) buffers the SSE stream and the browser receives events in large batches rather than individually.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Concurrent ICMP ping of 254 hosts | Custom async ping loop | `icmplib.multiping(privileged=False)` | Handles SOCK_DGRAM setup, timeout, retry, result parsing; tested 3.0.4 locally |
| NIC enumeration with IP + netmask | Parse `/proc/net/if_inet6` or `ifconfig` output | `netifaces.ifaddresses(iface)[AF_INET]` | Cross-platform, returns structured dict; 0.11.0 verified locally |
| Subnet host list generation | Manual IP arithmetic | `list(ipaddress.IPv4Network(cidr).hosts())` | Handles edge cases (broadcast, network address) |
| SSE reconnect with backoff | Custom XHR polling fallback | `EventSource` + exponential retry | Browser native; auto-reconnects on connection loss |
| State transition detection | Flag files or in-memory state | `DiscoveredDevice.consecutive_failures` + `last_known_state` in DB | Survives `run_monitor` restart; DB is the source of truth |

**Key insight:** The three "hard" problems in this phase (concurrent ping, NIC detection, SSE) all have library solutions that have been verified working on this exact hardware. Don't build custom implementations — the edge cases (subnet edge IPs, SOCK_DGRAM vs SOCK_RAW fallback, SSE retry on network blip) are already handled.

---

## Common Pitfalls

### Pitfall 1: icmplib `privileged=True` on macOS without root

**What goes wrong:** `icmplib.ping(..., privileged=True)` uses `SOCK_RAW` which requires root. Running `python manage.py run_monitor` without `sudo` raises `PermissionError: [Errno 1] Operation not permitted`.

**Why it happens:** The default in older icmplib docs shows `privileged=True`. macOS arm64 in dev is never run as root.

**How to avoid:** Always pass `privileged=False`. Verified: SOCK_DGRAM ICMP is available on this machine without root. [VERIFIED: local test 2026-04-22]

**Warning signs:** `PermissionError` on first poll cycle.

### Pitfall 2: Django runserver swallows SSE stream under WSGI (not a real problem)

**What goes wrong:** Django's dev server appears to buffer streaming responses, preventing real-time SSE delivery.

**Why it happens:** Django's runserver IS threaded by default (Django 4+) — `--nothreading` disables it. Each SSE connection gets its own thread. The response is not buffered if the generator yields immediately. The `Transfer-Encoding: chunked` header is set automatically by Django's WSGI layer.

**How to avoid:** Nothing special needed. The pattern in Pattern 1 works as-is. If testing locally and SSE seems delayed, check that the browser is not caching the stream endpoint — add `Cache-Control: no-cache` header (already in Pattern 1).

**Warning signs:** Events arrive in bursts rather than one by one — usually indicates the generator is not yielding frequently enough, not a buffering issue.

### Pitfall 3: `close_old_connections()` omitted in daemon thread

**What goes wrong:** After the first poll cycle, subsequent DB writes in the daemon thread raise `OperationalError: SSL connection has been closed unexpectedly` or `OperationalError: server closed the connection unexpectedly`.

**Why it happens:** Django's database connection pooling is designed for the request/response lifecycle. Threads that live outside that cycle must manually manage connection health.

**How to avoid:** Call `from django.db import close_old_connections; close_old_connections()` at the top of every polling iteration, before any ORM operation.

**Warning signs:** First poll cycle succeeds; second fails with an OperationalError.

### Pitfall 4: SSE connection blocks another request (misunderstanding threading)

**What goes wrong:** Engineer opens the dashboard (SSE stream connects) and then can't load other pages — requests time out.

**Why it happens:** Only if `--nothreading` is used with `runserver`. Default runserver is threaded; each SSE connection gets its own OS thread.

**How to avoid:** Never use `--nothreading` in development with this module running. The module's README/docs should note this.

**Warning signs:** Second browser tab hangs while first tab has the monitor open.

### Pitfall 5: Subnet sweep on a /16 or /8 takes too long

**What goes wrong:** Engineer is on a corporate network with a /16 or larger subnet. `multiping` on 65534 hosts with `concurrent_tasks=100` takes 655 seconds.

**Why it happens:** The sweep target count is derived from the NIC's actual subnet mask, which can be very large on corporate networks.

**How to avoid:** Cap sweep to /24 at maximum (254 hosts). If the NIC's subnet is larger than /24, sweep only the /24 containing the NIC's IP. Show a warning: "Large subnet detected ({cidr}) — scanning local /24 only." The CONTEXT.md design is for show networks which are always /24 or smaller in practice.

**Warning signs:** Scan "Start" button is clicked and the UI spins for minutes.

### Pitfall 6: MON-03 conflict — FK to existing device models vs. D-05

**What goes wrong:** Planner reads MON-03 ("pull from existing device records via FK") and creates a `GenericForeignKey` linking `DiscoveredDevice` to `Console`, `Amplifier`, etc. This conflicts with D-05 (discover independently from network scan).

**Why it happens:** REQUIREMENTS.md was written before the D-05 decision was made in CONTEXT.md.

**How to avoid:** D-05 takes precedence. `DiscoveredDevice` has no FK to existing module models. The scan creates standalone records. The REQUIREMENTS.md text for MON-03 describes a future integration that may never be needed — D-05 explicitly decided against it.

---

## Code Examples

### NIC detection and subnet derivation

```python
# Source: verified locally — netifaces 0.11.0 + ipaddress stdlib [VERIFIED: 2026-04-22]
import netifaces, ipaddress

def get_scannable_nics():
    """Return list of NIC options for the scan UI dropdown."""
    result = []
    for iface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_INET not in addrs:
            continue
        for addr in addrs[netifaces.AF_INET]:
            ip = addr['addr']
            netmask = addr.get('netmask', '')
            if ip.startswith('127.') or ip.startswith('169.254.') or not netmask:
                continue
            network = ipaddress.IPv4Network(f'{ip}/{netmask}', strict=False)
            # Cap sweep at /24 to avoid enormous subnets on corporate networks
            if network.prefixlen < 24:
                network = ipaddress.IPv4Network(f'{ip}/24', strict=False)
            result.append({
                'interface': iface,
                'ip': ip,
                'subnet': str(network),
                'display': f'{iface} ({ip} — {network})',
            })
    return result
```

### Model definitions

```python
# Source: ARCHITECTURE.md schema sketch + D-05 decision constraint [CITED: .planning/research/ARCHITECTURE.md]
# Place at end of planner/models.py

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


class DiscoveredDevice(models.Model):
    """A device found via subnet scan and added to monitoring."""
    DOMAIN_CHOICES = [
        ('la_network', 'LA Network'),
        ('dante', 'Dante'),
        ('switch', 'Switch'),
        ('unknown', 'Unknown'),
    ]
    STATE_CHOICES = [
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('unknown', 'Unknown'),
    ]
    project = models.ForeignKey('Project', on_delete=models.CASCADE,
                                related_name='discovered_devices')
    label = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField()
    domain = models.CharField(max_length=20, choices=DOMAIN_CHOICES, default='unknown')
    is_active = models.BooleanField(default=True)
    # N=3 state machine
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_known_state = models.CharField(max_length=10, choices=STATE_CHOICES, default='unknown')
    last_seen = models.DateTimeField(null=True, blank=True)
    # Discovery metadata
    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('project', 'ip_address')]
        ordering = ['domain', 'label', 'ip_address']

    def __str__(self):
        return f"{self.label or self.ip_address} ({self.domain})"

    def status(self):
        """Return 'online' | 'flapping' | 'offline' | 'unknown' for UI rendering."""
        if self.last_known_state == 'online':
            return 'online'
        if 0 < self.consecutive_failures < 3:
            return 'flapping'
        if self.consecutive_failures >= 3:
            return 'offline'
        return 'unknown'

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


class PollResult(models.Model):
    """Raw poll result — append-only, one row per poll per device."""
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


class DeviceEvent(models.Model):
    """State transition events — the session history the engineer reads."""
    EVENT_CHOICES = [
        ('ONLINE', 'Came online'),
        ('OFFLINE', 'Went offline'),
        ('SCAN_STARTED', 'Network scan started'),
        ('MONITOR_STARTED', 'Monitor started'),
    ]
    device = models.ForeignKey(DiscoveredDevice, on_delete=models.CASCADE,
                               related_name='events', null=True, blank=True)
    session = models.ForeignKey(MonitorSession, on_delete=models.CASCADE,
                                related_name='events')
    occurred_at = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    details = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=['session', 'occurred_at'])]
        ordering = ['-occurred_at']

    def as_sse_dict(self):
        return {
            'id': self.pk,
            'type': self.event_type,
            'device_id': self.device_id,
            'device_name': self.device.label if self.device else None,
            'occurred_at': self.occurred_at.isoformat(),
            'details': self.details,
        }
```

### URL registration pattern (mirrors comm-config and mic-tracker)

```python
# Add to planner/urls.py — follows existing path registration style
path('network-monitor/', views.network_monitor_view, name='network_monitor'),
path('network-monitor/stream/', views.monitor_stream_view, name='monitor_stream'),
path('network-monitor/scan/', views.trigger_scan_view, name='network_monitor_scan'),
path('network-monitor/devices/add/', views.add_monitor_devices_view, name='add_monitor_devices'),
path('network-monitor/devices/<int:device_id>/remove/', views.remove_monitor_device_view, name='remove_monitor_device'),
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Django Channels + Redis for push | `StreamingHttpResponse` SSE for one-directional push | Decision made pre-Phase-1 | No Redis dependency; works under dev `runserver` |
| `easysnmp` (abandoned 2021) | `pysnmp` (LeXtudio fork, v7.1.24) | 2022 (LeXtudio takeover) | Phase 2 concern; not needed in Phase 1 |
| `apscheduler` in-process scheduler | `run_monitor` management command | Architecture decision | Cleaner lifecycle; separate OS process from web server |
| icmplib `privileged=True` (docs default) | `privileged=False` (SOCK_DGRAM) | icmplib 2.x added SOCK_DGRAM | No root required; verified on macOS arm64 |

**Deprecated/outdated:**
- `easysnmp`: requires system Net-SNMP library, effectively abandoned — use `pysnmp` (Phase 2)
- `netaudio` for Dante clock status: protocol is reverse-engineered and unreliable — Phase 3 only, advisory use

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `privileged=False` ICMP works on all show laptops (macOS + Windows + Linux) | Standard Stack | Linux may require `net.ipv4.ping_group_range` sysctl; Windows may need different socket approach. Verified macOS arm64 only. [ASSUMED for non-macOS] |
| A2 | 10-second default poll interval is appropriate for Phase 1 | run_monitor Pattern | Too fast: DB bloat; too slow: misses brief outages. Should be user-configurable via `--interval` flag. [ASSUMED as appropriate default] |
| A3 | A /24 cap on subnet sweep is safe for all show networks | NIC sweep Pattern | Some show networks use /22 or /23 subnets legitimately. The cap prevents long sweeps but may miss devices outside the /24. [ASSUMED: show networks are always /24 or tighter in practice] |

---

## Open Questions

1. **Where does the "Monitor not running" state come from?**
   - What we know: The UI-SPEC defines a message "Monitor is not running. Start it with: python manage.py run_monitor" but there is no server-side state indicating whether `run_monitor` is currently executing.
   - What's unclear: How does the dashboard distinguish "monitor not started yet" from "no devices discovered yet"? Both result in an empty device list.
   - Recommendation: `MonitorSession` with `ended_at__isnull=True` indicates an active session. If no such session exists for the current project, show the "not running" message. `run_monitor` creates the session on start and sets `ended_at` on `KeyboardInterrupt`.

2. **Session history scope: per-MonitorSession or all-time?**
   - What we know: UI-SPEC shows a session history timeline. ARCHITECTURE.md defines `MonitorSession` as a single `run_monitor` invocation.
   - What's unclear: Does the timeline show only the current session's events, or all events since the last dashboard load?
   - Recommendation: Show current session events only. Previous sessions are accessible by filtering `MonitorSession` objects — a future feature.

3. **Alert banner persistence across page reload?**
   - What we know: The UI-SPEC says dismiss removes from banner. Devices with `consecutive_failures >= 3` remain red in the card.
   - What's unclear: If the engineer reloads the page, do active alerts re-appear in the banner?
   - Recommendation: On dashboard load, query `DeviceEvent.objects.filter(event_type='OFFLINE', session=current_session)` and show banners for devices that have not come back online. This ensures alerts survive page reload without a separate `acknowledged` field (simpler model).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.x | All code | Yes | 3.14.0 | — |
| Django | Web server + ORM | Yes | 5.2.4 | — |
| `icmplib` | ICMP ping, subnet sweep | Yes (installed in venv) | 3.0.4 | `subprocess ping` — fragile, not recommended |
| `netifaces` | NIC enumeration | Yes (installed in venv) | 0.11.0 | `socket.if_nameindex()` gives names but not IPs; `subprocess ifconfig` parsing is fragile |
| SOCK_DGRAM ICMP | `icmplib privileged=False` | Yes | macOS arm64 | Use `privileged=True` (requires root — not viable for dev) |
| PostgreSQL | Django ORM | Yes (Homebrew) | 14.22 | SQLite (already in repo as db.sqlite3 for local dev) |
| `threading` (stdlib) | Daemon poller thread | Yes | stdlib | — |
| `ipaddress` (stdlib) | Subnet calculation | Yes | stdlib | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:**
- `netifaces` is not in `requirements.txt` yet — must be added. Fallback to ifconfig parsing is too fragile.
- `icmplib` is not in `requirements.txt` yet — must be added.

---

## Validation Architecture

`nyquist_validation` is set to `false` in `.planning/config.json`. This section is skipped.

---

## Security Domain

This module runs on a local laptop on a show network, not exposed to the internet. Standard security controls apply to the Django layer (login_required, project scoping), but the network polling itself is read-only (ICMP ping, no authentication required on target devices).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `@login_required` / `@staff_member_required` on all monitor views |
| V3 Session Management | yes | Handled by Django's existing session framework |
| V4 Access Control | yes | `request.current_project` scoping — queries always filter by project |
| V5 Input Validation | yes | NIC name and device IP validated via `netifaces.interfaces()` allowlist and `GenericIPAddressField` |
| V6 Cryptography | no | No sensitive data beyond existing Django session cookies |

### Known Threat Patterns for ICMP + SSE Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthenticated SSE stream access | Information Disclosure | `@login_required` on `monitor_stream_view` |
| SSE endpoint as port scanner (crafted subnet input) | Tampering | NIC must be from `get_scannable_nics()` allowlist; subnet derived server-side from trusted NIC data, not from user input |
| Project data leakage via SSE | Information Disclosure | All DB queries scoped to `request.current_project` |

---

## Sources

### Primary (HIGH confidence)

- icmplib 3.0.4 — verified locally: `icmplib.ping('127.0.0.1', privileged=False)` works on macOS arm64 [VERIFIED: 2026-04-22]
- icmplib 3.0.4 — `multiping` and `async_multiping` verified locally [VERIFIED: 2026-04-22]
- netifaces 0.11.0 — `ifaddresses(iface)[AF_INET]` returns `{'addr': ..., 'netmask': ..., 'broadcast': ...}` verified locally [VERIFIED: 2026-04-22]
- Django 5.2.4 `StreamingHttpResponse` — SSE headers verified, `content_type='text/event-stream'` works [VERIFIED: 2026-04-22]
- Django 5.2.4 runserver threading — default is threaded (`--nothreading` disables); verified via `add_arguments` source inspection [VERIFIED: 2026-04-22]
- SOCK_DGRAM ICMP availability — verified on this macOS arm64 machine without root [VERIFIED: 2026-04-22]
- Project research: `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` [CITED: 2026-04-21]
- Phase decisions: `.planning/phases/01-foundation/01-CONTEXT.md` [CITED: 2026-04-22]
- UI contract: `.planning/phases/01-foundation/01-UI-SPEC.md` [CITED: 2026-04-22]
- Existing codebase patterns: `planner/views.py`, `planner/urls.py`, `planner/management/commands/amplifiers.py` [VERIFIED: 2026-04-22]

### Secondary (MEDIUM confidence)

- Django StreamingHttpResponse SSE pattern: https://minimalistdjango.com/TIL/2024-04-21-server-sent-events/ [CITED: .planning/research/ARCHITECTURE.md]
- HTMX SSE Extension (official docs): https://htmx.org/extensions/sse/ — referenced but NOT used in this phase; plain EventSource chosen [CITED]
- `close_old_connections()` for Django threads: Django docs on database connections in long-running processes [ASSUMED for specific wording]

### Tertiary (LOW confidence)

- `icmplib privileged=False` on Windows and Linux — verified macOS arm64 only; other platforms assumed to work based on icmplib documentation [ASSUMED for non-macOS]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — icmplib, netifaces, StreamingHttpResponse all verified locally
- Architecture: HIGH — two-process model is clear; patterns all verified
- Pitfalls: HIGH — Pitfalls 1/3/4/6 verified against actual code; Pitfall 5 based on ipaddress stdlib behavior
- MON-03 conflict: HIGH — clear reading of CONTEXT.md D-05 vs REQUIREMENTS.md

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (stable stack; no fast-moving dependencies)
