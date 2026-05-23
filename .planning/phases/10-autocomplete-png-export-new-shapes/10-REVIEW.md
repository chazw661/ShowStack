---
phase: 10-autocomplete-png-export-new-shapes
reviewed: 2026-05-23T18:47:49Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - planner/views.py
  - planner/urls.py
  - planner/tests/test_signal_flow_phase10.py
  - planner/static/planner/js/signal_flow_editor.js
  - planner/static/planner/css/signal_flow.css
  - planner/templates/planner/signal_flow/editor.html
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-05-23T18:47:49Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 10 adds (1) a project-scoped label-autocomplete view + URL, (2) Amp / SystemProcessor entries in the equipment picker, autosave IDOR allowlist, and `_enrich_nodes` allowlist, (3) two new JointJS shape classes + sidebar tiles + CSS, (4) a PNG export button + client-side handler.

The server-side work is solid and well-defended: every new project-scoped query routes through `request.current_project` per CLAUDE.md's session-based project resolution rule, the IDOR allowlist is correctly extended with an explicit model-name string match (not `hasattr`), `_enrich_nodes` mirrors the same allowlist, blank/null label fields are filtered server-side, the picker correctly targets SystemProcessor (not P1Processor / GalaxyProcessor child models), and a `select_related('amp_model')` was added to prevent N+1 in the amp picker. No CSRF concerns — the only new HTTP-exposed endpoint is GET-only and decorated with `@require_GET`. No XSS in the autocomplete renderer — values are written via `textContent`. The multi-line template comment in `editor.html` correctly uses `{% comment %}…{% endcomment %}` (not `{# … #}`).

Two real bugs were found in the new JavaScript: the synthetic `input` event dispatched after a user selects an autocomplete row will re-trigger the same input listener that scheduled the fetch, causing the dropdown to silently re-open ~200ms after selection (WR-01). And the debounce timer `acTimer` is never cleared on blur, so a pending fetch can re-render the listbox after `closeAcListbox` has closed it (WR-02). Both are localised to the new autocomplete combobox; neither affects autosave correctness, IDOR enforcement, or persisted canvas state.

Four lower-severity items: `var circuitLabelInput` is re-declared (function-scope shadow), the `{% comment %}` block is positioned mid-attribute-list which is functional but unusual, a pre-existing `Device, Device` double-import was touched in the diff without being cleaned up, and the PNG export captures a fixed 4000×3000 canvas at pixelRatio 2 which produces a very large file regardless of actual diagram size.

## Warnings

### WR-01: Synthetic `input` event re-opens autocomplete dropdown after selection

**File:** `planner/static/planner/js/signal_flow_editor.js:1822-1827,1908-1915`
**Issue:** `selectAcRow` dispatches a synthetic `input` event on `circuitLabelInput` (line 1914) to notify the existing Phase 9 autosave listener (D-14). However, the Phase 10 autocomplete `input` listener (line 1822) is *also* attached to the same element, so the synthetic event re-triggers the autocomplete debounce: with `q = chosen` (the just-selected label) and `q.length >= 1`, `setTimeout(fetchAcResults, 200)` is scheduled. ~200ms after the user clicks or presses Enter on a row, the dropdown silently re-opens with the same (or fuzzy-matching) results. Functional bug — the dropdown is supposed to stay closed after selection.

**Fix:** Add a "skip-next-input" flag set inside `selectAcRow` and checked by the input listener:
```js
var acSuppressNextInput = false;

circuitLabelInput.addEventListener('input', function () {
  if (acSuppressNextInput) { acSuppressNextInput = false; return; }
  var q = circuitLabelInput.value.trim();
  if (acTimer) clearTimeout(acTimer);
  if (q.length < 1) { closeAcListbox(); return; }
  acTimer = setTimeout(function () { fetchAcResults(q); }, 200);
});

function selectAcRow(rowEl, label) {
  var chosen = label || (rowEl.querySelector('span') && rowEl.querySelector('span').textContent) || '';
  circuitLabelInput.value = chosen;
  closeAcListbox();
  acSuppressNextInput = true;   // suppress the Phase 10 listener
  circuitLabelInput.dispatchEvent(new Event('input', { bubbles: true }));
}
```
The Phase 9 listener (line 1414) still fires and schedules autosave, which is the intended D-14 behaviour.

### WR-02: Pending autocomplete fetch can re-open dropdown after blur

**File:** `planner/static/planner/js/signal_flow_editor.js:1822-1827,1854-1856`
**Issue:** The blur handler (line 1854) calls `setTimeout(closeAcListbox, 150)` but does not clear `acTimer`. If the user types and immediately tabs/clicks away within the 200ms debounce window:
1. t=0: input fires, `acTimer` is scheduled for t=200ms
2. t=50: blur fires, `closeAcListbox` is scheduled for t=200ms
3. t=200: `closeAcListbox` runs (hides listbox), then `fetchAcResults` runs
4. Network resolves at t=~300: `renderAcResults` re-shows the listbox even though the input is no longer focused

**Fix:** Clear `acTimer` in both the blur handler and `closeAcListbox`:
```js
circuitLabelInput.addEventListener('blur', function () {
  if (acTimer) { clearTimeout(acTimer); acTimer = null; }
  setTimeout(closeAcListbox, 150);
});

function closeAcListbox() {
  if (acTimer) { clearTimeout(acTimer); acTimer = null; }
  if (!acListbox) return;
  acListbox.setAttribute('hidden', '');
  // … rest unchanged
}
```

## Info

### IN-01: `var circuitLabelInput` re-declared in the same function scope

**File:** `planner/static/planner/js/signal_flow_editor.js:1328,1784`
**Issue:** `circuitLabelInput` is declared with `var` at line 1328 (Phase 9 inspector) and again with `var` at line 1784 (Phase 10 autocomplete). Both declarations are within the same IIFE function scope, so they refer to the same binding. This is legal JS and harmless at runtime, but it is a code smell: a reader of the Phase 10 block could assume the variable is locally scoped. Future refactoring (e.g. wrapping each block in `{ … }` with `let`) would silently change behavior.

**Fix:** Remove the second `var` and just reuse the existing binding:
```js
// Phase 10 — reuses circuitLabelInput declared at line 1328
// (do not re-declare with `var`)
```

### IN-02: `{% comment %}` block placed mid-attribute-list

**File:** `planner/templates/planner/signal_flow/editor.html:30-37`
**Issue:** The `{% comment %}` block sits between the `data-export-png-url` and `data-label-autocomplete-url` attributes inside an opening `<div>` tag. This is functionally fine (Django strips the block to whitespace, which is valid between HTML attributes), but it is unusual and makes the source harder to scan. CLAUDE.md memory note explicitly warns that `{# … #}` is single-line only — this code correctly uses `{% comment %}` so the rule is honoured, just placed awkwardly.

**Fix:** Move the comment to just before the opening `<div>`:
```html
{% comment %}
  Plan-checker finding (2026-05-22): the URL name signal_flow_label_autocomplete
  is registered in urls.py by plan 10-01 (parallel wave 1)…
{% endcomment %}
<div id="sfd-container"
     data-diagram-id="{{ diagram.id }}"
     …
     data-label-autocomplete-url="{% url 'planner:signal_flow_label_autocomplete' %}">
```

### IN-03: Pre-existing `Device, Device` duplicate import touched by phase 10 diff, not cleaned up

**File:** `planner/views.py:66`
**Issue:** Line 66 reads `Device, Device, DeviceInput, DeviceOutput,` — `Device` appears twice. Pre-existing from commit `06f842a` (pre-phase 10), but phase 10 edited the same line to add `DeviceInput, DeviceOutput` without removing the duplicate. Python tolerates duplicate imports silently, so this is purely cosmetic.

**Fix:** Drop one of the `Device,`:
```python
Device, DeviceInput, DeviceOutput,
```

### IN-04: PNG export always captures the full 4000×3000 paper at pixelRatio 2

**File:** `planner/static/planner/js/signal_flow_editor.js:1968-1973`
**Issue:** `htmlToImage.toPng(paperEl, { pixelRatio: 2, width: paper.options.width, height: paper.options.height })` always passes the JointJS paper's full canvas dimensions (4000×3000 from the construction at line 282-283). At pixelRatio 2 this is an 8000×6000 PNG — even when the user's diagram only occupies 800×600 of the canvas. The output file is therefore large (tens of MB), slow to generate, and visually mostly empty whitespace. Not a correctness bug; the export is functional and the comment block (line 1941, "captures full paperEl including orphan ghosts") indicates the full-canvas capture is intentional for D-08. Worth flagging because it may surface as a beta-tester complaint.

**Fix:** Compute the bounding box of all graph cells and crop:
```js
var bbox = graph.getBBox();
if (bbox) {
  var pad = 40;
  htmlToImage.toPng(paperEl, {
    pixelRatio: 2,
    backgroundColor: '#ffffff',
    width: bbox.width + 2 * pad,
    height: bbox.height + 2 * pad,
    style: {
      transform: 'translate(' + (-bbox.x + pad) + 'px, ' + (-bbox.y + pad) + 'px)',
      'transform-origin': '0 0',
    },
  }).then(…);
}
```
Or accept current behavior and defer to v2.4. Recommend filing a follow-up rather than blocking the phase.

---

## Notes on items NOT flagged

- **CSRF on POST endpoints:** No new POST endpoints. `signal_flow_label_autocomplete` is GET-only with `@require_GET`. ✓
- **IDOR allowlist:** Amp / SystemProcessor correctly added to both `_enrich_nodes` (views.py:7574) and `signal_flow_autosave` (views.py:7709) using the explicit-string-match pattern; cross-project IDOR tests pass in `test_signal_flow_phase10.py:370-385` and `:535-556`. ✓
- **`request.current_project` usage:** All new view code reads via `getattr(request, 'current_project', None)` and 400s when absent. No URL-based project routing introduced. ✓
- **XSS in autocomplete renderer:** `renderAcResults` (line 1867) uses `textContent` exclusively for both label and source spans. No `innerHTML` of server-supplied data. ✓
- **Silent JS parse errors / handlers killed:** No silent `try/catch` wrapping anything in the new code. `getJSON(...).catch(closeAcListbox)` is a deliberate error recovery, not a silent swallow. ✓
- **DOMContentLoaded timing:** `signal_flow_editor.js` is loaded with `defer` (editor.html:160), so DOM is fully parsed when the IIFE evaluates. The plan-checker note at line 1793-1798 documents the assumption. ✓
- **Multi-line Django `{# … #}` comments:** None present in the new template diff — only `{% comment %}` blocks. ✓
- **`SystemProcessor` exclusion from label-autocomplete sources:** Intentional and documented (D-05, views.py:7915-7920). `SystemProcessor.name` is a device identifier, not a signal name. ✓
- **Picker targets `SystemProcessor`, not `P1Processor` / `GalaxyProcessor`:** Verified at views.py:7828 and test:521-523. ✓
- **N+1 in amp picker:** `qs = qs.select_related('amp_model')` at views.py:7856 prevents N+1 on `str(a.amp_model)`. ✓
- **URL ordering:** `signal-flow/label-autocomplete/` is registered before `signal-flow/<int:diagram_id>/` (urls.py:341 vs :342) per the codebase convention. ✓
- **`signal_flow_export_png` URL still wired:** Template still emits `data-export-png-url` (editor.html:29) and JS no longer reads it. URL reverse will resolve because the stub view + URL pattern remain (views.py:7984, urls.py:347). ✓

---

_Reviewed: 2026-05-23T18:47:49Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
