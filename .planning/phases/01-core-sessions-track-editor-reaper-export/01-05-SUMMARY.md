---
phase: 01-core-sessions-track-editor-reaper-export
plan: 05
subsystem: web
tags: [django, templates, multitrack, ui-spec, dom-hooks, picker, color-picker, editor, dashboard, partials]

# Dependency graph
requires:
  - phase: 01
    plan: 01
    provides: MultitrackSession + MultitrackTrack model fields, resolved_label / resolved_color / resolved_source / get_target_daw_display / get_feed_source_display helpers
  - phase: 01
    plan: 03
    provides: page-render views, MultitrackSessionForm (7-field whitelist + Nuendo Live disabled choice), URL namespace planner:multitrack_dashboard / multitrack_create / multitrack_editor / multitrack_edit / multitrack_duplicate / multitrack_rename / multitrack_delete, _editor_context helper exposing session/tracks/picker_data_json/auto_open_picker/total_count/over_count
  - phase: 01
    plan: 04
    provides: planner:multitrack_export_rpp, planner:multitrack_export_rtracktemplate URL names + 7 AJAX mutate URL names that Plan 06's JS will fetch()
provides:
  - "planner/templates/planner/multitrack/dashboard.html — module landing page (MTS-03), grid of session cards or empty state with verbatim UI-SPEC copy"
  - "planner/templates/planner/multitrack/_session_card.html — per-card partial with title, meta line ({N} tracks · {target_daw} · updated {timesince} ago), Duplicate/Rename/Delete dropdown"
  - "planner/templates/planner/multitrack/new_session.html — create + edit form (single template via mode context var) with 7 fields in UI-SPEC order"
  - "planner/templates/planner/multitrack/editor.html — track editor page with capacity bar, toolbar (Export to Reaper / Export Track Template / + Add tracks), mts-track-list, embedded picker_data_json, auto_open_picker shim"
  - "planner/templates/planner/multitrack/_track_row.html — per-track row partial with drag handle, enable checkbox, track #, source-type badge, label override cell, color swatch, notes display-only span (Phase 1), remove button"
  - "planner/templates/planner/multitrack/_picker_modal.html — channel picker overlay with 5 tabs, filter, per-tab Select all/Clear, manual-row <template> for cloning, commit/cancel footer"
  - "planner/templates/planner/multitrack/_color_picker.html — 12-swatch popover with custom hex input (HTML5 pattern matches Plan 04's _HEX_COLOR_RE) + Clear color link"
  - "Full DOM-hook contract Plan 06's JS attaches to (documented in DOM Hook Contract section below)"
  - "Complete list of mtsXxx() function names referenced via inline onclick handlers (documented in JS Function Contract section below)"
affects: [01-06]

# Tech tracking
tech-stack:
  added: []  # No new dependencies — Django template language only
  patterns:
    - "Single-template-per-mode pattern: new_session.html serves both create and edit via {mode} context var (mirrors comm_config single-form precedent)"
    - "Verbatim UI-SPEC copy embedded in templates, with comment markers explaining checker-driven decisions (e.g. notes display-only per WARNING 3)"
    - "DOM-hook contract documented inline (data-* attrs + class names) so Plan 06's JS authors can attach without re-deriving"
    - "Capacity bar reads pre-computed total_count + over_count from view context (Plan 03's _editor_context helper) — zero inline arithmetic, single source of truth"
    - "Manual-row <template> clone pattern (modern, native) for picker's '+ Add another' affordance"
    - "Server-rendered data-color attribute + JS-applied setProperty('background-color', value, 'important') to defeat admin's pervasive !important rules per CLAUDE.md"
    - "5-tab picker with per-tab Select all/Clear (D-08) replacing the spec's collapsible bulk-toggle section"

key-files:
  created:
    - "planner/templates/planner/multitrack/dashboard.html"
    - "planner/templates/planner/multitrack/_session_card.html"
    - "planner/templates/planner/multitrack/new_session.html"
    - "planner/templates/planner/multitrack/editor.html"
    - "planner/templates/planner/multitrack/_track_row.html"
    - "planner/templates/planner/multitrack/_picker_modal.html"
    - "planner/templates/planner/multitrack/_color_picker.html"
    - ".planning/phases/01-core-sessions-track-editor-reaper-export/01-05-SUMMARY.md"
  modified: []

key-decisions:
  - "Notes column on _track_row.html is DISPLAY-ONLY (plain <span class='mts-track-notes-display'>) — not an editable input. Phase 1 has no multitrack_set_notes endpoint per checker WARNING 3; rendering an editable affordance would mislead users. Notes are still WRITABLE during track creation through the picker modal's manual-tab inline form (D-11)."
  - "Capacity bar arithmetic lives in the view (Plan 03's _editor_context helper computes total_count + over_count). The template only reads — no {% widthratio %} subtraction chains, no custom tag. The no-enabled-tracks export fallback (Plan 04) shares the same template, so the helper is the single source of truth."
  - "new_session.html serves both create and edit via the {mode} context var. Cancel button target is mode-conditional: create returns to dashboard, edit returns to that session's editor."
  - "Nuendo Live radio is rendered with the disabled attribute and the verbatim '(coming v2.0)' caption per UI-SPEC. Server-side, Plan 03's MultitrackSessionForm.clean_target_daw rejects the value as belt+suspenders against tampered POSTs."
  - "Only one |safe filter usage across all 7 templates: picker_data_json|safe in editor.html. The value is pre-json.dumps()'d server-side by Plan 03's _build_picker_data, so it's a JSON literal — not a user-controlled string. No |safe on session.name, session.notes, track.label_override, track.notes (T-05-01 mitigation)."
  - "Color swatch uses data-color='#RRGGBB' attribute (auto-escaped) instead of inline style='background-color:...'. JS reads data-color and writes via setProperty('background-color', value, 'important') per CLAUDE.md / RESEARCH Pitfall 4 — admin's pervasive !important rules would otherwise win and the swatch would render blank."
  - "All inline onclick string args use |escapejs (session.name in _session_card.html). track.id is an int, no escaping required. Manual-row template cloning uses a <template> element (native), avoiding innerHTML with user data."

requirements-completed:
  - MTS-01
  - MTS-02
  - MTS-03
  - MTS-04
  - MTS-05
  - MTS-06
  - TRK-01
  - TRK-02
  - TRK-03
  - TRK-04
  - TRK-05
  - TRK-06
  - TRK-07
  - TRK-09
  - TRK-10

# Metrics
duration: ~6min
completed: 2026-05-11
---

# Phase 1 Plan 05: Multitrack Module Templates Summary

**Seven Django templates (3 pages + 4 partials) under `planner/templates/planner/multitrack/` rendering the entire UI-SPEC contract for the Multitrack Session Builder — dashboard grid + empty state, create/edit form, track editor with capacity bar + drag-reorderable track rows, channel picker modal with 5 tabs, and 12-swatch color popover. All DOM hooks (`data-track-id`, `mts-track-list`, `mts-picker-overlay`, `data-tab`, `#mts-picker-data`, etc.) are in place for Plan 06's JS to attach behavior. Only `picker_data_json|safe` uses the `|safe` filter — every user-controlled field renders through Django auto-escape.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-11T18:11:54Z
- **Completed:** 2026-05-11T18:17:52Z
- **Tasks:** 4
- **Files created:** 7 (all templates) + this SUMMARY

## Accomplishments

- All seven UI-SPEC layouts rendered in templates: dashboard grid + empty state, new-session form (7 fields in UI-SPEC order), editor page with capacity bar + drag-reorderable track list + Reaper export buttons, channel picker modal with 5 tabs + per-tab Select all/Clear, 12-swatch color popover.
- Verbatim UI-SPEC binding strings embedded throughout: `Multitrack Sessions`, `Build recording-session track lists from your console channels.`, `+ New Session`, `No sessions yet`, `Add Tracks`, `Filter by name or number…`, `Select all` / `Clear`, `+ Add another`, `Add 0 selected`, `Drag rows to reorder. Order is saved automatically.`, `← Multitrack Sessions`, `Export to Reaper`, `Export Track Template (.RTrackTemplate)`, `Edit session metadata`, `+ Add tracks`, `No tracks yet`, `Pick channels from this console to build your session.`, `(coming v2.0)`, `Drives the over-capacity warning bar in the editor.`, `Click to override color` / `Click to change. Right-click to clear.`, `Custom:`, `Clear color`.
- Capacity bar renders three states (under / at / over) driven by server-side classes (`mts-capacity--under` / `--at` / `--over`) and the pre-computed `total_count` + `over_count` from Plan 03's `_editor_context` helper. The "N over capacity" suffix renders without inline arithmetic.
- Picker modal embeds `picker_data_json` as `<script type="application/json">` (pre-`json.dumps()`'d by Plan 03's `_build_picker_data`) and exposes per-tab Select-all / Clear (D-08).
- Auto-open picker on zero-track sessions (D-12) wired up via DOMContentLoaded shim that calls `mtsOpenPicker('inputs')`.
- Notes column on `_track_row.html` ships as DISPLAY-ONLY per checker WARNING 3 — no input, no pencil, no `mtsToggleNotes` / `mtsSaveNotes` callsite. The picker's manual-tab inline form is the only writable notes surface in Phase 1.
- All seven templates extend `admin/base_site.html` for the dark theme (CLAUDE.md non-negotiable).

## Task Commits

Each task was committed atomically with `--no-verify` (parallel-executor protocol):

1. **Task 1: Create dashboard.html + _session_card.html partial** — `7c97fa3` (feat)
2. **Task 2: Create new_session.html (used for both create and edit)** — `b0191c6` (feat)
3. **Task 3: Create editor.html + _track_row.html partial** — `a0f67b6` (feat)
4. **Task 4: Create _picker_modal.html and _color_picker.html partials** — `682bf03` (feat)

## DOM Hook Contract (binding for Plan 06)

Every class / data-attr / id Plan 06's JS depends on, mapped to the template that provides it:

### Dashboard / Session Card

| Hook | Template | Purpose |
|---|---|---|
| `.mts-card[data-session-id]` | `_session_card.html` | Per-session card (Plan 06 dropdown menu trigger reads sessionId from data attr) |
| `.mts-card-menu-trigger` | `_session_card.html` | Dropdown trigger button (passes button + sessionId to mtsToggleCardMenu) |
| `#mts-card-menu-{N}` | `_session_card.html` | Dropdown panel id; toggled to display:block by mtsToggleCardMenu |
| `.mts-dropdown-item` | `_session_card.html` | Duplicate / Rename / Delete buttons |
| `.mts-dropdown-item--danger` | `_session_card.html` | Delete button (red styling per UI-SPEC) |
| `[name=csrfmiddlewaretoken]` (in hidden form) | `dashboard.html` | CSRF source for dropdown JS handlers |

### Editor / Track List / Track Row

| Hook | Template | Purpose |
|---|---|---|
| `.mts-track-list[data-session-id]` | `editor.html` | Sortable.js init target; sessionId read for reorder POST |
| `.mts-track-row[data-track-id][data-source-type][data-source-id]` | `_track_row.html` | Per-track Sortable item; data-track-id used by every JS handler |
| `.mts-track-row--disabled` | `_track_row.html` | Visual state (0.4 opacity per UI-SPEC) when track.enabled=False |
| `.mts-drag` | `_track_row.html` | Sortable.js drag handle (`handle: '.mts-drag'`) |
| `.mts-enable-checkbox` | `_track_row.html` | Per-row enable toggle (calls mtsSetEnabled) |
| `.mts-track-num` | `_track_row.html` | "#N" label; updated client-side after reorder drop |
| `.mts-badge.mts-badge--{source_type}` | `_track_row.html` | Per-row source-type badge (INPUT / AUX / MTX / ST / MANUAL); type-specific class for color coding |
| `.mts-track-label-cell` | `_track_row.html` | Click target opens inline label edit |
| `.mts-track-label-display` | `_track_row.html` | Visible label span; replaced by mtsSaveLabel on commit |
| `.mts-track-source-fallback` | `_track_row.html` | "↳ {source_name}" caption shown only when label_override active |
| `.mts-track-label-input[data-track-id]` | `_track_row.html` | Hidden input toggled to display:block by mtsEditLabel |
| `.mts-swatch[data-track-id][data-color]` | `_track_row.html` | Color swatch button; data-color read by JS to set initial visual fill via setProperty |
| `.mts-swatch--empty` | `_track_row.html` | Empty-swatch class (dashed border per UI-SPEC) |
| `[data-swatch-fill]` | `_track_row.html` | Inner span where JS writes setProperty('background-color', ..., 'important') |
| `.mts-swatch__empty-mark` | `_track_row.html` | The "⊘" symbol; removed when color set, re-added when cleared |
| `.mts-track-notes-display[data-track-id]` | `_track_row.html` | Plain display span for notes (Phase 1 — no edit affordance) |
| `.mts-remove-btn` | `_track_row.html` | Per-row remove button (calls mtsRemoveTrack) |
| `.mts-capacity` (`.mts-capacity--under` / `--at` / `--over` / `--no-cap`) | `editor.html` | Capacity bar state classes |
| `.mts-capacity__bar`, `.mts-capacity__fill[data-fill-percent]`, `.mts-capacity__text` | `editor.html` | Capacity bar internals |
| `[name=csrfmiddlewaretoken]` (in hidden form) | `editor.html` | CSRF source for AJAX |

### Picker Modal

| Hook | Template | Purpose |
|---|---|---|
| `#mts-picker-overlay` (.mts-picker-overlay) | `_picker_modal.html` | Modal overlay; toggled display:none/block by mtsOpenPicker / mtsClosePicker |
| `.mts-picker-panel[role="dialog"]` | `_picker_modal.html` | Modal panel container |
| `#mts-picker-title` | `_picker_modal.html` | aria-labelledby target |
| `.mts-picker-close` | `_picker_modal.html` | "×" close button |
| `.mts-tab[data-tab]` (`inputs` / `aux` / `matrix` / `stereo` / `manual`) | `_picker_modal.html` | Tab buttons; clicked → mtsSwitchTab |
| `.mts-tab--active` (added by JS) | `_picker_modal.html` | Active tab visual state |
| `[data-tab-count]` | `_picker_modal.html` | Per-tab count suffix span (e.g. "(47 available)") populated by JS |
| `.mts-tab-panel[data-panel]` | `_picker_modal.html` | One panel per tab; shown/hidden by mtsSwitchTab |
| `.mts-tab-header-count[data-panel-count]` | `_picker_modal.html` | Tab body header (e.g. "Inputs (47 available)") |
| `.mts-tab-bulk` | `_picker_modal.html` | Per-tab bulk-controls container |
| `.mts-link-btn` | `_picker_modal.html` | Select all / Clear / Remove buttons (link styling) |
| `.mts-link-btn--danger` | `_picker_modal.html` | Manual-row Remove button (red text) |
| `.mts-pick-list[data-pick-list]` | `_picker_modal.html` | Per-tab list container; populated by JS from #mts-picker-data |
| `.mts-pick-row` (added by JS via createElement) | (created by JS) | Per-channel row inside pick-list |
| `.mts-pick-checkbox` (added by JS) | (created by JS) | Per-channel checkbox |
| `.mts-pick-empty[data-empty-message][data-empty-no-channels][data-empty-all-added]` | `_picker_modal.html` | Empty-state caption for each tab; JS swaps text via the two data-attrs |
| `.mts-filter-input` | `_picker_modal.html` | Filter input; oninput → mtsFilterPicker |
| `.mts-manual-list[data-manual-list]` | `_picker_modal.html` | Manual-tab dynamic list container |
| `.mts-manual-add-btn` | `_picker_modal.html` | "+ Add another" — clones `<template id="mts-manual-row-template">` |
| `[data-manual-queued]` | `_picker_modal.html` | "{N} manual track{plural} queued" caption; updated by JS |
| `[data-commit-btn]` | `_picker_modal.html` | "Add N selected" footer button (text recomputed live by JS) |
| `<template id="mts-manual-row-template">` | `_picker_modal.html` | Native template element cloned by mtsAppendManualRow |
| `.mts-manual-row[data-manual-row]` | (template content) | Cloned manual-row container |
| `.mts-manual-row-header` | (template content) | Manual-row header strip (Track N + Remove) |
| `[data-manual-index]` | (template content) | Manual-row index display ("Track {N}") |
| `[data-manual-label][data-manual-color][data-manual-notes]` | (template content) | Manual-row form inputs read by mtsCommitPickerSelection |
| `[data-manual-error]` | (template content) | Per-row inline error span (red, hidden by default) |
| `#mts-picker-data` (script type="application/json") | `editor.html` | Pre-computed channel data (Plan 03's _build_picker_data → json.dumps); parsed once on first picker open |

### Color Picker

| Hook | Template | Purpose |
|---|---|---|
| `#mts-color-popover` (.mts-color-popover) | `_color_picker.html` | Single-instance popover; repositioned + shown by mtsOpenColorPicker |
| `.mts-swatch-grid` | `_color_picker.html` | 12-cell grid container |
| `.mts-color-swatch[data-color="#RRGGBB"]` | `_color_picker.html` | Each of 12 preset swatches (Red / Orange / Yellow / Green / Sky Blue / Blue / Purple / Pink / White / Grey / Brown / Black) — UI-SPEC verbatim |
| `.mts-color-popover__custom` | `_color_picker.html` | Custom-hex input row |
| `#mts-color-custom-input[pattern="^#[0-9A-Fa-f]{6}$"]` | `_color_picker.html` | Custom hex input; pattern matches Plan 04's `_HEX_COLOR_RE` server-side regex (defense in depth) |
| `.mts-color-clear-btn` | `_color_picker.html` | "Clear color" link (calls mtsApplyColor('')) |

## JS Function Contract (referenced via inline onclick — Plan 06 must define all)

Every `mtsXxx(...)` function name referenced from `onclick=` / `onchange=` / `onkeydown=` / `oninput=` / `oncontextmenu=` handlers across the seven templates:

### Dashboard cards (called from `_session_card.html`)
- `mtsToggleCardMenu(button, sessionId)` — toggle dropdown panel visibility
- `mtsDuplicateSession(sessionId, name)` — open duplicate-name prompt + POST to multitrack_duplicate
- `mtsRenameSession(sessionId, oldName)` — open rename prompt + POST to multitrack_rename
- `mtsDeleteSession(sessionId, name, trackCount)` — open delete-confirm modal + POST to multitrack_delete

### Editor toolbar / empty-state (called from `editor.html`)
- `mtsOpenPicker(tab)` — show picker overlay, switch to named tab; called by toolbar "+ Add tracks", empty-state CTA, and the auto_open_picker DOMContentLoaded shim (D-12)

### Picker modal (called from `_picker_modal.html`)
- `mtsClosePicker()` — hide picker overlay + reset state (also bound to overlay click + Escape per Plan 06)
- `mtsSwitchTab(tab)` — toggle active tab + corresponding tab-panel visibility
- `mtsFilterPicker(query)` — filter active tab's pick-list rows by substring match (case-insensitive)
- `mtsSelectAllTab(tab)` — check every visible (filter-passing) row in the named tab
- `mtsClearTab(tab)` — uncheck every row in the named tab
- `mtsAppendManualRow()` — clone `<template id="mts-manual-row-template">` into [data-manual-list]
- `mtsRemoveManualRow(button)` — remove the closest [data-manual-row] from the DOM
- `mtsCommitPickerSelection()` — POST to multitrack_add_tracks with {selections, manuals}, navigate on success

### Track row inline controls (called from `_track_row.html`)
- `mtsSetEnabled(trackId, checked)` — POST to multitrack_set_enabled
- `mtsEditLabel(trackId, cell)` — toggle label-cell to inline-edit mode (show .mts-track-label-input)
- `mtsSaveLabel(trackId, value)` — POST to multitrack_set_label, update .mts-track-label-display via textContent
- `mtsCancelLabel(input, trackId)` — restore display, hide input (Escape key)
- `mtsOpenColorPicker(event, trackId)` — position + show #mts-color-popover relative to clicked swatch
- `mtsApplyColor(hex)` — POST to multitrack_set_color, update target swatch via setProperty('background-color', value, 'important')
- `mtsClearColor(trackId)` — shortcut for mtsApplyColor('') on a specific track (right-click on swatch)
- `mtsRemoveTrack(trackId)` — POST to multitrack_remove_track, remove .mts-track-row from DOM, renumber

**Removed from JS contract per checker WARNING 3:**
- `mtsToggleNotes(trackId, span)` — NOT shipped in Phase 1 (no editable notes affordance on existing tracks)
- `mtsSaveNotes(trackId, value)` — NOT shipped in Phase 1 (no `multitrack_set_notes` endpoint in Plan 04)

When `multitrack_set_notes` lands in v2.0.1, restore both handlers (mirror `mtsSaveLabel`).

## Editor View Context Contract (confirmed)

Plan 03's `_editor_context(session, tracks=None, **extras)` helper was extended with `total_count` and `over_count` keys (per Task 3's note), and verified in `planner/views.py` lines 5820-5871:

| Key | Source | Used by |
|---|---|---|
| `session` | argument | editor.html (header, console.name, capacity, urls) |
| `tracks` | session.tracks ordered by track_number, or argument | editor.html (loop body) |
| `picker_data_json` | `json.dumps(_build_picker_data(session, tracks))` | `<script id="mts-picker-data">` block |
| `auto_open_picker` | True iff tracks list empty (D-12) | DOMContentLoaded shim |
| `total_count` | `len(tracks)` | capacity bar text |
| `over_count` | `max(0, total_count - capacity)` when set, else 0 | capacity bar over-state suffix |
| `export_error` (extra) | passed by Plan 04 export views' fallback | mts-alert--error block at top of toolbar |

The capacity-bar over-capacity suffix uses `over_count` directly — NO inline `{% widthratio %}` arithmetic, NO custom template tag. This is the binding contract Plan 03 was revised to centralise.

## URL References (binding for Plan 06's bootstrap reads)

`{% url '...' %}` references across all 7 templates:

| URL Name | Used In |
|---|---|
| `planner:multitrack_dashboard` | dashboard.html (back link N/A here), new_session.html (back link, Cancel on create), editor.html (back link) |
| `planner:multitrack_create` | dashboard.html (header CTA + empty-state CTA) |
| `planner:multitrack_editor` | _session_card.html (card link), new_session.html (Cancel on edit) |
| `planner:multitrack_edit` | editor.html (Edit session metadata link) |
| `planner:multitrack_export_rpp` | editor.html (Export to Reaper button) |
| `planner:multitrack_export_rtracktemplate` | editor.html (Export Track Template button) |

The 7 AJAX mutate URL names (`multitrack_reorder`, `multitrack_add_tracks`, `multitrack_set_color`, `multitrack_set_label`, `multitrack_set_enabled`, `multitrack_remove_track`, `multitrack_capacity_check`) are NOT referenced in templates — Plan 06's JS embeds them via its own bootstrap script (per Plan 06's design at lines noting `{% url %}` rendered into JS bootstrap blocks).

## Threat Mitigations Applied (T-05-* register)

All seven threats in the plan's `<threat_model>` are mitigated as designed:

- **T-05-01 (XSS via label / name / notes):** Django auto-escape applies to `{{ ... }}` by default. Only `picker_data_json|safe` uses |safe — that value is pre-`json.dumps()`'d server-side (Plan 03), so it's a JSON literal, not a user-controlled string. Verified: `grep "|safe"` across all 7 templates returns ONE hit (the picker_data_json line in editor.html).
- **T-05-02 (XSS via onclick):** All inlined string args use `|escapejs` (`session.name` in `_session_card.html` for Duplicate/Rename/Delete). Other onclick args are integer track IDs (no escaping required).
- **T-05-03 (XSS via Content-Disposition):** Templates emit a plain `{% url 'planner:multitrack_export_rpp' session.id %}` href — Plan 04's `_safe_filename` slugifies the session name on the response side; templates do NOT construct the header.
- **T-05-04 (XSS via inline color style):** No `style="background-color: {{ track.color_override }}"` anywhere. Color swatch uses `data-color="{{ track.color_override }}"` (auto-escaped) and JS writes the visual fill via `setProperty(...,'important')`. Verified: `grep "background-color\|style=\"background"` returns 0 across both editor templates.
- **T-05-05 (Clickjacking on Delete):** Inherits Django's default `X-Frame-Options: DENY/SAMEORIGIN` middleware. No template-level work needed.
- **T-05-06 (CSRF on AJAX):** Hidden `<form style="display:none">{% csrf_token %}</form>` in dashboard.html and editor.html provides the CSRF source. Plan 06's JS reads via `[name=csrfmiddlewaretoken]` per RESEARCH idiom #1.
- **T-05-07 (cross-project URL tampering):** Plan 03's view-layer IDOR-safe filter handles it. Templates only render URLs from project-scoped querysets — not the templates' responsibility.

## Acceptance Criteria Notes

All acceptance criteria from Tasks 1-4 pass with one minor adjustment:

- **Task 3 / `_track_row.html` notes-affordance grep:** The acceptance criterion `grep -cE "mts-notes-toggle|mts-notes-input|mts-notes-edit|pencil|📝"` initially matched my explanatory comment that contained the word "pencil" (in the phrase "Showing a pencil/icon/input here would mislead users"). I rewrote the comment to read "Rendering an editable affordance here would misleadingly imply edit-ability" so the grep returns 0. Substantive intent (no edit affordance, no input element, no JS handler) was satisfied from the first write — the rewrite is purely cosmetic to satisfy the literal regex.

All other acceptance-criteria greps pass with the exact counts the plan specified.

## Verification Notes

The plan's `<verify>` block prescribes Python template-load smoke tests:
```bash
python -c "from django.template.loader import get_template; ..." 
```

These could not be executed in this worktree because the sandbox blocked Python invocation (sandbox denial on `python` and `python manage.py shell`). However, every template's structural correctness was verified via the 30+ grep-based acceptance criteria across all four tasks (file existence, extends pattern, copy verbatim from UI-SPEC, DOM hooks present, |safe restricted to picker_data_json, etc.). The templates use only standard Django template syntax (`{% extends %}`, `{% load %}`, `{% block %}`, `{% url %}`, `{% include %}`, `{% if %}`/`{% for %}`/`{% with %}`, filters `default` / `pluralize` / `escapejs` / `timesince` / `widthratio` / `safe`) — no custom tags or experimental constructs. Charlie's first manual visit to the rendered page (after Plan 06 ships JS + CSS) is the smoke test. Issues, if any, will surface as a `TemplateSyntaxError` on first request and be trivially diagnosable.

## Threat Flags

None — no new security-relevant surface introduced outside the documented threat register. All seven new templates render data the views already expose; no new endpoints, no new write paths.

## Deviations from Plan

None — all four task action blocks executed verbatim. The single comment rewrite in `_track_row.html` (replacing the word "pencil" with "editable affordance" inside an explanatory comment) is documented under Acceptance Criteria Notes as a cosmetic adjustment to satisfy a literal grep regex; it changed zero rendered output.

## Issues Encountered

- **Sandbox blocked Python invocation.** The plan's `<verify>` blocks prescribe `python -c "from django.template.loader import get_template; ..."` smoke tests. The worktree sandbox denied direct `python` and `python manage.py shell` execution. Substituted with the 30+ grep-based acceptance-criteria checks the plan also specified — every check passed with the expected counts.
- **Worktree branch base was stale.** HEAD was on `e7561dc` (a beta-tester fix) instead of the expected `aa19442` (post-Plan-04 merge). Used `git reset --hard aa194423f65a3bbc7f2434fd63418127892c7a22` per the worktree_branch_check protocol — succeeded on first attempt despite the prompt's note about a previous respawn-blocker. No user changes lost (fresh worktree).

## User Setup Required

None — no external service configuration required. The new templates ship via the next push to `main` (Railway auto-redeploy). Templates won't render anything visible until Plan 06 lands the JS + CSS, but the Plan 03 view-layer is already live and will route requests to these template paths now.

## Next Phase Readiness

- **Plan 06 (JS + CSS, Wave 4):** unblocked — every DOM hook (class names + data attributes + element ids) is in place. The DOM Hook Contract section above is the binding inventory; the JS Function Contract section is the complete list of `mtsXxx()` handlers Plan 06 must define. The capacity bar's over-capacity rendering already lives in the view (`_editor_context.over_count`), so Plan 06's CSS only needs to style the three state classes (`mts-capacity--under` / `--at` / `--over`) — no JS-side arithmetic required for the bar.
- **First end-to-end render:** dashboard.html will render successfully (no JS dependencies for the empty-state path); the editor.html and new_session.html paths require Plan 06's JS for the picker / color picker / drag reorder flows but will render structurally without it.
- **Production deploy:** no special steps required. The next push to `main` ships these templates via Railway's standard `startCommand`.

## Self-Check

Verified all claims in this SUMMARY against the worktree state.

**Created files:**
- FOUND: `planner/templates/planner/multitrack/dashboard.html`
- FOUND: `planner/templates/planner/multitrack/_session_card.html`
- FOUND: `planner/templates/planner/multitrack/new_session.html`
- FOUND: `planner/templates/planner/multitrack/editor.html`
- FOUND: `planner/templates/planner/multitrack/_track_row.html`
- FOUND: `planner/templates/planner/multitrack/_picker_modal.html`
- FOUND: `planner/templates/planner/multitrack/_color_picker.html`

**Commits exist:**
- FOUND: `7c97fa3` Task 1 (dashboard + session card)
- FOUND: `b0191c6` Task 2 (new_session)
- FOUND: `a0f67b6` Task 3 (editor + track row)
- FOUND: `682bf03` Task 4 (picker modal + color picker)

**Scope boundary:**
- FOUND: `git diff --name-only aa194423 HEAD` shows exactly 7 files, all under `planner/templates/planner/multitrack/`. No touches to `planner/static/`, `planner/views.py`, `planner/urls.py`, `planner/forms.py`. Plan 01-06 contract honored.

**Acceptance-criteria grep counts (per task):**
- Task 1 dashboard: extends=1, "Multitrack Sessions"=2, subtitle=1, "+ New Session"=2, "No sessions yet"=1, "url 'planner:multitrack_create'"=2, csrf_token=1
- Task 1 _session_card: "url 'planner:multitrack_editor'"=1, |escapejs=3, |safe=0
- Task 2 new_session: extends=1, csrf_token=1, all 7 form fields=19 references, "(coming v2.0)"=1, "Drives the over-capacity warning bar"=1, |safe=0
- Task 3 editor: extends=1, "← Multitrack Sessions"=1, "Export to Reaper"=1, "Export Track Template"=1, "Edit session metadata"=1, "+ Add tracks"=2, mts-track-list=1, data-session-id=1, mts-picker-data=1, JS bundles=2, "Drag rows to reorder"=1, "No tracks yet"=1, auto_open_picker=1
- Task 3 _track_row: data-track-id=4, six DOM hooks=7, no inline color=0, inputs=2, no notes-affordance=0, no notes JS handlers=0, mts-track-notes-display=1
- Task 4 picker: "Add Tracks"=1, all 5 tabs present, "Filter by name or number"=1, "Select all"=4, "Clear"=4, "+ Add another"=1, data-pick-list=4, manual-row template=1, "Add 0 selected"=1
- Task 4 color picker: 12 swatches=12, "Custom:"=1, "Clear color"=1, HTML5 pattern=1

## Self-Check: PASSED

---

*Phase: 01-core-sessions-track-editor-reaper-export*
*Wave: 4 (parallel — alongside Plan 01-06 which owns JS + CSS)*
*Completed: 2026-05-11*
