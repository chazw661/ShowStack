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

### Active

(See Current Milestone below for the active capability under construction.)

### Out of Scope

- Real-time DAW or console transport control — ShowStack is a *planning* and *export* tool, not a live-control surface
- Audio metering, signal analysis, or any audio-stream processing
- Console families outside Yamaha CL/QL/Rivage PM — separate effort if/when demand surfaces
- Network monitoring inside ShowStack — moved to a standalone-app architecture (v1.0 scrapped)
- Replacing vendor tools that already work well (Dante Controller, LA Network Manager, Studio Manager) — ShowStack feeds them, doesn't replace them

## Current Milestone: v2.0 Multitrack Session Builder

**Goal:** Convert ShowStack console channel data into ready-to-use multitrack recording sessions for Reaper and Nuendo Live, with reusable templates and a per-session track editor.

**Target features:**
- Core data model: `MultitrackSession` + `MultitrackTrack` per project, referencing existing `Device` (console) and console channels
- Reaper `.RPP` exporter — plain text, simpler, ships first
- Nuendo Live `.nlpr` exporter via `lxml` template injection (XML structure + 16-color `Farb` palette already decoded in spec)
- CSV import for Yamaha CL/QL and Rivage PM channel labels (M7CL deferred until CSV path confirmed)
- `MultitrackTemplate` for reusable session structures across consoles, mirroring existing ShowStack template UX
- Track editor: drag-reorder, per-track override (label/color), bulk Aux/Matrix/Group toggles, capacity warning vs configurable recorder limit
- Pro Tools support deferred to v2.1 pending tester access

**Source-of-truth spec:** `multitrack_session_builder_spec.md` (in repo root)

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
| Multitrack Session Builder selected as v2.0 | Strong differentiation against flaky Yamaha-Steinberg native integration; Reaper has no first-party path | Pending |

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
*Last updated: 2026-05-12 — Phase 1 complete: Core Sessions, Track Editor & Reaper Export (6/6 plans, 21/21 requirements, all 5 HUMAN-UAT items passed). End-to-end MultitrackSession → .RPP / .RTrackTemplate working in browser. Two server-side authorization gaps from code review (CR-01/CR-02) deferred to /gsd-code-review-fix before push to Railway.*
