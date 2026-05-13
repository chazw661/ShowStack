---
phase: 03-multitrack-templates
plan: 04
subsystem: views
tags: [django, views, ajax, frontend, multitrack, templates, list, rename, delete]

# Dependency graph
requires:
  - phase: 03-multitrack-templates
    provides: "MultitrackTemplate + MultitrackTemplateSlot models from plan 03-01 (planner/models.py); admin registration from 03-02; multitrack_template_save view + 'Template save / rename / delete (Phase 3 / v3.0)' banner + mtsSaveAsTemplate JS handler from plan 03-03"
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: "MultitrackSession + MultitrackTrack models; csrfToken()/postJSON()/showToast() JS helpers in multitrack_editor.js; _multitrack_viewer_block() + _multitrack_logger in views.py; _session_card.html partial pattern; .mts-card / .mts-grid / .mts-empty-state CSS classes; .mts-dropdown-menu + .mts-card-menu-trigger machinery from mtsToggleCardMenu"
provides:
  - "multitrack_template_rename JSON POST view at /audiopatch/multitrack/templates/<int:template_id>/rename/ (TPL-03) — owner-scoped (D-05), IDOR-guarded via filter(id=template_id, created_by=request.user), 409-on-name-conflict (exclude(pk=self) so a no-op rename is allowed), narrow update_fields=['name', 'updated_at'], IntegrityError defensive 409, _multitrack_logger.exception + generic 500"
  - "multitrack_template_delete JSON POST view at /audiopatch/multitrack/templates/<int:template_id>/delete/ (TPL-03) — owner-scoped (D-05), IDOR-guarded, CASCADE on MultitrackTemplateSlot.template handles slot rows, sessions previously created from the template are NOT affected (no FK back to template), _multitrack_logger.exception + generic 500"
  - "Extended multitrack_dashboard context: owner-scoped templates queryset (filter(created_by=request.user).order_by('name')) passed to dashboard.html — server-rendered list, no separate list endpoint needed"
  - "_template_card.html partial: card markup for a MultitrackTemplate row with Rename + Delete dropdown actions (no Duplicate, no anchor wrap — templates have no detail page in v3.0); dropdown DOM id prefixed 'tmpl-' to avoid collision with session-card ids on the same page"
  - "dashboard.html Templates section: rendered below the sessions block, separated by <hr class='mts-section-divider'>, with empty-state copy exactly 'No templates yet — save one from the session editor.'"
  - "window.mtsRenameTemplate(templateId, oldName) JS handler — window.prompt + postJSON to /rename/ with {new_name: ...} body shape (DIFFERS from mtsRenameSession's {name: ...}) + window.location.reload on success"
  - "window.mtsDeleteTemplate(templateId, name) JS handler — window.confirm with copy explaining CASCADE scope ('Sessions previously created from this template are not affected') + postJSON to /delete/ + reload"
affects: [03-05 apply path consumes the same Templates section UI; future phases that touch the dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-card dropdown ID collision avoidance: when two card grids (sessions + templates) render on the same page, the second grid prefixes its dropdown IDs ('tmpl-{{ template.id }}') so mtsToggleCardMenu's getElementById lookup remains unique. Sessions use the raw integer ID; templates use the string with prefix. mtsToggleCardMenu accepts both because it concatenates the value into 'mts-card-menu-' + suffix."
    - "Server-rendered list (no JSON list endpoint): the dashboard view passes the templates queryset directly to the render context; client never fetches templates separately. Matches the Phase 1 sessions list pattern. Reduces moving parts and removes a network round-trip on dashboard load."
    - "Rename body shape divergence (intentional): /rename/ for sessions accepts {name: ...} (Phase 1), /rename/ for templates accepts {new_name: ...} (Phase 3). Both endpoints' views read what they expect; the JS handlers send what their view expects. Documented in plan 03-04 action block; not a bug."
    - "IDOR-via-404 (not 403): non-owner template_id resolves to None via filter(created_by=request.user).first() and returns 404 — avoids template_id enumeration that a 403 'wrong owner' message would leak. Same pattern as the session rename endpoint."

key-files:
  created:
    - "planner/templates/planner/multitrack/_template_card.html — new 22-line partial cloned from _session_card.html with: data-template-id attribute, no anchor wrap (template has no detail page), no Duplicate dropdown item (deferred per CONTEXT), 'tmpl-' prefixed dropdown DOM id, mtsRenameTemplate / mtsDeleteTemplate handlers"
  modified:
    - "planner/views.py — extended multitrack_dashboard (~line 5754) to include owner-scoped templates queryset in render context; appended multitrack_template_rename (~line 6447) and multitrack_template_delete (~line 6502) immediately after multitrack_template_save. Net diff: +96 lines, -2."
    - "planner/urls.py — inserted two new path() entries immediately after multitrack/templates/save/. Net diff: +2 lines."
    - "planner/templates/planner/multitrack/dashboard.html — appended Templates section after sessions {% endif %} and before .mts-container closing </div>: divider + section header + grid/empty branch using new partial. Net diff: +21 lines."
    - "planner/static/planner/js/multitrack_editor.js — appended window.mtsRenameTemplate and window.mtsDeleteTemplate functions inside the existing IIFE, immediately after mtsSaveAsTemplate's closing }; and before the Capacity bar banner. Under the same Phase 3 banner Plan 03-03 added (NOT a duplicate banner). Net diff: +30 lines."

key-decisions:
  - "Defensive pre-bound `new_name = ''` outside the try block in multitrack_template_rename so the IntegrityError except-clause's f-string interpolation cannot raise UnboundLocalError if json.loads fails before new_name is set. Matches the same defensive pattern Plan 03-03 used for `name` in multitrack_template_save."
  - "Rename uses .exclude(pk=template.pk).exists() so renaming a template to the SAME name (case-sensitive no-op) is allowed and returns 200, not 409. The unique_together(created_by, name) constraint allows the same row to retain its name. This matches user expectations — clicking Rename and pressing Enter without changing the value shouldn't error."
  - "Used filter(id=template_id, created_by=request.user).first() (not get_object_or_404) for the IDOR guard in both endpoints. Returns explicit JSON 404 with {'error': 'Template not found'} for AJAX consistency. The plan's action block also showed .first() (not get_object_or_404 helper) — followed literally."
  - "Did NOT add CSS for mts-section-divider / mts-h2 / mts-section-header in this plan, per the plan's explicit instruction ('this plan ships behaviour first, CSS polish second'). Visual polish is intentionally deferred — the section is functionally complete, default Django admin styling will apply to any unrecognized classes."
  - "Templates dropdown DOM id uses string 'tmpl-{{ template.id }}' — passed as a JS string literal in onclick. mtsToggleCardMenu concatenates 'mts-card-menu-' + arg, so the resulting id is 'mts-card-menu-tmpl-N'. Session cards use raw integer N. Same getElementById path, no collision possible even when sessions and templates have the same primary key."

patterns-established:
  - "Owner-scoped mutate endpoint shape (rename/delete variant): viewer-block FIRST (before any DB read), then IDOR-guard via filter(id=..., created_by=request.user).first() returning JSON 404 (NOT 403, to avoid enumeration), then body parse + validation, then DB write. Plans touching MultitrackTemplate downstream should mirror this exact ordering."
  - "Two-grid dashboard with collision-free dropdown ids: the prefix-string approach generalises to any future N-grid dashboard (e.g. if a Phase 4 'Shared templates' grid lands beside this one, it would use 'shared-' prefix). mtsToggleCardMenu already accepts arbitrary suffix strings."
  - "CASCADE-aware delete confirmation copy: when a delete cascades to child rows (slots) but explicitly does NOT cascade further (sessions previously materialised from the template), the confirm dialog spells out BOTH sides — what gets deleted and what doesn't. Reduces support questions."

requirements-completed: [TPL-03, TPL-04]

# Metrics
duration: 3m 7s
completed: 2026-05-13
---

# Phase 03 Plan 04: Multitrack Template Dashboard List + Rename/Delete Endpoints Summary

**Engineer sees a Templates section on the multitrack dashboard listing all their owner-scoped templates, with per-card Rename and Delete actions backed by two new IDOR-guarded JSON endpoints — empty state reads "No templates yet — save one from the session editor.", viewers get 403, non-owners get 404, duplicate rename returns 409.**

## Performance

- **Duration:** 3m 7s
- **Started:** 2026-05-13T19:34:51Z
- **Completed:** 2026-05-13T19:37:58Z
- **Tasks:** 4
- **Files modified:** 4 (`planner/views.py`, `planner/urls.py`, `planner/templates/planner/multitrack/dashboard.html`, `planner/static/planner/js/multitrack_editor.js`)
- **Files created:** 1 (`planner/templates/planner/multitrack/_template_card.html`)

## Accomplishments

- `multitrack_template_rename(request, template_id)` JSON POST view appended to `planner/views.py` (~line 6447) with `@login_required` + `@require_POST` decorators, `_multitrack_viewer_block(request)` gate first (T-03-15), IDOR-guard via `MultitrackTemplate.objects.filter(id=template_id, created_by=request.user).first()` returning 404 (T-03-11), 200-char cap on new name, owner-scoped uniqueness check returning HTTP 409 with `.exclude(pk=template.pk)` so a no-op rename is allowed (T-03-13), narrow `update_fields=['name', 'updated_at']` on save, `except IntegrityError:` defensive 409, `_multitrack_logger.exception` + generic 500 (T-03-17).
- `multitrack_template_delete(request, template_id)` JSON POST view appended right after rename (~line 6502). Same viewer-block + IDOR-guard shape. CASCADE on `MultitrackTemplateSlot.template` FK handles slot rows; sessions previously created from this template are NOT affected (T-03-12).
- `multitrack_dashboard` extended (~line 5754): added owner-scoped `templates` queryset (`MultitrackTemplate.objects.filter(created_by=request.user).order_by('name')` if authenticated, else empty) and passed to render context. D-05 honored — no project filter (T-03-16).
- Two URL routes added to `planner/urls.py` immediately after `multitrack/templates/save/`: `templates/<int:template_id>/rename/` and `templates/<int:template_id>/delete/`. Both reverse correctly via `reverse('planner:multitrack_template_rename', args=[N])`.
- `_template_card.html` partial created (22 lines) cloned from `_session_card.html` with the four targeted differences: `data-template-id` attribute, no `<a>` wrap (no detail page), `'tmpl-{{ template.id }}'` string id passed to `mtsToggleCardMenu` (collision-free), no Duplicate item.
- `dashboard.html` extended: Templates section appended after the sessions `{% endif %}` and before the `.mts-container` closing `</div>`. Includes `<hr class="mts-section-divider">`, `<h2 class="mts-h2">Templates</h2>` heading + subtitle, and the grid/empty-state branch. Empty-state copy verbatim: `No templates yet — save one from the session editor.`
- `window.mtsRenameTemplate(templateId, oldName)` and `window.mtsDeleteTemplate(templateId, name)` appended inside the existing IIFE in `multitrack_editor.js`, between `mtsSaveAsTemplate` and the "Capacity bar live update" banner. Under the SAME "Template save / rename / delete (Phase 3 / v3.0)" banner Plan 03-03 added — not a duplicate. Both reuse `postJSON` (CSRF auto-attached), use `window.prompt`/`window.confirm` for UX consistency with session rename/delete, and `window.location.reload()` on success.
- `python manage.py check planner` exits 0. JS parses cleanly under Node `new Function`. Both URL routes reverse correctly.

## Task Commits

Each task was committed atomically:

1. **Task 1: views.py — rename + delete endpoints + dashboard context extension** — `dbdd1b6` (feat)
2. **Task 2: urls.py — two new URL routes** — `bb91e31` (feat)
3. **Task 3: _template_card.html partial + dashboard.html Templates section** — `2bf8958` (feat)
4. **Task 4: multitrack_editor.js — mtsRenameTemplate + mtsDeleteTemplate handlers** — `afe66db` (feat)

## Files Created/Modified

- **`planner/views.py`** (modified) — Extended `multitrack_dashboard` to compute and pass the owner-scoped `templates` queryset alongside `sessions`. Appended `multitrack_template_rename` and `multitrack_template_delete` view functions in the contiguous Phase 3 endpoint region, immediately after `multitrack_template_save`. Both new views share the same viewer-block-first / IDOR-guard / typed-error response pattern. Net +96 lines, -2.
- **`planner/urls.py`** (modified) — Two new `path()` entries directly under `multitrack/templates/save/`. URL ordering note: both new routes capture the `templates/<int:template_id>/` prefix, which is more specific than the trailing `multitrack/<int:session_id>/...` block — no ordering hazard. Net +2 lines.
- **`planner/templates/planner/multitrack/_template_card.html`** (created, 22 lines) — Cloned from `_session_card.html` with four targeted differences: `data-template-id` instead of `data-session-id`; `mts-card-link` div is NOT wrapped in an `<a href>` (templates have no detail page in v3.0); dropdown DOM id passed as the string `'tmpl-{{ template.id }}'` to `mtsToggleCardMenu` (string concatenation, collision-free with the session-card int id); Duplicate dropdown item omitted (deferred per CONTEXT).
- **`planner/templates/planner/multitrack/dashboard.html`** (modified) — New Templates section appended after the existing sessions block's `{% endif %}` and before `.mts-container` closing `</div>`. Includes `<hr class="mts-section-divider">` divider, `<h2 class="mts-h2">Templates</h2>` section heading with subtitle, and the `{% if templates %}/{% else %}` branch using the new partial. Empty-state copy exactly: `No templates yet — save one from the session editor.` Net +21 lines.
- **`planner/static/planner/js/multitrack_editor.js`** (modified) — Two new `window.mtsRenameTemplate` and `window.mtsDeleteTemplate` functions appended inside the outer IIFE, between `mtsSaveAsTemplate`'s closing `};` and the existing "Capacity bar live update" banner. Both 2-space indented to match `mtsRenameSession`. Plan 03-03's Phase 3 banner stays at line 603 — no duplicate. Net +30 lines.

## Decisions Made

- **`.exclude(pk=template.pk)` on the rename uniqueness check.** A user clicking Rename and pressing Enter without changing the value would have hit a 409 if we used the same `.exists()` shape as `multitrack_template_save`. Adding `.exclude(pk=template.pk)` makes a no-op rename a 200 — the row keeps its name, the DB-level `unique_together(created_by, name)` is happy with the same row holding the same name. The plan's action block specifies exactly this pattern.
- **404 (not 403) for non-owner template_id.** The `filter(created_by=request.user)` clause causes a non-owner template_id to resolve to `None`, returning `JsonResponse({'error': 'Template not found'}, status=404)`. This is the plan's choice and matches T-03-11's mitigation explicitly — a 403 ("wrong owner") would let an attacker enumerate template_ids by distinguishing "exists but not yours" from "doesn't exist".
- **`'tmpl-' + id` string passed to `mtsToggleCardMenu` for templates.** Session cards pass `mtsToggleCardMenu(this, {{ session.id }})` — integer arg. Templates pass `mtsToggleCardMenu(this, 'tmpl-{{ template.id }}')` — string arg with prefix. The helper concatenates `'mts-card-menu-' + arg` for `getElementById`. Both string forms work because JS coerces the int to string at concatenation. Collision avoided: a session with id=5 and a template with id=5 produce DOM ids `mts-card-menu-5` and `mts-card-menu-tmpl-5` respectively.
- **No CSS for `mts-section-divider` / `mts-h2` / `mts-section-header` in this plan.** The plan's action block explicitly says "this plan ships behaviour first, CSS polish second". Default browser/admin styles will apply. If visual polish lands later, it goes in `multitrack.css` — outside this plan's scope.
- **Body key for template rename is `new_name` (not `name`).** The session rename endpoint accepts `{name: ...}`; the template rename endpoint accepts `{new_name: ...}`. This is divergent on purpose — Plan 03-04's action block specifies the divergent key, and the JS handler sends what the view expects. Documented as a pattern in tech-stack.patterns so future readers don't "fix" it.

## Deviations from Plan

None — plan executed exactly as written. No Rule 1/2/3 auto-fixes were needed.

The five cosmetic choices noted under "Decisions Made" (defensive `new_name = ''` pre-bind, `.exclude(pk=template.pk)`, 404-not-403 for non-owner, `'tmpl-'` prefix, no CSS) are all inside the plan's stated tolerance — each is either directly specified by the plan's action block or follows verbatim from Plan 03-03's matching pattern.

## Issues Encountered

- Pre-existing `Model 'planner.audiochecklist' was already registered` `RuntimeWarning` continues to emit on every `manage.py` invocation. First flagged in plan 03-01's summary; still out of scope per executor scope-boundary rule. Does not affect `python manage.py check planner` exit code (still 0).

## Verification Block Results

| Gate | Command | Result |
|------|---------|--------|
| `check` | `./venv/bin/python manage.py check planner` | PASS — System check identified no issues (0 silenced) |
| `reverse rename` | `reverse('planner:multitrack_template_rename', args=[1])` | PASS — `/audiopatch/multitrack/templates/1/rename/` |
| `reverse delete` | `reverse('planner:multitrack_template_delete', args=[1])` | PASS — `/audiopatch/multitrack/templates/1/delete/` |
| `JS parse` | `node -e "new Function(fs.readFileSync('.../multitrack_editor.js'))"` | PASS — no syntax errors |
| Task 1 rename view | `grep -q "def multitrack_template_rename(request, template_id):"` | PASS |
| Task 1 delete view | `grep -q "def multitrack_template_delete(request, template_id):"` | PASS |
| Task 1 dashboard context | `grep -q "'templates': templates,"` | PASS |
| Task 1 owner-scoping | `grep -q "MultitrackTemplate.objects.filter(created_by=request.user)"` | PASS |
| Task 1 IDOR guard | `grep -q "id=template_id, created_by=request.user"` | PASS (two matches) |
| Task 1 viewer block | `grep -q "_multitrack_viewer_block(request)"` | PASS (counts >= 5 across views.py) |
| Task 1 409 | `grep -q "status=409"` | PASS |
| Task 1 IntegrityError | `grep -q "except IntegrityError:"` | PASS |
| Task 1 rename log | `grep -q "_multitrack_logger.exception('multitrack_template_rename failed')"` | PASS |
| Task 1 delete log | `grep -q "_multitrack_logger.exception('multitrack_template_delete failed')"` | PASS |
| Task 1 narrow save | `grep -q "template.save(update_fields=\['name', 'updated_at'\])"` | PASS |
| Task 1 delete call | `grep -q "template.delete()"` | PASS |
| Task 1 no project scope | `! grep -A 25 "def multitrack_template_rename" \| grep -q "current_project"` | PASS |
| Task 1 no project scope | `! grep -A 25 "def multitrack_template_delete" \| grep -q "current_project"` | PASS |
| Task 2 rename route name | `grep -q "name='multitrack_template_rename'"` | PASS |
| Task 2 delete route name | `grep -q "name='multitrack_template_delete'"` | PASS |
| Task 2 rename path | `grep -q "multitrack/templates/<int:template_id>/rename/"` | PASS |
| Task 2 delete path | `grep -q "multitrack/templates/<int:template_id>/delete/"` | PASS |
| Task 2 save untouched | `grep -q "name='multitrack_template_save'"` | PASS |
| Task 3 partial exists | `test -f .../_template_card.html` | PASS |
| Task 3 data attribute | `grep -q "data-template-id"` | PASS |
| Task 3 tmpl- prefix | `grep -q "mtsToggleCardMenu(this, 'tmpl-"` | PASS |
| Task 3 no Duplicate | `! grep -q "mtsDuplicate" _template_card.html` | PASS |
| Task 3 no anchor | `! grep -q '<a class="mts-card-link" href='` | PASS |
| Task 3 dashboard include | `grep -q "_template_card.html"` | PASS |
| Task 3 if templates | `grep -q "{% if templates %}"` | PASS |
| Task 3 empty copy | `grep -q "No templates yet — save one from the session editor"` | PASS |
| Task 3 divider | `grep -q "mts-section-divider"` | PASS |
| Task 4 rename fn | `grep -q "window.mtsRenameTemplate = function (templateId, oldName)"` | PASS |
| Task 4 delete fn | `grep -q "window.mtsDeleteTemplate = function (templateId, name)"` | PASS |
| Task 4 rename URL | `grep -q "/audiopatch/multitrack/templates/' + templateId + '/rename/"` | PASS |
| Task 4 delete URL | `grep -q "/audiopatch/multitrack/templates/' + templateId + '/delete/"` | PASS |
| Task 4 body shape | `grep -q "{ new_name: newName.trim() }"` | PASS |
| Task 4 cascade copy | `grep -q "Sessions previously created from this template are not affected"` | PASS |
| Task 4 banner once | `[ $(grep -c "Template save / rename / delete (Phase 3 / v3.0)") -eq 1 ]` | PASS |
| Task 4 no saveAs dup | `[ $(grep -c "mtsSaveAsTemplate = function") -eq 1 ]` | PASS |
| Task 4 session rename intact | `grep -q "window.mtsRenameSession = function (sessionId, oldName)"` | PASS |

## Threat Register Compliance

Mitigations declared in the plan's `<threat_model>` and how they landed:

- **T-03-11 Tampering / rename IDOR (mitigate):** `MultitrackTemplate.objects.filter(id=template_id, created_by=request.user).first()` returns `None` for any template not owned by the authenticated user → JSON 404 (NOT 403 — avoids template_id enumeration). Verified by grep. ✓
- **T-03-12 Tampering / delete IDOR (mitigate):** Same IDOR guard. CASCADE only fires AFTER the owner check passes — non-owners cannot trigger cascading delete on someone else's slots. Verified by grep. ✓
- **T-03-13 Tampering / rename name conflict (mitigate):** `.exclude(pk=template.pk).exists()` returns HTTP 409 with friendly message; `except IntegrityError:` re-emits the same 409 if the DB-level `unique_together(created_by, name)` constraint catches a race. Verified by grep + check. ✓
- **T-03-14 Spoofing / CSRF (mitigate):** Existing `postJSON` helper reads `[name=csrfmiddlewaretoken]` and sets `X-CSRFToken` header. Hidden `{% csrf_token %}` form already present in `dashboard.html:53`. No new CSRF wiring needed — verified by source inspection. ✓
- **T-03-15 EoP / viewer bypass (mitigate):** `_multitrack_viewer_block(request)` called as the FIRST statement inside both new endpoints; viewers get HTTP 403 before any DB query runs. Verified by grep + ordering check. ✓
- **T-03-16 Info Disclosure / dashboard leak (mitigate):** `multitrack_dashboard` filters `MultitrackTemplate.objects.filter(created_by=request.user)` — no `Q(...) | Q(...)`, no project-scoping. D-05 comment block above the queryset documents the intent. Verified by grep. ✓
- **T-03-17 Info Disclosure / 500 stack trace (mitigate):** Both endpoints use `except Exception: _multitrack_logger.exception('...failed'); return JsonResponse({'error': 'Server error.'}, status=500)`. No `str(e)` in the new view bodies. Verified by grep. ✓
- **T-03-18 DoS / many templates (accept):** No rate limit; bounded by `unique_together(created_by, name)` (forces distinct names per user). Documented in plan as accepted risk for solo-dev SaaS. ✓

## Next Phase Readiness

- The dashboard now functions end-to-end for the template lifecycle: Plan 03-03 lets the engineer SAVE templates from the editor; Plan 03-04 lets them SEE, RENAME, and DELETE templates from the dashboard.
- Plan 03-05 (new-session apply path + form `template` dropdown) is unblocked. The Templates section gives the engineer a place to verify template creation visually before the apply path is built, which makes 03-05's smoke testing easier.
- No new external services, env vars, or migrations introduced. Railway deploy is no-op for infrastructure.
- Manual smoke test (optional per plan verification step 3): `python manage.py runserver` → log in → visit `/audiopatch/multitrack/` → confirm "Templates" section heading below sessions grid with divider; click ⋯ on a template card → confirm Rename + Delete options (NO Duplicate); test rename + delete flows end to end.

## Self-Check: PASSED

Verified post-write:

- `planner/views.py` contains `def multitrack_template_rename(request, template_id):` (grep PASS) and `def multitrack_template_delete(request, template_id):` (grep PASS). ✓
- `planner/urls.py` contains both new path entries and reverses cleanly to `/audiopatch/multitrack/templates/1/rename/` + `/audiopatch/multitrack/templates/1/delete/`. ✓
- `planner/templates/planner/multitrack/_template_card.html` exists with `data-template-id` + `mtsRenameTemplate` + `mtsDeleteTemplate` + `tmpl-` prefix; NO Duplicate, NO anchor wrap. ✓
- `planner/templates/planner/multitrack/dashboard.html` contains the `{% include "planner/multitrack/_template_card.html" %}` line + `{% if templates %}` branch + `mts-section-divider` + exact empty-state copy. ✓
- `planner/static/planner/js/multitrack_editor.js` contains `window.mtsRenameTemplate` + `window.mtsDeleteTemplate` inside the IIFE under the SINGLE Phase 3 banner; `mtsSaveAsTemplate = function` appears exactly once. ✓
- Commit `dbdd1b6` exists in `git log --oneline`. ✓
- Commit `bb91e31` exists in `git log --oneline`. ✓
- Commit `2bf8958` exists in `git log --oneline`. ✓
- Commit `afe66db` exists in `git log --oneline`. ✓
- `python manage.py check planner` exits 0. ✓
- JS parses cleanly under Node `new Function`. ✓

---
*Phase: 03-multitrack-templates*
*Completed: 2026-05-13*
