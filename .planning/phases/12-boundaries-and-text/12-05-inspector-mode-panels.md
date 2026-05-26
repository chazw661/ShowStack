---
phase: 12
plan_number: 05
wave: 4
depends_on: [01, 02, 03, 04]
files_modified:
  - planner/static/planner/js/signal_flow_editor.js
autonomous: true
requirements_addressed: [DRAW-02, DRAW-03, TXT-02]
must_haves:
  truths:
    - "setInspectorMode('boundary', cell) shows a boundary-mode panel and hides connector / node / portAuthor panels"
    - "setInspectorMode('text', cell) shows a text-mode panel and hides connector / node / portAuthor / boundary panels"
    - "Boundary panel: 4×2 color swatch grid (8 hexes from BOUNDARY_PALETTE) + 4-button line-style segmented picker (solid / dashed / dotted / double) with inline SVG previews"
    - "Text panel: 3×3 color swatch grid (9 hexes from TEXT_PALETTE — 8 + white) + 3-button font-size segmented (S 12 / M 16 / L 24)"
    - "Boundary swatch click mutates lastBoundaryColor FIRST, then cell.prop('color'), then applyBoundaryRender, then scheduleAutosave (Pattern Violation 1 order)"
    - "Boundary line-style click mutates lastBoundaryStyle FIRST, then cell.prop('lineStyle'), then applyBoundaryRender, then scheduleAutosave"
    - "Text swatch click mutates lastTextColor FIRST, then cell.prop('color') + cell.attr('label/fill'), then scheduleAutosave"
    - "Text font-size click mutates lastTextSize FIRST, then cell.prop('fontSize') + cell.attr('label/fontSize'), then scheduleAutosave"
    - "refreshBoundaryModeBlock(cell) syncs data-active='true' on the swatch matching cell.prop('color') and on the segmented button matching cell.prop('lineStyle')"
    - "refreshTextModeBlock(cell) syncs data-active='true' on the swatch matching cell.prop('color') and on the segmented button matching cell.prop('fontSize')"
  artifacts:
    - path: "planner/static/planner/js/signal_flow_editor.js"
      provides: "buildBoundaryModeBlock + refreshBoundaryModeBlock + buildTextModeBlock + refreshTextModeBlock + applyBoundaryColor + applyBoundaryLineStyle + applyTextColor + applyTextFontSize + renderLineStylePreviewSVG helper + two new branches in setInspectorMode for 'boundary' and 'text'"
      contains: "function buildBoundaryModeBlock"
      contains_also: "function buildTextModeBlock"
  key_links:
    - from: "boundary swatch button click"
      to: "applyBoundaryColor(cell, hex) -> cell.prop('color') + applyBoundaryRender + scheduleAutosave"
      via: "addEventListener('click', ...)"
      pattern: "applyBoundaryColor"
    - from: "text font-size segmented click"
      to: "applyTextFontSize(cell, size) -> cell.prop('fontSize') + cell.attr('label/fontSize') + scheduleAutosave"
      via: "addEventListener('click', ...)"
      pattern: "applyTextFontSize"
---

<objective>
Build the right-side inspector panels for selected BoundaryLine cells (color + line-style) and selected TextLabel cells (font-size + color including white). Add `'boundary'` and `'text'` branches to the existing `setInspectorMode(...)` switch at signal_flow_editor.js:2199 — both branches hide all other mode blocks (connector / node / portAuthor) via `style.setProperty('display','none','important')` before showing the new block. Lazy-build pattern mirrors Phase 9's `buildNodeModeBlock`. Selection wiring (calling `setInspectorMode('boundary' | 'text', cell)` on selection change) lives in Plan 06.
</objective>

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| Sticky-default mutation timing (Pattern Violation 1) | high (silent UX bug — next-drawn boundary inherits prior color) | Acceptance criterion: every swatch / segmented click handler mutates the closure-scoped `lastBoundaryColor` / `lastBoundaryStyle` / `lastTextSize` / `lastTextColor` BEFORE `cell.prop(...)`, BEFORE `applyBoundaryRender(...)`, BEFORE `scheduleAutosave()`. Verified by reading handler bodies and checking the literal line order. |
| `!important` missing on inspector DOM style writes (Violation 3) | medium | Every `style.setProperty` in `buildBoundaryModeBlock` / `buildTextModeBlock` / `refresh*` / `setInspectorMode` extension uses the 3-arg form with `'important'`. Acceptance criterion: zero `el.style.display = ` shorthand assignments in the new code. |
| Dark-navy palette regression (Violation 4) | medium | Plan 02 declares Section 17/18 CSS with `#aaa` muted labels and `#eee` text. Plan 05 attaches the classes; no inline `color:` overrides from JS. Verified by reading the lazy-build helpers — they set `className` only, never inline `color`. |
| `renderLineStylePreviewSVG(s)` uses innerHTML — XSS surface? | low | The function returns a FIXED literal SVG string (no user input interpolated). Document the safe-by-construction exception inline. Acceptance criterion: `renderLineStylePreviewSVG` body contains zero string concatenation with user-input variables. |
| Mode-switch leaks state across cells | medium | Both new `setInspectorMode` branches set `inspectorCurrentBoundary` / `inspectorCurrentText` to the new cell AND null out the other-mode trackers (`inspectorCurrentNode`, `inspectorCurrentLink`). |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Add inspector-current trackers + buildBoundaryModeBlock + refreshBoundaryModeBlock + applyBoundaryColor + applyBoundaryLineStyle + renderLineStylePreviewSVG</name>
  <files>planner/static/planner/js/signal_flow_editor.js</files>
  <read_first>
    - planner/static/planner/js/signal_flow_editor.js lines 1975-2060 (Phase 9 buildNodeModeBlock — the lazy-build template to clone)
    - planner/static/planner/js/signal_flow_editor.js lines 2195-2240 (the setInspectorMode switch — the insertion site for the new branches)
    - planner/static/planner/js/signal_flow_editor.js lines 2255-2275 (closure-state block with inspectorCurrentNode / inspectorCurrentLink — the site for new trackers)
    - planner/static/planner/js/signal_flow_editor.js (find the Plan 01 BOUNDARY_PALETTE constant and applyBoundaryRender helper — these are referenced)
    - planner/static/planner/js/signal_flow_editor.js (find the Plan 03 lastBoundaryColor / lastBoundaryStyle vars — these MUST be mutated BEFORE scheduleAutosave per Violation 1)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-08 (lines 670-755 — verbatim buildBoundaryModeBlock + setInspectorMode extension)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md "Region D" (lines 196-267 — change directive)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md Violation 1 (lines 662-674 — sticky-default mutation order)
    - .planning/phases/12-boundaries-and-text/12-CONTEXT.md D-09, D-10, D-11, D-12 (8-color palette, inspector-only edits, double-line semantics, segmented preview)
    - CLAUDE.md "Overriding Django admin CSS from JavaScript" — every inline style.setProperty uses 'important'.
  </read_first>
  <action>
    Two additive edits to `planner/static/planner/js/signal_flow_editor.js`.

    **EDIT 1 — Add inspector-current trackers.** Locate the closure-state block containing `var inspectorCurrentNode = ...` and `var inspectorCurrentLink = ...` (typically clustered with Phase 9 inspector state). Add immediately after those lines:

    ```javascript
        // Phase 12 — inspector mode-current trackers (parallel to inspectorCurrentNode / inspectorCurrentLink).
        var inspectorCurrentBoundary = null;
        var inspectorCurrentText = null;

        // Lazy-built mode blocks (built on first show, cached after).
        var boundaryModeBlock = null;
        var textModeBlock = null;
    ```

    **EDIT 2 — Add boundary mode panel helpers + the boundary branch in setInspectorMode.** Locate the existing `buildNodeModeBlock()` function definition (signal_flow_editor.js:~1980). Add AFTER its closing brace the following block. The block defines: `renderLineStylePreviewSVG`, `applyBoundaryColor`, `applyBoundaryLineStyle`, `buildBoundaryModeBlock`, `refreshBoundaryModeBlock`.

    ```javascript
      // ──────────────────────────────────────────────────────────────
      // Phase 12 — Boundary-mode inspector panel (DRAW-02, DRAW-03).
      // ──────────────────────────────────────────────────────────────

      // Safe-by-construction: returns a fixed-literal SVG snippet for the segmented
      // button content. No user input is interpolated; innerHTML use is acceptable.
      function renderLineStylePreviewSVG(style) {
        var dashAttr = '';
        if (style === 'dashed') dashAttr = ' stroke-dasharray="6 4"';
        else if (style === 'dotted') dashAttr = ' stroke-dasharray="1 3"';
        // 'solid' and 'double' both render as a plain stroke in the preview
        // (the double-stroke offset is too narrow to read at 28×12; the icon
        // is just two parallel solid strokes for 'double').
        if (style === 'double') {
          return '<svg viewBox="0 0 28 12" aria-hidden="true">' +
                 '<line x1="2" y1="4" x2="26" y2="4" stroke="currentColor" stroke-width="2"/>' +
                 '<line x1="2" y1="9" x2="26" y2="9" stroke="currentColor" stroke-width="2"/>' +
                 '</svg>';
        }
        return '<svg viewBox="0 0 28 12" aria-hidden="true">' +
               '<line x1="2" y1="6" x2="26" y2="6" stroke="currentColor" stroke-width="2"' + dashAttr + '/>' +
               '</svg>';
      }

      // Violation 1 — mutation order: sticky default FIRST, then cell, then render, then autosave.
      function applyBoundaryColor(cell, hex) {
        if (!cell) return;
        lastBoundaryColor = hex;              // 1. sticky default
        cell.prop('color', hex);              // 2. cell mutation
        applyBoundaryRender(cell);            // 3. SVG render
        refreshBoundaryModeBlock(cell);       // 4. inspector active-state visual
        scheduleAutosave();                   // 5. autosave LAST
      }

      function applyBoundaryLineStyle(cell, style) {
        if (!cell) return;
        lastBoundaryStyle = style;
        cell.prop('lineStyle', style);
        applyBoundaryRender(cell);
        refreshBoundaryModeBlock(cell);
        scheduleAutosave();
      }

      function buildBoundaryModeBlock() {
        if (!inspectorEl) return;
        boundaryModeBlock = document.createElement('div');
        boundaryModeBlock.setAttribute('data-mode', 'boundary');
        boundaryModeBlock.style.setProperty('display', 'none', 'important');

        // --- Color swatches: 4×2 grid (D-09 8 colors) ---
        var colorField = document.createElement('div');
        colorField.className = 'sfd-field';
        colorField.setAttribute('data-mode', 'boundary');
        var colorLabel = document.createElement('label');
        colorLabel.textContent = 'Color';                       // XSS-safe textContent
        colorField.appendChild(colorLabel);
        var swatchGrid = document.createElement('div');
        swatchGrid.className = 'sfd-color-swatches';
        BOUNDARY_PALETTE.forEach(function (hex) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'sfd-color-swatch';
          btn.setAttribute('data-color', hex);
          btn.setAttribute('aria-label', 'Color ' + hex);
          btn.style.setProperty('background-color', hex, 'important');
          btn.addEventListener('click', function () {
            applyBoundaryColor(inspectorCurrentBoundary, hex);
          });
          swatchGrid.appendChild(btn);
        });
        colorField.appendChild(swatchGrid);

        // --- Line-style segmented: solid / dashed / dotted / double (D-11, D-12) ---
        var styleField = document.createElement('div');
        styleField.className = 'sfd-field';
        styleField.setAttribute('data-mode', 'boundary');
        var styleLabel = document.createElement('label');
        styleLabel.textContent = 'Line style';
        styleField.appendChild(styleLabel);
        var styleSeg = document.createElement('div');
        styleSeg.className = 'sfd-segmented';
        styleSeg.setAttribute('role', 'group');
        styleSeg.setAttribute('aria-label', 'Boundary line style');
        ['solid', 'dashed', 'dotted', 'double'].forEach(function (s) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.setAttribute('data-style', s);
          btn.setAttribute('aria-label', 'Line style ' + s);
          // Fixed-literal SVG content — safe-by-construction (no user input).
          btn.innerHTML = renderLineStylePreviewSVG(s);
          btn.addEventListener('click', function () {
            applyBoundaryLineStyle(inspectorCurrentBoundary, s);
          });
          styleSeg.appendChild(btn);
        });
        styleField.appendChild(styleSeg);

        boundaryModeBlock.appendChild(colorField);
        boundaryModeBlock.appendChild(styleField);
        inspectorEl.appendChild(boundaryModeBlock);
      }

      function refreshBoundaryModeBlock(cell) {
        if (!boundaryModeBlock || !cell) return;
        var color = cell.prop('color') || '#000000';
        var style = cell.prop('lineStyle') || 'solid';
        // Sync color swatch active state.
        var swatches = boundaryModeBlock.querySelectorAll('.sfd-color-swatch');
        for (var i = 0; i < swatches.length; i++) {
          var s = swatches[i];
          if (s.getAttribute('data-color') === color) {
            s.setAttribute('data-active', 'true');
          } else {
            s.removeAttribute('data-active');
          }
        }
        // Sync line-style segmented active state.
        var styleBtns = boundaryModeBlock.querySelectorAll('.sfd-segmented button[data-style]');
        for (var j = 0; j < styleBtns.length; j++) {
          var b = styleBtns[j];
          if (b.getAttribute('data-style') === style) {
            b.setAttribute('data-active', 'true');
          } else {
            b.removeAttribute('data-active');
          }
        }
      }
    ```

    Note on `inspectorEl`: the Phase 9 inspector code uses a closure-scoped `inspectorEl` reference (the `#sfd-inspector` element). Confirm by grepping `var inspectorEl` — if the variable name is different, adjust the references. The buildNodeModeBlock function's null-guard pattern (`if (!inspectorEl) return;`) confirms the convention.
  </action>
  <verify>
    <automated>grep -n "var inspectorCurrentBoundary = null" planner/static/planner/js/signal_flow_editor.js && grep -n "var inspectorCurrentText = null" planner/static/planner/js/signal_flow_editor.js && grep -n "var boundaryModeBlock = null" planner/static/planner/js/signal_flow_editor.js && grep -n "function buildBoundaryModeBlock" planner/static/planner/js/signal_flow_editor.js && grep -n "function refreshBoundaryModeBlock" planner/static/planner/js/signal_flow_editor.js && grep -n "function applyBoundaryColor" planner/static/planner/js/signal_flow_editor.js && grep -n "function applyBoundaryLineStyle" planner/static/planner/js/signal_flow_editor.js && grep -n "function renderLineStylePreviewSVG" planner/static/planner/js/signal_flow_editor.js</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "var inspectorCurrentBoundary = null" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var inspectorCurrentText = null" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var boundaryModeBlock = null" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var textModeBlock = null" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function buildBoundaryModeBlock" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function refreshBoundaryModeBlock" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function applyBoundaryColor" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function applyBoundaryLineStyle" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function renderLineStylePreviewSVG" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - **Mutation order (Violation 1) — applyBoundaryColor body:** the literal line order is `lastBoundaryColor = hex;` THEN `cell.prop('color', hex);` THEN `applyBoundaryRender(cell);` THEN `scheduleAutosave();` — verified by reading the function body and confirming the source-line order matches the action's code block.
    - **Mutation order (Violation 1) — applyBoundaryLineStyle body:** the literal line order is `lastBoundaryStyle = style;` THEN `cell.prop('lineStyle', style);` THEN `applyBoundaryRender(cell);` THEN `scheduleAutosave();`.
    - `buildBoundaryModeBlock` opens with `if (!inspectorEl) return;` (null guard per Phase 9 pattern).
    - `buildBoundaryModeBlock` creates 8 swatch buttons (one per BOUNDARY_PALETTE entry) — verified by reading the `BOUNDARY_PALETTE.forEach` loop.
    - `buildBoundaryModeBlock` creates 4 segmented buttons (one per style) — verified by reading the `['solid', 'dashed', 'dotted', 'double'].forEach` loop.
    - Every `style.setProperty` call in the new code uses the 3-arg form with `'important'` — verified by `grep -c "\\.style\\.setProperty(" planner/static/planner/js/signal_flow_editor.js` increasing by AT LEAST 3 (background-color on swatch + display on block + others).
    - NO `el.style.display = ` shorthand assignments in the new code — verified by inspection.
  </acceptance_criteria>
  <done>Boundary inspector panel helpers + applyBoundaryColor / applyBoundaryLineStyle exist with the correct mutation order; setInspectorMode branch added in Task 2.</done>
</task>

<task type="auto">
  <name>Task 2: Add textModeBlock builders (buildTextModeBlock + refreshTextModeBlock + applyTextColor + applyTextFontSize) + two new branches in setInspectorMode for 'boundary' and 'text'</name>
  <files>planner/static/planner/js/signal_flow_editor.js</files>
  <read_first>
    - planner/static/planner/js/signal_flow_editor.js (the buildBoundaryModeBlock just added by Task 1 — Task 2 clones the structure for text)
    - planner/static/planner/js/signal_flow_editor.js lines 2199-2240 (the existing setInspectorMode switch — insertion site for the two new else-if branches)
    - planner/static/planner/js/signal_flow_editor.js (find `connectorFieldRows` — the per-field array used by existing branches to hide connector controls)
    - planner/static/planner/js/signal_flow_editor.js (find `nodeModeBlock` and `portAuthorBlock` — the existing other-mode blocks that must be hidden when boundary/text mode is shown)
    - planner/static/planner/js/signal_flow_editor.js (find Plan 04's `lastTextSize` and `lastTextColor` — these MUST be mutated BEFORE scheduleAutosave per Violation 1)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-08 (lines 720-754 — verbatim setInspectorMode branches)
    - .planning/phases/12-boundaries-and-text/12-CONTEXT.md D-19 (font sizes 12/16/24, 9-color text palette including white)
  </read_first>
  <action>
    Two additive edits to `planner/static/planner/js/signal_flow_editor.js`.

    **EDIT 1 — Add text mode panel helpers.** Locate the closing brace of `refreshBoundaryModeBlock` from Task 1. Insert AFTER it:

    ```javascript
      // ──────────────────────────────────────────────────────────────
      // Phase 12 — Text-mode inspector panel (TXT-02).
      // ──────────────────────────────────────────────────────────────

      // Violation 1 — mutation order parallel to boundary.
      function applyTextColor(cell, hex) {
        if (!cell) return;
        lastTextColor = hex;
        cell.prop('color', hex);
        cell.attr('label/fill', hex);
        refreshTextModeBlock(cell);
        scheduleAutosave();
      }

      function applyTextFontSize(cell, size) {
        if (!cell) return;
        var px = TEXT_FONT_SIZES[size];                    // 12 / 16 / 24
        if (!px) return;
        lastTextSize = px;
        cell.prop('fontSize', px);
        cell.attr('label/fontSize', px);
        // Auto-refit cell width/height to the new font-size (reuse Plan 04's helper).
        var text = cell.attr('label/text') || '';
        var w = (typeof measureTextLabelWidth === 'function') ? measureTextLabelWidth(text, px) + 8 : Math.max(60, px * 4);
        var h = Math.max(22, px + 6);
        cell.resize(Math.ceil(w), Math.ceil(h));
        refreshTextModeBlock(cell);
        scheduleAutosave();
      }

      function buildTextModeBlock() {
        if (!inspectorEl) return;
        textModeBlock = document.createElement('div');
        textModeBlock.setAttribute('data-mode', 'text');
        textModeBlock.style.setProperty('display', 'none', 'important');

        // --- Color swatches: 3×3 grid (D-19 9 colors incl. white) ---
        var colorField = document.createElement('div');
        colorField.className = 'sfd-field';
        colorField.setAttribute('data-mode', 'text');
        var colorLabel = document.createElement('label');
        colorLabel.textContent = 'Color';
        colorField.appendChild(colorLabel);
        var swatchGrid = document.createElement('div');
        // Compose both classes — base swatches + text-mode 3×3 override (Section 18).
        swatchGrid.className = 'sfd-color-swatches sfd-color-swatches--text';
        TEXT_PALETTE.forEach(function (hex) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'sfd-color-swatch';
          btn.setAttribute('data-color', hex);
          btn.setAttribute('aria-label', 'Color ' + hex);
          btn.style.setProperty('background-color', hex, 'important');
          btn.addEventListener('click', function () {
            applyTextColor(inspectorCurrentText, hex);
          });
          swatchGrid.appendChild(btn);
        });
        colorField.appendChild(swatchGrid);

        // --- Font-size segmented: S / M / L (D-19) ---
        var sizeField = document.createElement('div');
        sizeField.className = 'sfd-field';
        sizeField.setAttribute('data-mode', 'text');
        var sizeLabel = document.createElement('label');
        sizeLabel.textContent = 'Font size';
        sizeField.appendChild(sizeLabel);
        var sizeSeg = document.createElement('div');
        // Compose: base segmented styling + text-mode letter sizing (Section 18).
        sizeSeg.className = 'sfd-segmented sfd-text-fontsize-segmented';
        sizeSeg.setAttribute('role', 'group');
        sizeSeg.setAttribute('aria-label', 'Text font size');
        ['small', 'medium', 'large'].forEach(function (sz) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.setAttribute('data-size', sz);
          btn.setAttribute('aria-label', sz + ' (' + TEXT_FONT_SIZES[sz] + ' px)');
          // XSS-safe: textContent (NOT innerHTML); user input is not interpolated.
          btn.textContent = sz === 'small' ? 'S' : (sz === 'medium' ? 'M' : 'L');
          btn.addEventListener('click', function () {
            applyTextFontSize(inspectorCurrentText, sz);
          });
          sizeSeg.appendChild(btn);
        });
        sizeField.appendChild(sizeSeg);

        textModeBlock.appendChild(colorField);
        textModeBlock.appendChild(sizeField);
        inspectorEl.appendChild(textModeBlock);
      }

      function refreshTextModeBlock(cell) {
        if (!textModeBlock || !cell) return;
        var color = cell.prop('color') || '#000000';
        var fontSize = cell.prop('fontSize') || 16;
        // Map px back to size keyword for the segmented button data-size match.
        var sizeKey = null;
        if (fontSize === 12) sizeKey = 'small';
        else if (fontSize === 24) sizeKey = 'large';
        else sizeKey = 'medium';

        var swatches = textModeBlock.querySelectorAll('.sfd-color-swatch');
        for (var i = 0; i < swatches.length; i++) {
          var s = swatches[i];
          if (s.getAttribute('data-color') === color) {
            s.setAttribute('data-active', 'true');
          } else {
            s.removeAttribute('data-active');
          }
        }
        var sizeBtns = textModeBlock.querySelectorAll('.sfd-segmented button[data-size]');
        for (var j = 0; j < sizeBtns.length; j++) {
          var b = sizeBtns[j];
          if (b.getAttribute('data-size') === sizeKey) {
            b.setAttribute('data-active', 'true');
          } else {
            b.removeAttribute('data-active');
          }
        }
      }
    ```

    **EDIT 2 — Add two new branches to setInspectorMode.** Locate the existing `setInspectorMode` switch at signal_flow_editor.js:~2199. Find the existing `else if (mode === 'node')` branch (around line 2213). Add immediately AFTER its closing brace (before the final `}` of the function) the following two branches:

    ```javascript
        } else if (mode === 'boundary') {
          if (inspectorHeader) inspectorHeader.textContent = 'Boundary';
          // Hide all other mode blocks.
          connectorFieldRows.forEach(function (row) {
            row.style.setProperty('display', 'none', 'important');
          });
          if (nodeModeBlock) nodeModeBlock.style.setProperty('display', 'none', 'important');
          if (portAuthorBlock) portAuthorBlock.style.setProperty('display', 'none', 'important');
          if (textModeBlock) textModeBlock.style.setProperty('display', 'none', 'important');
          // Show the boundary block.
          if (!boundaryModeBlock) buildBoundaryModeBlock();
          if (boundaryModeBlock) boundaryModeBlock.style.setProperty('display', 'block', 'important');
          inspectorCurrentBoundary = cell;
          inspectorCurrentText = null;
          inspectorCurrentLink = null;
          inspectorCurrentNode = null;
          refreshBoundaryModeBlock(cell);
        } else if (mode === 'text') {
          if (inspectorHeader) inspectorHeader.textContent = 'Text';
          connectorFieldRows.forEach(function (row) {
            row.style.setProperty('display', 'none', 'important');
          });
          if (nodeModeBlock) nodeModeBlock.style.setProperty('display', 'none', 'important');
          if (portAuthorBlock) portAuthorBlock.style.setProperty('display', 'none', 'important');
          if (boundaryModeBlock) boundaryModeBlock.style.setProperty('display', 'none', 'important');
          if (!textModeBlock) buildTextModeBlock();
          if (textModeBlock) textModeBlock.style.setProperty('display', 'block', 'important');
          inspectorCurrentText = cell;
          inspectorCurrentBoundary = null;
          inspectorCurrentLink = null;
          inspectorCurrentNode = null;
          refreshTextModeBlock(cell);
        }
    ```

    Place these branches BEFORE the final `}` of `setInspectorMode` but AFTER the `else if (mode === 'node')` branch. Insertion order matters — JavaScript checks `else if` chains top-to-bottom; mode strings are unique so order doesn't change behavior, but keeping new branches grouped after `'node'` matches the Phase 9 / 11 lineage.

    Also locate the existing `else if (mode === 'connector')` branch and the existing `'node'` branch — confirm they each hide `boundaryModeBlock` and `textModeBlock` to prevent the new blocks lingering when switching back to a connector or node. Add the following lines inside the existing 'connector' branch (after `nodeModeBlock.style.setProperty('display', 'none', 'important');` or equivalent):

    ```javascript
          if (boundaryModeBlock) boundaryModeBlock.style.setProperty('display', 'none', 'important');
          if (textModeBlock) textModeBlock.style.setProperty('display', 'none', 'important');
    ```

    Add the SAME two lines inside the existing 'node' branch. If a generic "hide all blocks" helper exists, extend it instead; otherwise add the two lines explicitly to each existing branch.
  </action>
  <verify>
    <automated>grep -n "function buildTextModeBlock" planner/static/planner/js/signal_flow_editor.js && grep -n "function refreshTextModeBlock" planner/static/planner/js/signal_flow_editor.js && grep -n "function applyTextColor" planner/static/planner/js/signal_flow_editor.js && grep -n "function applyTextFontSize" planner/static/planner/js/signal_flow_editor.js && grep -n "} else if (mode === 'boundary')" planner/static/planner/js/signal_flow_editor.js && grep -n "} else if (mode === 'text')" planner/static/planner/js/signal_flow_editor.js</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "function buildTextModeBlock" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function refreshTextModeBlock" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function applyTextColor" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function applyTextFontSize" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "} else if (mode === 'boundary')" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "} else if (mode === 'text')" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - **Mutation order — applyTextColor body:** literal order is `lastTextColor = hex;` THEN `cell.prop('color', hex);` THEN `cell.attr('label/fill', hex);` THEN `scheduleAutosave();`.
    - **Mutation order — applyTextFontSize body:** literal order is `lastTextSize = px;` THEN `cell.prop('fontSize', px);` THEN `cell.attr('label/fontSize', px);` THEN `cell.resize(...)` THEN `scheduleAutosave();`.
    - `buildTextModeBlock` creates 9 swatch buttons (one per TEXT_PALETTE entry — 8 colors + white) — verified by reading the `TEXT_PALETTE.forEach` loop.
    - `buildTextModeBlock` creates 3 segmented buttons with `data-size` values `small`, `medium`, `large` — verified by reading the `['small', 'medium', 'large'].forEach` loop.
    - The boundary-mode branch in setInspectorMode hides ALL OTHER mode blocks (`connectorFieldRows`, `nodeModeBlock`, `portAuthorBlock`, `textModeBlock`) via `style.setProperty('display', 'none', 'important')` BEFORE showing `boundaryModeBlock`.
    - The text-mode branch hides ALL OTHER mode blocks (`connectorFieldRows`, `nodeModeBlock`, `portAuthorBlock`, `boundaryModeBlock`) BEFORE showing `textModeBlock`.
    - The existing 'connector' AND 'node' branches each contain `if (boundaryModeBlock) boundaryModeBlock.style.setProperty('display', 'none', 'important');` AND `if (textModeBlock) textModeBlock.style.setProperty('display', 'none', 'important');` — verified by `grep -B 2 "boundaryModeBlock.style.setProperty('display', 'none'" planner/static/planner/js/signal_flow_editor.js` showing each occurrence inside a connector or node block context.
    - `applyTextFontSize` consults `TEXT_FONT_SIZES[size]` (the Plan 01 constant) — verified by `grep -c "TEXT_FONT_SIZES\\[" planner/static/planner/js/signal_flow_editor.js` returning AT LEAST 1.
    - The font-size segmented button content uses `textContent` (not innerHTML) — verified by reading the loop. The S/M/L letter comes from a fixed-literal conditional, never from user input.
    - Browser manual: select a placed boundary — inspector shows "Boundary" header with 8 swatches in 4×2 grid and 4 line-style buttons. Click red swatch → boundary stroke turns red, autosave fires; refresh — color persists. Click "dashed" style → stroke becomes dashed; refresh — style persists.
    - Browser manual: select a placed text — inspector shows "Text" header with 9 swatches in 3×3 grid (including white) and 3 size buttons (S/M/L). Click white swatch → text turns white; click "L" → text becomes 24px; refresh — both persist.
    - Browser manual: select a connector AFTER editing a boundary — connector inspector replaces boundary inspector (boundary block hidden via setProperty 'none').
  </acceptance_criteria>
  <done>buildTextModeBlock + refreshTextModeBlock + applyTextColor + applyTextFontSize all present; setInspectorMode has the new 'boundary' and 'text' branches; existing 'connector' and 'node' branches hide the new blocks for clean mode switching.</done>
</task>

</tasks>

<verification>
- `grep -n "function build\\(Boundary\\|Text\\)ModeBlock\\|function refresh\\(Boundary\\|Text\\)ModeBlock\\|function apply\\(Boundary\\|Text\\)\\(Color\\|LineStyle\\|FontSize\\)\\|function renderLineStylePreviewSVG" planner/static/planner/js/signal_flow_editor.js` — expect 9 distinct function declarations.
- `grep -nc "mode === 'boundary'\\|mode === 'text'" planner/static/planner/js/signal_flow_editor.js` — expect AT LEAST `2` (one per new branch).
- `grep -nc "boundaryModeBlock\\|textModeBlock" planner/static/planner/js/signal_flow_editor.js` — expect AT LEAST `20` (declarations + builds + refreshes + 4 setInspectorMode references — boundary mode + text mode + connector hide + node hide).
- Browser UAT — full inspector cycle: draw boundary → select → change color → change style → select another boundary → previous changes persisted on first; select connector → connector inspector replaces. Repeat with text.
</verification>

<must_haves>
- Boundary inspector mode panel exists with 8-swatch color grid (D-09) and 4-button line-style segmented (D-11, D-12) — DRAW-02 + DRAW-03.
- Text inspector mode panel exists with 9-swatch color grid (D-19 — 8 colors + white) and 3-button font-size segmented (D-19 — 12/16/24 px S/M/L) — TXT-02.
- setInspectorMode('boundary', cell) and setInspectorMode('text', cell) branches exist; each hides all other mode blocks before showing its own.
- All inspector swatch / segmented click handlers mutate sticky-default closure vars (lastBoundaryColor / lastBoundaryStyle / lastTextSize / lastTextColor) BEFORE cell.prop / applyBoundaryRender / scheduleAutosave per Pattern Violation 1.
- refreshBoundaryModeBlock(cell) syncs data-active on swatch + segmented buttons matching the cell's current color + lineStyle.
- refreshTextModeBlock(cell) syncs data-active on swatch + segmented buttons matching the cell's current color + fontSize (mapped to small/medium/large keyword).
- The existing 'connector' and 'node' setInspectorMode branches hide boundaryModeBlock and textModeBlock so panels never overlap.
- All DOM style writes use setProperty(... 'important') per CLAUDE.md admin-CSS override rule.
- renderLineStylePreviewSVG returns fixed-literal SVG markup — no user input interpolated (XSS safe-by-construction).
</must_haves>
