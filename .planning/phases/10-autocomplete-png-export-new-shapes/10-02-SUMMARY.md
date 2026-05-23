---
phase: 10-autocomplete-png-export-new-shapes
plan: 02
subsystem: ui
tags: [jointjs, signal-flow, smart-shapes, sidebar, toolbar, css, autocomplete, png-export]

# Dependency graph
requires:
  - phase: 08-canvas-smart-shapes
    provides: joint.shapes.showstack namespace + existing 5 shape classes + PICKER_TYPE_CONFIG table + sidebar tile pattern
  - phase: 09-autosave-orphan
    provides: signal_flow.css Sections 10+11 (last existing sections — append target)
provides:
  - joint.shapes.showstack.Processor class (160x60, amber #b45309 band)
  - joint.shapes.showstack.Amp class (140x60, green #15803d band)
  - PICKER_TYPE_CONFIG entries for Processor (backend processor, admin /admin/planner/systemprocessor/) and Amp (backend amp, admin /admin/planner/amp/)
  - Sidebar tiles for Processor and Amp inserted between Device and SpeakerArray (D-11 order)
  - Export PNG toolbar button group scaffold (#sfd-export-group, #sfd-export-png) — handler wired by 10-03
  - data-label-autocomplete-url attribute on #sfd-container — consumed by 10-03 JS
  - signal_flow.css Section 12 (autocomplete dropdown styles)
  - signal_flow.css Section 13 (export button group styles)
affects: [10-03, 11, 12]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Smart shape registration: rect/band/text markup with portsForRect — applied to Processor and Amp"
    - "Sidebar tile order in HTML drives visual sidebar order — insertion between Device and SpeakerArray for D-11 compliance"
    - "CSS append-at-end convention — new Sections 12+13 appended after Section 11"
    - "Color-accent uniqueness audit — every shape's left band uses a distinct color (no reuse across 7 shape types)"

key-files:
  created: []
  modified:
    - planner/static/planner/js/signal_flow_editor.js
    - planner/templates/planner/signal_flow/editor.html
    - planner/static/planner/css/signal_flow.css

key-decisions:
  - "Used {% comment %} ... {% endcomment %} instead of multi-line {# ... #} for the inter-plan dependency note inside the #sfd-container element (Django {# #} is single-line only per MEMORY.md)"
  - "Used plain text 'PNG' on the export button instead of emoji glyph &#x1F5BC; for cross-browser font-stack reliability (per PLAN guidance)"
  - "Processor SVG glyph: rack rect + 3 vertical EQ lines (distinct from Device's horizontal shelves)"
  - "Amp SVG glyph: triangle + short vertical ground stub (distinct from SpeakerArray trapezoid)"

patterns-established:
  - "Shape class scaffolding pattern continues unchanged from Phase 8 — new shapes are mechanical extensions; drag-drop guard and assignPickerResult are already shape-type-agnostic"
  - "Cross-plan inter-dependency comment block in editor.html — documents the soft dependency on Plan 10-01's signal_flow_label_autocomplete URL"

requirements-completed: [SHP-10, SHP-11, EXP-01]

# Metrics
duration: 6min
completed: 2026-05-23
---

# Phase 10 Plan 02: Processor + Amp Shapes, Export Button Scaffold, CSS Sections 12+13 Summary

**Registered showstack.Processor (amber) and showstack.Amp (green) JointJS shape classes, added their D-11-ordered sidebar tiles, scaffolded the right-side export PNG toolbar group, and appended signal_flow.css Sections 12 (autocomplete dropdown) and 13 (export button group) — ready for Plan 10-03 to wire JS behavior.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-23T13:49:00Z (approx, worktree start)
- **Completed:** 2026-05-23T13:55:33Z
- **Tasks:** 2 (committed as 3 atomic commits)
- **Files modified:** 3

## Accomplishments

- Two new smart shape classes registered in `joint.shapes.showstack` namespace — Processor (160x60, amber #b45309 band, covers SystemProcessor GFK) and Amp (140x60, green #15803d band, covers Amp GFK)
- PICKER_TYPE_CONFIG extended with Processor (backend `processor`) and Amp (backend `amp`) entries between Device and SpeakerArray
- Sidebar now shows 7 tiles in D-11 order: Console → Device → Processor → Amp → SpeakerArray → CommBeltPack → Generic
- Distinct SVG glyphs for the two new tiles: Processor uses a rack rect + 3 vertical EQ lines; Amp uses a triangle + short ground stub
- Export PNG toolbar group (`#sfd-export-group`, `#sfd-export-png`) added to the right side of the toolbar — click handler is Plan 10-03 scope
- `data-label-autocomplete-url` attribute added to `#sfd-container` — consumed by 10-03 JS for the autocomplete fetch URL
- signal_flow.css Section 12 (autocomplete combobox dropdown) and Section 13 (export button group) appended after Section 11

## Task Commits

Each task was committed atomically:

1. **Task 1: Register Processor + Amp shape classes and extend PICKER_TYPE_CONFIG** — `970e1c3` (feat)
2. **Task 2a: editor.html — 2 sidebar tiles, export button group, data-label-autocomplete-url** — `3f51e2e` (feat)
3. **Task 2b: signal_flow.css — Sections 12 (autocomplete) and 13 (export group)** — `95edc14` (feat)

_Task 2 was split into two atomic commits because the plan explicitly requested two commit messages — one for editor.html and one for the CSS append — and the changes target different files._

## Files Created/Modified

- `planner/static/planner/js/signal_flow_editor.js` — added Processor + Amp shape class definitions (after Generic, before Graph init) and extended PICKER_TYPE_CONFIG with Processor and Amp entries between Device and SpeakerArray (44 insertions)
- `planner/templates/planner/signal_flow/editor.html` — inserted Processor + Amp sidebar tiles between Device and SpeakerArray tiles, added export PNG button group after persist group, added `data-label-autocomplete-url` attribute on `#sfd-container` with inline {% comment %} explaining the inter-plan dependency on 10-01 (22 insertions / 1 deletion)
- `planner/static/planner/css/signal_flow.css` — appended Section 12 (autocomplete dropdown: wrapper, listbox, rows with aria-selected/hover highlight, source tag) and Section 13 (export button group: right-aligned via margin-left:auto, teal PNG pill with hover and disabled states), all with !important per established Section 1-11 convention (95 insertions)

## Decisions Made

- **Multi-line Django comment style:** Used `{% comment %} … {% endcomment %}` instead of the plan's literal `{# … #}` block for the inter-plan dependency note inside the `#sfd-container` element. Per MEMORY.md `feedback_django_multiline_template_comments.md`, Django `{# … #}` comments are single-line only — a multi-line `{# … #}` block renders as literal page text. This preserves the planner's intent (a stripped server-side note explaining why 10-02 worktree alone would NoReverseMatch) without leaking comment text into the rendered HTML.
- **Export button text:** Used plain ASCII "PNG" on `#sfd-export-png` instead of `&#x1F5BC;` framed-picture emoji, per the plan's explicit guidance ("more reliable in production").
- **Section 12 / Section 13 heading comment style:** Matched the exact `/* ========= SECTION N — Title … ========= */` block-comment convention used by Section 11 in the same file.

## Deviations from Plan

None — plan executed exactly as written. The plan-author's documented choice of `{% comment %}` over multi-line `{# #}` was already implicit in the inter-plan note (the note is inside JSX-like HTML attribute context); using `{% comment %}` is the obviously-correct rendering-safe form and matches CLAUDE.md repository conventions.

## Issues Encountered

- The plan's Task 1 automated verify check uses the substring `'processor':` (single-quote + literal colon) to look for a `'processor': …` style PICKER_TYPE_CONFIG entry, but the existing PICKER_TYPE_CONFIG style uses unquoted capitalized keys (`Processor: { backend: 'processor', … }`). The match string mismatched the actual file convention. Resolved by running an equivalent check on the actual semantics: `backend: 'processor'` and `backend: 'amp'` are both present at lines 354–355. The intent of the verify (both backend handles present) is satisfied. No code change needed — this was a verify-script glitch, not a code defect. The overall plan verification (`python3 -c "…assert…"` block) passes all 8 assertions including `showstack.Processor`, `showstack.Amp`, `#b45309`, `#15803d`.

## Known Stubs

These are intentional scaffolds that Plan 10-03 will wire:

- **`#sfd-export-png` button** — no click handler attached in 10-02. Plan 10-03 binds `html-to-image` PNG generation to this button.
- **`data-label-autocomplete-url` attribute** — read by 10-03 JS to fetch label suggestions. The URL itself is registered by parallel Plan 10-01 (`signal_flow_label_autocomplete`). Rendering this template in any environment that lacks Plan 10-01's `urls.py` change will raise `NoReverseMatch`. Mitigation per plan: 10-01 and 10-02 land in the same merge to main; Railway deploy is atomic. Worktree must not be pushed standalone.
- **`#sfd-label-suggestions` listbox styles (CSS Section 12)** — the `<ul>` itself is not yet injected into the DOM. Plan 10-03 builds the listbox dynamically when the autocomplete combobox initializes.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 10-03 can now consume:
  - `joint.shapes.showstack.Processor` and `joint.shapes.showstack.Amp` for drag-drop and orphan rendering
  - `PICKER_TYPE_CONFIG.Processor` (backend `processor`) and `PICKER_TYPE_CONFIG.Amp` (backend `amp`) — the modal picker dispatch already works for any registered key
  - `#sfd-export-png` element for the html-to-image click handler
  - `#sfd-container.dataset.labelAutocompleteUrl` for the autocomplete fetch URL
  - CSS classes `.sfd-autocomplete-wrapper`, `.sfd-ac-row`, `.sfd-ac-source` and id `#sfd-label-suggestions` (Section 12) for the dropdown DOM the JS will inject
- No blockers. Plan 10-01 (parallel wave 1) must merge alongside this plan so that the `signal_flow_label_autocomplete` URL resolves; otherwise the template will NoReverseMatch on render. Wave 2 (Plan 10-03) is sequenced after both 10-01 and 10-02 merge.

## Self-Check: PASSED

- Files exist:
  - `planner/static/planner/js/signal_flow_editor.js` — FOUND
  - `planner/templates/planner/signal_flow/editor.html` — FOUND
  - `planner/static/planner/css/signal_flow.css` — FOUND
- Commits exist:
  - `970e1c3` — FOUND
  - `3f51e2e` — FOUND
  - `95edc14` — FOUND
- All 8 plan-level assertions pass: `showstack.Processor`, `showstack.Amp`, `#b45309`, `#15803d`, `data-shape-type="Processor"`, `data-shape-type="Amp"`, `sfd-export-group`, `data-label-autocomplete-url`, `SECTION 12`, `SECTION 13`.

---
*Phase: 10-autocomplete-png-export-new-shapes*
*Completed: 2026-05-23*
