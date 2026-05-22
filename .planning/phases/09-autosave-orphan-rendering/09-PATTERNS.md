# Phase 9: Autosave & Orphan Rendering — Pattern Map

**Mapped:** 2026-05-21
**Files analyzed:** 4 modified + 1 new helper (in-place in `views.py`)
**Analogs found:** 5 / 5 — every Phase 9 surface has a same-file or same-codebase analog

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `planner/views.py` — `signal_flow_autosave` (mod, lines 7545-7637) | view / controller | request-response (POST JSON) | itself (Phase 8 shape) + multitrack views | exact (self-extension) |
| `planner/views.py` — `signal_flow_state` (mod, lines 7528-7542) | view / controller | request-response (GET JSON) | itself (Phase 7 stub) | exact (self-extension) |
| `planner/views.py` — `_enrich_nodes()` (NEW helper above 7528) | utility / pure function | transform (deep-copy + bulk SELECT) | bulk-fetch `seed_maps` at `views.py:6733-6738` + IDOR walk at `7587-7624` | role-match |
| `planner/static/planner/js/signal_flow_editor.js` — autosave controller (replace 1306-1435) | client controller | event-driven debounce + POST | viewport-only debounce at `549-571` + manual `doSave` at `1332-1384` | exact (template) |
| `planner/static/planner/js/signal_flow_editor.js` — orphan ghost render hook (NEW) | client view-binding | event-driven (graph `add`/`change`) | link styling hook at `1175-1183` (`graph.on('add', applySignalType…)`) | role-match |
| `planner/static/planner/js/signal_flow_editor.js` — node-inspector mode (NEW, extends 1186-1304) | client UI controller | event-driven (selection-change) | connector inspector at `1186-1304` | exact (extension of same panel) |
| `planner/templates/planner/signal_flow/editor.html` — toolbar mod (lines 31-56) | template | declarative DOM | itself (Phase 8 toolbar) | exact (self-edit) |
| `planner/templates/planner/signal_flow/editor.html` — banner element (NEW between toolbar + canvas) | template | declarative DOM | `templates/planner/mic_tracker.html:407-411` (update banner) | role-match |
| `planner/static/planner/css/signal_flow.css` — banner styles (NEW section 10) | stylesheet | declarative | existing toast `.sfd-toast--error` at `447-470` + status `is-error` at `102-104` | role-match |
| `planner/static/planner/css/signal_flow.css` — orphan ghost styles (NEW section 11) | stylesheet | declarative | JointJS selection visual at `501-516` (attribute-driven SVG styling) | role-match |

---

## Pattern Assignments

### 1. `signal_flow_autosave` — atomic version-pinned UPDATE + If-Match

**Analog:** itself, `planner/views.py:7545-7637` (the Phase 8 version). Phase 9 only swaps the save block and adds an `If-Match` header read; the IDOR walk at lines 7587-7624 stays unchanged.

**Imports already in scope at top of file** (`views.py:1-26`):
```python
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import transaction, IntegrityError   # line 8
import json
```
Add to the existing imports (still local — keeps the global surface unchanged):
```python
from django.db.models import F                       # for F('version')+1
from django.utils import timezone                    # for now() on updated_at
```

**Existing IDOR walk to PRESERVE (verbatim) — `views.py:7587-7624`:**
```python
# Walk canvas JSON, validate every linked equipment ref (PITFALLS.md §4).
from django.contrib.contenttypes.models import ContentType
current_project = request.current_project
cells = canvas_state.get('cells') or []
for cell in cells:
    prop = cell.get('showstack') if isinstance(cell, dict) else None
    if not isinstance(prop, dict):
        continue
    ct_id = prop.get('contentTypeId')
    obj_id = prop.get('objectId')
    if not ct_id or not obj_id:
        continue
    ct = ContentType.objects.filter(id=ct_id).first()
    if not ct:
        return JsonResponse({'error': f'Unknown content type {ct_id}'}, status=422)
    Model = ct.model_class()
    if Model is None:
        return JsonResponse({'error': f'Content type {ct_id} not resolvable'}, status=422)
    model_name = Model.__name__
    if model_name == 'SpeakerArray':
        exists = Model.objects.filter(
            id=obj_id, prediction__project=current_project,
        ).exists()
    elif hasattr(Model, 'project') or model_name in ('Console', 'Device', 'CommBeltPack'):
        exists = Model.objects.filter(
            id=obj_id, project=current_project,
        ).exists()
    else:
        return JsonResponse(
            {'error': f'Type {ct.model} has no project scope'}, status=422,
        )
    if not exists:
        return JsonResponse(
            {'error': 'Equipment reference out of project'}, status=422,
        )
```

**Existing save block to REPLACE — `views.py:7626-7631`:**
```python
diagram.canvas_state = canvas_state
if 'viewport' in payload and isinstance(payload['viewport'], dict):
    diagram.viewport = payload['viewport']
diagram.version = (diagram.version or 1) + 1
diagram.save(update_fields=['canvas_state', 'viewport', 'version', 'updated_at'])
return JsonResponse({'ok': True, 'version': diagram.version})
```

**Replacement pattern — atomic version-checked UPDATE (D-05 / D-06):**
The new block (a) reads `If-Match` BEFORE the IDOR walk so the cheapest rejection happens first, (b) wraps the version-pinned UPDATE in `transaction.atomic()`, and (c) returns 409 with the expected body shapes from CONTEXT §"If-Match Header Format".
```python
# Phase 9 D-05: optimistic-lock header (FULL save only, not viewport-only writes)
if_match = request.headers.get('If-Match', '').strip()
if not if_match:
    return JsonResponse({'error': 'version_required'}, status=409)
try:
    loaded_version = int(if_match)
except ValueError:
    return JsonResponse({'error': 'version_required'}, status=409)

# … existing IDOR walk runs here unchanged …

# Phase 9 D-06: atomic version-pinned UPDATE
new_viewport = (
    payload['viewport']
    if 'viewport' in payload and isinstance(payload['viewport'], dict)
    else diagram.viewport
)
with transaction.atomic():
    rowcount = SignalFlowDiagram.objects.filter(
        id=diagram.id, version=loaded_version,
    ).update(
        canvas_state=canvas_state,
        viewport=new_viewport,
        version=F('version') + 1,
        updated_at=timezone.now(),
    )
if rowcount == 0:
    current = (
        SignalFlowDiagram.objects.filter(id=diagram.id)
        .values_list('version', flat=True).first()
    )
    return JsonResponse(
        {'error': 'version_conflict', 'current_version': current},
        status=409,
    )
return JsonResponse({'ok': True, 'version': loaded_version + 1})
```

**Decorators + viewer-block + exception envelope to KEEP verbatim (lines 7545-7547, 7561-7564, 7633-7637):**
```python
@login_required
@require_POST
def signal_flow_autosave(request, diagram_id):
    …
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    …
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Bad JSON'}, status=400)
    except Exception:
        _signal_flow_logger.exception('signal_flow_autosave failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

**Viewport-only branch (`?viewport_only=1`) must remain LAST-WRITE-WINS** per D-05 — do NOT read `If-Match` on that path. Keep `views.py:7572-7580` verbatim.

---

### 2. `signal_flow_state` — wire `_enrich_nodes()` on GET

**Analog:** itself, `planner/views.py:7528-7542` (the Phase 7 stub).

**Existing stub to extend — `views.py:7528-7542`:**
```python
@staff_member_required
def signal_flow_state(request, diagram_id):
    diagram = _get_diagram_for_request(request, diagram_id)
    if not diagram:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse({
        'canvas_state': diagram.canvas_state,
        'viewport': diagram.viewport,
        'version': diagram.version,
    })
```

**Phase 9 extension pattern (D-12):**
```python
@staff_member_required
def signal_flow_state(request, diagram_id):
    diagram = _get_diagram_for_request(request, diagram_id)
    if not diagram:
        return JsonResponse({'error': 'Not found'}, status=404)
    enriched = _enrich_nodes(diagram.canvas_state or {}, request.current_project)
    return JsonResponse({
        'canvas_state': enriched,
        'viewport': diagram.viewport,
        'version': diagram.version,
    })
```

The autosave POST does NOT call `_enrich_nodes()` (D-12: "Save responses do not re-enrich"). Only the GET path runs it.

---

### 3. `_enrich_nodes()` — NEW helper above `signal_flow_state`

**Analog — IDOR walk shape:** `planner/views.py:7587-7624` (re-used `(ct_id, obj_id)` extraction loop and `SpeakerArray`-via-`prediction__project` exception).

**Analog — bulk-fetch idiom (one query per content type, dict comprehension over `.values_list`):** `planner/views.py:6733-6738` (`seed_maps` for the multitrack module). This is the closest existing pattern in `views.py` for "bulk SELECT per type, build a `{id: …}` map":
```python
seed_maps = {
    'input':  {row[0]: (row[1], row[2]) for row in ConsoleInput.objects.filter(id__in=valid_input_ids).values_list('id', 'default_record', 'default_record_color')},
    'aux':    {row[0]: (row[1], row[2]) for row in ConsoleAuxOutput.objects.filter(id__in=valid_aux_ids).values_list('id', 'default_record', 'default_record_color')},
    'matrix': {row[0]: (row[1], row[2]) for row in ConsoleMatrixOutput.objects.filter(id__in=valid_matrix_ids).values_list('id', 'default_record', 'default_record_color')},
    'stereo': {row[0]: (row[1], row[2]) for row in ConsoleStereoOutput.objects.filter(id__in=valid_stereo_ids).values_list('id', 'default_record', 'default_record_color')},
}
```

**Analog — deep-copy of a JSON-ish blob before mutation:** no `copy.deepcopy` usage in `planner/views.py` today, but `planner/utils/nuendo_live_export.py:22` already does `import copy` and `copy.deepcopy(seed_track)` (line 346) — same idiom. Use stdlib `copy.deepcopy`; no new dependency.

**`_enrich_nodes()` recipe (D-12 + D-13 + D-14):**
```python
import copy
from django.contrib.contenttypes.models import ContentType
from collections import defaultdict

def _enrich_nodes(canvas_state, project):
    """Refresh GFK-linked cell labels and flag missing equipment as orphans.

    D-12: GET-only. Deep-copies the input — never mutates the persisted blob.
    D-13: One SELECT per content type. SpeakerArray scopes via
          `prediction__project`; others via `project` (same predicate as the
          IDOR walk at views.py:7587-7624).
    D-14: Live ref  -> isOrphan = False, savedLabel + attrs.label.text = <live name>
          Missing   -> isOrphan = True,  savedLabel + label.text untouched
          Non-linked cells (e.g. Generic, connectors) untouched.
    Never raises on missing CT -> treated as orphan.
    """
    if not isinstance(canvas_state, dict):
        return canvas_state
    result = copy.deepcopy(canvas_state)
    cells = result.get('cells') or []

    # 1) Group (ct_id, obj_id) pairs by content_type.
    by_ct = defaultdict(set)   # {ct_id: {obj_id, …}}
    for cell in cells:
        prop = cell.get('showstack') if isinstance(cell, dict) else None
        if not isinstance(prop, dict):
            continue
        ct_id, obj_id = prop.get('contentTypeId'), prop.get('objectId')
        if ct_id and obj_id:
            by_ct[ct_id].add(obj_id)

    # 2) Bulk SELECT per content type.
    resolved = {}   # {(ct_id, obj_id): name}
    for ct_id, obj_ids in by_ct.items():
        ct = ContentType.objects.filter(id=ct_id).first()
        if not ct:
            continue   # unknown CT — every cell with this ct_id becomes orphan
        Model = ct.model_class()
        if Model is None:
            continue
        model_name = Model.__name__
        if model_name == 'SpeakerArray':
            qs = Model.objects.filter(id__in=obj_ids, prediction__project=project)
        elif hasattr(Model, 'project') or model_name in ('Console', 'Device', 'CommBeltPack'):
            qs = Model.objects.filter(id__in=obj_ids, project=project)
        else:
            continue   # no project scope -> all orphan
        for row_id, row_name in qs.values_list('id', 'name'):
            resolved[(ct_id, row_id)] = row_name

    # 3) Second pass — mutate each linked cell.
    for cell in cells:
        prop = cell.get('showstack') if isinstance(cell, dict) else None
        if not isinstance(prop, dict):
            continue
        ct_id, obj_id = prop.get('contentTypeId'), prop.get('objectId')
        if not ct_id or not obj_id:
            continue
        name = resolved.get((ct_id, obj_id))
        if name is not None:
            prop['isOrphan'] = False
            prop['savedLabel'] = name
            attrs = cell.setdefault('attrs', {})
            label = attrs.setdefault('label', {})
            label['text'] = name
        else:
            prop['isOrphan'] = True
            # savedLabel + attrs.label.text intentionally untouched (D-14)

    return result
```

**Placement:** above `signal_flow_state` (D-12), below `_get_diagram_for_request`. No decorator (plain helper).

---

### 4. Autosave debounce controller — replaces manual-save IIFE

**Analog — debounce shape:** `signal_flow_editor.js:549-571` (the viewport-only debounce). Mirror this structure but route to the full autosave URL with the version header.

**Existing viewport-only debounce (verbatim — DO NOT modify; autosave is a parallel controller):**
```javascript
// signal_flow_editor.js:549-571
var viewportTimer = null;
function schedulePersistViewport() {
  if (viewportTimer) clearTimeout(viewportTimer);
  viewportTimer = setTimeout(function () {
    viewportTimer = null;
    var payload = {
      viewport: {
        x: currentViewport.x, y: currentViewport.y,
        scale: currentViewport.scale, snapEnabled: currentViewport.snapEnabled,
      },
    };
    fetch(autosaveUrl + '?viewport_only=1', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(payload),
    }).catch(function () {
      // Silent — viewport persistence is best-effort. Don't pester the user.
    });
  }, 800);
}
```

**Existing manual `doSave` (lines 1332-1384) — REMOVE the button-bound version. KEEP the `currentVersion`-bump and `setSaveStatus` plumbing. Three-state mapping is locked by D-04:**
```javascript
// EXACT COPY (D-04 — locked wording, do not paraphrase):
function setSaveStatus(state) {
  if (!saveStatusEl) return;
  saveStatusEl.classList.remove('is-saving', 'is-error');
  if (state === 'saved')    saveStatusEl.textContent = 'All changes saved.';
  else if (state === 'saving') {
    saveStatusEl.textContent = 'Saving…';
    saveStatusEl.classList.add('is-saving');
  } else if (state === 'error') {
    saveStatusEl.textContent = 'Save failed — retry';
    saveStatusEl.classList.add('is-error');
  }
}
```

**`postJSON` helper to reuse (`signal_flow_editor.js:55-64`):**
```javascript
function postJSON(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    credentials: 'same-origin',
    body: JSON.stringify(body || {}),
  }).then(function (r) {
    return r.json().then(function (data) { return { status: r.status, data: data }; });
  });
}
```
**NOTE:** the Phase 9 autosave needs `If-Match` and (for the unload flush) `keepalive: true` — `postJSON` does NOT support either. Use `fetch` directly inside the autosave controller and keep `postJSON` for everything else.

**Replacement controller (D-01 / D-02 / D-03 / D-08 / D-09 / D-10 / D-11) — replaces lines 1306-1435 entirely except for the `window.__sfd.*` handoff block:**
```javascript
// State
var saveStatusEl = document.getElementById('sfd-save-status');
var diagramDirty = false;
var savingNow    = false;
var conflicted   = false;
var autosaveTimer = null;
var lastFailedPayload = null;   // for the "Save failed — retry" click

// (setSaveStatus copied verbatim from above)

function scheduleAutosave() {
  if (conflicted) return;
  diagramDirty = true;
  if (autosaveTimer) clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(flushAutosave, 1500);   // D-02
}

function flushAutosave(opts) {
  opts = opts || {};
  if (autosaveTimer) { clearTimeout(autosaveTimer); autosaveTimer = null; }
  if (!diagramDirty) return Promise.resolve();
  if (conflicted)    return Promise.resolve();
  if (savingNow && !opts.force) return Promise.resolve();

  savingNow = true;
  setSaveStatus('saving');
  var payloadObj = {
    canvas_state: graph.toJSON(),
    viewport: {
      x: currentViewport.x, y: currentViewport.y,
      scale: currentViewport.scale, snapEnabled: currentViewport.snapEnabled,
    },
  };
  var fetchOpts = {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
      'If-Match': String(currentVersion),
    },
    body: JSON.stringify(payloadObj),
  };
  if (opts.keepalive) fetchOpts.keepalive = true;

  return fetch(autosaveUrl, fetchOpts).then(function (r) {
    return r.json().then(function (data) { return { status: r.status, data: data }; });
  }).then(function (resp) {
    if (resp.status === 200 && resp.data && resp.data.ok) {
      currentVersion = resp.data.version || (currentVersion + 1);
      diagramDirty = false;
      savingNow    = false;
      setSaveStatus('saved');
      return;
    }
    if (resp.status === 409) {
      savingNow = false;
      showConflictBanner();   // sets conflicted = true, locks canvas
      return;
    }
    if (resp.status === 422) {
      savingNow = false;
      lastFailedPayload = payloadObj;
      setSaveStatus('error');
      showToast(resp.data && resp.data.error
        ? resp.data.error
        : "Couldn't save — equipment reference is out of project.", 'error');
      return;
    }
    savingNow = false;
    lastFailedPayload = payloadObj;
    setSaveStatus('error');
    showToast((resp.data && resp.data.error) || 'Save failed. Please try again.', 'error');
  }).catch(function () {
    savingNow = false;
    lastFailedPayload = payloadObj;
    setSaveStatus('error');
    showToast('Network error. Try again.', 'error');
  });
}

// D-03: clickable status span retries the last failed save
if (saveStatusEl) {
  saveStatusEl.addEventListener('click', function () {
    if (!saveStatusEl.classList.contains('is-error')) return;
    diagramDirty = true;     // re-arm
    flushAutosave({ force: true });
  });
}

// D-01: graph events that trigger autosave
graph.on('add remove change:source change:target', scheduleAutosave);
// Mid-drag position events do NOT trigger autosave — only the drag-end.
paper.on('element:pointerup', function () {
  // Only schedule if a drag actually moved the cell (caller can refine —
  // the simplest gate is: any pointerup on a single-selection drag).
  scheduleAutosave();
});
// Inspector property changes (signalType/direction/circuitLabel) — wire from
// the existing inspector handlers at lines 1246-1289 by calling scheduleAutosave()
// after each applySignalType / applyDirection / applyCircuitLabel call.

// D-09 / D-10 / D-11: keepalive flush on tab-hide / page-hide
function maybeKeepaliveFlush() {
  if (!diagramDirty) return;
  if (savingNow) return;
  if (conflicted) return;
  flushAutosave({ keepalive: true });
}
document.addEventListener('visibilitychange', function () {
  if (document.visibilityState === 'hidden') maybeKeepaliveFlush();
});
window.addEventListener('pagehide', maybeKeepaliveFlush);
// NO beforeunload listener — browsers cancel the fetch (PITFALLS.md §3).
// NO navigator.sendBeacon — 64 KB cap silently drops typical diagrams.
```

**Handoff block to KEEP verbatim (lines 1404-1431) except `window.__sfd.save` now points at the force-flush:**
```javascript
window.__sfd.save = function () { return flushAutosave({ force: true }); };
```

---

### 5. 409 conflict banner — JS lock + reveal

**Analog — DOM-attribute toggling for canvas lock:** `signal_flow_editor.js:586` (`paperEl.style.setProperty('cursor', 'grab', 'important')`) — CLAUDE.md mandate that all inline style writes against admin-template DOM nodes use `setProperty(prop, value, 'important')`.

**Analog — reveal-via-removing-`hidden`:** `signal_flow_editor.js:1201-1212` (the inspector `showInspector` / `hideInspector` pair):
```javascript
function showInspector() {
  if (!inspectorEl) return;
  inspectorEl.removeAttribute('hidden');
  inspectorEl.style.setProperty('display', 'block', 'important');
}
function hideInspector() {
  if (!inspectorEl) return;
  inspectorEl.setAttribute('hidden', '');
  inspectorEl.style.setProperty('display', 'none', 'important');
}
```

**Pattern to write — D-07 / D-08:**
```javascript
function showConflictBanner() {
  conflicted = true;
  // Cancel any pending debounce
  if (autosaveTimer) { clearTimeout(autosaveTimer); autosaveTimer = null; }
  var banner = document.getElementById('sfd-conflict-banner');
  if (banner) {
    banner.removeAttribute('hidden');
    banner.style.setProperty('display', 'flex', 'important');
  }
  // D-08: lock the canvas. Toolbar zoom/pan/snap stay live.
  var paperEl = document.getElementById('sfd-paper');
  if (paperEl) paperEl.style.setProperty('pointer-events', 'none', 'important');
}

// Reload handler — bind once at controller setup
var reloadBtn = document.getElementById('sfd-conflict-reload');
if (reloadBtn) reloadBtn.addEventListener('click', function () {
  window.location.reload();
});
```

The keyboard-shortcut handler at `signal_flow_editor.js:849-866` (Ctrl+Z/Y) and the Delete-handler nearby need a `if (conflicted) return;` early-exit per D-08.

---

### 6. Orphan ghost render hook + node inspector

**Analog — same-event link-style hook:** `signal_flow_editor.js:1175-1183`. This is the closest pattern: a `graph.on('add', …)` handler that reads `cell.prop(...)` and applies a visual style on every cell. The orphan toggle uses an identical shape but writes an attribute to the cell's root SVG.

```javascript
// signal_flow_editor.js:1175-1183 (existing — copy the shape)
graph.on('add', function (cell, _coll, _opts) {
  if (cell.isLink && cell.isLink()) {
    var type = cell.prop('signalType') || 'analog';
    applySignalType(cell, type);
    applyDirection(cell, cell.prop('direction') || 'forward');
    var label = cell.prop('circuitLabel') || '';
    if (label) applyCircuitLabel(cell, label);
  }
});
```

**Pattern to write — D-15 orphan ghost via root-SVG attribute toggle:**
```javascript
// Mirror the structure above. Set joint-orphan="true" on the cell's root
// SVG <g>; the CSS rules in section 11 do the visual work.
function applyOrphanState(cell) {
  var view = paper.findViewByModel(cell);
  if (!view || !view.el) return;
  var sub = cell.prop('showstack') || {};
  if (sub.isOrphan === true) view.el.setAttribute('joint-orphan', 'true');
  else                       view.el.removeAttribute('joint-orphan');
}
graph.on('add', function (cell) {
  if (cell.isElement && cell.isElement()) applyOrphanState(cell);
});
graph.on('change:showstack', applyOrphanState);
// Connectors attached to an orphan: walk each link on graph load and tag if
// either endpoint cell carries isOrphan = true (per D-15 connector opacity rule).
```

**Analog — inspector mode-switch (existing pattern to extend):** `signal_flow_editor.js:1230-1242` (`onSelectionChanged`). Currently shows the inspector only when the single selection is a link. Phase 9 D-16 widens this to also handle a single element selection — same `showInspector()` call, different field set rendered.

```javascript
// signal_flow_editor.js:1230-1242 (existing — extend in place)
window.__sfd.onSelectionChanged = function (selectedIds) {
  if (selectedIds.length === 1) {
    var cell = graph.getCell(selectedIds[0]);
    if (cell && cell.isLink && cell.isLink()) {
      inspectorCurrentLink = cell;
      syncInspectorFromLink(cell);
      showInspector();
      return;
    }
  }
  hideInspector();
};
```

**Pattern to write — D-16 node-mode inspector:**
```javascript
window.__sfd.onSelectionChanged = function (selectedIds) {
  if (selectedIds.length === 1) {
    var cell = graph.getCell(selectedIds[0]);
    if (cell && cell.isLink && cell.isLink()) {
      setInspectorMode('connector', cell);
      showInspector();
      return;
    }
    if (cell && cell.isElement && cell.isElement()) {
      setInspectorMode('node', cell);
      showInspector();
      return;
    }
  }
  hideInspector();
};

function setInspectorMode(mode, cell) {
  // Show/hide the per-mode field groups inside #sfd-inspector. Node mode
  // exposes Re-link + Delete; connector mode keeps the existing fields.
  // Re-link button → window.__sfd.openEquipmentPicker(shapeType, cell)
  //   shapeType derived from cell.get('type').split('.').pop()
  // Delete button  → cell.remove() (existing undo-batching covers it)
}
```

**Re-link affordance reuses Phase 8 plumbing — `signal_flow_editor.js:1414`:**
```javascript
window.__sfd.openEquipmentPicker = openEquipmentPicker;
```
On pick, `assignPickerResult` at `signal_flow_editor.js:492-504` already writes `(contentTypeId, objectId, savedLabel)` — Phase 9 only needs to add `node.prop('showstack/isOrphan', false)` after the existing writes so the ghost styling clears.

---

### 7. Toolbar HTML — remove Save button, keep status span

**Existing — `editor.html:51-55`:**
```html
<span class="sfd-toolbar-spacer"></span>
<div class="sfd-btn-group" data-group="persist">
  <button type="button" id="sfd-save" aria-label="Save diagram">Save</button>
  <span id="sfd-save-status">All changes saved.</span>
</div>
```

**Phase 9 — D-03 (remove the button element entirely):**
```html
<span class="sfd-toolbar-spacer"></span>
<div class="sfd-btn-group" data-group="persist">
  <span id="sfd-save-status" role="status" aria-live="polite">All changes saved.</span>
</div>
```
The `role="status"` + `aria-live="polite"` are additive — the status span becomes the only persistence affordance, including the clickable retry in `is-error` state.

---

### 8. Conflict banner element — NEW, between toolbar and canvas

**Analog — `templates/planner/mic_tracker.html:407-411`** (existing prior art for a full-width refresh banner with inline `Reload`):
```html
<div id="mic-tracker-update-banner">
    🔄 <strong id="banner-message">Updates Available — refreshing in 5s</strong>
    <button onclick="location.reload()" style="…">Refresh Now</button>
    <button id="banner-dismiss" style="…">Dismiss</button>
</div>
```
Note that the mic tracker banner is **dismissable**. Phase 9's banner is **NOT** (D-07). The locked copy from DGM-07 is the only message text.

**Pattern to write — append between `</div>` closing `#sfd-toolbar` (line 56) and `<div id="sfd-canvas-container">` (line 58):**
```html
<div id="sfd-conflict-banner" role="alert" hidden>
  <span class="sfd-conflict-msg">Diagram was modified elsewhere — reload to see latest.</span>
  <button type="button" id="sfd-conflict-reload">Reload</button>
</div>
```

---

### 9. Banner CSS — extend `signal_flow.css`

**Analog — error-color token reuse:** `signal_flow.css:102-104` and `signal_flow.css:468-470`. Both already lock the project's error red to `#dc2626`:
```css
/* signal_flow.css:102-104 */
#sfd-save-status.is-error {
  color: #dc2626 !important;
}

/* signal_flow.css:468-470 */
.sfd-toast--error {
  border-left: 3px solid #dc2626 !important;
}
```
The CONTEXT "Claude's Discretion" says "default to a strong red (≈ `#c0392b` family)" but `#dc2626` is already the locked project red — prefer the existing token over a new shade for consistency.

**Pattern to write — Section 10 (insert after Section 9 "Empty canvas hint", before file end):**
```css
/* =========================================================================
   SECTION 10 — 409 Conflict banner (Phase 9 D-07)
   Full-width red bar pinned below #sfd-toolbar, above #sfd-canvas-container.
   Non-dismissable. Locked copy from DGM-07.
   ========================================================================= */

#sfd-conflict-banner {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  background-color: #dc2626 !important;
  color: #ffffff !important;
  font-weight: 600 !important;
  font-size: 13px !important;
  padding: 10px 16px !important;
  border-bottom: 1px solid #991b1b !important;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif !important;
}

#sfd-conflict-banner[hidden] {
  display: none !important;
}

.sfd-conflict-msg {
  flex: 1 1 auto !important;
}

#sfd-conflict-reload {
  background-color: #ffffff !important;
  color: #dc2626 !important;
  border: 1px solid #ffffff !important;
  border-radius: 4px !important;
  padding: 6px 14px !important;
  font-size: 12px !important;
  font-weight: 700 !important;
  cursor: pointer !important;
  font-family: inherit !important;
}

#sfd-conflict-reload:hover {
  background-color: #fee2e2 !important;
}

/* Clickable retry state on the status span (Phase 9 D-03). */
#sfd-save-status.is-error {
  cursor: pointer !important;
  text-decoration: underline !important;
}
```

---

### 10. Orphan ghost CSS — extend `signal_flow.css`

**Analog — attribute-driven SVG styling:** `signal_flow.css:501-516` (selection visuals — same shape: attribute selector on `.joint-element` + targeted `[joint-selector="…"]` inner-element styling).
```css
/* signal_flow.css:501-516 (existing — same selector strategy) */
.joint-element.is-selected [joint-selector="body"] {
  stroke: #0d9488 !important;
  stroke-width: 2.5 !important;
}
```

**Pattern to write — Section 11 (insert after Section 10):**
```css
/* =========================================================================
   SECTION 11 — Orphan ghost render (Phase 9 D-15 + SHP-07)
   JS toggles joint-orphan="true" on each ghosted cell's root SVG <g>.
   ========================================================================= */

.joint-element[joint-orphan="true"] [joint-selector="body"],
.joint-element[joint-orphan="true"] [joint-selector="band"] {
  stroke: #888 !important;
  stroke-dasharray: 4 3 !important;
  fill-opacity: 0.4 !important;
}

.joint-element[joint-orphan="true"] [joint-selector="label"] {
  fill: #555 !important;
}

.joint-link[joint-orphan-attached="true"] [joint-selector="line"] {
  opacity: 0.5 !important;
}
```
(Phase 8 shapes use `[joint-selector="body"]` consistently — see `signal_flow_editor.js:128-139`. The `band` selector is added so the Console teal stripe also fades.)

---

## Shared Patterns

### IDOR (project-scope) walk on linked equipment

**Source:** `planner/views.py:7587-7624` (existing — current `signal_flow_autosave`)
**Apply to:** `_enrich_nodes()` bulk lookup (predicates only — not the cell-by-cell `.exists()` walk)

Key rule: `SpeakerArray` uses `prediction__project=project`; all others use `project=project`; unknown content_types are treated as out-of-scope (in autosave: 422; in enrich: orphan).

### Reusable helpers (already in scope inside the IIFE)

**Source:** `signal_flow_editor.js:50-78` and `window.__sfd` handoff at 1404-1431.
**Apply to:** every Phase 9 JS hook.

```javascript
csrfToken()      // signal_flow_editor.js:50-53
postJSON(url, body)   // signal_flow_editor.js:55-64   (NO keepalive support)
getJSON(url)     // signal_flow_editor.js:66-69
showToast(msg, level) // signal_flow_editor.js:71-78  (transient errors only)
graph, paper, paperEl, currentViewport, currentVersion, autosaveUrl, csrfToken — closure vars
window.__sfd.openEquipmentPicker = openEquipmentPicker  // signal_flow_editor.js:1414
```

### Viewer block + IDOR + exception envelope (every signal-flow mutate view)

**Source:** `planner/views.py:7361-7387` + the boilerplate at 7561-7637.
**Apply to:** any new Phase 9 view code (but Phase 9 only modifies `signal_flow_autosave` and `signal_flow_state` — neither needs a new view).
```python
@login_required
@require_POST
def …(request, diagram_id):
    viewer_block = _signal_flow_viewer_block(request)
    if viewer_block is not None:
        return viewer_block
    try:
        diagram = _get_diagram_for_request(request, diagram_id)
        if not diagram:
            return JsonResponse({'error': 'Not found'}, status=404)
        …
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Bad JSON'}, status=400)
    except Exception:
        _signal_flow_logger.exception('… failed')
        return JsonResponse({'error': 'Server error.'}, status=500)
```

### DOM style overrides from JS

**Source:** CLAUDE.md §"Overriding Django admin CSS from JavaScript" + `signal_flow_editor.js:586` + `signal_flow_editor.js:1205,1210`.
**Apply to:** banner reveal, canvas pointer-events lock, status span style writes — anything outside the JointJS-managed `#sfd-paper` SVG subtree.
```javascript
el.style.setProperty('display', 'flex', 'important');
el.style.setProperty('pointer-events', 'none', 'important');
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| Keepalive `fetch(..., { keepalive: true })` on `visibilitychange` / `pagehide` | client controller | event-driven flush | First usage in the codebase — no existing analog. PITFALLS.md §3 prescribes the exact recipe; CONTEXT §"Autosave Debounce Recipe" + D-09/D-10 inline the full code. Implement from the CONTEXT spec, not from prior code. |
| `If-Match` header read on Django view | view | request-response | First usage in the codebase. Use `request.headers.get('If-Match', '').strip()` per CONTEXT §"If-Match Header Format". |

---

## Metadata

**Analog search scope:**
- `planner/views.py` (full file — 7700+ lines, targeted reads only)
- `planner/static/planner/js/signal_flow_editor.js` (full Phase 8 IIFE)
- `planner/static/planner/css/signal_flow.css` (full file)
- `planner/templates/planner/signal_flow/editor.html` (full file)
- `templates/planner/mic_tracker.html` (banner analog only)
- `planner/utils/nuendo_live_export.py` (deepcopy idiom only)

**Files scanned (incidental):** ~6
**Pattern extraction date:** 2026-05-21
