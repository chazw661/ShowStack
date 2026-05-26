---
phase: 12
plan_number: 03
wave: 2
depends_on: [01]
files_modified:
  - planner/templates/planner/signal_flow/editor.html
  - planner/static/planner/js/signal_flow_editor.js
autonomous: true
requirements_addressed: [DRAW-01, DRAW-02]
must_haves:
  truths:
    - "Toolbar contains a new .sfd-btn-group between #sfd-redo and the right-aligned spacer with two buttons: #sfd-tool-boundary and #sfd-tool-text"
    - "Clicking #sfd-tool-boundary enters sticky draw-boundary mode (per D-01)"
    - "While in draw mode, each blank:pointerdown adds a vertex; pointermove updates a live 'to cursor' SVG segment"
    - "Double-click commits the polyline with >=2 vertices; Esc commits if >=2 vertices else cancels (D-02, D-05)"
    - "Existing rubber-band selection is suppressed while draw mode is active (Risk #1 guard)"
    - "Pen-tool vertex placement is suppressed while spacebar pan is engaged (panState.spaceDown guard — WARNING 5)"
    - "Toolbar button receives .is-active + aria-pressed='true'; #sfd-paper cursor becomes 'crosshair' via setProperty(... 'important')"
    - "commitOrCancelBoundary creates a BoundaryLine cell with sticky-default color/style, calls applyBoundaryRender, and cell.toBack() for D-13 z-order"
    - "Snap-toggle reads from window.__sfd.viewport.snapEnabled (standardized source — matches Phase 11 CornerResize and Plan 06 BoundaryVertex)"
  artifacts:
    - path: "planner/templates/planner/signal_flow/editor.html"
      provides: "Toolbar create-tools button group with #sfd-tool-boundary + #sfd-tool-text"
      contains: 'id="sfd-tool-boundary"'
      contains_also: 'id="sfd-tool-text"'
    - path: "planner/static/planner/js/signal_flow_editor.js"
      provides: "drawState closure + enterBoundaryMode/exitBoundaryMode + pen-tool paper-event listeners + commitOrCancelBoundary + rubber-band guard + Esc keydown branch + sticky default closure vars (boundary-side)"
      contains: "var drawState = { active: false"
      contains_also: "function commitOrCancelBoundary"
  key_links:
    - from: "#sfd-tool-boundary click"
      to: "enterBoundaryMode()"
      via: "addEventListener('click', ...)"
      pattern: "enterBoundaryMode"
    - from: "paper blank:pointerdown while drawState.active"
      to: "drawState.vertices.push"
      via: "paper.on('blank:pointerdown', ...) gated on drawState.active"
      pattern: "drawState.vertices.push"
    - from: "commitOrCancelBoundary"
      to: "graph.addCell + applyBoundaryRender + cell.toBack"
      via: "new joint.shapes.showstack.BoundaryLine"
      pattern: "graph.addCell"
---

<objective>
Wire the toolbar create-tools button group into editor.html and implement the draw-boundary pen-tool state machine in signal_flow_editor.js: sticky mode entry/exit, vertex accumulation on blank:pointerdown, live "to cursor" segment on blank:pointermove, double-click + Esc commit/cancel paths, and the rubber-band early-exit guard (Risk #1). Also declares the boundary-side session-sticky defaults (`lastBoundaryColor`, `lastBoundaryStyle`). The text-mode counterpart lives in Plan 04; the inspector mode panels live in Plan 05; vertex-edit handles live in Plan 06.
</objective>

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| Rubber-band selection fires alongside the pen-tool's blank:pointerdown (Risk #1, Violation 2) | high (silent UX bug — selection rect appears under in-progress polyline) | Acceptance criterion: literal `if (drawState.active) return;` added as the FIRST executable line of the existing rubber-band handler at signal_flow_editor.js:1500-1501. |
| Paper cursor set without !important — Django admin overrides it (Violation 3) | medium | Acceptance criterion: `paperEl.style.setProperty('cursor', 'crosshair', 'important')` literal present; no `paperEl.style.cursor = ` shorthand assignments. |
| Esc keydown handler interleaving — picker-close / selection-clear / new draw exit (Risk #4, Violation 8) | medium | New Esc branch fires BEFORE existing selection-clear and calls `evt.preventDefault()`. Order verified by reading the inserted code and confirming the new branch precedes the existing block. |
| Pen-tool fires while spacebar-pan is engaged (WARNING 5) | medium | New `if (panState.spaceDown) return;` guard inside pen-tool blank:pointerdown — placed AFTER the `!drawState.active` early-exit and BEFORE the rest of the body. Mirrors the existing rubber-band handler at line 1501. |
| Snap-toggle source-of-truth divergence (WARNING 4) | low | All Phase 12 snap reads use `window.__sfd.viewport.snapEnabled` — matches Phase 11 CornerResize precedent and Plan 06 BoundaryVertex. |
| User-typed text in TextLabel (XSS) — N/A this plan; TextLabel inline edit lives in Plan 04. | n/a | n/a |
| Autosave wiring — `graph.on('add', scheduleAutosave)` at signal_flow_editor.js:2403 catches commitOrCancelBoundary's `graph.addCell` automatically. No explicit scheduleAutosave() call needed for the addCell path. | low | Verified by reading signal_flow_editor.js:2403 — the existing listener includes `'add'` in the comma-list. |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Insert create-tools button group into editor.html toolbar</name>
  <files>planner/templates/planner/signal_flow/editor.html</files>
  <read_first>
    - planner/templates/planner/signal_flow/editor.html lines 40-70 (entire #sfd-toolbar markup, including the 5 existing button groups + dividers + spacer)
    - planner/templates/planner/signal_flow/editor.html line 53 (#sfd-snap-toggle — the is-active + aria-pressed pattern to mirror)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md "HTML toolbar insertion" (lines 352-389 — verbatim block to insert)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-06 (lines 506-628 — confirms button IDs + initial aria-pressed="false")
  </read_first>
  <action>
    Locate the existing history group block ending with `</div>` and followed by `<span class="sfd-toolbar-spacer">`. Per RESEARCH/PATTERNS this is between lines 58 and 60 of editor.html. Confirm by reading: the closing `</div>` of the history group (`<div class="sfd-btn-group" data-group="history">`) should be on line ~59, and the next line should be `<span class="sfd-toolbar-spacer"></span>`.

    Insert the following lines AFTER the history group's `</div>` (line ~59) and BEFORE the `<span class="sfd-toolbar-spacer">` (line ~60). Preserve surrounding indentation (2 spaces inside the toolbar div):

    ```html
        <span class="sfd-toolbar-divider"></span>
        <div class="sfd-btn-group" data-group="create">
          <button type="button" id="sfd-tool-boundary" aria-label="Draw boundary" aria-pressed="false">&#x29C8;</button>
          <button type="button" id="sfd-tool-text"     aria-label="Place text"     aria-pressed="false">T</button>
        </div>
    ```

    Glyph choices: boundary uses Unicode U+29C8 (⧈ "Squared Or") which reads as a polyline/region glyph; text uses literal "T" (matches the convention of letter-on-button used by other compact toolbar systems). Initial `aria-pressed="false"` — JS flips to `"true"` on mode entry. Do NOT add `class="is-active"` in the template (it's added by JS at runtime).

    Do NOT modify any other line of editor.html. Do NOT add inline styles. Do NOT register on admin.site (irrelevant — Phase 12 has no admin work).
  </action>
  <verify>
    <automated>grep -n 'id="sfd-tool-boundary"' planner/templates/planner/signal_flow/editor.html && grep -n 'id="sfd-tool-text"' planner/templates/planner/signal_flow/editor.html && grep -n 'data-group="create"' planner/templates/planner/signal_flow/editor.html</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c 'id="sfd-tool-boundary"' planner/templates/planner/signal_flow/editor.html` returns exactly `1`
    - `grep -c 'id="sfd-tool-text"' planner/templates/planner/signal_flow/editor.html` returns exactly `1`
    - `grep -c 'data-group="create"' planner/templates/planner/signal_flow/editor.html` returns exactly `1`
    - Both new buttons carry `aria-pressed="false"` initially — verified by `grep -c 'aria-pressed="false"' planner/templates/planner/signal_flow/editor.html` returning at least `2` more than before the edit.
    - Both buttons sit inside a `<div class="sfd-btn-group" data-group="create">` — verified by reading the toolbar markup; the two `<button>` lines are siblings inside the same div.
    - Line number of `id="sfd-tool-boundary"` is GREATER than line number of `id="sfd-redo"` AND LESS than line number of `class="sfd-toolbar-spacer"` — confirms placement between history group and right-spacer per D-04.
    - Glyph for boundary is `&#x29C8;` (U+29C8); glyph for text is literal `T`.
    - Browser manual: load /audiopatch/signal-flow/<id>/edit/ — two new toolbar buttons visible between Undo/Redo and the export group. Hover tooltips show "Draw boundary" and "Place text".
  </acceptance_criteria>
  <done>Toolbar contains the create-tools button group with two new buttons at the correct insertion point; no JS handlers yet (Task 2 wires them).</done>
</task>

<task type="auto">
  <name>Task 2: Add drawState closure, enter/exit boundary mode, pen-tool paper-event listeners, commitOrCancelBoundary, sticky-default vars, Esc keydown branch, rubber-band guard</name>
  <files>planner/static/planner/js/signal_flow_editor.js</files>
  <read_first>
    - planner/static/planner/js/signal_flow_editor.js lines 1495-1545 (rubber-band-rect implementation — the pattern to clone for SVG live preview AND the file location of the guard insertion)
    - planner/static/planner/js/signal_flow_editor.js lines 1545-1600 (existing keydown handler — Esc branch insertion target)
    - planner/static/planner/js/signal_flow_editor.js lines 1717-1720 (in-tree comment confirming multiple blank:pointerdown listeners coexist)
    - planner/static/planner/js/signal_flow_editor.js lines 2255-2270 (closure-state block — `conflicted` / `diagramDirty` / `currentVersion` site for new sticky-default vars)
    - planner/static/planner/js/signal_flow_editor.js lines 2400-2415 (graph + paper autosave listener line — confirms `'add'` is in the comma-list so commitOrCancelBoundary's graph.addCell auto-triggers autosave)
    - planner/static/planner/js/signal_flow_editor.js (search for `window.__sfd.viewport.snapEnabled` — Phase 11 CornerResize uses this exact path; Plan 06 BoundaryVertex uses the same; standardize here too)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-06 (lines 506-628 — verbatim state machine + bodies)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-09 (lines 763-786 — sticky-default closure vars)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-10 (lines 790-820 — cell.toBack() for D-13)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md "Region C" (lines 127-193 — change directive + multi-listener confirmation)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md Violations 2, 3, 8 (lines 676-783 — Risk #1 guard, paper cursor !important, Esc handler ordering)
    - .planning/phases/12-boundaries-and-text/12-CONTEXT.md D-01..D-07 (sticky mode, click-each-vertex, snap rules, mode visual feedback)
    - CLAUDE.md "Overriding Django admin CSS from JavaScript" — paperEl.style.setProperty('cursor', ..., 'important') mandate.
  </read_first>
  <action>
    Five edits inside the existing IIFE in `planner/static/planner/js/signal_flow_editor.js`. All five are additive — do not remove existing code.

    **EDIT 1 — Declare boundary-side sticky-default closure vars.** Locate the closure-state block at signal_flow_editor.js:~2258 (the area containing `var conflicted = false;` / `var diagramDirty = false;` / `var currentVersion = ...`). Add immediately after those declarations (text-side vars are added by Plan 04):

    ```javascript
        // Phase 12 — session-sticky defaults for next-created boundary.
        // Closure-scoped; reset on page reload. Mutated BEFORE scheduleAutosave
        // per Plan 05 inspector-click handlers (Pattern Violation 1).
        var lastBoundaryColor = '#000000';    // D-09 initial — black
        var lastBoundaryStyle = 'solid';      // D-12 initial — solid
    ```

    **EDIT 2 — Add drawState closure + mode entry/exit helpers + commitOrCancelBoundary.** Find a stable insertion point inside the IIFE AFTER the existing keydown handler block (around signal_flow_editor.js:1600, after the existing Esc handling closes) and BEFORE the `paper.on('blank:pointerdown', ...)` rubber-band handler at line 1500. Specifically: insert the following block right BEFORE the rubber-band handler at line 1500, so the new `paper.on('blank:pointerdown', ...)` listener registered below registers AFTER the rubber-band one (multi-listener coexistence is verified at signal_flow_editor.js:1717-1720).

    Actually — JointJS emitter fires listeners in registration order; for the rubber-band early-exit guard (EDIT 4) to be the sole gate, the order of registration is irrelevant. Insert the block at the most readable location: AFTER `function detachResizeTools` (line ~619) and BEFORE the Console class (line 621). This places `drawState` + helpers in the same logical scope as the Phase 11 `attachResizeTools` helpers.

    ```javascript
      // ──────────────────────────────────────────────────────────────
      // Phase 12 — Pen-tool draw-boundary state machine (DRAW-01).
      // Sticky mode per D-01: enters on toolbar click, exits on Esc, re-click
      // of the boundary button, or click of the text-mode button. Click-each-
      // vertex per D-02. Snap-to-20px-grid when toggle is on per D-03.
      // ──────────────────────────────────────────────────────────────

      var drawState = {
        active: false,               // true while in draw-boundary mode
        vertices: [],                // [{x, y}, ...] accumulated since mode entry
        livePreview: null,           // SVG <polyline> showing placed vertices
        liveSegment: null,           // SVG <line> showing "to cursor" segment
      };

      function createPreviewPolyline() {
        var el = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
        el.setAttribute('fill', 'none');
        el.setAttribute('stroke', '#0d9488');
        el.setAttribute('stroke-width', '2');
        el.setAttribute('stroke-dasharray', '4 3');
        el.setAttribute('pointer-events', 'none');
        var vp = paper.viewport || paper.svg;
        if (vp && vp.appendChild) vp.appendChild(el);
        return el;
      }

      function createPreviewSegment() {
        var el = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        el.setAttribute('stroke', '#0d9488');
        el.setAttribute('stroke-width', '2');
        el.setAttribute('stroke-dasharray', '2 3');
        el.setAttribute('pointer-events', 'none');
        el.setAttribute('x1', '0'); el.setAttribute('y1', '0');
        el.setAttribute('x2', '0'); el.setAttribute('y2', '0');
        var vp = paper.viewport || paper.svg;
        if (vp && vp.appendChild) vp.appendChild(el);
        return el;
      }

      function updatePreviewPolyline() {
        if (!drawState.livePreview) return;
        var pts = drawState.vertices.map(function (v) { return v.x + ',' + v.y; }).join(' ');
        drawState.livePreview.setAttribute('points', pts);
      }

      function enterBoundaryMode() {
        // D-01 — if text mode is active, exit it (handoff to Plan 04's exitTextMode).
        if (typeof exitTextMode === 'function' && typeof textModeActive !== 'undefined' && textModeActive) {
          exitTextMode();
        }
        drawState.active = true;
        drawState.vertices = [];
        drawState.livePreview = createPreviewPolyline();
        drawState.liveSegment = createPreviewSegment();

        var btn = document.getElementById('sfd-tool-boundary');
        if (btn) {
          btn.classList.add('is-active');
          btn.setAttribute('aria-pressed', 'true');
        }
        // D-07 — cursor change MUST use setProperty(... 'important') per CLAUDE.md.
        var paperEl = document.getElementById('sfd-paper');
        if (paperEl) paperEl.style.setProperty('cursor', 'crosshair', 'important');
      }

      function exitBoundaryMode() {
        drawState.active = false;
        drawState.vertices = [];
        if (drawState.livePreview && drawState.livePreview.parentNode) {
          drawState.livePreview.parentNode.removeChild(drawState.livePreview);
        }
        if (drawState.liveSegment && drawState.liveSegment.parentNode) {
          drawState.liveSegment.parentNode.removeChild(drawState.liveSegment);
        }
        drawState.livePreview = null;
        drawState.liveSegment = null;

        var btn = document.getElementById('sfd-tool-boundary');
        if (btn) {
          btn.classList.remove('is-active');
          btn.setAttribute('aria-pressed', 'false');
        }
        var paperEl = document.getElementById('sfd-paper');
        // Empty string clears the inline cursor; CSS-defined default cursor resumes.
        if (paperEl) paperEl.style.setProperty('cursor', '', 'important');
      }

      function commitOrCancelBoundary() {
        if (drawState.vertices.length < 2) {
          // D-02 — single vertex or zero = no polyline created.
          drawState.vertices = [];
          updatePreviewPolyline();
          return;
        }
        var cell = new joint.shapes.showstack.BoundaryLine({
          vertices: drawState.vertices.slice(),
          color: lastBoundaryColor || '#000000',
          lineStyle: lastBoundaryStyle || 'solid',
        });
        graph.addCell(cell);
        applyBoundaryRender(cell);
        cell.toBack();                       // D-13 — behind shapes/connectors
        drawState.vertices = [];
        updatePreviewPolyline();
        // Sticky mode stays active per D-01 — engineer can immediately draw the next.
        // graph.addCell auto-triggers scheduleAutosave via the line-2403 'add' listener.
      }
    ```

    **EDIT 3 — Wire the toolbar button click + register paper pen-tool listeners.** Locate the existing toolbar wiring block (search for `document.getElementById('sfd-snap-toggle')` — the snap-toggle wiring; the existing toolbar click handlers are clustered there, typically around signal_flow_editor.js:1000-1100). Insert the following block at the SAME nesting level as the snap-toggle handler (inside the IIFE, after any existing toolbar wiring):

    ```javascript
      // Phase 12 — Toolbar wiring: draw-boundary mode toggle (D-01 sticky).
      var toolBoundaryBtn = document.getElementById('sfd-tool-boundary');
      if (toolBoundaryBtn) {
        toolBoundaryBtn.addEventListener('click', function () {
          if (drawState.active) {
            exitBoundaryMode();             // re-click exits per D-01
          } else {
            enterBoundaryMode();
          }
        });
      }

      // Pen-tool vertex placement — only fires when drawState.active is true.
      // Rubber-band listener at signal_flow_editor.js:1500 has its own
      // `if (drawState.active) return;` guard (EDIT 4 below) so both
      // listeners coexist safely (multi-listener pattern verified at
      // signal_flow_editor.js:1717-1720).
      paper.on('blank:pointerdown', function (evt, x, y) {
        if (!drawState.active) return;
        if (panState.spaceDown) return;        // WARNING 5 — spacebar pan trumps pen-tool
        var pt = { x: x, y: y };
        if (window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled) {
          pt.x = Math.round(pt.x / 20) * 20;
          pt.y = Math.round(pt.y / 20) * 20;
        }
        drawState.vertices.push(pt);
        updatePreviewPolyline();
      });

      // Live "to cursor" segment — refresh on every move while drawing.
      paper.on('blank:pointermove', function (evt, x, y) {
        if (!drawState.active) return;
        if (!drawState.vertices.length) return;
        var last = drawState.vertices[drawState.vertices.length - 1];
        var pt = { x: x, y: y };
        if (window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled) {
          pt.x = Math.round(pt.x / 20) * 20;
          pt.y = Math.round(pt.y / 20) * 20;
        }
        if (!drawState.liveSegment) return;
        drawState.liveSegment.setAttribute('x1', String(last.x));
        drawState.liveSegment.setAttribute('y1', String(last.y));
        drawState.liveSegment.setAttribute('x2', String(pt.x));
        drawState.liveSegment.setAttribute('y2', String(pt.y));
      });

      // Double-click commits (D-02).
      paper.on('blank:pointerdblclick', function (/* evt, x, y */) {
        if (!drawState.active) return;
        commitOrCancelBoundary();
      });
    ```

    **EDIT 4 — Add rubber-band early-exit guard (Risk #1, Violation 2 — the most-likely-forgotten edit).** Locate the existing rubber-band-rect handler at signal_flow_editor.js:~1500. It begins:

    ```javascript
    paper.on('blank:pointerdown', function (evt, x, y) {
      if (panState.spaceDown || evt.button !== 0) return;
      ...
    });
    ```

    Insert a new first executable line (immediately after the function-arg list opens), so the handler reads:

    ```javascript
    paper.on('blank:pointerdown', function (evt, x, y) {
      if (drawState.active) return;                              // Phase 12 — Risk #1 guard
      if (panState.spaceDown || evt.button !== 0) return;
      ...
    });
    ```

    Do NOT remove the existing `if (panState.spaceDown ...)` line. Both early-exits must be present. Plan 04 will insert a `textModeActive` guard between these two lines.

    **EDIT 5 — Extend the Esc keydown branch.** Locate the existing keydown handler at signal_flow_editor.js:~1549 (search for `document.addEventListener('keydown'` — there may be multiple; use the one that handles Esc for selection-clear / picker-close). At the very TOP of that handler's body (after any INPUT/TEXTAREA/SELECT early-exit but BEFORE the existing Esc selection-clear logic), insert:

    ```javascript
        // Phase 12 — Esc commits or cancels boundary draw mode (D-02, D-05).
        // Order: this branch fires BEFORE the existing selection-clear so a
        // mid-polyline Esc doesn't accidentally clear selection too (Violation 8).
        if (evt.key === 'Escape' && drawState.active) {
          evt.preventDefault();
          commitOrCancelBoundary();
          exitBoundaryMode();
          return;
        }
    ```

    Place this branch AFTER the existing `if (/INPUT|TEXTAREA|SELECT/.test(evt.target.tagName))` early-exit (if present), so the Esc-in-input case is still handled by Plan 04's text-edit-overlay logic when that lands. Place it BEFORE any other `if (evt.key === 'Escape')` block currently in the handler.

    Do NOT add `change:vertices` to the comma-separated event list at signal_flow_editor.js:2403 — Plan 06 adds it as a standalone listener (Violation 5). This plan touches the autosave listener line in no way.
  </action>
  <verify>
    <automated>grep -n "var drawState = {" planner/static/planner/js/signal_flow_editor.js && grep -n "function enterBoundaryMode" planner/static/planner/js/signal_flow_editor.js && grep -n "function exitBoundaryMode" planner/static/planner/js/signal_flow_editor.js && grep -n "function commitOrCancelBoundary" planner/static/planner/js/signal_flow_editor.js && grep -n "if (drawState.active) return;" planner/static/planner/js/signal_flow_editor.js && grep -n "var lastBoundaryColor = '#000000'" planner/static/planner/js/signal_flow_editor.js && grep -n "var lastBoundaryStyle = 'solid'" planner/static/planner/js/signal_flow_editor.js && grep -n "paperEl.style.setProperty('cursor', 'crosshair', 'important')" planner/static/planner/js/signal_flow_editor.js && grep -n "window.__sfd.viewport.snapEnabled" planner/static/planner/js/signal_flow_editor.js</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "var drawState = {" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function enterBoundaryMode" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function exitBoundaryMode" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function commitOrCancelBoundary" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "if (drawState.active) return;" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `4` (rubber-band guard at line 1500 + 3 pen-tool listener guards inside the new handlers — pointerdown, pointermove, pointerdblclick)
    - `grep -c "var lastBoundaryColor = '#000000'" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var lastBoundaryStyle = 'solid'" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "paperEl.style.setProperty('cursor', 'crosshair', 'important')" planner/static/planner/js/signal_flow_editor.js` returns exactly `1` (enter mode)
    - `grep -c "paperEl.style.setProperty('cursor', '', 'important')" planner/static/planner/js/signal_flow_editor.js` returns exactly `1` (exit mode)
    - **WARNING 4 — standardized snap-toggle source-of-truth.** Pen-tool snap reads use `window.__sfd.viewport.snapEnabled` (NOT `currentViewport.snapEnabled`). Verified by `grep -c "window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled" planner/static/planner/js/signal_flow_editor.js` returning AT LEAST `2` (pen-tool blank:pointerdown + blank:pointermove). After Plan 06 lands, the total `window.__sfd.viewport.snapEnabled` count across the file should be AT LEAST `3` (Phase 11 CornerResize + 2 Phase 12 pen-tool sites; Plan 04 adds one more; Plan 06 adds one more).
    - **WARNING 4 — no currentViewport.snapEnabled usage in pen-tool.** The literal `currentViewport.snapEnabled` MUST NOT appear inside the new pen-tool blank:pointerdown or blank:pointermove handlers. Verify by reading the new handler bodies — if a pre-existing `currentViewport.snapEnabled` reference exists elsewhere in the file (e.g., a Phase 8 or Phase 9 helper), leave it; this rule applies only to NEW Phase 12 code.
    - **WARNING 5 — pen-tool spacebar-pan guard.** The pen-tool blank:pointerdown body contains `if (panState.spaceDown) return;` as the SECOND executable line (after `if (!drawState.active) return;` and BEFORE the snap branch). Verified by `grep -B 2 -A 4 "drawState.vertices.push(pt);" planner/static/planner/js/signal_flow_editor.js | grep -c "if (panState.spaceDown) return;"` returning AT LEAST `1`.
    - The Esc keydown branch contains the literal pattern `if (evt.key === 'Escape' && drawState.active)` — verified by `grep -c "if (evt.key === 'Escape' && drawState.active)" planner/static/planner/js/signal_flow_editor.js` returning `1`.
    - `commitOrCancelBoundary` body contains the literal vertex-count guard `if (drawState.vertices.length < 2)` — verified by `grep -c "if (drawState.vertices.length < 2)" planner/static/planner/js/signal_flow_editor.js` returning `1`.
    - `commitOrCancelBoundary` calls `applyBoundaryRender(cell)` AND `cell.toBack()` — verified by `grep -c "applyBoundaryRender(cell)" planner/static/planner/js/signal_flow_editor.js` returning AT LEAST `1` and `grep -c "cell.toBack()" planner/static/planner/js/signal_flow_editor.js` returning AT LEAST `1` (Plan 04 will add toFront, not toBack).
    - The new commitOrCancelBoundary uses `new joint.shapes.showstack.BoundaryLine` — verified by `grep -c "new joint.shapes.showstack.BoundaryLine" planner/static/planner/js/signal_flow_editor.js` returning AT LEAST `1`.
    - The rubber-band-rect handler at line ~1500 begins with `paper.on('blank:pointerdown'` and its first executable line is now `if (drawState.active) return;` — verified by reading the handler body. The next line must still be the existing `if (panState.spaceDown || evt.button !== 0) return;` (Plan 04 will insert a `textModeActive` guard between them).
    - Browser manual: load editor, click "Draw boundary" button — button gets teal active-state; cursor over the paper changes to crosshair. Click 3 points on the canvas — vertices accumulate as a teal dashed polyline preview. Double-click — preview commits as a solid black polyline (color comes from sticky default; line-style picker lives in Plan 05). Click "Draw boundary" again — mode exits, cursor returns to default. Repeat: click button, click 1 vertex, press Esc — no polyline created (vertex count < 2 cancel). Repeat: click button, click 3 vertices, press Esc — polyline commits and mode exits.
    - Browser manual: with draw mode OFF, drag on blank canvas — rubber-band selection rect appears as before (no regression from the guard).
    - Browser manual: in draw mode, hold spacebar — cursor changes to grab; click on canvas — NO vertex added (WARNING 5). Release spacebar — clicks add vertices again.
    - Browser manual: refresh the page after drawing a boundary — the boundary persists (autosave-via-graph-add fires; canvas_state round-trips because BoundaryLine is registered per Plan 01 and the server treats canvas_state as opaque per R-04).
  </acceptance_criteria>
  <done>Toolbar create-tools group inserted; drawState + enterBoundaryMode/exitBoundaryMode/commitOrCancelBoundary + paper pen-tool listeners + Esc Branch + rubber-band guard + panState.spaceDown guard + boundary-side sticky-default vars all present, snap-toggle reads from window.__sfd.viewport.snapEnabled. Drawing a 3-vertex polyline, double-clicking, and refreshing the page persists the boundary.</done>
</task>

</tasks>

<verification>
- `grep -n "id=\"sfd-tool-boundary\"\\|id=\"sfd-tool-text\"\\|data-group=\"create\"" planner/templates/planner/signal_flow/editor.html` — expect 3 hits.
- `grep -n "drawState\\|enterBoundaryMode\\|exitBoundaryMode\\|commitOrCancelBoundary\\|lastBoundaryColor\\|lastBoundaryStyle" planner/static/planner/js/signal_flow_editor.js` — expect at least 10 hits spread across the IIFE.
- `grep -c "if (drawState.active) return;" planner/static/planner/js/signal_flow_editor.js` — expect AT LEAST 4 (rubber-band guard + 3 pen-tool listeners).
- `grep -c "window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled" planner/static/planner/js/signal_flow_editor.js` — expect AT LEAST 2 (pen-tool pointerdown + pointermove; standardized per WARNING 4).
- Browser UAT — draw a 4-vertex boundary, refresh the page, the boundary persists. This is the critical autosave round-trip verification for DRAW-01.
- Browser UAT — rubber-band selection still works when draw mode is off (Risk #1 regression check).
- Browser UAT — spacebar+click in draw mode pans WITHOUT placing a vertex (WARNING 5 regression check).
</verification>

<must_haves>
- Toolbar create-tools button group exists with two buttons (#sfd-tool-boundary, #sfd-tool-text) — DRAW-01 + TXT-01 share toolbar real estate.
- Clicking #sfd-tool-boundary toggles draw mode; mode is sticky per D-01.
- While drawing: blank:pointerdown adds vertex (snapped if snap toggle is on per D-03), blank:pointermove updates the live "to cursor" segment, blank:pointerdblclick commits per D-02.
- Pen-tool blank:pointerdown contains a `panState.spaceDown` early-exit so spacebar+click pans WITHOUT placing a vertex (WARNING 5).
- All Phase 12 pen-tool snap reads use `window.__sfd.viewport.snapEnabled` — standardized with Phase 11 CornerResize and Plan 06 BoundaryVertex (WARNING 4).
- Esc inside draw mode commits with ≥2 vertices, cancels with <2 vertices, always exits mode (D-02 + D-05).
- Toolbar button gets .is-active + aria-pressed="true" while active; cursor becomes crosshair via setProperty(..., 'important') per D-07.
- commitOrCancelBoundary creates a BoundaryLine cell with sticky-default color + style, calls applyBoundaryRender, calls cell.toBack() per D-13.
- Rubber-band selection is suppressed while drawing (Risk #1 guard at line 1500).
- Boundary-side sticky-default closure vars (lastBoundaryColor, lastBoundaryStyle) declared; will be mutated by Plan 05 inspector click handlers BEFORE scheduleAutosave per Violation 1.
- BoundaryLine cells persist through autosave round-trip (graph.addCell triggers the existing line-2403 listener with 'add' in its comma-list — no special-case wiring needed).
</must_haves>
</content>
</invoke>