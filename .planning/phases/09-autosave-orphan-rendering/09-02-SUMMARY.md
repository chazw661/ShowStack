---
phase: 09-autosave-orphan-rendering
plan: "02"
subsystem: signal-flow-diagrammer
tags: [dom, css, autosave, conflict-banner, orphan-render, accessibility]
dependency_graph:
  requires: []
  provides:
    - "editor.html Phase 9 DOM surfaces: conflict banner + Save-button removal"
    - "signal_flow.css Section 10: 409 conflict banner styles"
    - "signal_flow.css Section 11: orphan ghost CSS (joint-orphan attribute)"
  affects:
    - "09-03 (autosave JS): wires #sfd-save-status state transitions + banner reveal"
    - "09-04 (orphan render JS): sets joint-orphan=true on ghosted cell <g> elements"
tech_stack:
  added: []
  patterns:
    - "Attribute-driven SVG styling via [joint-orphan=\"true\"] CSS selector"
    - "Belt-and-suspenders hidden: display:none !important on [hidden] + HTML hidden attribute"
    - "role=alert + role=status ARIA pattern for live region announcements"
key_files:
  created: []
  modified:
    - planner/templates/planner/signal_flow/editor.html
    - planner/static/planner/css/signal_flow.css
decisions:
  - "Banner copy is hard-coded (no template interpolation) — satisfies T-09-08 tamper threat"
  - "Section 10 uses display:flex !important overridden by [hidden] belt-and-suspenders rule to counter admin !important cascade"
  - "Orphan styles target joint-selector attributes (body/band/label/line) to match JointJS shape renderer conventions established in Phase 8"
metrics:
  duration: "~8 minutes"
  completed: "2026-05-21"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
---

# Phase 9 Plan 02: DOM + CSS Surface for Autosave & Orphan Rendering

One-liner: Removed manual Save button and added hidden 409 conflict banner DOM + red-bar CSS (Section 10) and JointJS attribute-driven orphan ghost CSS (Section 11) so Wave 2 JS agents have zero additional styling work to do.

## Objective

Wave 1 DOM + CSS surface for Phase 9. Prepares editor.html and signal_flow.css so Wave 2 JS plans (09-03 autosave, 09-04 orphan render) can wire behavior against existing hooks with no additional template or stylesheet changes required.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Remove Save button, add conflict banner element, keep save-status | 43ee252 | planner/templates/planner/signal_flow/editor.html |
| 2 | Append Section 10 (banner) + Section 11 (orphan ghost) to signal_flow.css | 36abdd6 | planner/static/planner/css/signal_flow.css |

## Changes Made

### editor.html (Task 1)

- **Removed** `<button type="button" id="sfd-save" aria-label="Save diagram">Save</button>` from the persist toolbar group (DGM-06)
- **Updated** `#sfd-save-status` span: added `role="status" aria-live="polite"` so screen readers announce autosave state changes (D-03)
- **Inserted** `#sfd-conflict-banner` div between `</div>` (toolbar close) and `<div id="sfd-canvas-container">` with:
  - `role="alert"` for assistive-tech announcement on reveal
  - `hidden` attribute for initial invisibility
  - Locked DGM-07 copy (em-dash, exact punctuation): `Diagram was modified elsewhere — reload to see latest.`
  - `#sfd-conflict-reload` Reload button (click handler wired by 09-03 JS)

### signal_flow.css (Task 2)

- **Updated** existing `#sfd-save-status.is-error` rule: added `cursor: pointer !important;` and `text-decoration: underline !important;` for clickable retry affordance (D-03)
- **Appended Section 10** — `#sfd-conflict-banner`: full-width flex row, `background-color: #dc2626`, `color: #ffffff`, belt-and-suspenders `#sfd-conflict-banner[hidden] { display: none !important }`, `#sfd-conflict-reload` white button with red text, hover state `#fee2e2`
- **Appended Section 11** — orphan ghost: `[joint-orphan="true"]` attribute selectors targeting `[joint-selector="body"]`, `[joint-selector="band"]` (grey dashed stroke, 0.4 fill-opacity), `[joint-selector="label"]` (fill #555), and `[joint-orphan-attached="true"]` connector line (opacity 0.5)

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. Banner copy is hard-coded in the Django template with no `{{ }}` template variables or `|safe` filter — T-09-08 tamper mitigation confirmed. The `X-Frame-Options: DENY` header (T-09-10) is unmodified by this plan (Django/Whitenoise default).

## Known Stubs

None. This plan is pure DOM/CSS scaffolding — no data rendering or user-facing behavior. Wave 2 JS plans (09-03, 09-04) will activate the surfaces.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| editor.html exists | FOUND |
| signal_flow.css exists | FOUND |
| 09-02-SUMMARY.md exists | FOUND |
| Commit 43ee252 (Task 1) | FOUND |
| Commit 36abdd6 (Task 2) | FOUND |
| `id="sfd-conflict-banner"` in editor.html | 1 hit |
| `id="sfd-save"` in editor.html | 0 hits (removed) |
| SECTION 10 + SECTION 11 in signal_flow.css | 2 hits |
