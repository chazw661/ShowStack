# Domain Pitfalls: ShowStack Network Health Monitor

**Domain:** Live audio network monitoring (Dante/mDNS, SNMP switches, LA Network)
**Researched:** 2026-04-21
**Overall confidence:** HIGH for Dante/SNMP pitfalls (official Audinate docs + community evidence), MEDIUM for Django-specific deployment patterns

---

## Critical Pitfalls

Mistakes that cause rewrites, show-stopping failures, or fundamental architectural errors.

---

### Pitfall 1: Treating netaudio/network-audio-controller as a Reliable Dante API

**What goes wrong:** The only available Python library for Dante device discovery and control (`netaudio` / `network-audio-controller` on PyPI/GitHub) is reverse-engineered from Dante Controller's network traffic. Its author explicitly states: "The official Dante API for embedded devices isn't public information, so most of this information is guesswork and will likely be wrong or unreliable." It was created as a Python learning project.

**Why it happens:** Audinate does not publish an open API for embedded device control. The library is the only Python option, so engineers assume it's production-quality.

**Consequences:**
- Channel counts are unreliable ("can't be relied upon for the actual number of useable channels")
- Device protocol responses vary by hardware revision with no documentation
- The library warns it "could make devices behave unexpectedly"
- Breakage on Audinate firmware updates with no upstream fix commitment

**Prevention:**
- Use `netaudio` only for read-only discovery (mDNS enumeration), not for issuing commands to devices
- Treat any data returned as advisory, not authoritative
- Do not build alerting logic that depends on this library's protocol commands
- For clock status and device health, use ICMP ping for reachability and fall back to mDNS presence/absence as the authoritative signal
- Consider the Dante Controller REST API (Dante Domain Manager) if the production environment uses DDM

**Detection:** Unit tests that assert on specific channel counts or device states will be flaky across hardware revisions.

**Phase:** Must be resolved in architecture design before any Dante integration code is written.

---

### Pitfall 2: mDNS Dante Discovery Silently Fails Across VLAN or Subnet Boundaries

**What goes wrong:** mDNS operates on `224.0.0.251:5353` and is explicitly limited to single-layer-2 broadcast domains. In large-format shows, Dante is almost always on a dedicated VLAN (e.g., VLAN 10 for Dante, VLAN 1 for control). The monitoring laptop on the control VLAN will see zero Dante devices, and there will be no error — discovery simply returns empty.

**Why it happens:** Engineers assume that because they can ping Dante device IPs (via a routed VLAN), mDNS discovery will also work. Ping traverses layer-3; mDNS does not.

**Consequences:**
- Dashboard shows "no Dante devices found" rather than the real device list
- Engineers conclude the monitor is broken, not that discovery is constrained
- False "all-clear" if monitoring is never seeing the actual Dante network

**Prevention:**
- Document explicitly in the UI that the monitoring laptop must be physically on the Dante VLAN (or trunked to it) for discovery to work
- At startup, show a network interface selection dialog so the engineer can point discovery at the correct NIC/VLAN interface
- Offer manual IP entry as a fallback — monitor by IP even when mDNS is unavailable
- Provide a clear diagnostic state: "mDNS discovery found 0 devices — confirm laptop is on Dante VLAN"

**Detection:** Discovery returns empty while the engineer can ping known Dante device IPs.

**Phase:** Architecture decision in Phase 1; UI diagnostic in Phase 1-2.

---

### Pitfall 3: IGMP Snooping Misconfiguration Causes Silent Multicast Failure

**What goes wrong:** Dante multicast audio streams depend on IGMP snooping being correctly configured on all switches in the path. Three failure modes exist and all present as "devices disappear" or "clock loses sync":
1. Mixed switch vendors — IGMP multicast lists desynchronize between brands
2. Multiple IGMP queriers — two switches both acting as querier corrupt membership lists
3. IGMP v2/v3 version mismatch — macOS systems using IGMP v3 silently fail when connected to IGMP v2-only switches

**Why it happens:** Audinate's own blog calls IGMP snooping issues "elusive because they don't present obvious indications of the source of the failure."

**Consequences:**
- Monitoring detects devices "offline" when they are physically connected but multicast is broken
- False alerts during show, engineer chases a software problem that is actually a switch config problem
- The monitor cannot distinguish "device is down" from "multicast routing is broken"

**Prevention:**
- In the monitoring dashboard, expose IGMP querier count and SNMP multicast group membership if the switch supports it (Cisco and Netgear do; Luminex is limited)
- Add a "switch health" diagnostic separate from "device health" so these failure modes are distinguishable
- Document for engineers: "If Dante devices disappear from monitor but are visible in Dante Controller from a laptop on the same port, suspect IGMP snooping on intermediate switches"
- Do not claim to detect IGMP snooping errors from the monitor — instead surface "devices lost visibility" with a link to a checklist

**Detection:** Multiple Dante devices drop simultaneously while LA Network amps (unicast ping) remain visible.

**Phase:** Addressed in dashboard UX design (Phase 2); SNMP switch diagnostics (Phase 3).

---

### Pitfall 4: Dante Clock Monitoring Conflates "Multiple Leader Clocks" With "Device Offline"

**What goes wrong:** A Dante clock domain has exactly one Primary Leader and zero or more Subnet Leaders. If IGMP fails, a switch misconfiguration occurs, or a device is on a different VLAN, the PTP clock leader election can produce multiple simultaneous leaders. Devices that lose sync with the leader are automatically muted by the Dante firmware. The monitoring system detecting this will see affected devices as "unresponsive" — but the root cause is clock, not connectivity.

**Why it happens:** Dante uses PTPv1 (IEEE 1588v1). A device set as "Preferred Leader" but not deriving clock from the same external source as the actual leader will diverge and eventually be muted. This is documented Audinate behavior.

**Consequences:**
- The monitor reports devices offline during a show; engineer scrambles to reboot equipment that is physically fine
- Failing to distinguish "clock sync loss" from "network connectivity loss" means wrong triage response

**Prevention:**
- Poll clock status separately from reachability (ping): a device that responds to ping but has clock status "not synced" is a clock problem, not a connectivity problem
- The netaudio library can retrieve clock domain info via mDNS — use this to show "Leader / Follower / Unlocked" as distinct states in the UI
- Alert on "clock unlocked" before alerting on "device offline" — clock unlock is the leading indicator
- Never trigger a "device offline" alert when clock status transitions; use a separate "clock sync lost" alert

**Detection:** Device responds to ICMP ping but audio is muted; Dante Controller would show clock as unlocked.

**Phase:** Clock monitoring model must be designed in Phase 1 before any alert logic is built.

---

### Pitfall 5: SNMP Returns No Data for Luminex GigaCore Switches Without Manual Enablement

**What goes wrong:** Luminex GigaCore switches — the most common entertainment-touring switch — have SNMP disabled by default. It must be manually enabled via the Arano management tool or the device's web interface. Additionally, Luminex's SNMP implementation uses the RMON standard (RFC 1757) with SNMPv1 and v2c only, and the available OIDs are limited compared to Cisco. No MIB download is listed on Luminex's main product page — only on their support portal.

**Why it happens:** Engineers assume SNMP is on because the device looks manageable. The first-time setup step is invisible to the monitoring tool.

**Consequences:**
- SNMP timeouts interpreted as switch being offline, when it's just SNMP disabled
- Build effort spent on Luminex SNMP integration that silently returns nothing on real shows
- False "all-clear" because the monitoring dashboard has no data

**Prevention:**
- On first SNMP poll failure, distinguish between "SNMP unreachable" and "SNMP disabled / not configured" in the UI
- Provide an in-app setup guide: "Luminex GigaCore: How to enable SNMP via Arano"
- Fall back to ICMP ping for switch reachability when SNMP is unavailable — at minimum, confirm the switch is alive
- Only poll OIDs known to work on Luminex (standard interface MIBs: IF-MIB OIDs for port up/down/speed); do not attempt enterprise-specific OIDs

**Detection:** SNMP query times out with no response (not an authentication error) on a Luminex switch that is pingable.

**Phase:** Switch integration design (Phase 2–3); setup guide in Phase 3.

---

### Pitfall 6: SNMP v2c Community String "public" Is Wrong on Secured Show Networks

**What goes wrong:** The default SNMP community string on most switches is `public`. On secured show networks (broadcast, corporate, tour), IT departments routinely change community strings and may disable SNMPv1/v2c entirely in favor of SNMPv3. If the monitor hardcodes or defaults to `public`, SNMP authentication fails silently (SNMP v2c returns no error on auth failure — the agent simply does not respond).

**Why it happens:** SNMP v2c sends community strings in plaintext and provides no auth challenge-response. A wrong string produces the same timeout behavior as SNMP being disabled.

**Consequences:**
- SNMP appears broken; engineer assumes a code bug
- On broadcast/corporate events, IT will refuse to give credentials to the monitoring laptop at all — requiring fallback to ping-only mode

**Prevention:**
- Treat community string as a per-project configurable field, not a hardcoded default
- Support SNMPv3 (auth + priv) from the start — do not defer it, as broadcast/IT environments require it
- Surface authentication errors vs. timeout errors distinctly in the UI
- Design a graceful degraded mode: "SNMP unavailable — monitoring switch reachability via ping only"

**Detection:** SNMP polling times out but the switch is reachable via ping; no `noSuchObject` or error response is returned.

**Phase:** SNMP configuration model must support v3 credentials from Phase 2 onwards.

---

## Moderate Pitfalls

Mistakes that create significant rework or user-experience failures but don't block core functionality.

---

### Pitfall 7: Django Blocking I/O in SNMP/Ping Polling Requests

**What goes wrong:** SNMP polls, ICMP pings, and mDNS queries are all blocking network I/O. If these run synchronously in Django view handlers or WebSocket consumers, they block the entire WSGI/ASGI worker for their duration. On a show with 30+ devices being polled every 5 seconds, this saturates all workers.

**Prevention:**
- All polling must run in a background process (Celery worker or equivalent), never in a request handler
- Django Channels WebSocket consumers push pre-computed state to clients; they do not compute it
- Use `snmp-cmds` or `pysnmp-lextudio` with async support, or run sync SNMP calls inside `asyncio.to_thread()` to avoid blocking the event loop
- Railway supports a separate worker dyno process — use it from the start

**Phase:** Architecture decision before any polling code is written (Phase 1).

---

### Pitfall 8: Browser Tab Throttling Breaks WebSocket Heartbeats, Causing False Disconnects

**What goes wrong:** Chrome throttles background tabs to one-execution-per-minute for JavaScript timers starting approximately 5–7 minutes of inactivity. Safari closes WebSocket connections at exactly 5 minutes of inactivity. If the monitoring dashboard is open in a secondary monitor tab while the engineer works in another tab, the WebSocket heartbeat will stop firing, and the server-side Django Channels consumer will time out and close the connection. The monitoring dashboard goes blank or stale with no user notification.

**Why it happens:** Chrome/Safari power-saving mechanisms apply to all background tabs. WebSocket connections themselves are not throttled (the socket stays open), but the JavaScript heartbeat timer that keeps the connection alive stops executing.

**Prevention:**
- Move the WebSocket heartbeat and reconnection logic to a `Web Worker` — workers run on a separate thread not subject to tab throttling
- Implement exponential backoff reconnection on the client
- Use the Page Visibility API to detect tab backgrounding and trigger an immediate state refresh on tab becoming visible
- Server-side: configure Daphne/Uvicorn WebSocket ping interval at the ASGI level (not relying on client heartbeat alone)

**Detection:** Dashboard shows stale data; console shows WebSocket disconnect after ~5 minutes of tab inactivity.

**Phase:** Frontend architecture decision in Phase 2.

---

### Pitfall 9: Alert Fatigue From Show Setup and Teardown Events

**What goes wrong:** During load-in (before show) and load-out (after show), devices are constantly powered on and off, VLANs are being configured, and cables are being patched. A monitoring system that fires alerts on every device-down event will produce dozens of alerts within minutes of load-in starting. Engineers will immediately mute or ignore all alerts — including critical ones during the show itself.

**Why it happens:** Monitoring systems designed for 24/7 IT environments assume a "steady state" that live event networks do not have.

**Consequences:**
- Engineers disable alerts entirely or stop trusting the monitor
- Real show-day issues are missed because the system "cried wolf" during setup

**Prevention:**
- Implement a "show mode" toggle: Setup / Show / Wrap. Alerts are suppressed or lowered in severity during Setup and Wrap modes
- In Show mode, apply a debounce threshold: a device must be offline for a configurable duration (default: 10 seconds) before an alert fires
- Add "expected offline" device states — engineer can mark a device as "powered off" to suppress its alerts
- Session history should record all state changes regardless of alert mode, for post-show analysis

**Phase:** Alert design (Phase 2); show mode UX (Phase 2–3).

---

### Pitfall 10: Django Channels Memory Leaks From Uncleaned Group Memberships

**What goes wrong:** Django Channels uses a channel layer (Redis-backed in production) to manage group subscriptions. If a WebSocket consumer's `websocket_disconnect` handler does not call `channel_layer.group_discard()`, disconnected clients accumulate as dead entries in the Redis group. Over a show day with many browser refreshes, reconnections, and tab opens, this leaks memory in Redis and adds latency to group broadcasts.

**Prevention:**
- Always call `await self.channel_layer.group_discard(...)` in `websocket_disconnect`
- Use `AsyncWebsocketConsumer` (never `WebsocketConsumer`) — the sync base class blocks the event loop
- Use Redis as the channel layer in production (not in-memory) — Railway's Redis addon covers this
- Add a periodic task that audits group membership size; alert if it exceeds expected maximum

**Detection:** Redis memory grows continuously over a show day; broadcast latency degrades over time.

**Phase:** WebSocket infrastructure (Phase 2).

---

### Pitfall 11: The "Local Network Access" Dependency Is Not Communicated to Users

**What goes wrong:** ShowStack runs on Railway (cloud). The Network Health Monitor requires the laptop running the browser to have direct layer-3 access to Dante VLANs, SNMP-accessible switches, and LA Network amplifiers. This is a fundamentally different access model than any other ShowStack module. Engineers who open the dashboard expecting it to "just work" from a cloud URL will see empty dashboards with no explanation.

**Why it happens:** Every other ShowStack module operates on data the user entered into a cloud-hosted form. This module requires network reachability from the client's machine — an invisible precondition.

**Consequences:**
- Frustrated engineers filing "the monitor doesn't work" bugs
- Support overhead explaining the access model repeatedly

**Prevention:**
- At module activation, show a prerequisite check UI: "Is this laptop connected to the show network? Can you ping [a known device IP]?"
- Document clearly in the module header: "This monitor requires the laptop to be physically on the show network"
- Provide an in-app network diagnostic: "Click to test — can we reach the Dante VLAN from this browser?"
- Consider building a local agent concept (a small script the engineer runs on the show laptop that acts as a network proxy back to the Django backend) if the Railway-hosted model proves architecturally unworkable

**Phase:** UX design in Phase 1; diagnostic tooling in Phase 2.

---

### Pitfall 12: Correlating Multi-Layer Events Produces Confusing Duplicate Alerts

**What goes wrong:** A single failed gigabit uplink can simultaneously produce: 10 Dante devices offline (mDNS/ping fails), 5 LA Network amps offline (ping fails), 1 switch port down (SNMP ifOperStatus), and 1 clock domain leader gone (PTP). Without event correlation, the monitor fires 17 independent alerts for what is one root cause.

**Why it happens:** Most monitoring tools treat each sensor independently. Live audio engineers cannot diagnose a topology-level failure from 17 simultaneous single-device alerts.

**Prevention:**
- Build event grouping from the start: "Multiple devices offline simultaneously on the same switch" → one grouped alert, not N individual alerts
- Store device-to-switch port mappings (from the existing ShowStack project data) so co-failures on the same switch port can be correlated
- Show a "possible root cause" suggestion: "6 Dante devices and 2 amps are all downstream of switch port GE1/0/3 which is currently down"
- Use a 3-second debounce window — collect all failures before generating alerts, then group by topology

**Phase:** Alert engine design (Phase 2–3).

---

## Minor Pitfalls

---

### Pitfall 13: Energy Efficient Ethernet (EEE / "Green Ethernet") Disrupts PTP Clock

**What goes wrong:** Dante's own documentation lists EEE as a cause of clock instability. Many switches ship with EEE enabled. When a switch reduces power on idle ports, the PTP timing messages that keep the Dante clock domain synchronized are delayed, causing clock jitter that eventually results in automatic device muting.

**Prevention:** In the switch monitoring SNMP data, flag any port with EEE enabled that also carries Dante traffic. Surface this as a warning: "Energy Efficient Ethernet is enabled on this port — this can cause Dante clock instability."

**Phase:** Switch monitoring detail (Phase 3).

---

### Pitfall 14: LA Network Reachability via Ping Gives False Confidence on Power Amp State

**What goes wrong:** L'Acoustics amps have no public API for DSP state, gain, limiting, or thermal status. ICMP ping confirms the amp is on the network but nothing about its operational status. "Online" on the monitor means "IP stack is responding" — the amp could be in clip, muted, or in a protection state.

**Prevention:**
- Label LA Network amp status explicitly as "Network reachable" not "Healthy" or "Online"
- Do not add a green status indicator that implies audio health for LA Network amps
- Document this limitation in the UI tooltip: "LA Network status reflects IP reachability only"

**Phase:** LA Network integration (Phase 2).

---

### Pitfall 15: SNMP Polling Interval Too Aggressive Triggers Switch SNMP Rate Limiting

**What goes wrong:** Some entertainment switches (particularly entry-level Netgear and certain Luminex firmware versions) have low SNMP request rate limits. Polling 30 OIDs across 8 switch ports every 5 seconds can generate 48 SNMP requests/minute per switch. Switches may rate-limit or drop responses, producing spurious "port offline" readings.

**Prevention:**
- Default polling interval to 15–30 seconds for SNMP switch data (port status changes on show networks are rare)
- Default polling interval to 5–10 seconds for device reachability (ICMP ping is cheap)
- Make polling intervals configurable per monitoring type
- Use SNMP GetBulk (v2c) to retrieve multiple OIDs in one request rather than individual Gets

**Phase:** Polling engine design (Phase 2).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Dante device discovery | netaudio library unreliability | Use mDNS for enumeration only; treat protocol commands as experimental |
| Dante clock monitoring | Conflating clock loss with device offline | Model clock status as distinct from reachability |
| SNMP switch integration | Luminex SNMP disabled by default | First-run setup guide; graceful ping-only fallback |
| SNMP switch integration | Wrong community string = silent timeout | Per-project credential config; SNMPv3 support from day one |
| mDNS discovery on VLAN'd networks | Empty discovery with no error | NIC/VLAN selection UI; manual IP entry fallback |
| Alert design | Alert fatigue during load-in | Show mode toggle; debounce; "expected offline" states |
| WebSocket infrastructure | Tab throttling / Django Channels memory leak | Web Workers for heartbeat; group_discard on disconnect |
| LA Network integration | Overstating amp health from ping | Label as "Network reachable" not "Healthy" |
| Multi-device correlation | 17 alerts for one uplink failure | Event grouping with topology-aware correlation |
| User onboarding | Engineers confused why dashboard is empty | Network prerequisite check UI at module open |

---

## Sources

- Audinate — IGMP Snooping Pitfalls: https://www.getdante.com/blog/well-intentioned-mishaps-with-igmp-snooping/
- Audinate — Clock Status Monitoring docs: https://dev.audinate.com/GA/dante-controller/userguide/webhelp/content/clock_status_monitoring.htm
- Audinate — Dante Clock Status View: https://dev.audinate.com/GA/dante-controller/userguide/webhelp/content/clock_status_view.htm
- Audinate — Multiple Leader Clocks FAQ: https://www.getdante.com/support/faq/multiple-leader-clocks/
- Audinate — Dante Network Design Guide (Yamaha mirror): https://usa.yamaha.com/products/contents/proaudio/docs/dante_network_design_guide/301_multicast.html
- Audinate — DDM SNMP MIBs: https://www.getdante.com/support/faq/ddm-mibs-for-snmp-integration/
- Audinate — Dante and PTP Technical Dive (2025): https://www.getdante.com/wp-content/uploads/2025/02/DanteAndPrecisionTimeProtocol-TechnicalDive-20250221.pdf
- Shure — Dante Networks and IGMP Snooping: https://service.shure.com/s/article/dante-networks-and-igmp-snooping
- GitHub — network-audio-controller Technical Details (reverse-engineered Dante): https://github.com/chris-ritsen/network-audio-controller/wiki/Technical-details
- Luminex — SNMP/RMON on GigaCore switches: https://support.luminex.be/portal/en/kb/articles/snmp-rmon-on-gigacore-switches
- Luminex — Luminode SNMP MIB Details: https://support.luminex.be/portal/en/kb/articles/luminode-snmp-mib-details
- Django Channels — Memory leak issues (Daphne): https://github.com/django/daphne/issues/373
- Django Channels — Memory leak (channels_redis): https://github.com/django/channels/issues/1052
- WebSocket tab throttling (PixelsTech): https://www.pixelstech.net/article/1719122489-The-Pitfall-of-WebSocket-Disconnections-Caused-by-Browser-Power-Saving-Mechanisms
- Supabase Docs — Realtime silent disconnections in backgrounded apps: https://supabase.com/docs/guides/troubleshooting/realtime-handling-silent-disconnections-in-backgrounded-applications-592794
- BLACK HILLS INFOSEC — SNMP Community Strings security: https://www.blackhillsinfosec.com/snmp-strings-attached/
- Railway — Django + Celery + Redis deployment: https://voltageitlabs.com/blog/bf367624-302c-4c7d-8a57-c3d53af71156/
- WebSocket.org — Django Channels ASGI deployment: https://websocket.org/guides/frameworks/django/
