---
phase: 11-ports-and-resize
plan: "01"
subsystem: signal-flow-diagrammer
tags:
  - phase-11
  - foundation
  - refactor
  - autocomplete
  - requirements
dependency_graph:
  requires:
    - "10-03-SUMMARY.md (Phase 10 autocomplete combobox — source of initAutocomplete)"
  provides:
    - "attachAutocompleteToInput(inputEl, url, onSelect) — reusable combobox factory"
    - "REQUIREMENTS.md PORT-01 amended to 4-edge model"
  affects:
    - "planner/static/planner/js/signal_flow_editor.js (combobox region lines 1784+)"
    - "planner/static/planner/css/signal_flow.css (Section 12 selector update)"
    - ".planning/REQUIREMENTS.md (PORT-01 line 15)"
tech_stack:
  added: []
  patterns:
    - "Factory-function closure pattern: per-attachment widget state fully encapsulated"
    - "Uniquified DOM ids: sfd-label-suggestions-<inputEl.id|anon-N> via _acAttachCounter"
    - "Class-based CSS targeting: .sfd-ac-listbox replaces #sfd-label-suggestions id selector"
key_files:
  created: []
  modified:
    - ".planning/REQUIREMENTS.md"
    - "planner/static/planner/js/signal_flow_editor.js"
    - "planner/static/planner/css/signal_flow.css"
decisions:
  - "D-01 honored: PORT-01 now reads 4 edges (Top/Bottom/Left/Right)"
  - "Per-attachment closure scope chosen over returning a controller object — matches existing file style"
  - "Class .sfd-ac-listbox added to every generated listbox (alongside unique id) so CSS rule is id-independent"
  - "blur onSelect fires unconditionally (not only when value differs from last selection) — simplest correct behavior; callers that need dedup do it themselves"
metrics:
  duration: "3 minutes"
  completed_date: "2026-05-24"
  tasks_completed: 2
  files_modified: 3
---

# Phase 11 Plan 01: Foundation — PORT-01 Amendment + Combobox Refactor Summary

**One-liner:** PORT-01 amended to 4-edge model; `initAutocomplete()` generalized into `attachAutocompleteToInput(inputEl, url, onSelect)` closure factory enabling Plan 11-03's per-port-row autocomplete.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Amend REQUIREMENTS.md PORT-01 per D-01 | c0abf2d | `.planning/REQUIREMENTS.md` |
| 2 | Refactor initAutocomplete → attachAutocompleteToInput | 3e974e8 | `signal_flow_editor.js`, `signal_flow.css` |

## Task 1 Detail — REQUIREMENTS.md PORT-01 Amendment

**Before (line 15):**
```
- [ ] **PORT-01**: User can add a labeled port to any smart shape via the inspector. Ports anchor to one of three edges per shape: **Top** (horizontal-axis line), **Left** (vertical-axis line), **Right** (vertical-axis line). The bottom edge is reserved for the shape label and is not a port edge in v2.3.
```

**After (line 15):**
```
- [ ] **PORT-01**: User can add a labeled port to any smart shape via the inspector. Ports anchor to one of four edges per shape: **Top**, **Bottom**, **Left**, **Right**. The bottom edge is structurally free because all 7 shape classes left-anchor their body label inside the colored band (`refX: 16, refY: '50%'` in `signal_flow_editor.js`), so bottom-edge ports do not collide with the shape's own label.
```

PORT-02..06, SHP-RESIZE-01..03, SHP-10/11, and the Traceability table are unchanged.

## Task 2 Detail — Combobox Factory Refactor

### Function signature change

```javascript
// Before (Phase 10 — tightly coupled to single input)
function initAutocomplete() { ... }
initAutocomplete();

// After (Phase 11 — parameterized factory)
function attachAutocompleteToInput(inputEl, url, onSelect) { ... }
attachAutocompleteToInput(circuitLabelInput, labelAutocompleteUrl, null);
```

### Three required generalizations (per RESEARCH §Q9)

**1. Hardcoded element lookup → parameter**

`circuitLabelInput` (referenced 12× in the old region) is now `inputEl` (the function parameter). The module-scope `var circuitLabelInput = document.getElementById('sfd-circuit-label')` declaration is retained so the BC call site can pass it.

**2. Uniquified listbox id**

```javascript
// Old — one global id, collides on multiple attachments
acListbox.id = 'sfd-label-suggestions';

// New — unique per attachment
var listboxId = 'sfd-label-suggestions-' + (inputEl.id || ('anon-' + (++_acAttachCounter)));
acListbox.id = listboxId;
acListbox.className = 'sfd-ac-listbox';  // CSS hook; id is for ARIA only
```

Module-scope `var _acAttachCounter = 0` added near line 31 (after `labelAutocompleteUrl`).

`aria-controls` and `aria-activedescendant` updated in lockstep with `listboxId`. Row ids changed from `'sfd-ac-row-' + i` to `listboxId + '-row-' + i`.

**3. onSelect callback hook**

```javascript
// On row click/Enter selection (inside selectAcRow):
inputEl.dispatchEvent(new Event('input', { bubbles: true }));  // Phase 9 BC
if (typeof onSelect === 'function') onSelect(chosen);          // Phase 11 hook

// On blur freeform commit:
setTimeout(function () {
  closeAcListbox();
  if (typeof onSelect === 'function') onSelect(inputEl.value);
}, 150);
```

### Per-attachment state moved into closure scope

Variables that were module-scope in Phase 10 (`acListbox`, `acTimer`, `acActiveIndex`) are now declared with `var` inside `attachAutocompleteToInput`'s body. Each attachment owns independent state.

Helper functions (`fetchAcResults`, `renderAcResults`, `selectAcRow`, `updateAcActive`, `closeAcListbox`) are now declared inside the factory closure — they capture `inputEl`, `url`, `onSelect`, `listboxId`, and the local state vars via closure, with no module-scope pollution.

### CSS Section 12 update

`#sfd-label-suggestions` id selector replaced with `.sfd-ac-listbox` class selector. `#sfd-label-suggestions[hidden]` replaced with `.sfd-ac-listbox[hidden]`. No other CSS changes.

### Plan 11-03 call site (future)

```javascript
attachAutocompleteToInput(
  rowInput,
  labelAutocompleteUrl,
  function (label) { renameAuthoredPort(cell, portId, label); }
);
```

## Verification Results

| Check | Result |
|-------|--------|
| `node --check signal_flow_editor.js` | PASS (exit 0) |
| `grep -c "function attachAutocompleteToInput"` | 1 |
| `grep -c "attachAutocompleteToInput(circuitLabelInput"` | 1 |
| `grep -c "sfd-label-suggestions-"` | 3 |
| `grep -c "_acAttachCounter"` | 3 |
| `grep -c "innerHTML"` | 5 (unchanged — XSS contract preserved) |
| `grep -c "if (typeof onSelect === 'function')"` | 2 (selection + blur) |
| `function initAutocomplete` present | 0 (deleted) |
| `python3 manage.py check` | 0 issues |
| Phase 10 LBL UAT regression | Manual smoke-check required (no headless harness) |

## Deviations from Plan

None — plan executed exactly as written. The CSS id→class migration was required per Task 2 step 6 directive ("if there are id-based rules, refactor them to class-based selectors").

## Known Stubs

None — no placeholder data, hardcoded empty arrays, or TODO data-source stubs introduced in this plan.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The `attachAutocompleteToInput` factory uses the same Phase 10 endpoint (`signal_flow_label_autocomplete`) unchanged. XSS contract (T-11-01-01) confirmed preserved: `innerHTML` count unchanged at 5 (all are `= ''` clear operations).

## Self-Check: PASSED

Files exist:
- `.planning/REQUIREMENTS.md` — confirmed (grep returned line 15 with "four edges")
- `planner/static/planner/js/signal_flow_editor.js` — confirmed (node --check passed)
- `planner/static/planner/css/signal_flow.css` — confirmed (.sfd-ac-listbox present)

Commits exist:
- `c0abf2d` — Task 1 (docs: REQUIREMENTS.md amendment)
- `3e974e8` — Task 2 (feat: combobox refactor)
