---
phase: 03-multitrack-templates
plan: 05
subsystem: views
tags: [django, forms, views, frontend, multitrack, templates, apply, javascript]

# Dependency graph
requires:
  - phase: 03-multitrack-templates
    provides: "MultitrackTemplate.apply_to_session(session) → (mapped, skipped, summary) from plan 03-01; multitrack_template_save / mtsSaveAsTemplate + 'Template save / rename / delete (Phase 3 / v3.0)' banner in multitrack_editor.js from plan 03-03; mtsRenameTemplate + mtsDeleteTemplate from plan 03-04"
  - phase: 01-core-sessions-track-editor-reaper-export
    provides: "MultitrackSessionForm class shape (class Meta + __init__-scoped console queryset); multitrack_create_view body (form.is_valid → form.save → redirect); new_session.html form-row layout + radio-group blocks; messages framework already imported in views.py (line 18); .mts-form-row / .mts-help-text / .mts-field-error CSS classes; messages template block (rendered on editor page after redirect via admin/base_site.html)"
provides:
  - "MultitrackSessionForm.template — owner-scoped ModelChoiceField (queryset class-default MultitrackTemplate.objects.none(), assigned per-instance in __init__ to MultitrackTemplate.objects.filter(created_by=request.user).order_by('name')). NOT in Meta.fields — consumed by view via cleaned_data['template']."
  - "multitrack_create_view template-apply branch — when form.cleaned_data['template'] is not None, calls template.apply_to_session(session) after form.save() and surfaces (mapped, skipped, summary) via messages.info with three D-10/D-13 branches (mixed/all-mapped/empty)"
  - "new_session.html template dropdown — hand-rolled <select> (NOT {{ form.template }}) at the top of the form, guarded by {% if form.template.field.queryset.exists %}, each <option> carries data-target-daw / data-feed-source / data-track-order-mode / data-recorder-capacity / data-notes attributes for client-side auto-populate"
  - "window.mtsApplyTemplateToForm(selectEl) — pure-DOM auto-populate function (no AJAX) appended to multitrack_editor.js inside the existing IIFE. Reads selected <option>'s dataset.* and sets the matching radio groups (with bubbling change events) + recorder_capacity input + notes textarea. Silent no-op on '— None —' selection."
  - "<script src='...multitrack_editor.js' defer> tag in new_session.html — Phase 1 didn't load this file on the new-session page; Phase 3 adds it so mtsApplyTemplateToForm is available to the dropdown's onchange handler."
affects: [future phases that touch the new-session form or multitrack dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Owner-scoped form field queryset assigned in __init__ (per-instance), NOT at class level — defaults to .none() at class declaration; closes the IDOR vector that would expose every user's templates if the queryset were class-level"
    - "Form-level helper field NOT in Meta.fields — `template` is consumed by the view via form.cleaned_data after form.save() returns the new session; MultitrackSession has no `template` FK so adding to Meta.fields would crash form generation (RESEARCH Pitfall 7)"
    - "Hand-rolled <select> with data-* attributes per option for client-side auto-populate — Django's default Select widget renders bare <option value='N'>name</option> with no hook for data attrs, so the template iterates form.template.field.queryset directly. Preserves form parsing via {{ form.template.html_name }}."
    - "messages.info banner pattern for template apply — three branches (D-13 empty, all-mapped short, D-10 mixed mapped+skipped) all use Python f-string formatting; skipped_summary is pre-built by Plan 03-01's _summarise_skipped_slots so the view does NOT re-build it"
    - "Vanilla JS auto-populate with bubbling 'change' event dispatch on radio inputs — ensures any future onChange listeners (live validation, etc.) fire as if the engineer clicked the radio"

key-files:
  created: []
  modified:
    - "planner/forms.py — added MultitrackTemplate to the existing .models import line (top of file); inserted class-level `template = forms.ModelChoiceField(queryset=MultitrackTemplate.objects.none(), required=False, ...)` between Meta and __init__; appended per-instance owner-scoping block to __init__ after the existing D-13 console scoping block. Net +26 lines, -1."
    - "planner/views.py — extended multitrack_create_view to read form.cleaned_data['template'] after form.save(), call template.apply_to_session(session), and emit messages.info with three branches (D-13 empty / all-mapped / D-10 mixed). Net +38 lines, -1."
    - "planner/templates/planner/multitrack/new_session.html — inserted template dropdown form-row between {% if form.errors %} and the Name row, guarded by {% if form.template.field.queryset.exists %} (hides dropdown when user has no templates); added <script src='...multitrack_editor.js' defer> tag at end of {% block content %}. Net +24 lines."
    - "planner/static/planner/js/multitrack_editor.js — appended window.mtsApplyTemplateToForm function inside the existing IIFE, after mtsDeleteTemplate's closing }; and before the Capacity bar banner. Under a new 'New-session form: auto-populate fields from picked template (D-11)' banner. Net +48 lines."

key-decisions:
  - "Pre-instance __init__ assignment for the template queryset (NOT class-level): class declaration uses .none() as the IDOR-safe default; __init__ overrides per request to filter(created_by=request.user). A class-level queryset=.objects.all() would let every user see every other user's templates in the dropdown — closes RESEARCH Pitfall 6."
  - "Hand-rolled <select> instead of {{ form.template }}: needed to attach data-* attributes per <option>. Form parsing still works because name={{ form.template.html_name }} matches Django's parser expectations."
  - "data-recorder-capacity uses |default_if_none:'' — when the template has no recorder_capacity set, the data attribute is an empty string. The JS handler clears the input on selection (RESEARCH recommendation 2 — auto-populate everything, including the empty case)."
  - "data-notes uses |escape — Django's escape filter quotes <, >, &, \", ' so the data-* attribute string is HTML-safe. The JS assigns to textarea.value (NOT innerHTML), closing both layers of the XSS surface."
  - "Defensive onchange handler: typeof mtsApplyTemplateToForm === 'function' guard means the form still submits cleanly even if multitrack_editor.js fails to load (no auto-populate, but the dropdown still saves)."
  - "messages.info uses three branches rather than a single fall-through. The all-mapped branch (skipped==0 && total>0) is the RESEARCH-recommended polish: 'Applied template X — N of N slots mapped.' without the noisy '; 0 skipped' suffix."
  - "No re-fetch of the template in the view body: form.cleaned_data['template'] is already validated against the owner-scoped queryset by Django's ModelChoiceField machinery. Doing MultitrackTemplate.objects.get(pk=...) in the view would bypass the form's queryset and re-open the IDOR vector."

patterns-established:
  - "Owner-scoped ModelChoiceField with per-instance __init__ assignment — IDOR-safe default (.none()) + per-request scoping. Applies to any future form fields exposing user-owned cross-project resources."
  - "View-level apply call after form.save() with messages.info banner — generalises to any future 'pick a thing and apply it to the new row' workflow (e.g. session presets, console templates). The (mapped, skipped, summary) 3-tuple return shape is the canonical apply contract."
  - "data-* attribute auto-populate without AJAX — the chosen-option's dataset carries all metadata needed to fill the form; pure DOM. Faster than an AJAX round-trip and works offline. Pattern applies to any future template-style pick-and-fill UX."
  - "Bubbling change event dispatch on programmatically-set radios — ensures the rest of the form behaves as if the engineer clicked. Critical for any future radio-driven validation or conditional UI."

requirements-completed: [TPL-02, TPL-04]

# Metrics
duration: 3m 17s
completed: 2026-05-13
---

# Phase 03 Plan 05: Apply-Template Wiring on New-Session Form Summary

**Owner-scoped template ModelChoiceField on MultitrackSessionForm, multitrack_create_view extension that calls template.apply_to_session(session) after form.save() and surfaces a three-branch messages.info banner (D-10/D-13), plus a hand-rolled <select> in new_session.html with data-* attributes per option that vanilla JS reads to auto-populate target_daw / feed_source / track_order_mode / recorder_capacity / notes without any AJAX round-trip.**

## Performance

- **Duration:** 3m 17s
- **Started:** 2026-05-13T19:42:54Z
- **Completed:** 2026-05-13T19:46:11Z
- **Tasks:** 3
- **Files modified:** 4 (`planner/forms.py`, `planner/views.py`, `planner/templates/planner/multitrack/new_session.html`, `planner/static/planner/js/multitrack_editor.js`)

## Accomplishments

- `MultitrackSessionForm.template` ModelChoiceField added: class-level field declaration with `queryset=MultitrackTemplate.objects.none()` (IDOR-safe default) + `empty_label='— None —'` + `label='Start from template (optional)'` + `help_text='Picking a template pre-fills the fields below.'`. NOT in `Meta.fields` (MultitrackSession has no `template` FK).
- `__init__` owner-scoping block: `self.fields['template'].queryset = MultitrackTemplate.objects.filter(created_by=request.user).order_by('name')` when `request.user.is_authenticated`, else `.none()`. Per-instance assignment closes the IDOR vector (T-03-19 mitigation).
- `multitrack_create_view` extended (~line 6003): reads `form.cleaned_data.get('template')` after `form.save()`, calls `template.apply_to_session(session)` if non-None, unpacks the `(mapped, skipped, skipped_summary)` 3-tuple, and emits one of three `messages.info` branches:
  - D-13 (empty template, total==0): *"Applied template '{name}' — metadata seeded; no tracks in template."*
  - All-mapped (skipped==0): *"Applied template '{name}' — {mapped} of {total} slots mapped."*
  - D-10 mixed (skipped>0): *"Applied template '{name}' — {mapped} of {total} slots mapped; {skipped} skipped ({skipped_summary})."*
- `new_session.html` template dropdown: hand-rolled `<select>` form-row inserted between the `{% if form.errors %}` block and the Name row, guarded by `{% if form.template.field.queryset.exists %}` so the dropdown hides when the user has no templates yet. Each `<option>` carries the template's metadata as data-* attributes: `data-target-daw`, `data-feed-source`, `data-track-order-mode`, `data-recorder-capacity` (uses `|default_if_none:''`), `data-notes` (uses `|escape` for XSS safety). Inline `onchange="if (typeof mtsApplyTemplateToForm === 'function') mtsApplyTemplateToForm(this);"` handler is defensive — form still works if JS fails to load.
- `<script src="{% static 'planner/js/multitrack_editor.js' %}" defer></script>` tag appended at end of `{% block content %}` in new_session.html (Phase 1 didn't load this file on the new-session page; Plan 03-05 adds it so mtsApplyTemplateToForm is available).
- `window.mtsApplyTemplateToForm` appended to `multitrack_editor.js` inside the existing IIFE, between `mtsDeleteTemplate` and the "Capacity bar live update" banner. Pure DOM (no AJAX): reads `selectEl.options[selectEl.selectedIndex].dataset.*` and sets radio groups (with bubbling 'change' events for any future onChange listeners) + `recorder_capacity` input + `notes` textarea. Silent no-op on "— None —" selection so the engineer doesn't lose in-progress typing.
- All defensive selectors are if-guarded (`if (radio)`, `if (capacityInput)`, `if (notesField)`) — function is forward-compatible with form-field changes.
- `python manage.py check planner` exits 0. JS parses cleanly under Node's `new Function`. Form import sanity check returns `True 0` (template field present; queryset is none() when no request passed). View source contains `apply_to_session`. Runtime banner format-string output verified for both D-10 and D-13 wording verbatim.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add owner-scoped 'template' ModelChoiceField to MultitrackSessionForm in planner/forms.py** — `0cbbc78` (feat)
2. **Task 2: Extend multitrack_create_view in planner/views.py to apply chosen template + emit messages.info banner** — `5467beb` (feat)
3. **Task 3: Add template dropdown form-row + inline JS to new_session.html and append window.mtsApplyTemplateToForm to multitrack_editor.js** — `5f3df6c` (feat)

## Files Created/Modified

- **`planner/forms.py`** (modified) — Added `MultitrackTemplate` to the existing `from .models import Console, MultitrackSession` line (top of file). Inserted class-level `template = forms.ModelChoiceField(queryset=MultitrackTemplate.objects.none(), required=False, empty_label='— None —', label='Start from template (optional)', help_text='Picking a template pre-fills the fields below.')` between the `Meta` inner class and `__init__`. Appended an owner-scoping block to `__init__` AFTER the existing D-13 console scoping block: per-instance assignment of `self.fields['template'].queryset` to `MultitrackTemplate.objects.filter(created_by=request.user).order_by('name')` when authenticated, else `.none()`. Net +26 lines, -1.
- **`planner/views.py`** (modified) — Extended `multitrack_create_view` docstring to document the Phase 3 extension. Inserted apply branch between `session = form.save()` and `return redirect(...)`: read `form.cleaned_data.get('template')`, if non-None call `template.apply_to_session(session)`, then emit one of three `messages.info` branches based on `total == mapped + skipped` (D-13 empty), `skipped == 0` (all-mapped polish), or D-10 mixed. Net +38 lines, -1.
- **`planner/templates/planner/multitrack/new_session.html`** (modified) — Inserted template dropdown form-row between the `{% if form.errors %}` block (line 27) and the Name row (line 29). Hand-rolled `<select>` (NOT `{{ form.template }}`) so each `<option>` can carry data-* attributes for the auto-populate JS. Guarded by `{% if form.template.field.queryset.exists %}` so the dropdown hides when the user has no templates. Appended `<script src="{% static 'planner/js/multitrack_editor.js' %}" defer></script>` immediately before `{% endblock %}`. Net +24 lines.
- **`planner/static/planner/js/multitrack_editor.js`** (modified) — Appended `window.mtsApplyTemplateToForm = function (selectEl) { ... }` inside the existing outer IIFE, between `mtsDeleteTemplate`'s closing `};` (line 663) and the "Capacity bar live update" banner. Function reads the selected `<option>`'s `dataset.*` and sets matching form fields. Under a new section banner: `// New-session form: auto-populate fields from picked template (D-11)`. Net +48 lines.

## Decisions Made

- **Per-instance queryset assignment in `__init__` (NOT class-level).** This is the IDOR-closing line per RESEARCH Pitfall 6. A class-level `ModelChoiceField(queryset=MultitrackTemplate.objects.all())` would let every user see every other user's templates in the dropdown — a textbook IDOR. The class-level default is `.objects.none()`, which fails closed if `__init__` ever skips the assignment (e.g. anonymous form construction).
- **Hand-rolled `<select>` with explicit `<option>` iteration over `form.template.field.queryset`.** Django's default `Select` widget renders bare `<option value="N">name</option>` with no hook for data-* attributes. To wire up the auto-populate (D-11) without an AJAX round-trip, each option needs its template's metadata inline. The `name="{{ form.template.html_name }}"` attribute keeps Django's form parser happy so the submitted value flows through to `cleaned_data['template']`.
- **`{% if form.template.field.queryset.exists %}` outer guard.** Hides the dropdown entirely when the user has no templates yet. Avoids a useless "— None —"-only dropdown on the first-ever new-session form. The exact behavior is: first-time users see the form unchanged from Phase 1; once they save their first template via Plan 03-03, the dropdown appears.
- **Three-branch banner with all-mapped polish.** The plan's `<action>` block specifies three `messages.info` branches: D-13 empty (no tracks), all-mapped (skipped==0, no noisy "; 0 skipped" clause), and D-10 mixed. The all-mapped polish is RESEARCH-recommended; without it, the D-10 format string would render "16 of 16 slots mapped; 0 skipped ()." which is grammatically awkward. The three-branch split also satisfies the plan's `grep -c "messages.info(" >= 3` acceptance criterion.
- **No re-fetch of the template in the view body.** `form.cleaned_data['template']` is the already-validated instance Django's ModelChoiceField returned after running the submitted value through the owner-scoped queryset. Doing `MultitrackTemplate.objects.get(pk=request.POST['template'])` in the view body would bypass the queryset and re-open the IDOR vector — `! grep -q "MultitrackTemplate.objects.get(pk=" planner/views.py` confirms absence.
- **Defensive `typeof ... === 'function'` guard on the inline onchange.** If `multitrack_editor.js` fails to load (CDN hiccup, missing static collect, etc.), the dropdown still submits cleanly. The form just won't auto-populate — engineer gets the empty form and types as before. Graceful degradation.
- **`data-recorder-capacity="{{ tpl.recorder_capacity|default_if_none:'' }}"` — active-clear semantics.** When the template has no `recorder_capacity` set, the data attribute renders as an empty string. The JS handler sets `capacityInput.value = opt.dataset.recorderCapacity || ''` — empty string clears the input. Per "Claude's Discretion" in CONTEXT D-11: "default behavior is auto-populate everything" — applies to the empty-capacity case too.
- **`data-notes="{{ tpl.notes|escape }}"` — closes T-03-23 (DOM-XSS via data-attr breakout).** Django's `escape` filter quotes `<`, `>`, `&`, `"`, `'` so the attribute string is HTML-safe. The JS reads `opt.dataset.notes` (string) and assigns to `textarea.value` — `.value` never parses HTML, so no script execution path exists even if escape were bypassed.
- **Bubbling `Event('change', { bubbles: true })` dispatch on programmatically-set radios.** Ensures any future onChange listeners (live validation, conditional UI, analytics) fire as if the engineer clicked the radio button. Without bubbling, `radio.checked = true` is silent — the checked state changes but no event fires.

## Deviations from Plan

None — plan executed exactly as written. No Rule 1/2/3 auto-fixes were needed.

The eight decisions noted above are all inside the plan's stated tolerance — each is either directly specified by the plan's `<action>` block (per-instance queryset, hand-rolled select, queryset.exists guard, three branches, |escape, |default_if_none:'', bubbling change event) or follows the plan's anti-pattern reminders (no re-fetch, defensive `typeof` guard).

## Issues Encountered

- The plan's success-criteria checklist includes `grep -q "Start from template" planner/templates/.../new_session.html`. The literal string "Start from template (optional)" is the form field's `label` attribute (set in `forms.py`), which the template renders server-side via `{{ form.template.label }}` — the literal string does NOT appear in `new_session.html`. The plan's Task 3 acceptance criterion explicitly accounts for this: *"accept if the form `label` is rendered server-side"*. Verified at runtime: `MultitrackSessionForm().fields['template'].label` evaluates to `'Start from template (optional)'`. Not a code defect — a phrasing nuance in the prompt-level success criterion.
- The plan's success-criteria checklist includes `grep -q "of {total} slots mapped; {skipped} skipped" planner/views.py`. The literal string spans TWO concatenated f-string lines (`f"... mapped; "` + `f"{skipped} skipped (...)"`) — Python concatenates these at compile time into the runtime string, but `grep -q` doesn't see across newlines. The plan's Task 2 `<action>` block uses the same multi-line concatenation pattern, so this is the plan's intended shape. Verified at runtime: f-string concatenation produces `"... 4 of 20 slots mapped; 4 skipped (matrix 9, 10, 11, 12 not present on this console)."` verbatim. Not a code defect — a multi-line/regex nuance in the prompt-level success criterion.
- Pre-existing `Model 'planner.audiochecklist' was already registered` `RuntimeWarning` continues to emit on every `manage.py` invocation. First flagged in plan 03-01's summary; still out of scope per executor scope-boundary rule. Does not affect `python manage.py check planner` exit code (still 0).

## Verification Block Results

| Gate | Command | Result |
|------|---------|--------|
| `check` | `./venv/bin/python manage.py check planner` | PASS — System check identified no issues (0 silenced) |
| `form sanity` | `MultitrackSessionForm(); print('template' in f.fields, f.fields['template'].queryset.count())` | PASS — `True 0` (field present, queryset is .none() with no request) |
| `view sanity` | `inspect.getsource(multitrack_create_view) contains 'apply_to_session'` | PASS — `True` |
| `JS parse` | `node -e "new Function(fs.readFileSync('...multitrack_editor.js'))"` | PASS — no syntax errors |
| `label runtime` | `MultitrackSessionForm().fields['template'].label` | PASS — `'Start from template (optional)'` |
| `D-10 runtime` | runtime f-string concat with mapped=16, total=20, skipped=4 | PASS — `"Applied template 'X' — 16 of 20 slots mapped; 4 skipped (matrix 9, 10, 11, 12 not present on this console)."` |
| `D-13 runtime` | runtime f-string concat with mapped=0, total=0 | PASS — `"Applied template 'X' — metadata seeded; no tracks in template."` |
| Task 1 import | `grep -q "from .models import Console, MultitrackSession, MultitrackTemplate" planner/forms.py` | PASS |
| Task 1 field decl | `grep -q "template = forms.ModelChoiceField(" planner/forms.py` | PASS |
| Task 1 none default | `grep -q "queryset=MultitrackTemplate.objects.none()," planner/forms.py` | PASS |
| Task 1 empty_label | `grep -q "empty_label='— None —'" planner/forms.py` | PASS |
| Task 1 label | `grep -q "label='Start from template (optional)'" planner/forms.py` | PASS |
| Task 1 owner-scoping | `grep -q "self.fields['template'].queryset = MultitrackTemplate.objects.filter(" planner/forms.py` | PASS |
| Task 1 created_by | `grep -q "created_by=request.user" planner/forms.py` | PASS |
| Task 1 auth gate | `grep -q "if request is not None and request.user.is_authenticated:" planner/forms.py` | PASS |
| Task 1 not in Meta.fields | `! ( grep -B 5 "fields = \[" planner/forms.py \| grep -q "'template'" )` (subshell-grouped negation) | PASS |
| Task 2 cleaned_data | `grep -q "template = form.cleaned_data.get('template')" planner/views.py` | PASS |
| Task 2 apply call | `grep -q "template.apply_to_session(session)" planner/views.py` | PASS |
| Task 2 tuple unpack | `grep -q "mapped, skipped, skipped_summary = template.apply_to_session(session)" planner/views.py` | PASS |
| Task 2 D-13 copy | `grep -q "metadata seeded; no tracks in template" planner/views.py` | PASS |
| Task 2 banner count | `grep -c "messages.info(" planner/views.py` | PASS — 3 |
| Task 2 no re-fetch | `! grep -q "MultitrackTemplate.objects.get(pk=" planner/views.py` | PASS |
| Task 3 queryset.exists guard | `grep -q "{% if form.template.field.queryset.exists %}" new_session.html` | PASS |
| Task 3 data-target-daw | `grep -q 'data-target-daw="{{ tpl.target_daw }}"' new_session.html` | PASS |
| Task 3 data-feed-source | `grep -q 'data-feed-source="{{ tpl.feed_source }}"' new_session.html` | PASS |
| Task 3 data-track-order-mode | `grep -q 'data-track-order-mode="{{ tpl.track_order_mode }}"' new_session.html` | PASS |
| Task 3 data-recorder-capacity | `grep -q 'data-recorder-capacity=' new_session.html` | PASS |
| Task 3 data-notes escape | `grep -q 'data-notes="{{ tpl.notes\|escape }}"' new_session.html` | PASS |
| Task 3 onchange handler | `grep -q "mtsApplyTemplateToForm(this)" new_session.html` | PASS |
| Task 3 script tag | `grep -q "{% static 'planner/js/multitrack_editor.js' %}" new_session.html` | PASS |
| Task 3 fn signature | `grep -q "window.mtsApplyTemplateToForm = function (selectEl)" multitrack_editor.js` | PASS |
| Task 3 targetDaw access | `grep -q "opt.dataset.targetDaw" multitrack_editor.js` | PASS |
| Task 3 feedSource access | `grep -q "opt.dataset.feedSource" multitrack_editor.js` | PASS |
| Task 3 trackOrderMode access | `grep -q "opt.dataset.trackOrderMode" multitrack_editor.js` | PASS |
| Task 3 bubbling change | `grep -q "Event('change', { bubbles: true })" multitrack_editor.js` | PASS |
| Task 3 no AJAX in new fn | `! ( grep -A 50 "window.mtsApplyTemplateToForm" multitrack_editor.js \| grep -q "postJSON\|fetch(" )` | PASS |

## Threat Register Compliance

Mitigations declared in the plan's `<threat_model>` and how they landed:

- **T-03-19 Spoofing / engineer A picks engineer B's template via crafted POST (mitigate):** `MultitrackSessionForm.__init__` scopes `self.fields['template'].queryset = MultitrackTemplate.objects.filter(created_by=request.user)`. Django's ModelChoiceField validates the submitted value against this queryset — a non-owner template_id raises ValidationError. Class-level default is `.none()` so a misconfigured request (no request.user) cannot leak. Verified by grep + manual reading. ✓
- **T-03-20 Tampering / cross-tenant template apply (mitigate):** `multitrack_create_view` only calls `apply_to_session` on the JUST-created session, whose `project` is `request.current_project` (set in Phase 1's `MultitrackSessionForm.save()`). Both anchors (form template ownership + session project) must hold. Apply call sits AFTER `session = form.save()` and reads `form.cleaned_data` (the validated instance). ✓
- **T-03-21 Tampering / orphan form with no request (mitigate):** `__init__` defaults the queryset to `MultitrackTemplate.objects.none()` when `request is None or not request.user.is_authenticated`. Anonymous form construction yields an empty queryset; submitted template_id fails validation. Verified by `MultitrackSessionForm()` returning `template field queryset count = 0`. ✓
- **T-03-22 Information Disclosure / dropdown leaks other-tenant template names (mitigate):** The `__init__` queryset filter closes both the form-validation AND the rendering vector. `{% for tpl in form.template.field.queryset %}` only enumerates the current user's templates. No other user's template names, target_daw, notes, etc. ever reach the response HTML. Verified by reading new_session.html markup. ✓
- **T-03-23 Information Disclosure / data-notes breakout → DOM-XSS (mitigate):** Template renders `data-notes="{{ tpl.notes|escape }}"` — Django's `escape` filter quotes `<`, `>`, `&`, `"`, `'`. The JS reads `opt.dataset.notes` (string) and assigns to `textarea.value` (never `innerHTML`). Verified by grep `grep -q 'data-notes="{{ tpl.notes|escape }}"'`. ✓
- **T-03-24 Tampering / partial apply leaves session in half-populated state (accept):** Plan 03-01's `apply_to_session` uses a single `bulk_create`, wrapped in Django's implicit transaction. No `@transaction.atomic` on `form.save() + apply` — D-10 prefers skip-and-summarise over abort. If apply ever crashes, session exists with zero tracks, engineer sees the empty editor and re-applies. Low likelihood, low blast radius. ✓
- **T-03-25 Elevation of Privilege / viewer applies a template (mitigate):** `multitrack_create_view` decorated with `@staff_member_required` (Phase 1, unchanged). Form queryset-scoping (T-03-19) is the secondary anchor — even if @staff_member_required ever loosens, cross-tenant template access is still blocked. ✓

## Next Phase Readiness

- Plan 03-05 closes the Phase 3 TPL-02 loop: engineer can now (1) save a template from the editor (Plan 03-03), (2) see / rename / delete templates on the dashboard (Plan 03-04), and (3) create a new session from a template with auto-populated metadata + a banner reporting mapped/skipped slots (Plan 03-05). Phase 3 is feature-complete.
- Manual smoke (optional, requires beta-test data): save a template from a QL5 session with input slots 1-8 + matrix slots 1-12; create a new session on a CL5 (8 matrices); pick the template — form auto-populates; submit — editor loads with input tracks + matrix 1-8 only, banner reads `Applied template '<name>' — 16 of 20 slots mapped; 4 skipped (matrix 9, 10, 11, 12 not present on this console).`
- Empty-template smoke (D-13): save a metadata-only template (zero enabled tracks) → apply to a new session → banner reads `Applied template '<name>' — metadata seeded; no tracks in template.` and the editor opens with the picker auto-open per Phase 1 D-12 (already verified by Phase 1's `multitrack_editor` view — the picker auto-opens on zero-track sessions).
- IDOR smoke (optional, requires two users): User A saves template T1; user B opens `/audiopatch/multitrack/new/` → dropdown does NOT list T1; user B crafts `POST` with `template=<T1's id>` → form is invalid (`Select a valid choice. That choice is not one of the available choices.`) and apply does NOT fire.
- No new external services, env vars, or migrations introduced. Railway deploy is no-op for infrastructure.
- Phase 3 is complete — ROADMAP.md updates Phase 3 → 5/5 plans, Phase status → DONE.

## Self-Check: PASSED

Verified post-write:

- `planner/forms.py` contains `from .models import Console, MultitrackSession, MultitrackTemplate` (top of file) + class-level `template = forms.ModelChoiceField(queryset=MultitrackTemplate.objects.none(), ...)` + `__init__` block with `self.fields['template'].queryset = MultitrackTemplate.objects.filter(created_by=request.user).order_by('name')`. ✓
- `planner/views.py` `multitrack_create_view` contains `template = form.cleaned_data.get('template')` + `mapped, skipped, skipped_summary = template.apply_to_session(session)` + three `messages.info` branches (D-13 empty, all-mapped, D-10 mixed). ✓
- `planner/templates/planner/multitrack/new_session.html` contains the template dropdown form-row (guarded by `{% if form.template.field.queryset.exists %}`), data-* attributes per option, the `mtsApplyTemplateToForm(this)` onchange handler, and the `<script src="...multitrack_editor.js" defer>` tag. ✓
- `planner/static/planner/js/multitrack_editor.js` contains `window.mtsApplyTemplateToForm = function (selectEl) { ... }` inside the existing IIFE with `opt.dataset.targetDaw/feedSource/trackOrderMode/recorderCapacity/notes` reads, bubbling `Event('change', { bubbles: true })` dispatch on radios, no AJAX (no `postJSON`/`fetch(`). ✓
- Commit `0cbbc78` exists in `git log --oneline`. ✓
- Commit `5467beb` exists in `git log --oneline`. ✓
- Commit `5f3df6c` exists in `git log --oneline`. ✓
- `python manage.py check planner` exits 0. ✓
- JS parses cleanly under Node `new Function`. ✓

---
*Phase: 03-multitrack-templates*
*Completed: 2026-05-13*
