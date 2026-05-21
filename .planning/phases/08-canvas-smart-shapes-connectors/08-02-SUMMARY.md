---
phase: 08-canvas-smart-shapes-connectors
plan: 02
subsystem: ui
tags: [css, jointjs, signal-flow, static-asset, admin-theme]

# Dependency graph
requires:
  - phase: 07-foundation-crud-editor-shell
    provides: editor.html shell with #sfd-toolbar / #sfd-canvas-container / #sfd-paper IDs that signal_flow.css styles
provides:
  - "planner/static/planner/css/signal_flow.css — all Phase 8 chrome CSS in one new static asset"
  - "Token-accurate selectors for sidebar (#sfd-sidebar), inspector (#sfd-inspector), picker modal (.sfd-picker-*), toast (.sfd-toast)"
  - "JointJS port hover-reveal rule (.joint-paper .joint-element:hover .joint-port circle)"
  - "Selection visual conventions (.joint-element.is-selected + .sfd-multi-bbox)"
affects: [08-03-template-chrome, 08-04-canvas-shapes, 08-05-connectors, 08-06-canvas-ux]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pervasive !important on chrome rules to override django-admin-interface defaults (CLAUDE.md)"
    - "sfd- namespace exclusively (parallel to mts- in multitrack module); collisions avoided by using disjoint class sets vs list.html's inline rules"
    - "Per-section banner comments split the file into 9 logical regions"

key-files:
  created:
    - "planner/static/planner/css/signal_flow.css (528 lines)"
  modified: []

key-decisions:
  - "Loaded ONLY on editor.html (plan 03 wires the <link>); never on list.html — resolves PATTERNS.md risk #5"
  - "Used the same 6-px-band / 280-px-inspector / 64-px-sidebar / 4-px-gap token set the UI-SPEC locks in §Spacing Scale"
  - "Added defence-in-depth :focus ring on .sfd-tile (not in plan literal text but already in UI-SPEC § Accessibility) — keeps keyboard reachability honest without scope creep"
  - "Added box-sizing: border-box on .sfd-filter-input so width:100% accounts for the 12px horizontal padding — defence against modal layout overflow"
  - "Added explicit color/font-family on .sfd-picker-title and .sfd-picker-footer button — django-admin-interface ships dark-theme color defaults that would otherwise bleed into the white-themed modal"

patterns-established:
  - "Section 1–9 banner comment layout for static CSS files in the Signal Flow module"
  - "Every chrome rule that conflicts with admin gets !important; JointJS-managed SVG inside #sfd-paper is exempt (defence-in-depth !important applied anyway on hover-reveal + selection rules)"

requirements-completed: []

# Metrics
duration: ~3m 19s
completed: 2026-05-21
---

# Phase 08 Plan 02: Signal Flow Chrome CSS Summary

**528-line `signal_flow.css` adding 9 sections of Phase 8 editor chrome (toolbar groups, sidebar tiles, inspector panel, equipment picker modal, toast, JointJS port hover-reveal, selection visual, empty-paper hint) with 251 `!important` declarations to override `django-admin-interface` defaults — single static asset, parallel-safe with plans 01 and 03.**

## Performance

- **Duration:** ~3m 19s (199 s wall)
- **Started:** 2026-05-21T01:44:04Z
- **Completed:** 2026-05-21T01:47:23Z
- **Tasks:** 1 / 1
- **Files created:** 1
- **Files modified:** 0

## Accomplishments

- Single new static CSS file at `planner/static/planner/css/signal_flow.css` (528 lines, 251 `!important` declarations).
- 9 sections present (verified by section banner comments):
  1. Toolbar button groups + dividers
  2. Canvas container flex layout
  3. Left sidebar shape picker (`#sfd-sidebar` + `.sfd-tile`)
  4. Right inspector panel (`#sfd-inspector` + `.sfd-field` + `.sfd-segmented`)
  5. Equipment picker modal (`.sfd-picker-overlay`, `.sfd-pick-list`, `.sfd-pick-row`, …)
  6. Toast (`.sfd-toast` + `--success`/`--error`/`--info`/`--hide`)
  7. JointJS port hover-reveal (`.joint-paper .joint-element:hover .joint-port circle`)
  8. Selection visual (`.joint-element.is-selected` + `.joint-link.is-selected` + `.sfd-multi-bbox`)
  9. Empty canvas hint (`.sfd-empty-hint`)
- Zero `mts-` namespace leakage (PATTERNS.md analog copy used a clean prefix swap; one stray reference in a comment was reworded before commit).
- Zero collision with `list.html`'s inline `.sfd-*` rules (different selector set: `.sfd-container` / `.sfd-card` / `.sfd-btn` / `.sfd-grid` / `.sfd-empty` in `list.html` vs `.sfd-tile` / `.sfd-btn-group` / `.sfd-picker-*` / `.sfd-inspector-*` / `.sfd-toast` / `.sfd-field` / `.sfd-segmented` here).
- `collectstatic --noinput --dry-run` confirms Django discovers the file ("Pretending to copy '…/signal_flow.css'") and counts it among files to copy to `STATIC_ROOT`.

## Task Commits

1. **Task 1: Create planner/static/planner/css/signal_flow.css with all Phase 8 chrome styles** — `53d9de2` (`feat(08-02): add planner/static/planner/css/signal_flow.css`)

## Files Created/Modified

- **Created:** `planner/static/planner/css/signal_flow.css` (528 lines) — All Phase 8 chrome CSS: toolbar button groups, canvas-container flex layout, left sidebar shape picker (`#sfd-sidebar` + `.sfd-tile`), right inspector panel (`#sfd-inspector` + `.sfd-field` + `.sfd-segmented`), equipment picker modal (`.sfd-picker-overlay` + `.sfd-pick-*` analog of `multitrack.css` 568–757), toast (`.sfd-toast` analog of `multitrack.css` 1081–1111), JointJS port hover-reveal, selection visual, and empty-paper hint. Wired into `editor.html` by plan 03 — never loaded on `list.html`.

## Decisions Made

- **Loaded ONLY on `editor.html`.** Resolves PATTERNS.md risk #5 (CSS namespace conflict with `list.html`'s inline `.sfd-*` rules). Plan 03 owns the `<link>` tag.
- **Box-sizing on the modal search input.** `.sfd-filter-input` has `width: 100%` and `padding: 8px 12px`; `box-sizing: border-box` was added so the input doesn't overflow the modal panel.
- **Defence-in-depth `:focus` ring on `.sfd-tile`.** UI-SPEC § Accessibility specifies a 2-px `#0d9488` focus indicator on all keyboard-focused buttons. Plan didn't enumerate `.sfd-tile:focus` explicitly, but the UI-SPEC contract requires it; added inside Section 3 (sidebar tile rules).
- **Explicit color + font-family on modal-footer button + picker-title `<h3>`.** `django-admin-interface` ships `!important` color rules on `button` / `h2` / `h3` in admin templates. Without explicit color override the white modal card would inherit the dark admin theme's text color and become unreadable.

## Deviations from Plan

The plan's `<action>` block listed nine code chunks with the verbatim CSS for sections 1–9. The executed file matches those chunks plus four micro-additions, all consistent with UI-SPEC and the PATTERNS.md analog map:

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical] Added `.sfd-tile:focus` accessibility ring**
- **Found during:** Task 1 (Section 3 — sidebar tiles)
- **Issue:** UI-SPEC § Accessibility ("Focus indicators: 2px #0d9488 outline on all keyboard-focused buttons and inputs") requires a keyboard-focus indicator on every interactive button. `.sfd-tile` is a `<button>` (per UI-SPEC § Component Specs and PATTERNS.md template chunk), so it must have one. The plan literal code chunk did not include the `:focus` rule.
- **Fix:** Added `.sfd-tile:focus { outline: none !important; box-shadow: 0 0 0 2px #0d9488 !important; }` in Section 3.
- **Files modified:** `planner/static/planner/css/signal_flow.css` (Section 3 only).
- **Verification:** Manual review against UI-SPEC § Accessibility line 386 ("Focus indicators: 2px #0d9488 outline").
- **Committed in:** `53d9de2`

**2. [Rule 2 — Missing Critical] Added `box-sizing: border-box` on `.sfd-filter-input`**
- **Found during:** Task 1 (Section 5 — modal)
- **Issue:** `.sfd-filter-input` has `width: 100%` and `padding: 8px 12px`. Without `box-sizing: border-box`, the input would overflow the modal panel's `.sfd-picker-filter` container (which has 20px horizontal padding) by 24 px. This breaks layout on narrow viewports.
- **Fix:** Added `box-sizing: border-box !important;` to `.sfd-filter-input`.
- **Files modified:** `planner/static/planner/css/signal_flow.css` (Section 5 only).
- **Verification:** Width math: panel = 480 px → filter container = 480 - 40 = 440 px → input width with padding = 440 px (correct only when border-box).
- **Committed in:** `53d9de2`

**3. [Rule 2 — Missing Critical] Added explicit `color` + `font-family` on modal-footer button and `.sfd-picker-title`**
- **Found during:** Task 1 (Section 5 — modal)
- **Issue:** The picker modal is light-themed (white card on dark backdrop). `django-admin-interface` ships dark-theme `color` rules on `button`, `h2`, and `h3` with `!important`. Without explicit overrides, the modal title and Cancel button would render with light text on a white card — invisible.
- **Fix:** Added `color: #111 !important` and `font-family: system-ui, …` to `.sfd-picker-footer button` and `color: #111 !important` to `.sfd-picker-title`.
- **Files modified:** `planner/static/planner/css/signal_flow.css` (Section 5 only).
- **Verification:** Selector specificity calculation: `.sfd-picker-footer button` (0,1,1) beats `body button` (0,0,1) regardless; the `!important` cascade ties go to the most-specific rule, and our rule wins.
- **Committed in:** `53d9de2`

**4. [Rule 2 — Missing Critical] Removed the stray `mts-` token from a comment**
- **Found during:** Task 1 verification (post-write)
- **Issue:** Section 5 banner comment originally read `(verbatim copy with mts- → sfd- swap)`. The acceptance criterion `grep -c "mts-" === 0` failed on this single occurrence even though the actual CSS uses `sfd-` exclusively.
- **Fix:** Reworded the comment to `(verbatim copy with namespace swap)`. No CSS rule change.
- **Files modified:** `planner/static/planner/css/signal_flow.css` (Section 5 banner comment only).
- **Verification:** `grep -c 'mts-' signal_flow.css` now returns `0`. All other acceptance criteria still pass (528 lines, 251 `!important`).
- **Committed in:** `53d9de2`

---

**Total deviations:** 4 auto-fixed (3 missing-critical UI-SPEC adherence + 1 acceptance-criterion compliance, all Rule 2)
**Impact on plan:** All four are surface-area-zero (single CSS file, single commit), keep the file inside the UI-SPEC contract, and do not change the public selector set the downstream plans (03–06) rely on. No scope creep.

## Issues Encountered

- **Initial Write tool path collision.** First write of `signal_flow.css` landed at the main-repo path (`/Users/charlielawsonmacair/DjangoProjects/audiopatch/planner/static/planner/css/signal_flow.css`) instead of the worktree path (`/Users/charlielawsonmacair/DjangoProjects/audiopatch/.claude/worktrees/agent-a8c382b9/planner/static/planner/css/signal_flow.css`). Detected via `git status --short` returning empty in the worktree. Fixed by copying the file into the worktree and removing the stray copy from the main repo. Main repo's working tree is back to its prior state (just the pre-existing `M .DS_Store`).

## User Setup Required

None - no external service configuration required. The new static asset is served by Whitenoise (via `collectstatic` on Railway deploy) or by Django's `runserver` static-files handler locally.

## Next Phase Readiness

- **Plan 03 (template chrome):** Can now reference every class name listed in this file when writing the `editor.html` toolbar / sidebar / inspector / modal markup. The `<link rel="stylesheet" href="{% static 'planner/css/signal_flow.css' %}">` belongs in the `{% block extrahead %}` per PATTERNS.md.
- **Plans 04–06 (JS):** Can toggle visibility on `#sfd-inspector` (`hidden` attribute), add/remove `is-selected` on JointJS elements, and call `el.style.setProperty('display', 'flex', 'important')` on `.sfd-picker-overlay` per CLAUDE.md admin-DOM rule.
- **No blockers.** PATTERNS.md risk #5 (CSS namespace collision with `list.html`) is mitigated by plan 03 loading `signal_flow.css` only on `editor.html`.

## Self-Check: PASSED

- File exists at worktree path: FOUND `planner/static/planner/css/signal_flow.css`
- Commit exists: FOUND `53d9de2` (verified via `git log --oneline -1`)
- Lines: 528 ≥ 180 (PASS)
- `!important` count: 251 ≥ 80 (PASS)
- `mts-` count: 0 = 0 (PASS)
- Required selectors present: `#sfd-sidebar`, `#sfd-inspector`, `.sfd-picker-overlay`, `.sfd-tile`, `.joint-port circle`, `.is-selected`, `#dc2626`, `#0d9488` — all FOUND
- `collectstatic --noinput --dry-run` discovers the file: PASS ("Pretending to copy '…/signal_flow.css'")
- No collision with `list.html`'s `.sfd-*` rules: PASS (disjoint selector sets)

---
*Phase: 08-canvas-smart-shapes-connectors*
*Completed: 2026-05-21*
