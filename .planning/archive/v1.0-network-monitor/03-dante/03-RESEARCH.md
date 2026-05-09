# Phase 3: Dante - Research

**Researched:** 2026-04-25
**Domain:** Dante mDNS auto-discovery, clock status display, pre-show health check
**Confidence:** MEDIUM (netaudio API verified via source inspection; clock status path has confirmed gaps)

## Summary

Phase 3 adds a Dante device discovery thread to the existing `run_monitor` agent, using the `netaudio` library's `DanteBrowser` class for mDNS enumeration and `DanteDevice` attributes for clock status and channel counts. The agent pushes discovered Dante device data to a new Django API endpoint; the dashboard renders Dante cards with clock role badges, ghost cards for missing project devices, and a pre-show health check panel.

The netaudio library (0.2.4) provides mDNS discovery via zeroconf `AsyncServiceBrowser`, which discovers devices by browsing `_netaudio-dbc._udp`, `_netaudio-arc._udp`, `_netaudio-cmc._udp`, and `_netaudio-chan._udp` service types. Device name, IP, sample rate, model ID, and MAC address are reliably extracted from mDNS service properties. Channel counts (`tx_count`, `rx_count`) and clock role (`preferred_leader`, `ptp_v1_role`) require additional UDP protocol queries that are reverse-engineered and unreliable across hardware revisions.

The primary risk is clock status retrieval: the `get_clocking_status()` method on `DanteDevice` checks for `command_clocking_status` and `parse_clocking_status` methods, but **neither exists in the v0.2.4 source code**. The `DanteApplication` class uses a different path -- `probe_preferred_leader` via the notification service -- which does work but requires running the full `DanteApplication` stack (notification service, CMC service, settings service) rather than simple mDNS browsing. The simpler `DanteBrowser.get_devices()` path gives device name, IP, model, and sample rate but NOT clock status or channel counts.

**Primary recommendation:** Use `DanteBrowser` for mDNS discovery (device name + IP), supplement with `DanteApplication` for clock/channel data only if feasible, and degrade gracefully when clock data is unavailable.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Auto-match by name -- mDNS device names compared against project device labels/names. Matched devices linked automatically. Unmatched devices not shown in Dante section.
- **D-02:** Unmatched Dante devices go to the Unassigned section, same as unknown devices from Phase 1 ping sweep.
- **D-03:** Missing project devices show as ghost cards in Dante section AND are flagged in health check. Dual visibility.
- **D-04:** Clock status displayed prominently on collapsed card, same visual weight as reachability dot.
- **D-05:** Section-level advisory footnote: "Clock status is advisory -- verify on hardware before showtime." Not per-card.
- **D-06:** Show whatever netaudio reports -- if multiple devices claim master, show them all. No warning or interpretation.
- **D-07:** Auto-run health check on page load with manual Re-check button.
- **D-08:** Expandable panel in Dante section -- auto-expands when issues found.
- **D-09:** Presence-based matching for health check -- any Dante device on the network counts.
- **D-10:** Collapsed cards show: device name, clock role badge, channel count. IP in expanded view.
- **D-11:** Ghost cards are dimmed -- lower opacity, grey text, unreachable-style dot.

### Claude's Discretion
- Health check panel layout and styling
- Channel count display format
- Clock role icon/text presentation
- Ghost card exact opacity and styling
- Re-check button placement
- How auto-match handles partial name matches vs exact matches

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MON-01 | Dante devices auto-discovered on the network via mDNS without manual IP entry | `DanteBrowser` class uses zeroconf `AsyncServiceBrowser` to browse SERVICES list; returns device name + IP from mDNS service records |
| MON-04 | Pre-show health check compares discovered devices against project-defined device list | Server-side comparison of Dante `DiscoveredDevice` records (domain='dante') vs project Console/Device/Amp names; health check endpoint returns missing/unexpected lists |
| DAN-01 | Dashboard identifies the Dante clock master device | `DanteDevice.preferred_leader` (bool) and `ptp_v1_role` ("Leader"/"Follower") from notification service conmon parsing; requires `DanteApplication` stack, not just `DanteBrowser` |
| DAN-02 | Per-device clock lock/unlock status displayed (advisory) | `ptp_v1_role` provides "Leader" or "Follower"; "Unlocked" state needs inference from absence of role or separate protocol query; LOW confidence on completeness |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| mDNS discovery | Agent (local laptop) | -- | mDNS is link-local multicast; must run on show network |
| Clock status query | Agent (local laptop) | -- | UDP queries to device ports require local network access |
| ICMP reachability | Agent (local laptop) | -- | Ping requires local network; already exists from Phase 1 |
| Device matching | API / Backend (Django) | -- | Comparison logic against project device records in DB |
| Health check computation | API / Backend (Django) | -- | Server-side comparison, served as JSON to dashboard |
| Dashboard rendering | Browser / Client | -- | JS renders cards from AJAX poll data |
| Ghost card display | Browser / Client | -- | JS renders ghost cards from health check missing list |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| netaudio | 0.2.4 | Dante mDNS discovery + device info | Only Python library with Dante service type knowledge [VERIFIED: pip install to /tmp] |
| zeroconf | 0.148.0 | mDNS protocol (netaudio dependency) | Canonical Python mDNS library; netaudio depends on it [VERIFIED: installed as dependency] |
| icmplib | 3.0.4 | ICMP reachability for discovered Dante IPs | Already in use from Phase 1 [VERIFIED: existing codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| netifaces | (existing) | NIC enumeration for link-local detection | Already used in agent _scan_all_nics [VERIFIED: existing codebase] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| netaudio DanteBrowser | Raw zeroconf ServiceBrowser | Would need to hardcode Dante service types and parse TXT records manually; netaudio already does this |
| netaudio DanteApplication | DanteBrowser + manual UDP | Application runs full service stack (CMC, ARC, settings, notifications); heavier but provides clock/channel data |
| Full DanteApplication | DanteBrowser only | Browser gives name+IP only; no clock or channel data; simplest but incomplete for DAN-01/DAN-02 |

**Installation:**
```bash
pip install "netaudio==0.2.4"
# zeroconf installed automatically as dependency
```

**Version verification:** netaudio 0.2.4 is the latest release [VERIFIED: pip index versions netaudio]. zeroconf 0.148.0 installed as dependency [VERIFIED: pip install output].

## Architecture Patterns

### System Architecture Diagram

```
Engineer's Laptop (show network)           ShowStack Server (Django)           Browser
=================================          ==========================          =======

run_monitor command                         Django API                          Dashboard
  |                                           |                                  |
  +-- ICMPPoller thread (existing)            |                                  |
  |     ping all device IPs                   |                                  |
  |     POST /api/poll-results/  -----------> agent_poll_results()               |
  |                                           |                                  |
  +-- SNMPPoller thread (existing)            |                                  |
  |     walk switch MIBs                      |                                  |
  |     POST /api/snmp-results/ -----------> agent_snmp_results()                |
  |                                           |                                  |
  +-- DantePoller thread (NEW)                |                                  |
  |     DanteBrowser.get_devices()            |                                  |
  |     (mDNS discovery, 3s browse)           |                                  |
  |     + optional clock/channel queries      |                                  |
  |     POST /api/dante-results/ -----------> agent_dante_results() (NEW)        |
  |                                           |  store in DiscoveredDevice        |
  |                                           |  + new Dante fields              |
  |                                           |                                  |
  |                                     GET /status/ <========================== AJAX poll 3s
  |                                           |  returns devices + dante_data     |
  |                                           |                                  |
  |                                     GET /api/health-check/ <================ on page load
  |                                           |  compares discovered vs project   |
  |                                           |  returns missing/unexpected       |
  |                                           |                               renders cards,
  |                                           |                               ghost cards,
  |                                           |                               health panel
```

### Recommended Project Structure

No new files needed beyond extending existing ones:
```
planner/
  management/commands/
    run_monitor.py          # Add DantePoller thread
  models.py                 # Add fields to DiscoveredDevice (or new model)
  views_monitor.py          # Add agent_dante_results, health_check endpoints
templates/planner/
  network_monitor.html      # Replace Dante placeholder with real cards
```

### Pattern 1: DanteBrowser mDNS Discovery (Agent-Side)

**What:** Run `DanteBrowser.get_devices()` in a background thread on the agent.
**When to use:** Every Dante poll cycle (30-60 seconds; mDNS browsing takes `mdns_timeout` seconds).

```python
# Source: netaudio/dante/browser.py (v0.2.4) [VERIFIED: source inspection]
import asyncio
from netaudio.dante.browser import DanteBrowser

async def discover_dante_devices(timeout=3.0):
    """Discover Dante devices via mDNS. Returns dict of {server_name: DanteDevice}."""
    browser = DanteBrowser(mdns_timeout=timeout)
    devices = await browser.get_devices()
    results = []
    for server_name, device in devices.items():
        results.append({
            'name': device.name,
            'ip': str(device.ipv4),
            'server_name': server_name,
            'model_id': device.model_id or '',
            'sample_rate': device.sample_rate,
            'mac_address': device.mac_address or '',
            'tx_count': device.tx_count,  # May be None without protocol query
            'rx_count': device.rx_count,  # May be None without protocol query
            'preferred_leader': device.preferred_leader,  # None without DanteApplication
            'ptp_v1_role': device.ptp_v1_role,  # None without DanteApplication
        })
    return results
```

**Key detail:** `DanteBrowser.get_devices()` calls `async_run()` which starts an `AsyncServiceBrowser`, sleeps for `mdns_timeout` seconds, then gathers all discovered service info. The `mdns_timeout` controls how long to wait for devices to announce. 3 seconds is sufficient for most show networks (devices announce within 1-2 seconds).

### Pattern 2: DantePoller Thread (Agent-Side)

**What:** New daemon thread in `run_monitor.py`, alongside ICMPPoller and SNMPPoller.
**When to use:** Runs continuously while agent is active.

```python
# Source: Follows existing _snmp_loop pattern [VERIFIED: run_monitor.py]
def _dante_loop(self, stop_event, base_url, headers):
    """Dante mDNS discovery thread -- discovers devices every 30 seconds."""
    DANTE_INTERVAL = 30

    while not stop_event.is_set():
        try:
            devices = asyncio.run(discover_dante_devices(timeout=3.0))
        except Exception as e:
            self.stderr.write(self.style.WARNING(f'[Dante] Discovery error: {e}'))
            stop_event.wait(timeout=DANTE_INTERVAL)
            continue

        if devices:
            self._push_dante_results(base_url, headers, devices)

        stop_event.wait(timeout=DANTE_INTERVAL)
```

### Pattern 3: Health Check Endpoint (Server-Side)

**What:** Compare discovered Dante devices against project device records.
**When to use:** Called on page load and manual Re-check button.

```python
# Source: D-07, D-09 from CONTEXT.md
@login_required
def health_check_view(request):
    """GET /audiopatch/network-monitor/api/health-check/"""
    project = request.current_project
    if not project:
        return JsonResponse({'error': 'No project'}, status=400)

    # Discovered Dante devices (active, domain='dante')
    discovered = set(
        DiscoveredDevice.objects.filter(
            project=project, domain='dante', is_active=True
        ).values_list('label', flat=True)
    )

    # Expected project devices (Console, Device, Amp names)
    expected = set()
    for Model in [Console, Device, Amp]:
        expected.update(
            Model.objects.filter(project=project).values_list('name', flat=True)
        )

    # Presence-based matching (D-09)
    discovered_lower = {n.lower(): n for n in discovered}
    expected_lower = {n.lower(): n for n in expected}

    missing = [expected_lower[n] for n in expected_lower if n not in discovered_lower]
    unexpected = [discovered_lower[n] for n in discovered_lower if n not in expected_lower]

    return JsonResponse({
        'status': 'ok' if not missing and not unexpected else 'issues',
        'missing': missing,
        'unexpected': unexpected,
        'total_expected': len(expected),
        'total_found': len(discovered),
    })
```

### Anti-Patterns to Avoid

- **Running DanteApplication in agent thread without cleanup:** `DanteApplication` starts multiple UDP services (CMC, ARC, settings, notifications) that bind to specific ports. If not properly shut down, these block subsequent runs. Always use try/finally to close services.
- **Scanning /16 for link-local Dante IPs:** Never ping-sweep 169.254.0.0/16 (65K hosts). Use mDNS discovery or ARP cache (already implemented in Phase 1 `_discover_link_local`).
- **Treating clock status as authoritative:** Per PITFALLS.md and STATE.md, clock data from netaudio is LOW confidence. Never build alerting or automated responses on clock status.
- **Blocking the ICMP poll cycle with mDNS timeout:** mDNS discovery takes `mdns_timeout` seconds (blocking). Run in its own thread, never in the ICMP or SNMP polling threads.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dante mDNS service type browsing | Custom zeroconf browser for `_netaudio-*._udp` | `DanteBrowser` from netaudio | Service types, TXT record parsing, and server_name extraction already implemented |
| mDNS async lifecycle | Manual AsyncZeroconf + AsyncServiceBrowser management | `DanteBrowser.get_devices()` | Handles browser start, timeout, gather, close sequence |
| Device name extraction from mDNS | Parse DNS records manually | `DanteDevice.name` from `DanteBrowser.get_devices()` | netaudio already extracts from service properties |
| Clock role constants | Hardcode PTP role values | `PTP_V1_ROLE_MAP` from netaudio | Maps 0x0006->"Leader", 0x0009->"Follower" [VERIFIED: source] |

**Key insight:** netaudio's value is its knowledge of Dante mDNS service types and binary protocol opcodes. Its codebase is the only public documentation of these proprietary Audinate details. Use it for discovery; wrap it for isolation from API churn.

## Common Pitfalls

### Pitfall 1: DanteBrowser.get_devices() Returns No Clock or Channel Data
**What goes wrong:** `DanteBrowser.get_devices()` only populates device name, IP, model_id, sample_rate, and mac_address from mDNS service properties. `tx_count`, `rx_count`, `preferred_leader`, and `ptp_v1_role` remain `None` because they require separate UDP protocol queries via `DanteApplication`.
**Why it happens:** mDNS TXT records contain `id`, `model`, `rate`, `latency_ns` but not channel counts or clock role. Those come from binary protocol commands (opcode 0x1000 for channels, conmon notifications for clock).
**How to avoid:** Either (a) use `DanteApplication.get_devices()` instead of `DanteBrowser` to get full data, or (b) accept that clock/channel data may be None and show "Unknown" in the UI. Option (b) is safer and aligned with the advisory approach.
**Warning signs:** All Dante devices show "Unknown" clock role and no channel counts on the dashboard.

### Pitfall 2: get_clocking_status() Does Not Work in v0.2.4
**What goes wrong:** `DanteDevice.get_clocking_status()` checks `hasattr(self.commands, "command_clocking_status")` and `hasattr(self.parser, "parse_clocking_status")`, but NEITHER method exists in the v0.2.4 codebase. The method silently returns `None`.
**Why it happens:** The method was scaffolded for a future feature but never completed. Clock status actually comes through the `DanteNotificationService` conmon parsing path.
**How to avoid:** Do not call `device.get_clocking_status()`. If clock data is needed, use `DanteApplication` which runs the notification service and populates `device.preferred_leader` and `device.ptp_v1_role` via conmon responses.
**Warning signs:** `clock_role` is always `None` on discovered devices.

### Pitfall 3: DanteApplication Binds to Fixed UDP Ports
**What goes wrong:** `DanteApplication` starts `DanteCMCService`, `DanteARCService`, `DanteSettingsService`, and `DanteNotificationService`, each binding to specific UDP ports (8800, 4440, 8700, 8702/8708). If another instance is running (or if cleanup fails), port binding fails.
**Why it happens:** These ports are fixed in the Dante protocol; they cannot be changed.
**How to avoid:** (a) Use only `DanteBrowser` for discovery (no port binding needed -- mDNS uses zeroconf's own sockets). (b) If using `DanteApplication`, ensure single-instance enforcement and proper cleanup in `finally` blocks. (c) The agent already runs as a single process, so port conflicts are unlikely unless Dante Controller is also running on the same machine.
**Warning signs:** `OSError: [Errno 48] Address already in use` when starting the Dante poller.

### Pitfall 4: mDNS Discovery Timeout Too Short
**What goes wrong:** With `mdns_timeout=1`, devices on slower networks or behind switches with IGMP snooping may not announce in time. The browser returns an incomplete device list.
**Why it happens:** mDNS announcements are not instantaneous; devices respond to multicast queries within 0-3 seconds depending on firmware and network conditions.
**How to avoid:** Use `mdns_timeout=3` for the discovery window. This is a blocking sleep in the async browser, so it adds 3 seconds to each discovery cycle. For a 30-second poll interval, this is acceptable.
**Warning signs:** Device count varies between discovery cycles; some devices intermittently "disappear."

### Pitfall 5: Name Matching Between mDNS and Project Records
**What goes wrong:** Dante device names from mDNS (e.g., "RIO3224-D2") may not exactly match project device names entered by the engineer (e.g., "Rio 3224-D2" or "FOH RIO 3224"). Exact string matching produces false "missing" results in the health check.
**Why it happens:** Engineers name devices in ShowStack using their own conventions; Dante device names are factory defaults or configured in Dante Controller.
**How to avoid:** Use case-insensitive substring matching. A project device name "RIO3224-D2" should match mDNS name "RIO3224-D2" regardless of case. For the health check (D-09), presence-based matching is explicitly less strict. Consider: exact match first, then case-insensitive, then substring containment.
**Warning signs:** Health check shows devices as both "missing" and "unexpected" when the same physical device has slightly different names in the two systems.

## Code Examples

### mDNS Discovery via DanteBrowser (Minimal Path)

```python
# Source: netaudio/dante/browser.py v0.2.4 [VERIFIED: source inspection]
import asyncio
from netaudio.dante.browser import DanteBrowser

async def discover():
    browser = DanteBrowser(mdns_timeout=3.0)
    devices = await browser.get_devices()
    for server_name, device in devices.items():
        print(f"{device.name} @ {device.ipv4} (model: {device.model_id})")
        # device.tx_count = None (requires protocol query)
        # device.preferred_leader = None (requires DanteApplication)
    return devices

# Run from thread: asyncio.run(discover())
```

### DanteApplication (Full Path with Clock Status)

```python
# Source: netaudio/dante/application.py v0.2.4 [VERIFIED: source inspection]
import asyncio
from netaudio.dante.application import DanteApplication
from netaudio.dante.browser import DanteBrowser

async def discover_with_clock():
    app = DanteApplication()
    browser = DanteBrowser(mdns_timeout=3.0, app=app)
    devices = await app.get_devices(browser=browser, populate_time=5.0)
    for server_name, device in devices.items():
        print(f"{device.name} @ {device.ipv4}")
        print(f"  preferred_leader: {device.preferred_leader}")  # True/False/None
        print(f"  ptp_v1_role: {device.ptp_v1_role}")  # "Leader"/"Follower"/None
        print(f"  tx_count: {device.tx_count}, rx_count: {device.rx_count}")
    # IMPORTANT: cleanup
    await app.stop()
    return devices
```

### DiscoveredDevice Model Extension

```python
# Source: Existing DiscoveredDevice model [VERIFIED: planner/models.py line 4570]
# New fields for Dante-specific data:
class DiscoveredDevice(models.Model):
    # ... existing fields ...
    # Phase 3 additions:
    dante_device_name = models.CharField(max_length=200, blank=True,
        help_text="Device name from mDNS discovery (may differ from label)")
    clock_role = models.CharField(max_length=20, blank=True,
        choices=[('master', 'Master'), ('locked', 'Locked'),
                 ('unlocked', 'Unlocked'), ('unknown', 'Unknown')],
        default='unknown')
    tx_channel_count = models.PositiveIntegerField(null=True, blank=True)
    rx_channel_count = models.PositiveIntegerField(null=True, blank=True)
    dante_model_id = models.CharField(max_length=50, blank=True)
    dante_mac_address = models.CharField(max_length=20, blank=True)
```

### as_status_dict Extension

```python
# Source: Existing as_status_dict [VERIFIED: planner/models.py line 4612]
def as_status_dict(self):
    d = {
        'device_id': self.pk,
        'label': self.label or self.ip_address,
        'ip': self.ip_address,
        'domain': self.domain,
        'status': self.status(),
        'consecutive_failures': self.consecutive_failures,
        'last_seen': self.last_seen.isoformat() if self.last_seen else None,
    }
    if self.domain == 'dante':
        d.update({
            'dante_device_name': self.dante_device_name,
            'clock_role': self.clock_role,
            'tx_channels': self.tx_channel_count,
            'rx_channels': self.rx_channel_count,
        })
    return d
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| netaudio DanteBrowser only | DanteApplication full stack | v0.2.4 (March 2026) | Application provides clock/channel via notification service; browser alone gives name+IP only |
| `get_clocking_status()` on device | Notification service conmon parsing | v0.2.4 | `get_clocking_status` is a dead-end stub; clock data comes through notifications |
| PTP "master/slave" terminology | "Leader/Follower" terminology | netaudio v0.2.x | PTP_V1_ROLE_MAP uses "Leader"/"Follower" (matches Audinate's updated terminology) |

**Deprecated/outdated:**
- `DanteDevice.get_clocking_status()`: Scaffolded but non-functional. Do not use. [VERIFIED: source inspection -- `command_clocking_status` and `parse_clocking_status` do not exist on commands/parser classes]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `DanteApplication.get_devices()` can be called from a thread via `asyncio.run()` without port conflicts with Dante Controller | Architecture Patterns | If Dante Controller is running on same laptop, port binding fails -- agent would need to detect and skip DanteApplication, falling back to DanteBrowser only |
| A2 | 3-second mDNS timeout is sufficient for typical show networks | Pitfalls | May miss slow-announcing devices; would need increase to 5s at cost of longer poll cycles |
| A3 | Case-insensitive name comparison is sufficient for auto-matching (D-01) | Health Check pattern | If names are substantially different (e.g., "FOH Rio" vs "RIO3224-D2"), matching fails; may need manual linking UI in future |
| A4 | Project devices with Dante connectivity can be identified by checking Console.name, Device.name, and Amp.name | Health Check pattern | Some project devices may not have Dante; matching all names could produce false "unexpected" results. May need a "has Dante" flag on project devices. |

## Open Questions

1. **DanteApplication vs DanteBrowser: which path for the agent?**
   - What we know: DanteBrowser gives device name + IP reliably. DanteApplication gives clock + channels but is heavier and may conflict with Dante Controller.
   - What's unclear: Whether DanteApplication's port binding creates issues on a laptop where Dante Controller might also be running.
   - Recommendation: Start with DanteBrowser only. Add DanteApplication as an optional upgrade path. Show "Unknown" for clock when DanteApplication is not running. This satisfies MON-01 fully and provides DAN-01/DAN-02 as advisory.

2. **Which project device records represent Dante-capable devices?**
   - What we know: Console, Device, and Amp models all have `name` fields. Not all of them are Dante devices.
   - What's unclear: How to determine which project devices should appear in the Dante health check.
   - Recommendation: Match discovered Dante device names against ALL project device names. Any match is a "Dante device." Unmatched project devices are NOT flagged as missing in the Dante health check -- only matched ones that subsequently disappear are flagged. Alternatively, introduce a simple boolean `is_dante` field on Console/Device/Amp.

3. **Clock role mapping: "Leader"/"Follower" vs UI spec "Master"/"Locked"/"Unlocked"**
   - What we know: netaudio uses "Leader"/"Follower" (PTP_V1_ROLE_MAP). UI spec (D-04) uses "Master"/"Locked"/"Unlocked"/"Unknown".
   - What's unclear: The exact mapping. "Leader" = "Master" is clear. "Follower" likely = "Locked" (synced to leader). "Unlocked" = device not syncing (no ptp_v1_role value? or a specific state?).
   - Recommendation: Map "Leader" -> "Master", "Follower" -> "Locked", None/unknown -> "Unknown". "Unlocked" state may not be directly reportable from netaudio without DanteApplication's notification service detecting a device that has lost PTP sync. Start with three states (Master, Locked, Unknown); add Unlocked if the notification service provides enough signal.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| netaudio | Dante discovery | Installable | 0.2.4 | -- |
| zeroconf | netaudio dependency | Installable | 0.148.0 | -- |
| icmplib | ICMP reachability | Installed | 3.0.4 | -- (already in use) |
| netifaces | NIC enumeration | Installed | (existing) | -- (already in use) |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None. All dependencies are pip-installable Python packages.

## Sources

### Primary (HIGH confidence)
- netaudio v0.2.4 source code -- installed to /tmp and inspected directly:
  - `browser.py`: DanteBrowser class, get_devices(), async_run(), mDNS timeout
  - `device.py`: DanteDevice attributes (name, ipv4, tx_count, rx_count, preferred_leader, ptp_v1_role, clock_role)
  - `device_commands.py`: command_channel_count, command_probe_preferred_leader (no command_clocking_status)
  - `device_parser.py`: parse_volume, get_rx_channels, get_tx_channels (no parse_clocking_status)
  - `device_serializer.py`: to_json output format, optional fields
  - `const.py`: SERVICES list, SERVICE_CMC/ARC/DBC/CHAN, PTP_V1_ROLE constants
  - `services/notification.py`: PTP_V1_ROLE_MAP, CONMON_PREFERRED_LEADER_OFFSET, conmon parsing
  - `application.py`: DanteApplication.get_devices(), probe_preferred_leader_all()
- Existing ShowStack codebase [VERIFIED: direct file reads]:
  - `planner/models.py` lines 4570-4621: DiscoveredDevice model, domain choices, as_status_dict
  - `planner/views_monitor.py`: monitor_status_view, agent endpoints, _authenticate_agent
  - `planner/management/commands/run_monitor.py`: ICMPPoller, SNMPPoller thread pattern
  - `templates/planner/network_monitor.html` lines 1368-1387: Dante section placeholder

### Secondary (MEDIUM confidence)
- [netaudio wiki - Technical details](https://github.com/chris-ritsen/network-audio-controller/wiki/Technical-details) -- Dante mDNS service types, UDP protocol details
- [netaudio wiki - Examples](https://github.com/chris-ritsen/network-audio-controller/wiki/Examples) -- CLI usage patterns
- `.planning/research/STACK.md` -- Prior stack research (netaudio, zeroconf, icmplib recommendations)
- `.planning/research/PITFALLS.md` -- Prior pitfall research (netaudio unreliability, mDNS VLAN, IGMP, clock conflation)

### Tertiary (LOW confidence)
- Clock status "Unlocked" state detection -- no verified source for how netaudio represents a device that has lost PTP sync vs simply not having been queried [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- netaudio + zeroconf verified via source inspection; only option for Dante mDNS in Python
- Architecture: HIGH -- follows established agent-push-poll pattern from Phase 1/2; extends existing thread model
- Pitfalls: HIGH -- clock status gaps verified via source code; mDNS timeout and name matching are well-understood concerns
- Clock status completeness: LOW -- `get_clocking_status()` confirmed non-functional; DanteApplication path works but heavyweight; "Unlocked" state detection unclear

**Research date:** 2026-04-25
**Valid until:** 2026-05-25 (stable -- netaudio release cycle is months apart)
