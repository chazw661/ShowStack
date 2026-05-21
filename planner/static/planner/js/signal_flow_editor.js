// planner/static/planner/js/signal_flow_editor.js
//
// Signal Flow Diagrammer — editor controller.
// Phase 8: JointJS canvas, 5 smart shapes, drag-drop from sidebar,
// equipment picker modal. Plans 05/06 extend this same IIFE for
// pan/zoom/snap/undo/delete and connectors/inspector/save.
//
// IMPORTANT: All admin-DOM color/style writes use
//     el.style.setProperty(prop, value, 'important')
// Direct property assignment (the dot-style.color form) silently fails
// against Django admin's !important rules (CLAUDE.md > Coding Conventions).
//
// Note: JointJS canvas SVG elements are NOT in the admin DOM and are
// unaffected by the !important rule. The setProperty + important guard
// only matters for the modal HTML rendered by Django admin templates.

(function () {
  'use strict';

  var container = document.getElementById('sfd-container');
  if (!container) {
    // Either we're not on the editor page or the template was changed unexpectedly.
    return;
  }

  var diagramId = container.dataset.diagramId;
  var stateUrl = container.dataset.stateUrl;
  var autosaveUrl = container.dataset.autosaveUrl;
  var autocompleteUrl = container.dataset.autocompleteUrl;
  // (exportPngUrl is Phase 10 — do not read here)

  // Confirm JointJS UMD bundle loaded and exposes `joint` global.
  if (typeof joint === 'undefined') {
    console.error('[SFD] joint is not defined — check vendor/joint.min.js load order in editor.html');
    return;
  }

  // ──────────────────────────────────────────────────────────────
  // Helpers (analog of multitrack_editor.js — sfd- namespace).
  // ──────────────────────────────────────────────────────────────

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      credentials: 'same-origin',
      body: JSON.stringify(body || {}),
    }).then(function (r) {
      return r.json().then(function (data) { return { status: r.status, data: data }; });
    });
  }

  function getJSON(url) {
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); });
  }

  function showToast(message, level) {
    var t = document.createElement('div');
    t.className = 'sfd-toast sfd-toast--' + (level || 'info');
    t.textContent = message;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add('sfd-toast--hide'); }, 3000);
    setTimeout(function () { t.remove(); }, 3500);
  }

  // ──────────────────────────────────────────────────────────────
  // Smart shape classes — joint.shapes.showstack namespace.
  // PITFALLS §1: register BEFORE new joint.dia.Graph.
  // ──────────────────────────────────────────────────────────────

  joint.shapes.showstack = joint.shapes.showstack || {};

  // System fonts only — REQUIREMENTS Constraint (PNG canvas integrity in Phase 10).
  var FONT_STACK = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

  // Standard port-group definition — shared by all 5 shapes.
  // SHP-08: 4 ports per shape (in-left, out-right, in-top, out-bottom).
  // Magnet semantics: 'passive' = inbound only, true = outbound source.
  // Hidden at rest (opacity 0); plan 02 CSS handles hover-reveal.
  function standardPortGroups() {
    return {
      in: {
        position: { name: 'absolute' },
        attrs: { portBody: { magnet: 'passive', r: 4, fill: '#fff', stroke: '#666', 'stroke-width': 1, opacity: 0 } },
        markup: [{ tagName: 'circle', selector: 'portBody' }],
      },
      out: {
        position: { name: 'absolute' },
        attrs: { portBody: { magnet: true, r: 4, fill: '#fff', stroke: '#666', 'stroke-width': 1, opacity: 0 } },
        markup: [{ tagName: 'circle', selector: 'portBody' }],
      },
    };
  }

  // 4 ports placed on the bounding box mid-edges.
  // For polygon (SpeakerArray) and pill (CommBeltPack), bbox-position is acceptable
  // for the Phase 8 smoke test — RESEARCH Open Risk #2 acknowledges polygon docking
  // may want shapePerimeterConnectionPoint later, but not Phase 8.
  function portsForRect(width, height) {
    return {
      groups: standardPortGroups(),
      items: [
        { group: 'in',  args: { x: 0,         y: height / 2 } },
        { group: 'out', args: { x: width,     y: height / 2 } },
        { group: 'in',  args: { x: width / 2, y: 0 } },
        { group: 'out', args: { x: width / 2, y: height } },
      ],
    };
  }

  // ---- Console (180×60, teal #0d9488 left band) ----
  joint.shapes.showstack.Console = joint.dia.Element.extend({
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'rect', selector: 'band' },
      { tagName: 'text', selector: 'label' },
    ],
    defaults: joint.util.deepSupplement({
      type: 'showstack.Console',
      size: { width: 180, height: 60 },
      attrs: {
        body:  { refWidth: '100%', refHeight: '100%', fill: '#ffffff', stroke: '#333', 'stroke-width': 1.5 },
        band:  { x: 0, y: 0, width: 6, refHeight: '100%', fill: '#0d9488' },
        label: { refX: 16, refY: '50%', textAnchor: 'start', textVerticalAnchor: 'middle',
                 fontSize: 13, fontFamily: FONT_STACK, fill: '#111', text: 'Console' },
      },
      ports: portsForRect(180, 60),
    }, joint.dia.Element.prototype.defaults),
  });

  // ---- Device (140×56, slate #475569 left band) ----
  joint.shapes.showstack.Device = joint.dia.Element.extend({
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'rect', selector: 'band' },
      { tagName: 'text', selector: 'label' },
    ],
    defaults: joint.util.deepSupplement({
      type: 'showstack.Device',
      size: { width: 140, height: 56 },
      attrs: {
        body:  { refWidth: '100%', refHeight: '100%', fill: '#ffffff', stroke: '#333', 'stroke-width': 1.5 },
        band:  { x: 0, y: 0, width: 6, refHeight: '100%', fill: '#475569' },
        label: { refX: 16, refY: '50%', textAnchor: 'start', textVerticalAnchor: 'middle',
                 fontSize: 13, fontFamily: FONT_STACK, fill: '#111', text: 'Device' },
      },
      ports: portsForRect(140, 56),
    }, joint.dia.Element.prototype.defaults),
  });

  // ---- SpeakerArray (120×80, orange #ea580c band on left edge; polygon body) ----
  joint.shapes.showstack.SpeakerArray = joint.dia.Element.extend({
    markup: [
      { tagName: 'polygon', selector: 'body' },
      { tagName: 'rect',    selector: 'band' },
      { tagName: 'text',    selector: 'label' },
    ],
    defaults: joint.util.deepSupplement({
      type: 'showstack.SpeakerArray',
      size: { width: 120, height: 80 },
      attrs: {
        body:  { points: '20,0 100,0 120,80 0,80', fill: '#ffffff', stroke: '#333', 'stroke-width': 1.5 },
        band:  { x: 0, y: 0, width: 6, refHeight: '100%', fill: '#ea580c' },
        label: { refX: '50%', refY: '50%', textAnchor: 'middle', textVerticalAnchor: 'middle',
                 fontSize: 13, fontFamily: FONT_STACK, fill: '#111', text: 'Speaker Array' },
      },
      ports: portsForRect(120, 80),
    }, joint.dia.Element.prototype.defaults),
  });

  // ---- CommBeltPack (80×100, purple #7c3aed band, pill / rounded-rect body) ----
  joint.shapes.showstack.CommBeltPack = joint.dia.Element.extend({
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'rect', selector: 'band' },
      { tagName: 'text', selector: 'label' },
    ],
    defaults: joint.util.deepSupplement({
      type: 'showstack.CommBeltPack',
      size: { width: 80, height: 100 },
      attrs: {
        body:  { refWidth: '100%', refHeight: '100%', rx: 40, ry: 40,
                 fill: '#ffffff', stroke: '#333', 'stroke-width': 1.5 },
        band:  { x: 6, y: 12, width: 6, height: 76, fill: '#7c3aed' },
        label: { refX: '50%', refY: '50%', textAnchor: 'middle', textVerticalAnchor: 'middle',
                 fontSize: 12, fontFamily: FONT_STACK, fill: '#111', text: 'Beltpack' },
      },
      ports: portsForRect(80, 100),
    }, joint.dia.Element.prototype.defaults),
  });

  // ---- Generic (140×56, dashed grey #94a3b8 border, no band) ----
  joint.shapes.showstack.Generic = joint.dia.Element.extend({
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'text', selector: 'label' },
    ],
    defaults: joint.util.deepSupplement({
      type: 'showstack.Generic',
      size: { width: 140, height: 56 },
      attrs: {
        body:  { refWidth: '100%', refHeight: '100%', fill: '#ffffff', stroke: '#94a3b8',
                 'stroke-width': 1.5, 'stroke-dasharray': '4 3' },
        label: { refX: '50%', refY: '50%', textAnchor: 'middle', textVerticalAnchor: 'middle',
                 fontSize: 13, fontFamily: FONT_STACK, fill: '#111', text: 'Generic' },
      },
      ports: portsForRect(140, 56),
    }, joint.dia.Element.prototype.defaults),
  });

  // ──────────────────────────────────────────────────────────────
  // Graph + Paper init.
  // PITFALLS §1: pass cellNamespace AND cellViewNamespace.
  // ──────────────────────────────────────────────────────────────

  var cellNamespace = Object.assign({}, joint.shapes, { showstack: joint.shapes.showstack });

  var graph = new joint.dia.Graph({}, { cellNamespace: cellNamespace });

  var paperEl = document.getElementById('sfd-paper');
  var paper = new joint.dia.Paper({
    el: paperEl,
    model: graph,
    cellViewNamespace: cellNamespace,
    width: 4000,
    height: 3000,
    gridSize: 20,
    drawGrid: { name: 'dot', args: { color: '#dde', thickness: 1 } },
    background: { color: '#ffffff' },
    // CON-related options (linkPinning, validateConnection, defaultLink) ship in plan 06.
  });

  // ──────────────────────────────────────────────────────────────
  // Initial state load — viewport + canvas_state from data-state-url.
  // ──────────────────────────────────────────────────────────────

  // Module-scoped — plan 05 will read/write these from the UX layer.
  var currentViewport = { x: 0, y: 0, scale: 1, snapEnabled: true };
  var currentVersion = 1;

  getJSON(stateUrl)
    .then(function (state) {
      currentVersion = state.version || 1;
      var vp = state.viewport || {};
      if (typeof vp.scale === 'number') currentViewport.scale = Math.max(0.25, Math.min(2.0, vp.scale));
      if (typeof vp.x === 'number') currentViewport.x = vp.x;
      if (typeof vp.y === 'number') currentViewport.y = vp.y;
      if (typeof vp.snapEnabled === 'boolean') currentViewport.snapEnabled = vp.snapEnabled;

      // Apply viewport BEFORE loading cells so the user sees the right region immediately.
      paper.scale(currentViewport.scale, currentViewport.scale);
      paper.translate(currentViewport.x, currentViewport.y);

      var canvasState = state.canvas_state || {};
      if (canvasState && Array.isArray(canvasState.cells)) {
        // CRITICAL: undoable:false suppresses initial-load events from the undo stack (plan 05).
        graph.fromJSON(canvasState, { undoable: false });
      }
      console.log('[SFD] paper ready — diagram', diagramId,
                  '— version', currentVersion,
                  '— cells', graph.getCells().length);
    })
    .catch(function (err) {
      console.error('[SFD] state load failed', err);
      showToast("Couldn't load diagram state.", 'error');
    });

  // ──────────────────────────────────────────────────────────────
  // Handoff to plans 05 + 06 — single window-scoped attachment so
  // those plans extend the same Graph/Paper instances rather than
  // instantiating new ones.
  // ──────────────────────────────────────────────────────────────

  window.__sfd = window.__sfd || {};
  window.__sfd.graph = graph;
  window.__sfd.paper = paper;
  window.__sfd.paperEl = paperEl;
  window.__sfd.viewport = currentViewport;
  window.__sfd.helpers = { $: $, $$: $$, csrfToken: csrfToken, postJSON: postJSON, getJSON: getJSON, showToast: showToast };
  window.__sfd.urls = { state: stateUrl, autosave: autosaveUrl, autocomplete: autocompleteUrl };
  window.__sfd.shapeNamespace = joint.shapes.showstack;
  window.__sfd.cellNamespace = cellNamespace;

  // Phase 9 will: autosave debounce on graph events, keepalive fetch on visibilitychange.
  // Phase 10 will: circuit-label autocomplete widget, PNG export button.
})();
