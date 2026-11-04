// Mic Plan page: three views (#showflow, #packs, #review), click a person or
// RF anywhere to highlight it everywhere, the People / settings drawer, and
// the import, re-generate, edit and merge controls. Everything shown is
// rendered by the server from the stored plan; this only shows and hides --
// and sends moves (drag or tap a pack chart bar, a pack chip's menu, Undo),
// one POST each, after which the page reloads with the re-solved plan.
(function () {
    var root = document.getElementById('mp-root');
    if (!root) return;
    function $(id) { return document.getElementById(id); }
    function all(sel, el) { return Array.prototype.slice.call((el || root).querySelectorAll(sel)); }

    // The PDF link carries the browser's time zone, for its printed clock times.
    try {
        var zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (zone) all('a[data-tz-link]').forEach(function (a) {
            a.href += (a.href.indexOf('?') < 0 ? '?' : '&') + 'tz=' + encodeURIComponent(zone);
        });
    } catch (e) { /* UTC on the server */ }

    // Times stored in UTC ("Sent to Mic Tracker at"), in the browser's zone.
    all('time[data-local]').forEach(function (t) {
        var d = new Date(t.getAttribute('datetime'));
        if (isNaN(d)) return;
        t.textContent = d.toLocaleString(undefined, {month: 'short', day: 'numeric', hour: '2-digit',
                                                      minute: '2-digit', hour12: false});
    });

    // Import: the header button opens the file picker, choosing a file submits.
    var file = $('mp-file'), importBtn = $('mp-import-btn');
    if (file && importBtn) {
        importBtn.addEventListener('click', function () { file.click(); });
        file.addEventListener('change', function () {
            if (!file.files.length) return;
            importBtn.disabled = true;
            importBtn.textContent = 'Reading…';
            file.form.submit();
        });
    }

    // Re-generate asks before replacing the draft (inline, no browser dialog).
    // Its two choices: keep my changes (the default), or start over, which
    // asks once more because it clears the edit log.
    var regen = $('mp-regen'), ask = $('mp-regen-ask'), overAsk = $('mp-over-ask');
    if (regen && ask) {
        regen.addEventListener('click', function () { regen.hidden = true; ask.hidden = false; });
        $('mp-regen-cancel').addEventListener('click', function () { ask.hidden = true; regen.hidden = false; });
        $('mp-over').addEventListener('click', function () { ask.hidden = true; overAsk.hidden = false; });
        $('mp-over-cancel').addEventListener('click', function () { overAsk.hidden = true; regen.hidden = false; });
    }

    // Empty lines.
    var rowsTable = $('mp-rows'), emptyBox = $('mp-show-empty');
    if (emptyBox && rowsTable) {
        emptyBox.addEventListener('change', function () { rowsTable.classList.toggle('show-blank', emptyBox.checked); });
    }

    // Views, routed by hash: #showflow, #packs, #review; #showflow:row-N opens a line.
    var VIEWS = ['showflow', 'packs', 'review'];
    function show(hash) {
        var parts = (hash || '').replace(/^#/, '').split(':');
        var v = VIEWS.indexOf(parts[0]) === -1 ? 'showflow' : parts[0];
        VIEWS.forEach(function (k) {
            var sec = $('v-' + k), tab = $('t-' + k);
            if (sec) sec.hidden = k !== v;
            if (tab) tab.setAttribute('aria-selected', k === v ? 'true' : 'false');
        });
        var wrap = $('mp-empty-wrap');
        if (wrap) wrap.hidden = v !== 'showflow';
        if (v === 'packs') layoutChart();
        if (parts[1]) {
            var tr = document.getElementById(parts[1]);
            if (tr) {
                if (tr.classList.contains('blank') && emptyBox) { emptyBox.checked = true; rowsTable.classList.add('show-blank'); }
                all('#mp-rows tr.target').forEach(function (t) { t.classList.remove('target'); });
                tr.classList.add('target');
                tr.scrollIntoView({block: 'center'});
            }
        }
    }
    all('.mp-view').forEach(function (b) {
        b.addEventListener('click', function () {
            history.replaceState(null, '', '#' + b.dataset.v);
            show('#' + b.dataset.v);
        });
    });
    window.addEventListener('hashchange', function () { show(location.hash); });

    // Pack chart: a name that doesn't fit its bar goes under it, dropping a
    // row when it would run into the name before it. Measured, so only while
    // the chart is showing (a hidden chart has no widths).
    var UNDER_ROW = 14, UNDER_TOP = 27;
    function layoutChart() {
        var chart = $('mp-chart');
        if (!chart || !chart.offsetWidth) return;
        all('.lane', chart).forEach(function (lane) {
            var ends = [];          // per row of names: right edge of the last one (px)
            all('.stage', lane).sort(function (a, b) { return a.offsetLeft - b.offsetLeft; }).forEach(function (bar) {
                var under = bar.nextElementSibling, nm = bar.querySelector('.nm');
                if (!under || !under.classList.contains('under') || !nm) return;
                var fits = nm.offsetWidth + 10 <= bar.clientWidth;
                bar.classList.toggle('short', !fits);
                under.hidden = fits;
                if (fits) return;
                var x = bar.offsetLeft, k = 0;
                while (k < ends.length && ends[k] > x - 4) k++;
                under.style.top = (UNDER_TOP + k * UNDER_ROW) + 'px';
                ends[k] = x + under.offsetWidth;
            });
            lane.style.minHeight = ends.length ? (UNDER_TOP + ends.length * UNDER_ROW + 3) + 'px' : '';
        });
    }
    var layoutQueued = false;
    window.addEventListener('resize', function () {
        if (layoutQueued) return;
        layoutQueued = true;
        requestAnimationFrame(function () { layoutQueued = false; layoutChart(); });
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(layoutChart);

    // Focus: one person or RF highlighted everywhere, the rest dimmed.
    var people = {};
    all('.mp-people tr[data-person]').forEach(function (r) { people[r.dataset.person] = r; });
    var focus = null;
    var pill = $('mp-pill');
    function setFocus(f) {
        focus = f;
        root.classList.toggle('mp-focus', !!f);
        if (pill) {
            pill.hidden = !f;
            $('mp-pill-text').textContent = !f ? '' : f.who ? 'Showing ' + (people[f.who] ? people[f.who].dataset.name : 'person')
                : 'Showing RF ' + f.rf;
            $('mp-pill-details').hidden = !(f && f.who && people[f.who]);
        }
        all('#mp-rows tbody tr').forEach(function (tr) {
            var hit = false;
            if (f && f.who) hit = (tr.dataset.who || '').split(' ').indexOf(f.who) !== -1;
            if (f && f.rf) hit = (tr.dataset.rf || '').split(' ').indexOf(f.rf) !== -1;
            tr.classList.toggle('hit', !!f && hit);
            tr.classList.toggle('dim', !!f && !hit);
        });
        all('.mp-chart .worn, .mp-chart .stage, .mp-chart .under').forEach(function (el) {
            var on = !f || (f.who && el.dataset.who === f.who) || (f.rf && el.closest('.lane').dataset.rf === f.rf);
            el.classList.toggle('dim', !on);
        });
        all('.mp-chart .lane').forEach(function (lane) {
            lane.classList.toggle('hit', !!(f && f.rf && lane.dataset.rf === f.rf));
        });
        all('.mp-people tr[data-person]').forEach(function (r) {
            r.classList.toggle('selected', !!(f && f.who && r.dataset.person === f.who));
        });
    }
    if ($('mp-pill-clear')) $('mp-pill-clear').addEventListener('click', function () { setFocus(null); });
    if ($('mp-pill-details')) $('mp-pill-details').addEventListener('click', function () {
        if (focus && focus.who) { openDrawer('people'); select(focus.who, true); }
    });

    // Drawer: People (and crew) or Plan settings.
    var drawer = $('mp-drawer');
    function openDrawer(pane) {
        if (!drawer) return;
        drawer.hidden = false;
        all('[data-pane]', drawer).forEach(function (el) { el.hidden = el.dataset.pane !== pane; });
        $('mp-drawer-title').textContent = pane === 'settings' ? 'Plan settings' : 'People';
        $('mp-drawer-close').focus();
    }
    function closeDrawer() { if (drawer) drawer.hidden = true; }
    all('[data-drawer]').forEach(function (b) { b.addEventListener('click', function () { openDrawer(b.dataset.drawer); }); });
    if ($('mp-drawer-close')) $('mp-drawer-close').addEventListener('click', closeDrawer);

    // People: select to edit (one editor), merge by selecting the duplicate.
    var selected = null, merging = false;
    var editor = $('mp-editor');
    function syncBackup() {
        var wrap = $('mp-backup-wrap');
        if (wrap) wrap.hidden = $('mp-hint').value !== 'backup';
    }
    if ($('mp-hint')) $('mp-hint').addEventListener('change', syncBackup);
    function openEditor(pk) {
        if (!editor) return;
        var row = pk && people[pk];
        editor.classList.toggle('open', !!row);
        if (!row) return;
        $('mp-editor-name').textContent = row.dataset.name;
        var form = $('mp-person-form');
        form.action = form.dataset.action.replace('/0/', '/' + pk + '/');
        $('mp-presenter').value = row.dataset.presenter;
        $('mp-hint').value = row.dataset.hint;
        $('mp-backup').value = row.dataset.backup;
        syncBackup();
        all('.mp-aliases', editor).forEach(function (a) { a.hidden = a.dataset.for !== pk; });
    }
    function select(pk, keep) {
        if (merging) return pickDuplicate(pk);
        selected = (pk === selected && !keep) ? null : pk;
        openEditor(selected);
        setFocus(selected ? {who: selected} : null);
    }
    var mergeBar = $('mp-mergebar'), mergeGo = $('mp-merge-go'), mergeText = $('mp-merge-text');
    function endMerge() {
        merging = false;
        if (!mergeBar) return;
        mergeBar.classList.remove('open');
        mergeGo.disabled = true;
        all('.mp-people tr').forEach(function (r) { r.classList.remove('mp-merging'); });
    }
    function pickDuplicate(pk) {
        if (!pk || pk === selected) return;
        var keep = people[selected], dup = people[pk];
        all('.mp-people tr').forEach(function (r) { r.classList.toggle('mp-merging', r === dup); });
        mergeBar.action = mergeBar.dataset.action.replace('/0/', '/' + pk + '/');
        $('mp-merge-into').value = selected;
        mergeText.textContent = 'Merge ' + dup.dataset.name + ' into ' + keep.dataset.name +
            '? Their lines and cues move over and "' + dup.dataset.name + '" is kept as another spelling.';
        mergeGo.disabled = false;
    }
    if ($('mp-merge-start')) {
        $('mp-merge-start').addEventListener('click', function () {
            if (!selected) return;
            merging = true;
            mergeText.textContent = 'Now select the duplicate of ' + people[selected].dataset.name + ' in the list.';
            mergeBar.classList.add('open');
        });
        $('mp-merge-cancel').addEventListener('click', endMerge);
    }

    root.addEventListener('click', function (e) {
        var open = e.target.closest('[data-open-person]');
        if (open) { openDrawer('people'); return select(open.dataset.openPerson, true); }
        var row = e.target.closest('.mp-people tr[data-person]');
        if (row) {
            if (!e.target.closest('form, a, button, select, input')) select(row.dataset.person);
            return;
        }
        var rf = e.target.closest('[data-rf]');
        if (rf && rf.dataset.rf && !rf.matches('tr, .lane')) {
            return setFocus(focus && focus.rf === rf.dataset.rf ? null : {rf: rf.dataset.rf});
        }
        var who = e.target.closest('[data-who]');
        if (who && who.dataset.who && !who.matches('tr')) {
            selected = null;
            openEditor(null);
            setFocus(focus && focus.who === who.dataset.who ? null : {who: who.dataset.who});
        }
    });
    root.addEventListener('keydown', function (e) {
        var row = e.target.closest && e.target.closest('.mp-people tr[data-person]');
        if (row && e.target === row && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            select(row.dataset.person);
        }
        if (e.key === 'Escape') {
            if (moving || menuOpen()) return cancelMove();
            if (merging) return endMerge();
            if (drawer && !drawer.hidden) return closeDrawer();
            if (focus) setFocus(null);
        }
    });

    // Back from a save or merge (#person-N): the drawer is open on them again.
    var m = /^#person-(\d+)$/.exec(location.hash);
    if (m && people[m[1]]) {
        history.replaceState(null, '', '#showflow');
        openDrawer('people');
        select(m[1], true);
    } else if (location.hash === '#mp-people') {
        openDrawer('people');
    }
    // ---- Moves --------------------------------------------------------------
    var editBox = $('mp-edit'), moving = null, suppressClick = false;
    var menu = $('mp-movemenu'), msg = $('mp-edit-msg');
    var lanes = $('mp-lanes') ? JSON.parse($('mp-lanes').textContent) : [];
    var SCROLL_KEY = 'mp-chart-scroll';
    function menuOpen() { return menu && !menu.hidden; }
    function say(text) { if (msg) { msg.textContent = text; msg.hidden = !text; } }

    // A reload after a move keeps the chart's sideways scroll.
    try {
        var keptScroll = sessionStorage.getItem(SCROLL_KEY);
        sessionStorage.removeItem(SCROLL_KEY);
        var wrapEl = document.querySelector('.mp-chart-wrap');
        if (keptScroll && wrapEl) wrapEl.scrollLeft = +keptScroll;
    } catch (err) { /* storage blocked: start at the left */ }

    function post(url, fields) {
        var body = new FormData();
        body.append('csrfmiddlewaretoken', editBox.querySelector('[name=csrfmiddlewaretoken]').value);
        body.append('version', editBox.dataset.version);
        Object.keys(fields).forEach(function (k) { body.append(k, fields[k]); });
        root.classList.add('mp-busy');
        say('');
        fetch(url, {method: 'POST', body: body, credentials: 'same-origin'}).then(function (r) {
            return r.json().catch(function () { return {error: r.status === 403 ? 'You can view this plan but not change it.' : 'That did not work. Reload and try again.'}; })
                .then(function (j) { return {ok: r.ok, j: j}; });
        }).then(function (res) {
            if (res.ok) {
                try {
                    var w = document.querySelector('.mp-chart-wrap');
                    if (w) sessionStorage.setItem(SCROLL_KEY, String(w.scrollLeft));
                } catch (err) { /* fine */ }
                location.reload();
                return;
            }
            root.classList.remove('mp-busy');
            cancelMove();
            say(res.j.error || 'That did not work.');
        }, function () {
            root.classList.remove('mp-busy');
            say('No connection: the change was not saved.');
        });
    }
    function move(key, rf, pool) { post(editBox.dataset.editUrl, {kind: 'move_rf', key: key, rf: rf, pool: pool}); }

    // Where a key's pack is worn ([from, to] minutes) and who else wears
    // ``rf`` over that stretch.
    function wornOf(key) {
        for (var i = 0; i < lanes.length; i++) {
            for (var j = 0; j < lanes[i].worn.length; j++) {
                if (lanes[i].worn[j][2] === key) return {lane: lanes[i], from: lanes[i].worn[j][0], to: lanes[i].worn[j][1]};
            }
        }
        return null;
    }
    function busyOn(lane, key) {
        var w = wornOf(key);
        if (!w || !lane) return [];
        return lane.worn.filter(function (x) { return x[2] !== key && x[0] < w.to && w.from < x[1]; });
    }
    function laneOf(rf) { return lanes.filter(function (l) { return String(l.rf) === String(rf); })[0]; }
    function hm(t) {
        t = Math.round(t);
        var h = Math.floor(t / 60), m = t % 60;
        return ((h + 11) % 12 + 1) + ':' + (m < 10 ? '0' : '') + m + (h % 24 < 12 ? 'a' : 'p');
    }
    function poolWord(pool) { return pool === 'HH' ? 'handheld' : 'body pack'; }

    // Tap-to-move: the chosen bar is marked and every lane shows free/busy.
    function startMove(key) {
        moving = {key: key};
        root.classList.add('mp-moving');
        all('.mp-chart [data-key]').forEach(function (el) { el.classList.toggle('sel', el.dataset.key === key); });
        markLanes(key);
        var w = wornOf(key);
        say('');
        var hint = $('mp-movehint');
        if (hint) hint.textContent = 'Tap a lane to move ' + (w ? 'this pack (' + hm(w.from) + '–' + hm(w.to) + ')' : 'it') +
            ' there, or tap the bar again (or Esc) to cancel.';
    }
    function markLanes(key) {
        all('.mp-chart .lane.target').forEach(function (el) {
            var mine = wornOf(key);
            var own = mine && String(mine.lane.rf) === el.dataset.rf;
            var busy = !el.dataset.new && busyOn(laneOf(el.dataset.rf), key).length > 0;
            el.classList.toggle('own', !!own);
            el.classList.toggle('free', !own && !busy);
            el.classList.toggle('busy', !own && busy);
        });
    }
    function cancelMove() {
        moving = null;
        root.classList.remove('mp-moving');
        all('.mp-chart .sel').forEach(function (el) { el.classList.remove('sel'); });
        all('.mp-chart .lane').forEach(function (el) { el.classList.remove('own', 'free', 'busy', 'over'); });
        all('.mp-chart .dragging').forEach(function (el) { el.classList.remove('dragging'); el.style.transform = ''; });
        var hint = $('mp-movehint');
        if (hint) hint.textContent = 'Drag a bar up or down to another RF, or tap it and then tap a lane. Its times stay the same; everyone else keeps their RF wherever they can.';
        if (menu) menu.hidden = true;
    }
    function dropOn(lane) {
        if (!moving || !lane) return cancelMove();
        var key = moving.key, w = wornOf(key);
        if (w && String(w.lane.rf) === lane.dataset.rf) return cancelMove();      // same lane: nothing to do
        var pool = lane.dataset.new ? (w ? w.lane.pool : 'body') : lane.dataset.pool;
        cancelMove();
        move(key, lane.dataset.rf, pool);
    }

    var chartEl = $('mp-chart');
    if (editBox && chartEl) {
        // Drag: the bar follows the pointer up and down only (its time is
        // fixed); lanes light up free or busy; dropping on one moves it.
        var drag = null;
        chartEl.addEventListener('pointerdown', function (e) {
            var bar = e.target.closest('.movable');
            if (!bar || !bar.dataset.key || e.button > 0) return;
            drag = {key: bar.dataset.key, y: e.clientY, id: e.pointerId, on: false,
                    els: all('.mp-chart .movable[data-key="' + bar.dataset.key + '"]').filter(function (el) {
                        return el.closest('.lane') === bar.closest('.lane');
                    }).concat(all('.under', bar.closest('.lane')).filter(function (el) {
                        return el.previousElementSibling && el.previousElementSibling.dataset.key === bar.dataset.key;
                    }))};
            try { bar.setPointerCapture(e.pointerId); } catch (err) { /* fine */ }
        });
        chartEl.addEventListener('pointermove', function (e) {
            if (!drag || e.pointerId !== drag.id) return;
            var dy = e.clientY - drag.y;
            if (!drag.on && Math.abs(dy) < 6) return;
            if (!drag.on) {
                drag.on = true;
                startMove(drag.key);
                drag.els.forEach(function (el) { el.classList.add('dragging'); });
            }
            drag.els.forEach(function (el) { el.style.transform = 'translateY(' + dy + 'px)'; });
            var hit = document.elementFromPoint(e.clientX, e.clientY);
            var lane = hit && hit.closest('.mp-chart .lane.target');
            all('.mp-chart .lane.over').forEach(function (el) { if (el !== lane) el.classList.remove('over'); });
            if (lane) lane.classList.add('over');
        });
        function endDrag(e, drop) {
            if (!drag || e.pointerId !== drag.id) return;
            var was = drag;
            drag = null;
            if (!was.on) return;            // a tap: the click handler below
            suppressClick = true;
            if (!drop) return cancelMove();
            var hit = document.elementFromPoint(e.clientX, e.clientY);
            dropOn(hit && hit.closest('.mp-chart .lane.target'));
        }
        chartEl.addEventListener('pointerup', function (e) { endDrag(e, true); });
        chartEl.addEventListener('pointercancel', function (e) { endDrag(e, false); });
    }

    // Taps, before the focus handler: choose a bar, then a lane; or open a
    // pack chip's menu.
    root.addEventListener('click', function (e) {
        if (suppressClick) { suppressClick = false; e.stopPropagation(); e.preventDefault(); return; }
        if (!editBox) return;
        var item = e.target.closest('.mp-movemenu button');
        if (item) {
            e.stopPropagation();
            var key = menu.dataset.key;
            cancelMove();
            if (item.dataset.rf) move(key, item.dataset.rf, item.dataset.pool);
            else if (item.dataset.switch) post(editBox.dataset.editUrl, {kind: 'set_mic_type', key: key, mic_type: item.dataset.switch});
            else if (item.dataset.unpin) post(editBox.dataset.editUrl, {kind: 'unpin', key: key});
            return;
        }
        if (menuOpen() && !e.target.closest('.mp-movemenu')) menu.hidden = true;
        var bar = e.target.closest('.mp-chart .movable');
        if (moving) {
            if (bar && bar.dataset.key === moving.key) { cancelMove(); e.stopPropagation(); return; }
            var lane = e.target.closest('.mp-chart .lane.target');
            if (lane) { e.stopPropagation(); return dropOn(lane); }
            cancelMove();
            return;
        }
        if (bar && bar.dataset.key) { startMove(bar.dataset.key); return; }      // and the focus handler highlights them
        var chip = e.target.closest('.plan.packs .chip[data-key], .mp-changed .chip[data-key]');
        if (chip && chip.dataset.key && chip.closest('.plan.packs')) openMenu(chip);
    }, true);

    function openMenu(chip) {
        var key = chip.dataset.key, w = wornOf(key), pool = chip.dataset.pool;
        var html = '<p class="mp-muted">' + esc(chip.dataset.name) + (w ? ', worn ' + hm(w.from) + '–' + hm(w.to) : '') + '</p>';
        html += '<p class="mp-menu-h">Move to RF</p><div class="mp-menu-rfs">';
        lanes.forEach(function (l) {
            var own = w && w.lane.rf === l.rf;
            var busy = busyOn(l, key);
            var label = 'RF\u00a0' + l.rf + (l.pool !== pool ? ' · ' + (l.pool === 'HH' ? 'HH' : 'body') : '');
            var state = own ? 'now' : busy.length ? 'busy · ' + esc(busy[0][3]) + ' ' + hm(busy[0][0]) + '–' + hm(busy[0][1]) : 'free';
            html += '<button type="button" class="mp-btn small' + (busy.length ? ' busy' : '') + '" role="menuitem" data-rf="' + l.rf +
                '" data-pool="' + l.pool + '"' + (own ? ' disabled' : '') + '>' + label + ' <span>' + state + '</span></button>';
        });
        html += '<button type="button" class="mp-btn small" role="menuitem" data-rf="' + editBox.dataset.newRf + '" data-pool="' + pool +
            '">New pack <span>RF ' + editBox.dataset.newRf + '</span></button></div>';
        var other = pool === 'HH' ? 'body' : 'HH';
        html += '<button type="button" class="mp-btn small" role="menuitem" data-switch="' + other + '">Switch to ' + poolWord(other) + '</button>';
        if (chip.classList.contains('pinned')) html += '<button type="button" class="mp-btn small" role="menuitem" data-unpin="1">Unpin</button>';
        menu.innerHTML = html;
        menu.dataset.key = key;
        menu.hidden = false;
        menuY = window.scrollY;
        // Fixed to the viewport (the admin's #container is positioned, so
        // absolute would be off), below the chip or above it near the bottom.
        var r = chip.getBoundingClientRect(), vw = document.documentElement.clientWidth, vh = window.innerHeight;
        var top = r.bottom + 4;
        if (top + menu.offsetHeight > vh - 8) top = Math.max(8, r.top - 4 - menu.offsetHeight);
        menu.style.top = top + 'px';
        menu.style.left = Math.max(8, Math.min(r.left, vw - menu.offsetWidth - 8)) + 'px';
        var first = menu.querySelector('button:not([disabled])');
        if (first) first.focus({preventScroll: true});
    }
    // Fixed to the viewport, so it closes once the page has really scrolled
    // away from its chip (opening it can nudge the page a few pixels).
    var menuY = 0;
    window.addEventListener('scroll', function () {
        if (menuOpen() && Math.abs(window.scrollY - menuY) > 40) menu.hidden = true;
    }, {passive: true});
    function esc(t) { return String(t || '').replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }

    if ($('mp-undo') && editBox) {
        $('mp-undo').addEventListener('click', function () { post(editBox.dataset.undoUrl, {}); });
    }
    // The "N changed" list: a name shows that person.
    all('.mp-changed .chip[data-key]').forEach(function (chip) {
        chip.addEventListener('click', function () {
            var el = document.querySelector('.mp-chart [data-key="' + chip.dataset.key + '"], .plan.packs .chip[data-key="' + chip.dataset.key + '"]');
            if (el && el.dataset.who) setFocus({who: el.dataset.who});
        });
    });

    show(location.hash);
    // A link to a line (#showflow:row-N): scroll once the page has laid out.
    // The browser's own fragment handling runs after load and finds no element
    // called "showflow:row-N", so the scroll waits one more turn.
    if (/:row-\d+$/.test(location.hash)) {
        var later = function () { setTimeout(function () { show(location.hash); }, 50); };
        if (document.readyState === 'complete') later();
        else window.addEventListener('load', later);
    }
})();
