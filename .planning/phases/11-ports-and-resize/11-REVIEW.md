---
phase: 11-ports-and-resize
reviewed: 2026-05-24T13:30:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - planner/static/planner/js/signal_flow_editor.js
  - planner/static/planner/css/signal_flow.css
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-05-24T13:30:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Phase 11 introduces 4-edge engineer-authored port authoring, a `CornerResize` tool, and an auto-expansion path. The implementation follows the locked design pillars carefully — back-compat conversion is atomic, every mutator schedules autosave explicitly, the `change:ports` listener pitfall (RESEARCH §Q7) is correctly avoided, ports survive trash-removal via `reanchorLinksFromPort` → `removePort` ordering (PORT-05), and all 3 direct `cell.removePort` / `cell.addPort` calls are bracketed by `reanchorLinksFromPort` or `convertCellFromGenericToAuthored` as required. Five XSS-sensitive surfaces were verified safe: all `innerHTML` writes are `= ''` clears (4 assignments total — prompt expected 5; the 5th is a comment on line 924), engineer-authored labels round-trip via `textContent` / `.value` / SVG `<text>` only, and all admin-DOM `.style` writes use `setProperty(.., 'important')` per CLAUDE.md mandate (grep for `\.style\.[a-zA-Z]+\s*=` returns zero hits).

Three Warning-level findings:

1. **WR-01 (signal_flow.css §15) — `nwse-resize` cursor leaks onto every JointJS tool.** The selector `#sfd-paper .joint-tools .joint-tool { cursor: nwse-resize !important; }` matches link tools (Vertices, Segments, SourceAnchor, TargetAnchor, Remove) added in `paper.on('link:pointerclick', …)`, not just CornerResize handles. When a link is selected, hovering its vertex / anchor / remove handles will incorrectly show the resize cursor.
2. **WR-02 (signal_flow_editor.js refreshPortAuthorBlock) — autocomplete listboxes accumulate in `portAuthorBlock`.** Each `attachAutocompleteToInput` call appends a fresh `<ul.sfd-ac-listbox>` to `inputEl.closest('.sfd-field')`, which resolves to `portAuthorBlock` for port-row inputs. `refreshPortAuthorBlock` only clears the `<li>` rows under each `<ul.sfd-port-list>` — the listboxes at the parent level survive. After N add/rename/remove cycles you get N×4 stale listboxes, and because port IDs are stable, listbox IDs collide (invalid HTML — duplicate IDs).
3. **WR-03 (CornerResize.setPosition snap path) — opposite-corner drift when snap-on dragging from TL/TR/BL.** For non-`br` corners, `newX`/`newY` is computed from `p + (s.size − newDim)`, then `newW`/`newH` and `newX`/`newY` are independently snapped to 20px. The relationship that pins the *opposite* corner can desync by up to 19px after independent rounding, so the BR corner visibly moves when the user is dragging TL (mirror for the other corners).

Three Info-level findings cover a code-style smell (duplicate `var circuitLabelInput` declaration — pre-existing, not Phase 11), a hardcoded body-label font size of 13 in `computeMinSize` that's 12 for `CommBeltPack` (minor measurement inaccuracy), and an unbounded `_textMeasureCache` (no LRU cap; safe in practice but worth noting).

## Warnings

### WR-01: Section 15 cursor rule applies to all JointJS tools, not just resize handles

**File:** `planner/static/planner/css/signal_flow.css:858-861`
**Issue:** The cursor rule

```css
#sfd-paper .joint-tools .joint-tool {
  cursor: nwse-resize !important;
}
```

is scoped to `.joint-tool` inside any `.joint-tools` host, which is the JointJS root class for ALL tool-views (link tools too — Vertices / Segments / SourceAnchor / TargetAnchor / Remove are registered at line 1678-1690 of `signal_flow_editor.js`). When a connector is selected, hovering any of its tool handles will show the diagonal resize cursor instead of the move / pointer / x cursor that `joint.linkTools` normally renders.
**Fix:** Scope the cursor rule to the CornerResize handles only — match `[selector="handle"]` (or the JointJS-serialized variant) the same way the fill / stroke rules in Section 15 do:

```css
/* Cursor — nwse for the 4 corner resize handles only */
#sfd-paper .joint-tools .joint-tool [selector="handle"],
#sfd-paper g.joint-tool rect[joint-selector="handle"] {
  cursor: nwse-resize !important;
}
```

Alternatively, name the tool group and select on it: `attachResizeTools` already passes `name: 'sfd-resize'` to `joint.dia.ToolsView`, so `g[data-tools-name="sfd-resize"] .joint-tool { cursor: nwse-resize !important; }` is an even tighter scope.

### WR-02: Autocomplete listboxes accumulate in `portAuthorBlock` across refreshes

**File:** `planner/static/planner/js/signal_flow_editor.js:2519` (in `attachAutocompleteToInput`) and `:2096-2158` (in `refreshPortAuthorBlock`)
**Issue:** `attachAutocompleteToInput` resolves `var fieldDiv = inputEl.closest('.sfd-field')` and appends the new listbox there:

```js
fieldDiv.appendChild(acListbox);   // line 2519
```

For port-label inputs the `.sfd-field` ancestor is `portAuthorBlock` itself (the entire port-authoring block carries `class="sfd-field sfd-field--port-author"` — see line 2034). `refreshPortAuthorBlock` only clears the row `<li>` children under each `<ul class="sfd-port-list">` (line 2102), so the listboxes appended to `portAuthorBlock` in prior calls are never removed. Because port IDs are stable, the listbox ID `sfd-label-suggestions-sfd-port-label-<port.id>` recurs on every refresh — multiple `<ul>` siblings end up sharing the same `id`. Symptoms: monotonic DOM growth in the inspector panel as the engineer adds/removes/renames ports, plus invalid HTML (duplicate `id`s). Functionally, autocomplete still works because the live closure references the freshest `acListbox`, but `document.getElementById(listboxId)` would now return an old, orphaned one.
**Fix:** Remove prior listboxes inside `refreshPortAuthorBlock` before re-attaching. Two options:

Option A — purge by class at the top of `refreshPortAuthorBlock`:
```js
function refreshPortAuthorBlock(cell) {
  if (!portAuthorBlock || !cell) return;
  // Drop stale listboxes from prior refreshes (WR-02 fix).
  Array.from(portAuthorBlock.querySelectorAll('.sfd-ac-listbox')).forEach(function (lb) {
    lb.remove();
  });
  // … existing per-edge loop unchanged …
}
```

Option B — append the listbox INSIDE the row `<li>` instead of the field div. In `attachAutocompleteToInput`, swap `inputEl.closest('.sfd-field')` for `inputEl.closest('.sfd-port-row') || inputEl.closest('.sfd-field')` (preserves Phase 10 BC for the circuit-label field) and ensure the row's CSS gives the `<li>` `position: relative` so the listbox's `position: absolute` anchors correctly. This naturally garbage-collects the listbox with the row.

### WR-03: Snap-to-grid in CornerResize.setPosition drifts the opposite corner

**File:** `planner/static/planner/js/signal_flow_editor.js:533-572`
**Issue:** For TL / TR / BL corner drags the new origin is computed as `newX = p.x + (s.width - newW)` (and analog for Y), which pins the OPPOSITE corner. When `snapEnabled`, `newW` and `newX` are then independently rounded to the 20px grid:

```js
newW = Math.round(newW / 20) * 20;
newX = Math.round(newX / 20) * 20;
```

Because each is rounded in isolation, the invariant `newX + newW === p.x + s.width` no longer holds — drift up to ~19px appears on the corner the engineer is NOT dragging. Concrete case: `p.x = 103`, `s.width = 205`, user moves TL by `coordinates.x = 37` → `newW = 168`, `newX = 140`; after snap `newW = 160`, `newX = 140`; original BR was at `308`, new BR is at `300` — a visible 8px shift of an anchor that should be stationary. The min-size re-clamp at line 566-567 (`newW = Math.max(newW, minSize.width)`) compounds the drift when the snap rounds W below the floor.
**Fix:** After snapping `newW` / `newH` (and applying the min-size clamp), recompute the origin from the pinned opposite corner instead of snapping `newX` / `newY` independently:

```js
if (window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled) {
  newW = Math.round(newW / 20) * 20;
  newH = Math.round(newH / 20) * 20;
  newW = Math.max(newW, minSize.width);
  newH = Math.max(newH, minSize.height);
  // Re-anchor the stationary corner instead of snapping newX/newY independently.
  if (c === 'tl' || c === 'bl') newX = (p.x + s.width)  - newW;
  if (c === 'tl' || c === 'tr') newY = (p.y + s.height) - newH;
}
```

This keeps the opposite corner perfectly pinned across the full snap path.

## Info

### IN-01: Duplicate `var circuitLabelInput` declaration in the IIFE

**File:** `planner/static/planner/js/signal_flow_editor.js:1800` and `:2469`
**Issue:** `circuitLabelInput` is declared with `var` twice in the same IIFE scope. Both `getElementById` lookups happen at runtime (the second silently overwrites the first), and because `var` is hoisted, both `var` keywords refer to the same binding. No functional bug — the assigned value is identical — but it's a clear code smell that hides the read-before-write at line 2652 when the file is read top-to-bottom. Pre-existing (introduced in Phase 10 `5fc873b`); not a Phase 11 regression but worth cleaning up while the surrounding code is being touched.
**Fix:** Delete the second `var` keyword at line 2469 (or remove the line entirely and reuse the existing binding from line 1800). The Phase 11 call at line 2652 already sees the populated reference.

### IN-02: `computeMinSize` hardcodes body-label font-size 13, mismatch for `CommBeltPack`

**File:** `planner/static/planner/js/signal_flow_editor.js:472-473`
**Issue:**

```js
var bodyLabelText = (cell.attr('label/text') || '');
var bodyLabelReserveW = measureLabelWidth(bodyLabelText, 13) + 20;
```

The shape factories use `fontSize: 13` for Console / Device / SpeakerArray / Generic / Processor / Amp, but `CommBeltPack` is `fontSize: 12` (line 672). The min-size math therefore over-reserves a few pixels for the beltpack body label. Cosmetic only — over-reserve never under-clamps, so safe — but the magic 13 should be read from the cell attrs to stay in sync if a future shape uses a different size.
**Fix:** Read the font size from the cell's own attrs with a fallback:

```js
var bodyLabelFontSize = Number(cell.attr('label/fontSize')) || 13;
var bodyLabelReserveW = measureLabelWidth(bodyLabelText, bodyLabelFontSize) + 20;
```

### IN-03: `_textMeasureCache` has no eviction policy

**File:** `planner/static/planner/js/signal_flow_editor.js:439-450`
**Issue:** `measureLabelWidth` memoizes every `(fontSize, text)` pair into the module-scope object `_textMeasureCache`. Realistic port labels are short and few (engineers reuse names), so this is unlikely to grow large — but it's an unbounded cache that lives for the page lifetime. If a paste-bomb scenario ever inserted thousands of unique long labels via the autocomplete onSelect path, memory would grow without bound.
**Fix:** Either drop the cache (Canvas-2D `measureText` is fast for short strings) or add a simple size cap (e.g. evict to half when `Object.keys(_textMeasureCache).length > 512`). Lowest risk: leave as-is and revisit if a profiler ever flags it.

---

_Reviewed: 2026-05-24T13:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
