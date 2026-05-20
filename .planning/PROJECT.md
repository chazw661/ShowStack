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

### Active

(See Current Milestone below for the active capability under construction.)

### Out of Scope

- Real-time DAW or console transport control — ShowStack is a *planning* and *export* tool, not a live-control surface
- Audio metering, signal analysis, or any audio-stream processing
- Console families outside Yamaha CL/QL/Rivage PM — separate effort if/when demand surfaces
- Network monitoring inside ShowStack — moved to a standalone-app architecture (v1.0 scrapped)
- Replacing vendor tools that already work well (Dante Controller, LA Network Manager, Studio Manager) — ShowStack feeds them, doesn't replace them

## Current Milestone: v2.2 Signal Flow Diagrammer

**Goal:** ShowStack engineers can draw, save, and share project-scoped signal-flow diagrams using smart shapes that link to live ShowStack equipment records, with connector styles matched to signal type and circuit labels pulled from existing `signal_name` fields.

**Target features (module-MVP scope):**
- Drag-and-drop canvas powered by **JointJS core** (vanilla JS, MPL-2.0) — matches ShowStack's no-framework frontend
- `SignalFlowDiagram` model, project-scoped via `CurrentProjectMiddleware`
- Many diagrams per project (list page + name + delete)
- Smart shapes for `Console` / `Device` / `SpeakerArray` / `CommBeltPack` + a generic shape for gear not in ShowStack
- Nodes carry `(content_type, object_id)` → live link to ShowStack record; label propagates on rename, soft-fail render if the linked record is deleted
- Orthogonal cable connectors with line-style variants: analog / AES / Dante / MADI / intercom
- Circuit-label autocomplete sourced from existing signal-name fields (`ConsoleInput`, `DeviceInput/Output`, etc.)
- JSON autosave (blob on the model row)
- PNG export

**Source-of-truth spec:** issue #13 + `.planning/research/SUMMARY.md` (generated this milestone).

**Out of scope for v2.2 (carry to v2.3+):**
- Obstacle-aware orthogonal auto-routing (v2.2 hand-rolls basic routing)
- Custom rack-unit SVG equipment faceplates
- PDF / SVG export, version snapshots
- Mobile `/m/` viewer
- Real-time multi-user editing

**Previous milestones (closed):**
- v2.0 Multitrack Session Builder (Phases 1–5) — shipped 2026-05-14
- v2.1 Collaboration & User Management (Phase 6, Trusted Crew Rosters) — shipped 2026-05-15

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
*Last updated: 2026-05-20 — v2.2 Phase 7 shipped (Foundation, CRUD & Editor Shell). `SignalFlowDiagram` model + 0158 migration + admin on showstack_admin_site, 9 views + 9 URLs with project-scoped IDOR guards, `joint.min.js` (MPL-2.0) + `html-to-image.min.js` (MIT) vendored, list page + editor HTML shell + dashboard quick-action. Browser smoke test approved 2026-05-20 (console: `[SFD] JointJS ready — version 4.2.4`). 19/19 must-haves verified. DGM-01..05 + DGM-08 closed. Phase 8 (Canvas, Smart Shapes & Connectors) is next.*
