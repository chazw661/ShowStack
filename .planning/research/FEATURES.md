# Feature Landscape: Network Health Monitor

**Domain:** Live audio network monitoring for professional live events / touring / broadcast
**Researched:** 2026-04-21
**Overall confidence:** HIGH (core protocol behaviors) / MEDIUM (competitive landscape)

---

## Context: The Problem Space

A large-format live show involves three parallel networks that are each managed by separate vendor tools:

- **Dante** — monitored via Dante Controller (free desktop app, mDNS discovery, clock status panel, event log). No persistent history, no alerting outside the app window, no integration with anything else.
- **LA Network / LA-RAK amps** — monitored via LA Network Manager (real-time signal levels, temperature, voltage, limiter activity for the past 4 minutes). Proprietary protocol, no public API for deep telemetry.
- **Entertainment switches** — Luminex GigaCore runs ARANEO (topology viewer, VLAN health checks, bandwidth proximity alerts). Cisco/Netgear switches expose SNMP. No cross-tool aggregation.

The A1 engineer has three separate app windows open, no unified view, no persistent alerting, and no post-show log to correlate "what happened at 10:47 PM?" with a network event. That gap is what ShowStack's Network Health Monitor fills.

**No competing product provides a unified view across all three domains.** Dante Director is Dante-only and SaaS-oriented. ARANEO is Luminex-only. LA Network Manager is L-Acoustics-only. PRTG/Zabbix are generic IT tools requiring significant configuration — not deployable in 20 minutes at load-in.

---

## Table Stakes

Features users expect. Missing = product feels incomplete or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Per-device reachability status (up/down/unreachable) | Every monitoring tool in every domain shows this | Low | ICMP ping + mDNS presence. Must update within ~5s of a device going offline. |
| Dante device auto-discovery | Dante Controller does this automatically; engineers expect it to just find everything | Medium | python-zeroconf listening for `_netaudio-arc._udp.local` and `_netaudio-cmc._udp.local` service types. Requires laptop on same subnet as Dante network. |
| Dante clock status: master/follower/locked/unlocked | Dante Controller shows this; engineers live-watch it. A clock loss = audio muted across the entire network. | Medium | Dante CM API (port 8700-8800) or parsing mDNS TXT records. Device-level clock role + lock state. |
| Switch port status (up/down) per port | Engineers need to know which physical port a device dropped on, not just that a device is gone | Medium | SNMP GET `ifOperStatus` (IF-MIB, OID .1.3.6.1.2.1.2.2.1.8) polled every 10-15s. |
| At-a-glance dashboard: green/yellow/red | Every monitoring tool uses this convention; engineers scan from 10 feet away | Low | Three-state: healthy / warning / critical. Roll up per-domain and per-device. |
| Active alert on device offline (visual + audio) | During a show, the engineer is not staring at the monitor. They must be notified. | Low | Browser notification API + on-screen banner + optional audio cue. Must fire within one poll cycle. |
| Active alert on Dante clock loss / instability | Clock loss = show stops. This is the highest-severity Dante event. | Medium | Monitor clock master changes and devices reporting "not locked" state. |
| LA Network device reachability (ping/ARP) | No public API for amp telemetry, but "is the amp reachable?" is still show-critical | Low | ICMP ping to amp management IPs defined in the Amplifiers module. |
| Integration with existing ShowStack device records | Engineers already have all device IPs in ShowStack (Consoles, I/O Devices, Amplifiers, etc.) | Medium | FK references to existing models. No duplicate IP entry. Project-scoped. |
| Session history: timeline of state changes during show day | Engineers need to answer "what time did that device drop?" after a show or during an intermission | Medium | Append-only log table: timestamp, device, from_state, to_state, severity. Retained per show day. |

---

## Differentiators

Features that set this product apart from single-domain tools. Not expected by users unfamiliar with ShowStack, but high value once discovered.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Unified cross-domain view (Dante + LA Network + Switches) | No other tool shows all three simultaneously. The A1 sees the entire show network in one window. | High | Requires polling three different protocols. UI must present them as a coherent picture, not three separate panels. |
| Pre-show network health check report | Engineer runs a check at top-of-day: "all 34 expected devices reachable, clock master confirmed, 0 switch errors." Confidence before doors open. | Medium | Compare discovered devices vs project-defined devices. Report missing devices, clock anomalies, switch error counts. |
| Correlation across domains (e.g. switch port down = Dante device missing) | When a Dante device disappears, the engineer needs to know if the switch port also went down. Correlated alerts prevent wild-goose chases. | High | Link switch ports to Dante/amp devices in device metadata. Surface both events together when they co-occur within a time window. |
| Switch bandwidth proximity warning (pre-failure alerting) | Luminex ARANEO shows connections close to bandwidth limit before they fail. This should be a first-class ShowStack alert. | Medium | SNMP `ifInOctets`/`ifOutOctets` counters, calculate utilization vs port speed. Warn at 70%, critical at 90%. |
| Dante multicast bandwidth monitoring per device | Multicast overload is a silent Dante killer that doesn't appear as a device error. Engineers rarely know to watch for it. | Medium | Dante CM API exposes per-device multicast flow counts and bandwidth. Threshold alert. |
| Error counter trending on switch ports | A port accumulating errors over a show day predicts a failure that hasn't happened yet. Raw error counters alone are not actionable. | Medium | Store SNMP `ifInErrors`/`ifOutErrors` deltas. Alert on rate increase, not just absolute value. |
| Show-day session scope (reset at start of show day) | History relevant to "this show" not "all time." Clutter-free. | Low | Session object with start_time, tied to ShowStack project. Engineers start a new session at load-in. |
| Export show network log as PDF/CSV | A1 sends the log to the production manager or tour manager after a failure. Documentation for insurance, post-mortems, or venue disputes. | Low | Render the timeline table as PDF or CSV from the session history. |
| Mobile-friendly status view at `/m/` | A1 walks the stage and floor during a show; needs to glance at their phone to see network status without returning to FOH. | Low | Read-only status view. ShowStack already has a mobile interface at `/m/`. |

---

## Anti-Features

Things to deliberately NOT build in this module.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Dante subscription routing from this module | The Dante Subscription Planner module owns that domain and is frozen. Mixing routing and monitoring creates architectural confusion and duplicates a feature. | Link to the existing Dante Subscription Planner view if the engineer needs to reconfigure routing. |
| Amplifier DSP / EQ / gain control | LA Network Manager handles amp control. ShowStack's module is connectivity-only by design (per PROJECT.md). Adding DSP control requires the proprietary L-Acoustics protocol which is not publicly documented. | Surface a link to LA Network Manager when an amp alert fires. |
| VLAN provisioning or switch configuration writes | Read-only monitoring only. Writing switch config from a web app at show day = dangerous. Engineers provision VLANs before load-in, not during. | Document VLAN configuration in a separate network planning module (future). |
| Cloud relay / remote monitoring without local network access | Architecture explicitly requires the laptop to be on-site on the show networks. Building a cloud relay introduces latency, security complexity, and Railway dependency for a real-time use case. | Clearly document that ShowStack must run on a laptop physically on the show network. |
| Always-on background monitoring service | A separate daemon/service would require installation and OS-level permissions, violating the "open browser, it works" model. | Run polling from the Django process when the monitor page is open; pause polling when the page is closed. |
| Historical telemetry retention beyond the show season | Long-term data storage creates GDPR/privacy complexity and Railway Postgres cost. Engineers care about the current show and the last few shows, not 2-year-old data. | Implement a retention policy: keep session history for 90 days, then purge. |
| Alert suppression during known maintenance windows | Sophisticated alerting features from enterprise NMS tools (maintenance windows, dependency-based suppression) are overkill for a single-show workflow. They add configuration burden with no payoff in this context. | Use a simple manual "acknowledge" action on active alerts to silence them during maintenance. |
| Per-device packet-level analysis or capture | Wireshark-level diagnostics are not feasible from a Django web app and are not the A1's job. | Link to Dante Controller's built-in diagnostics for deep packet-level Dante analysis. |

---

## Feature Dependencies

```
Dante device auto-discovery
  --> Dante clock status monitoring (need discovered device list to query clock API)
  --> Dante multicast bandwidth monitoring (need device list)
  --> Correlation (Dante device) <-> (switch port) (need discovered device IP)

Switch SNMP polling (port up/down)
  --> Switch error counter trending (need baseline)
  --> Switch bandwidth monitoring (need baseline octets reading)
  --> Correlation (Dante device) <-> (switch port)

Device reachability (ICMP ping)
  --> LA Network reachability (same mechanism)
  --> Pre-show health check (aggregates reachability across all device types)

Session history (state change log)
  --> Post-show export (reads from history table)
  --> Show-day session scope (history is scoped to session)

Integration with existing device records
  --> All monitoring features (device IPs sourced from existing module records)
  --> Pre-show health check (compare discovered vs expected)
  --> Correlation across domains (device metadata links switch ports to Dante devices)
```

---

## Alert Design Principles for Live Shows

Based on research into live sound Dante troubleshooting patterns and general network monitoring best practices, these principles govern how alerts should behave to avoid false alarms in a show environment:

**The live show alerting constraint is real and severe.** An engineer responding to a false alarm during a show is worse than no alert at all — it creates panic, distracts the engineer, and erodes trust in the tool so they stop looking at it entirely. The industry standard (Dante Controller, ARANEO) is to alert only on definitive state changes, not transient blips.

1. **Confirm before firing.** A device must fail N consecutive polls (recommend N=3, ~15 seconds) before triggering a critical alert. A single missed poll is not an alert.
2. **Severity tiers.** Three levels: Info (state change, logged but no notification), Warning (early indicator, visual only), Critical (definitive failure, visual + audio). Only Critical gets audio notification.
3. **One alert per event.** A Dante device disappearing and its switch port going down is one event, not two separate alerts.
4. **Manual acknowledge, not auto-resolve.** An alert stays visible until the engineer explicitly dismisses it, even if the device comes back online. Auto-resolve hides whether the engineer actually saw the problem.
5. **Show-safe defaults.** Default thresholds must work without tuning on a typical show. Bandwidth warning at 70% of port capacity. Error rate alert at >10 errors/minute sustained for 3 minutes. Clock instability alert only on definitive "not locked" state, not histogram jitter.

---

## MVP Recommendation

The minimum viable set for an engineer to get meaningful value on day one:

**Must have for MVP:**
1. Dante device discovery and per-device reachability (up/down) — automatic, no configuration
2. Dante clock master identification and lock status per device
3. Switch SNMP port status (up/down) for configured switches
4. At-a-glance dashboard with green/yellow/red rollup
5. Critical alert on device offline or clock loss (visual, with confirm-before-firing logic)
6. Session history: state change log with timestamps
7. Integration with existing ShowStack project device records (source IPs from existing modules)
8. LA Network amp reachability via ping

**Defer to phase 2:**
- Switch bandwidth and error trending (requires baseline data collected over multiple shows to be meaningful)
- Cross-domain correlation (Dante device + switch port linkage) — powerful but requires device metadata enrichment
- Pre-show health check report — useful but not blocking
- Dante multicast bandwidth monitoring — niche, medium-complexity
- Export as PDF/CSV — useful, not urgent
- Mobile status view — quick win but not blocking MVP

---

## Sources

- [Dante Controller Clock Status Monitoring](https://dev.audinate.com/GA/dante-controller/userguide/webhelp/content/clock_status_monitoring.htm) — HIGH confidence, official Audinate docs
- [Dante Controller User Guide v4.17.x](https://dev.audinate.com/GA/dante-controller/userguide/pdf/latest/) — HIGH confidence, official Audinate docs
- [LA Network Manager Product Page](https://www.l-acoustics.com/products/network-manager/) — HIGH confidence, official L-Acoustics
- [Luminex ARANEO Software](https://www.luminex.be/products/software/araneo/) — MEDIUM confidence, product marketing page
- [Sennheiser Dante Clock Loss Troubleshooting](https://help.sennheiser.com/hc/en-us/articles/30046611307666-Troubleshooting-Steps-for-Dante-Clock-Loss) — HIGH confidence, official vendor support doc
- [ProSoundWeb: Dante Clock Issues Forum](https://forums.prosoundweb.com/index.php?topic=170845.0) — MEDIUM confidence, community forum
- [RFC 2863: The Interfaces Group MIB (IF-MIB)](https://datatracker.ietf.org/doc/html/rfc2863) — HIGH confidence, IETF standard
- [network-audio-controller (GitHub)](https://github.com/chris-ritsen/network-audio-controller) — MEDIUM confidence, open source, Python Dante mDNS discovery
- [Dante Domain Manager Monitoring Features](https://www.getdante.com/products/network-management/dante-domain-manager/) — HIGH confidence, official Audinate product page
- [LogicMonitor: Preventing Alert Fatigue](https://www.logicmonitor.com/blog/network-monitoring-avoid-alert-fatigue) — MEDIUM confidence, general NMS best practices
