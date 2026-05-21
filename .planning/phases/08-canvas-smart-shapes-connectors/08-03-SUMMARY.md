---
phase: 08-canvas-smart-shapes-connectors
plan: 03
subsystem: ui
tags: [django-template, signal-flow, jointjs, html5-drag-drop, modal, aria, accessibility]

# Dependency graph
requires:
  - phase: 07-foundation-crud-editor-shell
    provides: "editor.html shell with #sfd-container data-attrs, #sfd-paper, hidden CSRF form, vendor JS load order, list.html with .sfd-* inline scoped styles"
provides:
  - "Phase 8 chrome DOM contract — every stable ID/class plans 04-06 JS will bind to"
  - "Sidebar 5-tile shape picker with data-shape-type discovery hook for drag-drop"
  - "Hidden inspector panel for connector signal-type/direction/circuit-label editing"
  - "Equipment picker modal partial (single-pick, scoped autocomplete) included from editor.html only"
  - "<link> tag wiring planner/css/signal_flow.css into editor.html (loaded ONLY here, not list.html — PATTERNS risk #5 resolved)"
affects: [08-04 (drag-drop + modal JS binding), 08-05 (undo/redo button binding), 08-06 (inspector field binding), 09 (autosave button binding), 10 (autocomplete + PNG export)]

# Tech tracking
tech-stack:
  added: []  # template-only plan, no new libraries
  patterns:
    - "Single-CSS-file load scoped to editor.html — list.html intentionally untouched (PATTERNS.md risk #5)"
    - "Modal partial included once from editor.html — no separate URL/view (analog: multitrack/_picker_modal.html)"
    - "Inline SVG glyphs for sidebar tile icons — system-rendered, no external asset fetch, 12-line max per icon"
    - "Two-affordance modal close pattern (X button + footer Cancel button) — both bound to the same JS handler"
    - "hidden attribute + style=\"display:none\" belt-and-suspenders — JS must use !important to override (CLAUDE.md admin-DOM rule)"

key-files:
  created:
    - "planner/templates/planner/signal_flow/_equipment_picker_modal.html — equipment picker modal partial (38 lines)"
  modified:
    - "planner/templates/planner/signal_flow/editor.html — Phase 8 chrome: CSS link, toolbar groups, sidebar, inspector, modal include (+81 lines, -2 lines)"

key-decisions:
  - "Loaded signal_flow.css only on editor.html (not list.html) to avoid collision with list.html's inline .sfd-container / .sfd-h1 / .sfd-btn classes — resolves PATTERNS risk #5."
  - "Snap-to-grid button defaults to active (is-active class + aria-pressed=true) per CONTEXT D-13."
  - "Undo/redo buttons start with disabled attribute — plan 05 JS removes when CommandManager stacks become non-empty."
  - "Modal uses hidden attribute AND inline style=\"display:none\" — defense in depth so the modal is hidden even before signal_flow.css has loaded."
  - "No inline JS (onclick/onchange/oninput) in either template — keeps both CSP-friendly and XSS-clean. All behavior bound by signal_flow_editor.js via addEventListener in plans 04-06."
  - "Modal admin-link href left as href=\"#\" because target URL depends on which shape type was dropped — JS fills via setAttribute('href', ...) on open."

patterns-established:
  - "DOM contract for Phase 8 — all stable IDs that plans 04-06 JS will querySelector. See \"Stable IDs (binding contract)\" section below."
  - "Sidebar tile data-shape-type discovery — plan 04 JS uses document.querySelectorAll('[data-shape-type]') for dragstart binding."
  - "Right-side inspector auto-show — plan 06 JS toggles the hidden attribute (no .style.display manipulation needed)."

requirements-completed: []  # Plan 08-03 has no requirements in frontmatter — chrome wiring is supporting infrastructure for plans 04-06 which carry the CNV-* / SHP-* / CON-* requirements.

# Metrics
duration: ~12min
completed: 2026-05-21
---

# Phase 08 Plan 03: Editor Chrome Wiring Summary

**Phase 8 chrome wired into `editor.html` — 7-button toolbar (zoom/snap/undo/redo/save), 5-tile sidebar with data-shape-type drag hooks, hidden inspector panel, equipment picker modal partial, signal_flow.css link — all stable IDs locked as the DOM contract for plans 04–06 JS.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-21T01:35Z (approx)
- **Completed:** 2026-05-21T01:47:38Z
- **Tasks:** 2 / 2
- **Files modified:** 2 (1 modified + 1 created)

## Accomplishments

- **Toolbar fully wired** with the canonical order from CONTEXT D-06: zoom-out / level / zoom-in / fit / snap-toggle / undo / redo / save / save-status. Snap defaults to active; undo/redo default disabled.
- **5-tile sidebar** inside `#sfd-canvas-container` with `data-shape-type` on each tile — Console, Device, SpeakerArray, CommBeltPack, Generic — each carrying an inline SVG glyph and a human-readable label per the UI-SPEC copywriting contract ("Beltpack", "Speaker Array").
- **Hidden inspector panel** with signal-type select (Analog/AES/Dante/MADI/Intercom), segmented Source→Target / Bidirectional control, and circuit-label text input + helper text.
- **New `_equipment_picker_modal.html` partial** created with role="dialog" / role="listbox" / aria-modal / aria-labelledby. Single-pick (no checkboxes), two close affordances, empty state with type-specific admin link, all driven by plan 04 JS via stable IDs.
- **CSS link to `planner/css/signal_flow.css`** added inside `{% block extrahead %}` after the Phase 7 inline `<style>`. Loaded ONLY on editor.html — list.html intentionally untouched (PATTERNS risk #5 resolved).
- **Zero Phase 7 regressions:** `#sfd-container` data-attrs preserved, `#sfd-paper` preserved, hidden CSRF form preserved, vendor JS load order (joint un-deferred, html-to-image, app JS deferred) preserved.
- **Zero inline JavaScript** — both templates are CSP-friendly and XSS-clean. All behavior bound by `signal_flow_editor.js` via `addEventListener` in plans 04-06.

## Task Commits

Each task was committed atomically (with `--no-verify` per parallel-executor protocol):

1. **Task 1: Modify editor.html — add toolbar buttons, sidebar, inspector, modal include, CSS link** — `bea4583` (feat)
2. **Task 2: Create _equipment_picker_modal.html partial** — `5c0af0f` (feat)

_Plan metadata commit (SUMMARY.md) will be added after this file is written._

## Files Created/Modified

- **`planner/templates/planner/signal_flow/editor.html`** — modified (+81/-2 lines). Added: CSS `<link>` in `extrahead`; full toolbar button groups inside `#sfd-toolbar`; `#sfd-sidebar` with 5 draggable tiles; hidden `#sfd-inspector` with 3 field groups; modal `{% include %}` after CSRF form.
- **`planner/templates/planner/signal_flow/_equipment_picker_modal.html`** — new (38 lines). Hidden modal partial with title, search input, results listbox, empty state, footer cancel button. Two close affordances (X + Cancel). No inline JS.

## Stable IDs (Binding Contract)

These IDs are the contract plans 04–06 JS will `document.getElementById(...)` / `querySelector(...)` against. Treat them as load-bearing:

### Toolbar (`#sfd-toolbar`)

| ID | Purpose | Default state |
|----|---------|---------------|
| `sfd-zoom-out` | Zoom canvas out | enabled |
| `sfd-zoom-level` | Display current zoom % (aria-live="polite") | text `100%` |
| `sfd-zoom-in` | Zoom canvas in | enabled |
| `sfd-zoom-fit` | Zoom to fit all cells | enabled |
| `sfd-snap-toggle` | Toggle grid snap | `class="is-active"`, `aria-pressed="true"` |
| `sfd-undo` | Undo last command | `disabled` |
| `sfd-redo` | Redo undone command | `disabled` |
| `sfd-save` | Manual save trigger | enabled |
| `sfd-save-status` | Live save status text | text `All changes saved.` |

### Sidebar (`#sfd-sidebar`)

5 `<button class="sfd-tile" draggable="true" data-shape-type="X">` elements, where X ∈ {`Console`, `Device`, `SpeakerArray`, `CommBeltPack`, `Generic`}. Plan 04 JS discovers them via `document.querySelectorAll('[data-shape-type]')` and wires `dragstart` handlers that call `e.dataTransfer.setData('application/x-shape-type', e.currentTarget.dataset.shapeType)`.

### Inspector (`#sfd-inspector`)

| ID | Widget | Notes |
|----|--------|-------|
| `sfd-inspector-close` | Close button | toggles `hidden` attr on parent |
| `sfd-signal-type` | `<select>` | options: `analog`/`AES`/`Dante`/`MADI`/`intercom` (value attr; visible label uses Title Case) |
| `sfd-dir-forward` | Segmented button | `data-active="true"` default |
| `sfd-dir-bidir` | Segmented button | inactive default |
| `sfd-circuit-label` | `<input type="text">` | placeholder `e.g. CKT-01`, maxlength 100 |

### Equipment Picker Modal

| ID | Purpose |
|----|---------|
| `sfd-picker-overlay` | Modal root (hidden + style=display:none) |
| `sfd-picker-title` | Title with span slot |
| `sfd-picker-type` | Span inside title — JS fills with "Console" / "Speaker Array" / etc. via textContent |
| `sfd-picker-close-x` | X close button (top-right) |
| `sfd-picker-search` | Search input |
| `sfd-picker-results` | `<ul role="listbox">` — populated via createElement + textContent (no innerHTML) |
| `sfd-picker-empty` | Empty state container (hidden by default) |
| `sfd-picker-empty-type` | Span inside empty state — JS fills with shape type |
| `sfd-picker-admin-link` | "Add equipment in Admin" link — href filled by JS to type-specific admin changelist |
| `sfd-picker-cancel` | Cancel button (footer) |

## Decisions Made

- **CSS link scope:** `planner/css/signal_flow.css` is referenced ONLY from `editor.html`. `list.html` was intentionally NOT modified — its inline `.sfd-container`, `.sfd-h1`, `.sfd-btn`, `.sfd-empty` styles remain undisturbed. This resolves PATTERNS.md risk #5 (CSS namespace conflict).
- **Snap-toggle default state:** active (`class="is-active"`, `aria-pressed="true"`) per CONTEXT D-13. Plan 05 JS will toggle on click.
- **Undo/redo default state:** `disabled` attribute. Plan 05 JS removes the attribute when `CommandManager` stacks become non-empty.
- **Two close affordances on modal:** `#sfd-picker-close-x` (top-right X) and `#sfd-picker-cancel` (footer Cancel button) — both bound to the same JS handler in plan 04. ESC key also closes (also bound in plan 04). Cancel removes the placeholder shape per CONTEXT D-10.
- **Modal hidden technique:** `hidden` attribute AND inline `style="display:none"` — defense in depth so the modal stays hidden even before `signal_flow.css` finishes loading. Plan 04 JS must use `element.style.setProperty('display', 'flex', 'important')` to show (CLAUDE.md admin-DOM override rule).
- **Modal admin-link href:** left as `href="#"` — plan 04 JS fills via `setAttribute('href', ...)` on open because the target URL depends on which shape type was dropped (per-type Django admin changelist URL).
- **Inline SVG glyphs (not external icons):** every tile icon is inline SVG with `currentColor` fills/strokes so the tile color flows from the parent button's color/hover styles. Keeps the page free of additional asset fetches and removes any external-resource taint risk for the PNG export pipeline (Phase 10).

## Deviations from Plan

None — plan executed exactly as written. Both tasks' acceptance criteria passed on first attempt. Django `manage.py check planner` exits clean. `get_template(...)` resolves both `editor.html` and `_equipment_picker_modal.html` when Django runs from the worktree cwd. Full template render harness (with a stub `diagram` object) confirms all 22 expected DOM elements appear in output (the one "fail" is the expected `{% csrf_token %}` warning when rendered outside a `RequestContext` — runtime middleware injects the token correctly).

## Issues Encountered

- **`get_template` resolution snag while running Django from the worktree:** First template-load test ran via the venv's interpreter without changing cwd; Django's `APP_DIRS` template loader resolved against the parent repo's `planner/templates/` path (which doesn't yet contain my changes) so `_equipment_picker_modal.html` initially appeared missing. Resolved by running `manage.py` from inside the worktree root — both templates then loaded cleanly. No code change needed; this is a venv-vs-worktree artifact, not a bug in the work.

## User Setup Required

None — pure template work. No environment variables, no Railway changes, no migrations.

## Next Phase Readiness

- **Plan 08-04 (drag-drop + smart shapes + equipment picker JS):** Ready. All DOM hooks plan 04 needs are present and validated (`[data-shape-type]` tiles, modal IDs, `data-autocomplete-url` already wired in Phase 7).
- **Plan 08-05 (zoom + snap + undo/redo JS):** Ready. Toolbar button IDs are stable. `#sfd-zoom-level` is `aria-live="polite"` so screen readers will announce zoom changes when JS updates `textContent`.
- **Plan 08-06 (connector inspector JS):** Ready. `#sfd-inspector` toggles via the `hidden` attribute; all field IDs (`sfd-signal-type`, `sfd-dir-forward`, `sfd-dir-bidir`, `sfd-circuit-label`) are present.
- **Plans 08-01 (autocomplete view) and 08-02 (signal_flow.css):** This plan references `{% url 'planner:signal_flow_autocomplete' %}` (already present in Phase 7 — wired in plan 08-01) and `{% static 'planner/css/signal_flow.css' %}` (created in parallel plan 08-02). The `<link>` tag will render to a 404 until 08-02 lands its CSS file, but Django won't error — the browser will just paint with un-styled chrome until the CSS file exists.
- **No blockers.** No Phase 7 regressions. Both task commits clean. Worktree-only changes — orchestrator owns merge back to main.

## Self-Check

Verifying every claim made above against the filesystem and git history:

### Files created/modified — exist on disk

- `planner/templates/planner/signal_flow/editor.html` — FOUND (modified, 127 lines)
- `planner/templates/planner/signal_flow/_equipment_picker_modal.html` — FOUND (created, 38 lines)

### Commits — present in git history

- `bea4583` — FOUND (`feat(08-03): wire Phase 8 chrome into signal flow editor.html`)
- `5c0af0f` — FOUND (`feat(08-03): add equipment picker modal partial for signal flow editor`)

### Stable IDs — present in rendered template output

All 21 expected DOM elements confirmed via `get_template().render()` smoke test: `signal_flow.css` link, 5 `data-shape-type` tiles, 7 toolbar button IDs (zoom-out/zoom-in/zoom-fit/snap-toggle/undo/redo/save), save-status text, sidebar, inspector (with `hidden` attr), signal-type select, circuit-label input, modal overlay/search/results, vendor `joint.min.js`, `signal_flow_editor.js`. The single "fail" in the harness (`csrfmiddlewaretoken`) is the expected `{% csrf_token %}` empty-render warning when rendered outside a `RequestContext` — runtime middleware injects the token correctly.

### Phase 7 locked elements — preserved

`#sfd-container`, all 5 `data-*` attrs (diagram-id / state-url / autosave-url / autocomplete-url / export-png-url), `#sfd-paper`, hidden CSRF form, vendor JS load order (joint un-deferred, html-to-image, app JS deferred) — all present and unchanged.

## Self-Check: PASSED
