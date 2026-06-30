// Console Module — autofill for numeric columns (Dante / Channel)
// Adds an "Autofill" button to each numeric column header in the Input,
// Aux, and Matrix inline tables. Clicking opens a small popup that fills
// a chosen run of cells with a sequence (start value + step).
(function () {
    'use strict';

    const SECTIONS = [
        { groupId: 'consoleinput_set-group',        columns: ['dante_number', 'input_ch'] },
        { groupId: 'consoleauxoutput_set-group',    columns: ['dante_number', 'aux_number'] },
        { groupId: 'consolematrixoutput_set-group', columns: ['dante_number', 'matrix_number'] },
    ];

    let activePopup = null;

    document.addEventListener('DOMContentLoaded', init);

    function init() {
        injectStyles();
        SECTIONS.forEach(section => {
            const group = document.getElementById(section.groupId);
            if (!group) return;
            section.columns.forEach(fieldName => {
                const header = group.querySelector('thead th.column-' + fieldName);
                if (!header) return;
                addAutofillButton(group, header, fieldName);
            });
        });
        document.addEventListener('click', handleOutsideClick, true);
        document.addEventListener('keydown', handleEscape);
    }

    function addAutofillButton(group, header, fieldName) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'autofill-btn';
        btn.title = 'Autofill this column';
        btn.textContent = 'Autofill';
        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            openPopup(group, fieldName, btn);
        });
        header.appendChild(document.createTextNode(' '));
        header.appendChild(btn);
    }

    function getVisibleRows(group) {
        return Array.from(group.querySelectorAll('tbody tr.form-row'))
            .filter(tr => !tr.classList.contains('empty-form'));
    }

    function openPopup(group, fieldName, anchor) {
        closePopup();

        const rows = getVisibleRows(group);
        const totalRows = rows.length;
        if (totalRows === 0) return;

        const popup = document.createElement('div');
        popup.className = 'autofill-popup';
        popup.innerHTML =
            '<div class="autofill-popup-title">Autofill column</div>' +
            '<div class="autofill-popup-row"><label>Start row</label>' +
                '<input type="number" min="1" max="' + totalRows + '" value="1" class="af-start-row" /></div>' +
            '<div class="autofill-popup-row"><label>Number of rows</label>' +
                '<input type="number" min="1" max="' + totalRows + '" value="' + totalRows + '" class="af-count" /></div>' +
            '<div class="autofill-popup-row"><label>Start value</label>' +
                '<input type="number" value="1" class="af-start-value" /></div>' +
            '<div class="autofill-popup-row"><label>Step</label>' +
                '<input type="number" value="1" class="af-step" /></div>' +
            '<div class="autofill-popup-buttons">' +
                '<button type="button" class="autofill-cancel">Cancel</button>' +
                '<button type="button" class="autofill-apply">Fill</button>' +
            '</div>' +
            '<div class="autofill-popup-meta">' + totalRows + ' row' + (totalRows === 1 ? '' : 's') + ' in this section</div>';
        document.body.appendChild(popup);

        const rect = anchor.getBoundingClientRect();
        popup.style.position = 'absolute';
        popup.style.top = (window.scrollY + rect.bottom + 4) + 'px';
        popup.style.left = (window.scrollX + rect.left) + 'px';
        popup.style.zIndex = '10000';

        const startRowInput = popup.querySelector('.af-start-row');
        const countInput = popup.querySelector('.af-count');
        let countTouched = false;
        countInput.addEventListener('input', () => { countTouched = true; });
        startRowInput.addEventListener('input', () => {
            if (countTouched) return;
            const sr = Math.max(1, parseInt(startRowInput.value, 10) || 1);
            countInput.value = Math.max(1, totalRows - (sr - 1));
        });

        popup.querySelector('.autofill-cancel').addEventListener('click', closePopup);
        popup.querySelector('.autofill-apply').addEventListener('click', () => applyAndClose(popup, group, fieldName));

        popup.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                applyAndClose(popup, group, fieldName);
            }
        });

        startRowInput.focus();
        startRowInput.select();

        activePopup = popup;
    }

    function applyAndClose(popup, group, fieldName) {
        applyFill(group, fieldName, {
            startRow: parseInt(popup.querySelector('.af-start-row').value, 10) || 1,
            count: parseInt(popup.querySelector('.af-count').value, 10) || 0,
            startValue: parseInt(popup.querySelector('.af-start-value').value, 10) || 0,
            step: parseInt(popup.querySelector('.af-step').value, 10) || 1,
        });
        closePopup();
    }

    function applyFill(group, fieldName, opts) {
        const rows = getVisibleRows(group);
        const total = rows.length;
        if (total === 0 || opts.count <= 0) return;
        const startIdx = Math.max(0, Math.min(total - 1, opts.startRow - 1));
        const endIdx = Math.min(total - 1, startIdx + opts.count - 1);
        for (let i = startIdx; i <= endIdx; i++) {
            const row = rows[i];
            const cell = row.querySelector('td.field-' + fieldName);
            if (!cell) continue;
            const input = cell.querySelector('input, select, textarea');
            if (!input) continue;
            const value = opts.startValue + (i - startIdx) * opts.step;
            input.value = String(value);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    function closePopup() {
        if (activePopup && activePopup.parentNode) {
            activePopup.parentNode.removeChild(activePopup);
        }
        activePopup = null;
    }

    function handleOutsideClick(e) {
        if (!activePopup) return;
        if (activePopup.contains(e.target)) return;
        if (e.target.closest && e.target.closest('.autofill-btn')) return;
        closePopup();
    }

    function handleEscape(e) {
        if (e.key === 'Escape' && activePopup) {
            closePopup();
        }
    }

    function injectStyles() {
        const css =
            '.autofill-btn {' +
                'display:inline-block;margin-left:6px;padding:1px 6px;font-size:10px;' +
                'font-weight:normal;background:#2a73c4;color:#fff;border:none;' +
                'border-radius:3px;cursor:pointer;line-height:1.4;text-transform:none;}' +
            '.autofill-btn:hover{background:#1e5a9c;}' +
            '.autofill-popup{background:#2a2a2a;color:#eee;border:1px solid #555;' +
                'border-radius:4px;padding:10px 12px;min-width:220px;' +
                'box-shadow:0 4px 12px rgba(0,0,0,0.4);font-size:12px;}' +
            '.autofill-popup-title{font-weight:bold;font-size:13px;margin-bottom:8px;color:#fff;}' +
            '.autofill-popup-row{display:flex;justify-content:space-between;' +
                'align-items:center;margin-bottom:6px;}' +
            '.autofill-popup-row label{font-size:11px;color:#ddd;}' +
            '.autofill-popup-row input{width:80px;background:#1a1a1a;color:#fff;' +
                'border:1px solid #555;padding:2px 4px;border-radius:2px;text-align:right;}' +
            '.autofill-popup-buttons{display:flex;gap:6px;justify-content:flex-end;margin-top:8px;}' +
            '.autofill-popup-buttons button{padding:4px 10px;font-size:11px;border:none;' +
                'border-radius:3px;cursor:pointer;}' +
            '.autofill-cancel{background:#444;color:#eee;}' +
            '.autofill-cancel:hover{background:#555;}' +
            '.autofill-apply{background:#2a73c4;color:#fff;font-weight:bold;}' +
            '.autofill-apply:hover{background:#1e5a9c;}' +
            '.autofill-popup-meta{font-size:10px;color:#aaa;margin-top:6px;}';
        const styleEl = document.createElement('style');
        styleEl.textContent = css;
        document.head.appendChild(styleEl);
    }
})();
