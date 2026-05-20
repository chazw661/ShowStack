// planner/static/planner/js/signal_flow_editor.js
//
// Signal Flow Diagrammer — editor controller.
// Phase 7: STUB only. Confirms vendor bundles loaded; canvas init lands in Phase 8.
//
// IMPORTANT: All DOM color/style writes use
//     el.style.setProperty(prop, value, 'important')
// Direct property assignment (the dot-style.color form) silently fails
// against Django admin's !important rules (CLAUDE.md > Coding Conventions).
//
// Note: JointJS canvas SVG elements (added in Phase 8) are NOT in the admin DOM
// and are unaffected by the !important rule. This guidance only matters for any
// toolbar / modal HTML rendered by Django admin templates.

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

  // Confirm JointJS UMD bundle loaded and exposes `joint` global.
  if (typeof joint === 'undefined') {
    console.error('[SFD] joint is not defined — check vendor/joint.min.js load order in editor.html');
    return;
  }

  // Confirm html-to-image bundle loaded (Phase 10 needs this).
  // Some UMD builds expose `htmlToImage`; some expose individual functions on window.
  // For now, just log whichever shape is present.
  var h2iAvailable = (typeof htmlToImage !== 'undefined') ||
                     (typeof window.htmlToImage !== 'undefined');

  console.log('[SFD] JointJS ready — version', joint.version || '(unknown)',
              '— diagram', diagramId,
              '— html-to-image:', h2iAvailable ? 'loaded' : 'MISSING',
              '— stateUrl:', stateUrl,
              '— autosaveUrl:', autosaveUrl);

  // Phase 8 will: graph + paper init, graph.fromJSON(stateUrl), shape picker.
  // Phase 9 will: autosave debounce on graph events, keepalive fetch on visibilitychange.
  // Phase 10 will: circuit-label autocomplete widget, PNG export button.
})();
