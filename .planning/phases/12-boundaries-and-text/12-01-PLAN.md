---
phase: 12
plan_number: 01
wave: 1
depends_on: []
files_modified:
  - planner/static/planner/js/signal_flow_editor.js
autonomous: true
requirements_addressed: [DRAW-01, DRAW-02, TXT-01, TXT-02]
must_haves:
  truths:
    - "BoundaryLine cell class registered on joint.shapes.showstack namespace before graph instantiation"
    - "TextLabel cell class registered on joint.shapes.showstack namespace before graph instantiation"
    - "applyBoundaryRender helper exists and renders both polylines (primary + secondary) from cell.prop('vertices')"
    - "BOUNDARY_PALETTE, TEXT_PALETTE, BOUNDARY_LINE_STYLES, TEXT_FONT_SIZES module-level constants exist"
  artifacts:
    - path: "planner/static/planner/js/signal_flow_editor.js"
      provides: "BoundaryLine class, TextLabel class, applyBoundaryRender helper, palette/style constants"
      contains: "joint.shapes.showstack.BoundaryLine = joint.dia.Element.extend("
      contains_also: "joint.shapes.showstack.TextLabel = joint.dia.Element.extend("
  key_links:
    - from: "BoundaryLine.markup"
      to: "applyBoundaryRender(cell)"
      via: "selectors linePrimary + lineSecondary"
      pattern: "applyBoundaryRender"
---

<objective>
Register the two new JointJS custom element classes (`BoundaryLine` + `TextLabel`) and their module-level support code (palette constants, line-style table, font-size table, render helper) inside the existing IIFE. This plan creates the JointJS surface area Phase 12 needs; no UI is wired yet. Registration MUST land BEFORE `new joint.dia.Graph(...)` so loaded diagrams with these cell types deserialize correctly (PITFALLS §1, signal_flow_editor.js:88).
</objective>

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| Cell-class registration AFTER graph instantiation → diagrams with BoundaryLine cells fail to load silently | medium | Acceptance criterion: both classes registered after `Amp` (line 761) and BEFORE `new joint.dia.Graph(...)` (line ~770). Verified by grep showing both class definitions appear lexically before the graph instantiation. |
| Vertex array mutation by reference in setPosition (Violation 7) — bypasses change:vertices | n/a — this plan defines the helper, not the setter | Plan 06 owns BoundaryVertex.setPosition; this plan only ships applyBoundaryRender which reads vertices and writes attrs. |
| XSS via TextLabel text content | low | TextLabel uses SVG `<text>` (markup tagName: 'text', selector: 'label'). User input flows through `cell.attr('label/text', value)` which sets SVG text-node content, not innerHTML. No HTML injection surface. |
| Boundary stroke renders on top of equipment | n/a — z-order set in Plan 06 (toBack/toFront) | n/a here. |
| validateMagnet allows connector-to-boundary drag | low | BoundaryLine markup has NO `magnet` attr on any child. Existing validateMagnet returns false when `magnet` is falsy (signal_flow_editor.js:792). No code change needed; verified by R-05. |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Register BoundaryLine + TextLabel cell classes and module-level constants</name>
  <files>planner/static/planner/js/signal_flow_editor.js</files>
  <read_first>
    - planner/static/planner/js/signal_flow_editor.js lines 85-122 (FONT_STACK constant and namespace setup)
    - planner/static/planner/js/signal_flow_editor.js lines 615-640 (Console template — the exact pattern to clone)
    - planner/static/planner/js/signal_flow_editor.js lines 755-775 (Amp class end + graph instantiation site)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-01 (lines 120-217 — verbatim BoundaryLine body + applyBoundaryRender)
    - .planning/phases/12-boundaries-and-text/12-RESEARCH.md R-02 (lines 223-263 — verbatim TextLabel body)
    - .planning/phases/12-boundaries-and-text/12-PATTERNS.md "Region A" (lines 27-78 — change directive)
    - CLAUDE.md "Overriding Django admin CSS from JavaScript" — this plan touches SVG inside #sfd-paper which does NOT need !important, but referenced for awareness.
  </read_first>
  <action>
    Locate the end of the Amp shape class (around signal_flow_editor.js:761 — the last `}, joint.dia.Element.prototype.defaults),` of any showstack.* class before `new joint.dia.Graph`). Insert the following code block AFTER the Amp class and BEFORE `new joint.dia.Graph(...)`. Use indentation matching the surrounding shape definitions (2 spaces inside the IIFE).

    ```javascript
      // ──────────────────────────────────────────────────────────────
      // Phase 12 — Decorative cell classes (DRAW + TXT).
      // No ports. No magnets. No equipment GFK (server's IDOR allowlist
      // bypasses these via planner/views.py:7693 `continue`).
      // ──────────────────────────────────────────────────────────────

      // Palette constants (D-09, D-19).
      var BOUNDARY_PALETTE = ['#000000','#666666','#dc2626','#ea580c','#eab308','#16a34a','#2563eb','#9333ea'];
      var TEXT_PALETTE     = BOUNDARY_PALETTE.concat(['#ffffff']);                       // D-19 — +white
      var BOUNDARY_LINE_STYLES = {
        solid:  { dasharray: 'none',  doubleVisible: false },
        dashed: { dasharray: '6 4',   doubleVisible: false },
        dotted: { dasharray: '1 3',   doubleVisible: false },
        double: { dasharray: 'none',  doubleVisible: true  },
      };
      var TEXT_FONT_SIZES = { small: 12, medium: 16, large: 24 };                       // D-19

      // ---- BoundaryLine — decorative polyline, no ports, no magnets (DRAW) ----
      // VERTEX STORAGE: cell.prop('vertices') — array of {x, y} in paper-local coords.
      // DOUBLE-LINE: lineSecondary polyline is display:none for solid/dashed/dotted
      // and display:inline (with same color, no dasharray, +3 y-offset) for 'double'.
      joint.shapes.showstack.BoundaryLine = joint.dia.Element.extend({
        markup: [
          { tagName: 'g',        selector: 'lineGroup' },
          { tagName: 'polyline', selector: 'linePrimary' },
          { tagName: 'polyline', selector: 'lineSecondary' },
        ],
        defaults: joint.util.deepSupplement({
          type: 'showstack.BoundaryLine',
          // size + position are not meaningful for a polyline; vertices array drives
          // the rendered geometry. Zero size keeps JointJS layout helpers (snap-to-
          // grid on cell.position()) from accidentally applying.
          size: { width: 0, height: 0 },
          attrs: {
            linePrimary: {
              fill: 'none',
              stroke: '#000000',
              'stroke-width': 2,
              'stroke-dasharray': 'none',
              'stroke-linejoin': 'round',
              'stroke-linecap': 'round',
              'pointer-events': 'stroke',
            },
            lineSecondary: {
              fill: 'none',
              stroke: '#000000',
              'stroke-width': 2,
              'stroke-dasharray': 'none',
              'stroke-linejoin': 'round',
              'stroke-linecap': 'round',
              display: 'none',
              'pointer-events': 'none',
            },
          },
          // Custom property bag — survives toJSON round-trip via JointJS cell.attributes.
          vertices:    [],             // [{x, y}, ...] — paper-local coords
          color:       '#000000',
          lineStyle:   'solid',        // 'solid' | 'dashed' | 'dotted' | 'double'
          strokeWidth: 2,              // fixed at 2 in v2.3; not engineer-configurable
        }, joint.dia.Element.prototype.defaults),
      });

      // ---- TextLabel — single SVG <text> child + transient HTML <input> for edit (TXT) ----
      // INLINE-EDIT (D-16/D-17) is owned by Plan 04; this class declares the persisted form.
      joint.shapes.showstack.TextLabel = joint.dia.Element.extend({
        markup: [
          { tagName: 'rect', selector: 'hitArea' },    // invisible drag/select target
          { tagName: 'text', selector: 'label' },
        ],
        defaults: joint.util.deepSupplement({
          type: 'showstack.TextLabel',
          size: { width: 60, height: 22 },             // initial — auto-recomputed by Plan 04 on commit
          attrs: {
            hitArea: {
              refWidth: '100%', refHeight: '100%',
              fill: 'transparent',
              stroke: 'none',
            },
            label: {
              refX: '50%', refY: '50%',
              textAnchor: 'middle', textVerticalAnchor: 'middle',
              fontSize: 16,                            // D-19 medium default
              fontFamily: FONT_STACK,                  // system fonts only (PNG-export font-taint)
              fill: '#000000',                         // D-19 black default
              text: '',                                // populated by Plan 04 inline-edit on commit
            },
          },
          // Custom property bag.
          fontSize: 16,
          color:    '#000000',
        }, joint.dia.Element.prototype.defaults),
      });

      // applyBoundaryRender — single source of truth for re-rendering both polylines
      // after any vertex / color / lineStyle change. Called from:
      //   - Plan 03 commitOrCancelBoundary() after addCell
      //   - Plan 05 inspector swatch/segmented click handlers
      //   - Plan 06 graph.on('change:vertices', ...) listener
      // For v2.3 the double-line uses a flat (0, +3) y-offset on the secondary polyline
      // (acceptable for mostly-horizontal architectural boundaries; per-segment unit-
      // normal math is a Risk #3 v2.4 follow-up).
      function applyBoundaryRender(cell) {
        var verts = cell.prop('vertices') || [];
        var primaryPoints   = verts.map(function (v) { return v.x + ',' + v.y; }).join(' ');
        var secondaryPoints = verts.map(function (v) { return v.x + ',' + (v.y + 3); }).join(' ');
        var style = BOUNDARY_LINE_STYLES[cell.prop('lineStyle') || 'solid'];
        var color = cell.prop('color') || '#000000';

        cell.attr({
          linePrimary: {
            points: primaryPoints,
            stroke: color,
            'stroke-dasharray': style.dasharray,
          },
          lineSecondary: {
            points: secondaryPoints,
            stroke: color,
            display: style.doubleVisible ? 'inline' : 'none',
          },
        });
      }
    ```

    Do NOT modify any other code in this plan. Do NOT modify signal_flow_editor.js:80-122 (Phase 11 standardPortGroups / portsForRect). Do NOT register on `admin.site` (irrelevant — Phase 12 has no admin work).

    Constants placement: the four `var BOUNDARY_PALETTE / TEXT_PALETTE / BOUNDARY_LINE_STYLES / TEXT_FONT_SIZES` declarations MUST appear inside the IIFE so they are closure-visible to Plans 03, 04, 05, 06. The insertion site (right above the BoundaryLine class) puts them in the same scope as `FONT_STACK` (line 94) and `joint.shapes.showstack` (line 91).

    `applyBoundaryRender` MUST appear AFTER both class definitions so it can be invoked by downstream plans without forward-declaration concerns.
  </action>
  <verify>
    <automated>grep -n "joint.shapes.showstack.BoundaryLine = joint.dia.Element.extend(" planner/static/planner/js/signal_flow_editor.js && grep -n "joint.shapes.showstack.TextLabel = joint.dia.Element.extend(" planner/static/planner/js/signal_flow_editor.js && grep -n "function applyBoundaryRender" planner/static/planner/js/signal_flow_editor.js && grep -n "var BOUNDARY_PALETTE = " planner/static/planner/js/signal_flow_editor.js && grep -n "var BOUNDARY_LINE_STYLES = " planner/static/planner/js/signal_flow_editor.js</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "joint.shapes.showstack.BoundaryLine = joint.dia.Element.extend(" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "joint.shapes.showstack.TextLabel = joint.dia.Element.extend(" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - `grep -c "function applyBoundaryRender" planner/static/planner/js/signal_flow_editor.js` returns exactly `1`
    - The line number of `joint.shapes.showstack.BoundaryLine = joint.dia.Element.extend(` is LESS than the line number of `new joint.dia.Graph(` (verified with `grep -n` on both — registration-before-instantiation per PITFALLS §1)
    - `grep -c "var BOUNDARY_PALETTE = \\['#000000','#666666','#dc2626','#ea580c','#eab308','#16a34a','#2563eb','#9333ea'\\]" planner/static/planner/js/signal_flow_editor.js` returns `1`
    - `grep -c "TEXT_PALETTE\\s*=\\s*BOUNDARY_PALETTE.concat" planner/static/planner/js/signal_flow_editor.js` returns `1`
    - `grep -c "var BOUNDARY_LINE_STYLES = {" planner/static/planner/js/signal_flow_editor.js` returns `1`
    - `grep -c "var TEXT_FONT_SIZES = { small: 12, medium: 16, large: 24 }" planner/static/planner/js/signal_flow_editor.js` returns `1`
    - The BoundaryLine class markup contains exactly three children with selectors `lineGroup`, `linePrimary`, `lineSecondary` (verified by reading the inserted block).
    - The TextLabel class markup contains exactly two children with selectors `hitArea`, `label` (verified by reading the inserted block).
    - Browser manual: load the editor at /audiopatch/signal-flow/<diagram_id>/edit/ — no JS console errors; `window.joint.shapes.showstack.BoundaryLine` and `window.joint.shapes.showstack.TextLabel` both resolve to functions in DevTools console.
  </acceptance_criteria>
  <done>BoundaryLine + TextLabel + applyBoundaryRender + 4 module-level constants exist in signal_flow_editor.js, registered before graph instantiation, and the editor page loads without JS errors.</done>
</task>

</tasks>

<verification>
- `grep -n "joint.shapes.showstack.BoundaryLine\|joint.shapes.showstack.TextLabel\|function applyBoundaryRender\|var BOUNDARY_PALETTE\|var TEXT_PALETTE\|var BOUNDARY_LINE_STYLES\|var TEXT_FONT_SIZES" planner/static/planner/js/signal_flow_editor.js` — expect exactly 7 hits, all clustered between lines ~760 and ~870 (after Amp, before graph instantiation).
- `grep -n "new joint.dia.Graph(" planner/static/planner/js/signal_flow_editor.js` — graph instantiation line number MUST be greater than the BoundaryLine registration line number.
- Browser manual: open the editor, open DevTools console, type `joint.shapes.showstack.BoundaryLine` — should return a function (the Backbone-extended constructor). Same for `TextLabel`. No console errors on page load.
- Browser manual: type `typeof applyBoundaryRender === 'undefined'` — should return `true` from the window scope (function is closure-scoped inside the IIFE, NOT a global). This is the expected scoping outcome.
</verification>

<must_haves>
- BoundaryLine cell class registered on `joint.shapes.showstack` namespace before graph instantiation (DRAW-01, DRAW-02 foundation).
- TextLabel cell class registered on `joint.shapes.showstack` namespace before graph instantiation (TXT-01, TXT-02 foundation).
- `applyBoundaryRender(cell)` is the one true render helper for boundary cells — driven by `cell.prop('vertices')`, `cell.prop('color')`, `cell.prop('lineStyle')`.
- Module-level constants: `BOUNDARY_PALETTE` (8 hexes), `TEXT_PALETTE` (BOUNDARY_PALETTE + #ffffff), `BOUNDARY_LINE_STYLES` (4 keys with dasharray + doubleVisible), `TEXT_FONT_SIZES` ({small:12, medium:16, large:24}).
- Both classes have NO `ports:` key and NO `magnet` attribute on any markup child — preventing accidental connector endpoint snapping (R-05 carry).
- Editor page loads without JS errors after this plan.
</must_haves>
