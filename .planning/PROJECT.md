# ShowStack

## What This Is

A Django 5.x multi-tenant SaaS platform for professional live audio production management. ShowStack stores the project data — consoles, channels, patches, amplifiers, comm config, IP plans — that a lead A1 engineer needs across corporate events, tours, and broadcast, and converts that data into the deliverables every show actually requires: Yamaha console session files, Clear-Com `.cca` configs, Reaper / Nuendo recording sessions, PDF exports, and more.

Deployed at https://showstack.io. Sole developer: Charlie Lawson. Legal owner: Lawson Design & Engineering (USPTO Class 42 trademark filed 2026-03-19).

## Core Value

ShowStack knows your patch, your labels, and your gear. Once entered, that data drives every export your show needs — no double-entry, no copy-paste between vendor tools, no rebuilding the same session from scratch on every gig.

## Requirements

### Validated

- [x] Yamaha Rivage PM CSV export (11-file Console File Converter format)
- [x] Clear-Com Arcadia `.cca` offline config export — first software to do this
- [x] Clear-Com FreeSpeak II `.cca` offline config export
- [x] Mic Tracker, Power Distribution Calculator, IP Address Management, Console Templates
- [x] Soundvision Predictions PDF parsing (L'Acoustics)
- [x] Mobile interface (`/m/`) for the most-used views
- [x] Session-based project scoping (`CurrentProjectMiddleware`)
- [x] Role-based permissions (superuser / premium owner / editor / viewer)
- [x] Custom admin site (`showstack_admin_site`)
- [x] Per-row delete on amplifier change list (issue #1, fixed 2026-05-09)
- [x] Multitrack Session Builder — core sessions, track editor, Reaper export (Phase 1, 2026-05-13)
- [x] Console CSV import (Yamaha CL/QL/Rivage PM channel labels) — Phase 2, 2026-05-13
- [x] Multitrack Templates — owner-scoped, cross-console portable (Phase 3, 2026-05-13)
- [x] Nuendo Live `.nlpr` export — `lxml` template-injection with Yamaha→Farb color mapping (Phase 4, 2026-05-14)
- [x] Channel record defaults — `default_record` + `default_record_color` seed flags on `ConsoleChannel` (Phase 5, 2026-05-14)
- [x] Trusted Crew Rosters — owner-defined named groups, bulk-add with pre-onboarding email invites, auto-claim on register (Phase 6 / v2.1, 2026-05-15)
- [x] Signal Flow Diagrammer foundation — `SignalFlowDiagram` model, CRUD views, editor HTML shell with vendored JointJS 4.2.4 (Phase 7 / v2.2, 2026-05-20)
- [x] Signal Flow Diagrammer canvas — JointJS paper + shape picker + connector smart-routing + manual save flow + selection/undo (Phase 8 / v2.2, 2026-05-21)
- [x] Signal Flow Diagrammer autosave & orphan rendering — debounced JSON autosave with optimistic-locked `If-Match` 409 path, three-state status indicator, keepalive flush on unload, server-side `_enrich_nodes()` for label propagation + ghosted orphan rendering, node-mode inspector with Re-link/Delete (Phase 9 / v2.2, 2026-05-22)

### Active

(See Current Milestone below for the active capability under construction.)

### Out of Scope

- Real-time DAW or console transport control — ShowStack is a *planning* and *export* tool, not a live-control surface
- Audio metering, signal analysis, or any audio-stream processing
- Console families outside Yamaha CL/QL/Rivage PM — separate effort if/when demand surfaces
- Network monitoring inside ShowStack — moved to a standalone-app architecture (v1.0 scrapped)
- Replacing vendor tools that already work well (Dante Controller, LA Network Manager, Studio Manager) — ShowStack feeds them, doesn't replace them

## Current State

**Latest shipped:** v2.2 Signal Flow Diagrammer — 2026-05-22 (Phases 7, 8, 9)

ShowStack engineers can draw project-scoped signal-flow diagrams on a live JointJS canvas with smart shapes linked to Console / Device / SpeakerArray / CommBeltPack records, typed orthogonal connectors (analog / AES / Dante / MADI / intercom with distinct line styles + dash patterns for grayscale print), and the full canvas UX (pan / zoom / snap / undo / multi-select / keyboard delete / viewport restore). Edits persist via debounced 1500 ms autosave with `If-Match` optimistic-lock conflict handling — multi-tab conflicts reveal a locked-copy banner with hard reload; tab-close edits flush via `keepalive`. Equipment renames propagate on next diagram load via server-side `_enrich_nodes()`; deleted equipment renders ghosted with a node-mode inspector offering Re-link or Delete.

**Archived milestones (full detail):**
- [v2.2 Signal Flow Diagrammer](./milestones/v2.2-ROADMAP.md) — Phases 7–9, shipped 2026-05-22
- v2.1 Collaboration & User Management — Phase 6 Trusted Crew Rosters, shipped 2026-05-15 _(pre-dates milestone-close workflow; no archive file)_
- v2.0 Multitrack Session Builder — Phases 1–5, shipped 2026-05-14 _(pre-dates milestone-close workflow; no archive file)_

## Next Milestone Goals

**v2.3 — not yet planned.** Run `/gsd-new-milestone` to scope it.

**Top candidate for the v2.3 opening phase (carried forward from v2.2 deferred scope):**
- **Autocomplete & PNG Export** _(was v2.2 Phase 10, never started)_ — Circuit-label autocomplete from signal-name fields (`DeviceInput.signal_name`, `DeviceOutput.signal_name`, `ConsoleInput.source`, `ConsoleAuxOutput.name`) + JS autocomplete widget + one-click PNG export via the already-vendored `html-to-image` (Phase 7 vendor bundle). Closes LBL-01, LBL-02, LBL-03, EXP-01.

**v2.2 advisory items worth closing in v2.3 polish:**
- Pre-v2.2 carried UAT/verification gaps from phases 1, 3, 5, 6 (see STATE.md `## Deferred Items`). Phase 6 has 6 pending UAT scenarios; the rest are status-only false positives that should be cleaned up.
- Multi-line `{# … #}` Django comment audit was project-wide during v2.2 close — `feedback_django_multiline_template_comments.md` memory locked in to prevent recurrence.

## Context

ShowStack is in beta with live-audio engineer testers. The Multitrack Session Builder is the first new module since the Network Health Monitor was scrapped — that work moved to a separate standalone application. The standalone is its own codebase outside ShowStack.

**Key architectural decisions (carry forward from existing modules):**
- Session-based project scoping via `CurrentProjectMiddleware` — views and querysets scope themselves to `request.current_project`, never via URL-routed project IDs.
- All admin registers on `showstack_admin_site`, not `admin.site`. `admin_ordering.py` controls sidebar grouping and must be updated when new admin-registered models land.
- Templates extend `admin/base_site.html` for the dark theme.
- `BaseEquipmentAdmin` provides role-based permission filtering — extend it, don't reimplement.

**Deployment:** Railway uses `railway.json`'s `startCommand` (NOT the Procfile). Push to `main` triggers automatic redeploy.

## Constraints

- **Existing-codebase integration:** new modules must coexist with the monolithic `planner` app (~5700-line views.py, ~6000-line admin.py, ~4500-line models.py). Prefer foreign keys to existing models over duplicating data.
- **Beta-tester sensitivity:** breaking changes to existing modules need beta-tester coordination. New modules are additive and lower-risk.
- **Solo development:** no merge gates beyond Charlie's review; CI is light. Compensate with explicit verification gates in GSD phase plans.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Each ShowStack module is its own GSD milestone (v2.0, v2.1, ...) under a single ShowStack-as-platform project | One-module-per-project cluttered planning; unifying makes cross-module work tractable | In effect from 2026-05-09 |
| Network Health Monitor scrapped from ShowStack | WiFi/Dante NIC conflicts make cloud-hosted monitoring impossible — moved to standalone-app architecture | v1.0 closed without ship |
| Multitrack Session Builder selected as v2.0 | Strong differentiation against flaky Yamaha-Steinberg native integration; Reaper has no first-party path | Shipped 2026-05-14 (Phases 1–5) |
| Signal Flow Diagrammer selected as v2.2 (issue #13) | Engineers manually redraw signal flow in Visio/Lucidchart every gig despite having all the data in ShowStack; closes a high-leverage gap by reusing existing equipment/signal-name records | In progress |
| JointJS core (MPL-2.0) chosen over drawio iframe and maxGraph for v2.2 | Vanilla-JS drop-in matches ShowStack's no-framework frontend; iframe-embed loses native feel and complicates click-through-to-record; maxGraph requires TS build | Locked 2026-05-19 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-22 — Milestone v2.2 Signal Flow Diagrammer closed via `/gsd-complete-milestone`. v2.2 archive: `.planning/milestones/v2.2-ROADMAP.md` + `.planning/milestones/v2.2-REQUIREMENTS.md`. 31 / 35 v2.2 requirements shipped (89%); LBL-01..03 + EXP-01 (Phase 10 — Autocomplete & PNG Export) carried forward to v2.3. Git tag `v2.2` created at HEAD. ROADMAP.md collapsed to milestone index; fresh REQUIREMENTS.md to be created via `/gsd-new-milestone`.*
