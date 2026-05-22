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

  // Plans 04-06 progressively assign to window.__sfd (handoff seam between
  // sub-plans). Initialise here so anything that writes to it before the
  // full handoff block (around the bottom of this IIFE) doesn't throw.
  window.__sfd = window.__sfd || {};

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
    // CON-related options — must be set at construction; post-hoc
    // `paper.options.X = Y` is not reliably picked up by @joint/core 4.x.
    linkPinning: false,                       // CON-03 — reject drops on empty paper
    snapLinks: { radius: 24 },                // RESEARCH §12 — port snap radius
    defaultLink: function () {
      // joint.shapes.showstack.SignalLink is registered later in this IIFE,
      // but this factory is called lazily on first port-drag, so the lookup
      // resolves correctly at user-interaction time.
      return new joint.shapes.showstack.SignalLink();
    },
    validateMagnet: function (cellView, magnet) {
      // Allow link drag to START only from non-passive magnets (out-ports).
      // In-ports have magnet="passive" and act as drag TARGETS only.
      // PATTERNS risk #4 mitigation.
      return magnet && magnet.getAttribute('magnet') !== 'passive';
    },
    validateConnection: function (sourceView, sourceMagnet, targetView, targetMagnet) {
      // CON-03 — both ends MUST be magnets (ports). Mid-shape drops have null magnet.
      if (!sourceMagnet || !targetMagnet) return false;
      // Reject self-connections (same shape on both ends).
      if (sourceView === targetView) return false;
      return true;
    },
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
    node.prop('showstack/contentTypeId', rec.contentTypeId);
    node.prop('showstack/objectId', rec.id);
    node.prop('showstack/savedLabel', rec.name || '');
    node.attr('label/text', rec.name || '');

    // Phase 9 — picker assigns a live record, so this cell is no longer an orphan.
    node.prop('showstack/isOrphan', false);
    applyOrphanState(node);              // clear joint-orphan attribute on the view
    // Re-evaluate any link attached to this node — its attached-orphan attribute
    // may need to clear (if both endpoints are now live).
    graph.getConnectedLinks(node).forEach(applyAttachedOrphanState);
    scheduleAutosave();                  // persist the new GFK + cleared orphan flag

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

  // ══════════════════════════════════════════════════════════════
  // Plan 08-05 — Canvas UX layer
  //   Pan (space + middle-click), zoom (in/out/fit + level display),
  //   snap toggle, viewport debounced persistence,
  //   custom event-sourced undo/redo stack, multi-selection, delete.
  //
  //   All code below extends the same closure scope as plan 04 above —
  //   `graph`, `paper`, `paperEl`, `currentViewport`, `pickerState`,
  //   `csrfToken`, `autosaveUrl` are already in scope.
  // ══════════════════════════════════════════════════════════════

  // ──────────────────────────────────────────────────────────────
  // Viewport debounced POST (CNV-08).
  // 800ms coalesces rapid pan/zoom/snap events into one fetch.
  // Hits the plan-01 viewport-only fast path (`?viewport_only=1`):
  // does NOT bump version, does NOT validate equipment refs.
  // CSRF token via X-CSRFToken — matches multitrack postJSON pattern.
  // Defined BEFORE callers below.
  // ──────────────────────────────────────────────────────────────

  var viewportTimer = null;
  function schedulePersistViewport() {
    if (viewportTimer) clearTimeout(viewportTimer);
    viewportTimer = setTimeout(function () {
      viewportTimer = null;
      var payload = {
        viewport: {
          x: currentViewport.x,
          y: currentViewport.y,
          scale: currentViewport.scale,
          snapEnabled: currentViewport.snapEnabled,
        },
      };
      fetch(autosaveUrl + '?viewport_only=1', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
        body: JSON.stringify(payload),
      }).catch(function () {
        // Silent — viewport persistence is best-effort. Don't pester the user.
      });
    }, 800);
  }

  // ──────────────────────────────────────────────────────────────
  // Pan (CNV-02) — Space+left-drag OR middle-click drag.
  // CLAUDE.md: cursor writes MUST use setProperty(... 'important').
  // Guard against typing into inputs and against the picker modal.
  // ──────────────────────────────────────────────────────────────

  var panState = { spaceDown: false, dragging: false, startX: 0, startY: 0, baseTx: 0, baseTy: 0 };

  document.addEventListener('keydown', function (evt) {
    if (/INPUT|TEXTAREA|SELECT/.test(evt.target.tagName)) return;
    if (pickerState && pickerState.open) return;
    if (evt.code === 'Space' && !panState.spaceDown) {
      panState.spaceDown = true;
      paperEl.style.setProperty('cursor', 'grab', 'important');
      evt.preventDefault();
    }
  });
  document.addEventListener('keyup', function (evt) {
    if (evt.code === 'Space') {
      panState.spaceDown = false;
      if (!panState.dragging) paperEl.style.setProperty('cursor', '', 'important');
    }
  });

  paperEl.addEventListener('mousedown', function (evt) {
    var isMiddle = evt.button === 1;
    var isSpaceLeft = evt.button === 0 && panState.spaceDown;
    if (!isMiddle && !isSpaceLeft) return;
    panState.dragging = true;
    panState.startX = evt.clientX;
    panState.startY = evt.clientY;
    var t = paper.translate();
    panState.baseTx = t.tx;
    panState.baseTy = t.ty;
    paperEl.style.setProperty('cursor', 'grabbing', 'important');
    evt.preventDefault();
  });
  document.addEventListener('mousemove', function (evt) {
    if (!panState.dragging) return;
    var dx = evt.clientX - panState.startX;
    var dy = evt.clientY - panState.startY;
    paper.translate(panState.baseTx + dx, panState.baseTy + dy);
    currentViewport.x = panState.baseTx + dx;
    currentViewport.y = panState.baseTy + dy;
  });
  document.addEventListener('mouseup', function (evt) {
    if (!panState.dragging) return;
    panState.dragging = false;
    paperEl.style.setProperty('cursor', panState.spaceDown ? 'grab' : '', 'important');
    schedulePersistViewport();
  });

  // ──────────────────────────────────────────────────────────────
  // Zoom (CNV-03) — in / out / fit + persistent level display.
  // Clamp to [0.25, 2.0]. Each step is 1.2x / ÷1.2.
  // Zoom-to-fit pads bbox by 40px on each side, never exceeds 2.0.
  // ──────────────────────────────────────────────────────────────

  var zoomLevelEl = document.getElementById('sfd-zoom-level');

  function setZoom(newScale) {
    newScale = Math.max(0.25, Math.min(2.0, newScale));
    paper.scale(newScale, newScale);
    currentViewport.scale = newScale;
    if (zoomLevelEl) zoomLevelEl.textContent = Math.round(newScale * 100) + '%';
    schedulePersistViewport();
  }
  function zoomIn()  { setZoom(currentViewport.scale * 1.2); }
  function zoomOut() { setZoom(currentViewport.scale / 1.2); }
  function zoomToFit() {
    var cells = graph.getCells();
    if (!cells.length) {
      setZoom(1.0);
      paper.translate(0, 0);
      currentViewport.x = 0; currentViewport.y = 0;
      return;
    }
    var bbox = graph.getBBox(cells);
    if (!bbox || bbox.width === 0 || bbox.height === 0) { setZoom(1.0); return; }
    var paperW = paperEl.clientWidth;
    var paperH = paperEl.clientHeight;
    var fitScale = Math.min(paperW / (bbox.width + 80), paperH / (bbox.height + 80), 2.0);
    fitScale = Math.max(0.25, fitScale);
    paper.scale(fitScale, fitScale);
    var tx = -bbox.x * fitScale + 40;
    var ty = -bbox.y * fitScale + 40;
    paper.translate(tx, ty);
    currentViewport.scale = fitScale;
    currentViewport.x = tx;
    currentViewport.y = ty;
    if (zoomLevelEl) zoomLevelEl.textContent = Math.round(fitScale * 100) + '%';
    schedulePersistViewport();
  }

  document.getElementById('sfd-zoom-in').addEventListener('click', zoomIn);
  document.getElementById('sfd-zoom-out').addEventListener('click', zoomOut);
  document.getElementById('sfd-zoom-fit').addEventListener('click', zoomToFit);

  // Initial display — currentViewport.scale was set by the state-load promise
  // (or defaults to 1.0 from the initial currentViewport literal).
  if (zoomLevelEl) zoomLevelEl.textContent = Math.round(currentViewport.scale * 100) + '%';

  // ──────────────────────────────────────────────────────────────
  // Snap to grid (CNV-04) — default ON per CONTEXT D-13.
  // On: 20px grid + dotted overlay; off: 1px grid + no overlay.
  // Updates aria-pressed + is-active class on toolbar button.
  // ──────────────────────────────────────────────────────────────

  var snapToggleBtn = document.getElementById('sfd-snap-toggle');

  function setSnap(on) {
    // `@joint/core` 4.x: setGrid() takes a drawGrid config (or null to hide);
    // setGridSize() sets the snap grid spacing. There is no public drawGrid() method.
    currentViewport.snapEnabled = !!on;
    paper.setGridSize(on ? 20 : 1);
    paper.setGrid(on ? { name: 'dot', args: { color: '#dde', thickness: 1 } } : null);
    if (snapToggleBtn) {
      if (on) {
        snapToggleBtn.classList.add('is-active');
        snapToggleBtn.setAttribute('aria-pressed', 'true');
        snapToggleBtn.setAttribute('aria-label', 'Snap to grid: on');
      } else {
        snapToggleBtn.classList.remove('is-active');
        snapToggleBtn.setAttribute('aria-pressed', 'false');
        snapToggleBtn.setAttribute('aria-label', 'Snap to grid: off');
      }
    }
    schedulePersistViewport();
  }

  snapToggleBtn.addEventListener('click', function () { setSnap(!currentViewport.snapEnabled); });
  setSnap(currentViewport.snapEnabled);   // apply initial state from plan-04 viewport load

  // ──────────────────────────────────────────────────────────────
  // Custom event-sourced undo / redo stack (CNV-05).
  //
  // @joint/core 4.2.4 ships NO CommandManager — it's JointJS+ (paid)
  // only. We roll our own per RESEARCH.md "Custom Undo-Stack Pattern".
  //
  // Bounded to UNDO_HISTORY_CAP=50 batches (T-08-30 mitigation).
  // EVERY applyInverse / applyForward call MUST pass { undoable: false }
  // so the graph listeners below don't re-record their own actions.
  //
  // Plan 04 already runs the initial fromJSON with { undoable: false },
  // so initial-load adds never reach this stack.
  // ──────────────────────────────────────────────────────────────

  var undoStack = [];
  var redoStack = [];
  var undoCapturing = true;
  var undoBatchDepth = 0;
  var undoBatchCurrent = null;
  var UNDO_HISTORY_CAP = 50;

  function undoRecord(cmd) {
    if (!undoCapturing) return;
    if (undoBatchDepth > 0) {
      undoBatchCurrent.push(cmd);
    } else {
      undoStack.push([cmd]);
      if (undoStack.length > UNDO_HISTORY_CAP) undoStack.shift();
      redoStack.length = 0;
    }
    refreshUndoButtons();
  }

  function undoBeginBatch() {
    undoBatchDepth++;
    if (undoBatchDepth === 1) undoBatchCurrent = [];
  }
  function undoEndBatch() {
    undoBatchDepth = Math.max(0, undoBatchDepth - 1);
    if (undoBatchDepth === 0 && undoBatchCurrent && undoBatchCurrent.length) {
      undoStack.push(undoBatchCurrent);
      if (undoStack.length > UNDO_HISTORY_CAP) undoStack.shift();
      redoStack.length = 0;
      undoBatchCurrent = null;
      refreshUndoButtons();
    } else if (undoBatchDepth === 0) {
      undoBatchCurrent = null;
    }
  }

  graph.on('add', function (cell, _coll, opts) {
    if (opts && opts.undoable === false) return;
    undoRecord({ type: 'add', cellId: cell.id, json: cell.toJSON() });
  });
  graph.on('remove', function (cell, _coll, opts) {
    if (opts && opts.undoable === false) return;
    undoRecord({ type: 'remove', cellId: cell.id, json: cell.toJSON() });
  });
  graph.on('change', function (cell, opts) {
    if (opts && opts.undoable === false) return;
    var before = cell.previousAttributes();
    if (!before) return;
    undoRecord({
      type: 'change',
      cellId: cell.id,
      before: JSON.parse(JSON.stringify(before)),
      after: JSON.parse(JSON.stringify(cell.toJSON())),
    });
  });

  function applyInverse(cmd) {
    undoCapturing = false;
    try {
      if (cmd.type === 'add') {
        var c = graph.getCell(cmd.cellId);
        if (c) c.remove({ undoable: false });
      } else if (cmd.type === 'remove') {
        graph.addCell(cmd.json, { undoable: false });
      } else if (cmd.type === 'change') {
        var c2 = graph.getCell(cmd.cellId);
        if (c2) c2.set(cmd.before, { undoable: false });
      }
    } finally {
      undoCapturing = true;
    }
  }
  function applyForward(cmd) {
    undoCapturing = false;
    try {
      if (cmd.type === 'add') {
        graph.addCell(cmd.json, { undoable: false });
      } else if (cmd.type === 'remove') {
        var c = graph.getCell(cmd.cellId);
        if (c) c.remove({ undoable: false });
      } else if (cmd.type === 'change') {
        var c2 = graph.getCell(cmd.cellId);
        if (c2) c2.set(cmd.after, { undoable: false });
      }
    } finally {
      undoCapturing = true;
    }
  }

  function doUndo() {
    var batch = undoStack.pop();
    if (!batch) return;
    for (var i = batch.length - 1; i >= 0; i--) applyInverse(batch[i]);
    redoStack.push(batch);
    refreshUndoButtons();
  }
  function doRedo() {
    var batch = redoStack.pop();
    if (!batch) return;
    for (var i = 0; i < batch.length; i++) applyForward(batch[i]);
    undoStack.push(batch);
    refreshUndoButtons();
  }

  // Toolbar Undo / Redo buttons — disabled when their stack is empty.
  var undoBtn = document.getElementById('sfd-undo');
  var redoBtn = document.getElementById('sfd-redo');
  function refreshUndoButtons() {
    if (undoBtn) {
      if (undoStack.length > 0) undoBtn.removeAttribute('disabled');
      else undoBtn.setAttribute('disabled', '');
    }
    if (redoBtn) {
      if (redoStack.length > 0) redoBtn.removeAttribute('disabled');
      else redoBtn.setAttribute('disabled', '');
    }
  }
  undoBtn.addEventListener('click', doUndo);
  redoBtn.addEventListener('click', doRedo);
  refreshUndoButtons();   // initial — both disabled

  // Multi-cell drag batching (RESEARCH Open Risk #1). JointJS emits
  // a flurry of `change:position` events during a drag — wrap them in
  // a single undo batch so one Ctrl+Z reverts the whole gesture.
  paper.on('element:pointerdown', function () { undoBeginBatch(); });
  paper.on('element:pointerup',   function () { undoEndBatch(); });

  // Keyboard shortcuts — Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z, Ctrl/Cmd+Y.
  // Guard against input-field focus and modal-open per RESEARCH §7.
  document.addEventListener('keydown', function (evt) {
    if (/INPUT|TEXTAREA|SELECT/.test(evt.target.tagName)) return;
    if (pickerState && pickerState.open) return;
    if (conflicted) return;   // Phase 9 D-08 — banner is showing
    var meta = evt.ctrlKey || evt.metaKey;
    if (!meta) return;
    var key = evt.key.toLowerCase();
    if (key === 'z' && !evt.shiftKey) {
      evt.preventDefault();
      doUndo();
    } else if ((key === 'z' && evt.shiftKey) || key === 'y') {
      evt.preventDefault();
      doRedo();
    }
  });

  // ──────────────────────────────────────────────────────────────
  // Selection (CNV-06) and keyboard delete (CNV-07).
  //
  //  - Plain click on an element/link: replace selection with that cell.
  //  - Shift+click: toggle the cell in/out of the selection set.
  //  - Blank click: clear selection.
  //  - Blank pointerdown + drag: rubber-band — selects all views inside
  //    the rectangle via paper.findViewsInArea(). Gated on
  //    !panState.spaceDown && evt.button === 0 so it never starts during
  //    a pan (CONTEXT D-08 + RESEARCH §8).
  //  - Delete / Backspace: remove the current selection in one undo batch.
  //
  // Selection visual is via CSS class `.is-selected` (plan 02 styles).
  // Multi-select bbox overlay uses `.sfd-multi-bbox` (plan 02 styles).
  // ──────────────────────────────────────────────────────────────

  var selectedSet = new Set();
  var multiBboxRect = null;   // SVG <rect> overlay for multi-select bbox

  function applySelectionVisuals() {
    graph.getCells().forEach(function (cell) {
      var view = paper.findViewByModel(cell);
      if (!view || !view.el) return;
      if (selectedSet.has(cell.id)) view.el.classList.add('is-selected');
      else view.el.classList.remove('is-selected');
    });
    // Plan 06's inspector hooks into this — see window.__sfd.selection below.
    if (typeof window.__sfd.onSelectionChanged === 'function') {
      window.__sfd.onSelectionChanged(Array.from(selectedSet));
    }
  }

  function redrawSelection() {
    applySelectionVisuals();
    // Multi-select bbox overlay
    if (multiBboxRect && multiBboxRect.parentNode) {
      multiBboxRect.parentNode.removeChild(multiBboxRect);
    }
    multiBboxRect = null;
    if (selectedSet.size > 1) {
      var cells = Array.from(selectedSet)
        .map(function (id) { return graph.getCell(id); })
        .filter(Boolean);
      if (cells.length > 1) {
        var bbox = graph.getCellsBBox(cells);
        if (bbox) {
          multiBboxRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          multiBboxRect.setAttribute('class', 'sfd-multi-bbox');
          multiBboxRect.setAttribute('x', String(bbox.x - 4));
          multiBboxRect.setAttribute('y', String(bbox.y - 4));
          multiBboxRect.setAttribute('width',  String(bbox.width + 8));
          multiBboxRect.setAttribute('height', String(bbox.height + 8));
          var vp = paper.viewport || paper.svg;
          if (vp && vp.appendChild) vp.appendChild(multiBboxRect);
        }
      }
    }
  }

  // Plain / shift click on an element or link.
  paper.on('element:pointerclick', function (elementView, evt) {
    var id = elementView.model.id;
    if (evt.shiftKey) {
      if (selectedSet.has(id)) selectedSet.delete(id); else selectedSet.add(id);
    } else {
      selectedSet.clear();
      selectedSet.add(id);
    }
    redrawSelection();
  });
  paper.on('link:pointerclick', function (linkView, evt) {
    var id = linkView.model.id;
    if (evt.shiftKey) {
      if (selectedSet.has(id)) selectedSet.delete(id); else selectedSet.add(id);
    } else {
      selectedSet.clear();
      selectedSet.add(id);
    }
    redrawSelection();
  });
  paper.on('blank:pointerclick', function () {
    selectedSet.clear();
    redrawSelection();
  });

  // Rubber-band drag on blank canvas — RESEARCH §8.
  // Gated against panState.spaceDown so space+drag is always a pan.
  paper.on('blank:pointerdown', function (evt, x, y) {
    if (panState.spaceDown || evt.button !== 0) return;
    var startLocal = { x: x, y: y };
    var rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('fill', 'rgba(13, 148, 136, 0.08)');   // accent at 8% opacity
    rect.setAttribute('stroke', '#0d9488');
    rect.setAttribute('stroke-width', '1');
    rect.setAttribute('stroke-dasharray', '4 3');
    rect.setAttribute('pointer-events', 'none');
    rect.setAttribute('x', String(x));
    rect.setAttribute('y', String(y));
    rect.setAttribute('width', '0');
    rect.setAttribute('height', '0');
    var vp = paper.viewport || paper.svg;
    if (vp && vp.appendChild) vp.appendChild(rect);

    function onMove(evt2) {
      var p = paper.clientToLocalPoint({ x: evt2.clientX, y: evt2.clientY });
      var x0 = Math.min(startLocal.x, p.x);
      var y0 = Math.min(startLocal.y, p.y);
      var w = Math.abs(p.x - startLocal.x);
      var h = Math.abs(p.y - startLocal.y);
      rect.setAttribute('x', String(x0));
      rect.setAttribute('y', String(y0));
      rect.setAttribute('width',  String(w));
      rect.setAttribute('height', String(h));
    }
    function onUp(evt2) {
      var p = paper.clientToLocalPoint({ x: evt2.clientX, y: evt2.clientY });
      var x0 = Math.min(startLocal.x, p.x);
      var y0 = Math.min(startLocal.y, p.y);
      var w = Math.abs(p.x - startLocal.x);
      var h = Math.abs(p.y - startLocal.y);
      if (rect.parentNode) rect.parentNode.removeChild(rect);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      if (w < 4 && h < 4) return;   // ignore tiny accidental drags
      var hits = paper.findViewsInArea({ x: x0, y: y0, width: w, height: h });
      if (!evt2.shiftKey) selectedSet.clear();
      hits.forEach(function (v) { if (v && v.model) selectedSet.add(v.model.id); });
      redrawSelection();
    }
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });

  // Keyboard delete — Delete or Backspace removes the current selection
  // in a single undo batch. Guarded against input-field focus and the
  // picker modal.
  document.addEventListener('keydown', function (evt) {
    if (/INPUT|TEXTAREA|SELECT/.test(evt.target.tagName)) return;
    if (pickerState && pickerState.open) return;
    if (conflicted) return;   // Phase 9 D-08 — banner is showing
    if (evt.key === 'Delete' || evt.key === 'Backspace') {
      var ids = Array.from(selectedSet);
      if (!ids.length) return;
      evt.preventDefault();
      undoBeginBatch();
      ids.forEach(function (id) {
        var cell = graph.getCell(id);
        if (cell) cell.remove();
      });
      undoEndBatch();
      selectedSet.clear();
      redrawSelection();
    }
  });

  // Re-apply selection visuals after JointJS re-renders (RESEARCH Open
  // Risk #4). `add` covers cell creation; `change:attrs` covers
  // attribute-driven re-paints (label edits, signal-type style swaps).
  // We DO NOT bind to `change:position` — that would re-paint constantly
  // during drags. Position changes don't re-create the DOM node, so the
  // .is-selected class survives them anyway.
  graph.on('add change:attrs', function () {
    applySelectionVisuals();
  });

  // ──────────────────────────────────────────────────────────────
  // Plan 06 — Connectors (SignalLink class + signal-type recipe).
  // CON-01, CON-02, CON-03, CON-04, CON-05.
  // RESEARCH §§11-15, CONTEXT D-16 (locked signal-type table).
  // ──────────────────────────────────────────────────────────────

  // SignalLink — custom orthogonal-routed link with signal-type props (CON-01, CON-02, CON-05, CON-06).
  // joint.shapes.standard.Link.extend gives us the `line` SVG sub-element that all attrs target.
  joint.shapes.showstack.SignalLink = joint.shapes.standard.Link.extend({
    defaults: joint.util.deepSupplement({
      type: 'showstack.SignalLink',
      // `manhattan` with padding produces a longer initial segment off the source
      // edge — separates visually when several connectors share the same port edge.
      router: { name: 'manhattan', args: { padding: 24, step: 20 } },
      connector: { name: 'rounded', args: { radius: 4 } },
      attrs: {
        line: {
          stroke: '#1a1a1a',
          strokeWidth: 2,
          strokeDasharray: 'none',
          sourceMarker: { type: 'none' },
          targetMarker: {
            type: 'path',
            d: 'M 10 -5 0 0 10 5 z',
            fill: '#1a1a1a',
            stroke: 'none',
          },
        },
      },
      // Custom property bag — JointJS toJSON serializes everything under cell.attributes,
      // so these survive the save/reload round-trip.
      signalType:   'analog',
      direction:    'forward',
      circuitLabel: '',
    }, joint.shapes.standard.Link.prototype.defaults),
  });

  // Signal-type style table — CONTEXT D-16. Each entry: hex stroke + width + dash pattern.
  // AVB + Network added during Phase 8 UAT (solid, distinct hues).
  var SIGNAL_TYPE_STYLES = {
    analog:   { stroke: '#1a1a1a', strokeWidth: 2,   strokeDasharray: 'none'      },
    AES:      { stroke: '#1565c0', strokeWidth: 2,   strokeDasharray: 'none'      },
    Dante:    { stroke: '#00bcd4', strokeWidth: 2,   strokeDasharray: '6 4'       },
    MADI:     { stroke: '#ef6c00', strokeWidth: 2.5, strokeDasharray: '10 3 3 3'  },
    intercom: { stroke: '#7b1fa2', strokeWidth: 2,   strokeDasharray: '2 4'       },
    AVB:      { stroke: '#dc2626', strokeWidth: 2,   strokeDasharray: 'none'      },
    Network:  { stroke: '#16a34a', strokeWidth: 2,   strokeDasharray: 'none'      },
  };

  function applySignalType(link, type) {
    var s = SIGNAL_TYPE_STYLES[type];
    if (!s) return;   // unknown types silently ignored (T-08-41)
    link.attr('line/stroke', s.stroke);
    link.attr('line/strokeWidth', s.strokeWidth);
    link.attr('line/strokeDasharray', s.strokeDasharray);
    link.prop('signalType', type);
    // Recolor the target marker to match the new stroke (only when forward direction).
    if (link.prop('direction') !== 'bidirectional') {
      link.attr('line/targetMarker', {
        type: 'path', d: 'M 10 -5 0 0 10 5 z', fill: s.stroke, stroke: 'none',
      });
    }
  }

  function applyDirection(link, direction) {
    link.prop('direction', direction);
    if (direction === 'bidirectional') {
      // Both markers stripped — pure line, both ends.
      link.attr('line/sourceMarker', { type: 'none' });
      link.attr('line/targetMarker', { type: 'none' });
    } else {
      // Forward direction (default): target arrow only, colored to match stroke.
      link.attr('line/sourceMarker', { type: 'none' });
      var sType = link.prop('signalType') || 'analog';
      var stroke = (SIGNAL_TYPE_STYLES[sType] || SIGNAL_TYPE_STYLES.analog).stroke;
      link.attr('line/targetMarker', {
        type: 'path', d: 'M 10 -5 0 0 10 5 z', fill: stroke, stroke: 'none',
      });
    }
  }

  function applyCircuitLabel(link, label) {
    link.prop('circuitLabel', label || '');
    if (!label) {
      link.labels([]);   // empty array clears all labels
      return;
    }
    link.labels([{
      position: { distance: 0.5, offset: -10 },
      attrs: {
        labelText: {
          text: label,
          fill: '#111',
          fontSize: 11,
          fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
          fontWeight: 500,
          textAnchor: 'middle',
          textVerticalAnchor: 'middle',
        },
        labelRect: {
          fill: 'rgba(255,255,255,0.85)',   // 85% white pill background per UI-SPEC
          stroke: '#aaa',
          strokeWidth: 0.5,
          ref: 'labelText',
          refWidth: '110%', refHeight: '110%',
          refX: '-5%', refY: '-5%',
        },
      },
      markup: [
        { tagName: 'rect', selector: 'labelRect' },
        { tagName: 'text', selector: 'labelText' },
      ],
    }]);
  }

  // (Paper-level connector options — linkPinning, snapLinks, defaultLink,
  // validateMagnet, validateConnection — are now set at Paper construction
  // above. Post-construction `paper.options.X = Y` was unreliable in
  // @joint/core 4.x, producing pinned links + accepted self-loops.)

  // Link tools — vertices for midpoint waypoints (CON-04), source/target anchors,
  // and a Remove handle for the connector. Attached on link click; cleared on blank click.
  paper.on('link:pointerclick', function (linkView) {
    if (linkView.hasTools()) return;   // avoid stacking duplicate tool sets
    var tools = new joint.dia.ToolsView({
      tools: [
        // Vertices: drag the midpoint dot of each existing vertex.
        new joint.linkTools.Vertices(),
        // Segments: drag the midpoint of each STRAIGHT SEGMENT to slide it
        // perpendicular — adjusts knuckle length / direction of each leg.
        new joint.linkTools.Segments(),
        new joint.linkTools.SourceAnchor(),
        new joint.linkTools.TargetAnchor(),
        new joint.linkTools.Remove({ distance: -30 }),
      ],
    });
    linkView.addTools(tools);
  });

  // NOTE: plan 05 already registers a `blank:pointerdown` listener for rubber-band selection.
  // JointJS event emitter supports multiple listeners on the same event; the rubber-band
  // listener runs first (registered earlier), then this `removeTools()` runs. Both coexist.
  paper.on('blank:pointerdown', function () { paper.removeTools(); });

  // Defensive re-apply on cell add — covers both new links from the user AND links coming
  // back from `fromJSON` on diagram reload (the `add` event fires per cell during load).
  // Re-applying ensures stroke/dasharray/markers/label match the saved signalType/direction/label.
  graph.on('add', function (cell, _coll, _opts) {
    if (cell.isLink && cell.isLink()) {
      var type = cell.prop('signalType') || 'analog';
      applySignalType(cell, type);
      applyDirection(cell, cell.prop('direction') || 'forward');
      var label = cell.prop('circuitLabel') || '';
      if (label) applyCircuitLabel(cell, label);
    }
  });

  // ──────────────────────────────────────────────────────────────
  // Phase 9 — Orphan ghost render hook (SHP-07, D-15).
  // CSS work (Section 11 of signal_flow.css) is keyed on:
  //   joint-orphan="true"          on the orphaned element's root <g>
  //   joint-orphan-attached="true" on any link attached to an orphan
  // The server's _enrich_nodes() (Phase 9 09-01) sets the cell.showstack.isOrphan
  // boolean on every linked cell when state is fetched; this block syncs that
  // model property to the DOM attribute.
  // ──────────────────────────────────────────────────────────────

  function applyOrphanState(cell) {
    if (!cell || !cell.isElement || !cell.isElement()) return;
    var view = paper.findViewByModel(cell);
    if (!view || !view.el) return;
    var sub = cell.prop('showstack') || {};
    if (sub.isOrphan === true) {
      view.el.setAttribute('joint-orphan', 'true');
    } else {
      view.el.removeAttribute('joint-orphan');
    }
  }

  function isCellOrphan(cell) {
    if (!cell) return false;
    var sub = cell.prop('showstack') || {};
    return sub.isOrphan === true;
  }

  function applyAttachedOrphanState(link) {
    if (!link || !link.isLink || !link.isLink()) return;
    var view = paper.findViewByModel(link);
    if (!view || !view.el) return;
    var src = link.getSourceElement();
    var tgt = link.getTargetElement();
    if (isCellOrphan(src) || isCellOrphan(tgt)) {
      view.el.setAttribute('joint-orphan-attached', 'true');
    } else {
      view.el.removeAttribute('joint-orphan-attached');
    }
  }

  // Initial load via fromJSON: views may not be rendered yet when the `add`
  // event fires for each cell. Defer the attribute write to next tick so
  // paper.findViewByModel() can find the rendered view.
  function applyOrphanStateDeferred(cell) {
    setTimeout(function () { applyOrphanState(cell); }, 0);
  }
  function applyAttachedOrphanStateDeferred(link) {
    setTimeout(function () { applyAttachedOrphanState(link); }, 0);
  }

  graph.on('add', function (cell) {
    if (cell.isElement && cell.isElement()) {
      applyOrphanStateDeferred(cell);
    } else if (cell.isLink && cell.isLink()) {
      applyAttachedOrphanStateDeferred(cell);
    }
  });

  // Re-link or server-enrich changes -> re-evaluate both the element AND every
  // link attached to it (the attached-orphan visual must clear when the
  // underlying element goes live again).
  graph.on('change:showstack', function (cell) {
    if (!cell) return;
    if (cell.isElement && cell.isElement()) {
      applyOrphanState(cell);
      // Re-evaluate every link in the graph that has this cell as an endpoint.
      graph.getConnectedLinks(cell).forEach(function (link) {
        applyAttachedOrphanState(link);
      });
    }
  });

  // Link endpoint swaps -> re-evaluate the link's attached-orphan attribute.
  graph.on('change:source change:target', function (cell) {
    if (cell && cell.isLink && cell.isLink()) applyAttachedOrphanState(cell);
  });

  // ──────────────────────────────────────────────────────────────
  // Plan 06 — Right-side inspector (auto-show on connector select).
  // CON-02 / CON-05 / CON-06 user-facing field wiring.
  // CONTEXT D-07 (auto-show/hide rule), UI-SPEC "Inspector Panel".
  // ──────────────────────────────────────────────────────────────

  var inspectorEl       = document.getElementById('sfd-inspector');
  var inspectorCloseBtn = document.getElementById('sfd-inspector-close');
  var signalTypeSelect  = document.getElementById('sfd-signal-type');
  var dirForwardBtn     = document.getElementById('sfd-dir-forward');
  var dirBidirBtn       = document.getElementById('sfd-dir-bidir');
  var circuitLabelInput = document.getElementById('sfd-circuit-label');

  // The link model currently bound to the inspector (null when hidden).
  var inspectorCurrentLink = null;

  function showInspector() {
    if (!inspectorEl) return;
    inspectorEl.removeAttribute('hidden');
    // CLAUDE.md override rule — admin-template DOM nodes need !important.
    inspectorEl.style.setProperty('display', 'block', 'important');
  }
  function hideInspector() {
    if (!inspectorEl) return;
    inspectorEl.setAttribute('hidden', '');
    inspectorEl.style.setProperty('display', 'none', 'important');
    inspectorCurrentLink = null;
    inspectorCurrentNode = null;    // Phase 9 — clear node ref too
  }

  function syncInspectorFromLink(link) {
    // Populate field values from the link model (no events fired — pure DOM write).
    signalTypeSelect.value = link.prop('signalType') || 'analog';
    var dir = link.prop('direction') || 'forward';
    if (dir === 'bidirectional') {
      dirForwardBtn.setAttribute('data-active', 'false');
      dirBidirBtn.setAttribute('data-active', 'true');
    } else {
      dirForwardBtn.setAttribute('data-active', 'true');
      dirBidirBtn.setAttribute('data-active', 'false');
    }
    circuitLabelInput.value = link.prop('circuitLabel') || '';
  }

  // Phase 9 D-16 — Selection-change widened to node mode.
  window.__sfd.onSelectionChanged = function (selectedIds) {
    if (selectedIds.length === 1) {
      var cell = graph.getCell(selectedIds[0]);
      if (cell && cell.isLink && cell.isLink()) {
        setInspectorMode('connector', cell);
        showInspector();
        return;
      }
      if (cell && cell.isElement && cell.isElement()) {
        setInspectorMode('node', cell);
        showInspector();
        return;
      }
    }
    hideInspector();
  };

  // Field handlers — every change writes to the link model AND updates the live SVG
  // via the helpers defined in Task 1 (applySignalType / applyDirection / applyCircuitLabel).
  if (signalTypeSelect) {
    signalTypeSelect.addEventListener('change', function () {
      if (!inspectorCurrentLink) return;
      applySignalType(inspectorCurrentLink, signalTypeSelect.value);
      scheduleAutosave();   // Phase 9 D-01 — inspector mutation triggers autosave
    });
  }

  if (dirForwardBtn) {
    dirForwardBtn.addEventListener('click', function () {
      if (!inspectorCurrentLink) return;
      applyDirection(inspectorCurrentLink, 'forward');
      dirForwardBtn.setAttribute('data-active', 'true');
      dirBidirBtn.setAttribute('data-active', 'false');
      scheduleAutosave();   // Phase 9 D-01
    });
  }
  if (dirBidirBtn) {
    dirBidirBtn.addEventListener('click', function () {
      if (!inspectorCurrentLink) return;
      applyDirection(inspectorCurrentLink, 'bidirectional');
      dirForwardBtn.setAttribute('data-active', 'false');
      dirBidirBtn.setAttribute('data-active', 'true');
      scheduleAutosave();   // Phase 9 D-01
    });
  }

  // Circuit-label input — debounced 200ms during typing AND committed on blur.
  // Prevents one undo-stack record per keystroke (T-08-30 memory hygiene).
  // Plan 05's keyboard handler already excludes /INPUT|TEXTAREA|SELECT/ so Backspace
  // here doesn't delete the connector being edited.
  var circuitLabelTimer = null;
  if (circuitLabelInput) {
    circuitLabelInput.addEventListener('input', function () {
      if (!inspectorCurrentLink) return;
      if (circuitLabelTimer) clearTimeout(circuitLabelTimer);
      var snapshot = inspectorCurrentLink;
      circuitLabelTimer = setTimeout(function () {
        circuitLabelTimer = null;
        if (snapshot) applyCircuitLabel(snapshot, circuitLabelInput.value);
        scheduleAutosave();   // Phase 9 D-01 — 1500ms autosave debounce coalesces keystrokes
      }, 200);
    });
    circuitLabelInput.addEventListener('blur', function () {
      if (circuitLabelTimer) { clearTimeout(circuitLabelTimer); circuitLabelTimer = null; }
      if (inspectorCurrentLink) applyCircuitLabel(inspectorCurrentLink, circuitLabelInput.value);
      scheduleAutosave();   // Phase 9 D-01
    });
  }

  if (inspectorCloseBtn) {
    inspectorCloseBtn.addEventListener('click', function () {
      // Clear selection — plan 05's onSelectionChanged then fires with [] and hides.
      if (window.__sfd.selection && typeof window.__sfd.selection.clear === 'function') {
        window.__sfd.selection.clear();
      }
      hideInspector();
    });
  }

  // Defensive — ensure inspector is hidden on initial page load.
  // The template renders with the `hidden` attribute set, but a previous render
  // could leave inline styles; this normalizes both.
  hideInspector();

  // ──────────────────────────────────────────────────────────────
  // Phase 9 D-16 — Node-mode inspector (SHP-07 re-link UX).
  //
  // Extends the Phase 8 #sfd-inspector panel to ALSO render a node-mode
  // sub-block with `Re-link equipment` + `Delete shape` buttons. The Phase 8
  // connector fields are hidden when a node is selected; the Phase 9 node
  // sub-block is built lazily the first time setInspectorMode('node', …) runs.
  // ──────────────────────────────────────────────────────────────

  var inspectorHeader = inspectorEl ? inspectorEl.querySelector('.sfd-inspector-header h3') : null;
  // Cache references to the Phase 8 connector-mode field rows (the three .sfd-field divs).
  var connectorFieldRows = inspectorEl ? Array.from(inspectorEl.querySelectorAll('.sfd-field')) : [];
  var nodeModeBlock = null;           // built on first 'node' call
  var nodeRelinkBtn = null;
  var nodeDeleteBtn = null;
  var inspectorCurrentNode = null;    // the cell currently shown in node mode

  function buildNodeModeBlock() {
    if (!inspectorEl) return;
    nodeModeBlock = document.createElement('div');
    nodeModeBlock.className = 'sfd-field sfd-field--node-actions';
    nodeModeBlock.setAttribute('data-mode', 'node');
    nodeModeBlock.style.setProperty('display', 'none', 'important');

    nodeRelinkBtn = document.createElement('button');
    nodeRelinkBtn.type = 'button';
    nodeRelinkBtn.id = 'sfd-node-relink';
    nodeRelinkBtn.textContent = 'Re-link equipment';
    nodeRelinkBtn.style.setProperty('display', 'block', 'important');
    nodeRelinkBtn.style.setProperty('width', '100%', 'important');
    nodeRelinkBtn.style.setProperty('margin-bottom', '8px', 'important');
    nodeRelinkBtn.style.setProperty('padding', '8px 12px', 'important');
    nodeRelinkBtn.style.setProperty('cursor', 'pointer', 'important');

    nodeDeleteBtn = document.createElement('button');
    nodeDeleteBtn.type = 'button';
    nodeDeleteBtn.id = 'sfd-node-delete';
    nodeDeleteBtn.textContent = 'Delete shape';
    nodeDeleteBtn.style.setProperty('display', 'block', 'important');
    nodeDeleteBtn.style.setProperty('width', '100%', 'important');
    nodeDeleteBtn.style.setProperty('padding', '8px 12px', 'important');
    nodeDeleteBtn.style.setProperty('cursor', 'pointer', 'important');

    nodeModeBlock.appendChild(nodeRelinkBtn);
    nodeModeBlock.appendChild(nodeDeleteBtn);
    inspectorEl.appendChild(nodeModeBlock);

    nodeRelinkBtn.addEventListener('click', function () {
      if (!inspectorCurrentNode) return;
      var type = inspectorCurrentNode.get('type') || '';
      var shapeType = type.split('.').pop();  // 'showstack.Console' -> 'Console'
      if (typeof window.__sfd.openEquipmentPicker === 'function') {
        window.__sfd.openEquipmentPicker(shapeType, inspectorCurrentNode);
      }
    });

    nodeDeleteBtn.addEventListener('click', function () {
      if (!inspectorCurrentNode) return;
      var cell = inspectorCurrentNode;
      if (window.__sfd.undo && typeof window.__sfd.undo.beginBatch === 'function') {
        window.__sfd.undo.beginBatch();
        cell.remove();
        window.__sfd.undo.endBatch();
      } else {
        cell.remove();
      }
      if (window.__sfd.selection && typeof window.__sfd.selection.clear === 'function') {
        window.__sfd.selection.clear();
      }
      inspectorCurrentNode = null;
      hideInspector();
    });
  }

  function setInspectorMode(mode, cell) {
    if (!inspectorEl) return;
    if (!nodeModeBlock) buildNodeModeBlock();

    if (mode === 'connector') {
      if (inspectorHeader) inspectorHeader.textContent = 'Connector';
      connectorFieldRows.forEach(function (row) {
        row.style.setProperty('display', 'block', 'important');
      });
      if (nodeModeBlock) nodeModeBlock.style.setProperty('display', 'none', 'important');
      inspectorCurrentLink = cell;
      inspectorCurrentNode = null;
      syncInspectorFromLink(cell);
    } else if (mode === 'node') {
      if (inspectorHeader) inspectorHeader.textContent = 'Node';
      connectorFieldRows.forEach(function (row) {
        row.style.setProperty('display', 'none', 'important');
      });
      nodeModeBlock.style.setProperty('display', 'block', 'important');
      inspectorCurrentNode = cell;
      inspectorCurrentLink = null;
      // Hide the Re-link button when the cell has no equipment GFK
      // (pure Generic shape with no contentTypeId — nothing to relink to).
      var prop = cell.prop('showstack') || {};
      var hasLink = !!(prop.contentTypeId);
      if (nodeRelinkBtn) {
        nodeRelinkBtn.style.setProperty(
          'display', hasLink ? 'block' : 'none', 'important'
        );
      }
    }
  }

  // ──────────────────────────────────────────────────────────────
  // Phase 9 — Autosave controller.
  // Replaces the Phase 8 manual-save flow. The #sfd-save button
  // was removed by template plan 09-02; #sfd-save-status is now the
  // only persistence affordance (clickable in the 'error' state).
  //
  //   D-01: graph events trigger; mid-drag positions do not
  //   D-02: 1500ms trailing debounce
  //   D-03: clickable status span retries on error
  //   D-04: locked three-state copy
  //   D-05: If-Match: <currentVersion> on every full save
  //   D-06: server returns 409 on stale version
  //   D-08: 409 -> reveal banner + lock canvas + cancel debounce
  //   D-09/D-10/D-11: keepalive flush on visibilitychange + pagehide
  // ──────────────────────────────────────────────────────────────

  var saveStatusEl       = document.getElementById('sfd-save-status');
  var conflictBannerEl   = document.getElementById('sfd-conflict-banner');
  var conflictReloadBtn  = document.getElementById('sfd-conflict-reload');

  var diagramDirty        = false;
  var savingNow           = false;   // in-flight POST guard
  var conflicted          = false;   // 409 lockout — true freezes all save paths
  var autosaveTimer       = null;
  var lastFailedPayload   = null;    // for the clickable-retry path (D-03)

  // D-04 — locked three-state copy. Do NOT paraphrase. Punctuation matters:
  //   'All changes saved.' has a trailing period.
  //   'Saving…' uses U+2026 (single ellipsis char), NOT three dots.
  //   'Save failed — retry' uses U+2014 em-dash, NOT a hyphen.
  function setSaveStatus(state) {
    if (!saveStatusEl) return;
    saveStatusEl.classList.remove('is-saving', 'is-error');
    if (state === 'saved') {
      saveStatusEl.textContent = 'All changes saved.';
    } else if (state === 'saving') {
      saveStatusEl.textContent = 'Saving…';
      saveStatusEl.classList.add('is-saving');
    } else if (state === 'error') {
      saveStatusEl.textContent = 'Save failed — retry';
      saveStatusEl.classList.add('is-error');
    }
  }

  function scheduleAutosave() {
    if (conflicted) return;
    diagramDirty = true;
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(flushAutosave, 1500);   // D-02
  }

  function flushAutosave(opts) {
    opts = opts || {};
    if (autosaveTimer) { clearTimeout(autosaveTimer); autosaveTimer = null; }
    if (!diagramDirty) return Promise.resolve();
    if (conflicted)    return Promise.resolve();
    if (savingNow) return Promise.resolve();

    savingNow = true;
    setSaveStatus('saving');

    var payloadObj = {
      canvas_state: graph.toJSON(),
      viewport: {
        x: currentViewport.x,
        y: currentViewport.y,
        scale: currentViewport.scale,
        snapEnabled: currentViewport.snapEnabled,
      },
    };

    var fetchOpts = {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        'If-Match': String(currentVersion),   // D-05
      },
      body: JSON.stringify(payloadObj),
    };
    if (opts.keepalive) fetchOpts.keepalive = true;   // D-10

    return fetch(autosaveUrl, fetchOpts).then(function (r) {
      return r.json().then(function (data) {
        return { status: r.status, data: data };
      }).catch(function () {
        // Body was not JSON — synthesize an empty data object.
        return { status: r.status, data: {} };
      });
    }).then(function (resp) {
      if (resp.status === 200 && resp.data && resp.data.ok) {
        currentVersion    = resp.data.version || (currentVersion + 1);
        diagramDirty      = false;
        savingNow         = false;
        lastFailedPayload = null;
        setSaveStatus('saved');
        return;
      }
      if (resp.status === 409) {
        // D-06 / D-08 — version conflict OR missing/invalid If-Match.
        savingNow = false;
        showConflictBanner();
        return;
      }
      if (resp.status === 422) {
        savingNow = false;
        lastFailedPayload = payloadObj;
        setSaveStatus('error');
        showToast(resp.data && resp.data.error
          ? resp.data.error
          : "Couldn't save — equipment reference is out of project.", 'error');
        return;
      }
      // Generic failure (403 Viewer block, 400 malformed, 500, etc.)
      savingNow = false;
      lastFailedPayload = payloadObj;
      setSaveStatus('error');
      showToast((resp.data && resp.data.error) || 'Save failed. Please try again.', 'error');
    }).catch(function () {
      // Network error
      savingNow = false;
      lastFailedPayload = payloadObj;
      setSaveStatus('error');
      showToast('Network error. Try again.', 'error');
    });
  }

  // D-03 — clickable status span retries the last failed save.
  if (saveStatusEl) {
    saveStatusEl.addEventListener('click', function () {
      if (!saveStatusEl.classList.contains('is-error')) return;
      diagramDirty = true;   // re-arm
      flushAutosave({ force: true });
    });
  }

  // D-07 / D-08 — 409 banner reveal + canvas lock + debounce cancel.
  function showConflictBanner() {
    conflicted = true;
    if (autosaveTimer) { clearTimeout(autosaveTimer); autosaveTimer = null; }
    if (conflictBannerEl) {
      conflictBannerEl.removeAttribute('hidden');
      // CLAUDE.md override rule — admin-template DOM nodes need !important.
      conflictBannerEl.style.setProperty('display', 'flex', 'important');
    }
    // Lock the canvas — pointer events off the JointJS paper. Toolbar
    // zoom/pan/snap stay live for inspection (D-08).
    if (paperEl) paperEl.style.setProperty('pointer-events', 'none', 'important');
    // Persistent error chrome on the status span so the user knows their
    // edits are not being saved.
    setSaveStatus('error');
  }
  if (conflictReloadBtn) {
    conflictReloadBtn.addEventListener('click', function () {
      window.location.reload();
    });
  }

  // D-01 — graph events that trigger autosave. Note: change:position is NOT
  // listed here. Mid-drag position events are intentionally excluded
  // (PITFALLS.md §6 "autosave flooding"); only the element:pointerup
  // drag-end below fires the debounce for moves.
  graph.on('add remove change:source change:target', scheduleAutosave);
  paper.on('element:pointerup', scheduleAutosave);

  // D-09 / D-10 / D-11 — keepalive flush on tab-hide / page-hide.
  // We intentionally avoid the pre-unload event (browser cancels the fetch
  //   — PITFALLS.md §3) and navigator.send_beacon (64 KB cap — PITFALLS.md §6).
  function maybeKeepaliveFlush() {
    if (!diagramDirty) return;
    if (savingNow)     return;   // in-flight will land it
    if (conflicted)    return;   // banner is showing
    flushAutosave({ keepalive: true }).catch(function () {
      // Keepalive fetch failed (network down on hide). Re-schedule a normal
      // debounce so the next visible event gets another attempt.
      scheduleAutosave();
    });
  }
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') maybeKeepaliveFlush();
  });
  window.addEventListener('pagehide', maybeKeepaliveFlush);

  // Normalize initial state — clean slate on every page render.
  setSaveStatus('saved');

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
  // Plan 05 undo handoff — plan 06's manual Save can wrap multi-step writes
  // in beginBatch/endBatch so one Ctrl+Z reverts the whole gesture.
  window.__sfd.undo = {
    undo: doUndo, redo: doRedo,
    beginBatch: undoBeginBatch, endBatch: undoEndBatch,
    record: undoRecord,
  };
  // Plan 05 selection handoff — plan 06's inspector reads getSelected()
  // and sets onSelectionChanged to be notified when the selection changes.
  window.__sfd.selection = {
    getSelected: function () { return Array.from(selectedSet); },
    clear: function () { selectedSet.clear(); redrawSelection(); },
    // onSelectionChanged hook — plan 06 sets this to drive inspector show/hide.
  };
  // Phase 9 manual-flush seam — Cmd+S shortcut (deferred to v2.3) or any
  // future caller can force an immediate save.
  window.__sfd.save = function () { return flushAutosave({ force: true }); };

  // Phase 10 will: circuit-label autocomplete widget, PNG export button.
})();
