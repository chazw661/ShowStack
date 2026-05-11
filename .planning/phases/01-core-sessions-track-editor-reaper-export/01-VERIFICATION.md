---
phase: 01-core-sessions-track-editor-reaper-export
verified: 2026-05-10T00:00:00Z
status: human_needed
score: 21/26 must-haves verified
overrides_applied: 0
counts:
  truths_total: 26
  truths_verified: 21
  truths_partial: 3
  truths_planned_deferral: 2
  artifacts_total: 23
  artifacts_verified: 23
  key_links_total: 12
  key_links_verified: 12
  requirements_total: 21
  requirements_satisfied: 18
  requirements_partial: 3
  anti_patterns_blocker: 0
  anti_patterns_warning: 4
  human_verification_items: 5
human_verification:
  - test: "Open exported .RPP in Reaper 7.x and confirm project loads"
    expected: "Reaper opens the file with one track per enabled MultitrackTrack, names + colors as configured, no errors"
    why_human: "Requires Reaper 7.x install + display. The 42 automated reaper_export tests cover the file-format structure (PEAKCOL, MAINSEND, NAME tokens, GUID consistency, six required tokens per block), but the actual Reaper-opens-it acceptance criterion (RPP-01..05 + ROADMAP SC #5) can only be confirmed by a live Reaper session."
  - test: "Drag-reorder a track in the editor and confirm the row numbers update + new order persists after reload"
    expected: "Sortable.js fires onEnd → POST /reorder/ → row numbers renumber 1..N client-side; reloading the page shows the same order"
    why_human: "Drag UX (cursor change, ghost row, drop animation) is a visual/interactive behavior; XHR contract is verified via 42 unit tests + URL-resolve checks but the user-facing drag behavior needs a real browser."
  - test: "Color-swatch picker visual: click a track's swatch, then click a color swatch in the popover"
    expected: "Popover opens below-left of the clicked swatch; clicked color fills the row swatch immediately; right-click on swatch clears it back to the dashed-border empty state"
    why_human: "setProperty('background-color', value, 'important') is verified in code (54 setProperty hits, no direct .style.X = Y assignments per CLAUDE.md), but the visual fill, popover positioning via getBoundingClientRect, and right-click clear are interactive behaviors."
  - test: "Capacity bar transitions: under → at → over"
    expected: "With recorder_capacity=4 and 3 tracks, bar shows '3 / 4' partially filled blue; add a 4th track, bar fills + shows '4 / 4'; add a 5th, bar turns red and shows '5 / 4 — 1 over capacity'"
    why_human: "Server-side classes (mts-capacity--under/--at/--over) and counts (total_count, over_count) are verified in code, but the live state transition (and the real visual width of the under-fill bar — see WR-01 below) needs a browser. **NOTE:** the under-capacity fill always renders 100% wide because no JS reads data-fill-percent — see WR-01 in the Anti-Patterns section."
  - test: "+ New Session flow ends in editor with picker auto-opened on Inputs tab"
    expected: "Submit form → land on /audiopatch/multitrack/<id>/ → picker overlay visible immediately, Inputs tab active (D-12)"
    why_human: "auto_open_picker context flag wires to a DOMContentLoaded shim that calls mtsOpenPicker('inputs') — verified in code, but the rendered modal visibility + tab active state needs a browser."

issues_carried_to_review_fix:
  # Two server-side authorization gaps identified in 01-REVIEW.md.
  # Per orchestrator directive these are quality issues handled via
  # /gsd-code-review-fix, NOT phase-completion gaps. The phase goal
  # is achieved end-to-end; viewer-write-access tightening is a
  # post-merge hardening pass.
  - id: "CR-01"
    issue: "9 AJAX mutate endpoints lack @login_required + viewer-block check"
    files: "planner/views.py:5949, 6016, 6056, 6115, 6158, 6283, 6309, 6339, 6362"
    severity: "critical (security — viewer privilege escalation within own project)"
    handled_by: "/gsd-code-review-fix (post-merge hardening)"
  - id: "CR-02"
    issue: "Mutate endpoints' inconsistent auth gate creates within-project enumeration + mutation oracle"
    severity: "critical (same root cause as CR-01)"
    handled_by: "/gsd-code-review-fix (closed by CR-01 fix)"
---

# Phase 1: Core Sessions, Track Editor & Reaper Export — Verification Report

**Phase Goal:** Build a session and export `.RPP` end-to-end. Engineer lands on Multitrack Session Builder, sees all sessions for current project, can create/duplicate/rename/delete one. In the editor, can include input channels, Aux/Matrix/Group/FX/Cue outputs as tracks; bulk-toggle Aux/Matrix/Group sections; add a manual track; remove any track without affecting the underlying console channel. Per-track label/color override, drag-reorder, enable/disable, capacity counter that turns red when over `recorder_capacity`. Click "Export to Reaper" → downloads `.RPP` (and optionally `.RTrackTemplate`) where names/colors/order match the resolved values. Opening the exported `.RPP` in Reaper produces a valid project.

**Verified:** 2026-05-10T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Roadmap Success Criterion | Status | Evidence |
|---|---------------------------|--------|----------|
| SC-1 | Engineer lands on Multitrack Session Builder, sees all sessions for current project, can create/duplicate/rename/delete one | VERIFIED | `multitrack_dashboard` (views.py:5744) renders dashboard.html with `MultitrackSession.objects.filter(project=current_project)` queryset. Session card dropdown wires Duplicate/Rename/Delete (`mtsDuplicateSession`/`mtsRenameSession`/`mtsDeleteSession` in JS, posting to multitrack_duplicate/rename/delete endpoints — all 3 URLs reverse correctly). Create flow via `multitrack_create_view` (5897). |
| SC-2a | Editor can include input channels, Aux outputs, Matrix outputs as tracks | VERIFIED | `_build_picker_data` (views.py:5763) populates four channel lists (inputs, aux, matrix, stereo); picker modal has 5 tabs (verified in `_picker_modal.html`); `multitrack_add_tracks` (views.py:6158) creates `MultitrackTrack` rows with the correct `source_type` discriminator. |
| SC-2b | Editor can include **Group outputs, FX returns, and Cue outputs** as tracks | PLANNED DEFERRAL | **NOT first-class in Phase 1.** No `ConsoleGroupOutput`/`ConsoleFXReturn`/`ConsoleCueOutput` models exist in the codebase. The discriminator `source_type` choices are `[input, aux, matrix, stereo, manual]` only (models.py:992). CONTEXT D-03 explicitly defers Group/FX/Cue first-class support to v2.1: "Group / FX return / Cue output are handled as `manual` tracks for v2.0 (engineer types the label by hand). See Deferred Ideas for the v2.1 path." Engineers can add these as Manual tracks via the picker's Manual tab (D-11). The literal ROADMAP SC #2 and TRK-06 wording is not met; the v2.0-as-manual workaround is documented as the intentional scope decision. **Requires human acknowledgement** that this v2.1 deferral is acceptable for Phase 1 sign-off. |
| SC-2c | Bulk-toggle Aux/Matrix/Group sections | PARTIAL (D-08 reframed) | **Reframed per CONTEXT D-08:** "TRK-09 bulk toggles live inside the picker as per-tab Select all / Clear header controls — not as a separate sticky row in the editor." The picker modal has `mtsSelectAllTab` / `mtsClearTab` per tab (Inputs, Aux, Matrix, Stereo). The literal "collapsible section toggles" wording in TRK-09 is reframed to per-tab Select-all/Clear. There is no Group tab (deferred to v2.1 per D-03). Functionally the bulk-toggle requirement is met for Aux/Matrix; Group bulk toggle is unavailable until v2.1. |
| SC-2d | Add a manual track with no source channel | VERIFIED | Picker has Manual tab (`_picker_modal.html`); `mtsAppendManualRow` clones `<template id="mts-manual-row-template">` (D-11); `multitrack_add_tracks` validates label-required and creates rows with `source_type='manual', source_id=None` (views.py:6240). |
| SC-2e | Remove any track without affecting underlying console channel | VERIFIED | `multitrack_remove_track` (views.py:6362) calls `track.delete()`. The discriminator pattern (D-01) means `MultitrackTrack` has NO FK to channel models — there is no CASCADE risk. Verified: `MultitrackTrack` has only `session` FK (CASCADE); `source_id` is a plain `PositiveIntegerField`. |
| SC-3a | Per-track label override | VERIFIED | `MultitrackTrack.label_override` field (CharField max=100); `multitrack_set_label` endpoint (views.py:6309); `mtsSaveLabel` JS handler; click-to-edit pair `.mts-track-label-display` / `.mts-track-label-input` in `_track_row.html`. |
| SC-3b | Per-track color override | VERIFIED | `MultitrackTrack.color_override` field; `multitrack_set_color` (views.py:6283) validates `^#[0-9A-Fa-f]{6}$`; 12-swatch popover + custom hex input in `_color_picker.html`; `mtsApplyColor` writes via `setProperty('background-color', value, 'important')`. |
| SC-3c | Drag-reorder | VERIFIED | Sortable.js 1.15.7 vendored at `planner/static/planner/js/vendor/Sortable.min.js` (45478 bytes); `Sortable.create(list, { handle: '.mts-drag', animation: 150, onEnd: ... })`; `multitrack_reorder` (views.py:6115) does dense renumber 1..N via `bulk_update`. (Drag UX itself is in `human_verification`.) |
| SC-3d | Enable/disable individual tracks | VERIFIED | `MultitrackTrack.enabled` field; `multitrack_set_enabled` endpoint (views.py:6339); `mtsSetEnabled` JS handler toggling `.mts-track-row--disabled` class. |
| SC-3e | Capacity counter "47 / 64" turning red when over | PARTIAL | Counter logic correct: `_editor_context` computes `total_count` + `over_count` (views.py:5837-5853); template renders three CSS state classes (`mts-capacity--under` / `--at` / `--over`); CSS color tokens correct (`#dc3545` over, `#00ff88` at, `#4a9eff` under). **HOWEVER** — see Anti-Patterns WR-01: under-capacity fill bar always renders 100% width because no JS reads `data-fill-percent`. The text count shows correctly; only the bar visual under-state is wrong. |
| SC-4a | Click "Export to Reaper" downloads .RPP | VERIFIED | `multitrack_export_rpp` (views.py:6435) returns `HttpResponse(build_rpp(session), content_type='text/plain')` with `Content-Disposition: attachment; filename="<safe>.RPP"`. End-to-end smoke test (verifier ran live): generated 721-char RPP for 3-track session with Kick In (red), Snare Top (green), Hat (no color) — all 6 required tokens present per track block. |
| SC-4b | Track names match resolved labels | VERIFIED | `_track_block` writes `NAME "{_sanitize_name(track.resolved_label)}"`; sanitization replaces `"` → `'` (Pitfall 8); D-14 `resolved_label` cascade verified (label_override → channel name field → '(untitled)'). End-to-end smoke test confirmed names appear correctly. |
| SC-4c | Track colors match resolved colors via packed RGB | VERIFIED | `hex_to_peakcol(hex)` returns `0x01000000 \| (B<<16) \| (G<<8) \| R`; sentinel `16576` for empty/None/malformed. End-to-end smoke test confirmed `#FF0000 → 16777471`, `#00FF00 → 16842496`, `'' → 16576`. PEAKCOL formula verified across 5 sources per RESEARCH (LOCKED). |
| SC-4d | Track order matches session.track_order_mode | VERIFIED | `_ordered_enabled_tracks(session)` dispatches: `'console'` (source-type priority then channel number), `'dante'` (resolved_dante_number ascending), `'custom'` (track_number ascending). 12 of 42 unit tests cover ordering across all three modes. |
| SC-4e | Optional .RTrackTemplate export | VERIFIED | `build_rtracktemplate(session)` returns same per-track blocks at indent 0 with no `<REAPER_PROJECT>` wrapper; `multitrack_export_rtracktemplate` view (6481) wires it. End-to-end smoke test produced 529-char RTT output, no project wrapper, 3 track blocks. |
| SC-5 | Opening exported .RPP in Reaper produces valid project | HUMAN VERIFICATION REQUIRED | Cannot verify without Reaper install. Automated tests cover file-format correctness (42 tests including PEAKCOL, MAINSEND, six required tokens per block, GUID consistency, no forbidden tokens). The actual Reaper-opens-it test must be run by Charlie at phase merge time. **Note:** Plan 02 SUMMARY confirms `MAINSEND 1 0` is present per block (Pitfall 6 — without it tracks are silent in DAW). |

### Plan-Level Must-Haves (from PLAN frontmatter)

| Plan | Must-Have | Status |
|------|-----------|--------|
| 01 | MultitrackSession + MultitrackTrack tables exist with proper schema | VERIFIED (models.py:915, 982; migration 0152) |
| 01 | Discriminator `(source_type, source_id)` with DB index | VERIFIED (mts_track_src_idx in migration; index in Meta) |
| 01 | 4 @property resolver helpers (resolved_source/label/color/dante_number) | VERIFIED (all 4 confirmed as `property` instances via introspection) |
| 01 | post_delete signals convert orphans to manual (D-04) | VERIFIED (live ORM test: ConsoleInput delete → MultitrackTrack.source_type='manual', source_id=None, label_override='Kick In' snapshot preserved) |
| 01 | MultitrackSessionAdmin on showstack_admin_site (NOT admin.site) | VERIFIED (`MultitrackSession in showstack_admin_site._registry`) |
| 01 | admin_ordering 'multitracksession': 12.7 | VERIFIED (admin_ordering.py:112) |
| 01 | Migration 0152 additive only — zero ALTER on channel models | VERIFIED (`grep ConsoleInput\|ConsoleAuxOutput\|ConsoleMatrixOutput\|ConsoleStereoOutput` returns 0; only 2 CreateModel ops) |
| 02 | build_rpp(session) → str | VERIFIED (live smoke test produced 721-char output, structurally correct) |
| 02 | build_rtracktemplate(session) → str | VERIFIED (live smoke test produced 529-char output, no project wrapper) |
| 02 | hex_to_peakcol via documented formula | VERIFIED (formula at reaper_export.py:69; 42 unit tests pass) |
| 02 | YAMAHA_TO_HEX dormant in Phase 1 | VERIFIED (only test file imports it) |
| 03 | MultitrackSessionForm with current-project console scoping | VERIFIED (queryset narrowing in __init__; project NOT in fields) |
| 03 | 7 page-render views | VERIFIED (all 7 importable from planner.views) |
| 03 | _editor_context as canonical context contract | VERIFIED (returns {session, tracks, picker_data_json, auto_open_picker, total_count, over_count}; called by Plan 03 editor + Plan 04 export fallbacks) |
| 04 | 7 AJAX mutate endpoints + 2 file-download views | VERIFIED (all 9 importable; URLs reverse) |
| 04 | _get_track_for_request IDOR-safe via session.project chain | VERIFIED (uses `session__project=current_project` filter) |
| 04 | _HEX_COLOR_RE rejects everything except '' or '#RRGGBB' | VERIFIED (live: rejects 'red', '#FFF', 'javascript:alert(1)') |
| 04 | _safe_filename slugifies for Content-Disposition | VERIFIED (live: '../../etc/passwd' → '______etc_passwd') |
| 05 | All 7 templates load without TemplateSyntaxError | VERIFIED (Django get_template() succeeds for all 7) |
| 05 | Picker has 5 tabs, picker_data_json embedded | VERIFIED (5 tabs in _picker_modal.html; `<script id="mts-picker-data" type="application/json">` in editor.html) |
| 05 | No `\|safe` on user fields | VERIFIED (only picker_data_json\|safe; that value is pre-json.dumps()'d) |
| 06 | Sortable.js 1.15.7 vendored | VERIFIED (45478 bytes at planner/static/planner/js/vendor/Sortable.min.js, MIT) |
| 06 | All DOM color writes use setProperty('important') | VERIFIED (54 setProperty hits; node --check exits 0) |
| 06 | All 22 mtsXxx functions on window match template onclick handlers | VERIFIED (22 unique window.mts* exports, covers every onclick from Plan 05 templates) |

### Required Artifacts (file-by-file)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `planner/models.py` | MultitrackSession + MultitrackTrack + _source_model_for | VERIFIED | Added at lines 915, 969, 982; ~162 lines added |
| `planner/signals.py` | _convert_orphans_to_manual + 4 receivers | VERIFIED | Helper at signals.py:41; 4 @receiver decorators at 61, 72, 78, 84 |
| `planner/admin.py` | MultitrackSessionAdmin on showstack_admin_site | VERIFIED | Class at admin.py:5904; registration at 5947 |
| `planner/admin_ordering.py` | 'multitracksession': 12.7 | VERIFIED | Entry at admin_ordering.py:112 |
| `planner/migrations/0152_multitrack_session_track.py` | Additive only, 2 CreateModel | VERIFIED | 2 CreateModel ops, 0 references to existing channel models |
| `planner/utils/reaper_export.py` | build_rpp, build_rtracktemplate, hex_to_peakcol, YAMAHA_TO_HEX | VERIFIED | All 4 public exports + helpers; 9877 bytes |
| `planner/forms.py` | MultitrackSessionForm | VERIFIED | Class with current-project console scoping; project NOT in fields |
| `planner/views.py` | 16 views + 6 helpers | VERIFIED | All 7 page-render + 9 AJAX/export views; helpers _build_picker_data, _editor_context, _get_track_for_request, _safe_filename, _has_enabled_tracks, _HEX_COLOR_RE |
| `planner/urls.py` | 16 multitrack URL routes | VERIFIED | All 16 URLs reverse correctly |
| `planner/templates/planner/multitrack/dashboard.html` | Module landing page | VERIFIED | Loads via Django template loader; UI-SPEC copy verbatim |
| `planner/templates/planner/multitrack/editor.html` | Track editor page | VERIFIED | Loads; mts-track-list, picker_data_json embed, JS bundles wired |
| `planner/templates/planner/multitrack/new_session.html` | Create + edit form | VERIFIED | Loads; 7 form fields in UI-SPEC order; Nuendo Live disabled with caption |
| `planner/templates/planner/multitrack/_session_card.html` | Per-card partial | VERIFIED | Loads; \|escapejs on session.name in dropdown handlers |
| `planner/templates/planner/multitrack/_track_row.html` | Per-track row partial | VERIFIED | Loads; 8-column layout; notes display-only per WARNING 3 |
| `planner/templates/planner/multitrack/_picker_modal.html` | Channel picker modal | VERIFIED | Loads; 5 tabs; manual-row `<template>`; commit footer |
| `planner/templates/planner/multitrack/_color_picker.html` | 12-swatch popover | VERIFIED | Loads; 12 data-color attrs; HTML5 pattern matches server regex |
| `planner/static/planner/js/multitrack_editor.js` | Module controller | VERIFIED | 666 lines; node --check OK; 22 window.mts* exports; 54 setProperty/CSRF/Sortable/fetch hits |
| `planner/static/planner/js/vendor/Sortable.min.js` | Sortable.js 1.15.7 vendored | VERIFIED | 45478 bytes; MIT |
| `planner/static/planner/css/multitrack.css` | Module CSS | VERIFIED | 1081 lines; 159 mts-* class rules; 12 data-color selectors; 0 cc- leakage |
| `planner/tests/test_reaper_export.py` | 42 unit tests | VERIFIED | All 42 tests pass with `--settings=audiopatch.test_settings` |

### Key Link Verification (Wiring)

| From | To | Via | Status |
|------|----|----|--------|
| MultitrackTrack.resolved_source | ConsoleInput/Aux/Matrix/Stereo | _source_model_for(source_type) module-level dispatch | VERIFIED (live test: resolved_label correctly returned 'Kick In' before delete) |
| post_delete receivers | MultitrackTrack rows | _convert_orphans_to_manual helper | VERIFIED (live test: ConsoleInput delete → orphan converted with snapshot) |
| MultitrackSessionAdmin.changelist_view | /audiopatch/multitrack/ | redirect('planner:multitrack_dashboard') | VERIFIED (URL resolves) |
| build_rpp / build_rtracktemplate | MultitrackTrack.resolved_label/color/dante_number | _ordered_enabled_tracks(session) iteration | VERIFIED (live smoke test: names + colors render correctly in output) |
| MultitrackSessionForm.console queryset | Console.objects.filter(project=current_project) | __init__ kwarg request= | VERIFIED (form scopes via request.current_project; project not in fields) |
| multitrack_create_view | redirect('planner:multitrack_editor') | POST success branch | VERIFIED (views.py:5912) |
| multitrack_duplicate | MultitrackTrack.bulk_create | iterate source.tracks.all() | VERIFIED (views.py:6000) |
| multitrack_reorder | MultitrackTrack.bulk_update | dense renumber 1..N | VERIFIED (views.py:6149) |
| multitrack_export_rpp | build_rpp from planner.utils.reaper_export | HttpResponse + Content-Disposition | VERIFIED (live smoke test: 721 chars, attachment header) |
| multitrack_set_color | MultitrackTrack.color_override | regex-validated hex update | VERIFIED (live: regex rejects javascript:alert(1)) |
| editor.html | _track_row.html (per track) | {% for %}{% include %} | VERIFIED (template loads) |
| Sortable.js onEnd | /audiopatch/multitrack/<id>/reorder/ | fetch POST with X-CSRFToken | VERIFIED (JS source includes Sortable.create + fetch wiring) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| dashboard.html | sessions | `MultitrackSession.objects.filter(project=current_project)` | YES (real ORM query, no fixtures) | FLOWING |
| editor.html | tracks | `session.tracks.all().order_by('track_number')` (via _editor_context) | YES (real ORM relation) | FLOWING |
| editor.html | picker_data_json | `_build_picker_data(session, tracks)` queries ConsoleInput/Aux/Matrix/Stereo for session.console | YES (real ORM queries on each channel model) | FLOWING |
| editor.html | total_count, over_count | `len(tracks)` and `max(0, total_count - capacity)` from _editor_context helper | YES (computed from real data) | FLOWING |
| _track_row.html | track.resolved_label | D-14 cascade: label_override → channel name field → '(untitled)' | YES (live test confirmed 'Kick In' resolved correctly) | FLOWING |
| build_rpp output | track names + colors + order | resolved_label / resolved_color / track_number | YES (live smoke test produced correct PEAKCOL ints + names) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 42 reaper_export unit tests pass | `python manage.py test planner.tests.test_reaper_export --settings=audiopatch.test_settings` | "Ran 42 tests... OK" | PASS |
| All 16 multitrack URLs resolve | Live `reverse()` for all 16 URL names | All 16 print expected paths | PASS |
| All 7 templates load | `get_template()` for all 7 paths | All 7 print "loaded" | PASS |
| JS syntax valid | `node --check planner/static/planner/js/multitrack_editor.js` | exit 0, no output | PASS |
| D-04 orphan conversion | Live ORM: create ConsoleInput + MultitrackTrack, delete input, refresh track | source_type='manual', source_id=None, label_override='Kick In' | PASS |
| End-to-end .RPP build | Live `build_rpp(session)` for 3-track session | 721-char output with all 6 required tokens per block, correct PEAKCOLs | PASS |
| End-to-end .RTrackTemplate build | Live `build_rtracktemplate(session)` | 529-char output, 0 REAPER_PROJECT wrappers, 3 TRACK blocks | PASS |
| _HEX_COLOR_RE rejects XSS | Live regex match against 'javascript:alert(1)' | False | PASS |
| _safe_filename rejects path traversal | Live `_safe_filename('../../etc/passwd')` | '______etc_passwd' | PASS |
| Models import + admin registration | Live import + `showstack_admin_site._registry` | MultitrackSession registered on showstack_admin_site (NOT admin.site) | PASS |

### Requirements Coverage

| Req | Source Plan(s) | Description | Status | Evidence |
|-----|----------------|-------------|--------|----------|
| MTS-01 | 01-01, 01-03 | Create new MultitrackSession with console / DAW / feed-source / track-order | SATISFIED | MultitrackSessionForm + multitrack_create_view; live URL resolves |
| MTS-02 | 01-01, 01-03 | Name + rename, unique per project | SATISFIED | unique_together=(project,name); clean_name + multitrack_rename with verbatim UI-SPEC error string |
| MTS-03 | 01-03, 01-05, 01-06 | List sessions, create/duplicate/delete actions | SATISFIED | multitrack_dashboard + dashboard.html + _session_card.html dropdown |
| MTS-04 | 01-01, 01-03 | Edit metadata without losing tracks | SATISFIED | multitrack_edit_view uses ModelForm(instance=session); tracks not touched |
| MTS-05 | 01-01, 01-03, 01-06 | Delete session + cascade tracks | SATISFIED | multitrack_delete; FK CASCADE on MultitrackTrack.session |
| MTS-06 | 01-03, 01-06 | Duplicate session + tracks | SATISFIED | multitrack_duplicate uses bulk_create for tracks |
| TRK-01 | 01-01, 01-05 | See all tracks ordered with #, type, label, color, enabled, notes | PARTIAL | Editor renders all required columns. **Caveat:** TRK-01 requires display of "input / aux / matrix / **group / FX return / cue**" — Group/FX/Cue are absent (deferred per D-03). |
| TRK-02 | 01-01, 01-04, 01-05, 01-06 | Enable/disable individual tracks | SATISFIED | enabled BooleanField + multitrack_set_enabled + mtsSetEnabled |
| TRK-03 | 01-01, 01-04, 01-05, 01-06 | Override label | SATISFIED | label_override + multitrack_set_label + mtsSaveLabel |
| TRK-04 | 01-01, 01-04, 01-05, 01-06 | Color picker | SATISFIED | color_override + multitrack_set_color + 12-swatch picker + custom hex |
| TRK-05 | 01-04, 01-05, 01-06 | Drag-reorder | SATISFIED (UX human-verify) | Sortable.js + multitrack_reorder + bulk_update renumber |
| TRK-06 | 01-04, 01-05, 01-06 | Add tracks from any console channel — **inputs, aux, matrix, group, FX return, cue all first-class** | PARTIAL | Inputs/Aux/Matrix/Stereo are first-class in the picker. **Group/FX/Cue missing** — deferred per CONTEXT D-03 to v2.1; in v2.0 they ride the Manual tab. |
| TRK-07 | 01-04, 01-05, 01-06 | Manual track with no source | SATISFIED | Manual tab with inline form (D-11); source_type='manual', source_id=None |
| TRK-08 | 01-01, 01-04, 01-05, 01-06 | Remove track without affecting source channel | SATISFIED | track.delete() removes only MultitrackTrack; no FK constraint to source |
| TRK-09 | 01-05, 01-06 | Bulk include/exclude Aux/Matrix/Group via collapsible section toggles | PARTIAL (D-08 reframed) | Per-tab Select all / Clear in picker (Aux, Matrix). **Group toggle absent** (no Group source type in v2.0). |
| TRK-10 | 01-01, 01-04, 01-05 | Capacity counter "47 / 64", red over capacity | PARTIAL | Counter text + red/at/under classes correct. **Bar visual under-state always 100% wide** (WR-01 — JS doesn't read data-fill-percent). |
| RPP-01 | 01-02, 01-04 | Export .RPP, one track per enabled track | SATISFIED | build_rpp + multitrack_export_rpp; enabled filter in _ordered_enabled_tracks |
| RPP-02 | 01-02, 01-04 | Track names match resolved labels | SATISFIED | _track_block writes _sanitize_name(track.resolved_label); 42 tests cover |
| RPP-03 | 01-02, 01-04 | Track colors mapped Yamaha→Reaper packed RGB | SATISFIED | hex_to_peakcol formula verified; YAMAHA_TO_HEX dormant in Phase 1 (Phase 2 consumer) — Phase 1 colors come from color_override hex directly |
| RPP-04 | 01-02, 01-04 | Track order matches track_order_mode | SATISFIED | _ordered_enabled_tracks dispatches console/dante/custom; 12 tests cover |
| RPP-05 | 01-02, 01-04 | .RTrackTemplate export | SATISFIED | build_rtracktemplate + multitrack_export_rtracktemplate |

**No orphaned requirements** — all 21 IDs from the phase are claimed by at least one plan.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| planner/views.py | 5949,6016,6056,6115,6158,6283,6309,6339,6362 | 9 AJAX mutate endpoints lack @login_required + viewer-block | CRITICAL (security) | Viewer (read-only) role can mutate any session/track in current project. Identified in 01-REVIEW.md (CR-01/CR-02). **NOT a phase-completion gap per orchestrator directive — handled via /gsd-code-review-fix.** |
| planner/templates/planner/multitrack/editor.html | 56 | `data-fill-percent` attribute never read by JS | WARNING (visual bug) | Under-capacity fill bar always renders 100% wide due to CSS `width: 100% !important`. Text count is correct; only visual under-state is wrong. WR-01 in code review. |
| planner/views.py | 6011,6051,6077,6153,6278,6304,6334,6357,6380 | `try / except Exception as e: return JsonResponse({'error': str(e)})` | WARNING (info disclosure) | Raw Python exception messages leak to clients (DB constraint names, NoneType errors). WR-02 in code review. |
| planner/signals.py | 73-86 | `name or f'Aux {None}' or '(deleted aux)'` — `'(deleted ...)'` fallback unreachable | WARNING (UX) | Orphaned tracks get labels like 'Aux None' instead of '(deleted aux)' when both name and aux_number are missing. WR-05 in code review. |
| planner/views.py | 6132 | `multitrack_reorder` accepts subset of session tracks (latent bug) | WARNING (data integrity) | Posting only some IDs creates duplicate track_numbers. Client always sends full list, but a third-party API caller could exploit. WR-04. |
| planner/views.py | 6421 | `_safe_filename` keeps non-ASCII letters via isalnum() | WARNING (RFC 6266) | Session named "Café Show" emits non-ASCII filename in Content-Disposition; some browsers mojibake. WR-06. |

### Human Verification Required

5 items require human testing — see `human_verification` in frontmatter. Most critical:

1. **Open exported .RPP in Reaper 7.x** — Plan 02 SUMMARY documents this as a documented manual smoke-test step deferred to phase merge. Verifier confirmed the file-format structure is correct via 42 unit tests + live end-to-end smoke (721-char output with all 6 required tokens, correct PEAKCOLs, no forbidden tokens). Acceptance gate: file opens cleanly with one track per enabled MultitrackTrack, names + colors as configured.

2. **Drag-reorder UX** — Sortable.js 1.15.7 vendored + `Sortable.create` wired with handle '.mts-drag', animation 150, and onEnd POST to /reorder/. The XHR contract is verified, but the cursor change + ghost row + drop animation is interactive.

3. **Color-swatch picker visual** — `setProperty('background-color', value, 'important')` is verified in code (no direct `.style.X = Y` assignments), but the visual fill, popover positioning, and right-click clear are interactive.

4. **Capacity bar transitions** — Server-side classes + counts are verified, but the live state transition (and the actual under-fill width — see WR-01) needs a browser.

5. **+ New Session → editor with picker auto-opened** — auto_open_picker context flag is verified, but the rendered modal visibility needs a browser.

### Gaps Summary (Planned Deferrals + Partial Truths)

The phase is functionally complete with two intentional v2.1 deferrals that diverge from a literal reading of the ROADMAP and TRK-06:

**1. Group / FX return / Cue output as first-class source types — DEFERRED to v2.1 per CONTEXT D-03**

ROADMAP SC #2 and TRK-06 both explicitly require these channel types as first-class selectable sources. CONTEXT D-03 documents the deliberate scope decision: "Phase 1 ships exactly four real channel types plus `manual`: input, aux, matrix, stereo. Group / FX return / Cue output are handled as `manual` tracks for v2.0 (engineer types the label by hand). See Deferred Ideas for the v2.1 path." The codebase has no `ConsoleGroup*`/`ConsoleFX*`/`ConsoleCue*` models — adding them is real schema + UI work that is intentionally pushed to v2.1.

**Functional impact:** engineers can still capture these channels in their session, but as Manual tracks (no source FK, hand-entered label). Group bulk-toggle (TRK-09 fragment) is unavailable. The literal phase goal is not met; the v2.0-as-manual workaround is documented.

**Resolution:** requires Charlie's explicit acknowledgement that v2.1 deferral of Group/FX/Cue first-class support is acceptable for Phase 1 sign-off.

**2. Capacity bar under-state visual (WR-01) — bug**

The under-capacity branch renders `<span class="mts-capacity__fill" data-fill-percent="...">` but no JS reads `data-fill-percent` and the CSS rule is `width: 100% !important;`. Result: a 4-of-64 session shows the same fully-filled bar as a 63-of-64 session. Text count + state class are correct; only the fill width is wrong. Trivial fix: inline `style="width:{% widthratio total_count session.recorder_capacity 100 %}%"` on the under-branch span.

**3. Server-side authorization gaps (CR-01, CR-02) — handled via /gsd-code-review-fix**

9 AJAX mutate endpoints lack `@login_required` and a viewer-block check. `CurrentProjectMiddleware` blocks anonymous access in practice, but viewers in a project can mutate any session/track in that project. Per orchestrator directive these are quality issues for the post-merge `/gsd-code-review-fix` cycle, NOT phase-completion gaps. The phase goal (engineer can build a session and export Reaper) is not blocked by these gaps.

---

_Verified: 2026-05-10T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
