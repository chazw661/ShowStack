---
gsd_state_version: 1.0
milestone: v2.2
milestone_name: Signal Flow Diagrammer
status: defining_requirements
last_updated: "2026-05-19T00:00:00.000Z"
last_activity: 2026-05-19 -- Milestone v2.2 opened, defining requirements
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-19)

**Core value:** ShowStack knows your patch, your labels, and your gear; once entered, that data drives every export your show needs.
**Current focus:** v2.2 — Signal Flow Diagrammer (defining requirements)

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-05-19 — Milestone v2.2 started

Progress: [          ] 0%

## Roadmap Summary

(Pending — `/gsd-roadmapper` will fill this in after REQUIREMENTS.md is locked.)

## Accumulated Context

### From v1.0 Network Health Monitor (scrapped)

- Cloud-hosted ShowStack cannot reliably monitor on-site Dante networks (WiFi/Dante NIC conflicts, mDNS interface binding, link-local discovery). Standalone-app architecture is the correct path; the standalone app lives in a separate codebase.
- Reusable lesson: AJAX polling (2–3 s) is more robust than SSE for ShowStack's request lifecycle. Apply to any future near-real-time UI.
- Phase artifacts archived to `.planning/archive/v1.0-network-monitor/`.

### From v2.0 Multitrack Session Builder (shipped 2026-05-14)

- 5 phases / 38 requirements shipped end-to-end. Reaper `.RPP` byte-stable export, Nuendo Live `.nlpr` template-injection via `lxml`, Yamaha CL/QL + Rivage PM CSV import, owner-scoped Multitrack Templates, channel record defaults.
- Reusable lessons applicable to v2.2:
  - **Defence-in-depth at the AJAX boundary** — server-side validation must re-run even when client-side form validation already ran (Phase 5 hex-color re-check pattern). The Signal Flow autosave endpoint should mirror this.
  - **Additive migrations only.** Phases 1–5 added tables/columns; never altered existing columns destructively. Apply to `SignalFlowDiagram` model.
  - **CharField(default='') over nullable** for "may not exist" string fields — keeps queries simple and matches MultitrackTrack.color_override pattern.
  - **Atomic per-task commits** with `feat(NN-MM): ...` subject convention. Apply per plan task in v2.2.
  - Full per-phase detail archived in `.planning/phases/01-*/SUMMARY.md` through `05-*/SUMMARY.md`.

### From v2.1 Trusted Crew Rosters (shipped 2026-05-15)

- 7 plans / 1 phase. Owner-scoped Crew model, bulk-add with Resend pre-onboarding emails, auto-claim on register.
- Reusable lesson for v2.2: **`CurrentProjectMiddleware` scoping is the standard** — never URL-route project IDs. v2.2's `SignalFlowDiagram` queryset must filter by `project=request.current_project`.
- Hidden-from-sidebar pattern (admin_ordering.py whitelist) — apply if v2.2 ships intermediate models that shouldn't clutter the admin sidebar.

### v2.2 Locked Scope Decisions (this milestone)

1. **JointJS core (MIT) is the canvas library** — chosen over drawio iframe and maxGraph. Vanilla-JS drop-in matches the no-framework frontend.
2. **Module-MVP scope** — desktop only, smart shapes for Console/Device/SpeakerArray/CommBeltPack/Generic, orthogonal connectors with line-style variants (analog/AES/Dante/MADI/intercom), circuit-label autocomplete from existing `signal_name` fields, JSON autosave, PNG export.
3. **Many diagrams per project** — list page + name + delete, not single-diagram-per-project.
4. **Out of scope for v2.2:** obstacle-aware auto-routing, custom rack-unit SVG faceplates, PDF / SVG export, version snapshots, mobile `/m/` viewer, real-time multi-user editing. All carried to v2.3+.
5. **Research path:** 4-agent domain research before requirements are finalized (JointJS docs, diagramming patterns in Django apps, signal-flow industry conventions, common pitfalls).
