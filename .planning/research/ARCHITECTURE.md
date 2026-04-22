# Architecture: Network Health Monitor

**Domain:** Multi-protocol network monitoring module in an existing Django 5.x app
**Researched:** 2026-04-21
**Overall confidence:** HIGH for component structure and data model; MEDIUM for Dante-specific protocol details

---

## Core Architectural Constraint

ShowStack runs on Railway. The monitoring targets show networks that are local (Dante, LA Net, switches). The engineer's laptop is the bridge — it runs a browser pointed at a **locally-running Django dev server**, not the Railway instance. This inverts the typical "cloud SaaS" model: the monitoring process must be a local process that can reach `192.168.x.x` and multicast subnets directly.

**Consequence:** The architecture is designed for `python manage.py runserver` on a laptop joined to the show network — not for Railway deployment. The Railway instance remains the production host for all other modules. The monitor is a locally-executed mode.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│  Engineer's Laptop (on show network)                            │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Django process  (python manage.py runserver)             │  │
│  │                                                           │  │
│  │  ┌─────────────────┐    ┌──────────────────────────────┐ │  │
│  │  │  Web layer       │    │  Poll engine (threads)       │ │  │
│  │  │  - Views         │    │  - ICMPPoller (all devices)  │ │  │
│  │  │  - SSE endpoint  │◄───│  - SNMPPoller (switches)     │ │  │
│  │  │  - REST API      │    │  - mDNSWatcher (Dante)       │ │  │
│  │  └────────┬─────────┘    └──────────────┬───────────────┘ │  │
│  │           │                             │                 │  │
│  │           └──────────┐  ┌───────────────┘                 │  │
│  │                      ▼  ▼                                 │  │
│  │              ┌───────────────┐                            │  │
│  │              │  PostgreSQL    │  (local SQLite or          │  │
│  │              │  (or SQLite)   │   Railway pg via tunnel)   │  │
│  │              └───────────────┘                            │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Browser (same laptop or another device on same LAN)           │
│  - Dashboard page fetches SSE stream from Django               │
│  - Status indicators update in place via HTMX + SSE            │
└─────────────────────────────────────────────────────────────────┘

Show network devices (reachable from laptop):
  Dante endpoints  ──►  mDNS multicast (224.0.0.251:5353)
  LA Net amps      ──►  ICMP ping
  Switches         ──►  SNMP v2c/v3 (UDP 161)
```

---

## Component Boundaries

| Component | Responsibility | Lives In | Communicates With |
|-----------|---------------|----------|-------------------|
| Poll Engine | Executes periodic network checks; writes results to DB | Django process, background threads | Network devices (direct), PostgreSQL |
| ICMP Poller | Ping-based reachability for all device types (amps, Dante, switches) | Thread inside poll engine | IP network |
| SNMP Poller | Port status, link speed, error counters from switches | Thread inside poll engine | Switch SNMP agent (UDP 161) |
| mDNS Watcher | Continuous Dante device discovery + presence tracking | Thread inside poll engine | mDNS multicast |
| Web Layer | Serves dashboard, SSE stream, REST endpoints | Django views | PostgreSQL, browser |
| SSE Endpoint | Pushes status deltas to connected browsers | Django async view (StreamingHttpResponse) | PostgreSQL (reads latest state) |
| Dashboard UI | Status display, alert banner, session timeline | Browser (HTMX + SSE extension) | SSE endpoint |
| Django Admin | Device registration, threshold config | showstack_admin_site | PostgreSQL |

---

## Polling Architecture Decision

### Recommendation: Django management command as long-running poller

Do not use Celery, Django-Q, or APScheduler for this module. Rationale:

1. **No broker needed.** Adding Redis just for network polling is excessive for a laptop-local tool.
2. **No Railway complexity.** Celery workers on Railway cannot reach the show network — they would need to run locally anyway.
3. **Single process.** The monitoring session is inherently single-laptop. Race conditions from multiple workers are not a concern.
4. **Simple lifecycle.** The engineer starts monitoring, uses it for the show day, stops it. A management command maps cleanly to that lifecycle.

**Pattern:**

```
python manage.py run_monitor
```

This command starts a long-running process that:
- Spawns one daemon thread per poller type (ICMP, SNMP, mDNS)
- Each thread runs an infinite loop: poll → write to DB → sleep(interval)
- Main thread blocks on `threading.Event` so `Ctrl+C` terminates cleanly
- All threads are daemon threads — they die when the main process exits

**Why not AppConfig.ready():** `ready()` fires for every Gunicorn worker and every management command. On Railway (multi-worker), this would spawn multiple polling threads. On local dev, `runserver` calls `ready()` twice (auto-reloader). Using a dedicated management command gives explicit lifecycle control.

**Why not threading inside runserver:** `runserver` is for serving HTTP. Mixing a polling engine into the request-handling process is fragile; a crash in the poller could affect request serving. The management command runs as a separate OS process alongside `runserver`.

**Operational model for the engineer:**

```bash
# Terminal 1 — web server
python manage.py runserver

# Terminal 2 — monitor poller
python manage.py run_monitor --project-id 42 --interval 10
```

Or wrap both in a single management command that forks the poller as a subprocess before starting the dev server — simpler UX, evaluated during build.

---

## Real-Time Push: Server-Sent Events (SSE)

### Recommendation: SSE with Django's StreamingHttpResponse + HTMX SSE extension

**Why SSE over WebSockets:**
- Monitoring is one-directional: server pushes status to browser. Browsers never need to send data back over the stream.
- SSE works over standard HTTP — no ASGI server needed for basic functionality.
- HTMX has a first-class SSE extension that swaps DOM fragments on incoming events, which matches the status-card update pattern exactly.
- No Django Channels installation required (Channels adds `daphne`/`uvicorn` + Redis for the channel layer).

**Why SSE over AJAX polling:**
- AJAX polling (setInterval every N seconds) creates thundering herd if many engineers have the dashboard open.
- SSE holds one persistent connection per browser tab and the server decides when to push.
- Network latency for a local request is negligible — SSE is cleanly reactive.

**Implementation shape:**

```python
# views.py
import json, time
from django.http import StreamingHttpResponse

def monitor_stream(request):
    project = get_active_project(request)

    def event_generator():
        last_seq = 0
        while True:
            events = DeviceEvent.objects.filter(
                project=project, id__gt=last_seq
            ).order_by('id')[:50]
            for ev in events:
                last_seq = ev.id
                data = json.dumps(ev.as_dict())
                yield f"data: {data}\n\n"
            time.sleep(2)

    return StreamingHttpResponse(
        event_generator(),
        content_type='text/event-stream'
    )
```

HTMX in the template subscribes and swaps status cards in place. No JavaScript framework needed.

**Note on ASGI:** Django's StreamingHttpResponse works under both WSGI (gunicorn) and ASGI (daphne). For local dev with `runserver`, it works out of the box. The only production constraint (HTTP/2 for many concurrent SSE connections) does not apply here — a show laptop will have at most 2-3 browser tabs open.

---

## Data Model

### Design principles
- `DeviceMonitorTarget` links to existing module models (Console, IODevice, Amplifier, etc.) via GenericForeignKey — avoids duplicating device records.
- `DevicePollResult` is append-only (no updates) — each poll cycle writes a new row. This gives free session history without a separate events table.
- `DeviceEvent` records state transitions only (up→down, down→up) — the event log the engineer reads.
- `MonitorSession` tracks the start/end of each monitoring run for post-show review.

### Schema sketch

```python
class MonitorSession(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

class DeviceMonitorTarget(models.Model):
    """A device registered for monitoring in this project."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    label = models.CharField(max_length=100)       # human name, e.g. "FOH Console"
    ip_address = models.GenericIPAddressField()
    protocol = models.CharField(
        max_length=10,
        choices=[('icmp', 'ICMP'), ('snmp', 'SNMP'), ('dante', 'Dante/mDNS')]
    )
    snmp_community = models.CharField(max_length=64, blank=True)  # v2c
    # Link to existing module device (optional but preferred)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    linked_device = GenericForeignKey('content_type', 'object_id')
    is_active = models.BooleanField(default=True)

class DevicePollResult(models.Model):
    """Raw poll result — append only, one row per poll cycle per device."""
    target = models.ForeignKey(DeviceMonitorTarget, on_delete=models.CASCADE)
    session = models.ForeignKey(MonitorSession, on_delete=models.CASCADE)
    polled_at = models.DateTimeField(auto_now_add=True)
    is_reachable = models.BooleanField()
    latency_ms = models.FloatField(null=True, blank=True)    # ICMP RTT
    # SNMP-specific (null for non-switch targets)
    snmp_data = models.JSONField(null=True, blank=True)      # port table snapshot

    class Meta:
        indexes = [
            models.Index(fields=['target', 'polled_at']),
            models.Index(fields=['session', 'polled_at']),
        ]

class DeviceEvent(models.Model):
    """State transition events — what the engineer reads."""
    target = models.ForeignKey(DeviceMonitorTarget, on_delete=models.CASCADE)
    session = models.ForeignKey(MonitorSession, on_delete=models.CASCADE)
    occurred_at = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=30)   # 'went_offline', 'came_online', 'snmp_error', 'dante_lost'
    details = models.JSONField(default=dict)
    acknowledged = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=['session', 'occurred_at'])]
```

**Storage concern:** At 10-second poll intervals with 50 devices, `DevicePollResult` accumulates 360 rows/hour or ~3,000/show-day. Plain PostgreSQL handles this without TimescaleDB. Add a periodic cleanup task (or management command flag `--retain-days N`) to trim old sessions.

---

## Protocol Library Decisions

### ICMP (ping) — use `icmplib`
- Pure Python, no Net-SNMP dependency.
- Async and synchronous modes; synchronous is fine for threaded polling.
- Works on macOS without raw socket privileges (uses `ping` subprocess fallback on macOS).
- **Confidence:** MEDIUM — confirm `icmplib` works without root on macOS during Phase 1.

### SNMP — use `ezsnmp` (Net-SNMP bindings fork)
- `easysnmp` is abandoned; `ezsnmp` is the maintained fork.
- 4x faster than pure-Python `pysnmp` (native Net-SNMP bindings).
- SNMP v2c is sufficient for entertainment switches (Luminex, Cisco Catalyst, Netgear).
- Required OIDs: `IF-MIB::ifOperStatus`, `IF-MIB::ifSpeed`, `IF-MIB::ifInErrors`, `IF-MIB::ifOutErrors`, `POWER-ETHERNET-MIB::pethPsePortDetectionStatus` (PoE).
- **Constraint:** Requires `net-snmp` system library (`brew install net-snmp` on macOS). Add to `apt-packages` file for Railway, but Railway workers don't run the poller — note this in docs.
- **Confidence:** MEDIUM — ezsnmp on macOS arm64 has had intermittent build issues historically; verify install during Phase 1.

### Dante / mDNS — use `zeroconf` (python-zeroconf)
- The `netaudio` PyPI package wraps `python-zeroconf` and knows Dante's specific mDNS service types (`_netaudio-arc._udp`, `_netaudio-dbc._udp`, `_netaudio-cmc._udp`, `_netaudio-chan._udp`).
- Use `netaudio` for Dante device discovery (device name, IP, channel count).
- For clock master/slave status: Dante does not expose this via any public API. The `netaudio` library is reverse-engineered from Dante Controller network traffic. Clock status is not reliably available. Treat Dante monitoring as discovery + reachability (ICMP) only for now; flag clock monitoring as a research item for a later phase.
- **Confidence:** LOW for clock status. HIGH for device presence detection via mDNS.

---

## Data Flow

```
Poll cycle (every N seconds):
  Thread → ping device → DevicePollResult(is_reachable=True/False, latency_ms=X)
  Thread → compare with previous result → if state changed: DeviceEvent(event_type='went_offline')

SSE stream (browser connected):
  Django view → SELECT DeviceEvent WHERE id > last_seen → yield as SSE data
  Browser (HTMX SSE extension) → swap status card HTML fragment

Dashboard load:
  Django view → SELECT latest DevicePollResult per target → render initial state
  Browser → connect SSE stream → receive deltas going forward

Session history:
  Engineer clicks "End Session" → MonitorSession.ended_at = now()
  History view → SELECT DeviceEvent WHERE session=X ORDER BY occurred_at
```

---

## Build Order (Dependency Chain)

The components have hard dependencies that constrain phase ordering:

```
1. Data models (DeviceMonitorTarget, DevicePollResult, DeviceEvent, MonitorSession)
   └─ Everything else reads/writes these tables

2. ICMP poller + management command scaffold
   └─ Validates poll → DB → SSE pipeline with the simplest protocol
   └─ Unblocks dashboard development (real data flowing)

3. Dashboard UI + SSE endpoint
   └─ Requires data models and at least ICMP poller to have real data
   └─ Unblocks UX iteration

4. SNMP poller
   └─ Requires data models; independent of ICMP poller
   └─ Build after ICMP pipeline is proven; SNMP has higher setup friction

5. mDNS / Dante watcher
   └─ Requires data models; independent of ICMP and SNMP
   └─ Build last — most protocol uncertainty; defer clock status

6. Session history view + alert acknowledgement
   └─ Requires events flowing from all pollers
   └─ Polish phase
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Polling inside AppConfig.ready()
**What happens:** On `runserver`, `ready()` fires twice (auto-reloader). On Railway with multiple gunicorn workers, it fires once per worker. You get N polling threads fighting to write to the same DB rows.
**Instead:** Use a dedicated `run_monitor` management command.

### Anti-Pattern 2: Django Channels for SSE
**What happens:** Channels requires a channel layer (Redis or in-memory), Daphne or Uvicorn as ASGI server, and introduces significant operational complexity. For one-directional server-push with no message fanout needs, this is severe over-engineering.
**Instead:** `StreamingHttpResponse` with a simple DB-polling generator. Works under the existing gunicorn WSGI setup.

### Anti-Pattern 3: Storing raw poll results in the events table
**What happens:** The events table becomes enormous; querying "what happened during the show" requires filtering millions of "still up" no-ops.
**Instead:** Two separate tables — `DevicePollResult` (raw, append-only, prunable) and `DeviceEvent` (state transitions only, permanent record).

### Anti-Pattern 4: New device model for monitor targets
**What happens:** Engineers enter the same device twice — once in Consoles/Amplifiers/IO Devices and again in the monitor. Data drifts; names diverge.
**Instead:** `DeviceMonitorTarget` uses a GenericForeignKey to link to the existing device record. The monitor pulls label and IP from the source-of-truth model. Manual targets (for devices with no corresponding module) are allowed but not the default.

### Anti-Pattern 5: Blocking SNMP calls on the web thread
**What happens:** SNMP v2c GET requests can time out (default 1-2 seconds per device). If SNMP is called from a Django view, the HTTP response hangs for each timed-out switch port.
**Instead:** All polling happens exclusively in background threads. Views only read from the DB. No network I/O in views.

---

## Scalability Notes

This module is designed for a single show network, single engineer, single laptop. Scale concerns are intentionally out of scope. The data model and SSE design would not require changes to support 10 engineers on one show (each opens the dashboard; SSE streams are independent). Supporting 100+ devices requires verifying that the poll thread timing stays within acceptable bounds — a concern for a later phase after basic monitoring works.

---

## Sources

- [Lightweight Django Task Queues in 2025](https://medium.com/@g.suryawanshi/lightweight-django-task-queues-in-2025-beyond-celery-74a95e0548ec) — MEDIUM confidence
- [django-apscheduler PyPI](https://pypi.org/project/django-apscheduler/) — MEDIUM confidence
- [Server-Sent Events — Minimalist Django](https://minimalistdjango.com/TIL/2024-04-21-server-sent-events/) — MEDIUM confidence
- [Django + Gunicorn threading discussion](https://github.com/benoitc/gunicorn/discussions/3202) — MEDIUM confidence (confirms AppConfig.ready() multi-worker hazard)
- [HTMX SSE Extension](https://htmx.org/extensions/sse/) — HIGH confidence (official docs)
- [netaudio PyPI](https://pypi.org/project/netaudio/) — LOW confidence (reverse-engineered Dante protocol)
- [network-audio-controller Technical Details](https://github.com/chris-ritsen/network-audio-controller/wiki/Technical-details) — LOW confidence (community reverse engineering)
- [ezsnmp PyPI](https://pypi.org/project/ezsnmp/) — MEDIUM confidence
- [Dante Network Admin Guide](https://audinateweb.sfo2.cdn.digitaloceanspaces.com/wp-content/uploads/2022/03/dante-information-for-network-admins.pdf) — HIGH confidence (official Audinate)
