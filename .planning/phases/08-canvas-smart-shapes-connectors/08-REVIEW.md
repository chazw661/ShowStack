---
phase: 08-canvas-smart-shapes-connectors
reviewed: 2026-05-21T18:01:10Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - planner/views.py
  - planner/static/planner/css/signal_flow.css
  - planner/templates/planner/signal_flow/editor.html
  - planner/templates/planner/signal_flow/_equipment_picker_modal.html
  - planner/static/planner/js/signal_flow_editor.js
findings:
  critical: 0
  warning: 5
  info: 7
  total: 12
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-05-21T18:01:10Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 8 adds the JointJS canvas, five smart shapes, drag-drop equipment
picker, pan/zoom/snap, custom undo-redo, multi-select rubber-band,
connectors with signal-type styling, an inspector panel, and a manual
save flow. Two new server endpoints (`signal_flow_autosave`,
`signal_flow_autocomplete`) replace the Phase 7 stubs.

The review found **no critical security vulnerabilities**. The
high-priority IDOR concerns called out in the scope note are all
correctly addressed:

- `_get_diagram_for_request` scopes the diagram lookup to
  `request.current_project` on both endpoints.
- `SpeakerArray` is correctly scoped via `prediction__project` (no
  direct `project` FK).
- `validateMagnet` properly rejects passive (in-port) magnets as drag
  sources.
- All picker/inspector DOM construction uses `createElement` +
  `textContent`; no content-bearing `innerHTML` writes.
- CSRF is in place via `X-CSRFToken` header + Django middleware.
- JS admin-DOM style writes uniformly use
  `setProperty(prop, value, 'important')`.
- Undo-stack recursion guards (`{ undoable: false }`) are applied on
  every `applyInverse`/`applyForward` call and on the initial
  `fromJSON`.
- The `joint.shapes.showstack` namespace is registered **before**
  `new joint.dia.Graph`, with both `cellNamespace` and
  `cellViewNamespace` passed.
- Autocomplete is hard-capped at 50 rows with per-row `try/except`.

The findings below are five **warnings** (correctness / defense-in-depth)
and seven **info** items (cosmetic / dead code / minor maintenance).
None block ship of Phase 8; several should land before Phase 9
optimistic-locking work touches the same endpoints.

## Warnings

### WR-01: Autosave wipes `canvas_state` on a payload without that key

**File:** `planner/views.py:7583`
**Issue:** In the non-`viewport_only` branch, `canvas_state =
payload.get('canvas_state') or {}` silently treats a missing
`canvas_state` key as an empty diagram. The subsequent
`diagram.canvas_state = canvas_state` then overwrites the persisted
diagram with `{}`. A client that POSTs only a `viewport` to the full-save
URL (forgetting `?viewport_only=1`) — or any malformed save — would
permanently lose its canvas. The JS client today always includes
`canvas_state` (line 1324), so this is latent data loss waiting for a
client bug to expose it.
**Fix:**
```python
# Full canvas_state save — require the key explicitly.
if 'canvas_state' not in payload:
    return JsonResponse(
        {'error': 'canvas_state required for full save (use ?viewport_only=1 for viewport-only)'},
        status=400,
    )
canvas_state = payload['canvas_state']
if not isinstance(canvas_state, dict):
    return JsonResponse({'error': 'Bad canvas_state payload'}, status=400)
```

### WR-02: Permissive equipment-ref scoping accepts any model with a `project` attribute

**File:** `planner/views.py:7613`
**Issue:** The IDOR-validation loop accepts a cell's GFK reference iff
`hasattr(Model, 'project')` (after the SpeakerArray special-case). Most
models in this project have a `project` FK (`Crew`, `AudioChecklist`,
`ChecklistTemplate`, `SoundvisionPrediction`, etc.), so a crafted
`canvas_state` can stash arbitrary content-type pointers in the diagram.
The cross-tenant IDOR is still blocked (the `project=current_project`
filter holds), but the server happily persists references that the UI
never produces. Phase 9's `_enrich_nodes` may dereference these and
crash on missing `name`/`__str__` attributes, or worse, leak unrelated
project data into the diagram view. Defense-in-depth: whitelist
exactly the four shape backends.
**Fix:**
```python
ALLOWED_GFK_MODELS = {'Console', 'Device', 'SpeakerArray', 'CommBeltPack'}
# ... inside the loop:
if model_name not in ALLOWED_GFK_MODELS:
    return JsonResponse(
        {'error': f'Type {ct.model} not allowed on signal flow canvas'},
        status=422,
    )
if model_name == 'SpeakerArray':
    exists = Model.objects.filter(id=obj_id, prediction__project=current_project).exists()
else:
    exists = Model.objects.filter(id=obj_id, project=current_project).exists()
```

### WR-03: Viewport-only saves bump `updated_at` and re-sort the diagram list

**File:** `planner/views.py:7579`
**Issue:** The viewport-only branch calls
`diagram.save(update_fields=['viewport', 'updated_at'])`, and `updated_at`
has `auto_now=True`. The diagram list orders by `-updated_at`
(views.py:7395; `Meta.ordering = ['-updated_at', 'name']`), so every
pan/zoom/snap-toggle silently moves the active diagram to the top of the
list for every project member. This breaks the implicit "most-recently-
edited first" semantic that the list page advertises. The full-save path
correctly bumps `updated_at` (real edit), but viewport-only should not.
**Fix:** Exclude `updated_at` from the update_fields set on the
viewport-only path (and explicitly set the field to keep its prior value
so Django doesn't overwrite via auto_now):
```python
# Suppress auto_now bump for cosmetic viewport writes.
SignalFlowDiagram.objects.filter(pk=diagram.pk).update(viewport=viewport)
return JsonResponse({'ok': True, 'viewport_only': True})
```
A queryset `.update()` skips `auto_now`. Alternatively, drop
`updated_at` from `update_fields` only — but `auto_now` fires
regardless of update_fields when calling `.save()`, so the queryset
form is the actual fix.

### WR-04: No size cap on `canvas_state` body — DoS surface

**File:** `planner/views.py:7570`
**Issue:** `json.loads(request.body or '{}')` accepts a body of arbitrary
size. There's no per-request length check before parsing, and no cap on
`len(cells)` before the validation loop. An authenticated editor in any
project could POST a 100 MB canvas (or a million-cell array) and
DOS the worker thread + Postgres JSONField write. Django's
`DATA_UPLOAD_MAX_MEMORY_SIZE` (2.5 MB default) is a partial backstop,
but JSON parses still blow memory inside that limit, and the cell-loop
walks every entry before persistence.
**Fix:**
```python
MAX_CELLS = 1000  # matches REQUIREMENTS implicit canvas scale
if len(request.body) > 1_000_000:  # 1 MB hard limit on diagram payload
    return JsonResponse({'error': 'Diagram too large'}, status=413)
payload = json.loads(request.body or '{}')
# ... later, after cells = canvas_state.get('cells') or []:
if len(cells) > MAX_CELLS:
    return JsonResponse({'error': 'Too many cells'}, status=413)
```

### WR-05: `applySelectionVisuals` reads `window.__sfd` without a defensive guard

**File:** `planner/static/planner/js/signal_flow_editor.js:868`
**Issue:** `if (typeof window.__sfd.onSelectionChanged === 'function')`
will throw `TypeError: Cannot read properties of undefined` if
`window.__sfd` was not yet assigned at line 1387. Today this is safe
because the IIFE runs synchronously and assigns `window.__sfd` before
any user event can fire. But the `graph.on('add change:attrs', ...)`
listener at line 1001 also fires during the async
`getJSON(stateUrl).then(...)` initial `fromJSON` — which technically
runs after the IIFE completes, so `window.__sfd` is defined by then.
The bug is latent: any future refactor that moves the `window.__sfd`
assignment, or any test harness that calls `applySelectionVisuals`
during IIFE evaluation, will get a runtime error that's hard to trace.
**Fix:**
```js
// Plan 06's inspector hooks into this — see window.__sfd.selection below.
if (window.__sfd && typeof window.__sfd.onSelectionChanged === 'function') {
  window.__sfd.onSelectionChanged(Array.from(selectedSet));
}
```

## Info

### IN-01: `console.log` left in production code path

**File:** `planner/static/planner/js/signal_flow_editor.js:268`
**Issue:** `console.log('[SFD] paper ready — diagram', diagramId, ...)`
fires on every editor page load. Useful during dev; noise in production
browser consoles. The two `console.error` calls (lines 34, 273) are
appropriate for genuine failures and should stay.
**Fix:** Remove the log, or gate behind a `DEBUG` flag from a template
data-attr. Lightweight version:
```js
// (remove the console.log; the toast on error path is sufficient signal)
```

### IN-02: Unused `data-diagram-name` attribute with incorrect escape filter

**File:** `planner/templates/planner/signal_flow/editor.html:25`
**Issue:** `data-diagram-name="{{ diagram.name|escapejs }}"` is never
read by the JS (verified with `grep diagramName`). Two issues: (a) it's
dead, and (b) `|escapejs` is the wrong filter for an HTML attribute
context — Django's default `|escape` would be correct. `|escapejs`
produces `'` sequences that survive HTML-attribute parsing as
literal characters, so any consumer that ever reads
`dataset.diagramName` will see Unicode-escape gibberish for names with
quotes. Auto-escape on `{{ diagram.name }}` would already be HTML-safe.
**Fix:** Remove the attribute, or if Phase 9 needs it, drop the filter:
```html
data-diagram-name="{{ diagram.name }}"
```

### IN-03: Duplicate `location` field declarations on `Console`

**File:** `planner/models.py:873-874` (out of Phase 8 diff but visible
in scope check)
**Issue:** `class Console` declares `location` twice — the second
declaration wins, but the first is dead code. Not Phase 8's bug; flagged
because the autocomplete `lambda c: (...)` could theoretically reference
`c.location` later and silently use the wrong related_name.
**Fix:** Remove line 873 (the `related_name='devices'` variant is
clearly a copy-paste leftover from `Device`).

### IN-04: Generic `except Exception` catches too much

**File:** `planner/views.py:7635`, `planner/views.py:7742`
**Issue:** Both endpoints wrap the bulk of their logic in `try: ...
except Exception:` returning a 500. Standard project pattern (matches
`signal_flow_create`/`rename`/`delete`), but it swallows specific errors
that would be useful to surface: e.g.
`Project.DoesNotExist` (already guarded), or ContentType
`MultipleObjectsReturned` (impossible by schema, but still). Per project
convention this is acceptable — flagging only so a future hardening pass
can replace the blanket except with typed handlers.
**Fix:** Either accept the convention as-is, or narrow to
`(ValueError, KeyError, ContentType.DoesNotExist)` and let truly
unexpected exceptions propagate to Django's 500 handler (which already
logs).

### IN-05: `paper.options.defaultLink` / `linkPinning` / `snapLinks` /
`validateConnection` / `validateMagnet` set AFTER `new joint.dia.Paper`

**File:** `planner/static/planner/js/signal_flow_editor.js:1118-1133`
**Issue:** JointJS docs recommend passing these in the Paper
constructor options. Mutating `paper.options` post-construction works in
@joint/core 4.2.4 (verified empirically by the team per RESEARCH §11),
but is undocumented behavior. If the team upgrades to 5.x and these
options are cached internally at construction time, all five connector
features silently break.
**Fix:** Move them into the `new joint.dia.Paper({ ... })` block at
line 230. This requires reordering — the namespace-registered
SignalLink class must exist before the Paper is constructed, which
means moving the SignalLink definition above line 227.

### IN-06: `Q().children` is a Django internal API

**File:** `planner/views.py:7713`
**Issue:** `if cond.children:` reads a Django Q-object internal
attribute to detect an empty filter. Works today and is unlikely to
change, but isn't part of the documented Q API. Cleaner pattern:
track whether any clause was added with a local flag.
**Fix:**
```python
qs = Model.objects.filter(**project_kw)
if q:
    cond = Q()
    has_clause = False
    for f in search_fields:
        if f == 'bp_number':
            if q.isdigit():
                cond |= Q(bp_number=int(q))
                has_clause = True
        else:
            cond |= Q(**{f'{f}__icontains': q})
            has_clause = True
    if has_clause:
        qs = qs.filter(cond)
```

### IN-07: Multiple global `document.addEventListener('keydown', ...)`
handlers — risk of duplicate registration if the IIFE re-runs

**File:** `planner/static/planner/js/signal_flow_editor.js:494, 554, 826, 977`
**Issue:** Four separate global keydown listeners on `document`, none
removable. If the editor is ever loaded twice into the same page (e.g.,
SPA-style navigation in a future refactor), every keystroke fires each
handler N times. Not a bug today because the editor template is full-
page Django render and the IIFE has an early `return` when
`#sfd-container` is missing.
**Fix:** Acceptable for Phase 8. Worth consolidating into a single
keydown router function if a Phase 11+ refactor moves the editor into
an embedded context.

---

_Reviewed: 2026-05-21T18:01:10Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
