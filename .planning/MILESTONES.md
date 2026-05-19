# ShowStack Milestones

## v1.0 — Network Health Monitor (SCRAPPED, not shipped)

- **Started:** 2026-04-21
- **Closed:** 2026-05-05
- **Outcome:** Phases 1–3 (foundation, switch SNMP, Dante) reached implementation, but the cloud-hosted architecture proved fundamentally incompatible with on-site Dante monitoring (WiFi/Dante NIC conflicts, mDNS interface binding, link-local discovery). Module work paused, then formally scrapped from ShowStack. Effort moved to a standalone-app codebase outside ShowStack.
- **Phase artifacts archived:** `.planning/archive/v1.0-network-monitor/`

## v2.0 — Multitrack Session Builder (shipped)

- **Started:** 2026-05-09
- **Closed:** 2026-05-14
- **Goal:** Convert ShowStack console channel data into ready-to-use multitrack recording sessions for Reaper and Nuendo Live, with reusable templates and a per-session track editor.
- **Spec:** `multitrack_session_builder_spec.md`
- **Outcome:** 5 phases / 38 requirements shipped end-to-end. Reaper `.RPP` byte-stable export, Nuendo Live `.nlpr` template-injection export via `lxml`, Yamaha CL/QL + Rivage PM CSV import, owner-scoped Multitrack Templates, channel record defaults (`default_record` + `default_record_color`). HUMAN-UAT signed off across all 5 phases.

## v2.1 — Collaboration & User Management (shipped)

- **Started:** 2026-05-15
- **Closed:** 2026-05-15
- **Goal:** Reduce friction for repeat collaborators on ShowStack projects via owner-defined named crew rosters.
- **Outcome:** Phase 6 (Trusted Crew Rosters) shipped — owner-scoped `Crew` model with `CrewMember` rows, bulk-add UI, pre-onboarding email invites via Resend, auto-claim on register (case-insensitive email match), regression test suite (7/7 plans). Beta-validated (memory note: "bulk-add + auto-claim + pending-signup email all working in beta"). Follow-up fix #12 hid `CrewMember` / `CrewProjectAdd` from admin sidebar.

## v2.2 — Signal Flow Diagrammer (in progress)

- **Started:** 2026-05-19
- **Goal:** Drag-and-drop signal-flow diagrammer (Lucidchart-style) that uses ShowStack equipment as smart shapes, with connector styles per signal type and circuit-label autocomplete from existing signal-name fields.
- **Driver:** GitHub issue #13 — engineers manually redraw signal flow in Visio / Lucidchart every gig.
- **Library:** JointJS core (MIT, vanilla JS).
- **v2.2 boundary:** module MVP only — desktop canvas, smart shapes, orthogonal connectors with type variants, circuit-label autocomplete, JSON autosave, PNG export. Mobile viewer + obstacle-aware auto-routing + custom SVG faceplates + PDF/SVG export + version snapshots deferred to v2.3+.
