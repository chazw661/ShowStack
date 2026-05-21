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
  // Picker type config — drives modal title, autocomplete ?type=, and admin-link href.
  // SHP-05: Generic skips the picker entirely.
  // ──────────────────────────────────────────────────────────────

  var PICKER_TYPE_CONFIG = {
    Console:      { backend: 'console',      label: 'Console',       admin: '/admin/planner/console/' },
    Device:       { backend: 'device',       label: 'Device',        admin: '/admin/planner/device/' },
    SpeakerArray: { backend: 'speakerarray', label: 'Speaker Array', admin: '/admin/planner/speakerarray/' },
    CommBeltPack: { backend: 'commbeltpack', label: 'Beltpack',      admin: '/admin/planner/commbeltpack/' },
  };

  // ──────────────────────────────────────────────────────────────
  // Sidebar tile dragstart wiring (CNV-01).
  // ──────────────────────────────────────────────────────────────

  $$('.sfd-tile').forEach(function (tile) {
    tile.addEventListener('dragstart', function (evt) {
      var shapeType = tile.dataset.shapeType;
      if (!shapeType) return;
      evt.dataTransfer.setData('application/x-shape-type', shapeType);
      evt.dataTransfer.effectAllowed = 'copy';
    });
  });

  // ──────────────────────────────────────────────────────────────
  // Paper drop target (CNV-01).
  // PITFALLS §2: use paper.clientToLocalPoint() to translate
  // pointer coords through scroll + zoom.
  // ──────────────────────────────────────────────────────────────

  paperEl.addEventListener('dragover', function (evt) {
    evt.preventDefault();
    evt.dataTransfer.dropEffect = 'copy';
  });

  paperEl.addEventListener('drop', function (evt) {
    evt.preventDefault();
    var shapeType = evt.dataTransfer.getData('application/x-shape-type');
    // T-08-20: defence against crafted dataTransfer carrying an unknown type.
    if (!shapeType || !joint.shapes.showstack[shapeType]) return;

    var local = paper.clientToLocalPoint({ x: evt.clientX, y: evt.clientY });

    // Snap-to-grid — plan 05 turns currentViewport.snapEnabled into a live toggle.
    // For now we honor the default (snap ON, grid 20) per CONTEXT D-13.
    if (currentViewport.snapEnabled) {
      local.x = Math.round(local.x / 20) * 20;
      local.y = Math.round(local.y / 20) * 20;
    }

    var ShapeClass = joint.shapes.showstack[shapeType];
    var node = new ShapeClass({ position: { x: local.x, y: local.y } });
    graph.addCell(node);

    if (shapeType === 'Generic') {
      // SHP-05 — no picker; user types the label later via inspector (plan 06).
      return;
    }

    // Typed shape — open picker; on cancel, remove the placeholder node (CONTEXT D-10).
    openEquipmentPicker(shapeType, node);
  });

  // ──────────────────────────────────────────────────────────────
  // Equipment picker modal (SHP-01..04 / SHP-09).
  // CONTEXT D-09 (drop-first), D-10 (cancel removes placeholder),
  // D-11 (instant search w/ 200ms debounce), D-12 (reuse admin modal pattern).
  // ──────────────────────────────────────────────────────────────

  var pickerOverlay      = document.getElementById('sfd-picker-overlay');
  var pickerTypeSpan     = document.getElementById('sfd-picker-type');
  var pickerEmptyTypeSpan = document.getElementById('sfd-picker-empty-type');
  var pickerSearchInput  = document.getElementById('sfd-picker-search');
  var pickerResultsUL    = document.getElementById('sfd-picker-results');
  var pickerEmptyDiv     = document.getElementById('sfd-picker-empty');
  var pickerAdminLink    = document.getElementById('sfd-picker-admin-link');
  var pickerCancelBtn    = document.getElementById('sfd-picker-cancel');
  var pickerCloseXBtn    = document.getElementById('sfd-picker-close-x');

  var pickerState = {
    open: false,
    shapeType: null,   // 'Console' | 'Device' | 'SpeakerArray' | 'CommBeltPack'
    node: null,        // the placeholder cell to assign-or-remove
    searchTimer: null,
  };

  function openEquipmentPicker(shapeType, node) {
    var cfg = PICKER_TYPE_CONFIG[shapeType];
    if (!cfg) return;

    pickerState.open = true;
    pickerState.shapeType = shapeType;
    pickerState.node = node;

    // textContent only — XSS-safe (T-08-21).
    pickerTypeSpan.textContent = cfg.label;
    pickerEmptyTypeSpan.textContent = cfg.label;
    // T-08-23: admin URL is a hardcoded constant — no user input touches the href.
    pickerAdminLink.setAttribute('href', cfg.admin);

    // Reset UI state.
    pickerSearchInput.value = '';
    pickerResultsUL.innerHTML = '';   // empty-string clear — no content-bearing innerHTML write.
    pickerEmptyDiv.setAttribute('hidden', '');

    // CLAUDE.md admin-DOM override — display:flex must use setProperty + important
    // because the modal partial carries `style="display:none"` inline.
    pickerOverlay.removeAttribute('hidden');
    pickerOverlay.style.setProperty('display', 'flex', 'important');

    // Initial fetch (empty query → first 50 records per project) + focus.
    fetchPickerResults('');
    setTimeout(function () { pickerSearchInput.focus(); }, 50);
  }

  function closeEquipmentPicker(opts) {
    // opts.assigned === true means a row was clicked; leave the node in place.
    // opts.assigned === false (any cancel path) removes the placeholder.
    if (!pickerState.open) return;
    if (!opts || !opts.assigned) {
      if (pickerState.node) {
        // CONTEXT D-10 — no half-built nodes in canvas_state.
        // undoable:false because the placeholder was never user-visible work.
        pickerState.node.remove({ undoable: false });
      }
    }
    pickerOverlay.style.setProperty('display', 'none', 'important');
    pickerOverlay.setAttribute('hidden', '');
    pickerState.open = false;
    pickerState.shapeType = null;
    pickerState.node = null;
    if (pickerState.searchTimer) {
      clearTimeout(pickerState.searchTimer);
      pickerState.searchTimer = null;
    }
  }

  function fetchPickerResults(query) {
    var cfg = PICKER_TYPE_CONFIG[pickerState.shapeType];
    if (!cfg) return;
    var url = autocompleteUrl + '?type=' + encodeURIComponent(cfg.backend);
    if (query) url += '&q=' + encodeURIComponent(query);

    getJSON(url)
      .then(function (data) {
        if (!pickerState.open) return;   // user cancelled while in-flight
        renderPickerResults(data.results || []);
      })
      .catch(function () {
        if (!pickerState.open) return;
        showToast("Couldn't load equipment.", 'error');
        renderPickerResults([]);
      });
  }

  function renderPickerResults(results) {
    // PATTERNS.md XSS rule — createElement + textContent only, no content-bearing innerHTML.
    pickerResultsUL.innerHTML = '';
    if (!results.length) {
      pickerEmptyDiv.removeAttribute('hidden');
      return;
    }
    pickerEmptyDiv.setAttribute('hidden', '');

    results.forEach(function (rec) {
      var row = document.createElement('li');
      row.className = 'sfd-pick-row';
      row.setAttribute('role', 'option');
      row.dataset.id = String(rec.id || '');
      row.dataset.contentTypeId = String(rec.contentTypeId || '');

      var nameSpan = document.createElement('span');
      nameSpan.className = 'sfd-pick-name';
      nameSpan.textContent = rec.name || '(unnamed)';

      var detailSpan = document.createElement('span');
      detailSpan.className = 'sfd-pick-detail';
      detailSpan.textContent = rec.detail || '';

      row.appendChild(nameSpan);
      row.appendChild(detailSpan);
      row.addEventListener('click', function () { assignPickerResult(rec); });

      pickerResultsUL.appendChild(row);
    });
  }

  function assignPickerResult(rec) {
    var node = pickerState.node;
    if (!node) return closeEquipmentPicker({ assigned: false });

    // GFK payload + label snapshot.
    // Phase 9 will use savedLabel for orphan ghosting (SHP-07).
    node.prop('showstack/contentTypeId', rec.contentTypeId);
    node.prop('showstack/objectId', rec.id);
    node.prop('showstack/savedLabel', rec.name || '');
    node.attr('label/text', rec.name || '');

    closeEquipmentPicker({ assigned: true });
  }

  // Search debounce — CONTEXT D-11 instant-search at 200ms.
  pickerSearchInput.addEventListener('input', function () {
    if (pickerState.searchTimer) clearTimeout(pickerState.searchTimer);
    pickerState.searchTimer = setTimeout(function () {
      fetchPickerResults(pickerSearchInput.value.trim());
    }, 200);
  });

  // Close affordances — Cancel button, top-right X, backdrop click, Escape key.
  pickerCancelBtn.addEventListener('click', function () { closeEquipmentPicker({ assigned: false }); });
  pickerCloseXBtn.addEventListener('click', function () { closeEquipmentPicker({ assigned: false }); });
  pickerOverlay.addEventListener('click', function (evt) {
    // Backdrop click only — clicks inside the panel must not close.
    if (evt.target === pickerOverlay) closeEquipmentPicker({ assigned: false });
  });
  document.addEventListener('keydown', function (evt) {
    if (!pickerState.open) return;
    if (evt.key === 'Escape') {
      evt.preventDefault();
      closeEquipmentPicker({ assigned: false });
    }
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
  // Useful seam for plan 06's "re-link equipment" if the inspector wants it (not a Phase 8 requirement).
  window.__sfd.openEquipmentPicker = openEquipmentPicker;

  // Phase 9 will: autosave debounce on graph events, keepalive fetch on visibilitychange.
  // Phase 10 will: circuit-label autocomplete widget, PNG export button.
})();
