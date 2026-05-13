/* Multitrack Session Builder editor controller (Phase 1 of v2.0).
 *
 * Attaches behavior to the DOM hooks declared in Plan 05's templates:
 * - Sortable drag-reorder on .mts-track-list
 * - Channel picker modal (5 tabs + manual queue)
 * - Inline color popover (12-swatch palette + custom hex)
 * - Track row inline label edit, enable, remove
 * - Dashboard per-card dropdown menu (duplicate / rename / delete)
 *
 * IMPORTANT: All DOM color/style writes use
 *     el.style.setProperty(prop, value, 'important')
 * Direct property assignment (the dot-style.color form) silently fails
 * against Django admin's !important rules (CLAUDE.md > Coding Conventions).
 *
 * NOTE: mtsToggleNotes / mtsSaveNotes are NOT defined here. Per checker
 * WARNING 3, Phase 1 ships notes as DISPLAY-ONLY on existing tracks
 * (Plan 05 _track_row.html renders a plain <span>, no input affordance,
 * and there is no multitrack_set_notes endpoint in Plan 04). Notes are
 * still WRITABLE at creation time via the picker manual-tab inline form.
 * When v2.0.1 adds the set_notes endpoint, mirror mtsSaveLabel here.
 */

(function () {
  'use strict';

  // ──────────────────────────────────────────────────────────────
  // Globals + helpers
  // ──────────────────────────────────────────────────────────────

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function csrfToken() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
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

  // Toast (UI-SPEC § Toasts) — minimal passive notification.
  function showToast(message, level) {
    const t = document.createElement('div');
    t.className = 'mts-toast mts-toast--' + (level || 'info');
    t.textContent = message;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add('mts-toast--hide'); }, 3000);
    setTimeout(function () { t.remove(); }, 3500);
  }

  // ──────────────────────────────────────────────────────────────
  // Sortable drag-reorder (TRK-05)
  // ──────────────────────────────────────────────────────────────

  function initSortable() {
    const list = $('.mts-track-list');
    if (!list || typeof Sortable === 'undefined') return;
    Sortable.create(list, {
      handle: '.mts-drag',
      animation: 150,
      onEnd: function () {
        const ids = $$('[data-track-id]', list).map(function (el) {
          return parseInt(el.dataset.trackId, 10);
        }).filter(function (n) { return !isNaN(n); });
        const sessionId = list.dataset.sessionId;
        postJSON('/audiopatch/multitrack/' + sessionId + '/reorder/', { ordered_ids: ids })
          .then(function (resp) {
            if (resp.status !== 200 || !resp.data.ok) {
              showToast("Couldn't save track order. Check your connection and reload the page.", 'error');
              return;
            }
            // Optimistic UI: renumber #1..#N client-side
            $$('.mts-track-num', list).forEach(function (el, idx) {
              el.textContent = '#' + (idx + 1);
            });
          })
          .catch(function () {
            showToast("Couldn't save track order. Check your connection and reload the page.", 'error');
          });
      },
    });
  }

  // ──────────────────────────────────────────────────────────────
  // Picker modal (TRK-06, TRK-07, TRK-09 / D-07..D-11)
  // ──────────────────────────────────────────────────────────────

  let pickerData = null;             // parsed once from #mts-picker-data
  let pickerSelections = { inputs: new Set(), aux: new Set(), matrix: new Set(), stereo: new Set() };
  let pickerManualQueue = [];        // [{label, color, notes}, ...]
  let pickerActiveTab = 'inputs';

  function loadPickerData() {
    if (pickerData !== null) return pickerData;
    const el = $('#mts-picker-data');
    if (!el) { pickerData = { inputs: [], aux: [], matrix: [], stereo: [] }; return pickerData; }
    try {
      pickerData = JSON.parse(el.textContent);
    } catch (e) {
      pickerData = { inputs: [], aux: [], matrix: [], stereo: [] };
    }
    return pickerData;
  }

  function renderPickerLists() {
    const data = loadPickerData();
    ['inputs', 'aux', 'matrix', 'stereo'].forEach(function (tab) {
      const list = $('[data-pick-list="' + tab + '"]');
      const empty = $('[data-panel="' + tab + '"] [data-empty-message]') ||
                    $('[data-panel="' + tab + '"] .mts-pick-empty');
      if (!list) return;
      // Clearing list contents — empty-string assignment ONLY.
      // (No user data ever inserted via this property anywhere in this file.)
      list.innerHTML = '';
      const channels = data[tab] || [];
      if (channels.length === 0) {
        if (empty) {
          // UI-SPEC: "All {type} channels are already in this session." vs
          // "This console has no {type} channels." — server-side
          // _build_picker_data already excluded in-use rows, so we can't
          // distinguish here. Default to the no-channels copy.
          empty.textContent = empty.dataset.emptyNoChannels || empty.textContent;
          empty.style.display = 'block';
        }
        return;
      }
      if (empty) empty.style.display = 'none';
      channels.forEach(function (ch) {
        const row = document.createElement('label');
        row.className = 'mts-pick-row';
        row.dataset.sourceType = tab.replace(/s$/, '');  // 'inputs' -> 'input'
        row.dataset.sourceId = ch.id;

        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'mts-pick-checkbox';
        cb.checked = pickerSelections[tab].has(ch.id);
        cb.addEventListener('change', function () {
          if (cb.checked) pickerSelections[tab].add(ch.id);
          else pickerSelections[tab].delete(ch.id);
          updateCommitButton();
        });

        const num = document.createElement('span');
        num.className = 'mts-pick-num';
        num.textContent = ch.channel_number || '';

        const lbl = document.createElement('span');
        lbl.className = 'mts-pick-name';
        lbl.textContent = ch.label;   // textContent — XSS-safe

        row.appendChild(cb);
        row.appendChild(num);
        row.appendChild(lbl);
        list.appendChild(row);
      });
    });
    updateTabCounts();
    updateCommitButton();
  }

  function updateTabCounts() {
    const data = loadPickerData();
    ['inputs', 'aux', 'matrix', 'stereo'].forEach(function (tab) {
      const tabEl = $('[data-tab="' + tab + '"]');
      if (!tabEl) return;
      const count = (data[tab] || []).length;
      const span = tabEl.querySelector('[data-tab-count]');
      if (span) span.textContent = ' (' + count + ' available)';
    });
  }

  function updateCommitButton() {
    const total = pickerSelections.inputs.size + pickerSelections.aux.size +
                  pickerSelections.matrix.size + pickerSelections.stereo.size +
                  pickerManualQueue.length;
    const btn = $('[data-commit-btn]');
    if (!btn) return;
    btn.textContent = 'Add ' + total + ' selected';
    btn.style.setProperty('opacity', total === 0 ? '0.5' : '1', 'important');
    btn.disabled = total === 0;
  }

  window.mtsOpenPicker = function (tab) {
    renderPickerLists();
    window.mtsSwitchTab(tab || 'inputs');
    const overlay = $('#mts-picker-overlay');
    if (overlay) overlay.style.setProperty('display', 'flex', 'important');
    setTimeout(function () { const f = $('.mts-filter-input'); if (f) f.focus(); }, 100);
  };

  window.mtsClosePicker = function () {
    const overlay = $('#mts-picker-overlay');
    if (overlay) overlay.style.setProperty('display', 'none', 'important');
    // Reset selection state on close
    pickerSelections = { inputs: new Set(), aux: new Set(), matrix: new Set(), stereo: new Set() };
    pickerManualQueue = [];
    const list = $('[data-manual-list]'); if (list) list.innerHTML = '';
    const queued = $('[data-manual-queued]'); if (queued) queued.textContent = '0 manual tracks queued';
    updateCommitButton();
  };

  window.mtsSwitchTab = function (tab) {
    pickerActiveTab = tab;
    $$('.mts-tab').forEach(function (t) {
      t.classList.toggle('mts-tab--active', t.dataset.tab === tab);
    });
    $$('.mts-tab-panel').forEach(function (p) {
      p.style.setProperty('display', (p.dataset.panel === tab) ? 'block' : 'none', 'important');
    });
    const filter = $('.mts-filter-input');
    if (filter) { filter.value = ''; window.mtsFilterPicker(''); }
  };

  window.mtsFilterPicker = function (query) {
    const q = (query || '').toLowerCase().trim();
    if (pickerActiveTab === 'manual') return;
    const list = $('[data-pick-list="' + pickerActiveTab + '"]');
    if (!list) return;
    $$('.mts-pick-row', list).forEach(function (row) {
      const num = (row.querySelector('.mts-pick-num') || {}).textContent || '';
      const name = (row.querySelector('.mts-pick-name') || {}).textContent || '';
      const haystack = (num + ' ' + name).toLowerCase();
      row.style.setProperty('display', (q === '' || haystack.indexOf(q) >= 0) ? 'flex' : 'none', 'important');
    });
  };

  window.mtsSelectAllTab = function (tab) {
    if (tab === 'manual') return;
    const list = $('[data-pick-list="' + tab + '"]');
    if (!list) return;
    $$('.mts-pick-checkbox', list).forEach(function (cb) {
      const row = cb.closest('.mts-pick-row');
      const visible = !row || row.style.display !== 'none';
      if (visible && !cb.checked) {
        cb.checked = true;
        cb.dispatchEvent(new Event('change'));
      }
    });
  };

  window.mtsClearTab = function (tab) {
    if (tab === 'manual') return;
    const list = $('[data-pick-list="' + tab + '"]');
    if (!list) return;
    $$('.mts-pick-checkbox', list).forEach(function (cb) {
      if (cb.checked) {
        cb.checked = false;
        cb.dispatchEvent(new Event('change'));
      }
    });
  };

  window.mtsAppendManualRow = function () {
    const list = $('[data-manual-list]');
    const tpl = $('#mts-manual-row-template');
    if (!list || !tpl) return;
    const node = tpl.content.firstElementChild.cloneNode(true);
    const idx = list.children.length + 1;
    const idxEl = node.querySelector('[data-manual-index]');
    if (idxEl) idxEl.textContent = idx;
    list.appendChild(node);
    pickerManualQueue.push({ label: '', color: '', notes: '' });
    refreshManualQueueFromDOM();
  };

  window.mtsRemoveManualRow = function (btn) {
    const row = btn.closest('[data-manual-row]');
    if (row) row.remove();
    refreshManualQueueFromDOM();
  };

  function refreshManualQueueFromDOM() {
    const list = $('[data-manual-list]');
    if (!list) { pickerManualQueue = []; updateCommitButton(); return; }
    pickerManualQueue = $$('[data-manual-row]', list).map(function (row) {
      return {
        label: (row.querySelector('[data-manual-label]') || {}).value || '',
        color: (row.querySelector('[data-manual-color]') || {}).value || '',
        notes: (row.querySelector('[data-manual-notes]') || {}).value || '',
      };
    });
    const queued = $('[data-manual-queued]');
    const n = pickerManualQueue.length;
    if (queued) queued.textContent = n + ' manual track' + (n === 1 ? '' : 's') + ' queued';
    updateCommitButton();
  }

  // Re-read manual queue on every keystroke
  document.addEventListener('input', function (e) {
    if (e.target && e.target.closest && e.target.closest('[data-manual-row]')) {
      refreshManualQueueFromDOM();
    }
  });

  window.mtsCommitPickerSelection = function () {
    refreshManualQueueFromDOM();
    // Validate manual queue client-side
    const list = $('[data-manual-list]');
    let firstInvalid = null;
    if (list) {
      $$('[data-manual-row]', list).forEach(function (row) {
        const labelEl = row.querySelector('[data-manual-label]');
        const errEl = row.querySelector('[data-manual-error]');
        const label = (labelEl && labelEl.value || '').trim();
        if (!label) {
          if (labelEl) labelEl.style.setProperty('border-color', '#dc3545', 'important');
          if (errEl) errEl.style.setProperty('display', 'block', 'important');
          if (!firstInvalid) firstInvalid = labelEl;
        } else {
          if (labelEl) labelEl.style.removeProperty('border-color');
          if (errEl) errEl.style.setProperty('display', 'none', 'important');
        }
      });
    }
    if (firstInvalid) {
      window.mtsSwitchTab('manual');
      firstInvalid.focus();
      return;
    }

    // Build payload — preserve INSERTION ORDER (D-10) for picker selections
    const trackList = $('.mts-track-list');
    const sessionId = trackList ? trackList.dataset.sessionId : null;
    if (!sessionId) {
      // Editor-empty-state path: the .mts-track-list isn't rendered.
      // Look for the data attribute on a known-stable container instead.
      // Fall back to reading from a hidden marker the editor template exposes.
      const fallback = document.querySelector('[data-mts-session-id]');
      if (!fallback) { showToast('Cannot determine session id.', 'error'); return; }
      submitPickerCommit(fallback.dataset.mtsSessionId);
      return;
    }
    submitPickerCommit(sessionId);
  };

  function submitPickerCommit(sessionId) {
    const selections = {
      inputs: Array.from(pickerSelections.inputs),
      aux: Array.from(pickerSelections.aux),
      matrix: Array.from(pickerSelections.matrix),
      stereo: Array.from(pickerSelections.stereo),
    };
    const payload = { selections: selections, manuals: pickerManualQueue };

    postJSON('/audiopatch/multitrack/' + sessionId + '/add-tracks/', payload)
      .then(function (resp) {
        if (resp.status === 200 && resp.data.ok) {
          showToast(resp.data.created_count + ' track' +
                    (resp.data.created_count === 1 ? '' : 's') + ' added.', 'success');
          window.location.reload();
        } else {
          showToast(resp.data.error || 'Add failed.', 'error');
        }
      })
      .catch(function () { showToast('Network error. Try again.', 'error'); });
  }

  // ──────────────────────────────────────────────────────────────
  // Track row interactions (TRK-02, TRK-03, TRK-04, TRK-08)
  // ──────────────────────────────────────────────────────────────

  window.mtsSetEnabled = function (trackId, enabled) {
    postJSON('/audiopatch/multitrack/track/set-enabled/', { track_id: trackId, enabled: enabled })
      .then(function (resp) {
        if (resp.status === 200 && resp.data.ok) {
          const row = document.querySelector('[data-track-id="' + trackId + '"]');
          if (row) row.classList.toggle('mts-track-row--disabled', !enabled);
        } else {
          showToast(resp.data.error || 'Save failed.', 'error');
        }
      });
  };

  window.mtsEditLabel = function (trackId, cell) {
    const display = cell.querySelector('.mts-track-label-display');
    const input = cell.querySelector('.mts-track-label-input');
    if (!input) return;
    if (display) display.style.setProperty('display', 'none', 'important');
    input.style.setProperty('display', 'block', 'important');
    input.focus();
    input.select();
  };

  window.mtsSaveLabel = function (trackId, value) {
    postJSON('/audiopatch/multitrack/track/set-label/', { track_id: trackId, label: value })
      .then(function (resp) {
        const row = document.querySelector('[data-track-id="' + trackId + '"]');
        if (!row) return;
        const display = row.querySelector('.mts-track-label-display');
        const input = row.querySelector('.mts-track-label-input');
        if (resp.status === 200 && resp.data.ok) {
          if (display) display.textContent = resp.data.resolved_label;
        } else {
          showToast(resp.data.error || 'Save failed.', 'error');
        }
        if (input) input.style.setProperty('display', 'none', 'important');
        if (display) display.style.removeProperty('display');
      });
  };

  window.mtsCancelLabel = function (input, trackId) {
    const row = document.querySelector('[data-track-id="' + trackId + '"]');
    if (!row) return;
    const display = row.querySelector('.mts-track-label-display');
    if (input) input.style.setProperty('display', 'none', 'important');
    if (display) display.style.removeProperty('display');
  };

  let activeColorPickerTrackId = null;

  window.mtsOpenColorPicker = function (event, trackId) {
    activeColorPickerTrackId = trackId;
    const popover = $('#mts-color-popover');
    if (!popover) return;
    const swatch = event.currentTarget;
    const rect = swatch.getBoundingClientRect();
    popover.style.setProperty('position', 'absolute', 'important');
    popover.style.setProperty('top', (window.scrollY + rect.bottom + 4) + 'px', 'important');
    popover.style.setProperty('left', (window.scrollX + rect.left) + 'px', 'important');
    popover.style.setProperty('display', 'block', 'important');
    setTimeout(function () { document.addEventListener('click', dismissColorPicker, { once: true }); }, 50);
  };

  function dismissColorPicker(e) {
    const popover = $('#mts-color-popover');
    if (popover && !popover.contains(e.target)) popover.style.setProperty('display', 'none', 'important');
  }

  window.mtsApplyColor = function (color) {
    const trackId = activeColorPickerTrackId;
    if (trackId === null) return;
    const value = (color || '').trim();
    postJSON('/audiopatch/multitrack/track/set-color/', { track_id: trackId, color: value })
      .then(function (resp) {
        if (resp.status === 200 && resp.data.ok) {
          updateSwatchVisual(trackId, value);
          const popover = $('#mts-color-popover');
          if (popover) popover.style.setProperty('display', 'none', 'important');
        } else {
          showToast(resp.data.error || 'Color save failed.', 'error');
        }
      });
  };

  window.mtsClearColor = function (trackId) {
    activeColorPickerTrackId = trackId;
    window.mtsApplyColor('');
  };

  function updateSwatchVisual(trackId, hex) {
    const swatch = document.querySelector('.mts-swatch[data-track-id="' + trackId + '"]');
    if (!swatch) return;
    swatch.dataset.color = hex || '';
    const fill = swatch.querySelector('[data-swatch-fill]');
    const empty = swatch.querySelector('.mts-swatch__empty-mark');
    if (hex) {
      swatch.classList.remove('mts-swatch--empty');
      if (empty) empty.remove();
      let f = fill;
      if (!f) {
        f = document.createElement('span');
        f.setAttribute('data-swatch-fill', '');
        swatch.appendChild(f);
      }
      // CRITICAL: setProperty with 'important' to override admin's !important rules.
      f.style.setProperty('background-color', hex, 'important');
      swatch.title = 'Click to change. Right-click to clear.';
    } else {
      swatch.classList.add('mts-swatch--empty');
      if (fill) fill.remove();
      if (!empty) {
        const e = document.createElement('span');
        e.className = 'mts-swatch__empty-mark';
        e.textContent = '⊘';
        swatch.appendChild(e);
      }
      swatch.title = 'Click to override color';
    }
  }

  // Render initial swatch fills on page load (data-color attribute -> visual fill)
  function paintInitialSwatches() {
    $$('.mts-swatch').forEach(function (sw) {
      const hex = sw.dataset.color || '';
      const fill = sw.querySelector('[data-swatch-fill]');
      if (hex && fill) {
        fill.style.setProperty('background-color', hex, 'important');
      }
    });
  }

  // Paint under-capacity bar fill width from server-rendered data-fill-percent
  // (WR-01). The over/at branches inline style="width:100%"; the under branch
  // sets data-fill-percent so the bar can reflect the real ratio. The CSS
  // default for .mts-capacity__fill is no longer width:100% !important, so a
  // plain inline style would win — but we still use setProperty('important')
  // for defence in depth against future stylesheet changes.
  function paintCapacityFill() {
    $$('.mts-capacity__fill').forEach(function (el) {
      const pct = el.dataset.fillPercent;
      if (pct === undefined || pct === '') return;
      el.style.setProperty('width', pct + '%', 'important');
    });
  }

  // Notes editing on existing tracks is DEFERRED in Phase 1 (per checker
  // WARNING 3). Plan 05's _track_row.html renders notes as a plain
  // <span class="mts-track-notes-display"> — no input, no pencil affordance.
  // Therefore mtsToggleNotes / mtsSaveNotes are NOT defined here. When a
  // multitrack_set_notes endpoint is added (v2.0.1 polish), this is where
  // the inline-edit handler would live, mirroring mtsSaveLabel above.

  window.mtsRemoveTrack = function (trackId) {
    postJSON('/audiopatch/multitrack/track/remove/', { track_id: trackId })
      .then(function (resp) {
        if (resp.status === 200 && resp.data.ok) {
          const row = document.querySelector('[data-track-id="' + trackId + '"]');
          if (row) row.remove();
          showToast('1 track removed.', 'info');
          // Renumber remaining
          const list = $('.mts-track-list');
          if (list) {
            $$('.mts-track-num', list).forEach(function (el, idx) {
              el.textContent = '#' + (idx + 1);
            });
          }
        } else {
          showToast(resp.data.error || 'Remove failed.', 'error');
        }
      });
  };

  // ──────────────────────────────────────────────────────────────
  // Dashboard card menu (MTS-03, MTS-05, MTS-06)
  // ──────────────────────────────────────────────────────────────

  window.mtsToggleCardMenu = function (btn, sessionId) {
    const menu = document.getElementById('mts-card-menu-' + sessionId);
    if (!menu) return;
    $$('.mts-dropdown-menu').forEach(function (m) {
      if (m !== menu) m.classList.remove('mts-dropdown-menu--open');
    });
    menu.classList.toggle('mts-dropdown-menu--open');
  };

  window.mtsDuplicateSession = function (sessionId, name) {
    const newName = window.prompt('Duplicate "' + name + '" — new session name:', name + ' (copy)');
    if (newName === null) return;   // user cancelled
    postJSON('/audiopatch/multitrack/' + sessionId + '/duplicate/', { new_name: newName })
      .then(function (resp) {
        if (resp.status === 200 && resp.data.ok) {
          window.location.href = resp.data.redirect_url;
        } else {
          showToast(resp.data.error || 'Duplicate failed.', 'error');
        }
      });
  };

  window.mtsRenameSession = function (sessionId, oldName) {
    const newName = window.prompt('Rename session:', oldName);
    if (newName === null || newName.trim() === '') return;
    postJSON('/audiopatch/multitrack/' + sessionId + '/rename/', { name: newName })
      .then(function (resp) {
        if (resp.status === 200 && resp.data.ok) {
          window.location.reload();
        } else {
          showToast(resp.data.error || 'Rename failed.', 'error');
        }
      });
  };

  window.mtsDeleteSession = function (sessionId, name, trackCount) {
    const ok = window.confirm(
      'Delete "' + name + '"?\n\n' +
      'This will permanently delete the session and its ' + trackCount + ' tracks. ' +
      'The console\'s channel data is not affected.'
    );
    if (!ok) return;
    postJSON('/audiopatch/multitrack/' + sessionId + '/delete/', {})
      .then(function (resp) {
        if (resp.status === 200 && resp.data.ok) {
          window.location.href = resp.data.redirect_url;
        } else {
          showToast(resp.data.error || 'Delete failed.', 'error');
        }
      });
  };

  // ──────────────────────────────────────────────────────────────
  // Template save / rename / delete (Phase 3 / v3.0)
  // All endpoints are OWNER-scoped (created_by=request.user) per D-05.
  // ──────────────────────────────────────────────────────────────

  window.mtsSaveAsTemplate = function (sessionId, sessionName) {
    // Called from editor.html's "Save as Template" button.
    // Prompts for a template name, POSTs to /audiopatch/multitrack/templates/save/,
    // shows a toast on success or 409 conflict.
    const name = window.prompt('Save session as template — name?', sessionName || '');
    if (name === null) return;            // user cancelled
    const trimmed = name.trim();
    if (trimmed === '') {
      showToast('Template name is required.', 'error');
      return;
    }
    postJSON('/audiopatch/multitrack/templates/save/', {
      name: trimmed,
      session_id: sessionId,
    }).then(function (resp) {
      if (resp.status === 200 && resp.data.ok) {
        showToast('Saved template "' + trimmed + '" (' + resp.data.slot_count + ' tracks).', 'success');
      } else if (resp.status === 409) {
        // Pitfall 1 — name conflict is surfaced as an actionable toast, NOT a silent
        // overwrite. The server already includes a friendly message in resp.data.error.
        showToast(resp.data.error || ('A template named "' + trimmed + '" already exists.'), 'error');
      } else {
        showToast(resp.data.error || 'Save failed.', 'error');
      }
    });
  };

  // ──────────────────────────────────────────────────────────────
  // Capacity bar live update (uses GET /capacity/ endpoint).
  //
  // The mtsCommitPickerSelection() and mtsRemoveTrack() flows above already
  // reload or remove the row; this helper is exposed as window.mtsRefreshCapacity
  // so future callers (or v2.0.1 polish) can update without a full reload.
  // ──────────────────────────────────────────────────────────────

  window.mtsRefreshCapacity = function (sessionId) {
    if (!sessionId) {
      const list = $('.mts-track-list');
      sessionId = list ? list.dataset.sessionId : null;
    }
    if (!sessionId) return Promise.resolve(null);
    return getJSON('/audiopatch/multitrack/' + sessionId + '/capacity/').then(function (data) {
      const cap = $('.mts-capacity');
      if (!cap || !data) return data;
      const text = cap.querySelector('.mts-capacity__text');
      if (text) {
        if (data.capacity == null) {
          text.textContent = data.count + ' track' + (data.count === 1 ? '' : 's');
        } else if (data.over) {
          const over = data.count - data.capacity;
          text.textContent = data.count + ' / ' + data.capacity + ' — ' + over + ' over capacity';
        } else {
          text.textContent = data.count + ' / ' + data.capacity;
        }
      }
      return data;
    }).catch(function () { return null; });
  };

  // ──────────────────────────────────────────────────────────────
  // "Export to Reaper" button — show a passive toast while download starts.
  // The link's normal href triggers the download dialog; we just notify.
  // ──────────────────────────────────────────────────────────────

  function wireExportToasts() {
    $$('a.mts-btn-success').forEach(function (a) {
      if (a.href && a.href.indexOf('/export.rpp/') >= 0) {
        a.addEventListener('click', function () {
          showToast('Generating Reaper project file…', 'info');
        });
      }
    });
  }

  // ──────────────────────────────────────────────────────────────
  // Init
  // ──────────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    initSortable();
    paintInitialSwatches();
    paintCapacityFill();
    wireExportToasts();
    // Close picker on Escape (matches admin help-modal pattern)
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        const overlay = $('#mts-picker-overlay');
        if (overlay && overlay.style.display !== 'none') window.mtsClosePicker();
        const popover = $('#mts-color-popover');
        if (popover && popover.style.display !== 'none') popover.style.setProperty('display', 'none', 'important');
      }
    });
    // Close picker on backdrop click
    const overlay = $('#mts-picker-overlay');
    if (overlay) overlay.addEventListener('click', function (e) {
      if (e.target === overlay) window.mtsClosePicker();
    });
    // Close any open dropdown menus when clicking outside.
    document.addEventListener('click', function (e) {
      if (!e.target.closest || !e.target.closest('.mts-card-actions')) {
        $$('.mts-dropdown-menu').forEach(function (m) { m.classList.remove('mts-dropdown-menu--open'); });
      }
    });
  });

})();
