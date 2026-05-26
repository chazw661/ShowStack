---
phase: 12
plan_number: 04
wave: 3
depends_on: [01, 03]
files_modified:
  - planner/static/planner/js/signal_flow_editor.js
autonomous: true
requirements_addressed: [TXT-01, TXT-02, TXT-03]
must_haves:
  truths:
    - "Clicking #sfd-tool-text enters sticky place-text mode (per D-01); exits via Esc, re-click, or click of the boundary button"
    - "While in text mode, a blank:pointerdown places a TextLabel cell at the snapped position with sticky font-size + color, calls cell.toFront() (D-14), and immediately enters inline-edit mode (D-16)"
    - "Inline-edit mounts an <input type='text'> overlay positioned via paper.localToPaperRect(cell.getBBox()); writes back to cell.attr('label/text') on Enter or blur"
    - "Empty body on commit auto-deletes the cell (D-18); Esc on a newly placed cell with no prior text auto-deletes (D-16)"
    - "Double-click on a placed TextLabel re-enters inline-edit mode (D-17); single-click selects only (handled by Plan 06)"
    - "Pan/zoom force-commit any active text edit (Risk #5 — via explicit hooks in pan + zoom handler bodies, NOT a paper.on('translate scale') listener — BLOCKER 1)"
    - "Place-text handler ignores clicks while spacebar pan is engaged (panState.spaceDown guard — WARNING 5)"
    - "Place-text handler does NOT trigger rubber-band selection (textModeActive guard added to rubber-band handler — BLOCKER 2)"
    - "Snap-toggle reads from window.__sfd.viewport.snapEnabled (standardized source — WARNING 4)"
    - "commitTextEdit calls scheduleAutosave() explicitly as defence-in-depth against no-op cell.resize (WARNING 3)"
    - "Text-side session-sticky defaults (lastTextSize, lastTextColor) declared"
  artifacts:
    - path: "planner/static/planner/js/signal_flow_editor.js"
      provides: "textModeActive flag + enterTextMode/exitTextMode + place-text paper-event listener + enterTextEditMode/commitTextEdit/cancelTextEdit/teardownTextEditOverlay + element:pointerdblclick re-entry handler + lastTextSize/lastTextColor closure vars + pan/zoom force-commit hooks in pan + zoom handler bodies + rubber-band textModeActive guard"
      contains: "function enterTextMode"
      contains_also: "function enterTextEditMode"
  key_links:
    - from: "#sfd-tool-text click"
      to: "enterTextMode()"
      via: "addEventListener('click', ...)"
      pattern: "enterTextMode"
    - from: "blank:pointerdown while textModeActive"
      to: "new joint.shapes.showstack.TextLabel + cell.toFront + enterTextEditMode"
      via: "paper.on('blank:pointerdown', ...) gated on textModeActive"
      pattern: "enterTextEditMode"
    - from: "Enter/blur on overlay input"
      to: "cell.attr('label/text', value) OR cell.remove()"
      via: "commitTextEdit"
      pattern: "label/text"
    - from: "pan handler body (mousemove ~line 1158) AND setZoom (~line 1181)"
      to: "commitTextEdit() if inTextEdit"
      via: "explicit if (inTextEdit) commitTextEdit(); inserted at top of each handler body (BLOCKER 1)"
      pattern: "if \\(inTextEdit\\) commitTextEdit\\(\\);"
---

<objective>
Implement the text-place mode and inline-edit lifecycle: sticky mode toggle on `#sfd-tool-text`, click-to-place + immediate-edit per D-16, Enter/blur commit and Esc cancel paths per D-18, double-click re-entry per D-17, empty-body auto-delete per D-18, pan/zoom force-commit (Risk #5 — implemented via explicit hooks in the existing pan and zoom handler bodies, NOT via a `paper.on('translate scale', ...)` listener which JointJS 4.2.4 does NOT emit), and text-side session-sticky default closure vars (`lastTextSize`, `lastTextColor`). Depends on Plan 01 (TextLabel cell class) and Plan 03 (mode-handoff convention with drawState — D-01 cross-mode exit). Inspector text-mode panel lives in Plan 05; selection wiring to setInspectorMode('text', cell) lives in Plan 06.
</objective>

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| XSS via TextLabel text body | low | TextLabel uses SVG `<text>` (Plan 01 markup). All user input flows through `cell.attr('label/text', input.value)` which sets the SVG text-node content (NOT innerHTML). The overlay input writes its `.value` directly. Acceptance criterion: NO `innerHTML` assignment from `input.value` anywhere in this plan's code. |
| Stale overlay drifts off cell on pan/zoom (Risk #5, BLOCKER 1) | high | JointJS 4.2.4 Paper does NOT emit `'translate'` or `'scale'` events — verified by reading all `paper.translate(...)` and `paper.scale(...)` call sites in signal_flow_editor.js (lines 826, 827, 1152, 1162, 1183, 1194, 1204, 1207); every one is a bare setter with no `paper.trigger(...)` anywhere. Mitigation: explicit `if (inTextEdit) commitTextEdit();` hooks inserted at the top of (a) the document mousemove pan handler at signal_flow_editor.js:~1158 (before the `paper.translate(...)` call at line 1162), and (b) the `setZoom` function body at signal_flow_editor.js:~1181 (before the `paper.scale(...)` call at line 1183). Acceptance criterion: TWO occurrences of literal `if (inTextEdit) commitTextEdit();` in the file. |
| Esc keydown ordering — Esc-in-edit must cancel-edit, NOT bubble to selection-clear | medium | The overlay `<input>` holds focus during edit; the document keydown handler at signal_flow_editor.js:~1549 has an `INPUT/TEXTAREA/SELECT` early-exit that returns before any other branch. Plan 04 verifies that early-exit remains in place; the overlay's own keydown listener handles Esc. |
| Overlay positioned in wrong coords (SVG vs CSS pixels) | medium | Use `paper.localToPaperRect(cell.getBBox())` — documented JointJS API for converting cell-local bbox to paper-screen-pixel coords. Verified in PATTERNS Region E lines 287-296. |
| Commit triggers double-fire (blur + Enter both fire) | low | `commitTextEdit` tears down the overlay FIRST, then performs the cell mutation. The teardown flips `inTextEdit = false`; a re-entrant call early-returns on the `if (!inTextEdit) return;` guard. |
| commitTextEdit no-op resize → no autosave (WARNING 3) | low | `cell.resize(...)` fires `change:size` which the line-2403 listener catches; `cell.attr('label/text', ...)` does NOT autosave on its own (the listener does NOT include `change:attrs` in its comma-list). If a re-edit produces the same measured width (same character count + same font), `cell.resize` is a no-op and no `change:size` fires. Defence-in-depth: explicit `scheduleAutosave();` call at the end of `commitTextEdit`. |
| Place-text fires alongside rubber-band selection (BLOCKER 2 — parallel to Plan 03 Risk #1) | high | `if (textModeActive) return;` inserted as the SECOND executable line of the rubber-band handler at signal_flow_editor.js:1500 — AFTER Plan 03's `if (drawState.active) return;` and BEFORE the `if (panState.spaceDown || evt.button !== 0) return;`. |
| Place-text fires while spacebar-pan engaged (WARNING 5) | medium | `if (panState.spaceDown) return;` added inside the place-text blank:pointerdown handler — AFTER the `!textModeActive` early-exit and BEFORE the rest of the body. |
| Snap-toggle source divergence (WARNING 4) | low | Place-text snap branch reads `window.__sfd.viewport.snapEnabled` — matches Phase 11 CornerResize, Plan 03 pen-tool, and Plan 06 BoundaryVertex. |
| Autosave triggers on every keystroke | low | Autosave only fires on commit (cell.attr/cell.resize/scheduleAutosave inside commitTextEdit), NOT during typing. |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Declare text-side sticky-default vars + textModeActive flag + enterTextMode/exitTextMode + toolbar text-button wiring</name>
  <files>planner/static/planner/js/signal_flow_editor.js</files>
  <read_first>
    - planner/static/planner/js/signal_flow_editor.js (read the drawState block inserted by Plan 03 — find the literal `var drawState = {` and the surrounding `enterBoundaryMode` / `exitBoundaryMode` functions to mirror)
    - planner/static/planner/js/signal_flow_editor.js (read the sticky-default closure block from Plan 03 — find `var lastBoundaryColor = '#000000'` to know the insertion site for the text-side vars)
    - planner/static/planner/js/signal_flow_editor.js (read the toolbar wiring block from Plan 03 — find `var toolBoundaryBtn = document.getElementById('sfd-tool-boundary')` to find the parallel wiring site for `#sfd-tool-text`)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-02 (lines 223-309 — verbatim TextLabel inline-edit flow)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-09 (lines 763-786 — sticky defaults)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md "Region E" (lines 271-306 — text inline-edit lifecycle directive)
    - .planning/phases/12-boundaries-and-text/12-CONTEXT.md D-16..D-19 (sticky place-text, inline edit, single-line, empty auto-delete, font sizes/palette)
    - CLAUDE.md "Overriding Django admin CSS from JavaScript" — overlay-input style.setProperty('font-size', ..., 'important') mandate.
  </read_first>
  <action>
    Three additive edits to `planner/static/planner/js/signal_flow_editor.js`.

    **EDIT 1 — Add text-side sticky-default closure vars + textModeActive flag.** Locate the Plan 03 block containing `var lastBoundaryColor = '#000000';` and `var lastBoundaryStyle = 'solid';`. Add immediately AFTER those two lines:

    ```javascript
        // Phase 12 — session-sticky defaults for next-placed text label.
        // Closure-scoped; reset on page reload.
        var lastTextSize  = 16;            // D-19 medium default
        var lastTextColor = '#000000';     // D-19 black default

        // Phase 12 — text-mode + inline-edit state. textModeActive is the sticky
        // mode flag (parallel to drawState.active). inTextEdit is the per-edit
        // flag used by the pan/zoom force-commit hooks (Risk #5, BLOCKER 1).
        var textModeActive = false;
        var inTextEdit = false;
        var textEditCell = null;           // the cell currently being edited (null when not)
        var textEditOverlay = null;        // the transient <input> overlay element
        var textEditWasPlaced = false;     // true if this edit session is a fresh place (D-16 Esc cancel rules)
    ```

    **EDIT 2 — Add enterTextMode + exitTextMode helpers.** Locate the Plan 03 `function exitBoundaryMode() {` block — the closing `}` of that function. Insert AFTER `exitBoundaryMode`'s closing brace:

    ```javascript
      // ──────────────────────────────────────────────────────────────
      // Phase 12 — Place-text mode (TXT-01) + inline-edit lifecycle.
      // ──────────────────────────────────────────────────────────────

      function enterTextMode() {
        // D-01 — if boundary draw is active, exit it (cross-mode handoff).
        if (drawState.active) exitBoundaryMode();
        textModeActive = true;
        var btn = document.getElementById('sfd-tool-text');
        if (btn) {
          btn.classList.add('is-active');
          btn.setAttribute('aria-pressed', 'true');
        }
        var paperEl = document.getElementById('sfd-paper');
        if (paperEl) paperEl.style.setProperty('cursor', 'crosshair', 'important');
      }

      function exitTextMode() {
        textModeActive = false;
        var btn = document.getElementById('sfd-tool-text');
        if (btn) {
          btn.classList.remove('is-active');
          btn.setAttribute('aria-pressed', 'false');
        }
        var paperEl = document.getElementById('sfd-paper');
        if (paperEl) paperEl.style.setProperty('cursor', '', 'important');
      }
    ```

    **EDIT 3 — Wire the toolbar #sfd-tool-text click.** Locate the Plan 03 toolbar wiring block (`var toolBoundaryBtn = document.getElementById('sfd-tool-boundary');`). Insert AFTER that block's closing brace:

    ```javascript
      // Phase 12 — Toolbar wiring: place-text mode toggle (D-01 sticky).
      var toolTextBtn = document.getElementById('sfd-tool-text');
      if (toolTextBtn) {
        toolTextBtn.addEventListener('click', function () {
          if (textModeActive) {
            // Re-click exits per D-01. If an edit is mid-flight, force-commit first.
            if (inTextEdit) commitTextEdit();
            exitTextMode();
          } else {
            enterTextMode();
          }
        });
      }
    ```

    Note: `commitTextEdit` is referenced before declaration; it's defined in Task 2. JavaScript hoisting of function declarations covers this — Task 2's `commitTextEdit` is a `function commitTextEdit() {}` declaration (NOT `var commitTextEdit = function () {}`).

    Plan 03's `enterBoundaryMode` already calls `exitTextMode()` (via `if (typeof exitTextMode === 'function' && typeof textModeActive !== 'undefined' && textModeActive) exitTextMode();`); now that exitTextMode is declared, that call will resolve. Verify Plan 03's enterBoundaryMode still contains the textModeActive guard — if missing, this plan SHOULD add the equivalent exit-handoff inside enterBoundaryMode. Read the function body to confirm.
  </action>
  <verify>
    <automated>grep -n "var lastTextSize  = 16" planner/static/planner/js/signal_flow_editor.js && grep -n "var lastTextColor = '#000000'" planner/static/planner/js/signal_flow_editor.js && grep -n "var textModeActive = false" planner/static/planner/js/signal_flow_editor.js && grep -n "var inTextEdit = false" planner/static/planner/js/signal_flow_editor.js && grep -n "function enterTextMode" planner/static/planner/js/signal_flow_editor.js && grep -n "function exitTextMode" planner/static/planner/js/signal_flow_editor.js && grep -n "var toolTextBtn = document.getElementById" planner/static/planner/js/signal_flow_editor.js</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "var lastTextSize  = 16" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var lastTextColor = '#000000'" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var textModeActive = false" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var inTextEdit = false" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var textEditCell = null" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var textEditOverlay = null" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function enterTextMode" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function exitTextMode" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - The `enterTextMode` body contains the literal `if (drawState.active) exitBoundaryMode();` (cross-mode handoff per D-01).
    - The `enterTextMode` body contains `paperEl.style.setProperty('cursor', 'crosshair', 'important')`.
    - `grep -c "var toolTextBtn = document.getElementById('sfd-tool-text')" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
  </acceptance_criteria>
  <done>textModeActive flag + sticky defaults + enterTextMode/exitTextMode + toolbar #sfd-tool-text click handler all present.</done>
</task>

<task type="auto">
  <name>Task 2: Add place-text blank:pointerdown listener + enterTextEditMode/commitTextEdit/cancelTextEdit + teardown + dblclick re-entry + pan/zoom force-commit hooks + rubber-band textModeActive guard + measureTextLabelWidth helper</name>
  <files>planner/static/planner/js/signal_flow_editor.js</files>
  <read_first>
    - planner/static/planner/js/signal_flow_editor.js (find the Plan 03 `function commitOrCancelBoundary` — insertion happens immediately after its closing brace)
    - planner/static/planner/js/signal_flow_editor.js lines 440-460 (Phase 11 measureLabelWidth — Canvas-2D measureText pattern to clone for text auto-fit width)
    - planner/static/planner/js/signal_flow_editor.js lines 1145-1172 (document mousemove pan handler body — site for BLOCKER 1 hook #1; the `paper.translate(...)` call is at line 1162)
    - planner/static/planner/js/signal_flow_editor.js lines 1181-1187 (setZoom function body — site for BLOCKER 1 hook #2; the `paper.scale(...)` call is at line 1183)
    - planner/static/planner/js/signal_flow_editor.js line 1500 (rubber-band handler — site for BLOCKER 2 guard insertion; Plan 03 EDIT 4 inserts `if (drawState.active) return;` as the first line, this plan inserts `if (textModeActive) return;` as the second line)
    - planner/static/planner/js/signal_flow_editor.js (NOTE: JointJS 4.2.4 Paper does NOT emit 'translate' or 'scale' events. Verify by `grep -n "paper.trigger" planner/static/planner/js/signal_flow_editor.js` returning ZERO hits for translate/scale. The original Risk #5 mitigation via `paper.on('translate scale', ...)` is a no-op and MUST NOT be used — use the explicit-hook approach below.)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-02 (lines 263-307 — verbatim commit / cancel event-flow)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md "Region E" (lines 271-306 — overlay lifecycle directive)
    - .planning/phases/12-boundaries-and-text/12-CONTEXT.md D-16..D-18 (inline edit lifecycle, single-line, auto-delete empty)
    - CLAUDE.md "Overriding Django admin CSS from JavaScript" — overlay-input style.setProperty mandate.
  </read_first>
  <action>
    Five additive edits to `planner/static/planner/js/signal_flow_editor.js`.

    **EDIT 1 — Place-text + inline-edit lifecycle block.** Locate the Plan 03 `function commitOrCancelBoundary() { ... }` block — find its closing brace. Insert AFTER that closing brace the following block:

    ```javascript
      // ──────────────────────────────────────────────────────────────
      // Phase 12 — Place-text + inline-edit lifecycle (TXT-01, TXT-02, TXT-03).
      // D-16: click → place + immediate edit.
      // D-17: dblclick → re-enter edit on a placed cell.
      // D-18: Enter or blur commits; empty body auto-deletes; Esc cancels
      //       (deletes if newly placed, otherwise restores).
      // ──────────────────────────────────────────────────────────────

      // Canvas-2D measure for auto-fit cell width on commit. Mirrors the Phase 11
      // measureLabelWidth pattern at signal_flow_editor.js:445-455.
      function measureTextLabelWidth(text, fontSize) {
        if (!text) return 0;
        var ctx = document.createElement('canvas').getContext('2d');
        ctx.font = fontSize + 'px ' + 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
        return ctx.measureText(text).width;
      }

      // Place-text vertex listener — gated on textModeActive. Coexists with the
      // pen-tool listener from Plan 03 (each early-exits if their mode is not active).
      paper.on('blank:pointerdown', function (evt, x, y) {
        if (!textModeActive) return;
        if (panState.spaceDown) return;        // WARNING 5 — spacebar pan trumps place-text
        if (inTextEdit) return;                // a placed cell is already in edit; click commits via blur
        var pt = { x: x, y: y };
        if (window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled) {
          pt.x = Math.round(pt.x / 20) * 20;
          pt.y = Math.round(pt.y / 20) * 20;
        }
        // Initial size — auto-fit happens on commit. Start narrow.
        var cell = new joint.shapes.showstack.TextLabel({
          position: pt,
          fontSize: lastTextSize,
          color:    lastTextColor,
          attrs: {
            label: {
              fontSize: lastTextSize,
              fill:     lastTextColor,
              text:     '',
            },
          },
        });
        graph.addCell(cell);
        cell.toFront();                 // D-14 — text always on top
        enterTextEditMode(cell, /* wasPlaced= */ true);
      });

      // Inline-edit entry — mounts a transient <input> overlay over the cell bbox.
      function enterTextEditMode(cell, wasPlaced) {
        if (inTextEdit) return;
        inTextEdit = true;
        textEditCell = cell;
        textEditWasPlaced = !!wasPlaced;

        // Hide the SVG glyph during edit so a stale label doesn't sit under the input.
        cell.attr('label/display', 'none');

        var paperEl = document.getElementById('sfd-paper');
        var screenBbox = paper.localToPaperRect(cell.getBBox());

        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'sfd-text-edit-overlay';
        input.value = cell.attr('label/text') || '';
        // Position absolutely over the cell screen bbox.
        // Per CLAUDE.md admin-CSS override rule, every inline style uses setProperty(... 'important').
        input.style.setProperty('left',   screenBbox.x + 'px', 'important');
        input.style.setProperty('top',    screenBbox.y + 'px', 'important');
        input.style.setProperty('width',  Math.max(60, screenBbox.width)  + 'px', 'important');
        input.style.setProperty('height', screenBbox.height + 'px', 'important');
        input.style.setProperty('font-size', (cell.prop('fontSize') || 16) + 'px', 'important');
        input.style.setProperty('color',     (cell.prop('color')    || '#000000'),  'important');

        // Append to the paper's parent (HTML overlay must be HTML, not SVG child).
        (paperEl && paperEl.parentNode || document.body).appendChild(input);
        textEditOverlay = input;

        input.addEventListener('blur', function () { commitTextEdit(); });
        input.addEventListener('keydown', function (evt) {
          if (evt.key === 'Enter') {
            evt.preventDefault();           // D-18 — Enter commits, no newline insertion
            commitTextEdit();
          } else if (evt.key === 'Escape') {
            evt.preventDefault();
            cancelTextEdit();
          }
        });
        input.focus();
        input.select();
      }

      function commitTextEdit() {
        if (!inTextEdit) return;
        var cell = textEditCell;
        var input = textEditOverlay;
        var raw = (input && input.value) || '';
        var value = raw.trim();
        // Tear down the overlay FIRST so a re-entrant call (blur fires after focus
        // is removed) does not double-commit.
        teardownTextEditOverlay();
        if (!cell) return;
        if (value === '') {
          // D-18 — empty commit auto-deletes.
          cell.remove();
          return;
        }
        // Persist the text + auto-fit cell width.
        // WARNING 3 — cell.resize(...) fires change:size which is caught by the
        // line-2403 listener; cell.attr('label/text', ...) does NOT trigger
        // autosave on its own (the listener does NOT include change:attrs).
        // If the new value measures to the same width as the prior value (same
        // characters + same font), cell.resize is a no-op and no change:size
        // fires. Defence-in-depth: explicit scheduleAutosave() below.
        cell.attr('label/text', value);
        cell.attr('label/display', null);
        var fontSize = cell.prop('fontSize') || 16;
        var w = measureTextLabelWidth(value, fontSize) + 8;     // 4px padding each side per D-19
        var h = Math.max(22, fontSize + 6);
        cell.resize(Math.ceil(w), Math.ceil(h));
        scheduleAutosave();                                     // WARNING 3 — defence-in-depth
      }

      function cancelTextEdit() {
        if (!inTextEdit) return;
        var cell = textEditCell;
        var wasPlaced = textEditWasPlaced;
        teardownTextEditOverlay();
        if (!cell) return;
        if (wasPlaced) {
          // D-16 — Esc on a freshly placed empty cell removes it.
          cell.remove();
        } else {
          // D-16 — re-entered edit (D-17 dblclick): keep existing text; just restore SVG.
          cell.attr('label/display', null);
        }
      }

      function teardownTextEditOverlay() {
        if (textEditOverlay && textEditOverlay.parentNode) {
          textEditOverlay.parentNode.removeChild(textEditOverlay);
        }
        textEditOverlay = null;
        textEditCell = null;
        textEditWasPlaced = false;
        inTextEdit = false;
      }

      // D-17 — double-click on a placed TextLabel re-enters edit mode.
      paper.on('element:pointerdblclick', function (elementView, evt) {
        var cell = elementView.model;
        if (cell && cell.get('type') === 'showstack.TextLabel') {
          if (evt && typeof evt.preventDefault === 'function') evt.preventDefault();
          enterTextEditMode(cell, /* wasPlaced= */ false);
        }
      });
    ```

    **EDIT 2 — Pan force-commit hook (BLOCKER 1, hook #1).** Locate the document mousemove pan handler at signal_flow_editor.js:~1158. Its body currently reads:

    ```javascript
    document.addEventListener('mousemove', function (evt) {
      if (!panState.dragging) return;
      var dx = evt.clientX - panState.startX;
      var dy = evt.clientY - panState.startY;
      paper.translate(panState.baseTx + dx, panState.baseTy + dy);
      ...
    });
    ```

    Insert `if (inTextEdit) commitTextEdit();` as a new line immediately BEFORE `paper.translate(panState.baseTx + dx, panState.baseTy + dy);` so the handler reads:

    ```javascript
    document.addEventListener('mousemove', function (evt) {
      if (!panState.dragging) return;
      var dx = evt.clientX - panState.startX;
      var dy = evt.clientY - panState.startY;
      if (inTextEdit) commitTextEdit();          // Phase 12 BLOCKER 1 — Risk #5 force-commit on pan
      paper.translate(panState.baseTx + dx, panState.baseTy + dy);
      ...
    });
    ```

    Do NOT move or remove any other line of the pan handler.

    **EDIT 3 — Zoom force-commit hook (BLOCKER 1, hook #2).** Locate the `setZoom` function at signal_flow_editor.js:~1181. Its body currently reads:

    ```javascript
    function setZoom(newScale) {
      newScale = Math.max(0.25, Math.min(2.0, newScale));
      paper.scale(newScale, newScale);
      ...
    }
    ```

    Insert `if (inTextEdit) commitTextEdit();` as a new line immediately BEFORE `paper.scale(newScale, newScale);` so the function reads:

    ```javascript
    function setZoom(newScale) {
      newScale = Math.max(0.25, Math.min(2.0, newScale));
      if (inTextEdit) commitTextEdit();          // Phase 12 BLOCKER 1 — Risk #5 force-commit on zoom
      paper.scale(newScale, newScale);
      ...
    }
    ```

    Do NOT move or remove any other line of `setZoom`. Do NOT add hooks to `zoomToFit` — it calls `setZoom` and the hook will run via that call path (the additional `paper.translate(0, 0)` and `paper.translate(tx, ty)` calls at lines 1194 and 1207 are reachable only when `cells.length === 0` or fresh-fit, scenarios where a text edit being mid-flight is implausible; if defence-in-depth is desired, an `if (inTextEdit) commitTextEdit();` line at the TOP of `zoomToFit` would cover it — OPTIONAL, not required by BLOCKER 1).

    **EDIT 4 — Rubber-band textModeActive guard (BLOCKER 2).** Locate the rubber-band handler at signal_flow_editor.js:~1500. After Plan 03 EDIT 4 lands, the handler reads:

    ```javascript
    paper.on('blank:pointerdown', function (evt, x, y) {
      if (drawState.active) return;                              // Plan 03 EDIT 4
      if (panState.spaceDown || evt.button !== 0) return;
      ...
    });
    ```

    Insert `if (textModeActive) return;` as a new line between Plan 03's `if (drawState.active) return;` and the existing `if (panState.spaceDown ...) return;` line. After insertion, the handler reads:

    ```javascript
    paper.on('blank:pointerdown', function (evt, x, y) {
      if (drawState.active) return;                              // Plan 03 EDIT 4
      if (textModeActive) return;                                // Phase 12 BLOCKER 2
      if (panState.spaceDown || evt.button !== 0) return;
      ...
    });
    ```

    Do NOT remove either of the existing early-exits.

    **EDIT 5 — Do NOT install a paper.on('translate scale', ...) listener.** This was the original Risk #5 mitigation but it is a no-op against JointJS 4.2.4 (verified by reading all `paper.translate(...)` and `paper.scale(...)` call sites — none call `paper.trigger(...)`). The force-commit is achieved by EDITs 2 and 3 above. Acceptance criterion: `grep -c "paper.on('translate" planner/static/planner/js/signal_flow_editor.js` returns `0`.

    Do NOT modify the existing keydown handler — the overlay's input-local `keydown` listener handles Esc/Enter while focus is in the input. The existing document keydown handler has an `INPUT/TEXTAREA/SELECT` early-exit that lets the input's local listener handle the event undisturbed. If the existing early-exit is missing or has been modified to NOT early-exit, fix it to early-return per Plan 03's expected state.

    Do NOT add a new listener to the line-2403 autosave event list — `cell.resize(...)` already fires `change:size` which the existing listener catches, and the explicit `scheduleAutosave()` call in `commitTextEdit` covers the no-op-resize edge case (WARNING 3).
  </action>
  <verify>
    <automated>grep -n "function enterTextEditMode" planner/static/planner/js/signal_flow_editor.js && grep -n "function commitTextEdit" planner/static/planner/js/signal_flow_editor.js && grep -n "function cancelTextEdit" planner/static/planner/js/signal_flow_editor.js && grep -n "function teardownTextEditOverlay" planner/static/planner/js/signal_flow_editor.js && grep -n "function measureTextLabelWidth" planner/static/planner/js/signal_flow_editor.js && grep -n "new joint.shapes.showstack.TextLabel" planner/static/planner/js/signal_flow_editor.js && grep -n "cell.toFront" planner/static/planner/js/signal_flow_editor.js && grep -n "paper.on('element:pointerdblclick'" planner/static/planner/js/signal_flow_editor.js && grep -n "if (inTextEdit) commitTextEdit();" planner/static/planner/js/signal_flow_editor.js && grep -n "if (textModeActive) return;" planner/static/planner/js/signal_flow_editor.js && grep -n "paper.localToPaperRect" planner/static/planner/js/signal_flow_editor.js</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "function enterTextEditMode" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function commitTextEdit" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function cancelTextEdit" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function teardownTextEditOverlay" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function measureTextLabelWidth" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "new joint.shapes.showstack.TextLabel" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `1` (in the place-text listener)
    - `grep -c "cell.toFront" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `1` (place-text post-addCell call)
    - `grep -c "paper.on('element:pointerdblclick'" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `1`
    - **BLOCKER 1 — explicit force-commit hooks.** `grep -c "if (inTextEdit) commitTextEdit();" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `2` (one inserted above `paper.translate(panState.baseTx + dx, ...)` in the pan handler; one inserted above `paper.scale(newScale, newScale)` in setZoom). Per-site sanity check:
      - `grep -B 2 -A 1 "if (inTextEdit) commitTextEdit();" planner/static/planner/js/signal_flow_editor.js | grep -c "paper.translate"` returns AT LEAST `1`
      - `grep -B 2 -A 1 "if (inTextEdit) commitTextEdit();" planner/static/planner/js/signal_flow_editor.js | grep -c "paper.scale"` returns AT LEAST `1`
    - **BLOCKER 1 — no unfireable listener.** `grep -c "paper.on('translate" planner/static/planner/js/signal_flow_editor.js` returns EXACTLY `0`. `grep -c "paper.on('translate scale'" planner/static/planner/js/signal_flow_editor.js` returns EXACTLY `0`.
    - **BLOCKER 2 — textModeActive rubber-band guard.** `grep -c "if (textModeActive) return;" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `2` (rubber-band guard at line ~1501 inserted by this EDIT 4 + the existing first-line check in the place-text handler itself). After Plan 04 lands, the rubber-band handler at line ~1500 begins with `paper.on('blank:pointerdown'` and its first three executable lines are, in order: `if (drawState.active) return;`, `if (textModeActive) return;`, `if (panState.spaceDown || evt.button !== 0) return;`.
    - `grep -c "paper.localToPaperRect" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `1`
    - **WARNING 3 — explicit scheduleAutosave + corrected comment.** `commitTextEdit` body contains the literal `scheduleAutosave();` call as its final executable statement before the closing brace — verified by `grep -B 4 -A 1 "scheduleAutosave();" planner/static/planner/js/signal_flow_editor.js | grep -c "cell.resize(Math.ceil(w)"` returning AT LEAST `1`. The misleading "cell.attr('label/text', value) triggers autosave via the line-2403 listener" comment is corrected to state "cell.resize(...) fires change:size which is caught by the line-2403 listener; cell.attr('label/text', ...) does not trigger autosave on its own" — verified by `grep -c "does NOT trigger autosave on its own" planner/static/planner/js/signal_flow_editor.js` OR `grep -c "does not trigger autosave on its own" planner/static/planner/js/signal_flow_editor.js` returning AT LEAST `1`.
    - **WARNING 4 — standardized snap-toggle.** Place-text snap branch reads `window.__sfd.viewport.snapEnabled` (NOT `currentViewport.snapEnabled`). Verified by reading the place-text handler body and confirming the literal `if (window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled)` is present. After Plans 03 and 04 land, `grep -c "window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `3` (pen-tool blank:pointerdown + pen-tool blank:pointermove + place-text blank:pointerdown).
    - **WARNING 5 — place-text spacebar-pan guard.** Place-text blank:pointerdown body contains `if (panState.spaceDown) return;` as the SECOND executable line — after `if (!textModeActive) return;` and BEFORE `if (inTextEdit) return;`. Verified by reading the handler body.
    - `commitTextEdit` body contains the literal `if (value === '')` (auto-delete empty per D-18) — verified by `grep -c "if (value === '')" planner/static/planner/js/signal_flow_editor.js` returning `1`.
    - `cancelTextEdit` body contains the literal `if (wasPlaced)` (D-16 Esc-on-newly-placed delete) — verified by `grep -c "if (wasPlaced)" planner/static/planner/js/signal_flow_editor.js` returning `1`.
    - The overlay input creation contains the literal `input.className = 'sfd-text-edit-overlay'` (uses Plan 02's Section 18 CSS class) — verified by grep.
    - NO `input.innerHTML` assignment anywhere in the new code (XSS audit) — verified by `grep -c "input.innerHTML" planner/static/planner/js/signal_flow_editor.js` returning the SAME count as before this plan (no new innerHTML introduced).
    - The overlay style writes use `setProperty(... 'important')` for left, top, width, height, font-size, color — verified by 6 hits inside `enterTextEditMode` for `input.style.setProperty`.
    - Browser manual: click "Place text" button — teal active, cursor crosshair. Click on the canvas — a blinking caret appears in a teal-bordered transparent input over the click point. Type "FOH" + press Enter — input disappears, "FOH" appears as SVG text. Refresh — "FOH" persists.
    - Browser manual: place text "Test" + commit. Double-click on the text — input re-appears with "Test" selected. Type "Hello" + Enter — text now reads "Hello".
    - Browser manual: place text + immediately press Esc with no characters typed — cell auto-deletes (D-16).
    - Browser manual: place text "X" + select-all + Backspace + Enter — cell auto-deletes (D-18 empty commit).
    - Browser manual: place text + start editing + pan the canvas with spacebar — edit force-commits (Risk #5 via BLOCKER 1 pan hook).
    - Browser manual: place text + start editing + scroll-wheel zoom — edit force-commits (Risk #5 via BLOCKER 1 zoom hook).
    - Browser manual: in text mode, drag on blank canvas — NO rubber-band marquee appears (BLOCKER 2 guard); exit text mode then drag — rubber-band marquee returns.
    - Browser manual: in text mode, hold spacebar + click — NO text cell placed (WARNING 5); release spacebar then click — text cell places as normal.
  </acceptance_criteria>
  <done>Click-to-place text + immediate edit + Enter/blur commit + Esc cancel + dblclick re-entry + auto-delete empty + pan/zoom force-commit via explicit hooks + rubber-band textModeActive guard + spacebar-pan guard + standardized snap-toggle + explicit scheduleAutosave defence-in-depth all working; placed text persists through autosave round-trip including the no-op-resize edge case.</done>
</task>

</tasks>

<verification>
- `grep -n "function enter\\(Text\\)\\?Mode\\|function exit\\(Text\\)\\?Mode\\|function \\(enter\\|commit\\|cancel\\|teardown\\)TextEdit" planner/static/planner/js/signal_flow_editor.js` — expect at least 6 distinct function declarations for text-mode + inline-edit.
- `grep -c "showstack.TextLabel" planner/static/planner/js/signal_flow_editor.js` — expect AT LEAST `4` (class registration from Plan 01, place-text constructor, dblclick type check, potentially other references).
- `grep -c "cell.toFront\\|cell.toBack" planner/static/planner/js/signal_flow_editor.js` — expect AT LEAST `2` (one toBack from Plan 03, one toFront from Plan 04).
- `grep -c "if (inTextEdit) commitTextEdit();" planner/static/planner/js/signal_flow_editor.js` — expect AT LEAST `2` (BLOCKER 1 pan hook + zoom hook; plus 1 inside the toolbar text-button click handler from Task 1 EDIT 3 — total may be `3`).
- `grep -c "paper.on('translate" planner/static/planner/js/signal_flow_editor.js` — expect EXACTLY `0` (BLOCKER 1 negative check; the unfireable listener MUST NOT exist).
- `grep -c "if (textModeActive) return;" planner/static/planner/js/signal_flow_editor.js` — expect AT LEAST `2` (BLOCKER 2 rubber-band guard + the place-text handler's own first-line check).
- Browser UAT — place 3 text labels in different font sizes (size picker is Plan 05, but test the default 16px here), refresh the page, all 3 persist.
- Browser UAT — place a text label, double-click to re-edit, change text, commit, refresh — updated text persists.
- Browser UAT — confirm pan and zoom do not leave a stale overlay floating on screen (Risk #5 via BLOCKER 1 explicit hooks).
- Browser UAT — in text mode, drag on blank canvas does NOT show a rubber-band selection rect (BLOCKER 2).
</verification>

<must_haves>
- Toolbar #sfd-tool-text toggles sticky place-text mode per D-01 (TXT-01).
- Place-text blank:pointerdown creates a TextLabel cell at the snapped position, calls cell.toFront() per D-14, immediately enters inline-edit mode per D-16.
- Place-text handler ignores clicks while spacebar pan is engaged (panState.spaceDown guard — WARNING 5).
- Rubber-band handler at line 1500 contains `if (textModeActive) return;` as the SECOND executable line so text-mode clicks do NOT trigger rubber-band selection (BLOCKER 2).
- enterTextEditMode mounts an `<input type="text">` overlay positioned via paper.localToPaperRect(cell.getBBox()); writes back to cell.attr('label/text') on Enter or blur per D-18.
- Empty body on commit auto-deletes the cell per D-18; Esc on a freshly placed empty cell auto-deletes per D-16; Esc on a re-entered (dblclick) cell restores the existing text per D-16.
- Double-click on a placed TextLabel re-enters edit mode per D-17 (TXT-03 partial — selection wired in Plan 06).
- pan/zoom force-commit any active text edit per Risk #5 — implemented via explicit `if (inTextEdit) commitTextEdit();` hooks inserted in the pan handler body (above `paper.translate(...)`) and the zoom handler body (above `paper.scale(...)`), NOT via a `paper.on('translate scale', ...)` listener which JointJS 4.2.4 does NOT emit (BLOCKER 1).
- commitTextEdit calls `scheduleAutosave()` explicitly as defence-in-depth against the no-op cell.resize edge case (WARNING 3).
- All Phase 12 place-text snap reads use `window.__sfd.viewport.snapEnabled` — standardized with Phase 11 CornerResize, Plan 03 pen-tool, and Plan 06 BoundaryVertex (WARNING 4).
- Text-side sticky-default closure vars (lastTextSize=16, lastTextColor='#000000') declared; will be mutated by Plan 05 inspector click handlers.
- All overlay style writes use setProperty(... 'important') per CLAUDE.md admin-CSS override rule.
- NO innerHTML assignment from user input (XSS audit).
- TextLabel cells persist through autosave round-trip via cell.resize → change:size catching at line 2403 + explicit scheduleAutosave fallback.
</must_haves>
</content>
</invoke>
