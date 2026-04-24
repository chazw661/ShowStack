# Phase 2: Switch SNMP - Research

**Researched:** 2026-04-24
**Domain:** SNMP v2c polling, IF-MIB bandwidth counters, Django model design, agent threading, show mode state
**Confidence:** HIGH (pysnmp API, IF-MIB OIDs, architecture); MEDIUM (Luminex-specific behavior)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Credentials entered via the dashboard — a settings panel accessible from a gear icon in the dashboard header. No admin panel entry required.
- **D-02:** Per-project credentials — one SNMP v2c community string shared by all switches in the project. No per-switch override.
- **D-03:** SNMP v2c only — community string authentication. Covers the target switch brands: Luminex, Netgear, and Ubiquiti entertainment switches. No v3 support in this phase.
- **D-04:** Both auto-detect and manual entry — devices assigned to the Switch domain from the Phase 1 ping sweep automatically get SNMP-polled, AND engineers can manually add switch IPs via the settings panel. Unassigned devices remain in the Unassigned section until reassigned.
- **D-05:** Expandable switch cards — collapsed view shows switch name, IP, port count summary (e.g., "24 ports - 22 up - 0 err"). Click to expand reveals a per-port table.
- **D-06:** Per-port table columns: port number, up/down status dot, link speed (100M/1G/10G), bandwidth utilization %. Error counters accessible on click/hover as secondary detail, not inline in the table.
- **D-07:** Three-state toggle (Setup / Show / Wrap) in the dashboard header bar, next to the domain rollup pills. Always visible regardless of scroll.
- **D-08:** Only device-offline (N=3 consecutive failures) is critical and always fires in any mode. All other alerts — port status changes, bandwidth warnings, error counter spikes, link speed changes — are non-critical and suppressed in Setup and Wrap modes.
- **D-09:** Subtle amber banner appears below the header when in Setup or Wrap mode: "Setup mode — non-critical alerts suppressed". Banner disappears in Show mode.
- **D-10:** Bandwidth utilization displayed as a color-coded percentage per port: green (<70%), amber (70-90%), red (>90%).
- **D-11:** Thresholds are fixed at 70%/90% — not configurable by the engineer. Standard network monitoring thresholds.

### Claude's Discretion
- Settings panel layout and styling
- Error counter detail display (tooltip vs expandable row vs modal)
- SNMP polling interval (within reasonable bounds for entertainment switches)
- How manual switch IP entry UI works within the settings panel
- Show mode toggle visual design (segmented control, radio buttons, etc.)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SW-01 | Switch port up/down status and link speed displayed via SNMP polling | IF-MIB ifOperStatus (1.3.6.1.2.1.2.2.1.8) + ifHighSpeed (1.3.6.1.2.1.31.1.1.1.15) |
| SW-02 | Per-project SNMP credential configuration (community string for v2c) | New ProjectSNMPConfig model on Project FK; per-project CharField stored plaintext (see Architecture Patterns) |
| SW-03 | Port error counter tracking over time | IF-MIB ifInErrors/ifOutErrors accumulated in SwitchPortSnapshot per poll cycle |
| SW-04 | Bandwidth utilization warnings at configurable thresholds (default 70%/90%) | Delta calculation from ifHCInOctets/ifHCOutOctets; fixed 70/90 per D-11 |
| DASH-04 | Show mode toggle (Setup / Show / Wrap) suppresses non-critical alerts during load-in/out | show_mode field on MonitorSession; JS localStorage mirrors server state |
</phase_requirements>

---

## Summary

Phase 2 adds SNMP-based switch port monitoring on top of the Phase 1 ICMP/agent infrastructure. The engineer-facing work is a settings panel (gear icon) for entering one community string per project, plus expandable switch cards that show per-port status, link speed, and color-coded bandwidth utilization. A three-state show mode toggle suppresses non-critical alerts during load-in and load-out.

The backend work is: two new models (ProjectSNMPConfig and SwitchPortSnapshot), a parallel SNMP polling thread inside the existing run_monitor agent, three new agent API endpoints (push SNMP results, receive snmp-settings, set show-mode), and an extension to the monitor_status_view JSON payload to include port data.

pysnmp 7.1.25 (LeXtudio fork) is the correct library. It is async-first; the integration pattern is a dedicated daemon thread in run_monitor that calls `asyncio.run()` per poll cycle. This is safe because each daemon thread has no running event loop of its own, and `asyncio.run()` creates and closes its own event loop per call. The existing run_monitor architecture (single while-loop, pushes to Django API via HTTP) maps cleanly to a second daemon thread for SNMP alongside the existing ICMP thread.

**Primary recommendation:** Add a dedicated SNMP daemon thread to run_monitor that polls all Switch-domain devices every 30 seconds using pysnmp's asyncio `get_cmd` with explicitly listed OIDs (not a full MIB walk), then POSTs results to a new `/api/snmp-results/` endpoint. Store the last snapshot per port in SwitchPortSnapshot; the dashboard reads port data from the same `monitor_status` poll every 3 seconds.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SNMP v2c polling (get OIDs) | Agent (run_monitor daemon thread) | — | All network I/O is local; agent runs on show laptop |
| IF-MIB counter delta / bandwidth calc | Agent | — | Agent has both consecutive readings; avoids double-store |
| SNMP credentials storage | Django (DB model) | — | Needs to persist across agent restarts |
| Community string retrieval by agent | Django API (GET /api/snmp-settings/) | — | Agent fetches creds at startup; stays decoupled |
| Port status / bandwidth display | Django (JSON payload extension) | — | Dashboard reads from DB via monitor_status poll |
| Show mode storage | Django (MonitorSession.show_mode field) | localStorage mirror | Server is authoritative; JS caches for instant UI response |
| Show mode alert suppression | Django (agent_poll_results + agent_snmp_results) | — | Suppression logic lives server-side, not in agent |
| Settings panel UI | Browser (vanilla JS in template) | — | Matches existing Phase 1 pattern |
| Manual switch IP entry | Browser (settings panel) → Django API | — | POST to /api/add-switch/ creates DiscoveredDevice |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pysnmp | 7.1.25 [VERIFIED: PyPI 2026-04-24] | SNMP v2c GET for IF-MIB OIDs | LeXtudio maintained fork; pure Python; no net-snmp C dep required |
| Django 5.x ORM | (already installed) | SwitchPortSnapshot, ProjectSNMPConfig models | Matches existing model pattern |
| requests | (already installed) | Agent HTTP push to Django API | Already used in run_monitor |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio (stdlib) | Python 3.11+ | Run pysnmp from daemon thread via asyncio.run() | Required by pysnmp v7 async-first API |
| threading (stdlib) | Python 3.11+ | SNMP daemon thread parallel to ICMP loop | Existing pattern in run_monitor architecture |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pysnmp 7.x async via asyncio.run() | easysnmp | easysnmp requires native net-snmp C lib via brew; not portable; abandoned 2021 |
| pysnmp 7.x async via asyncio.run() | puresnmp | No async; simpler API but less ecosystem; no GetBulk support |
| Dedicated SNMP daemon thread | Full asyncio rewrite of run_monitor | Asyncio rewrite is more invasive; daemon thread is additive and isolated |

**Installation:**
```bash
pip install "pysnmp>=7.1,<8.0"
```

**Version verification:** pysnmp 7.1.25 confirmed current as of 2026-04-24. [VERIFIED: PyPI registry]

---

## Architecture Patterns

### System Architecture Diagram

```
AGENT (run_monitor on show laptop)
│
├── ICMP Thread (existing) ──────────────── pings all devices every 10s
│   └── POST /api/poll-results/
│
├── SNMP Thread (NEW) ───────────────────── polls switch OIDs every 30s
│   ├── GET /api/snmp-settings/  ←── fetch community string + switch IPs
│   ├── asyncio.run(poll_all_switches())  ← pysnmp getCmd per switch
│   └── POST /api/snmp-results/  ──────→  Django stores SwitchPortSnapshot
│
└── Signal handler (Ctrl+C) → sets stop_event, stops both threads

DJANGO (cloud API)
│
├── GET  /api/snmp-settings/     ←── agent fetches community string + switch IPs
├── POST /api/snmp-results/      ←── agent pushes port data per switch
├── POST /api/show-mode/         ←── browser POSTs mode change (Setup/Show/Wrap)
├── POST /api/snmp-settings/     ←── browser saves community string (session auth)
├── POST /api/add-switch/        ←── browser adds manual switch IP (session auth)
│
├── GET  /network-monitor/status/  ←── browser polls every 3s
│   └── returns devices[] + events[] + switch_ports{} (EXTENDED in Phase 2)
│
└── DB
    ├── ProjectSNMPConfig (project FK, community_string, updated_at)
    └── SwitchPortSnapshot (discovered_device FK, session FK, port data per port)

BROWSER (dashboard)
├── AJAX poll /status/ every 3s → updates switch cards + port tables in DOM
├── Settings panel → GET/POST snmp-settings, POST add-switch
└── Show mode toggle → POST /api/show-mode/ + localStorage cache
```

### Recommended Project Structure

New files / changes in Phase 2 (following Phase 1 patterns):

```
planner/
├── models.py              # Add ProjectSNMPConfig, SwitchPortSnapshot at end
├── views_monitor.py       # Add 5 new endpoints
├── urls.py                # Register new paths
├── admin.py               # Register ProjectSNMPConfig, SwitchPortSnapshot
├── admin_ordering.py      # Add new models to order_map
├── management/
│   └── commands/
│       └── run_monitor.py # Add SNMP daemon thread + /api/snmp-settings fetch
templates/planner/
└── network_monitor.html   # Add settings panel, show mode toggle, switch card expansion
```

No new apps, no new files outside existing directories.

---

### Pattern 1: SNMP v2c GetCmd for Specific OIDs

Use `get_cmd` (not a walk) with explicit OIDs per port. For a 24-port switch, fetch all port OIDs in one GetBulk or as a multi-OID GET. Avoid walking the full MIB — too slow, not needed.

```python
# Source: Context7 /lextudio/pysnmp — verified pysnmp v7.1.x hlapi.asyncio API
import asyncio
from pysnmp.hlapi.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity, bulkCmd,
)

# OIDs to poll per switch (IF-MIB, RFC 2863 + RFC 2233)
# ifOperStatus.N: 1=up, 2=down — OID 1.3.6.1.2.1.2.2.1.8.{port_index}
# ifHighSpeed.N: speed in Mbps — OID 1.3.6.1.2.1.31.1.1.1.15.{port_index}
# ifHCInOctets.N: 64-bit in-counter — OID 1.3.6.1.2.1.31.1.1.1.6.{port_index}
# ifHCOutOctets.N: 64-bit out-counter — OID 1.3.6.1.2.1.31.1.1.1.10.{port_index}
# ifInErrors.N: error counter — OID 1.3.6.1.2.1.2.2.1.14.{port_index}
# ifDescr.N: port label — OID 1.3.6.1.2.1.2.2.1.2.{port_index}

IF_MIB_WALK_ROOTS = [
    ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.8')),   # ifOperStatus table
    ObjectType(ObjectIdentity('1.3.6.1.2.1.31.1.1.1.15')), # ifHighSpeed table
    ObjectType(ObjectIdentity('1.3.6.1.2.1.31.1.1.1.6')),  # ifHCInOctets table
    ObjectType(ObjectIdentity('1.3.6.1.2.1.31.1.1.1.10')), # ifHCOutOctets table
    ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.14')),   # ifInErrors table
]

async def poll_switch(ip, community_string, timeout=5):
    """Poll a single switch, return dict of port_index -> port data."""
    snmp_engine = SnmpEngine()
    results = {}

    try:
        for oid_root in IF_MIB_WALK_ROOTS:
            async for (err_indication, err_status, err_index, var_binds) in bulkCmd(
                snmp_engine,
                CommunityData(community_string),
                UdpTransportTarget((ip, 161), timeout=timeout, retries=1),
                ContextData(),
                0, 25,  # non-repeaters=0, max-repetitions=25
                oid_root,
                lexicographicMode=False,
            ):
                if err_indication:
                    return None, str(err_indication)  # SNMP unreachable
                if err_status:
                    break  # End of table or error
                for var_bind in var_binds:
                    oid_str, value = var_bind
                    # Parse port index from last OID component
                    port_idx = int(str(oid_str).split('.')[-1])
                    results.setdefault(port_idx, {})[str(oid_str).rsplit('.', 1)[0]] = value.prettyPrint()
    finally:
        snmp_engine.close()

    return results, None

# In the SNMP daemon thread:
def _snmp_poll_once(switches, community_string):
    return asyncio.run(poll_all_switches(switches, community_string))
```

[VERIFIED: Context7 /lextudio/pysnmp — bulkCmd with lexicographicMode=False confirmed for table walk]

---

### Pattern 2: Bandwidth Calculation from Counter Deltas

```python
# [CITED: RFC 2863 IF-MIB specification, standard SNMP bandwidth formula]
# Agent computes bandwidth % before pushing to Django.
# Django stores the already-computed % — no raw counter history needed in DB.

COUNTER64_MAX = 2**64  # ifHCInOctets wraps at 2^64
COUNTER32_MAX = 2**32  # ifInOctets wraps at 2^32 (not used if HC available)

def compute_bandwidth_pct(in_octets_now, in_octets_prev,
                           out_octets_now, out_octets_prev,
                           interval_secs, speed_mbps):
    """
    Returns combined in+out bandwidth utilization as a percentage.
    speed_mbps from ifHighSpeed OID (correct for 1G and 10G links).
    """
    if speed_mbps == 0 or interval_secs == 0:
        return None

    # Handle 64-bit counter wrap
    delta_in = in_octets_now - in_octets_prev
    if delta_in < 0:
        delta_in += COUNTER64_MAX

    delta_out = out_octets_now - out_octets_prev
    if delta_out < 0:
        delta_out += COUNTER64_MAX

    # Convert: octets to bits, divide by link capacity in bits/sec
    bits_in = delta_in * 8
    bits_out = delta_out * 8
    link_bps = speed_mbps * 1_000_000  # Mbps → bps

    # Use whichever direction is higher (typical network monitoring convention)
    max_bits = max(bits_in, bits_out)
    bandwidth_pct = (max_bits / (link_bps * interval_secs)) * 100

    return min(round(bandwidth_pct, 1), 100.0)  # cap at 100%


# Speed detection: ifHighSpeed (OID .31.1.1.1.15) returns Mbps directly
# ifHighSpeed == 0 means no link / unknown
# ifHighSpeed == 1000 → 1G, 10000 → 10G, 100 → 100M
# For older devices reporting ifSpeed (Counter32), 4294967295 = 10G maxed out
# In that case, fall back to ifHighSpeed which is always present in ifXTable
```

---

### Pattern 3: SNMP Daemon Thread Integration in run_monitor

The existing `handle()` method is a single-threaded while-loop. Phase 2 adds a parallel daemon thread using the same `threading.Event` stop pattern established in Phase 1 PATTERNS.md.

```python
# [CITED: Phase 1 01-PATTERNS.md — daemon thread pattern]
import threading
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        # ... existing heartbeat, scan setup ...
        stop_event = threading.Event()

        # Existing ICMP poll loop (keep as-is, convert to thread)
        icmp_thread = threading.Thread(
            target=self._icmp_loop,
            args=(stop_event, base_url, headers, interval),
            daemon=True, name='ICMPPoller',
        )

        # New SNMP poll thread
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

    def _snmp_loop(self, stop_event, base_url, headers):
        """Polls all switch-domain devices via SNMP every 30 seconds."""
        SNMP_INTERVAL = 30  # seconds — safe for Luminex/Netgear rate limits
        prev_counters = {}  # {(ip, port_idx): {'in': N, 'out': N, 'ts': T}}
        snmp_settings = self._fetch_snmp_settings(base_url, headers)

        while not stop_event.is_set():
            if snmp_settings is None:
                snmp_settings = self._fetch_snmp_settings(base_url, headers)
            if snmp_settings:
                results = self._poll_all_switches(
                    snmp_settings['switches'],
                    snmp_settings['community_string'],
                    prev_counters,
                )
                if results:
                    self._push_snmp_results(base_url, headers, results)

            # Refresh settings periodically (picks up new community string)
            snmp_settings = self._fetch_snmp_settings(base_url, headers)

            # Wait with stop_event check
            stop_event.wait(timeout=SNMP_INTERVAL)

    def _poll_all_switches(self, switches, community_string, prev_counters):
        """Wraps asyncio.run() safely — no event loop in this thread."""
        return asyncio.run(_async_poll_all(switches, community_string, prev_counters))
```

Key note: `asyncio.run()` called from a daemon thread is safe in Python 3.10+ because it creates a fresh event loop per call and the thread has no existing event loop. [CITED: Python 3.11 asyncio documentation — "asyncio.run() always creates a new event loop and closes it at the end"]

---

### Pattern 4: New Django Models

```python
# Append to planner/models.py after DeviceEvent — following Phase 1 model patterns

class ProjectSNMPConfig(models.Model):
    """Stores the SNMP v2c community string for a project."""
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
    """One row per port per SNMP poll cycle. Stores latest values only.
    Old rows replaced via update_or_create(device, session, port_index)."""
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
    bandwidth_pct = models.FloatField(null=True, blank=True)  # 0-100
    error_count = models.PositiveBigIntegerField(default=0)  # cumulative since session start
    polled_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('device', 'session', 'port_index')]
        indexes = [
            models.Index(fields=['device', 'session']),
        ]

    def __str__(self):
        return f"{self.device} port {self.port_index} ({self.oper_status})"


# Also add show_mode to MonitorSession:
# show_mode = models.CharField(
#     max_length=10,
#     choices=[('setup', 'Setup'), ('show', 'Show'), ('wrap', 'Wrap')],
#     default='show',
# )
# Add this field via migration — it fits on the existing MonitorSession model.
```

**Storage note for community string:** The community string is stored as a plain `CharField`. The `agent_api_key` is already stored as a plain `UUIDField` — the codebase has no encryption infrastructure. For the target use case (show-day networks, not corporate compliance), plain storage is consistent with the existing security posture. [ASSUMED: Charlie is comfortable with this tradeoff — it matches agent_api_key storage precedent. Flag for confirmation if stricter security needed.]

---

### Pattern 5: New API Endpoints

Five new endpoints in `views_monitor.py`:

```
# Agent endpoints (Bearer token auth — csrf_exempt + require_POST):
GET  /api/snmp-settings/  → returns community_string + switch IPs for this project
POST /api/snmp-results/   → agent pushes per-port data; Django stores in SwitchPortSnapshot

# Dashboard endpoints (session auth — @login_required):
POST /api/snmp-settings/  → browser saves community string
POST /api/add-switch/     → browser manually adds a switch IP → creates DiscoveredDevice(domain='switch')
POST /api/show-mode/      → browser changes show mode → updates MonitorSession.show_mode
```

The `monitor_status_view` (existing, polled every 3s) is extended to include switch port data:

```python
# Extended response adds switch_ports dict keyed by device_id
return JsonResponse({
    'ok': True,
    'monitor_running': ...,
    'devices': [...],
    'events': [...],
    'last_event_id': ...,
    'show_mode': session.show_mode if session else 'show',  # NEW
    'switch_ports': {                                         # NEW
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

---

### Pattern 6: Show Mode Alert Suppression

Show mode is stored on `MonitorSession.show_mode`. Alert suppression is enforced in `agent_poll_results` and `agent_snmp_results` on the server side — the agent reports raw data; the server decides whether to create `DeviceEvent` records.

```python
# In agent_poll_results and agent_snmp_results:
session = MonitorSession.objects.get(project=project, ended_at__isnull=True)
suppress_non_critical = session.show_mode in ('setup', 'wrap')

# Critical alert — always fires regardless of mode (D-08)
if device.consecutive_failures == 3 and device.last_seen is not None:
    DeviceEvent.objects.create(event_type='OFFLINE', ...)

# Non-critical alert — suppressed in setup/wrap mode (D-08)
if not suppress_non_critical:
    DeviceEvent.objects.create(event_type='PORT_DOWN', ...)  # example
```

Show mode state flows: server (MonitorSession.show_mode) → JSON in `monitor_status` response (`show_mode` field) → JS sets localStorage + updates toggle UI. On page load, JS reads from status response (not just localStorage) so browser and server stay in sync after agent restart.

---

### Anti-Patterns to Avoid

- **Full MIB walk per switch poll:** Walking `1.3.6.1` retrieves thousands of OIDs. Use targeted subtree walks of the five IF-MIB tables only. A 24-port switch should require ≤ 5 GetBulk requests.
- **Storing raw counter values in SwitchPortSnapshot for later delta calculation:** Agent computes bandwidth % before pushing; Django stores the result. Eliminates need for counter history in DB.
- **Calling `asyncio.run()` from within an already-running event loop:** Only do this from the SNMP daemon thread (which has no event loop). Never call it from a Django async view.
- **Hardcoding community string 'public' in agent:** Agent always fetches community string from `/api/snmp-settings/` at startup and refreshes each cycle. This handles community string changes without restart.
- **Creating new DiscoveredDevice for manually-added switches:** Use the existing `DiscoveredDevice` model with `domain='switch'`. The "Add Switch" button in the settings panel creates a `DiscoveredDevice` — exactly what the Unassigned-to-Switch reassign flow does. No new model needed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SNMP v2c GET/WALK | Custom UDP socket + BER encoding | pysnmp 7.x | SNMP BER encoding, community string auth, timeouts, retries are non-trivial |
| IF-MIB port enumeration | Custom OID discovery | GetBulk walk of ifOperStatus table | The table index IS the port index — no discovery needed |
| Counter wrap handling | Custom 64-bit math | Standard formula (pattern above) | Well-specified in RFC 2863; error-prone to get right without spec |

**Key insight:** The IF-MIB is a 30-year-old standard. Every switch in existence implements it. There is nothing custom to build for basic port status, speed, and counters.

---

## Common Pitfalls

### Pitfall 1: Luminex GigaCore Has SNMP Disabled by Default
**What goes wrong:** SNMP polls timeout with no response on a Luminex switch that is reachable via ICMP. Agent treats it as SNMP offline when it's actually SNMP not enabled.
**Why it happens:** Luminex ships SNMP disabled; must be enabled via Arano management tool or web UI.
**How to avoid:** Distinguish timeout (SNMP not responding) from auth failure (wrong community string) in the agent. On timeout, set switch SNMP status to `unreachable` in the push payload — dashboard shows "SNMP unreachable" card state. Do NOT mark the switch as fully offline.
**Warning signs:** Switch card shows "SNMP unreachable" but switch card status dot is green (ICMP still passing).

[CITED: .planning/research/PITFALLS.md Pitfall 5 — Luminex SNMP disabled by default]

### Pitfall 2: Wrong Community String Produces Silent Timeout (Not Auth Error)
**What goes wrong:** SNMP v2c does not return an authentication error — wrong community string = no response = same as SNMP disabled.
**Why it happens:** SNMP v2c community strings are plaintext; the switch discards mismatched requests without a response.
**How to avoid:** Surface both states as "SNMP unreachable" in the dashboard — user action is always "check community string in settings." Do not try to distinguish auth failure from timeout at the UI level (indistinguishable from agent perspective).

[CITED: .planning/research/PITFALLS.md Pitfall 6]

### Pitfall 3: ifSpeed (Counter32) Saturates at 4,294,967,295 for 10G Links
**What goes wrong:** `ifSpeed` is a Counter32 max value for any 10G+ interface. Bandwidth calculation using ifSpeed gives wrong results (100% utilization on idle 10G port).
**Why it happens:** Counter32 caps at ~4Gbps; 10G exceeds that. RFC 2233 added `ifHighSpeed` (in Mbps) specifically to fix this.
**How to avoid:** Always use `ifHighSpeed` (OID 1.3.6.1.2.1.31.1.1.1.15) for speed, and `ifHCInOctets`/`ifHCOutOctets` (Counter64) for byte counters. Fall back to `ifSpeed` and `ifInOctets` only if the switch doesn't support ifXTable (very old equipment).

[ASSUMED: All target switches (Luminex GigaCore, Netgear, Ubiquiti) support ifXTable — likely true for modern entertainment switches but not verified against specific firmware versions]

### Pitfall 4: SNMP Polling Too Frequent Triggers Rate Limits on Entry-Level Switches
**What goes wrong:** Polling at 10-second intervals (same as ICMP) can overwhelm entry-level Netgear and Luminex firmware with SNMP request queues.
**How to avoid:** Default SNMP poll interval to 30 seconds. ICMP stays at 10 seconds. Port status changes on show networks are rare; 30-second detection lag is acceptable.

[CITED: .planning/research/PITFALLS.md Pitfall 15]

### Pitfall 5: asyncio.run() Compatibility in Background Threads
**What goes wrong:** If pysnmp ever gets called from a context with an existing event loop (e.g., Django async views), `asyncio.run()` raises RuntimeError.
**Why it happens:** `asyncio.run()` requires no running event loop in the calling thread.
**How to avoid:** Keep SNMP polling strictly in the dedicated daemon thread. Never call SNMP functions from Django views or Celery tasks.

### Pitfall 6: Switching from run_monitor Single Loop to Two Daemon Threads
**What goes wrong:** The existing run_monitor uses a flat while-loop with `_poll_devices()` inline. Converting to daemon threads requires restructuring — easy to introduce a race condition where the main thread exits before daemon threads finish their first poll.
**How to avoid:** Main thread blocks on `stop_event.wait()` in a loop (not `stop_event.wait()` with no timeout, which is uninterruptible on Windows). Both threads set `daemon=True` so they auto-exit on main thread exit.

---

## Code Examples

Verified patterns from official sources:

### Targeted IF-MIB Subtree Walk (pysnmp v7 asyncio)
```python
# Source: Context7 /lextudio/pysnmp — bulkCmd with lexicographicMode=False
from pysnmp.hlapi.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, bulkCmd,
)

async def walk_iftable_subtree(ip, community, oid_root):
    """Walk a single IF-MIB subtree, return {port_index: value} dict."""
    snmp_engine = SnmpEngine()
    rows = {}
    try:
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
                return None  # SNMP unreachable or error
            for name, val in var_binds:
                port_idx = int(str(name).split('.')[-1])
                rows[port_idx] = int(val)
    finally:
        snmp_engine.close()
    return rows
```

### Bandwidth Pct from Two Consecutive Snapshots
```python
# Source: RFC 2863 + RFC 2233 (standard IF-MIB bandwidth formula)
import time

def calc_bandwidth(curr_in, prev_in, curr_out, prev_out,
                   prev_ts, curr_ts, speed_mbps):
    interval = curr_ts - prev_ts
    if interval <= 0 or not speed_mbps:
        return None
    delta_in = (curr_in - prev_in) % (2**64)
    delta_out = (curr_out - prev_out) % (2**64)
    link_bps = speed_mbps * 1_000_000
    pct = (max(delta_in, delta_out) * 8 / (link_bps * interval)) * 100
    return min(round(pct, 1), 100.0)
```

### show_mode Migration Addition to MonitorSession
```python
# In planner/models.py — add field to MonitorSession
# After: notes = models.TextField(blank=True)
show_mode = models.CharField(
    max_length=10,
    choices=[('setup', 'Setup'), ('show', 'Show'), ('wrap', 'Wrap')],
    default='show',
)
```
Run `makemigrations` + `migrate` after adding. No data migration needed (default='show' applies to existing sessions).

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `etingof/pysnmp` (abandoned) | `pysnmp` (LeXtudio fork, v7.x) | 2022 (takeover), 2024 (v7 API rewrite) | v7 is async-first; sync API removed; use asyncio.run() in thread |
| `pysnmp-lextudio` PyPI name | `pysnmp` PyPI name | 2024 | Install `pysnmp`, not `pysnmp-lextudio` (deprecated) |
| ifSpeed for all speeds | ifHighSpeed for ≥10G links | RFC 2233 (1997), relevant now | Must use ifHighSpeed/ifHCInOctets for 10G switch ports |

**Deprecated/outdated:**
- `easysnmp`: Last release 2021, requires native net-snmp. Do not use.
- `pysnmp-lextudio`: Deprecated PyPI name. Install `pysnmp` instead.
- `pysnmp` v4.x (etingof era): Sync generator API with `nextCmd`. Replaced by async in v6+.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Plain CharField storage for community string is acceptable (matches agent_api_key precedent) | Architecture Patterns (Pattern 4) | If compliance required, need to add `django-cryptography` or Fernet encryption — adds a package dependency and key management |
| A2 | Luminex GigaCore, Netgear, and Ubiquiti entertainment switches support ifXTable (ifHighSpeed, ifHCInOctets) | Pitfall 3 | If older firmware doesn't support ifXTable, must fall back to ifSpeed + ifInOctets with Counter32 wrap handling — bandwidth inaccurate on 10G ports |
| A3 | asyncio.run() called from daemon thread works correctly on macOS arm64 Python 3.11+ | Pattern 3 | If there is a platform-specific issue, alternative is to use concurrent.futures.ThreadPoolExecutor with asyncio integration — more complex |
| A4 | Existing show-day networks don't rate-limit SNMP at 30s intervals | Pitfall 4 | If they do, need to increase to 60s or support per-switch configurable interval (out of scope per D-11 philosophy) |

---

## Open Questions

1. **Existing run_monitor: restructure to threads or keep flat loop + inline SNMP?**
   - What we know: Current agent is a flat while-loop with inline ICMP polling. Phase 1 PATTERNS.md shows the daemon thread pattern was discussed but not implemented.
   - What's unclear: Whether the existing loop was implemented as a single-thread flat loop or whether threads were added.
   - Recommendation: Read the current `run_monitor.py` handle() method before planning Wave 1. If it's still a flat loop (confirmed above), the restructure to two daemon threads is Wave 1 task 0.

2. **Does MonitorSession.show_mode need to survive across agent reconnections?**
   - What we know: MonitorSession is keyed per project; a restart creates a new session (or finds existing open one).
   - What's unclear: If engineer sets "Setup" mode then restarts agent, should mode persist? Current design (field on MonitorSession, default='show') resets on new session.
   - Recommendation: The UI-SPEC says localStorage persists mode — so browser re-POSTs mode on reconnect. No change needed to the model design, but the JavaScript should POST the stored mode value on monitor start.

3. **How many ports do target switches have — affects GetBulk max-repetitions tuning?**
   - Luminex GigaCore 16 = 16 ports, GigaCore 26 = 26 ports. With max-repetitions=25, a single GetBulk covers most Luminex switches in one round trip.
   - Recommendation: Default max-repetitions=25 covers Luminex and most 24-port Netgear/Ubiquiti. Upgrade to 50 if 48-port switches appear. Not blocking.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | asyncio.run() in thread | Confirmed (macOS arm64) [VERIFIED: platform check] | — | — |
| pysnmp 7.1.25 | SNMP polling | Not installed yet | — | Install via pip |
| cryptography | Optional: Fernet encrypt community string | Not in project venv | — | Store plain CharField (A1 assumption) |
| Django 5.2.4 | All models + views | Installed [VERIFIED: requirements.txt] | 5.2.4 | — |
| requests | Agent HTTP push | Installed [VERIFIED: requirements.txt] | ≥2.33 | — |

**Missing dependencies:**
- `pysnmp>=7.1,<8.0` — required, no fallback. Must be added to requirements.txt.

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 2 |
|-----------|-------------------|
| Session-based project scoping via `request.current_project` | All new views must use `getattr(request, 'current_project', None)` — no URL-based project routing |
| Always register on `showstack_admin_site`, not `admin.site` | `ProjectSNMPConfig` and `SwitchPortSnapshot` must be registered on `showstack_admin_site` |
| Update `admin_ordering.py` for every new admin-registered model | Add `projectsnmpconfig` and `switchportsnapshot` to `order_map` |
| New models append to end of `planner/models.py` | `ProjectSNMPConfig` and `SwitchPortSnapshot` go after `DeviceEvent` (line 4666+) |
| No feature branches unless risky/multi-session | Commit directly to main per normal solo-dev flow |
| Django admin CSS override requires `element.style.setProperty(..., 'important')` | Applies to any dashboard JS that touches inline styles |
| Dante Subscription Planner is frozen — do not touch | Not relevant to Phase 2 |
| Network Health Monitor is the active module | Confirmed — Phase 2 is in scope |

---

## Validation Architecture

> `nyquist_validation: false` in `.planning/config.json` — this section is skipped.

---

## Security Domain

> Phase 2 introduces SNMP community string storage and new unauthenticated-adjacent API endpoints (agent endpoints use Bearer token, not CSRF).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Partial | Agent endpoints: Bearer token (project agent_api_key). Dashboard endpoints: Django @login_required session auth |
| V5 Input Validation | Yes | community_string: CharField max_length=255, stripped. Manual IP entry: validated as valid IP before DiscoveredDevice creation |
| V6 Cryptography | No | Community string stored plaintext (consistent with agent_api_key precedent — A1 assumption) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Agent endpoint called without valid API key | Spoofing | `_authenticate_agent()` Bearer token check (existing pattern) — apply to all 2 new agent endpoints |
| Malicious switch IP injection via add-switch | Tampering | Validate IP format before DiscoveredDevice creation; scoped to current_project |
| Community string exposed in JSON response | Information Disclosure | `/api/snmp-settings/` response sent over HTTPS in production (Railway). Dev: localhost only |

---

## Sources

### Primary (HIGH confidence)
- Context7 `/lextudio/pysnmp` — bulkCmd, getCmd, CommunityData, UdpTransportTarget API patterns
- PyPI registry — pysnmp 7.1.25 confirmed current as of 2026-04-24 [VERIFIED]
- RFC 2863 (IF-MIB) — ifOperStatus, ifSpeed, ifInOctets, ifInErrors OID assignments [CITED]
- RFC 2233 (IF-MIB extensions) — ifHighSpeed, ifHCInOctets, ifHCOutOctets OID assignments [CITED]
- Python 3.11 asyncio docs — asyncio.run() thread safety guarantee [CITED]
- `.planning/research/PITFALLS.md` — Luminex SNMP disabled, rate limiting, community string silent timeout [CITED]
- `.planning/research/STACK.md` — pysnmp recommendation rationale, IF-MIB OID list [CITED]
- `planner/management/commands/run_monitor.py` — existing agent architecture [VERIFIED: codebase]
- `planner/models.py` lines 4549-4666 — existing monitor models [VERIFIED: codebase]
- `planner/views_monitor.py` — existing API endpoint patterns [VERIFIED: codebase]
- `requirements.txt` — installed package versions [VERIFIED: codebase]
- `.planning/phases/02-switch-snmp/02-UI-SPEC.md` — settings panel layout, port table spec [CITED]
- `.planning/phases/01-foundation/01-PATTERNS.md` — daemon thread pattern, CSS conventions [CITED]

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` Pitfall 5 — Luminex SNMP OID compatibility (cited from Luminex support portal)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pysnmp 7.1.25 version verified on PyPI; IF-MIB OIDs are 30-year-old IANA standards
- Architecture: HIGH — integration pattern is additive to existing agent; threading pattern documented in Phase 1
- Pitfalls: HIGH — Luminex SNMP behavior from PITFALLS.md (cited from Luminex support); RFC math is exact

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (pysnmp moves fast; verify version before install)
