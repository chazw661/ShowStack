---
phase: 01-core-sessions-track-editor-reaper-export
reviewed: 2026-05-10T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - audiopatch/test_settings.py
  - planner/admin.py
  - planner/admin_ordering.py
  - planner/forms.py
  - planner/migrations/0152_multitrack_session_track.py
  - planner/models.py
  - planner/signals.py
  - planner/static/planner/css/multitrack.css
  - planner/static/planner/js/multitrack_editor.js
  - planner/templates/planner/multitrack/_color_picker.html
  - planner/templates/planner/multitrack/_picker_modal.html
  - planner/templates/planner/multitrack/_session_card.html
  - planner/templates/planner/multitrack/_track_row.html
  - planner/templates/planner/multitrack/dashboard.html
  - planner/templates/planner/multitrack/editor.html
  - planner/templates/planner/multitrack/new_session.html
  - planner/tests/test_reaper_export.py
  - planner/urls.py
  - planner/utils/reaper_export.py
  - planner/views.py
findings:
  critical: 2
  warning: 7
  info: 6
  total: 15
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-05-10T00:00:00Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Phase 1 of v2.0 (Multitrack Session Builder) is implemented across 20 source files: data layer (models, additive migration, signals), form, page-render views, AJAX endpoints, file-download views, Reaper exporter, full editor UI (templates + JS + CSS), and a robust test suite (~560 lines).

The architecture is sound and the prevailing patterns are followed correctly:

- **IDOR protection** uses combined `id=session_id, project=current_project` filters (page views) and `_get_track_for_request()` for track-level mutations — all 11 in-scope endpoints scope correctly.
- **CSRF** protection is intact: no `@csrf_exempt` decorators; the JS controller sends `X-CSRFToken` from the hidden token form.
- **CLAUDE.md conventions** are honoured: `MultitrackSession` is registered on `showstack_admin_site` (admin.py:5944), `admin_ordering.py` includes the new model at slot 12.7, and the JS uses `el.style.setProperty(prop, value, 'important')` everywhere (no bare `el.style.X = Y` style assignments that would be defeated by Django admin's `!important` rules).
- **XSS surface** is well controlled: every user-supplied label flows through `textContent` (JS) or auto-escaped Django templates (HTML), and the `_HEX_COLOR_RE` validator strictly enforces `''` or `#RRGGBB` for color writes.
- **Migration `0152`** is purely additive — only two `CreateModel` operations, zero `ALTER TABLE` against existing channel models. Phase 1 contract honoured.
- **Reaper exporter** matches the verified `PEAKCOL` bit layout, sanitises `"` → `'` in NAME tokens (Pitfall 8), emits `MAINSEND 1 0` (Pitfall 6), and is comprehensively unit-tested.

The two **critical** findings are both server-side authorization gaps: (1) seven of the nine AJAX mutate endpoints have no `@login_required` / `@staff_member_required` decorator at all, and (2) viewers (read-only role) can mutate every multitrack endpoint because the role check from `BaseEquipmentAdmin` is not replicated in the custom views. The defence-in-depth from `CurrentProjectMiddleware` (which ignores anonymous users) prevents pure-anon access in practice, but viewer write access is unmitigated.

The remaining warnings cover a real UI bug (under-capacity bar always renders 100% full because no JS reads `data-fill-percent`), error-message information disclosure, a dead session-id fallback in the JS (the picker can never find one because the editor template only sets `data-mts-session-id` when `tracks` is non-empty AND `data-session-id` on the same level), and a few doc/style nits.

## Critical Issues

### CR-01: AJAX mutate endpoints lack authentication decorators — viewers can mutate any session in their active project

**File:** `planner/views.py:5948-6381` (9 endpoints)
**Issue:**
Nine of the new endpoints carry only `@require_POST` and rely entirely on `request.current_project` (set by `CurrentProjectMiddleware`) for access control:

```
@require_POST
def multitrack_duplicate(request, session_id):  # 5949
def multitrack_rename(request, session_id):     # 6016
def multitrack_delete(request, session_id):     # 6056
def multitrack_reorder(request, session_id):    # 6115
def multitrack_add_tracks(request, session_id): # 6158
def multitrack_set_color(request):              # 6283
def multitrack_set_label(request):              # 6309
def multitrack_set_enabled(request):            # 6339
def multitrack_remove_track(request):           # 6362
```

`CurrentProjectMiddleware.__call__` (planner/middleware.py:23) only sets `request.current_project` when `request.user.is_authenticated`, so the practical effect is that *anonymous* requests fall through to `'No active project'` 400. **However**, every authenticated user who is a member of the active project — including those with the `viewer` role — can call these endpoints and mutate state. The viewer-restriction enforced everywhere else in the codebase (`BaseEquipmentAdmin.has_change_permission` returns False for viewers; admin classes in `admin.py` call `request.user.groups.filter(name='Viewer').exists()`) is bypassed by routing through the custom views.

Two further consequences:
- A viewer in project A can call `multitrack_set_color`, `multitrack_set_label`, `multitrack_set_enabled`, `multitrack_remove_track`, `multitrack_add_tracks`, `multitrack_reorder`, and `multitrack_rename`/`multitrack_delete`/`multitrack_duplicate` for any session/track in project A. This violates the CLAUDE.md role contract ("`viewer` — read-only").
- `multitrack_dashboard`, `multitrack_editor`, `multitrack_create_view`, `multitrack_edit_view`, `multitrack_capacity_check`, `multitrack_export_rpp`, and `multitrack_export_rtracktemplate` *do* carry `@staff_member_required` (5743, 5874, 5896, 5917, 6384, 6434, 6480), so the inconsistency is local to the mutate POSTs.

**Fix:** Add an authentication decorator stack and a viewer-block helper to every mutate endpoint:

```python
from django.contrib.auth.decorators import login_required

def _user_can_edit_current_project(request):
    """Return True iff the authenticated user has edit rights on
    request.current_project. Mirrors BaseEquipmentAdmin.has_change_permission."""
    if not request.user.is_authenticated:
        return False
    if request.user.is_superuser:
        return True
    if request.user.groups.filter(name='Viewer').exists():
        return False
    project = getattr(request, 'current_project', None)
    if project is None:
        return False
    if project.owner_id == request.user.id:
        return True
    from .models import ProjectMember
    return ProjectMember.objects.filter(
        user=request.user, project=project, role='editor'
    ).exists()


@login_required
@require_POST
def multitrack_set_color(request):
    if not _user_can_edit_current_project(request):
        return JsonResponse({'error': 'Read-only access.'}, status=403)
    # ... existing body
```

Apply the same `@login_required` + `_user_can_edit_current_project` guard to all nine endpoints listed above. The page-render views should also gain the role check (the `@staff_member_required` is necessary but not sufficient — a `staff` user with the `Viewer` group should not see the "+ New Session" button reach `multitrack_create_view`).

---

### CR-02: `multitrack_capacity_check` exposes session presence/absence to any non-staff authenticated user via `@staff_member_required` while every mutate endpoint uses no auth at all — inconsistent gate creates an XS-Search style oracle

**File:** `planner/views.py:6385-6407`
**Issue:**
This is the same root cause as CR-01 viewed from a different angle: the inconsistency between `@staff_member_required` on read endpoints and bare `@require_POST` on mutate endpoints means a non-staff authenticated attacker who is a member of the current project can:

1. Discover whether a session ID exists in their project via `POST /multitrack/<id>/rename/` body `{}` — gets `'Name is required.'` (400) when the session exists, `'Session not found'` (404) when it does not.
2. Enumerate track IDs across the project via `POST /multitrack/track/set-enabled/` body `{track_id: N, enabled: true}` — gets `{ok: true}` (200) for hits, `'Track not found'` (404) for misses.
3. The same enumeration also writes! `multitrack_set_enabled` is the simplest case — a single attacker request flips a track's `enabled` flag if the IDOR check passes (and silently fails if not), giving the attacker a discovery primitive AND a mutation primitive in the same call.

The `_get_track_for_request` filter (planner/views.py:6097) does scope by `session__project=current_project`, so cross-project IDOR is blocked. But within-project enumeration combined with mutation by a viewer is a real privilege escalation.

**Fix:** Same as CR-01. Adding `@login_required` plus the viewer-block check on every mutate endpoint closes the within-project read/write oracle. The `_get_track_for_request` IDOR check is correct and should remain.

## Warnings

### WR-01: Under-capacity progress bar always renders at 100% — `data-fill-percent` is set on the DOM but no code reads it

**File:** `planner/templates/planner/multitrack/editor.html:55-56` (template) and `planner/static/planner/css/multitrack.css:303-308` (CSS rule)
**Issue:**
The under-capacity bar template writes:
```html
<span class="mts-capacity__fill" data-fill-percent="{% widthratio total_count session.recorder_capacity 100 %}"></span>
```
But:
- The CSS rule for `.mts-capacity__fill` is `width: 100% !important;` (multitrack.css:306).
- No JavaScript reads `data-fill-percent` or sets `style.width` based on it (`grep -n "data-fill-percent\|fill-percent\|capacity__fill" planner/static/planner/js/multitrack_editor.js` returns zero matches).
- The over- and at-capacity branches explicitly set `style="width:100%"` on the inline span (lines 43 and 49), but the under branch only sets `data-fill-percent`.

Result: a session with `recorder_capacity=64` and `total_count=8` shows the same fully-filled blue bar as a session with `total_count=63`. The percentage value is computed server-side but never applied.

**Fix:** Either (a) inline the width directly in the template:
```html
<span class="mts-capacity__fill"
      style="width:{% widthratio total_count session.recorder_capacity 100 %}%"></span>
```
or (b) add a small `paintCapacityFill()` initializer in `multitrack_editor.js` that reads `data-fill-percent` from every `.mts-capacity__fill` and calls `el.style.setProperty('width', val + '%', 'important')` — needs `'important'` because the CSS rule is `!important`. Option (a) is simpler and works without JS.

---

### WR-02: All bare `try / except Exception as e: return JsonResponse({'error': str(e)})` blocks leak internal error messages to clients

**File:** `planner/views.py:6011-6012, 6051-6052, 6077-6078, 6153-6154, 6278-6279, 6304-6305, 6334-6335, 6357-6358, 6380-6381`
**Issue:**
Each AJAX mutate endpoint ends with:
```python
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
```
This hands raw Python exception messages to the client — including database error details, stack-relative attribute names, and `IntegrityError` constraint names. Examples of what a curious caller could see by sending malformed bodies: `'duplicate key value violates unique constraint "planner_multitracksession_project_id_name_..."'`, `'NoneType' object has no attribute 'tracks'`, `'invalid literal for int() with base 10: ...'`. None of those should reach a browser.

**Fix:** Catch and log; return a generic 500:
```python
import logging
logger = logging.getLogger(__name__)

    except Exception:
        logger.exception("multitrack_set_color failed")
        return JsonResponse({'error': 'Internal error.'}, status=500)
```
Apply to all nine mutate endpoints. Specific anticipated errors (e.g. `IntegrityError` for unique violation in duplicate/rename) should be caught and translated to a 409 with a UI-SPEC-compliant message instead of bubbling out.

---

### WR-03: `mtsCommitPickerSelection` "fallback to `[data-mts-session-id]`" is dead code — the editor template always renders `data-session-id` on `.mts-track-list` whenever there are tracks, and `[data-mts-session-id]` is on `.mts-container` regardless

**File:** `planner/static/planner/js/multitrack_editor.js:336-348`
**Issue:**
The picker's commit handler does:
```js
const trackList = $('.mts-track-list');
const sessionId = trackList ? trackList.dataset.sessionId : null;
if (!sessionId) {
  const fallback = document.querySelector('[data-mts-session-id]');
  if (!fallback) { showToast('Cannot determine session id.', 'error'); return; }
  submitPickerCommit(fallback.dataset.mtsSessionId);
  return;
}
submitPickerCommit(sessionId);
```
This is intended to handle the empty-state path where `<div class="mts-track-list">` is not rendered (editor.html:76 — the `{% else %}` branch). The fallback is correct in intent but:

- `editor.html:12` ALREADY puts `data-mts-session-id="{{ session.id }}"` on `.mts-container` unconditionally, so the fallback always finds it. Good — this works.
- However, the comment says "Editor-empty-state path: the `.mts-track-list` isn't rendered." That is the only time the fallback fires, so the `if (!sessionId)` branch IS reachable. Just confirm: when zero tracks, `auto_open_picker=True` runs `mtsOpenPicker('inputs')`, the user selects N tracks and clicks "Add N selected" — `trackList` is null, fallback fires, `submitPickerCommit` posts to the right URL, server creates rows and returns `redirect_url` — the JS calls `window.location.reload()` and the new tracks render.

This is actually working correctly. The only nit is that `[data-mts-session-id]` is a generic attribute selector and could in theory be matched by another future container; consider renaming it to `[data-mts-session-id-hint]` or keying off `#mts-editor-root` to avoid accidental collision. **No functional fix required**, but the prompt called it out as a focus area, so flagging it as confirmed-correct.

**Fix:** No change needed. Optionally tighten the fallback to a unique ID-based selector to forestall future name collisions.

---

### WR-04: `multitrack_reorder` allows partial reorder on subset of session tracks — track_numbers will collapse non-deterministically

**File:** `planner/views.py:6132-6151`
**Issue:**
The validation accepts any subset of the session's tracks: `set(ordered_ids).issubset(existing_ids)`. If the client posts only `[5, 3]` from a 4-track session (existing tracks 1, 2, 3, 5), only those two get renumbered — track 5 becomes 1, track 3 becomes 2, and the existing tracks 1 and 2 keep their old numbers. Result: two tracks with `track_number=1` and two with `track_number=2`, breaking the `ordering = ['track_number']` invariant in `MultitrackTrack.Meta`.

The client (Sortable.onEnd handler at multitrack_editor.js:74-78) always sends every track in the list, so this is a latent bug rather than an active one — but a third party could exploit it via raw API calls.

**Fix:** Require the posted set to equal the full existing set:
```python
if set(ordered_ids) != existing_ids:
    return JsonResponse({
        'error': 'ordered_ids must include every track in the session exactly once.'
    }, status=400)
if len(ordered_ids) != len(set(ordered_ids)):
    return JsonResponse({'error': 'Duplicate track IDs in ordered_ids.'}, status=400)
```

---

### WR-05: Signal `_convert_orphans_to_manual` short-circuit `track.label_override or (snapshot_label or '')` permanently overwrites the snapshot when the existing override is non-empty — but the snapshot is the only fallback once the channel is gone

**File:** `planner/signals.py:51-58`
**Issue:**
```python
for track in orphans:
    track.label_override = track.label_override or (snapshot_label or '')
    track.color_override = track.color_override or (snapshot_color or '')
    track.source_type = 'manual'
    track.source_id = None
    track.save(update_fields=[...])
```
If `track.label_override` was already set (engineer typed a custom label), the snapshot is dropped — that is correct (UX: keep user override). But for a track with `label_override=''` and `source.source='Kick In'`, the snapshot fills it in. So far, fine.

The subtler issue: `consoleauxoutput_to_manual` (signals.py:73-75) computes:
```python
label = instance.name or f'Aux {instance.aux_number}' or '(deleted aux)'
```
The chained `... or '(deleted aux)'` is unreachable because `f'Aux {instance.aux_number}'` is a non-empty string even when `aux_number` is None or empty (it just becomes `'Aux None'` or `'Aux '`). Same pattern in `consolematrixoutput_to_manual` (line 80) and `consolestereooutput_to_manual` (line 86: `instance.name or instance.get_stereo_type_display() or '(deleted stereo)'` — `get_stereo_type_display()` always returns a string, so `'(deleted stereo)'` is unreachable too).

The orphaned tracks therefore get labels like `Aux None` instead of `(deleted aux)` when the source had no `name` and no `aux_number`. Visible to engineers and confusing.

**Fix:**
```python
@receiver(post_delete, sender=ConsoleAuxOutput)
def consoleauxoutput_to_manual(sender, instance, **kwargs):
    if instance.name:
        label = instance.name
    elif instance.aux_number:
        label = f'Aux {instance.aux_number}'
    else:
        label = '(deleted aux)'
    _convert_orphans_to_manual('aux', instance.pk, label)
```
Apply the same explicit-branch pattern to `consolematrixoutput_to_manual` and `consolestereooutput_to_manual`.

---

### WR-06: `_safe_filename` keeps non-ASCII letters via `c.isalnum()` — ASCII-only is safer for `Content-Disposition`

**File:** `planner/views.py:6421-6427`
**Issue:**
`isalnum()` returns True for Unicode letters (`'é'.isalnum() == True`, `'café'.isalnum() == True`, `'ñ'.isalnum() == True`). The `Content-Disposition: attachment; filename="..."` header is RFC 6266 — bare filenames must be ASCII; non-ASCII bytes require a `filename*=UTF-8''...` encoded form. As written, a session named `Café Show` would emit `filename="Café Show.RPP"` — most browsers cope with this in practice, but some reject it and others mojibake the result.

This is not a path-traversal risk — the function strips `/`, `\`, `..` segments because none of those pass `isalnum()`. The risk is purely ASCII compliance / browser robustness.

**Fix:** Restrict to ASCII alphanumerics and hyphen/underscore:
```python
def _safe_filename(name):
    cleaned = ''.join(
        c if (c.isascii() and c.isalnum()) or c in '-_' else '_'
        for c in (name or '').strip()
    )
    return cleaned or 'session'
```

---

### WR-07: Console picker queryset in `_build_picker_data` ignores deleted/orphan tracks correctly but joins on session.console without re-validating that the session still belongs to `current_project` — relies on caller

**File:** `planner/views.py:5763-5817`
**Issue:**
`_build_picker_data(session, existing_tracks)` is called only from `_editor_context` (5865), which is in turn only called from view functions that have already verified `session.project == request.current_project` (multitrack_editor at 5885; multitrack_export_rpp at 6444; multitrack_export_rtracktemplate at 6491). So in practice this is safe.

However the helper itself unconditionally queries `ConsoleInput.objects.filter(console=session.console)` etc. There is no defence-in-depth assertion that the caller did the IDOR check. A future caller that forgets to scope by `current_project` would silently leak channel data from another project's console.

**Fix:** Either (a) accept `current_project` as a required arg and assert `session.project_id == current_project.id`, or (b) rename the helper to `_build_picker_data_unsafe` to make the caller contract explicit. Minor hardening.

## Info

### IN-01: Test comment claims `0x0100FF00 == 16842240` — actual decimal is `16842496`

**File:** `planner/tests/test_reaper_export.py:283-284`
**Issue:**
The inline comment on line 284 says `# Green track -> 0x0100FF00 = 16842240`. The decimal is wrong — `0x0100FF00 = 16842496`. The test passes (the assertion is `f'PEAKCOL {0x010 0FF00}'` which Python evaluates correctly), but the comment misleads.

A separate test `test_pure_green` (lines 60-65) acknowledges the same arithmetic typo in the Plan 01-02 `<behavior>` block. Worth removing the typo from this block too.

**Fix:** Update line 284 comment to `# Green track -> 0x0100FF00 = 16842496`.

---

### IN-02: `_source_channel_number` for input falls through `int(src.input_ch) if src.input_ch else int(src.dante_number or 999999)` — the `or 999999` inside `int()` is wrong if `dante_number` is `'0'`

**File:** `planner/utils/reaper_export.py:113-116`
**Issue:**
`int(src.dante_number or 999999)` — if `dante_number=='0'` (string zero), the `or` evaluates `'0'` as truthy (non-empty string), so `int('0')` returns 0. That's actually correct. If `dante_number==''` (empty string), `or` falls back to `999999`. Also correct. If `dante_number is None`, same. So this is fine for ConsoleInput where `dante_number` is `CharField`. Flagging only because `int(... or N)` is subtle and a future dev may "fix" it incorrectly.

**Fix:** No change. Add a one-line comment explaining the intent.

---

### IN-03: `print("ADMIN_ORDERING.PY LOADED")` and `print("*** FUNCTION CALLED ***")` are debug artifacts left in `admin_ordering.py` (pre-existing, not Phase 1 — but also not removed by Phase 1)

**File:** `planner/admin_ordering.py:7-10, 20`
**Issue:**
The file prints to stdout on every Django startup and every admin sidebar render. Pre-existing code (the diff only touches the dictionary entry at line 110 to add `'multitracksession': 12.7,`), so this is out of strict Phase 1 scope. Mentioning here because the phase touches the file.

**Fix:** Out of scope for this phase. File a separate cleanup task to remove the prints.

---

### IN-04: `forms.py` and `signals.py` files have multiple `print(...)` debug calls — pre-existing in `forms.py`, not introduced by Phase 1

**File:** `planner/forms.py:23-26, 1106-1119` (pre-existing); `planner/signals.py` (clean — no prints added)
**Issue:**
The new `MultitrackSessionForm` in `forms.py` does NOT contain any debug prints — clean. Mentioning the surrounding file's pre-existing `print` statements only because reviewers may flag them; they are out of Phase 1 scope.

**Fix:** No action. Phase 1 forms code is clean.

---

### IN-05: `editor.html` loads Sortable.min.js without `defer` while loading `multitrack_editor.js` with `defer` — Sortable will be defined when the controller's DOMContentLoaded handler runs, but the loose ordering is fragile

**File:** `planner/templates/planner/multitrack/editor.html:104-105`
**Issue:**
```html
<script src="{% static 'planner/js/vendor/Sortable.min.js' %}"></script>
<script src="{% static 'planner/js/multitrack_editor.js' %}" defer></script>
```
The deferred controller will execute after the synchronous Sortable script has parsed and run — so `typeof Sortable !== 'undefined'` is true at `initSortable()` call time. Works in practice. The `multitrack_editor.js:70` defensive `if (typeof Sortable === 'undefined') return;` is the safety net.

**Fix:** For consistency, add `defer` to the Sortable script tag too:
```html
<script src="{% static 'planner/js/vendor/Sortable.min.js' %}" defer></script>
```
Defer-tagged scripts execute in document order, so Sortable will still be defined first.

---

### IN-06: `MultitrackSessionForm.clean_target_daw` validates `nuendo_live` is rejected, but the dispatch comment in `__init__` (lines 1166-1171) describes "belt + suspenders" without actually adding the suspenders — the cross-reference is misleading

**File:** `planner/forms.py:1166-1189`
**Issue:**
The `__init__` block has a comment block:
```python
# Disable Nuendo Live choice in Phase 1 (UI-SPEC: "(coming v2.0)")
# We render this in the template; here we just ensure the form
# validates if Reaper is picked. The template marks the radio
# disabled — server-side, we additionally refuse `nuendo_live`.
# (Belt + suspenders against a tampered POST.)
```
But `__init__` itself does nothing about Nuendo Live. The actual rejection lives in `clean_target_daw` (line 1181). The comment block reads as if `__init__` is enforcing something, when in fact it's a prose pointer to `clean_target_daw`. Confusing on a quick scan.

**Fix:** Move the comment to immediately above `clean_target_daw`, or reword as `# (Nuendo Live block is enforced in clean_target_daw below.)`.

---

_Reviewed: 2026-05-10T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
