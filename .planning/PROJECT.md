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

**Latest shipped:** v2.3 Phase 10 — Autocomplete, PNG Export & New Shape Types — 2026-05-23 (closes LBL-01..03, EXP-01, SHP-10, SHP-11)
**Previous milestone:** v2.2 Signal Flow Diagrammer — 2026-05-22 (Phases 7, 8, 9)

ShowStack engineers can draw project-scoped signal-flow diagrams on a live JointJS canvas with smart shapes linked to Console / Device / SpeakerArray / CommBeltPack records, typed orthogonal connectors (analog / AES / Dante / MADI / intercom with distinct line styles + dash patterns for grayscale print), and the full canvas UX (pan / zoom / snap / undo / multi-select / keyboard delete / viewport restore). Edits persist via debounced 1500 ms autosave with `If-Match` optimistic-lock conflict handling — multi-tab conflicts reveal a locked-copy banner with hard reload; tab-close edits flush via `keepalive`. Equipment renames propagate on next diagram load via server-side `_enrich_nodes()`; deleted equipment renders ghosted with a node-mode inspector offering Re-link or Delete.

**Archived milestones (full detail):**
- [v2.2 Signal Flow Diagrammer](./milestones/v2.2-ROADMAP.md) — Phases 7–9, shipped 2026-05-22
- v2.1 Collaboration & User Management — Phase 6 Trusted Crew Rosters, shipped 2026-05-15 _(pre-dates milestone-close workflow; no archive file)_
- v2.0 Multitrack Session Builder — Phases 1–5, shipped 2026-05-14 _(pre-dates milestone-close workflow; no archive file)_

## Current Milestone: v2.3 Signal Flow Diagrammer — Export & Enhancements

**Driver:** Issue #14 + v2.2 carried scope
**Defined:** 2026-05-22

**Goal:** Close v2.2's deferred Phase 10 scope (autocomplete + PNG export) and ship the engineer-requested Signal Flow Diagrammer power-user features from issue #14: per-shape labeled ports with project-scoped autofill, resizable shapes, two new smart shape types (Processor + Amp), freeform boundary lines, and freeform text annotations.

**Target features:**
- **Per-shape labeled ports** with auto-equal-spacing on top/left/right edges; labels via dropdown (project signal-name fields) or custom text
- **Resizable shapes** (corner-handle drag, per-type min-size) — all existing v2.2 shape types plus the new v2.3 types
- **Two new smart shape types** linked via GFK: **Processor** (covering `SystemProcessor` + `P1Processor` + `GalaxyProcessor`) and **Amp** (covering `Amp` model)
- **Boundary lines** — toolbar draw mode, freeform polyline, color + line-style picker (solid/dashed/dotted/double)
- **Text annotations** — freeform canvas text, font-size + color
- **Circuit-label autocomplete** from existing signal-name fields across Device, Console, Amp, and Processor models (project-scoped)
- **PNG export** — one-click via the already-vendored `html-to-image`

**Phase plan (continues numbering from v2.2):**
- Phase 10 — Autocomplete, PNG Export & New Shape Types (LBL + EXP + SHP-10/11) — **shipped 2026-05-23**
- Phase 11 — Per-Shape Labeled Ports + Resizable Shapes (PORT + SHP-RESIZE)
- Phase 12 — Boundary Lines + Text Annotations (DRAW + TXT)

**Out of scope for v2.3 (carry to v2.4+):**
- Manual port position dragging (auto-equal-spacing only in v2.3)
- Curved boundary lines (polyline only)
- Filled translucent zones (line boundaries only)
- Rich text formatting in TXT (font-size + color only, no bold/italic)
- PDF / SVG export, mobile viewer, auto-routing, clipboard copy/paste, IP annotations, COMM Config integration, PA Cable Schedule overlay, alignment guides, SVG faceplate icons

**Source-of-truth spec:** issue #14 + `.planning/REQUIREMENTS.md`

**Carried polish items from v2.2 (not v2.3 scope but worth tracking):**
- Pre-v2.2 UAT/verification gaps from phases 1, 3, 5, 6 (see STATE.md `## Deferred Items`). Phase 6 has 6 real pending UAT scenarios; the rest are status-only false positives.

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
*Last updated: 2026-05-22 — Milestone v2.3 (Signal Flow Diagrammer Export & Enhancements) opened. Driver: GitHub issue #14 + carried scope from v2.2 Phase 10. 22 requirements across 6 categories (PORT, SHP-RESIZE, SHP, DRAW, TXT, LBL, EXP) mapped to 3 phases (10/11/12). State stays in the existing `SignalFlowDiagram.canvas_state` JSONField — no model migrations expected. Awaiting plan-phase to start Phase 10.*
