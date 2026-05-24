---
phase: 11-ports-and-resize
reviewed: 2026-05-24T17:05:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - planner/views.py
  - planner/static/planner/js/signal_flow_editor.js
  - planner/static/planner/css/signal_flow.css
findings:
  critical: 1
  warning: 0
  info: 2
  total: 3
status: issues_found
---

# Phase 11: Code Review Report (Gap-Closure: 11-07 + 11-08)

**Reviewed:** 2026-05-24T17:05:00Z
**Depth:** standard
**Files Reviewed:** 3
**Diff Range:** `6c39d65..HEAD` (commits 133cc97, fabffdf, 9844745)
**Status:** issues_found

## Summary

Reviewed the three gap-closure changes for phase 11 (GAP-11.1 through GAP-11.5):

1. **Backend (`signal_flow_label_autocomplete`)** — new `SHAPE_CLASS_SOURCES` allowlist + `shape_class` query-param filter. Backend implementation is clean: tight allowlist (4 known cell types), allowlist-only filter (unknown values fall through, no exception), preserves backward compatibility for the connector circuit-label call site, and the IDOR guard (`device__project=current_project` etc.) remains intact on every row. No injection risk — `shape_class` is only used as a dict key and as a string-equality filter against hardcoded tag strings. The `@staff_member_required` decorator matches the project-wide pattern used by the rest of `planner/views.py`.

2. **JS (`signal_flow_editor.js`)** — `addAuthoredPort` opacity:1 override is correct (generic `standardPortGroups` ports at lines 104/109 still keep opacity:0 for hover-reveal). `sumLabelWidths` / `edgeWidthRequired` math implements RESEARCH §Q2 horizontal-edge formula correctly. `refreshPortAuthorBlock` listbox purge is correct given that `attachAutocompleteToInput` resolves `inputEl.closest('.sfd-field')` to `portAuthorBlock` itself (the only `.sfd-field` ancestor — confirmed at line 2057).

3. **CSS Section 16** — colors match Section 4 canonical `.sfd-field input[type="text"]` pattern verbatim (lines 260-266). `background` shorthand correctly replaced with `background-color` longhand to avoid wiping unrelated background properties. `::placeholder` rule reuses `#aaa` from `.sfd-field-help` — no new hex codes introduced.

**However, one critical bug was found in the URL builder for the new per-shape autocomplete scoping.** The query string composition collides with `fetchAcResults` (existing Phase 10 code), producing a malformed URL that silently breaks BOTH the new shape-scoping AND the core search-term filtering. Details below.

## Critical Issues

### CR-01: `portAutocompleteUrl` produces malformed double-`?` query string, breaking GAP-11.1 silently

**File:** `planner/static/planner/js/signal_flow_editor.js:2133-2135` (in conjunction with `planner/static/planner/js/signal_flow_editor.js:2608`)

**Issue:**
The new GAP-11.1 URL builder pre-appends `?shape_class=<type>` to `labelAutocompleteUrl`:

```js
// signal_flow_editor.js:2133-2135
var portAutocompleteUrl = labelAutocompleteUrl
  + (labelAutocompleteUrl.indexOf('?') === -1 ? '?' : '&')
  + 'shape_class=' + encodeURIComponent(cell.get('type') || '');
```

The resulting `portAutocompleteUrl` is then passed to `attachAutocompleteToInput`, which calls `fetchAcResults` (line 2607-2612):

```js
// signal_flow_editor.js:2608
function fetchAcResults(q) {
  var fetchUrl = url + '?q=' + encodeURIComponent(q);   // ← UNCONDITIONAL '?'
  getJSON(fetchUrl)
```

`fetchAcResults` unconditionally appends `?q=...`. With the Phase 10 connector circuit-label call (line 2690) this was fine because the URL had no existing query string. But the new Phase 11 port-autocomplete URL already contains `?shape_class=...`, so the final fetched URL is:

```
/audiopatch/.../signal-flow/label-autocomplete/?shape_class=showstack.Console?q=Vox
```

This is a single query component with the literal value `shape_class=showstack.Console?q=Vox`. Django's QueryDict will:
- `request.GET.get('shape_class')` → `"showstack.Console?q=Vox"` (no longer matches any allowlist key)
- `request.GET.get('q')` → `""` (empty)

Two failure modes occur simultaneously:

1. **Shape-scoping silently disabled.** `shape_class` no longer matches `SHAPE_CLASS_SOURCES` (it now contains the trailing `?q=Vox`), so the allowlist filter falls through — the very behaviour GAP-11.1 was supposed to fix re-appears.
2. **Search-term filtering disabled.** With `q=""`, the backend's `if q:` check at `views.py:7984` skips the `__icontains` filter, returning all labels from the project — the user types "Vox" but the dropdown shows the first 8 alphabetical labels in the project, completely unrelated to their input.

The UAT bug GAP-11.1 was supposed to close (Amp Channel suggestions appearing on a Device shape) is therefore still present in production after this fix — and a new bug (search ignored) was introduced on top of it.

**Fix:**
Move the `?`-detection into `fetchAcResults` so it composes the URL correctly regardless of whether the base URL already carries query params. Minimal, low-blast-radius patch:

```js
// signal_flow_editor.js:2607-2612 — replace fetchAcResults:
function fetchAcResults(q) {
  var sep = (url.indexOf('?') === -1) ? '?' : '&';
  var fetchUrl = url + sep + 'q=' + encodeURIComponent(q);
  getJSON(fetchUrl)
    .then(function (data) { renderAcResults(data.results || []); })
    .catch(function () { closeAcListbox(); });
}
```

The Phase 10 connector-label path (no pre-existing `?`) is preserved because `sep` will be `?` exactly as before. The Phase 11 port path now correctly produces `?shape_class=...&q=...`.

**Verification after fix:**
1. Open DevTools Network tab on the editor page.
2. Drop a Device shape, open the inspector, add a port, type one character into the port-label input.
3. Confirm the XHR is `?shape_class=showstack.Device&q=<char>` (one `?`, one `&`).
4. Confirm only Device Input / Device Output results appear — no Amp Channel rows.

## Info

### IN-01: `SHAPE_CLASS_SOURCES` dict re-created on every request

**File:** `planner/views.py:7938-7943`

**Issue:**
The allowlist dict is defined inside the view function body, so it's allocated on every GET request. With debounced autocomplete (200ms) and 8-row caps the perf impact is negligible, but the constant nature of the data (4 hardcoded entries, never mutated) makes module-level placement more idiomatic.

**Fix (low priority, style only):**
Move `SHAPE_CLASS_SOURCES` to module scope above the view, alongside `_signal_flow_logger`:

```python
# planner/views.py — above signal_flow_label_autocomplete:
_SIGNAL_FLOW_SHAPE_CLASS_SOURCES = {
    'showstack.Console':   {'Console Input', 'Console Aux Out'},
    'showstack.Device':    {'Device Input', 'Device Output'},
    'showstack.Amp':       {'Amp Channel'},
    'showstack.Processor': {'P1 Input', 'P1 Output', 'Galaxy Input', 'Galaxy Output'},
}
```

Then reference it inside the view. Not blocking — current placement keeps the allowlist visually next to its consumer, which has its own readability merit.

### IN-02: `cell.get('type') || ''` masks a `null`/`undefined` type case that should never happen

**File:** `planner/static/planner/js/signal_flow_editor.js:2135`

**Issue:**
```js
'shape_class=' + encodeURIComponent(cell.get('type') || '')
```

If `cell.get('type')` ever returned a falsy value, this would send `shape_class=` (empty string). The backend strips and treats empty `shape_class` as "no filter" (line 7975-7976), so behaviour is benign. But every JointJS cell created via `joint.dia.Element.define` carries a non-empty `type` — an empty type would indicate a graph-corruption bug worth surfacing rather than silently masking. The defensive fallback could hide such a bug if it ever appears.

**Fix (defensive style only, optional):**
Drop the fallback or surface a console warning:

```js
var cellType = cell.get('type');
if (!cellType && window.console) console.warn('[sfd] port autocomplete: cell missing type', cell.id);
'shape_class=' + encodeURIComponent(cellType || '')
```

Not blocking — the current code is safe in production.

---

_Reviewed: 2026-05-24T17:05:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
