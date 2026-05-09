# ShowStack Milestones

## v1.0 — Network Health Monitor (SCRAPPED, not shipped)

- **Started:** 2026-04-21
- **Closed:** 2026-05-05
- **Outcome:** Phases 1–3 (foundation, switch SNMP, Dante) reached implementation, but the cloud-hosted architecture proved fundamentally incompatible with on-site Dante monitoring (WiFi/Dante NIC conflicts, mDNS interface binding, link-local discovery). Module work paused, then formally scrapped from ShowStack. Effort moved to a standalone-app codebase outside ShowStack.
- **Phase artifacts archived:** `.planning/archive/v1.0-network-monitor/`

## v2.0 — Multitrack Session Builder (in progress)

- **Started:** 2026-05-09
- **Goal:** Convert ShowStack console channel data into ready-to-use multitrack recording sessions for Reaper and Nuendo Live, with reusable templates and a per-session track editor.
- **Spec:** `multitrack_session_builder_spec.md`
