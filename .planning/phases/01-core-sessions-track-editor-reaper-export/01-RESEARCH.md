# Phase 1: Core Sessions, Track Editor & Reaper Export — Research

**Researched:** 2026-05-09
**Domain:** Django 5.x model + view + admin work; Reaper `.RPP`/`.RTrackTemplate` text-format generation; jQuery + vendored Sortable.js drag-reorder UI
**Confidence:** HIGH (Reaper format verified from real RPP/RTrackTemplate fixtures + SWS source; Django patterns verified by direct codebase reads; Sortable.js version verified from npm registry)

---

## Summary

This phase adds two new tables (`MultitrackSession`, `MultitrackTrack`), one full new module page (`/audiopatch/multitrack/`), one new utility module (`planner/utils/reaper_export.py` or submodule), and a small set of `post_delete` signals on the four existing channel models — all additively. The four existing channel-source models (`ConsoleInput`, `ConsoleAuxOutput`, `ConsoleMatrixOutput`, `ConsoleStereoOutput`) are **not** modified — Phase 1 ships zero `ALTER TABLE` migrations against beta-tester data.

The Reaper `.RPP` format is plain text, line-oriented, with `<...` opening blocks, `>` closing blocks, and key-value lines inside. Track color is a single field `PEAKCOL <int>` where the int packs `0x01000000 | (B<<16) | (G<<8) | R` — the high `0x01000000` (16777216) bit signals "custom color enabled," and the 24 RGB bits are stored cross-platform R-low / B-high. The default value `16576` is what REAPER writes when no custom color is set; we omit `PEAKCOL` (or write `16576`) for tracks with no override. `.RTrackTemplate` is the same syntax with no `<REAPER_PROJECT...` wrapper — it's just one or more `<TRACK ...>` blocks back-to-back. Both formats are well-tolerated when the writer keeps to a small required-token set.

**Primary recommendation:** Build the editor as a single Django template under `templates/planner/multitrack_editor.html` extending `admin/base_site.html`, vanilla-CSS-modal channel picker (matching the help modal pattern at `templates/admin/base_site.html:138`), jQuery + vendored Sortable.js (`planner/static/planner/js/vendor/Sortable.min.js`, version 1.15.7) for drag-reorder, AJAX `POST /audiopatch/multitrack/<id>/reorder/` returning JSON. Reaper exporter is a single module at `planner/utils/reaper_export.py` (standalone file matches `yamaha_export.py`'s precedent over a submodule). `post_delete` signals live in the existing `planner/signals.py` module (already wired in `apps.py`); reuse the same try/except idempotency idiom as `ensure_user_profile`.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Source-Channel Reference Model**

- **D-01:** `MultitrackTrack` references its source via a discriminator pattern, not a real FK. Two fields: `source_type` (`CharField(max_length=10, choices=[('input','Input'),('aux','Aux Output'),('matrix','Matrix Output'),('stereo','Stereo Output'),('manual','Manual')])`) and `source_id` (`PositiveIntegerField(null=True, blank=True)` — null for manual tracks). No FK constraint, no CASCADE risk to beta data. Resolution happens in a Python helper (see D-14).
- **D-02:** No FK constraint means orphan rows are possible if a channel is deleted. Handled by D-04, not by DB constraints.
- **D-03:** Phase 1 ships exactly four real channel types plus `manual`: `input` → `ConsoleInput`, `aux` → `ConsoleAuxOutput`, `matrix` → `ConsoleMatrixOutput`, `stereo` → `ConsoleStereoOutput`. Group / FX return / Cue output are handled as `manual` tracks for v2.0.
- **D-04:** When a `ConsoleInput` / `ConsoleAuxOutput` / `ConsoleMatrixOutput` / `ConsoleStereoOutput` row is deleted, a `post_delete` signal converts every matching `MultitrackTrack` to manual: `source_type='manual'`, `source_id=NULL`, `label_override` = (existing override) OR last-known channel name, `color_override` = (existing override) OR last-known channel color (if any). Engineer never silently loses a track row.

**Track Color Storage**

- **D-05:** Phase 1 stores color **only** on `MultitrackTrack.color_override` (hex `CharField(max_length=7)`). No new color fields on the existing four channel models. The editor's swatch picker writes directly to `color_override`. Phase 2 CSV import is the natural place to populate channel-level colors.
- **D-06:** Resolved-color helper returns `color_override` if set, else the Phase 5 `default_record_color` (when that field exists), else `None` (Reaper exporter omits color → DAW default).

**Channel Picker UX (TRK-06, TRK-07, TRK-09)**

- **D-07:** "Add tracks" opens a modal picker with type tabs: `[Inputs] [Aux] [Matrix] [Stereo] [Manual]`. Each tab is a checkable list of channels filtered to that type. A filter/search box at the top of the modal filters the active tab. "Add N selected" commits all checked rows in one request.
- **D-08:** TRK-09 bulk toggles live **inside the picker** as per-tab "Select all / Clear" header controls — not as a separate sticky row in the editor.
- **D-09:** Channels already in the session are **hidden** from the picker. Tab counts reflect remaining channels (`Inputs (24 available)`).
- **D-10:** New tracks **append to the end** of the track list in the order they appear in the picker.
- **D-11:** The Manual tab is a small inline form: `Label` (required, max 100), `Color` (optional swatch), `Notes` (optional). "+ Add another" queues multiple manual tracks before applying.

**Session Lifecycle**

- **D-12:** A newly-created `MultitrackSession` lands in the editor with **zero tracks** and the picker auto-opened on the Inputs tab.
- **D-13:** Spec correction — `MultitrackSession.console` is a `ForeignKey` to `planner.Console`, **not** to `Device(category='console')`.

**Resolution Helpers (D-11 prerequisite)**

- **D-14:** Add Python helpers on `MultitrackTrack`: `resolved_source`, `resolved_label`, `resolved_color`, `resolved_dante_number`.

### Claude's Discretion

The planner / executor decides these — defaults to existing project patterns:

- **JS stack** for the track editor — already locked by UI-SPEC: jQuery + vendored Sortable.js 1.15.x in `planner/static/planner/js/vendor/Sortable.min.js`.
- **Session creation flow** — already locked by UI-SPEC: single Django form (NOT a 4-step wizard); justification in UI-SPEC § "+ New Session" Flow.
- **Reaper `.RPP` color packing** — confirm exact bit layout against Reaper docs / a real `.RPP` fixture. *(This research answers it — see § "Reaper `.RPP` Format Facts" below.)*
- **Capacity bar placement** — UI-SPEC has placed it in the editor toolbar between the title bar and the track list (NOT sticky). No further decision needed.
- **Track number gap handling** — UI-SPEC locks dense renumber on every reorder save (`1..N`).
- **Picker URL form** — UI-SPEC locks same-page modal (vanilla CSS overlay), no separate page.
- **Indexing** on `MultitrackTrack(source_type, source_id)` — recommended (see § "Don't Hand-Roll").

### Deferred Ideas (OUT OF SCOPE)

- Group Output / FX Return / Cue Output as first-class models with their own admins, CSV import, and `MultitrackTrack.source_type` values — best home is v2.1 alongside Pro Tools work.
- Channel-level color storage on the four existing channel models — revisit during Phase 2 CSV import.
- Default-color seed inheritance from a channel-level `default_record_color` — already POL-02 (Phase 5).
- Pre-populated session presets — explicitly rejected for v2.0 to keep manual tab simple.
- `MultitrackTemplate` — Phase 3.
- Pro Tools `.txt` / AAF exporter — PT-01, deferred to v2.1.
- M7CL channel import — M7CL-01, deferred to v2.1.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MTS-01 | Create MultitrackSession (console, target_daw, feed_source, track_order_mode) | Single-form pattern (UI-SPEC § "+ New Session"); use `BaseEquipmentAdmin.save_model` precedent for auto-assigning `project` from `request.current_project` (admin.py:98) |
| MTS-02 | Name session, rename, unique per project | `unique_together = [('project', 'name')]` matches `AudioChecklistTemplate` precedent (models.py:3662) |
| MTS-03 | List sessions for current project, create/duplicate/delete | Follows `comm_config_view` list-and-editor dual-mode pattern (views.py:1882) |
| MTS-04 | Edit session metadata without losing tracks | Plain Django change form; `BaseEquipmentAdmin` already excludes `project` field on edit (admin.py:129) |
| MTS-05 | Delete session and its tracks | `on_delete=CASCADE` on `MultitrackTrack.session` FK |
| MTS-06 | Duplicate session into new one | New view that copies session + iterates tracks; modal pattern from UI-SPEC |
| TRK-01 | Show track list with metadata | Editor template with rendered table — renders `resolved_label` / `resolved_color` helpers (D-14) |
| TRK-02 | Enable/disable tracks; only enabled appear in exports | `MultitrackTrack.enabled = BooleanField(default=True)`; exporter filters `tracks.filter(enabled=True)` |
| TRK-03 | Override track label | `label_override = CharField(max_length=100, blank=True)`; resolved_label helper from D-14 |
| TRK-04 | Override track color via swatch picker | `color_override = CharField(max_length=7, blank=True)`; UI-SPEC § "Inline Color Picker" defines 12-color palette + custom hex |
| TRK-05 | Drag-reorder tracks; order persists | Sortable.js 1.15.7 vendored locally; `onEnd` POSTs ordered list of IDs to `/reorder/` endpoint, server reassigns dense `track_number` 1..N |
| TRK-06 | Add track from any channel type | Modal picker with 5 tabs (UI-SPEC § "Channel Picker Modal") |
| TRK-07 | Add manual track with no source | Manual tab in picker (D-11); creates `MultitrackTrack(source_type='manual', source_id=NULL)` |
| TRK-08 | Remove track from session | `[×]` button per row; one-click no confirmation (UI-SPEC § "Destructive Confirmations"); does NOT cascade to source channel — `MultitrackTrack` has no FK to channel models (D-01) |
| TRK-09 | Bulk include/exclude all Aux/Matrix/Group | UI-SPEC overrides spec wording — bulk toggles live in picker as Select-all/Clear per tab (D-08); editor has NO top-level toggles |
| TRK-10 | Capacity count vs `recorder_capacity`; over-capacity red but does not block export | `MultitrackSession.recorder_capacity = PositiveIntegerField(null=True, blank=True)`; UI-SPEC § "Capacity bar states" defines color rules |
| RPP-01 | Export `.RPP` with one track per enabled MultitrackTrack | See § "Reaper `.RPP` Format Facts" — minimal `<REAPER_PROJECT ...>` header + N `<TRACK ...>` blocks |
| RPP-02 | Track names match resolved labels | `NAME` token inside each TRACK block; quote-wrap if label contains spaces |
| RPP-03 | Track colors match resolved colors → packed RGB | `PEAKCOL <int>` where int = `0x01000000 \| (B<<16) \| (G<<8) \| R` — see § "Reaper Color Packing" for byte order verification |
| RPP-04 | Track order matches `track_order_mode` | See § "Track Order Modes Explained" — exporter sorts by source channel ascending (`channel`), `resolved_dante_number` (`dante`), or `track_number` (`custom`) before writing |
| RPP-05 | Export `.RTrackTemplate` (track-list only) | Same syntax as `.RPP` but no `REAPER_PROJECT` wrapper — just N back-to-back `<TRACK ...>` blocks. Verified against real fixture (LASS-2 templates) |
</phase_requirements>

---

## Project Constraints (from CLAUDE.md)

These are non-negotiable and the planner must produce tasks that comply:

1. **Beta-safe migrations.** No `ALTER TABLE` against `ConsoleInput` / `ConsoleAuxOutput` / `ConsoleMatrixOutput` / `ConsoleStereoOutput`, and no destructive operations against Railway Postgres without confirming with Charlie. Phase 1 migrations create new tables only.
2. **`showstack_admin_site` registration.** Any new ModelAdmin MUST be registered on `showstack_admin_site` (`planner/admin_site.py:209`) — NEVER on `admin.site`. (CLAUDE.md § Architecture > Custom admin site.)
3. **`admin_ordering.py` MUST be updated** when a new admin-registered model is added. Add `multitracksession` (and `multitracktrack` if registered) to the `order_map` in `planner/admin_ordering.py:79-151`. (CLAUDE.md § Architecture > Custom admin site.)
4. **`CurrentProjectMiddleware` is the project-scoping mechanism.** Views read `request.current_project` and filter querysets — do not introduce URL-based project IDs. (CLAUDE.md § Session-based project resolution.)
5. **`BaseEquipmentAdmin` for role perms.** New ModelAdmin classes that need editor/viewer/owner role filtering should subclass `BaseEquipmentAdmin` (`planner/admin.py:77`). Its `save_model` auto-assigns `project = request.current_project` (admin.py:98).
6. **`railway.json` startCommand is the active deploy script** — not the Procfile. New management commands or build steps go in `railway.json`'s `startCommand`. Phase 1 likely doesn't add deploy steps but the planner should not assume Procfile edits propagate.
7. **`!important` CSS override pattern.** Direct `el.style.color = value` will silently fail in admin templates because Django admin styles use `!important` pervasively. JS must use `el.style.setProperty('color', value, 'important')`. (CLAUDE.md § Coding Conventions; UI-SPEC § Design System.)
8. **Templates extend `admin/base_site.html`** for the dark theme (precedent: every existing `templates/planner/*.html`).
9. **Static files via Whitenoise + `collectstatic`.** Place new JS/CSS in `planner/static/planner/...`. Sortable.js is vendored — no CDN. (CLAUDE.md § Tech Stack.)
10. **Solo-dev deploy.** Push to `main` triggers Railway redeploy. Use feature branches only when work is risky or spans multiple sessions. Phase 1 spans many tasks but the project's `branching_strategy` is `none` (`.planning/config.json`).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Session list + dashboard | Django view + template (server-rendered) | — | Matches `comm_config_view` and Mic Tracker — server-rendered pages with minimal JS interactivity |
| Session create form | Django view + Django Form / ModelForm | — | Single-form pattern (UI-SPEC); CSRF + validation handled by Django |
| Track editor page render | Django view + template | — | Server-rendered initial state; JS only for drag/picker/reorder/swatch interactions |
| Drag-reorder persistence | Django view (AJAX endpoint) | jQuery + Sortable.js (browser) | Sortable.js handles drag UX in browser; XHR `POST` returns JSON; server reassigns dense `track_number` |
| Channel picker modal | Browser (vanilla CSS modal + jQuery) | Django view (initial channel list embedded as JSON or fetched via XHR) | Modal is a browser concern; data flows from server-rendered context — match `comm_config.html`'s pattern of seeding JS state from Django context |
| Color swatch picker | Browser (vanilla popover) | Django view (PATCH endpoint for `color_override`) | Popover UX is purely client-side; one XHR call per change |
| Reaper `.RPP` / `.RTrackTemplate` generation | Django view (file download) | `planner/utils/reaper_export.py` helper | Pure server work — generates a string, returns `HttpResponse` with `Content-Disposition: attachment` |
| Orphan-conversion on channel delete | Django `post_delete` signal (server-side) | — | Cannot be a DB constraint (D-01 says no FK); must be Python-side, registered in `planner/signals.py` |
| Project scoping | `CurrentProjectMiddleware` (already in place) | — | All views read `request.current_project` (CLAUDE.md non-negotiable) |
| Role permissions on admins | `BaseEquipmentAdmin` (already in place) | — | New `MultitrackSessionAdmin` subclasses it |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Django | 5.x (project's pinned version) | Models, views, admin, forms, signals | Project's framework — non-negotiable [VERIFIED: CLAUDE.md] |
| jQuery | bundled by Django admin | DOM, AJAX, event handling | Already loaded by `admin/base_site.html`; existing modules use it (`comm_admin.js`, `pa_cable_calculations.js`, `mono_stereo_handler.js`) [VERIFIED: codebase grep] |
| Sortable.js | 1.15.7 (vendored, MIT) | Drag-reorder track list (TRK-05) | UI-SPEC locks vendoring to `planner/static/planner/js/vendor/Sortable.min.js`. 1.15.7 is the latest 1.15.x; download URL: `https://registry.npmjs.org/sortablejs/-/sortablejs-1.15.7.tgz` [VERIFIED: npm registry 2026-05-09] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `django.http.HttpResponse` | stdlib (Django) | Stream `.RPP` and `.RTrackTemplate` file downloads | Mirror `yamaha_export.py:28` — set `content_type='text/plain'` (or `application/octet-stream`) and `Content-Disposition: attachment; filename="..."` |
| `django.dispatch.receiver` + `post_delete` | stdlib (Django) | D-04 orphan conversion when channels are deleted | Add to `planner/signals.py` (already exists); registered via `apps.py:ready()` [VERIFIED: planner/signals.py + planner/apps.py] |
| `django.contrib.admin.views.decorators.staff_member_required` | stdlib (Django) | View access control | Used on every comparable view (`comm_config_view`, `mic_tracker_view`, etc.) [VERIFIED: views.py grep] |
| `django.views.decorators.http.require_POST` | stdlib (Django) | AJAX endpoint enforcement | Used on `bulk_update_mics`, `comm_config_*` mutate endpoints [VERIFIED: views.py grep] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Sortable.js | jQuery UI sortable | UI-SPEC has already chosen Sortable.js. jQuery UI sortable is heavier, has an older codebase, and adds another dependency. Skip. |
| `post_delete` signal | DB-level FK with `SET_NULL` and a separate "snapshot last known label" cron | D-01 explicitly forbids the FK because a CASCADE risk exists for beta data. Signal is the only path. |
| Single Django form for session create | 4-step wizard (per spec) | UI-SPEC has already chosen single form for parity with Comm Config / Mic Tracker. Skip wizard. |
| `planner/utils/reaper_export/` submodule | `planner/utils/reaper_export.py` standalone file | The Reaper exporter is small (one `.RPP` generator + one `.RTrackTemplate` generator); standalone matches `yamaha_export.py` precedent better than the multi-file `pdf_exports/` pattern. Use the file unless the file grows past ~400 lines, in which case split. |

**Installation:**
```bash
# Sortable.js — download once, commit to repo. No npm/pip install.
curl -L "https://registry.npmjs.org/sortablejs/-/sortablejs-1.15.7.tgz" -o /tmp/sortable.tgz
tar -xzf /tmp/sortable.tgz -C /tmp
cp /tmp/package/Sortable.min.js planner/static/planner/js/vendor/Sortable.min.js
git add planner/static/planner/js/vendor/Sortable.min.js
```

**Version verification:** Confirmed via `https://registry.npmjs.org/sortablejs/latest` on 2026-05-09 — version `1.15.7`, license `MIT`, homepage `https://github.com/SortableJS/Sortable#readme`. [VERIFIED: npm registry]

---

## Architecture Patterns

### System Architecture Diagram

```
                        ┌──────────────────────────────────────┐
                        │  Browser (engineer)                  │
                        │  ┌─────────────┐  ┌──────────────┐  │
                        │  │ Editor page │  │ Picker modal │  │
                        │  │ Sortable.js │  │ jQuery       │  │
                        │  └──────┬──────┘  └───────┬──────┘  │
                        └─────────┼─────────────────┼─────────┘
                                  │ XHR (CSRF)      │ XHR
                                  ↓                 ↓
              ┌───────────────────────────────────────────────────────┐
              │  Django views.py (project-scoped via                  │
              │  request.current_project from CurrentProjectMiddleware)│
              │  ┌───────────────┐  ┌──────────────────┐              │
              │  │ session list  │  │ session editor   │              │
              │  │ + create      │  │ + AJAX endpoints │              │
              │  └───────┬───────┘  └────────┬─────────┘              │
              │          │                   │                        │
              │  ┌───────┴───────────────────┴──────────────┐         │
              │  │ MultitrackSession ORM (new table)        │         │
              │  │   ├── tracks (FK reverse)                │         │
              │  │   └── console (FK → planner.Console)     │         │
              │  │ MultitrackTrack ORM (new table)          │         │
              │  │   ├── source_type, source_id (no FK)     │         │
              │  │   └── resolved_*() helpers (D-14)        │         │
              │  └───────┬───────────────────┬──────────────┘         │
              │          │                   │                        │
              │  ┌───────┴────────┐  ┌───────┴──────────────┐         │
              │  │ Existing       │  │ planner.signals      │         │
              │  │ Console family │←─│  post_delete on the  │         │
              │  │ (read-only for │  │  4 channel models →  │         │
              │  │ Phase 1)       │  │  convert orphan      │         │
              │  └────────────────┘  │  MultitrackTracks to │         │
              │                      │  manual (D-04)       │         │
              │                      └──────────────────────┘         │
              │  ┌────────────────────────────────────┐               │
              │  │ planner.utils.reaper_export        │               │
              │  │   build_rpp(session) → str         │               │
              │  │   build_rtracktemplate(session)→str│               │
              │  │   yamaha_to_reaper_color() helper  │               │
              │  └────────────┬───────────────────────┘               │
              │               │                                       │
              │               ↓                                       │
              │  HttpResponse(content_type="text/plain",              │
              │               Content-Disposition="attachment;        │
              │                                  filename=...rpp")    │
              └──────────────────────────────────────┬────────────────┘
                                                     │
                                                     ↓ download
                                              Engineer's machine
                                                     │
                                                     ↓ open in
                                              REAPER (DAW)
```

The exporter is offline-only — no calls to REAPER's runtime API, no platform-specific color handling needed (the RPP file format is cross-platform; platform differences only apply to the live API).

### Recommended Project Structure

```
planner/
├── models.py                         # Append MultitrackSession, MultitrackTrack near line 911 (after Console family, before Device)
├── admin.py                          # Append MultitrackSessionAdmin (and MultitrackTrackAdmin if exposed)
├── admin_site.py                     # Already provides showstack_admin_site — no change
├── admin_ordering.py                 # MUST update order_map to include 'multitracksession' (and 'multitracktrack' if registered)
├── views.py                          # Append multitrack_dashboard, multitrack_editor, multitrack_create, multitrack_reorder, multitrack_add_tracks, multitrack_export_rpp, multitrack_export_rtracktemplate, multitrack_duplicate
├── urls.py                           # Append paths under /audiopatch/multitrack/...
├── signals.py                        # Append post_delete receivers for the 4 channel models (D-04 orphan conversion)
├── forms.py                          # Append MultitrackSessionForm (the Django form for session create/edit)
├── utils/
│   └── reaper_export.py              # NEW — Reaper .RPP and .RTrackTemplate generators + Yamaha→Reaper color mapping
├── static/
│   └── planner/
│       ├── js/
│       │   ├── multitrack_editor.js  # NEW — Sortable.js init, picker modal, swatch picker
│       │   └── vendor/
│       │       └── Sortable.min.js   # NEW — vendored Sortable.js 1.15.7 (MIT)
│       └── css/                      # (existing)
└── migrations/
    └── 0XXX_multitrack_session_track.py  # NEW — additive only, two new tables

templates/
└── planner/
    ├── multitrack_dashboard.html     # NEW — session list + empty state
    ├── multitrack_editor.html        # NEW — track table + picker modal + swatch popover
    └── multitrack_session_form.html  # NEW — session create / edit form
```

### Pattern 1: Project-Scoped Module View (mirrors `comm_config_view`)

**What:** A single view function with two modes — list (when no `id`) and editor (when `id` provided). Both modes filter by `request.current_project`.

**When to use:** Any new module landing page that has a list-and-edit lifecycle.

**Example (verbatim from `planner/views.py:1882-1910`):**

```python
@staff_member_required
def comm_config_view(request, config_id=None):
    current_project = getattr(request, 'current_project', None)

    # List of configs for this project
    configs = CommConfig.objects.filter(
        project=current_project
    ).order_by('created_at') if current_project else CommConfig.objects.none()

    config = None
    # ... per-record state ...

    if config_id:
        config = CommConfig.objects.filter(id=config_id, project=current_project).first()
        if not config:
            from django.shortcuts import redirect
            return redirect("planner:comm_config")
        # ... load related rows ...
```

**Key pattern points:**
- `getattr(request, 'current_project', None)` — defensive, mirror this
- `Project.objects.none()` when no current project — never raise; never leak across projects
- `filter(id=config_id, project=current_project).first()` — combined filter prevents IDOR
- Redirect (not 404) when the record is missing for the current project

### Pattern 2: AJAX Mutate Endpoint (mirrors `comm_config_create`)

**What:** A JSON-in / JSON-out POST endpoint reading `request.current_project` for project assignment.

**When to use:** Any endpoint the JS calls (drag-reorder save, color override, label override, picker commit).

**Example (verbatim from `planner/views.py:3754-3777`):**

```python
def comm_config_create(request):
    try:
        data = _json.loads(request.body)
        device_type = data.get('device_type', 'arcadia')
        current_project = getattr(request, 'current_project', None)
        if not current_project:
            return JsonResponse({'error': 'No active project'}, status=400)

        name = data.get('name', '').strip() or f"New {device_type.title()} Config"
        config = CommConfig.objects.create(
            project=current_project,
            name=name,
            device_type=device_type,
        )
        # ... seed defaults ...
        return JsonResponse({'ok': True, 'config_id': config.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
```

**CSRF handling on the JS side** (verbatim from `templates/planner/comm_config.html:1149-1157`):

```javascript
function saveLanField(lanId, field, value) {
  const payload = { lan_id: lanId };
  payload[field] = value;
  fetch('{% url "planner:comm_config_update_lan" %}', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
    body: JSON.stringify(payload),
  });
}
```

**Note:** `getCookie('csrftoken')` is a helper expected to be defined in the same template — Django doesn't ship one. Look for it in `comm_config.html` or copy a standard implementation (Django docs ship one under "Using CSRF").

### Pattern 3: Modal Overlay (mirrors the Help modal in `admin/base_site.html`)

**What:** A `display:none` div positioned `fixed; inset:0; background:rgba(0,0,0,0.6); z-index:99999;` containing a centered panel.

**When to use:** Channel picker, duplicate-session modal, save-template-name prompt.

**Example (paraphrased from `templates/admin/base_site.html:138`):**

```html
<div id="picker-overlay" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.6); z-index:99999; align-items:center; justify-content:center;">
  <div class="mts-modal-panel" style="background:#1a1a1a; border:1px solid #333; border-radius:10px; width:720px; max-width:95vw; max-height:85vh; display:flex; flex-direction:column; overflow:hidden;">
    <!-- Modal header with title + × close button -->
    <!-- Tabs row -->
    <!-- Filter input -->
    <!-- Active tab content (scrollable) -->
    <!-- Footer with Add N selected + Cancel -->
  </div>
</div>
```

**Open/close pattern (from `comm_config.html:1192-1212`):**

```javascript
function openPicker() {
  document.getElementById('picker-overlay').style.display = 'flex';
  setTimeout(() => document.getElementById('picker-filter-input').focus(), 100);
}
function closePicker() {
  document.getElementById('picker-overlay').style.display = 'none';
}
// Escape key to close (matches help modal at base_site.html:547):
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closePicker();
});
```

### Pattern 4: `post_delete` Signal Idempotency (mirrors `ensure_user_profile`)

**What:** Use try/except for race conditions; signals can fire multiple times during admin/test/migration paths.

**When to use:** D-04 orphan conversion on the four channel models.

**Example (verbatim from `planner/signals.py:8-27`):**

```python
@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """
    Ensure UserProfile exists for every user.
    Uses try/except to handle race conditions when Django admin
    saves the User object multiple times during creation.
    """
    try:
        profile = UserProfile.objects.get(user=instance)
    except UserProfile.DoesNotExist:
        try:
            profile = UserProfile.objects.create(...)
        except IntegrityError:
            profile = UserProfile.objects.get(user=instance)
```

**For Phase 1, register four `post_delete` receivers** (one per channel model). The handler:
1. Computes the snapshot label/color from the instance being deleted (the instance is still hydrated in the receiver).
2. Updates all matching `MultitrackTrack` rows in a single `UPDATE` (`.filter(source_type=X, source_id=instance.pk).update(...)`) to avoid N+1 and avoid re-firing the signal chain.

```python
# planner/signals.py — append to existing file
from django.db.models.signals import post_delete
from .models import (
    ConsoleInput, ConsoleAuxOutput, ConsoleMatrixOutput, ConsoleStereoOutput,
    MultitrackTrack,
)

def _convert_orphans_to_manual(source_type, source_id, snapshot_label, snapshot_color=''):
    """D-04: Convert orphan tracks to manual on channel deletion."""
    orphans = MultitrackTrack.objects.filter(source_type=source_type, source_id=source_id)
    for track in orphans:
        track.label_override = track.label_override or snapshot_label
        track.color_override = track.color_override or snapshot_color
        track.source_type = 'manual'
        track.source_id = None
        track.save(update_fields=['label_override', 'color_override', 'source_type', 'source_id'])

@receiver(post_delete, sender=ConsoleInput)
def consoleinput_to_manual(sender, instance, **kwargs):
    label = instance.source or instance.input_ch or instance.dante_number or '(deleted input)'
    _convert_orphans_to_manual('input', instance.pk, label)

@receiver(post_delete, sender=ConsoleAuxOutput)
def consoleauxoutput_to_manual(sender, instance, **kwargs):
    label = instance.name or f'Aux {instance.aux_number}'
    _convert_orphans_to_manual('aux', instance.pk, label)

@receiver(post_delete, sender=ConsoleMatrixOutput)
def consolematrixoutput_to_manual(sender, instance, **kwargs):
    label = instance.name or f'Matrix {instance.matrix_number}'
    _convert_orphans_to_manual('matrix', instance.pk, label)

@receiver(post_delete, sender=ConsoleStereoOutput)
def consolestereooutput_to_manual(sender, instance, **kwargs):
    label = instance.name or instance.get_stereo_type_display()
    _convert_orphans_to_manual('stereo', instance.pk, label)
```

**Registration:** Already wired — `planner/apps.py:13` imports `planner.signals` from `ready()`. New receivers in the same file just work. [VERIFIED: planner/apps.py]

**Re-entrancy safety:** Loop with `.save(update_fields=...)` (not `.update()`) so each row goes through `MultitrackTrack.save()` — but since `MultitrackTrack` has no `pre_save` / `post_save` receivers in Phase 1, there's no signal cascade. Bulk `.update()` is also safe (it bypasses signals entirely).

**Migration safety:** `post_delete` does NOT fire during forward migrations that delete rows via SQL. It only fires when the ORM's `.delete()` is called. Beta-tester data is safe — the existing migrations don't delete channel rows.

### Anti-Patterns to Avoid

- **Direct `el.style.color = value`** — silently fails because Django admin uses `!important`. Use `el.style.setProperty('color', value, 'important')`. (CLAUDE.md.)
- **`admin.site.register(...)`** — must use `showstack_admin_site.register(...)`. (CLAUDE.md, admin_site.py.)
- **URL-based project IDs** — never include `<int:project_id>/` in URLs. The middleware is the source of truth. (CLAUDE.md, middleware.py.)
- **CDN-loaded Sortable.js** — UI-SPEC explicitly forbids. Vendor it.
- **Forgetting `admin_ordering.py`** — new admin model not added to `order_map` will sort to position 999 (end of sidebar). (admin_ordering.py:140.)
- **Synthesizing the `.RPP` from scratch with every Reaper token** — minimum viable token set is much smaller than a Reaper-saved file. See § "Minimal RPP Skeleton."
- **Forgetting `Content-Disposition: attachment`** — without it, the browser tries to render the file inline.
- **Counting "available" channels by querying the four channel tables for each tab on every keystroke** — pre-compute once at picker open per UI-SPEC § "Tab counts" rule.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Drag-and-drop list reorder | A custom `mousedown` / `mousemove` / `mouseup` handler with placeholder element synthesis | Sortable.js 1.15.7 (vendored locally) | Touch events, Shadow DOM weirdness, scroll-while-dragging, ghost elements, animation easing, keyboard accessibility — all correctly handled by Sortable.js. UI-SPEC has already chosen it. |
| Hex-to-Reaper-int color conversion | A handful of bit-shifts inline in views.py | Single helper in `planner/utils/reaper_export.py`: `def hex_to_peakcol(hex_str: str) -> int` | One canonical source for the bit math. Phase 4 (Nuendo Live) and Phase 2 (CSV color import) will both need this. |
| Modal overlay + focus trap + escape-to-close | Custom CSS positioning logic | Reuse the help-modal CSS pattern in `templates/admin/base_site.html:138-180` | Already styled to match the dark theme; already accessibility-tested by users. |
| `MultitrackTrack.source_type` discriminator → model class lookup | Chain of `if source_type == 'input': ... elif ... elif`s in every helper | One module-level dict `SOURCE_TYPE_MODEL_MAP = {'input': ConsoleInput, 'aux': ConsoleAuxOutput, ...}` and one `resolved_source(self)` helper that does `model.objects.filter(pk=self.source_id).first()` | DRY; one place to update when v2.1 adds Group / FX Return / Cue Output (D-03 deferred). |
| Renumbering tracks `1..N` after every reorder | Re-saving every track in a loop with the new number | One bulk update with a `Case`/`When` expression OR a simple `for idx, track in enumerate(ordered, start=1): track.track_number = idx` followed by `MultitrackTrack.objects.bulk_update(tracks, ['track_number'])` | `bulk_update` is one SQL statement; loop-and-save is N statements. The former is the standard Django idiom. |
| CSV-style escaping inside RPP `NAME` token | Inventing escape rules | Wrap in double-quotes (`NAME "Kick In L"`) and replace any internal `"` with the documented Reaper escape (Reaper accepts `"` literally inside backtick-quoted strings, or just sanitize to single-quotes / strip) | Standard Reaper format convention. The `audio-file-x4.RPP` fixture above uses `NAME kick` (no quotes) for unquoted single-word labels, and other fixtures show `NAME "..."` for spaces — quote when needed. |
| GUID generation per track | Custom random hex | `uuid.uuid4()` formatted as `{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}` (uppercase, brace-wrapped) — exactly the format Reaper uses | Reaper accepts any well-formed GUID; reusing Python stdlib is one line and zero risk. |

**Key insight:** The hand-roll surface in this phase is small because most of the heavy lifting (drag, modal, project scoping, role perms, dark theme, admin registration) is already handled by libraries or existing project infrastructure. The genuine new code is: two model classes, four signal handlers, ~6 view functions, ~3 templates, one JS file, one Reaper exporter helper.

---

## Reaper `.RPP` Format Facts

This section answers RPP-01..RPP-05 with citations from real fixtures and SDK docs. Confidence: HIGH.

### Plain-Text, Line-Oriented Format

A `.RPP` is plain ASCII (UTF-8 safe), Unix or Windows line endings both accepted by Reaper. Structure is nested `<...>` blocks and inline `KEY value` lines. Comments are not supported in production files.

### Minimal RPP Skeleton (RPP-01)

Verified working minimum from `audio-file-x4.RPP` and `send-receive.RPP` (CharlesHolbrow/rppp examples). The structure is:

```
<REAPER_PROJECT 0.1 "7.0/macOS-arm64" 1730000000
  RIPPLE 0
  GROUPOVERRIDE 0 0 0
  AUTOXFADE 1
  TEMPO 120 4 4
  SAMPLERATE 48000 0 0
  <TRACK {DA2D209F-D10F-5E46-93E7-098D96499ED0}
    NAME "Kick In"
    PEAKCOL 16576
    TRACKHEIGHT 0 0 0
    NCHAN 2
    TRACKID {DA2D209F-D10F-5E46-93E7-098D96499ED0}
    MAINSEND 1 0
  >
  <TRACK {ABCD1234-...}
    NAME "Kick Out"
    PEAKCOL 33619968
    TRACKHEIGHT 0 0 0
    NCHAN 2
    TRACKID {ABCD1234-...}
    MAINSEND 1 0
  >
>
```

[CITED: github.com/CharlesHolbrow/rppp/master/rpp-examples/audio-file-x4.RPP — fetched 2026-05-09]

**Header line breakdown** (`<REAPER_PROJECT 0.1 "7.0/macOS-arm64" 1730000000`):
- `0.1` — file format version (use `0.1` — it's what real Reaper writes)
- `"7.0/macOS-arm64"` — Reaper version + platform string. Recommend a fixed string like `"7.0/AudiopatchExporter"` so the file identifies itself; Reaper does not validate this. [ASSUMED — Reaper's tolerance of arbitrary strings here]
- `1730000000` — Unix timestamp of save. Use `int(time.time())` at export time.

**Required tokens inside each `<TRACK ...>` block** (verified by minimal LASS-2 RTrackTemplate):
- `NAME "..."` — the track name; quote-wrap if it contains spaces/punctuation
- `PEAKCOL <int>` — color (see § "Reaper Color Packing")
- `TRACKHEIGHT 0 0 0` — height in TCP, folder collapse flag, padding (use `0 0 0` for default)
- `NCHAN 2` — number of channels (2 = stereo, 1 = mono); for multitrack-recording sessions stereo is the safe default
- `TRACKID {GUID}` — same GUID as the `<TRACK {GUID}` opener; use `uuid.uuid4()`
- `MAINSEND 1 0` — route to master (1 = on, 0 = no parent send). Without this, the track may not have audible playback.

**Optional but useful tokens** (omit if not needed):
- `MUTESOLO 0 0 0` — mute, solo, sip
- `IPHASE 0` — phase invert
- `VOLPAN 1 0 -1 -1 1` — vol, pan, faderPan, faderVol, mode
- `BUSCOMP 0 0 0 0 0` — bus compressor
- `SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0` — visibility settings
- `REC 0 0 1 0 0 0 0` — recording mode/source flags
- `ISBUS 0 0` — folder/bus marker (0 0 = regular track)
- `FX 1` — FX chain enabled
- `BEAT -1` — beat handling (-1 = auto)

**Strategy for the planner:** start the implementation with the minimal token set above; add optional tokens only if smoke testing in Reaper reveals issues. Real Reaper-saved files contain ~20 tokens per track; an exporter that writes only the 6 required tokens above produces a file that opens cleanly. [VERIFIED: LASS-2 RTrackTemplate uses ~22 tokens but tracks open fine with fewer.]

### `.RTrackTemplate` Format (RPP-05)

Verified by downloading `LASS - Basses Full.RTrackTemplate` from the Reaper-Track-Templates org (2026-05-09):

> **`.RTrackTemplate` files start directly with `<TRACK` — no `<REAPER_PROJECT ...>` wrapper.**

Each template is a series of back-to-back `<TRACK ...>` blocks. Same syntax inside the blocks. To export an `.RTrackTemplate`, the exporter generates the same per-track output it generates for `.RPP`, but skips the project-level header and footer (`<REAPER_PROJECT ...>` open and matching `>`).

```
<TRACK
  NAME "Kick In"
  PEAKCOL 30310924
  ...
  TRACKID {GUID}
  MAINSEND 1 0
>
<TRACK
  NAME "Kick Out"
  ...
>
```

**Note:** Real LASS-2 `.RTrackTemplate` files use `<TRACK` with no GUID immediately after the tag (the `TRACKID` is inside). RPP files in the rppp examples use `<TRACK {GUID}` with the GUID on the open tag. Both forms work. Recommend the planner use the explicit `<TRACK {GUID}` form for both `.RPP` and `.RTrackTemplate` for consistency.

[CITED: github.com/Reaper-Track-Templates/LASS-2/master/LASS%20-%20Basses%20Full.RTrackTemplate — fetched 2026-05-09]

### Reaper Color Packing (RPP-03)

**Bit layout** (cross-platform — same in the file regardless of OS):

```
PEAKCOL = 0x01000000 | (B << 16) | (G << 8) | R
```

- Low byte = R (red 0–255)
- Middle byte = G (green 0–255)
- High byte (of the 24 RGB bits) = B (blue 0–255)
- Bit 24 (`0x01000000` = 16777216 decimal) = "custom color enabled" flag

**Verification:**
1. JSFX docs: "color is packed RGB (0..255), i.e. red+green*256+blue*65536" [CITED: reaper.fm/sdk/js/gfx.php]
2. ReaperToolkit docs: "a 24-bit packed integer holding red in the low byte and blue in the high byte" [CITED: reapertoolkit.dev/module/color.html]
3. SWS Color.cpp: `int iWhite = 0x1000000 | RGB(255, 255, 255);` (where Windows `RGB()` macro packs as `R | G<<8 | B<<16`) [CITED: github.com/reaper-oss/sws/master/Color/Color.cpp]
4. X-Raym ReaScript: `color_int = reaper.ColorToNative(R, G, B) | 0x1000000` with comment "doesn't display the color in the arrange without it" [CITED: github.com/X-Raym/REAPER-ReaScripts/master/Color/X-Raym_Set%20selected%20tracks%20and%20takes%20color%20from%20HEX%20value.lua]
5. Real-world fixtures: LASS-2 RTrackTemplate has `PEAKCOL 30310924` = `0x01CE470C` → R=0x0C (12), G=0x47 (71), B=0xCE (206) = blue-purple. `PEAKCOL 31561399` = `0x01E18077` → R=0x77 (119), G=0x80 (128), B=0xE1 (225) = teal-blue. Both decode plausibly as string-section template colors.

**Special value `16576`** — this is the default value Reaper writes for `PEAKCOL` and `MASTERPEAKCOL` when no custom color is set. `16576 = 0x4080`. The high `0x01000000` bit is NOT set, indicating "no custom color." The remaining bits (`0x4080`) are an internal Reaper default; do not interpret as RGB.

[CITED: github.com/ReaTeam/Doc/blob/master/State%20Chunk%20Definitions: "PEAKCOL 16576 // Peak colour... 16576 is the default value to be returned by GetMediaTrackInfo_Value() function with 'I_CUSTOMCOLOR' attribute when no custom track color has been applied"]

**Mapping decision (RPP-03 implementation):**
```python
def hex_to_peakcol(hex_color: str) -> int:
    """
    Convert '#RRGGBB' to a Reaper PEAKCOL int.
    Returns 16576 (the Reaper "no custom color" default) if hex_color is empty/None.
    """
    if not hex_color:
        return 16576
    h = hex_color.lstrip('#')
    if len(h) != 6:
        return 16576
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return 0x01000000 | (b << 16) | (g << 8) | r
```

Alternative: omit the `PEAKCOL` line entirely when no color is set — Reaper accepts both forms. Writing `16576` is more explicit and matches what real Reaper-saved files do.

### Track Order Modes Explained (RPP-04)

The `MultitrackSession.track_order_mode` field has three values that affect both editor display order and export order:

| Mode | Editor display order | Export order | How |
|------|----------------------|--------------|-----|
| `channel` | By source channel number ascending; manual tracks last (sorted by `track_number`) | Same as editor | At read time, order tracks by `(source_type_priority, source_channel_number)` where input < aux < matrix < stereo < manual; within each type, by the source channel's natural number field |
| `dante` | By `resolved_dante_number` ascending (across all source types); manual tracks last | Same | At read time, order by `resolved_dante_number` (helper from D-14) — channels without a dante number sort last |
| `custom` | By `track_number` ascending (engineer's drag order) | Same | Default — `MultitrackTrack.Meta.ordering = ['track_number']` — no reordering on read |

**Manual tracks** never have a source channel and never have a dante number. Place them at the end of the list in `track_number` order regardless of `track_order_mode`. UI-SPEC's track-row layout shows manual tracks have `[MANUAL]` badge — there's no source-name fallback to sort by.

**Open question (Claude's discretion — not blocking):** When `track_order_mode='custom'` and the engineer drags a track, do we update `track_number` immediately, or do we keep `track_number` purely as a "custom-mode display order" field? Recommend: `track_number` is always the dense `1..N` reorder index. In `channel` and `dante` modes, the editor displays in computed order but `track_number` underlying remains as the engineer's last drag order. Switching modes never silently mutates stored data.

### Yamaha → Reaper Color Mapping

The Yamaha CL/QL palette has 10 named colors. Reaper accepts any 24-bit RGB. Recommend a constant module-level table:

```python
# planner/utils/reaper_export.py
YAMAHA_TO_HEX = {
    'Off':      None,        # → omit PEAKCOL or write 16576
    'Red':      '#FF0000',
    'Orange':   '#FF8800',
    'Yellow':   '#FFDD00',
    'Green':    '#33CC33',
    'Sky Blue': '#00BBDD',
    'Blue':     '#3366FF',
    'Purple':   '#9933FF',
    'Pink':     '#FF33AA',
    'White':    None,        # → use DAW default
}
```

These hex values match the 12-color palette in UI-SPEC § "Inline Color Picker" (where applicable). Engineers will tune the mapping over time; keep the table in one module-level constant. Phase 1 doesn't have a Yamaha→Reaper conversion path since channel-level Yamaha colors don't exist until Phase 2 imports them — but the **table should land in Phase 1** so Phase 2 doesn't have to introduce it.

### What's NOT Required

- **No FX block** — exported tracks are recorder placeholders, not playback projects. Skip `<FXCHAIN ...>`.
- **No items** (`<ITEM ...>` blocks) — engineers record audio onto these tracks live.
- **No master track block** — Reaper synthesizes one if missing. Skip `<MASTERPLAYSPEEDENV ...>` etc.
- **No `<TEMPOENVEX ...>` / `<METRONOME ...>`** — Reaper supplies defaults.
- **No `RECORD_PATH` / `RENDER_*`** — defaults are fine.

A 5-line `<REAPER_PROJECT ...>` header followed by N `<TRACK ...>` blocks each with 6 tokens is a complete file. Total file size for a 64-track session: ~3KB.

---

## Existing Channel-Source Field Reference (D-14 prerequisite)

Confirmed by direct read of `planner/models.py:777-905` on 2026-05-09:

### `ConsoleInput` (planner/models.py:777)

```python
class ConsoleInput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    dante_number = models.CharField(max_length=3, blank=True, null=True)
    input_ch = models.CharField(max_length=10, blank=True, null=True)
    source = models.CharField(max_length=100, blank=True, null=True)
    source = models.CharField(max_length=100, blank=True, null=True)  # ⚠ DUPLICATE LINE in source
    SOURCE_HARDWARE_CHOICES = [...]
    source_hardware = models.CharField(max_length=50, choices=SOURCE_HARDWARE_CHOICES, blank=True, null=True)
    group = models.CharField(max_length=100, blank=True, null=True)
    dca = models.CharField(max_length=100, blank=True, null=True)
    mute = models.CharField(max_length=100, blank=True, null=True)
    direct_out = models.CharField(max_length=100, blank=True, null=True)
    omni_in = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        if self.dante_number:    return f"Input {self.dante_number}"
        elif self.input_ch:      return f"Input {self.input_ch}"
        else:                    return f"Input {self.pk or 'New'}"
```

**⚠ Codebase quirk:** Line 781 and 782 both define `source = models.CharField(max_length=100, blank=True, null=True)`. Python takes the second definition (a no-op redefinition). This is harmless but is a smell — flag it for cleanup but DO NOT fix it in Phase 1 (out of scope, beta-tester risk).

**Field semantics for D-14 `resolved_label` on input source:**
- `source` is the **channel name** (free text — engineer types "Kick In", "Lead Vox", etc.) — this is the field the engineer actually types channel labels into. **This is the right field for `resolved_label`.**
- `input_ch` is the **physical input identifier** (e.g. "1", "A1", "OMNI 17") — useful for the picker's left-column display ("IN 1") but not the label.
- `dante_number` is the Dante stream number (string, max 3 chars).
- No `name` field exists.
- No `color` field exists. (D-05 confirmed.)
- No `project` field. The project comes via `console.project`.

**resolved_label fallback chain for input:**
```
label_override → source → input_ch → dante_number → '(untitled)'
```

### `ConsoleAuxOutput` (planner/models.py:846)

```python
class ConsoleAuxOutput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    dante_number = models.IntegerField(null=True, blank=True)   # ⚠ Integer, not Char (different from ConsoleInput!)
    aux_number = models.CharField(max_length=10)
    name = models.CharField(max_length=100, blank=True, null=True)
    mono_stereo = models.CharField(max_length=10, choices=[("Mono","Mono"),("Stereo","Stereo")], blank=True, null=True)
    bus_type = models.CharField(max_length=10, choices=[("Fixed","Fixed"),("Variable","Variable")], blank=True, null=True)
    omni_in = models.CharField(max_length=100, blank=True)
    omni_out = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"Aux {self.aux_number} - {self.name}"
```

**Field semantics:** has `name` (the user-typed label), `aux_number` (display channel number), `dante_number` as `IntegerField` (NOT `CharField` like `ConsoleInput`).

**resolved_label fallback for aux:** `label_override → name → 'Aux ' + aux_number → '(untitled)'`

### `ConsoleMatrixOutput` (planner/models.py:870)

```python
class ConsoleMatrixOutput(models.Model):
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    dante_number = models.IntegerField(null=True, blank=True)
    matrix_number = models.CharField(max_length=10)
    name = models.CharField(max_length=100, blank=True, null=True)
    mono_stereo = models.CharField(max_length=10, choices=[("Mono","Mono"),("Stereo","Stereo")], blank=True, null=True)
    destination = models.CharField(max_length=100, blank=True, null=True)
    omni_out = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Matrix {self.matrix_number} - {self.name}"
```

**resolved_label fallback for matrix:** `label_override → name → 'Matrix ' + matrix_number → '(untitled)'`

### `ConsoleStereoOutput` (planner/models.py:888)

```python
class ConsoleStereoOutput(models.Model):
    STEREO_CHOICES = [('L','Stereo Left'),('R','Stereo Right'),('M','Mono')]
    console = models.ForeignKey(Console, on_delete=models.CASCADE)
    stereo_type = models.CharField(max_length=2, choices=STEREO_CHOICES, verbose_name="Buss")
    name = models.CharField(max_length=100, blank=True, null=True)
    dante_number = models.IntegerField(null=True, blank=True)
    omni_out = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.get_stereo_type_display()} - {self.name}"

    class Meta:
        ordering = ['stereo_type']
```

**resolved_label fallback for stereo:** `label_override → name → get_stereo_type_display() → '(untitled)'`

### Cross-cutting field notes

1. **All four channel models scope by `console.project`**, NOT a direct `project` FK. The picker queryset filter is:
   ```python
   ConsoleInput.objects.filter(console__project=request.current_project, console=session.console)
   ```
2. **`dante_number` type inconsistency:** `ConsoleInput.dante_number` is `CharField`, the other three are `IntegerField`. The `resolved_dante_number` helper must handle this:
   ```python
   def resolved_dante_number(self):
       src = self.resolved_source
       if not src or not src.dante_number:
           return None
       try:
           return int(src.dante_number)  # works for both CharField('5') and IntegerField(5)
       except (ValueError, TypeError):
           return None
   ```
3. **No model has a `color` field** — confirms D-05.
4. **No model has a `project_id` field directly** — confirms `console.project_id` is the join path for project filtering.

---

## Runtime State Inventory

> Phase 1 is a **greenfield** addition (two new tables, additive only). No rename/refactor/migration of existing data.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 1 creates new tables only | None |
| Live service config | None — no external services touched | None |
| OS-registered state | None — no scheduled tasks, no daemons | None |
| Secrets/env vars | None — no new secrets | None |
| Build artifacts | None — `collectstatic` will pick up the new `Sortable.min.js` and `multitrack_editor.js` automatically; no stale artifacts | None |

**Nothing found in any category** — verified by reviewing the phase scope (CONTEXT.md) and confirming all changes are net-new files / models / signals. No existing data is renamed or migrated.

---

## Common Pitfalls

### Pitfall 1: Forgetting `admin_ordering.py`
**What goes wrong:** New `MultitrackSession` admin appears at the bottom of the sidebar (position 999) instead of grouped with related modules.
**Why it happens:** `admin_ordering.py:140` defaults unmapped models to 999.
**How to avoid:** Add a new entry to `order_map` in `planner/admin_ordering.py` for `multitracksession` (suggest position ~12.7, between `commconfig:12.5` and `showday:16` so it groups near other "session-like" modules — but Charlie's call).
**Warning signs:** Multitrack Sessions appears at the bottom of the admin sidebar after the SNMP/Network items.

### Pitfall 2: Registering on `admin.site` instead of `showstack_admin_site`
**What goes wrong:** Admin model invisible from ShowStack's UI; only visible if user navigates to default Django admin (which is suppressed).
**Why it happens:** Copy-paste from Django docs that say `admin.site.register(...)`.
**How to avoid:** Always use `from .admin_site import showstack_admin_site` and `showstack_admin_site.register(...)`. Every existing admin in `planner/admin.py` does this.
**Warning signs:** Adding the model appears successful in code, but it never shows in the sidebar.

### Pitfall 3: `request.current_project` is `None`
**What goes wrong:** `MultitrackSession.objects.filter(project=None)` returns nothing (or worse, leaks records belonging to other projects if filter logic is wrong).
**Why it happens:** A user lands on the page before any project is selected (rare but possible after invalidation, fresh login, deleted project).
**How to avoid:** Defensive check at the top of every view:
```python
if not request.current_project:
    return redirect('/')  # or render a "select a project" message
```
This matches `comm_config_create`'s pattern (views.py:3759).
**Warning signs:** Empty list view with no error message; or, in dev, the queryset returns inappropriate records.

### Pitfall 4: Direct `el.style.color = value` doesn't override admin styles
**What goes wrong:** The track's color swatch appears unchanged after the user picks a new color via JS, despite the JS executing without error.
**Why it happens:** Django admin CSS uses `!important` everywhere; inline styles set without `!important` lose the cascade.
**How to avoid:** Use `el.style.setProperty('color', value, 'important')` and `el.style.setProperty('background-color', value, 'important')`.
**Warning signs:** Color picker UI works (popover appears, click registers, JS runs, network call succeeds), but the swatch on the page doesn't visually update.

### Pitfall 5: PEAKCOL byte-order confusion (Windows vs macOS)
**What goes wrong:** Engineer exports on macOS, opens on Windows (or vice versa), sees swapped colors (red where blue should be).
**Why it happens:** The Reaper API `SetMediaTrackInfo_Value(track, 'I_CUSTOMCOLOR', N)` expects platform-native byte order at runtime — but the **RPP file format itself** stores cross-platform R-low / B-high. Mixing up these two contexts produces swapped values.
**How to avoid:** Our exporter only writes the file. **Do not try to apply Windows-style BGR swapping.** The file format is cross-platform; Reaper handles the swap on read for the runtime API. Always pack as `0x01000000 | (B<<16) | (G<<8) | R`.
**Warning signs:** Round-trip test (generate file → open in Reaper → eyeball colors) shows red/blue swapped.

### Pitfall 6: `<TRACK` block missing `MAINSEND 1 0`
**What goes wrong:** Track exists in Reaper after import but is silent — no audio routes to master.
**Why it happens:** Track's main send is undefined; default behavior is "no send."
**How to avoid:** Always emit `MAINSEND 1 0` (1 = enabled, 0 = no parent send override). Confirmed in every fixture.
**Warning signs:** Reaper opens the project successfully, tracks are visible, but the master meter shows no signal during playback test.

### Pitfall 7: `post_delete` signal fires during admin bulk-delete confirmations and tests
**What goes wrong:** Bulk-delete of 100 channels in admin triggers 100 signal handler runs each updating ~5 tracks → 500 single-row UPDATEs.
**Why it happens:** `post_delete` fires once per row deleted via the ORM.
**How to avoid:** Use a single `MultitrackTrack.objects.filter(...).update(...)` per signal call (a single UPDATE statement). Even with 100 signal fires, that's 100 UPDATEs, not 500. Acceptable for the actual deletion frequency (rare; engineers don't bulk-delete channels).
**Warning signs:** Slow admin bulk-delete on the channel models. If this becomes a problem, the planner may want to add a batched approach using `pre_delete` to collect IDs, but Phase 1 doesn't need it.

### Pitfall 8: Channels with quote-marks or commas in `name` break the RPP `NAME` token
**What goes wrong:** A channel named `Lead Vox "Frank" L` produces an RPP file with mismatched quotes; Reaper either fails to load it or truncates the name.
**Why it happens:** Reaper's RPP `NAME` token expects either an unquoted single word or a `"..."`-wrapped string with no internal `"`.
**How to avoid:** Sanitize the name in the exporter: replace `"` with `'` (single quote) and ensure the wrapped form: `NAME "Lead Vox 'Frank' L"`. Don't try to escape — just substitute. Engineers will see single-quote in the imported track, which is acceptable.
**Warning signs:** Reaper shows "could not parse line N" on import for any track whose label contains a double-quote.

### Pitfall 9: Sortable.js `onUpdate` vs `onEnd`
**What goes wrong:** Reorder save fires on every drag move (e.g. mid-drag scroll), not just on drop.
**Why it happens:** `onUpdate` fires whenever sort order changes; `onEnd` fires only when drag completes.
**How to avoid:** Use `onEnd` for the AJAX call. (`onUpdate` is for live preview if you need it, but UI-SPEC doesn't require live preview.)
**Warning signs:** Excessive XHR traffic during a single drag operation; backend log shows multiple reorder POSTs per drag.

---

## Code Examples

### Hex → PEAKCOL (verified)

```python
# planner/utils/reaper_export.py
def hex_to_peakcol(hex_color):
    """
    Convert '#RRGGBB' to a Reaper PEAKCOL int.

    Reaper RPP file format: PEAKCOL = 0x01000000 | (B<<16) | (G<<8) | R
    The 0x01000000 high bit signals "custom color enabled."
    The 24 RGB bits are stored cross-platform (R-low, B-high).

    Returns 16576 (Reaper's "no custom color" default sentinel) if hex_color
    is empty or malformed.

    Source: github.com/X-Raym/REAPER-ReaScripts (verified 2026-05-09);
    cross-checked with reapertoolkit.dev/module/color.html and JSFX docs.
    """
    if not hex_color:
        return 16576
    h = hex_color.lstrip('#').strip()
    if len(h) != 6:
        return 16576
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except ValueError:
        return 16576
    return 0x01000000 | (b << 16) | (g << 8) | r
```

### RPP body builder (verified pattern)

```python
# planner/utils/reaper_export.py
import time
import uuid
from io import StringIO

def _sanitize_name(name):
    """Replace any double-quote with single-quote; safe inside Reaper NAME token."""
    return (name or '').replace('"', "'").strip() or '(untitled)'

def _track_block(track, indent=2):
    """
    Render a single MultitrackTrack as a Reaper <TRACK ...> block.
    `track` must expose .resolved_label (str), .resolved_color (str hex or None).
    """
    pad = ' ' * indent
    label = _sanitize_name(track.resolved_label)
    peakcol = hex_to_peakcol(track.resolved_color)
    guid = '{' + str(uuid.uuid4()).upper() + '}'
    lines = [
        f'{pad}<TRACK {guid}',
        f'{pad}  NAME "{label}"',
        f'{pad}  PEAKCOL {peakcol}',
        f'{pad}  TRACKHEIGHT 0 0 0',
        f'{pad}  NCHAN 2',
        f'{pad}  TRACKID {guid}',
        f'{pad}  MAINSEND 1 0',
        f'{pad}>',
    ]
    return '\n'.join(lines)

def build_rpp(session):
    """
    Generate a complete Reaper .RPP file as a string.
    Tracks are filtered to enabled=True and ordered per session.track_order_mode.
    """
    enabled_tracks = _ordered_enabled_tracks(session)  # honors track_order_mode
    out = StringIO()
    out.write(f'<REAPER_PROJECT 0.1 "7.0/AudiopatchExporter" {int(time.time())}\n')
    out.write('  RIPPLE 0\n')
    out.write('  GROUPOVERRIDE 0 0 0\n')
    out.write('  AUTOXFADE 1\n')
    out.write('  TEMPO 120 4 4\n')
    out.write('  SAMPLERATE 48000 0 0\n')
    for track in enabled_tracks:
        out.write(_track_block(track, indent=2))
        out.write('\n')
    out.write('>\n')
    return out.getvalue()

def build_rtracktemplate(session):
    """
    Generate a Reaper .RTrackTemplate file as a string.
    Same as RPP but no <REAPER_PROJECT ...> wrapper — just back-to-back <TRACK ...> blocks.
    """
    enabled_tracks = _ordered_enabled_tracks(session)
    out = StringIO()
    for track in enabled_tracks:
        out.write(_track_block(track, indent=0))
        out.write('\n')
    return out.getvalue()
```

### View pattern for file download (mirrors `yamaha_export.py`)

```python
# planner/views.py
from django.http import HttpResponse
from .utils.reaper_export import build_rpp, build_rtracktemplate

@staff_member_required
def multitrack_export_rpp(request, session_id):
    session = get_object_or_404(
        MultitrackSession,
        id=session_id,
        project=request.current_project,
    )
    body = build_rpp(session)
    response = HttpResponse(body, content_type='text/plain; charset=utf-8')
    safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in session.name)
    response['Content-Disposition'] = f'attachment; filename="{safe_name}.RPP"'
    return response
```

### Sortable.js wiring (binding pattern from UI-SPEC)

```javascript
// planner/static/planner/js/multitrack_editor.js
function initSortable() {
  const list = document.querySelector('.mts-track-list');
  if (!list) return;
  Sortable.create(list, {
    handle: '.mts-drag',
    animation: 150,
    onEnd: function(evt) {
      const ids = Array.from(list.querySelectorAll('[data-track-id]'))
                       .map(el => parseInt(el.dataset.trackId, 10));
      const sessionId = list.dataset.sessionId;
      fetch(`/audiopatch/multitrack/${sessionId}/reorder/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify({ ordered_ids: ids }),
      }).then(r => r.json()).then(data => {
        if (!data.ok) {
          showToast('Couldn\'t save track order. Check your connection and reload the page.', 'error');
          // Optionally re-fetch the list to revert order.
        } else {
          // Optimistic UI: renumber locally
          list.querySelectorAll('.mts-track-num').forEach((el, idx) => {
            el.textContent = '#' + (idx + 1);
          });
        }
      });
    },
  });
}
document.addEventListener('DOMContentLoaded', initSortable);
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| jQuery UI sortable | Sortable.js | Sortable.js v1.0 (~2014); modern projects standardize on it | Smaller, no jQuery UI dependency, better touch support — but UI-SPEC has already chosen this |
| Reaper 6.x file format | Reaper 7.x file format | Reaper 7.0 release (2023) | RPP format is stable across 6.x → 7.x for the token set we use; no version-sensitivity for our minimal token set [VERIFIED: rppp examples include 6.13 files that still load in 7.x] |
| Synthesizing full Reaper config tokens | Minimal-token approach | Best practice in community RPP writers | Smaller files, faster to validate, easier to round-trip test |
| jQuery UI dialog | Vanilla CSS overlay | Project-level (existing precedent in `admin/base_site.html` help modal) | Less JS dependency surface |

**Deprecated/outdated:** None for our scope. Reaper RPP format is remarkably stable.

---

## Assumptions Log

These are claims tagged `[ASSUMED]` in this research that should be confirmed before implementation. Each carries a risk-of-wrong assessment.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `"7.0/AudiopatchExporter"` string in `<REAPER_PROJECT 0.1 ...>` header can be any value Reaper will tolerate (i.e. Reaper does not validate the version/platform string). | Reaper Format Facts > Header line breakdown | LOW — Reaper has historically been very lenient about this field; the worst case is Reaper refuses to load and we fall back to `"7.0/win64"` literal. Quickly verifiable by attempting an open. |
| A2 | The `track_order_mode='custom'` semantics — `track_number` is always the dense `1..N` reorder index across all modes. | Track Order Modes Explained | LOW — this is a design call. If the engineer expects `track_number` to be only-relevant-in-custom-mode, the planner can carve out a separate `display_order` field. Recommend deferring this to discuss-phase if engineering pushes back. |
| A3 | Sortable.js 1.15.x default config (`onEnd` only, no live `onUpdate`) is the right behavior for TRK-05. | Code Examples > Sortable.js wiring | LOW — UI-SPEC implies "save on drop"; if engineering wants live preview reorder, that's `onUpdate`. Trivially changeable. |
| A4 | `MAINSEND 1 0` is the correct token for "route to master, no parent send override" — verified across multiple fixtures, but the second `0` may have edge cases. | Reaper Format Facts > Required tokens | LOW — every fixture has this exact value. |
| A5 | Sanitizing a label by replacing `"` with `'` is acceptable to engineers (no escaping). | Pitfall 8 | LOW — engineers who use double-quotes in channel names are rare in live audio. If it becomes a problem, switch to backslash escaping. |
| A6 | `admin_ordering.py` position `12.7` for Multitrack Sessions (between Comm Config at 12.5 and Show Day at 16) is a sensible group placement. | Pitfall 1 | LOW — purely cosmetic. Charlie may want it elsewhere in the sidebar; that's a final-call decision. |
| A7 | Phase 1 does NOT need to build the Yamaha→Reaper color mapping table from a Phase 2 channel-color field that doesn't exist yet — the table is dormant in Phase 1 and activated in Phase 5 / Phase 2. | Reaper Format Facts > Yamaha → Reaper Color Mapping | LOW — table just lives in the module; no behavior depends on it in Phase 1 since `color_override` is the only color field. |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed.

In this research, the table is non-empty but all assumptions are LOW-risk and don't block the planner. No discuss-phase reopen is required for any of them.

---

## Open Questions (RESOLVED)

All seven questions below were resolved during /gsd-discuss-phase (see 01-CONTEXT.md). The recommendations were accepted and locked. Listed here for traceability.

1. **`MultitrackSession.notes` — required field?**
   - What we know: `multitrack_session_builder_spec.md` lists `notes = TextField(blank=True)` on `MultitrackSession`.
   - What's unclear: UI-SPEC § "+ New Session" Flow shows a "Notes (optional)" field — confirmed it should exist.
   - Recommendation: include it. `notes = TextField(blank=True, default='')`.
   - **RESOLVED:** optional `TextField(blank=True, default='')` (matches CONTEXT.md spec patterns).

2. **`MultitrackTrack.notes` — `CharField` or `TextField`?**
   - What we know: spec says `notes = CharField(max_length=200, blank=True)`. UI-SPEC describes per-track inline notes as short.
   - What's unclear: 200 chars feels right for a track-row inline field; nothing forces this.
   - Recommendation: `CharField(max_length=200, blank=True, default='')` per spec.
   - **RESOLVED:** `TextField(blank=True, default='')` — engineers may write multi-line notes.

3. **Edit metadata flow — full Django change form or inline modal?**
   - What we know: UI-SPEC § "Editor" lists "Edit metadata" as a tertiary action (plain link styling).
   - What's unclear: Does it open a dedicated form page (consistent with new-session form) or a modal?
   - Recommendation: dedicated form page at `/audiopatch/multitrack/<id>/edit/` — reuses the new-session form's template — simpler.
   - **RESOLVED:** simple page (`/audiopatch/multitrack/<id>/edit/`) using same form template as create — matches existing planner module precedent.

4. **What does the per-card dropdown's "Rename" do?**
   - What we know: UI-SPEC dashboard has Duplicate / Rename / Delete in the per-card dropdown.
   - What's unclear: Rename = inline text-edit on the card, or a small modal like Duplicate?
   - Recommendation: small modal matching Duplicate's pattern (single field, prefilled, primary "Rename" + Cancel).
   - **RESOLVED:** opens an inline modal that posts a single `name` field to `/audiopatch/multitrack/<id>/rename/`.

5. **`track_order_mode='dante'` ordering when channels have no Dante number.**
   - What we know: `dante_number` is nullable on all four channel models.
   - What's unclear: Where do channels with `dante_number=NULL` sort in `dante` mode? End? Hidden?
   - Recommendation: sort to end (after channels with numbers), then apply `track_number` as tiebreak. Manual tracks (also no Dante number) sort behind those.
   - **RESOLVED:** null-Dante channels sort to the END of the list, then by track_number ascending; manual tracks sort after all real channels (also by track_number).

6. **Does `Export to Reaper` produce `.RPP` or `.RTrackTemplate` by default?**
   - What we know: UI-SPEC has both as separate buttons (`[Export to Reaper]` primary, `[Export Track Template (.RTrackTemplate)]` secondary).
   - What's unclear: Is the primary button definitely `.RPP`?
   - Recommendation: yes — `.RPP` is the primary Reaper export per UI-SPEC. `.RTrackTemplate` is for "merge into existing project" workflows.
   - **RESOLVED:** `.RPP` is the primary export from the editor toolbar; `.RTrackTemplate` is a secondary action (separate dropdown item or separate button).

7. **`track_order_mode` mid-session change — preserve manual track positions?**
   - What we know: Custom mode uses `track_number`. Channel/Dante modes compute order on read.
   - What's unclear: If engineer drags in custom mode, then switches to channel mode, then back to custom, do drag positions persist?
   - Recommendation: yes — `track_number` is always saved on drag. Mode switches never mutate `track_number`. Mode purely controls render order.
   - **RESOLVED:** changing mode does NOT renumber track_number; the sort-key for display is computed at render time. Switching to `custom` preserves the current order; switching back to `channel` or `dante` resorts on the resolved channel/dante number, with manual tracks sorted at the end by track_number.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Django 5.x | Everything | ✓ | (project pinned) | — |
| Python `uuid` | RPP TRACK GUID generation | ✓ | stdlib | — |
| Python `time` | RPP header timestamp | ✓ | stdlib | — |
| Python `io.StringIO` | RPP body assembly | ✓ | stdlib | — |
| Sortable.js | Drag-reorder UX | Will be vendored | 1.15.7 (MIT) | — (UI-SPEC requires it) |
| Whitenoise | Serving the vendored JS | ✓ | (project pinned) | — |
| Reaper application | Manual smoke test of exported `.RPP` | (engineer's machine — Charlie's) | Reaper 7.x | — Charlie has Reaper 7 |
| jQuery | All AJAX/UI work in editor JS | ✓ | (bundled by Django admin) | — |
| `getCookie` JS helper | CSRF token retrieval in JS | (defined in existing templates — see comm_config.html:1154 invocation, helper itself defined elsewhere) | — | If missing, copy from Django docs (~10 lines) |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — but verify `getCookie` helper exists at template scope before reusing. If not, define it in `multitrack_editor.js`.

---

## Sources

### Primary (HIGH confidence)
- `planner/models.py:754-905` (Console + 4 channel models) — read directly 2026-05-09
- `planner/middleware.py` (CurrentProjectMiddleware) — read directly 2026-05-09
- `planner/admin_site.py` (showstack_admin_site, has_permission, get_app_list) — read directly 2026-05-09
- `planner/admin_ordering.py` (sidebar order_map) — read directly 2026-05-09
- `planner/admin.py:1-200` (BaseEquipmentAdmin pattern) — read directly 2026-05-09
- `planner/signals.py` (existing post_save pattern) — read directly 2026-05-09
- `planner/apps.py:8-13` (signal wiring via `ready()`) — read directly 2026-05-09
- `planner/views.py:1882-1980` (comm_config_view list+editor pattern) — read directly 2026-05-09
- `planner/views.py:3754-3777` (comm_config_create AJAX pattern) — read directly 2026-05-09
- `planner/utils/yamaha_export.py:1-30` (file download pattern) — read directly 2026-05-09
- `templates/planner/comm_config.html:1149-1212` (modal + AJAX + CSRF JS pattern) — read directly 2026-05-09
- `templates/admin/base_site.html:138-180` (help modal overlay pattern referenced by UI-SPEC) — confirmed via grep 2026-05-09
- `npm registry: sortablejs/latest` — version 1.15.7, MIT, fetched 2026-05-09
- CharlesHolbrow/rppp `audio-file-x4.RPP` — fetched 2026-05-09 (verbatim TRACK block)
- CharlesHolbrow/rppp `empty-track.RPP` — fetched 2026-05-09 (verbatim full file)
- CharlesHolbrow/rppp `send-receive.RPP` — fetched 2026-05-09 (verified PEAKCOL 16576 default)
- Reaper-Track-Templates/LASS-2 `LASS - Basses Full.RTrackTemplate` — fetched 2026-05-09 (verified RTrackTemplate format starts directly with `<TRACK`, has non-default PEAKCOL values 30310924 and 31561399)
- ReaTeam/Doc `State Chunk Definitions` — fetched 2026-05-09 (PEAKCOL 16576 documented as the default)

### Secondary (MEDIUM confidence)
- reaper.fm/sdk/js/gfx.php — JSFX color packing formula (cross-verified by SWS source)
- reapertoolkit.dev/module/color.html — RGB byte order documentation
- github.com/reaper-oss/sws/master/Color/Color.cpp — `0x1000000 | RGB(r,g,b)` pattern
- github.com/X-Raym/REAPER-ReaScripts — hex-to-Reaper conversion idiom

### Tertiary (LOW confidence — flag for validation)
- None. All claims that affect implementation are HIGH or MEDIUM.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library is either already in the project or vendored from a major OSS release confirmed on npm
- Architecture: HIGH — every pattern has a verbatim citation from the existing codebase
- Pitfalls: HIGH — pitfalls 1, 2, 3, 4, 7 come directly from CLAUDE.md / project conventions; 5, 6, 8, 9 come from format research with specific citations
- Reaper format facts: HIGH — verified by direct fetch of real `.RPP` and `.RTrackTemplate` files plus three independent docs sources for color packing (JSFX docs, ReaperToolkit, SWS source)
- Channel model fields: HIGH — read directly from models.py
- Track order modes: MEDIUM — interpretation of spec text; should be confirmed with Charlie if any ambiguity surfaces in planning

**Research date:** 2026-05-09
**Valid until:** 2026-06-09 (30 days — Reaper format is stable; Sortable.js 1.15.x line is mature; existing codebase patterns are not in active flux)
