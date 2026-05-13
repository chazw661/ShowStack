---
phase: 03-multitrack-templates
verified: 2026-05-13T20:15:00Z
status: human_needed
score: 6/6 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: 0/0
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "End-to-end save → list → rename → delete flow on a live browser session"
    expected: "Engineer clicks 'Save as Template' on /audiopatch/multitrack/<id>/, enters a name, sees success toast; navigates to /audiopatch/multitrack/ and sees the template card; clicks ⋯ → Rename, enters new name, page reloads with renamed card; clicks ⋯ → Delete, confirms, card disappears."
    why_human: "Toast visibility, dropdown menu interactivity, and page-reload behavior cannot be verified without rendering JS in a real browser."
  - test: "Apply a CL5-saved template to a QL5 target — confirm skipped-slot banner appears with correct count"
    expected: "Save a template from a session whose console has matrix 9-12; create a new session on a console with only 8 matrices and pick the template. Banner reads exactly: 'Applied template '<name>' — 16 of 20 slots mapped; 4 skipped (matrix 9, 10, 11, 12 not present on this console).'"
    why_human: "Banner is rendered server-side via messages.info on the editor page (admin/base_site.html); confirming the exact wording requires a real session+console+template tuple, which requires a logged-in browser context."
  - test: "Empty-template apply — confirm the metadata-seeded banner appears"
    expected: "Save a template from a session with zero enabled tracks. Create a new session and pick the template. Banner reads exactly: 'Applied template '<name>' — metadata seeded; no tracks in template.' and the editor opens with the track picker auto-opened on Inputs per Phase 1 D-12."
    why_human: "Requires creating a zero-track session, saving its template, then applying. Picker auto-open is a Phase 1 behavior triggered on zero-track sessions — confirm cross-phase wiring still works."
  - test: "Multi-user owner-scoping smoke test (user A's templates don't appear in user B's dropdown)"
    expected: "User A saves template T1; user B opens /audiopatch/multitrack/new/ and the dropdown does NOT list T1. User B crafts a POST with template=<T1's id>; form validation rejects with 'Select a valid choice.'"
    why_human: "IDOR closure is verified statically by code review (every queryset filters by created_by=request.user), but a multi-user smoke test confirms no bypass at runtime — especially confirming the form's ModelChoiceField rejects cross-tenant ids."
  - test: "Viewer-group write blocks (save/rename/delete return 403)"
    expected: "Add a user to the Viewer group; attempt to POST /audiopatch/multitrack/templates/save/, /rename/, /delete/. All three return HTTP 403 with body {'error': 'Read-only access.'}."
    why_human: "Verifying viewer-block requires constructing a CSRF-valid POST as a Viewer-group user, which is a multi-step setup that's faster to validate via curl + a real session cookie."
  - test: "TPL-04 visual parity with Audio Checklist / Comm Config template patterns"
    expected: "The Save-as-Template button placement, the rename modal/prompt behavior, and the empty-state copy on the Templates dashboard section look and feel comparable to AudioChecklistTemplate's existing patterns (rename/load/delete dropdown shape)."
    why_human: "Visual parity is a UX judgement call; automated grep can confirm structural similarity but cannot judge whether the rendered result 'matches'."
---

# Phase 3: Multitrack Templates Verification Report

**Phase Goal:** Engineer can save a working session's structure as a reusable template (owner-scoped per CONTEXT D-05) and apply it to seed new sessions on any console.
**Verified:** 2026-05-13T20:15:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Engineer saves the current session's structure as a named MultitrackTemplate | ✓ VERIFIED | `multitrack_template_save` view at views.py:6390 + "Save as Template" button at editor.html:25-30 + `mtsSaveAsTemplate` JS at multitrack_editor.js:608. Endpoint POSTs to `/audiopatch/multitrack/templates/save/` (URL resolves), owner-scopes via `created_by=request.user` (views.py:6437, 6444), creates `MultitrackTemplate` + bulk-creates `MultitrackTemplateSlot` rows from enabled tracks. Name conflict returns 409. |
| 2 | Engineer applies a template to a new session; track list + metadata are seeded; per-track values overridable afterward | ✓ VERIFIED | `MultitrackSessionForm.template` ModelChoiceField at forms.py:1160-1166 with owner-scoped queryset in `__init__` at forms.py:1186; `multitrack_create_view` calls `template.apply_to_session(session)` at views.py:6026 after `form.save()`; `apply_to_session` at models.py:1160 dispatches via `_source_model_for` + per-source-type channel-number field map; manual slots materialise, non-matching slots skipped and surfaced via messages.info banner (views.py:6031-6049). Per-track values remain overridable because tracks are normal `MultitrackTrack` rows post-apply (Phase 1 editor TRK-03/TRK-04 still apply). |
| 3 | Engineer can list, rename, and delete templates from the module landing page | ✓ VERIFIED | `multitrack_dashboard` extended at views.py:5754-5786 to pass owner-scoped `templates` queryset; `dashboard.html:51-71` renders Templates section with divider + empty state + grid; `_template_card.html` (22 lines) renders each template with Rename/Delete dropdown. `multitrack_template_rename` (views.py:6486) and `multitrack_template_delete` (views.py:6538) endpoints registered, both IDOR-guarded via `created_by=request.user`, rename returns 409 on name conflict. `mtsRenameTemplate` (multitrack_editor.js:635) and `mtsDeleteTemplate` (multitrack_editor.js:648) JS handlers in place. |
| 4 | Save/load buttons, placement, and modal behavior visually and behaviorally match existing ShowStack template patterns | ⚠️ NEEDS HUMAN | Structural patterns match: dropdown card menus mirror `_session_card.html`; rename uses `window.prompt` + reload (same UX as `mtsRenameSession`); delete uses `window.confirm` (same UX as `mtsDeleteSession`); save button uses same `mts-btn-tertiary` class. Visual parity vs Comm Config / Audio Checklist requires a rendered comparison. Routed to human_verification. |
| 5 | Owner-scoping enforced everywhere (D-05): no template query without `created_by=request.user` filter | ✓ VERIFIED | All 10 `MultitrackTemplate.objects` queries audited: forms.py:1161 (.none() class default), 1186 (`filter(created_by=request.user)`), 1190 (.none() fallback); views.py:5773 (`filter(created_by=request.user)`), 5775 (.none() fallback), 6436 (`filter(created_by=..., name=...)`), 6443 (`create(created_by=request.user, ...)`), 6501 (`filter(id=..., created_by=request.user)`), 6515 (`filter(created_by=..., name=...)`), 6554 (`filter(id=..., created_by=request.user)`). Zero `MultitrackTemplate.objects.all()` or `.get(pk=...)` without owner filter. Zero `project=` on template queries. |
| 6 | Dropped fields (include_aux, color_scheme, naming_pattern) not introduced (D-14/D-15/D-16) | ✓ VERIFIED | `grep -nE "include_aux\|color_scheme\|naming_pattern\|include_matrix\|include_groups"` returns zero matches across models.py, forms.py, admin.py, migrations/0154_multitrack_template.py. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `planner/models.py` | MultitrackTemplate + MultitrackTemplateSlot + apply_to_session + _summarise_skipped_slots | ✓ VERIFIED | Classes at lines 1122 and 1228; apply_to_session at 1160; helper at 1267. `unique_together=[('created_by','name')]` and `[('template','position')]` confirmed at runtime. NO `project` FK on MultitrackTemplate. |
| `planner/migrations/0154_multitrack_template.py` | Additive migration (CreateModel only) | ✓ VERIFIED | 2 CreateModel + 2 AddIndex + 2 AlterUniqueTogether ops, all targeting newly created tables. Zero AlterField/RemoveField/RenameField/RunSQL. `showmigrations` reports `[X] 0154_multitrack_template` applied. `makemigrations --dry-run` reports "No changes detected". |
| `planner/admin.py` | MultitrackTemplateAdmin + Inline registered on showstack_admin_site | ✓ VERIFIED | `class MultitrackTemplateSlotInline` at line 5990; `class MultitrackTemplateAdmin` at 6007; registered on `showstack_admin_site` (not `admin.site`) at line 6051. `MultitrackTemplateSlot` NOT separately registered (runtime check: `MultitrackTemplateSlot in showstack_admin_site._registry == False`). |
| `planner/admin_ordering.py` | 'multitracktemplate' inserted in order_map between sessions and consoleimport | ✓ VERIFIED | Lines 163-165: `multitracksession: 50`, `multitracktemplate: 51` (NEW), `consoleimport: 52` (bumped from 51). |
| `planner/views.py` | save, rename, delete views + dashboard context extension + create_view apply branch | ✓ VERIFIED | `multitrack_template_save` at 6390 with viewer-block + IDOR-guard + 409 + bulk_create; `multitrack_template_rename` at 6486 with `.exclude(pk=template.pk).exists()` allowing no-op rename; `multitrack_template_delete` at 6538 with CASCADE comment; `multitrack_dashboard` extended at 5754 to include `templates` context; `multitrack_create_view` at 6004 calls `template.apply_to_session` and emits 3-branch banner via 3 `messages.info` calls at 6031, 6038, 6045. |
| `planner/urls.py` | 3 URL routes for save/rename/delete | ✓ VERIFIED | Routes at lines 112-114; URL ordering before `multitrack/<int:session_id>` routes per acceptance criterion; all 3 reverse cleanly. |
| `planner/forms.py` | template ModelChoiceField with owner-scoped queryset in __init__ | ✓ VERIFIED | Class-level field at 1160-1166 with `queryset=MultitrackTemplate.objects.none()` (IDOR-safe default); per-instance scoping at 1185-1190 via `filter(created_by=request.user)`. `template` NOT in Meta.fields (Meta block at 1141-1147 lists only `name, console, target_daw, feed_source, track_order_mode, recorder_capacity, notes`). |
| `planner/templates/planner/multitrack/editor.html` | "Save as Template" button in .mts-editor-actions | ✓ VERIFIED | Button at lines 25-30 with `mtsSaveAsTemplate({{ session.id }}, '{{ session.name|escapejs }}')` onclick; |escapejs filter present (XSS guard). CSRF form preserved at line 111. |
| `planner/templates/planner/multitrack/dashboard.html` | Templates section with divider + empty state + grid | ✓ VERIFIED | Section at lines 51-71 with `<hr class="mts-section-divider">`, exact empty-state copy "No templates yet — save one from the session editor." at line 68, and `{% include "planner/multitrack/_template_card.html" with template=template %}` loop. |
| `planner/templates/planner/multitrack/_template_card.html` | New partial with Rename + Delete dropdown (no Duplicate, no anchor) | ✓ VERIFIED | 22-line partial with `data-template-id`, `tmpl-` prefixed dropdown DOM id (collision-free), Rename + Delete buttons calling `mtsRenameTemplate`/`mtsDeleteTemplate` with `|escapejs`-filtered name. No `mtsDuplicate*`. No `<a href>` wrap. |
| `planner/templates/planner/multitrack/new_session.html` | Template dropdown form-row with data-* attrs + JS script tag | ✓ VERIFIED | Dropdown at lines 31-49 guarded by `{% if form.template.field.queryset.exists %}`, each option carries `data-target-daw`, `data-feed-source`, `data-track-order-mode`, `data-recorder-capacity` (`\|default_if_none:''`), `data-notes` (`\|escape`). Onchange handler at 35 calls `mtsApplyTemplateToForm`. `{% load static %}` at line 2; script tag at line 132. |
| `planner/static/planner/js/multitrack_editor.js` | mtsSaveAsTemplate + mtsRenameTemplate + mtsDeleteTemplate + mtsApplyTemplateToForm | ✓ VERIFIED | All 4 handlers present at lines 608, 635, 648, 669 inside the IIFE. Phase 3 banner at line 604 appears exactly once. JS parses cleanly under `node -e "new Function(...)"`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| editor.html "Save as Template" button onclick | mtsSaveAsTemplate JS | inline `onclick="mtsSaveAsTemplate({{ session.id }}, ...)"` | ✓ WIRED | editor.html:27 references the function exposed at multitrack_editor.js:608. |
| mtsSaveAsTemplate JS | POST /audiopatch/multitrack/templates/save/ | postJSON helper | ✓ WIRED | multitrack_editor.js:608+ posts to the URL that views.py:6390 handles; URL reverses to the expected path. |
| multitrack_template_save view | MultitrackTemplate.objects.create + MultitrackTemplateSlot.objects.bulk_create | ORM | ✓ WIRED | views.py:6443 creates the template, 6466 bulk-creates slot rows; enabled-only filter at 6455. |
| dashboard.html Templates section | _template_card.html partial | `{% include with template=template %}` | ✓ WIRED | dashboard.html:62 includes the partial; partial reads `template.id`, `template.name`, `template.slots.count`, `template.get_target_daw_display`, `template.updated_at`. |
| _template_card.html dropdown | mtsRenameTemplate / mtsDeleteTemplate JS | inline onclick | ✓ WIRED | partial:17,19 call the JS handlers defined at multitrack_editor.js:635, 648. |
| mtsRenameTemplate / mtsDeleteTemplate JS | POST /audiopatch/multitrack/templates/<id>/rename/ /delete/ | postJSON | ✓ WIRED | URLs reverse correctly (verified via `reverse(..., args=[1])`); endpoints exist at views.py:6486, 6538. |
| MultitrackSessionForm.template field | MultitrackTemplate.objects.filter(created_by=request.user) | __init__ per-instance assignment | ✓ WIRED | forms.py:1186 filters by user; class-level default at 1161 is `.none()` (IDOR-safe). |
| new_session.html template select onchange | mtsApplyTemplateToForm | inline onchange | ✓ WIRED | new_session.html:35 calls the function defined at multitrack_editor.js:669; the function reads `opt.dataset.targetDaw/feedSource/trackOrderMode/recorderCapacity/notes`. |
| multitrack_create_view | MultitrackTemplate.apply_to_session | `form.cleaned_data.get('template')` → method call | ✓ WIRED | views.py:6024-6026 reads cleaned_data and calls apply_to_session; result tuple feeds the 3-branch messages.info banner at 6031-6049. |
| MultitrackTemplate.apply_to_session | MultitrackTrack.objects.bulk_create | bulk_create in single transaction | ✓ WIRED | models.py:1224 bulk-creates tracks; per-source-type dispatch via _source_model_for at 1198. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| dashboard.html `{% for template in templates %}` | `templates` context var | `multitrack_dashboard` view filters `MultitrackTemplate.objects.filter(created_by=request.user).order_by('name')` | Yes — real ORM query against MultitrackTemplate table | ✓ FLOWING |
| new_session.html dropdown `{% for tpl in form.template.field.queryset %}` | form.template.field.queryset | `MultitrackSessionForm.__init__` assigns `filter(created_by=request.user)` | Yes — same owner-scoped query | ✓ FLOWING |
| editor.html "Save as Template" button | `session.id` + `session.name` | Server-rendered from `MultitrackSession` instance | Yes — real session row | ✓ FLOWING |
| Banner on editor after apply | `messages.info(request, ...)` | View emits before `redirect`; rendered via admin/base_site.html messages block | Yes — real `apply_to_session` return tuple | ✓ FLOWING |
| _template_card.html `{{ template.slots.count }}` | template.slots related manager | MultitrackTemplateSlot rows via FK | Yes — counts real rows | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Django system check | `./venv/bin/python manage.py check planner` | "System check identified no issues (0 silenced)." | ✓ PASS |
| No pending migrations | `./venv/bin/python manage.py makemigrations planner --dry-run` | "No changes detected in app 'planner'" | ✓ PASS |
| Migration applied | `./venv/bin/python manage.py showmigrations planner` | `[X] 0154_multitrack_template` | ✓ PASS |
| URL reverses work | `reverse('planner:multitrack_template_save')` etc. | `/audiopatch/multitrack/templates/save/`, `/audiopatch/multitrack/templates/1/rename/`, `/audiopatch/multitrack/templates/1/delete/` | ✓ PASS |
| Model unique_together | `MultitrackTemplate._meta.unique_together` | `(('created_by', 'name'),)` | ✓ PASS |
| Slot unique_together | `MultitrackTemplateSlot._meta.unique_together` | `(('template', 'position'),)` | ✓ PASS |
| apply_to_session callable | `callable(MultitrackTemplate().apply_to_session)` | True | ✓ PASS |
| _summarise_skipped_slots grouped | `_summarise_skipped_slots([('matrix','9'),('matrix','10')])` | `"matrix 9, 10 not present on this console"` | ✓ PASS |
| _summarise_skipped_slots empty | `_summarise_skipped_slots([])` | `''` | ✓ PASS |
| Admin registration | `MultitrackTemplate in showstack_admin_site._registry` | True | ✓ PASS |
| Slot NOT separately registered | `MultitrackTemplateSlot not in showstack_admin_site._registry` | True | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TPL-01 | 03-01, 03-02, 03-03 | User can save the current session's structure as a named MultitrackTemplate | ✓ SATISFIED | Save endpoint + button + JS handler shipped end-to-end; owner-scoped per D-05 (divergence from spec's "project-scoped" wording documented in CONTEXT). Note: spec originally listed `include_aux/matrix/groups + color_scheme + naming_pattern` fields — D-14/D-15/D-16 deliberately dropped them (rationale in CONTEXT). REQUIREMENTS.md checkbox `[x]`. |
| TPL-02 | 03-01, 03-05 | User can apply a template to a new session, seeding track list + metadata | ✓ SATISFIED | `apply_to_session` algorithm + form `template` field + create-view apply branch + messages.info banner shipped. Per-track override remains possible via Phase 1 TRK-03/TRK-04 (independent). REQUIREMENTS.md checkbox `[x]`. |
| TPL-03 | 03-02, 03-04 | User can list, rename, and delete templates from the module landing page | ✓ SATISFIED | Dashboard Templates section + rename + delete endpoints + JS handlers. REQUIREMENTS.md checkbox `[x]`. |
| TPL-04 | 03-03, 03-04, 03-05 | Visual + behavioral parity with existing ShowStack template patterns | ⚠️ NEEDS HUMAN | Structural parity verified (dropdown card menus mirror `_session_card.html`; window.prompt/confirm UX matches `mtsRenameSession`/`mtsDeleteSession`; button classes reused). Visual judgement requires human comparison vs Audio Checklist / Comm Config rendered pages. REQUIREMENTS.md checkbox `[x]`. |

**No orphaned requirements** — all 4 TPL-* IDs from REQUIREMENTS.md are claimed by Phase 3 plans and verified above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| planner/views.py | 6004-6051 | `multitrack_create_view` lacks `_multitrack_viewer_block` (only `@staff_member_required`); Phase 3's `apply_to_session` adds a new write surface (`MultitrackTrack.objects.bulk_create`) that bypasses the viewer-gate present on every other multitrack mutation endpoint. | ⚠️ Warning | Code-review finding WR-03 (advisory). A user with `is_staff=True` and `Viewer` group membership can apply a template and create tracks. Pre-existing weakness from Phase 1 (viewer-staff could already create empty sessions); Phase 3 only expanded what that POST does. Not goal-blocking — viewers should not normally be `is_staff`. |
| planner/views.py | 6019-6051 | No `transaction.atomic()` wrap around `form.save() + apply_to_session()`. Same applies to `multitrack_template_save` (lines 6443-6466). | ⚠️ Warning | Code-review finding WR-02 (advisory). If `bulk_create` raises mid-apply, the session row persists with zero tracks (or template persists with zero slots). Engineer sees the empty editor and re-applies manually. Low likelihood (apply_to_session is defensive — `.first()` returns None on miss, no IntegrityError path inside bulk_create unless DB-level corruption). Not goal-blocking. |
| planner/models.py | 1206-1209 | `apply_to_session` filters by `**{field: slot.source_number}` even when `slot.source_number == ''` for non-manual slots. `ConsoleInput.input_ch` allows `blank=True/null=True` — could silently bind to a partially-configured channel row. | ⚠️ Warning | Code-review finding WR-01 (advisory). Edge case: a template saved between a source channel's deletion and the D-04 post_delete cascade running could persist a non-manual slot with empty source_number. Defensive fix: skip non-manual slots whose source_number is empty. Not goal-blocking in normal operation (manual short-circuit at 1187 + post_delete cascade in Phase 1 handle the common path). |
| planner/forms.py | 1155-1166 | `template = forms.ModelChoiceField(...)` declared AFTER `class Meta:` — Django's metaclass accepts this but convention is fields before Meta. | ℹ️ Info | Code-review finding IN-01. Cosmetic only. Functional. |
| planner/views.py | 6354-6385 | `_resolve_track_source_number` issues one SELECT per track inside `multitrack_template_save`'s loop — N+1 for sessions with many enabled tracks (max ~144 on Rivage PM10). | ℹ️ Info | Code-review finding IN-02. Performance, not correctness. Out of scope for v1. |
| planner/templates/planner/multitrack/editor.html | 25-30 | "Save as Template" button rendered unconditionally; viewers see it, click it, get 403. | ℹ️ Info | Code-review finding IN-03. Matches existing pattern for sibling buttons. Not a regression. |

**Blockers:** 0. All anti-patterns are advisory; none prevent goal achievement.

### Human Verification Required

See frontmatter `human_verification` block for the 6 items. Summary:

1. **End-to-end save/list/rename/delete flow** in a live browser — confirm toast visibility, dropdown menu interactivity, and page-reload behaviors.
2. **CL5 → QL5 apply with skipped-slot banner** — confirm exact banner wording matches `"Applied template '<name>' — N of M slots mapped; K skipped (...)."`.
3. **Empty-template apply** — confirm "metadata seeded; no tracks in template." banner + Phase 1 picker auto-open on zero-track session.
4. **Multi-user owner-scoping smoke** — user A's templates do NOT appear in user B's dropdown; crafted POST with cross-tenant template_id returns ValidationError.
5. **Viewer-group write blocks** — save/rename/delete endpoints return 403 for Viewer-group users.
6. **TPL-04 visual parity** — judgement call against Audio Checklist / Comm Config patterns.

### Gaps Summary

**No goal-blocking gaps.** All 4 ROADMAP success criteria are structurally implemented end-to-end:

1. ✓ Save current session as named MultitrackTemplate (TPL-01).
2. ✓ Apply template to a new session, seeding tracks + metadata (TPL-02).
3. ✓ List/rename/delete templates from landing page (TPL-03).
4. ⚠️ TPL-04 visual parity — needs human verification (judgement call).

The 3 code-review warnings (WR-01 empty source_number edge case, WR-02 missing transaction wrapper, WR-03 viewer-as-staff bypass on multitrack_create_view) are advisory quality concerns surfaced in `03-REVIEW.md`. They do NOT block goal achievement — they describe robustness improvements for hardening passes, not core functionality gaps.

The 6 human verification items in the frontmatter need to be exercised in a live browser before Phase 3 can be marked fully done. Automated verification has confirmed:

- All models, migration, admin, views, URL routes, templates, partials, and JS handlers exist with correct shape.
- D-05 owner-scoping is enforced on every single `MultitrackTemplate` query path (audited).
- D-14/D-15/D-16 dropped fields are absent.
- TPL-01..TPL-04 are checked `[x]` in REQUIREMENTS.md.
- `python manage.py check planner` exits 0; `makemigrations --dry-run` reports no changes; the 0154 migration is applied locally.
- URL routes reverse correctly; admin registration is on `showstack_admin_site` (not `admin.site`); `MultitrackTemplateSlot` is intentionally NOT separately registered.

---

_Verified: 2026-05-13T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
