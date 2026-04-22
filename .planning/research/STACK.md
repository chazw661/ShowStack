# Technology Stack: Network Health Monitor

**Project:** ShowStack Network Health Monitor  
**Researched:** 2026-04-21  
**Scope:** Libraries needed to add real-time network monitoring (Dante, LA Network/Milan AVB, SNMP switches) to an existing Django 5.x app on Railway.

---

## Critical Architectural Constraint

The Django process running on Railway cannot reach show networks. Show networks are local, air-gapped VLANs. The engineer's laptop bridges the gap by running `python manage.py runserver` locally while connected to the show network. All SNMP, ICMP, and mDNS operations happen on the local Django process — the Railway deployment is not involved in monitoring. This is already documented in PROJECT.md and CLAUDE.md §7b. Every library recommendation below assumes local execution on the engineer's laptop.

---

## Recommended Stack

### 1. Dante Device Discovery — mDNS/Bonjour

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|-----------|
| `zeroconf` | `>=0.148.0` | mDNS listener for Dante service types | HIGH |
| `netaudio` | `0.2.4` | High-level Dante device discovery and status; wraps zeroconf | MEDIUM |

**Why `zeroconf`:** The canonical pure-Python mDNS library, actively maintained by the `python-zeroconf` organization (v0.148.0, October 2025). Home Assistant uses it for all mDNS discovery. `netaudio` itself declares `zeroconf>=0.38.3` as a dependency. It supports asyncio via `AsyncServiceBrowser` and `AsyncZeroconf`, which integrates cleanly with Django's async views.

**Why `netaudio` (0.2.4, March 2026):** The `network-audio-controller` project (`netaudio` on PyPI) is the only Python library that has already reverse-engineered and validated Dante's mDNS service types (`_netaudio-dbc._udp`, `_netaudio-arc._udp`, `_netaudio-cmc._udp`, `_netaudio-chan._udp`) and the binary control protocol on UDP port 4440/4455. It provides device discovery, subscription listing, channel enumeration, device name/latency/sample rate readout, and clock status queries — exactly what the health monitor needs. It is maintained by Christopher Ritsen and was updated March 31, 2026.

**Caution:** `netaudio` is a CLI tool, not a library designed for embedding. Its internals can be imported but the API is not stable. Use it for the discovery/query logic; wrap it in a service layer to isolate ShowStack from API churn.

**What `netaudio` uses for mDNS service types:**
- `_netaudio-dbc._udp` — device browser/controller (main device presence)
- `_netaudio-arc._udp` — ARC routing control (used for subscription commands)
- `_netaudio-cmc._udp` — clock master control
- `_netaudio-chan._udp` — individual channel advertisements

**Dante-specific:** Discovery is not part of AES67 scope. Dante uses Audinate's proprietary mDNS types above. Standard AES67 endpoints (non-Dante) use SAP/SDP for stream announcement — out of scope for this module.

---

### 2. Switch Monitoring — SNMP

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|-----------|
| `pysnmp` | `7.1.24` | SNMP v1/v2c/v3 GET/WALK for switch port status, counters, PoE | HIGH |

**Why `pysnmp` (maintained fork by LeXtudio):** The original `etingof/pysnmp` was abandoned in 2020. LeXtudio Inc. took over maintainership in 2022 and released v7.1.24 on April 18, 2026. It is now published as `pysnmp` on PyPI (the `pysnmp-lextudio` name is deprecated — use `pysnmp`). Supports SNMPv1, v2c, v3 with full MIB handling and asyncio operations.

**Why not `easysnmp`:** Requires native `net-snmp` C library installed on the host (`brew install net-snmp`). For a tool engineers install on their laptops, a pure-Python dependency is much friendlier. EasySNMP is also effectively abandoned (last release 2021). The fork `ezsnmp` exists but has minimal adoption.

**MIBs needed for entertainment switches:**
- `IF-MIB` — interface status, speed, octets, errors (universal)
- `BRIDGE-MIB` — VLAN membership
- `RFC1213-MIB` — standard system info
- `ENTITY-MIB` — physical inventory (optional)
- Luminex-specific MIBs if deeper telemetry is needed (vendor-provided)

**SNMP versions:** Target v2c for Luminex/Netgear; v3 for Cisco in secured environments. `pysnmp` handles both.

---

### 3. LA Network / Milan AVB Device Reachability

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|-----------|
| `icmplib` | `3.0.4` | ICMP ping for LA-amplifier reachability checks | HIGH |

**Why `icmplib`:** Pure Python, no external dependencies, supports `multiping` and `async_multiping` for concurrent checks across many amp IPs. Can operate without root privileges (`privileged=False` uses unprivileged SOCK_DGRAM sockets). The `async_multiping` function integrates with asyncio polling loops.

**Why not deeper LA Network / Milan AVB protocol integration:** L-Acoustics' open-source AVDECC library (`L-Acoustics/avdecc`) is C++17 — no Python bindings exist. There is no Python library for IEEE 1722.1 AVDECC as of April 2026. L-Acoustics Network Manager owns that protocol space. ShowStack's scope is connectivity-only (per PROJECT.md), which `icmplib` covers completely.

**Also use `icmplib` for Dante device reachability verification:** mDNS discovery confirms presence; a ping round-trip confirms the device is actually responding on the network. Both checks together give a more reliable health signal.

---

### 4. Real-Time Dashboard Push

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|-----------|
| Django async `StreamingHttpResponse` + SSE | built-in (Django 5.x) | Push device status updates to browser | HIGH |
| `daphne` (ASGI) | `>=4.0` | ASGI server that enables async views and streaming | HIGH |

**Recommendation: SSE over Django Channels or WebSockets.**

The monitoring dashboard is read-only push: the server sends status updates to the browser; the browser never sends monitoring commands back. That is exactly the use case SSE was designed for. SSE requires no Redis, no Channels, no additional processes, and no extra infrastructure.

**Implementation pattern:**

```python
# views.py
import asyncio
from django.http import StreamingHttpResponse

async def status_stream(request):
    async def event_stream():
        while True:
            data = await get_current_network_status(request)  # async DB read
            yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(5)
    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
```

Requires Django running under Daphne (ASGI), which ShowStack already uses or can trivially add since it deploys on Railway with a `Procfile`. The ASGI switch does not break existing WSGI-style views.

**Why not Django Channels:** Channels adds Redis as a required dependency, a separate worker process, and significant operational complexity. For a local-running tool that pushes to one or two browser tabs, that overhead is not justified. Channels also has a history of breaking API changes between major versions.

**Why not polling from the browser:** A polling interval of 5 seconds means every engineer on the show has their browser making HTTP requests every 5 seconds. SSE keeps one persistent connection per browser tab and the server pushes only on state changes — lower overhead and lower latency.

**Frontend:** Plain `EventSource` API (built into every browser, no npm dependency). HTMX can also handle SSE natively with `hx-ext="sse"` if ShowStack is using HTMX elsewhere.

---

### 5. Background Network Polling

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|-----------|
| `apscheduler` | `>=3.10` | In-process periodic polling of devices (SNMP, ping, mDNS) | MEDIUM |

**Why `apscheduler` over Celery:** Celery requires a Redis broker and a separate worker process. For a local development tool running `python manage.py runserver`, standing up Redis and a Celery worker adds friction that is inappropriate for a laptop-deployed tool. APScheduler runs inside the Django process with no external dependencies, scheduling polling tasks every N seconds without a broker.

**Polling architecture:** A single background `AsyncIOScheduler` job collects status from all configured devices and writes results to the database. SSE views read from the database (or an in-memory cache) and push changes to connected browsers. This separates the polling concern from the push concern cleanly.

**Caveat:** In a multi-worker production deployment (Railway, gunicorn multi-process), in-process schedulers run in every worker, causing duplicate polls. Since this module is designed for local use (`runserver`), single-process execution is the norm. If production deployment ever needs background polling, migrating to Celery Beat is straightforward — the polling logic does not need to change, only the scheduler wrapper.

---

### 6. Session History / Event Storage

| Technology | Version | Purpose | Confidence |
|------------|---------|---------|-----------|
| Native Django ORM + PostgreSQL | Django 5.x built-in | Event log table for show-day history | HIGH |

**Recommendation: plain Django model with `timestamp` index, not TimescaleDB.**

**Rationale:** TimescaleDB is a separate PostgreSQL extension that requires a different Railway service (the Railway-managed Postgres does not have the TimescaleDB extension enabled by default). Adding a second database service for a feature that stores at most a few thousand events per show day is not justified. A standard Django model with a `db_index=True` on `timestamp` and a `show_session` FK scoping queries to the current session will handle years of data without performance issues.

```python
class NetworkEvent(models.Model):
    show_session = models.ForeignKey('planner.Project', on_delete=models.CASCADE)
    timestamp    = models.DateTimeField(auto_now_add=True, db_index=True)
    device_name  = models.CharField(max_length=255)
    event_type   = models.CharField(max_length=50)  # UP, DOWN, CLOCK_LOST, etc.
    details      = models.JSONField(default=dict)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['show_session', '-timestamp'])]
```

**Retention:** Add a management command or APScheduler job to prune records older than 30 days. No TimescaleDB automatic compression needed at this event volume.

**When to reconsider:** If the project ever stores per-second metrics from dozens of SNMP interfaces (bandwidth graphs, error rate over time), TimescaleDB becomes worth the operational overhead. That is not in scope for this milestone.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Dante discovery | `zeroconf` + `netaudio` | `aiozeroconf` | Abandoned; `zeroconf` absorbed async support natively |
| SNMP | `pysnmp` (LeXtudio) | `easysnmp` / `ezsnmp` | Requires native net-snmp C lib; easysnmp abandoned 2021 |
| SNMP | `pysnmp` (LeXtudio) | `puresnmp` | No SNMPv3 support; smaller ecosystem |
| Reachability | `icmplib` | `pythonping` | Less maintained, no async multiping |
| Reachability | `icmplib` | subprocess `ping` | Fragile OS-specific output parsing, slow |
| Real-time push | SSE via `StreamingHttpResponse` | Django Channels | Requires Redis broker + worker process; bidirectional not needed |
| Real-time push | SSE | Long-polling | Higher request overhead, more complex client logic |
| Background polling | `apscheduler` | Celery + Redis | Celery requires external broker; overkill for local tool |
| History storage | Native PostgreSQL | TimescaleDB | Requires separate Railway service; unnecessary for event volumes |
| Milan AVB | `icmplib` (ping only) | `L-Acoustics/avdecc` C++ lib | C++17 only, no Python bindings; out of scope per PROJECT.md |

---

## Installation

```bash
# Core monitoring libraries
pip install "zeroconf>=0.148.0"
pip install "netaudio==0.2.4"
pip install "pysnmp>=7.0,<8.0"
pip install "icmplib>=3.0"
pip install "apscheduler>=3.10,<4.0"

# No additional infrastructure required for local dev
# (no Redis, no Celery worker, no TimescaleDB)
```

For production Railway deployment, no changes to existing `requirements.txt` pattern are needed beyond the above additions.

---

## Open Questions

1. **SNMP community strings / v3 credentials:** These are per-project configuration. The data model needs fields on a `NetworkSwitch` model to store SNMP version, community string (v2c), or auth/priv credentials (v3). These must be stored encrypted or at minimum flagged as sensitive in the admin.

2. **mDNS multicast on multi-VLAN networks:** mDNS is link-local (224.0.0.251). If Dante lives on a separate VLAN, the laptop's interface must be on that VLAN for discovery to work. The engineer's network access level determines what `zeroconf` can see — a documentation/UX concern, not a library limitation.

3. **`netaudio` clock status query:** Dante clock master/slave state is readable via the `_netaudio-cmc._udp` service and binary protocol. `netaudio` exposes device-level info but clock domain detail may require direct UDP queries. Validate in Phase 1 implementation against real hardware before committing to clock-status UI.

4. **`apscheduler` v3 vs v4:** APScheduler v4 (beta as of 2025) is a significant rewrite with a different API. Pin to `>=3.10,<4.0` until v4 is stable and has Django integration guidance.

---

## Sources

- python-zeroconf: https://github.com/python-zeroconf/python-zeroconf (v0.148.0, Oct 2025)
- netaudio: https://pypi.org/project/netaudio/ (v0.2.4, March 2026); https://github.com/chris-ritsen/network-audio-controller
- Dante mDNS service types: https://github.com/chris-ritsen/network-audio-controller/wiki/Technical-details
- pysnmp (LeXtudio): https://pypi.org/project/pysnmp/ (v7.1.24, April 2026); https://github.com/lextudio/pysnmp
- icmplib: https://github.com/ValentinBELYN/icmplib (v3.0.4)
- L-Acoustics AVDECC (C++, for reference): https://github.com/L-Acoustics/avdecc
- Django SSE with async StreamingHttpResponse: https://valberg.dk/django-sse-postgresql-listen-notify.html
- Railway Django + Celery: https://dev.to/techbychoiceorg/django-celery-and-redis-on-railway-214h
- TimescaleDB on Railway: https://railway.com/deploy/timescaledb
