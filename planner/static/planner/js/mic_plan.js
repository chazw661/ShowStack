// Mic Plan review page: select a person to highlight their lines and edit
// them; merge by selecting the duplicate; import from the header button.
(function () {
    var root = document.getElementById('mp-root');
    if (!root) return;

    // Import: the header button opens the file picker, choosing a file submits.
    var file = document.getElementById('mp-file');
    var importBtn = document.getElementById('mp-import-btn');
    if (file && importBtn) {
        importBtn.addEventListener('click', function () { file.click(); });
        file.addEventListener('change', function () {
            if (!file.files.length) return;
            importBtn.disabled = true;
            importBtn.textContent = 'Reading…';
            file.form.submit();
        });
    }

    // All showflow lines: collapsed; opened when a flag links into it.
    var all = document.getElementById('mp-all');
    var table = document.getElementById('mp-rows');
    var blankBox = document.getElementById('mp-show-blank');
    if (blankBox && table) {
        blankBox.addEventListener('change', function () { table.classList.toggle('show-blank', blankBox.checked); });
    }
    function revealRow(hash) {
        var row = hash && document.querySelector(hash);
        if (!row || !all || !all.contains(row)) return;
        all.open = true;
        if (row.classList.contains('blank') && blankBox) {
            blankBox.checked = true;
            table.classList.add('show-blank');
        }
    }
    document.addEventListener('click', function (e) {
        var link = e.target.closest('[data-open-rows]');
        if (link) revealRow(link.getAttribute('href'));
    });
    revealRow(location.hash);

    // Selecting a person.
    var peopleRows = Array.prototype.slice.call(root.querySelectorAll('.mp-people tr[data-person]'));
    var selected = null;
    var merging = false;
    var editor = document.getElementById('mp-editor');
    var focusName = document.getElementById('mp-focus-name');

    function rowFor(pk) {
        return peopleRows.filter(function (r) { return r.dataset.person === pk; })[0];
    }

    function highlight(pk) {
        root.classList.toggle('mp-focus', !!pk);
        root.querySelectorAll('.mp-stage [data-person]').forEach(function (el) {
            var hit = pk && el.dataset.person === pk;
            el.classList.toggle('hit', !!hit);
            el.classList.toggle('dim', !!pk && !hit);
        });
        root.querySelectorAll('.mp-seg').forEach(function (seg) {
            seg.classList.toggle('dim', !!pk && !seg.querySelector('[data-person="' + pk + '"]'));
        });
        root.querySelectorAll('.mp-rows tr[data-people]').forEach(function (tr) {
            tr.classList.toggle('hit', !!pk && tr.dataset.people.split(' ').indexOf(pk) !== -1);
        });
        peopleRows.forEach(function (r) { r.classList.toggle('selected', r.dataset.person === pk); });
        if (focusName) focusName.textContent = pk && rowFor(pk) ? rowFor(pk).dataset.name : '';
    }

    function openEditor(pk) {
        if (!editor) return;
        var row = pk && rowFor(pk);
        editor.classList.toggle('open', !!row);
        if (!row) return;
        document.getElementById('mp-editor-name').textContent = row.dataset.name;
        var form = document.getElementById('mp-person-form');
        form.action = form.dataset.action.replace('/0/', '/' + pk + '/');
        document.getElementById('mp-presenter').value = row.dataset.presenter;
        document.getElementById('mp-hint').value = row.dataset.hint;
        editor.querySelectorAll('.mp-aliases').forEach(function (a) { a.hidden = a.dataset.for !== pk; });
    }

    function select(pk) {
        if (merging) return pickDuplicate(pk);
        selected = (pk === selected) ? null : pk;
        highlight(selected);
        openEditor(selected);
    }

    // Merge: the selected person keeps their name; the next one picked is folded in.
    var mergeBar = document.getElementById('mp-mergebar');
    var mergeStart = document.getElementById('mp-merge-start');
    var mergeGo = document.getElementById('mp-merge-go');
    var mergeText = document.getElementById('mp-merge-text');
    function endMerge() {
        merging = false;
        if (!mergeBar) return;
        mergeBar.classList.remove('open');
        mergeGo.disabled = true;
        peopleRows.forEach(function (r) { r.classList.remove('mp-merging'); });
    }
    function pickDuplicate(pk) {
        if (!pk || pk === selected) return;
        var keep = rowFor(selected), dup = rowFor(pk);
        peopleRows.forEach(function (r) { r.classList.toggle('mp-merging', r === dup); });
        mergeBar.action = mergeBar.dataset.action.replace('/0/', '/' + pk + '/');
        document.getElementById('mp-merge-into').value = selected;
        mergeText.textContent = 'Merge ' + dup.dataset.name + ' into ' + keep.dataset.name +
            '? Their lines and cues move over and "' + dup.dataset.name + '" is kept as another spelling.';
        mergeGo.disabled = false;
    }
    if (mergeStart) {
        mergeStart.addEventListener('click', function () {
            if (!selected) return;
            merging = true;
            mergeText.textContent = 'Now select the duplicate of ' + rowFor(selected).dataset.name + ' in the list.';
            mergeBar.classList.add('open');
        });
        document.getElementById('mp-merge-cancel').addEventListener('click', endMerge);
    }

    root.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-select]');
        if (btn) return select(btn.dataset.select);
        var row = e.target.closest('.mp-people tr[data-person]');
        if (row && !e.target.closest('form, a, button, select, input')) select(row.dataset.person);
    });
    root.addEventListener('keydown', function (e) {
        var row = e.target.closest && e.target.closest('.mp-people tr[data-person]');
        if (row && e.target === row && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            select(row.dataset.person);
        }
        if (e.key === 'Escape' && (selected || merging)) {
            endMerge();
            select(selected);
        }
    });
    var clear = document.getElementById('mp-focus-clear');
    if (clear) clear.addEventListener('click', function () { endMerge(); if (selected) select(selected); });

    // Back from a save or merge (#person-N): that person is selected again.
    var m = /^#person-(\d+)$/.exec(location.hash);
    if (m && rowFor(m[1])) select(m[1]);
})();
