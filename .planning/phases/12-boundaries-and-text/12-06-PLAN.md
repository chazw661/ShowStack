---
phase: 12
plan_number: 06
wave: 5
depends_on: [01, 03, 04, 05]
files_modified:
  - planner/static/planner/js/signal_flow_editor.js
autonomous: true
requirements_addressed: [DRAW-04, TXT-03]
must_haves:
  truths:
    - "BoundaryVertex elementTools.Control subclass exists with vertexIndex option, getPosition reading cell.prop('vertices')[idx], setPosition writing a SLICED copy of the vertices array back via cell.prop('vertices', verts)"
    - "BoundaryVertex visible handle is a teal #0d9488 circle r=6 (per D-06); hit-area is a second transparent circle r=12 (Claude's Discretion)"
    - "BoundaryVertex.setPosition snaps to 20px grid via window.__sfd.viewport.snapEnabled (Phase 8 D-13 parity; WARNING 4 standardized source — Plans 03 + 04 now read the same expression for pen-tool and place-text snap)"
    - "attachBoundaryVertexTools(cell) installs one BoundaryVertex per vertex via view.addTools(new joint.dia.ToolsView(...))"
    - "graph.on('change:vertices', ...) is a STANDALONE listener (NOT added to the line-2403 comma-list per Violation 5); on change it calls applyBoundaryRender + view.updateTools + scheduleAutosave"
    - "onSelectionChanged extension adds two new branches BEFORE the existing isElement branch: BoundaryLine → setInspectorMode('boundary', cell) + attachBoundaryVertexTools; TextLabel → setInspectorMode('text', cell)"
    - "Selection deselect of boundary calls view.removeTools() to remove vertex handles"
  artifacts:
    - path: "planner/static/planner/js/signal_flow_editor.js"
      provides: "BoundaryVertex class + attachBoundaryVertexTools + detachBoundaryVertexTools + graph.on('change:vertices', ...) standalone listener + onSelectionChanged extension for BoundaryLine/TextLabel"
      contains: "var BoundaryVertex = joint.elementTools.Control.extend("
      contains_also: "function attachBoundaryVertexTools"
  key_links:
    - from: "selection of a BoundaryLine cell"
      to: "setInspectorMode('boundary', cell) + attachBoundaryVertexTools(cell)"
      via: "onSelectionChanged branch"
      pattern: "setInspectorMode\\('boundary'"
    - from: "vertex drag (BoundaryVertex.setPosition)"
      to: "applyBoundaryRender + view.updateTools + scheduleAutosave"
      via: "graph.on('change:vertices', ...) standalone listener"
      pattern: "graph.on\\('change:vertices'"
---

<objective>
Implement the vertex-edit-handle tool (`BoundaryVertex` `joint.elementTools.Control` subclass) and wire selection events so selecting a BoundaryLine cell installs per-vertex handles + opens the boundary inspector, and selecting a TextLabel cell opens the text inspector. Adds the standalone `graph.on('change:vertices', ...)` listener that re-renders + refreshes tools + calls `scheduleAutosave()` explicitly (Violation 5 — do NOT add to the existing line-2403 comma-list). This plan closes DRAW-04 (vertex drag reshape) and TXT-03 (selection → inspector + Delete/Backspace inherits from existing handler).
</objective>

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| `change:vertices` infinite loop (Violation 5) | high | Standalone `graph.on('change:vertices', function(cell) { ... })` listener that explicitly calls `scheduleAutosave()` — NOT added to the comma-separated event list at signal_flow_editor.js:2403. Acceptance criterion: line-2403 listener event-string is unchanged (no `change:vertices` in the comma list). |
| Vertex array mutation by reference (Violation 7) | high | `setPosition` MUST call `.slice()` on `cell.prop('vertices')` before mutating. Acceptance criterion: `BoundaryVertex.setPosition` body contains literal `.slice()` on the prop read. |
| Selection wiring leaks across cell types | medium | The new `onSelectionChanged` branches null-out the inspector trackers for the other mode (per Plan 05's branches handling this in setInspectorMode), AND call `view.removeTools()` for any previously-attached resize / vertex tools before attaching the new ones. Acceptance criterion: tracker `_vertexAttachedCell` is updated on attach and `detachBoundaryVertexTools` is called on deselect. |
| Delete/Backspace not honoring boundary/text cells | low | The existing Delete/Backspace handler at signal_flow_editor.js:~1549 calls `cell.remove()` on selected cells via the same selection state used by all other shapes. BoundaryLine and TextLabel inherit this for free as standard JointJS elements. No code change needed — verified by reading the handler. |
| Vertex hit-target too small (UX) | low | Hit-area is a second transparent SVG circle with r=12 (12px hit radius). The visible handle is r=6 (6px visible). Mirrors Phase 11 CornerResize 10px-visible / SVG-rect-bounds hit-target approach. |
| `validateMagnet` accepts vertex handles as connector endpoints | low | BoundaryVertex children carry no `magnet` attribute. validateMagnet (signal_flow_editor.js:792) returns false on falsy magnet. Verified by R-05. |
| Snap-toggle source-of-truth divergence (WARNING 4) | low | This plan is the canonical reference for `window.__sfd.viewport.snapEnabled` — matches Phase 11 CornerResize precedent. Plans 03 (pen-tool) and 04 (place-text) have been revised to read the SAME expression (standardized at planner revision time). Acceptance criterion: across the full file, `grep -c "window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled"` returns AT LEAST `4` (Plan 03 pen-tool pointerdown + pointermove + Plan 04 place-text pointerdown + this plan's BoundaryVertex.setPosition) — confirming all four Phase 12 snap-aware sites use the standardized form. |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Add BoundaryVertex elementTools.Control subclass + attachBoundaryVertexTools + detachBoundaryVertexTools + standalone change:vertices listener</name>
  <files>planner/static/planner/js/signal_flow_editor.js</files>
  <read_first>
    - planner/static/planner/js/signal_flow_editor.js lines 537-613 (Phase 11 CornerResize subclass + attachResizeTools/detachResizeTools — the exact template to clone)
    - planner/static/planner/js/signal_flow_editor.js lines 2395-2415 (Phase 9/11 autosave listener block — confirm `change:vertices` is NOT in the existing comma-list; Plan 06 adds it as a STANDALONE listener)
    - planner/static/planner/js/signal_flow_editor.js (find `window.__sfd.viewport.snapEnabled` references — the snap toggle source-of-truth used by CornerResize.setPosition AND Phase 12 Plans 03 + 04 after revision)
    - planner/static/planner/js/signal_flow_editor.js (find `applyBoundaryRender` from Plan 01 — this listener calls it)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-03 (lines 314-446 — verbatim BoundaryVertex + attachBoundaryVertexTools + change:vertices listener)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md "Region B" (lines 81-124 — change directive)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md Violations 5, 7 (lines 717-758 — listener placement + slice-then-mutate)
    - .planning/phases/12-boundaries-and-text/12-CONTEXT.md D-06 (teal #0d9488 vertex handles, visible 6px, hit 12px)
  </read_first>
  <action>
    Two additive edits to `planner/static/planner/js/signal_flow_editor.js`.

    **EDIT 1 — Add BoundaryVertex subclass + attach/detach helpers.** Locate the Phase 11 `CornerResize` class (signal_flow_editor.js:~537) and its `attachResizeTools` / `detachResizeTools` helpers (~599-619). Find the closing brace of `detachResizeTools`. Insert AFTER it the following block:

    ```javascript
      // ──────────────────────────────────────────────────────────────
      // Phase 12 — Boundary vertex-edit handle (DRAW-04).
      // Per-vertex circular handle in teal #0d9488 (matches Phase 11 D-05 corner-resize
      // handle language). Visible 6px circle + transparent 12px hit-area sibling
      // (Claude's Discretion). Snap-to-20px-grid via window.__sfd.viewport.snapEnabled
      // (WARNING 4 — same expression Plans 03 + 04 read for their snap branches).
      // ──────────────────────────────────────────────────────────────

      var BoundaryVertex = joint.elementTools.Control.extend({
        children: [{
          tagName: 'circle',
          selector: 'handle',
          attributes: {
            r: 6,                                  // D-06 visible radius
            fill: '#0d9488',                       // teal — Phase 11 D-05 parity
            stroke: '#fff',
            'stroke-width': 1,
            cursor: 'move',
          }
        }, {
          tagName: 'circle',
          selector: 'hitArea',
          attributes: {
            r: 12,                                 // 12px hit-target (Claude's Discretion)
            fill: 'transparent',
            cursor: 'move',
          }
        }],

        getPosition: function (view) {
          var verts = view.model.prop('vertices') || [];
          var v = verts[this.options.vertexIndex];
          return v ? { x: v.x, y: v.y } : { x: 0, y: 0 };
        },

        setPosition: function (view, coordinates) {
          var model = view.model;
          var idx = this.options.vertexIndex;
          // Violation 7 — .slice() COPY of the live array before mutation.
          var verts = (model.prop('vertices') || []).slice();
          var newX = coordinates.x;
          var newY = coordinates.y;
          // Same snap rule as Phase 11 CornerResize.setPosition (D-03 + Phase 8 D-13).
          // WARNING 4 — Plans 03 + 04 (pen-tool, place-text) use the SAME expression.
          if (window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled) {
            newX = Math.round(newX / 20) * 20;
            newY = Math.round(newY / 20) * 20;
          }
          verts[idx] = { x: newX, y: newY };
          model.prop('vertices', verts);
          // The graph.on('change:vertices', ...) listener below re-renders + refreshes tools
          // + calls scheduleAutosave. Do NOT call applyBoundaryRender here (avoid double-render).
        }
      });

      // Per-boundary attach — installs one BoundaryVertex per vertex via a ToolsView.
      // Mirror of Phase 11 attachResizeTools at signal_flow_editor.js:599.
      var _vertexAttachedCell = null;          // tracker (parallel to Phase 11 _resizeAttachedCell)

      function attachBoundaryVertexTools(cell) {
        if (!cell || !cell.findView) return;
        if (cell.get('type') !== 'showstack.BoundaryLine') return;
        var view = cell.findView(paper);
        if (!view) return;
        view.removeTools();                    // clear any prior tools
        var verts = cell.prop('vertices') || [];
        var tools = verts.map(function (_, i) {
          return new BoundaryVertex({ vertexIndex: i });
        });
        view.addTools(new joint.dia.ToolsView({
          name: 'sfd-boundary-vertices',
          tools: tools,
        }));
        _vertexAttachedCell = cell;
      }

      function detachBoundaryVertexTools(cell) {
        if (!cell || !cell.findView) return;
        var view = cell.findView(paper);
        if (view) view.removeTools();
        if (_vertexAttachedCell === cell) _vertexAttachedCell = null;
      }
    ```

    **EDIT 2 — Add standalone change:vertices listener.** Locate the Phase 9/11 autosave listener block at signal_flow_editor.js:~2401-2415 (look for `graph.on('add remove change:source change:target change:size', scheduleAutosave);`). Insert AFTER that line (NOT modifying the comma-list — Violation 5):

    ```javascript
      // Phase 12 — Standalone change:vertices listener (Violation 5).
      // Do NOT extend the line-2403 comma-list — naïve listening with applyBoundaryRender
      // write-back could re-fire change events. Explicit listener gives us deterministic
      // re-render + tool refresh + autosave call.
      graph.on('change:vertices', function (cell) {
        if (cell.get('type') !== 'showstack.BoundaryLine') return;
        applyBoundaryRender(cell);
        var view = cell.findView(paper);
        if (view) view.updateTools();
        scheduleAutosave();
      });
    ```

    Do NOT remove or modify the existing line-2403 listener. The new listener is a SECOND `graph.on(...)` call — JointJS supports multiple listeners per event.
  </action>
  <verify>
    <automated>grep -n "var BoundaryVertex = joint.elementTools.Control.extend(" planner/static/planner/js/signal_flow_editor.js && grep -n "function attachBoundaryVertexTools" planner/static/planner/js/signal_flow_editor.js && grep -n "function detachBoundaryVertexTools" planner/static/planner/js/signal_flow_editor.js && grep -n "graph.on('change:vertices'" planner/static/planner/js/signal_flow_editor.js && grep -n "var _vertexAttachedCell = null" planner/static/planner/js/signal_flow_editor.js && grep -n "window.__sfd.viewport.snapEnabled" planner/static/planner/js/signal_flow_editor.js</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "var BoundaryVertex = joint.elementTools.Control.extend(" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function attachBoundaryVertexTools" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function detachBoundaryVertexTools" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "graph.on('change:vertices'" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "var _vertexAttachedCell = null" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - **Violation 5 check — line-2403 listener event-string DOES NOT contain `change:vertices`.** Verified by `grep -n "graph.on('add remove change:source change:target change:size'" planner/static/planner/js/signal_flow_editor.js` returning the existing listener as-is (no Phase 12 extension). A second hit `grep -nc "graph.on('add remove change:source change:target change:size change:vertices'" planner/static/planner/js/signal_flow_editor.js` MUST return `0`.
    - **Violation 7 check — BoundaryVertex.setPosition uses .slice() COPY.** Verified by reading the function body: the line `var verts = (model.prop('vertices') || []).slice();` is present. `grep -c "(model.prop('vertices') || \\[\\]).slice()" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`.
    - The visible handle child has `r: 6` and `fill: '#0d9488'` (D-06 + Phase 11 D-05 parity).
    - The hit-area child has `r: 12` and `fill: 'transparent'`.
    - `setPosition` snap branch checks `window.__sfd.viewport.snapEnabled` — verified by `grep -c "window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled" planner/static/planner/js/signal_flow_editor.js` returning AT LEAST `4` (Plan 03 pen-tool pointerdown + Plan 03 pen-tool pointermove + Plan 04 place-text pointerdown + this BoundaryVertex.setPosition — WARNING 4 standardization complete).
    - The change:vertices listener body contains `applyBoundaryRender(cell)` + `view.updateTools()` + `scheduleAutosave()` in that order.
    - The change:vertices listener has the type-guard `if (cell.get('type') !== 'showstack.BoundaryLine') return;` — verified by grep.
    - `attachBoundaryVertexTools` calls `view.removeTools()` BEFORE adding new tools (prevents duplicate handles when re-selecting the same cell).
    - `attachBoundaryVertexTools` creates a `joint.dia.ToolsView` with `name: 'sfd-boundary-vertices'`.
  </acceptance_criteria>
  <done>BoundaryVertex subclass + attach/detach helpers + standalone change:vertices listener all present, correctly slicing the vertices array before mutation, snapping via the shared (WARNING 4 standardized) snapEnabled flag, and never duplicating tools on re-select.</done>
</task>

<task type="auto">
  <name>Task 2: Extend onSelectionChanged with BoundaryLine + TextLabel branches; hook detach on deselect</name>
  <files>planner/static/planner/js/signal_flow_editor.js</files>
  <read_first>
    - planner/static/planner/js/signal_flow_editor.js lines 1855-1900 (existing onSelectionChanged — search for `function onSelectionChanged` or `window.__sfd.onSelectionChanged`)
    - planner/static/planner/js/signal_flow_editor.js (find `_resizeAttachedCell` and how Phase 11 `attachResizeTools` is invoked from onSelectionChanged — the new BoundaryVertex attach mirrors this exact pattern)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-03 (lines 425-445 — verbatim onSelectionChanged extension)
    - .planning/phases/12-boundaries-and-text/12-CONTEXT.md D-17 (single-click selects only — does NOT enter edit mode; double-click re-enters edit, handled by Plan 04)
  </read_first>
  <action>
    Two additive edits to `planner/static/planner/js/signal_flow_editor.js`.

    **EDIT 1 — Add BoundaryLine + TextLabel branches at the TOP of onSelectionChanged.** Locate the existing `onSelectionChanged` function (or `window.__sfd.onSelectionChanged` if exposed externally). Find the existing `if (cell ... isLink)` / `if (cell ... isElement)` branches.

    Insert the following TWO branches BEFORE the existing isLink / isElement branches but AFTER any null-cell guard at the top of the function:

    ```javascript
        // Phase 12 — Boundary selection branch (DRAW-03, DRAW-04).
        if (cell && cell.get && cell.get('type') === 'showstack.BoundaryLine') {
          // Clean up any prior resize / vertex tools from a different selection.
          if (typeof _resizeAttachedCell !== 'undefined' && _resizeAttachedCell) {
            if (typeof detachResizeTools === 'function') detachResizeTools(_resizeAttachedCell);
            _resizeAttachedCell = null;
          }
          if (_vertexAttachedCell && _vertexAttachedCell !== cell) {
            detachBoundaryVertexTools(_vertexAttachedCell);
          }
          setInspectorMode('boundary', cell);
          if (typeof showInspector === 'function') showInspector();
          attachBoundaryVertexTools(cell);
          return;
        }

        // Phase 12 — Text selection branch (TXT-03 selection-only; dblclick edit lives in Plan 04).
        if (cell && cell.get && cell.get('type') === 'showstack.TextLabel') {
          if (typeof _resizeAttachedCell !== 'undefined' && _resizeAttachedCell) {
            if (typeof detachResizeTools === 'function') detachResizeTools(_resizeAttachedCell);
            _resizeAttachedCell = null;
          }
          if (_vertexAttachedCell) {
            detachBoundaryVertexTools(_vertexAttachedCell);
          }
          setInspectorMode('text', cell);
          if (typeof showInspector === 'function') showInspector();
          // Text labels get no tools — drag is handled by JointJS native cell-move
          // on the hitArea rect declared in Plan 01.
          return;
        }
    ```

    **EDIT 2 — Add detach-on-deselect cleanup.** In the same `onSelectionChanged` function, locate the existing branch that handles "no cell selected" (null cell / empty selection) — typically at the END of the function or at the very TOP guarded by `if (!cell)`. Inside that null-branch (or add one if missing), ensure the following lines fire BEFORE any inspector-hide logic:

    ```javascript
        // Phase 12 — detach vertex tools when selection clears or moves to a non-boundary.
        if (_vertexAttachedCell) {
          detachBoundaryVertexTools(_vertexAttachedCell);
          _vertexAttachedCell = null;
        }
    ```

    Also, inside the existing isLink and isElement branches (the non-Phase-12 branches that the new branches sit BEFORE), add the same detach lines at their top so that selecting a regular shape after a boundary correctly removes the vertex handles. Search for the existing branch heads (e.g., `if (cell && cell.isLink && cell.isLink())` or `if (cell && cell.isElement && cell.isElement())`) and insert the same detach block as the FIRST statement inside each.

    If a generic "clear all selection visuals" helper exists in onSelectionChanged (e.g., `clearSelectionTools()`), extend that helper with the detachBoundaryVertexTools call instead. Otherwise repeat the 4-line block at each call site.

    Do NOT modify the existing connector or node setInspectorMode branches that Plan 05 already updated to hide boundaryModeBlock + textModeBlock. Those branches use the same paths and are already correctly extended.
  </action>
  <verify>
    <automated>grep -n "cell.get('type') === 'showstack.BoundaryLine'" planner/static/planner/js/signal_flow_editor.js && grep -n "cell.get('type') === 'showstack.TextLabel'" planner/static/planner/js/signal_flow_editor.js && grep -n "setInspectorMode('boundary'" planner/static/planner/js/signal_flow_editor.js && grep -n "setInspectorMode('text'" planner/static/planner/js/signal_flow_editor.js && grep -n "attachBoundaryVertexTools(cell)" planner/static/planner/js/signal_flow_editor.js && grep -n "detachBoundaryVertexTools(_vertexAttachedCell)" planner/static/planner/js/signal_flow_editor.js</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "cell.get('type') === 'showstack.BoundaryLine'" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `2` (one in onSelectionChanged, one in change:vertices listener — both from this plan)
    - `grep -c "cell.get('type') === 'showstack.TextLabel'" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `2` (Plan 04 dblclick handler + Plan 06 onSelectionChanged branch)
    - `grep -c "setInspectorMode('boundary', cell)" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `1`
    - `grep -c "setInspectorMode('text', cell)" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `1`
    - `grep -c "attachBoundaryVertexTools(cell)" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `1`
    - `grep -c "detachBoundaryVertexTools(_vertexAttachedCell)" planner/static/planner/js/signal_flow_editor.js` returns AT LEAST `1`
    - The boundary branch in onSelectionChanged appears BEFORE any isLink / isElement branch — verified by reading the function body: the line number of the BoundaryLine type check is LESS than the line number of `cell.isLink && cell.isLink()` (or equivalent).
    - The text branch in onSelectionChanged appears BEFORE the isLink / isElement branches — same check.
    - Both new branches end with `return;` so the non-Phase-12 isLink / isElement branches do NOT also fire for boundary or text cells.
    - The detach-on-non-boundary-select logic appears inside the isLink AND isElement branches (or in a shared cleanup helper) — verified by reading the branches and confirming `detachBoundaryVertexTools(_vertexAttachedCell)` or equivalent is called when transitioning away from a boundary selection.
    - Browser manual: draw a 4-vertex boundary, click on it — inspector opens "Boundary" panel, 4 teal vertex handles visible at the polyline corners. Drag the middle vertex — polyline reshapes, autosave fires; refresh — new vertex positions persist.
    - Browser manual: with a boundary selected, click on a placed text label — inspector switches to "Text" panel, boundary handles disappear, no vertex handles remain on the (now-deselected) boundary.
    - Browser manual: with a boundary selected, click on a placed Console shape — inspector switches to "Node" panel, boundary handles disappear.
    - Browser manual: with a boundary selected, press Delete (or Backspace) — boundary cell is removed; autosave fires; refresh — boundary is gone (DRAW-04 keyboard delete via existing handler at signal_flow_editor.js:~1549, no Phase 12 code added).
    - Browser manual: with a text label selected, press Delete — text cell is removed (TXT-03 keyboard delete inheritance).
  </acceptance_criteria>
  <done>onSelectionChanged has two new branches that fire BEFORE the generic isLink/isElement branches; boundary selection installs vertex handles; text selection opens text inspector; non-boundary selection cleanly removes any prior vertex tools; Delete/Backspace inherits from the existing handler.</done>
</task>

</tasks>

<verification>
- `grep -n "BoundaryVertex\\|attachBoundaryVertexTools\\|detachBoundaryVertexTools\\|_vertexAttachedCell" planner/static/planner/js/signal_flow_editor.js` — expect at least 8 hits (class def + attach + detach + tracker + onSelectionChanged usage + change:vertices listener).
- `grep -c "graph.on('change:vertices'" planner/static/planner/js/signal_flow_editor.js` — expect exactly `1` (standalone listener — Violation 5).
- `grep -c "graph.on('add remove change:source change:target change:size change:vertices'" planner/static/planner/js/signal_flow_editor.js` — expect EXACTLY `0` (Violation 5 negative check — change:vertices NOT in the line-2403 comma-list).
- `grep -c "(model.prop('vertices') || \\[\\]).slice()" planner/static/planner/js/signal_flow_editor.js` — expect exactly `1` (Violation 7).
- `grep -c "window.__sfd && window.__sfd.viewport && window.__sfd.viewport.snapEnabled" planner/static/planner/js/signal_flow_editor.js` — expect AT LEAST `4` after all of Phase 12 lands (Plan 03 pen-tool x2 + Plan 04 place-text + Plan 06 BoundaryVertex — WARNING 4 standardization complete).
- Browser UAT — draw boundary, select, drag a middle vertex, refresh, confirm new shape persists. This is the critical DRAW-04 round-trip verification.
- Browser UAT — draw boundary, double-click on its stroke (NOT a vertex): JointJS may have default cell-move behavior; confirm this does NOT enter any unexpected mode. (Plan 04's element:pointerdblclick handler filters by `cell.get('type') === 'showstack.TextLabel'` so it ignores boundaries.)
</verification>

<must_haves>
- BoundaryVertex elementTools.Control subclass exists with vertexIndex option; visible 6px teal #0d9488 circle + 12px transparent hit-area sibling per D-06 (DRAW-04 supporting tool).
- setPosition reads vertices via `.slice()` COPY before mutating (Violation 7); snaps to 20px grid via window.__sfd.viewport.snapEnabled (D-03 + Phase 8 D-13 parity; WARNING 4 — same expression Plans 03 + 04 use after revision).
- attachBoundaryVertexTools(cell) installs one BoundaryVertex per vertex via joint.dia.ToolsView; called from onSelectionChanged when a BoundaryLine is selected.
- detachBoundaryVertexTools(cell) called on deselect or when selection moves to a non-boundary cell.
- Standalone graph.on('change:vertices', ...) listener exists — NOT added to the line-2403 comma-list (Violation 5). On change it calls applyBoundaryRender + view.updateTools + scheduleAutosave.
- onSelectionChanged has BoundaryLine + TextLabel branches BEFORE the generic isLink/isElement branches; each branch calls setInspectorMode('boundary' | 'text', cell), attaches/detaches tools as appropriate, returns early (TXT-03 selection wiring).
- Delete/Backspace keyboard path INHERITS from the existing handler at signal_flow_editor.js:~1549 — boundaries and text labels delete via the same cell.remove() path as shapes (no Phase 12 code change needed; verified by reading the existing handler).
</must_haves>
</content>
</invoke>
