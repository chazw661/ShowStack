---
phase: 03-multitrack-templates
reviewed: 2026-05-13T19:30:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - planner/admin.py
  - planner/admin_ordering.py
  - planner/forms.py
  - planner/migrations/0154_multitrack_template.py
  - planner/models.py
  - planner/static/planner/js/multitrack_editor.js
  - planner/templates/planner/multitrack/_template_card.html
  - planner/templates/planner/multitrack/dashboard.html
  - planner/templates/planner/multitrack/editor.html
  - planner/templates/planner/multitrack/new_session.html
  - planner/urls.py
  - planner/views.py
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-05-13T19:30:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 3 adds owner-scoped `MultitrackTemplate` / `MultitrackTemplateSlot` models, three new POST endpoints (save / rename / delete), a dropdown in the new-session form, and a "Save as Template" button on the editor.

**Security posture is strong.** The two critical scoping risks called out in the review brief — IDOR via cross-tenant template access, and XSS via template-name DOM injection — are both closed:

- Every server-side template lookup filters by `created_by=request.user`. The form's `template` queryset is correctly set per-instance in `__init__` (forms.py:1185-1190), not as a class-level attribute, closing the IDOR Pitfall 6 vector identified in research.
- All template-name interpolations into HTML / JS use Django's autoescape, `|escapejs`, or `textContent` assignment. No `innerHTML`, no `mark_safe`, no `dangerouslySetInnerHTML`. `data-notes` is explicitly `|escape`'d.
- Migration `0154_multitrack_template.py` is purely additive: two `CreateModel`s, two `AddIndex`es, two `AlterUniqueTogether`s (on the newly created tables). Zero `AlterField` / `RemoveField` / `RunSQL` on existing tables. Safe.
- All three new mutate endpoints (`multitrack_template_save`, `multitrack_template_rename`, `multitrack_template_delete`) use `@login_required + @require_POST + _multitrack_viewer_block(request)` matching the established phase-1/2 pattern.
- All admin registration goes through `showstack_admin_site` (admin.py:6050).
- Dropped fields (`include_aux`, `include_matrix`, `include_groups`, `color_scheme`, `naming_pattern`) are correctly absent from the migration and model.

The remaining findings are correctness/robustness concerns: a missing-source-row edge case in `apply_to_session`, a missing transaction wrapper around `form.save() + apply_to_session()`, and a viewer-write inconsistency in `multitrack_create_view` that lets a viewer call `apply_to_session` and bulk-create tracks. All Warning-level; none block the phase.

## Warnings

### WR-01: `apply_to_session` empty `source_number` matches arbitrary channel

**File:** `planner/models.py:1206-1209`
**Issue:** When `slot.source_number == ''` for a non-manual slot, the lookup `model.objects.filter(console=session.console, **{field: ''}).first()` will match the first `ConsoleInput` / `ConsoleAuxOutput` / etc. on that console whose channel-number field happens to be empty. `ConsoleInput.input_ch` is declared `blank=True, null=True` (models.py:797), so a partially-configured console can have rows with empty `input_ch`, and the slot would silently bind to one of them.

This shouldn't happen in normal operation because `_resolve_track_source_number` only returns `''` for manual tracks (which are short-circuited earlier) or when the source row has been deleted. The latter is intentionally converted to `manual` by the D-04 `post_delete` handler — but if a template is saved between the source deletion and the cascade running (or the cascade is bypassed during admin bulk delete), the bad state can persist. The result is silent incorrect track mapping rather than the intended "skip + banner".

**Fix:** Guard against empty `source_number` for non-manual slots so they fall through to the skipped path:
```python
# planner/models.py — inside apply_to_session(), after computing `field`:
if not slot.source_number:
    skipped.append((slot.source_type, slot.source_number))
    continue
channel = model.objects.filter(
    console=session.console,
    **{field: slot.source_number},
).first()
```

### WR-02: Missing transaction wrapper around session create + template apply

**File:** `planner/views.py:6020-6049`
**Issue:** `multitrack_create_view` does `session = form.save()` followed by `template.apply_to_session(session)`, which internally does `MultitrackTrack.objects.bulk_create(new_tracks)`. There is no `transaction.atomic()` wrapper. If `bulk_create` raises (e.g. IntegrityError on an unique constraint, DB connection blip), the session row persists with zero tracks and the user gets a 500 response — but on retry, the unique_together constraint on `MultitrackSession.(project, name)` blocks them. The orphan session has to be cleaned up manually.

The same issue exists in `multitrack_template_save` (views.py:6443-6466): the `MultitrackTemplate` is created, then slots are bulk-created. A failure mid-way leaves an empty template that blocks re-save under the same name (unique_together(`created_by`, `name`) at views.py:6436).

**Fix:** Wrap both write paths in `transaction.atomic()`:
```python
# views.py — multitrack_create_view, around lines 6018-6049
if form.is_valid():
    with transaction.atomic():
        session = form.save()
        template = form.cleaned_data.get('template')
        if template is not None:
            mapped, skipped, skipped_summary = template.apply_to_session(session)
            # ... messages.info(...) inside the block is fine
    return redirect('planner:multitrack_editor', session_id=session.id)

# views.py — multitrack_template_save, wrap lines 6443-6466
with transaction.atomic():
    template = MultitrackTemplate.objects.create(...)
    # ... slot building ...
    if slots:
        MultitrackTemplateSlot.objects.bulk_create(slots)
```
`transaction` is already imported at views.py:8.

### WR-03: Viewer can apply a template through `multitrack_create_view`

**File:** `planner/views.py:6003-6049`
**Issue:** `multitrack_create_view` is gated only by `@staff_member_required`, with no `_multitrack_viewer_block(request)` call. A user in the `Viewer` group who also has `is_staff=True` (which is the standard role-stack setup per `BaseEquipmentAdmin`) can POST this form and create a `MultitrackSession`. Phase 3 extends what that POST does — it now also bulk-creates `MultitrackTrack` rows via `apply_to_session`. The three new dedicated mutate endpoints all correctly call `_multitrack_viewer_block`; the create view should too, for consistency.

This is partly pre-existing (Phase 1 already allowed viewer-staff to create sessions), but Phase 3's template apply is a new write surface that bypasses the viewer-gate enforced on every other multitrack-track-creation endpoint (`multitrack_add_tracks` at views.py:6705 has the block; this path now does not).

**Fix:** Add the viewer-block at the top of `multitrack_create_view` (after the `current_project` redirect), matching the pattern used on every other mutate endpoint:
```python
@staff_member_required
def multitrack_create_view(request):
    current_project = getattr(request, 'current_project', None)
    if not current_project:
        return redirect('/')
    if request.method == 'POST' and request.user.groups.filter(name='Viewer').exists():
        return redirect('planner:multitrack_dashboard')   # silent block; matches D-09 pattern
    # ... existing body
```
The `_multitrack_viewer_block` helper returns a JsonResponse, so it's not directly reusable here (page render, not AJAX) — hence the inline check + redirect.

## Info

### IN-01: Class-body field declared after `Meta` is unusual but functional

**File:** `planner/forms.py:1155-1166`
**Issue:** `MultitrackSessionForm` declares its extra `template` `ModelChoiceField` *after* the `Meta` inner class. Django's metaclass picks it up either way (declared fields are scanned anywhere in the class body), but the convention is to declare extra fields *before* `Meta` so the field order in the class matches the field order in the rendered form. Reading the file top-down currently looks like the `template` field is some kind of helper attribute on `Meta` rather than a form field.

**Fix:** Move the `template = forms.ModelChoiceField(...)` block above the `class Meta:` declaration so the file reads in declaration order. No behavioural change.

### IN-02: N+1 query in `_resolve_track_source_number`

**File:** `planner/views.py:6354-6385`
**Issue:** `multitrack_template_save` calls `_resolve_track_source_number(track)` inside the enabled-tracks loop, which issues one SELECT per track to fetch the source row's number field. For a 144-track session (typical Rivage PM10 max), this is 144 extra queries — not catastrophic, but a single annotated queryset could collapse them to one. Performance issues are out-of-scope for v1, noted for v2.

**Fix (v2):** Pre-fetch the number fields with `prefetch_related` + a custom `Prefetch`, or annotate the source rows in a single dispatch query keyed by `source_type`.

### IN-03: "Save as Template" button visible to viewers (matches existing pattern)

**File:** `planner/templates/planner/multitrack/editor.html:25-30`
**Issue:** The new "Save as Template" button is rendered unconditionally — viewers see it, click it, and get a 403 from `_multitrack_viewer_block`. This matches the existing pattern for "Edit session metadata", "+ Add tracks", and the export buttons on the same page, so it's not a regression. Flagging for awareness; if Charlie wants viewer-aware button rendering, it should be done across all four buttons at once (out of scope for Phase 3).

**Fix:** None needed for Phase 3. Future cleanup could pass an `is_viewer` flag from `_editor_context` and gate the button cluster on it.

### IN-04: `apply_to_session` returns `mapped` as a counter, not `len(new_tracks)`

**File:** `planner/models.py:1183, 1196, 1221`
**Issue:** The function maintains a `mapped` counter and increments it manually in each branch that appends to `new_tracks`. The two values are always equal — `mapped` could be replaced with `len(new_tracks)` at the return statement, removing a class of "forgot to increment" bugs. Not a defect today.

**Fix:** Replace `mapped += 1` lines (1196, 1221) and `mapped = 0` (1183) with `mapped = len(new_tracks)` immediately before the return at 1225. Pure cleanup.

---

_Reviewed: 2026-05-13T19:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
