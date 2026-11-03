// Mic Plan page: three views (#showflow, #packs, #review), click a person or
// RF anywhere to highlight it everywhere, the People / settings drawer, and
// the import, re-generate, edit and merge controls. Everything shown is
// rendered by the server from the stored plan; this only shows and hides.
(function () {
    var root = document.getElementById('mp-root');
    if (!root) return;
    function $(id) { return document.getElementById(id); }
    function all(sel, el) { return Array.prototype.slice.call((el || root).querySelectorAll(sel)); }

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
    var regen = $('mp-regen'), ask = $('mp-regen-ask');
    if (regen && ask) {
        regen.addEventListener('click', function () { regen.hidden = true; ask.hidden = false; });
        $('mp-regen-cancel').addEventListener('click', function () { ask.hidden = true; regen.hidden = false; });
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
        all('.mp-chart .worn, .mp-chart .stage').forEach(function (el) {
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
