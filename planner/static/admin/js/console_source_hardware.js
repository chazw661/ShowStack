// Console Module — quick "+ Add new" + "Manage list" affordances for the
// Source Hardware column. Pairs with the SourceHardwareOption model:
//   - Each Source Hardware <select> on the page gets a "+ Add new…"
//     pseudo-option at the bottom. Picking it prompts for a label, POSTs to
//     the add endpoint, and inserts the new option into every Source
//     Hardware <select> on the page so the user can immediately reuse it.
//   - The Source Hardware column header gets a "Manage list" link that
//     opens the full SourceHardwareOption admin page in a new tab for
//     rename/reorder/delete.
(function () {
    'use strict';

    const ADD_NEW_VALUE = '__add_new__';
    const ADD_URL = '/audiopatch/source-hardware-options/add/';
    const MANAGE_URL = '/admin/planner/sourcehardwareoption/';
    const BACK_STORAGE_KEY = 'showstack_source_hardware_back_to';
    const CONSOLE_CHANGE_RE = /^\/admin\/planner\/console\/\d+\/change\/?$/;

    document.addEventListener('DOMContentLoaded', function () {
        injectStyles();
        rememberCurrentConsole();
        addManageLinkToHeader();
        document.addEventListener('change', handleChange, true);
        document.addEventListener('focus', captureCurrentValue, true);
    });

    function rememberCurrentConsole() {
        // Stash the current console edit URL so the "← Back to Console" button
        // on the Source Hardware Options page can return here even if the user
        // navigates to that page via the sidebar instead of "Manage list".
        if (!CONSOLE_CHANGE_RE.test(window.location.pathname)) return;
        try {
            sessionStorage.setItem(BACK_STORAGE_KEY, window.location.pathname);
        } catch (e) { /* ignore */ }
    }

    function addManageLinkToHeader() {
        const headers = document.querySelectorAll(
            '#consoleinput_set-group thead th.column-source_hardware'
        );
        const backTo = window.location.pathname;
        const href = MANAGE_URL + '?back_to=' + encodeURIComponent(backTo);
        headers.forEach(function (th) {
            if (th.querySelector('.source-hw-manage-link')) return;
            const link = document.createElement('a');
            link.href = href;
            link.textContent = 'Manage list';
            link.className = 'source-hw-manage-link';
            link.title = 'Open the full Source Hardware list (rename / reorder / delete)';
            th.appendChild(document.createTextNode(' '));
            th.appendChild(link);
        });
    }

    function captureCurrentValue(e) {
        const sel = e.target;
        if (!isSourceHardwareSelect(sel)) return;
        if (sel.value !== ADD_NEW_VALUE) {
            sel.dataset.previousValue = sel.value;
        }
    }

    function handleChange(e) {
        const sel = e.target;
        if (!isSourceHardwareSelect(sel)) return;
        if (sel.value !== ADD_NEW_VALUE) return;
        handleAddNew(sel);
    }

    function handleAddNew(sel) {
        const prev = sel.dataset.previousValue || '';
        const raw = window.prompt('New Source Hardware label:');
        if (raw === null) {
            sel.value = prev;
            return;
        }
        const label = raw.trim();
        if (!label) {
            sel.value = prev;
            return;
        }
        if (label.length > 50) {
            window.alert('Label must be 50 characters or fewer.');
            sel.value = prev;
            return;
        }
        // If the label already exists in the dropdown, just select it.
        const existing = Array.from(sel.options).find(function (o) {
            return o.value === label;
        });
        if (existing) {
            sel.value = label;
            sel.dataset.previousValue = label;
            return;
        }

        const body = new FormData();
        body.append('label', label);

        fetch(ADD_URL, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCsrf() },
            body: body,
            credentials: 'same-origin',
        })
            .then(function (r) {
                return r.json().then(function (data) {
                    return { status: r.status, data: data };
                });
            })
            .then(function (result) {
                if (result.status !== 200) {
                    window.alert(result.data.error || 'Could not add option.');
                    sel.value = prev;
                    return;
                }
                appendOptionToAllSelects(result.data.label);
                sel.value = result.data.label;
                sel.dataset.previousValue = result.data.label;
                sel.dispatchEvent(new Event('input', { bubbles: true }));
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            })
            .catch(function (err) {
                console.error('Add Source Hardware option failed:', err);
                window.alert('Network error. Could not add option.');
                sel.value = prev;
            });
    }

    function appendOptionToAllSelects(label) {
        const selects = document.querySelectorAll('select[name$="-source_hardware"]');
        selects.forEach(function (s) {
            if (Array.from(s.options).some(function (o) { return o.value === label; })) {
                return;
            }
            const opt = document.createElement('option');
            opt.value = label;
            opt.textContent = label;
            const addNewOpt = Array.from(s.options).find(function (o) {
                return o.value === ADD_NEW_VALUE;
            });
            if (addNewOpt) {
                s.insertBefore(opt, addNewOpt);
            } else {
                s.appendChild(opt);
            }
        });
    }

    function isSourceHardwareSelect(el) {
        if (!(el instanceof HTMLSelectElement)) return false;
        const name = el.getAttribute('name') || '';
        return name.endsWith('-source_hardware');
    }

    function getCsrf() {
        const match = document.cookie.split('; ').find(function (c) {
            return c.startsWith('csrftoken=');
        });
        return match ? match.split('=')[1] : '';
    }

    function injectStyles() {
        const css =
            '.source-hw-manage-link {' +
                'display:inline-block;margin-left:8px;padding:1px 6px;font-size:10px;' +
                'font-weight:normal;background:#2a73c4;color:#fff !important;' +
                'border-radius:3px;text-decoration:none;line-height:1.4;}' +
            '.source-hw-manage-link:hover{background:#1e5a9c;text-decoration:none;}';
        const style = document.createElement('style');
        style.textContent = css;
        document.head.appendChild(style);
    }
})();
