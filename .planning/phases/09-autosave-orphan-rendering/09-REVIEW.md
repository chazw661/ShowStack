---
phase: 09-autosave-orphan-rendering
reviewed: 2026-05-21T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - planner/views.py
  - planner/static/planner/js/signal_flow_editor.js
  - planner/static/planner/css/signal_flow.css
  - planner/templates/planner/signal_flow/editor.html
  - planner/tests/test_signal_flow_phase9.py
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-05-21
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 9 adds server-side optimistic-lock autosave (`If-Match` / atomic `UPDATE`), server-side label enrichment and orphan detection (`_enrich_nodes`), and client-side autosave debounce + conflict-banner UX. The security posture is good — the IDOR walk in `signal_flow_autosave` is correct and consistent with `_enrich_nodes`, and the XSS surface in the node-mode inspector buttons is clean (all text set via `textContent`, no `innerHTML`). The optimistic-lock database path is logically correct.

Four warnings were found — none are data-loss bugs in the happy path, but two can cause silent state divergence under race conditions that are reachable in production (debounced save fires while an in-flight keepalive is landing, and keepalive flush does not reset `diagramDirty`). Three info items cover a missing HTTP method guard, a `hasattr` IDOR footgun, and a dead console.log.

---

## Warnings

### WR-01: `force` flag bypasses `savingNow` guard — stale `currentVersion` possible on concurrent forced flush

**File:** `planner/static/planner/js/signal_flow_editor.js:1564`

**Issue:** `flushAutosave({ force: true })` skips the `savingNow` early-return guard. Two code paths call `force: true` — the retry click handler (line 1641) and the `window.__sfd.save` shim (line 1724). If a normal debounced POST is currently in-flight (setting `savingNow = true`) and the user simultaneously triggers a force-flush (e.g. by clicking the error status span), two concurrent POSTs are dispatched both carrying the same `If-Match: <currentVersion>`. The first to land advances the server version. The second lands, is accepted if it arrives while the server version still matches (race window is the network RTT), and the client's `currentVersion` is written twice. In practice the main danger is a silent dropped save, not corruption — but it is surprising behaviour for a flag named "force". The retry path is the higher-risk one because `lastFailedPayload` exists precisely when a prior save failed and the state is already suspect.

**Fix:**
```javascript
// In flushAutosave, change the guard to also block force when a save is
// genuinely in-flight:
if (savingNow) return Promise.resolve();   // no force bypass
```
The retry click path is safe because `savingNow` is set to `false` in every failure branch before `setSaveStatus('error')` is called, so by the time the user can click the retry it will always be `false`. Remove the `&& !opts.force` condition entirely.

---

### WR-02: `maybeKeepaliveFlush` does not reset `diagramDirty` — debounce re-fires after page returns to foreground

**File:** `planner/static/planner/js/signal_flow_editor.js:1677-1681`

**Issue:** `maybeKeepaliveFlush` calls `flushAutosave({ keepalive: true })` and returns immediately. `flushAutosave` sets `savingNow = true` but — because the page is hidden — the `.then()` callback runs after the tab is backgrounded and may run after a subsequent `visibilitychange` back to visible. When the tab returns to visible, `diagramDirty` is still `true` (it is only cleared in the success branch of the `.then()`). This does not cause data loss — the re-fire sends a valid `If-Match` and the server correctly handles it — but it does fire a redundant save that resets `savingNow` and resets status to 'saving' / 'saved' again, which can produce a visible UI flash if the user is already looking at the page. More concretely: if the tab-hide keepalive fails (network gone on mobile), `diagramDirty` stays `true` but `savingNow` is reset to `false` by the catch, so the 1500 ms debounce timer that may have been cancelled by the flush is never rescheduled — the user's unsaved change is silently abandoned. 

**Fix:**
```javascript
function maybeKeepaliveFlush() {
  if (!diagramDirty) return;
  if (savingNow)     return;
  if (conflicted)    return;
  flushAutosave({ keepalive: true }).catch(function () {
    // Keepalive fetch failed (network down on hide). Re-schedule a normal
    // debounce so the next visible event gets another attempt.
    scheduleAutosave();
  });
}
```

---

### WR-03: `signal_flow_state` missing `@require_GET` — POST to state URL is silently accepted

**File:** `planner/views.py:7602`

**Issue:** `signal_flow_state` has `@staff_member_required` but no HTTP-method guard. A POST, PUT, or DELETE to `/audiopatch/signal-flow/<id>/state/` will reach the view, call `_get_diagram_for_request`, and return the enriched JSON as if it were a GET. Django does not enforce method safety on its own. The immediate risk is low (the view is read-only), but the missing guard is inconsistent with every other Phase 8-9 view that uses `@require_POST` or `@require_http_methods`, and it prevents Django from automatically returning `405 Method Not Allowed` for CSRF-exempt methods.

**Fix:**
```python
@staff_member_required
@require_GET          # add this line
def signal_flow_state(request, diagram_id):
    ...
```
`require_GET` is already imported at `views.py:6`.

---

### WR-04: `_enrich_nodes` — `hasattr(Model, 'project')` is an unreliable IDOR gate

**File:** `planner/views.py:7573`

**Issue:** The project-scope predicate in `_enrich_nodes` (line 7573) uses `hasattr(Model, 'project')` as the primary test for whether a model can be scoped via `project=project`. This is fragile: `hasattr` returns `True` for any Django model that has a class-level `project` descriptor — including models where `project` is a property, a related manager, or any non-FK attribute named `project`. A future model that adds a `project` attribute for unrelated reasons (e.g. a `@property` that returns a string) would silently pass the `hasattr` check, and `Model.objects.filter(id__in=..., project=project)` would either match nothing (treating all such cells as orphans) or — if the attribute happened to be filterable — scope incorrectly. The autosave IDOR walk at line 7701 has the same pattern and carries the same risk.

The current four concrete model types (`Console`, `Device`, `CommBeltPack`, `SpeakerArray`) are handled by explicit name checks that are correct. The `hasattr` branch is a forward-compatibility fallback that could admit unexpected models.

**Fix:** Invert the guard — use an explicit allowlist:
```python
KNOWN_PROJECT_MODELS = frozenset({'Console', 'Device', 'CommBeltPack'})
# ...
if model_name == 'SpeakerArray':
    qs = Model.objects.filter(id__in=obj_ids, prediction__project=project)
elif model_name in KNOWN_PROJECT_MODELS:
    qs = Model.objects.filter(id__in=obj_ids, project=project)
else:
    continue  # unknown model -> orphan (safe default)
```
Apply the same change symmetrically to `signal_flow_autosave` at line 7701.

---

## Info

### IN-01: `console.log` left in initial-state load path

**File:** `planner/static/planner/js/signal_flow_editor.js:295-297`

**Issue:** A `console.log` call remains in the state-load success path, logging diagram ID, version, and cell count on every editor page load. This is not harmful but will appear in every user's DevTools console in production.

```javascript
console.log('[SFD] paper ready — diagram', diagramId,
            '— version', currentVersion,
            '— cells', graph.getCells().length);
```

**Fix:** Remove or gate behind a debug flag (e.g. `window.__sfd_debug && console.log(...)`).

---

### IN-02: `signal_flow_state` missing `@require_GET` is also a test coverage gap

**File:** `planner/tests/test_signal_flow_phase9.py` (all `SignalFlowStateEnrichmentTests` methods)

**Issue:** All 5 enrichment tests use `self.client.get(...)`. None tests that `POST /state/` returns `405`. Once WR-03 is fixed, a corresponding test should be added:

```python
def test_post_to_state_returns_405(self):
    diagram = SignalFlowDiagram.objects.create(...)
    resp = self.client.post(reverse('planner:signal_flow_state', args=[diagram.id]),
                            data='{}', content_type='application/json')
    self.assertEqual(resp.status_code, 405)
```

---

### IN-03: `_enrich_nodes` imported `copy` and `defaultdict` inside function body on every call

**File:** `planner/views.py:7542-7544`

**Issue:** `import copy` and `from collections import defaultdict` and `from django.contrib.contenttypes.models import ContentType` are executed inside `_enrich_nodes` on every call. Python caches module imports so this is not a correctness issue, but it is inconsistent with the rest of `views.py` which performs all standard-library and Django imports at the top of the file. A function called on every `GET /state/` request (which will grow with autosave round-trips) should not carry import statements.

**Fix:** Move `import copy` and `from collections import defaultdict` to the top of `views.py`. `ContentType` is already imported elsewhere in the file — check and consolidate.

---

_Reviewed: 2026-05-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
