/* Jumpers have no length.
 *
 * "NL4 Jumper" is a short box-to-box link ordered by quantity, so a Length
 * input on a jumper row is a trap: anything typed there is ignored by the
 * summary, and a long run entered as a jumper silently drops out of the
 * footage. The input is replaced by a muted "—" instead.
 *
 * The server says which types are jumpers -- the changelist marks each row's
 * Cable cell with data-jumper, and the form's <select> carries
 * data-jumper-values -- so planner/utils/pa_cable_math.JUMPER_TYPES stays
 * the only place a jumper is named. There is no list of types in here.
 *
 * Two places, one function: `paintLength` takes the cell holding the input
 * and whether this row is a jumper, and is called on page load and again
 * whenever the type changes, so a reloaded page and a just-edited one cannot
 * disagree.
 */
(function () {
    'use strict';

    var NA_CLASS = 'pa-length-na';

    /* ---- the one renderer -------------------------------------------- */

    function paintLength(cell, isJumper) {
        if (!cell) return;
        var input = cell.querySelector('input[name$="length"], input#id_length');
        var note = cell.querySelector('.' + NA_CLASS);

        if (isJumper) {
            if (input) {
                /* Hidden, not removed: switching the type back has to reveal
                   it again with no reload. `disabled` also keeps it out of
                   the POST, which is why the form makes length optional and
                   re-imposes it for every other type. */
                input.hidden = true;
                input.disabled = true;
            }
            if (!note) {
                note = document.createElement('span');
                note.className = NA_CLASS;
                note.textContent = '—';
                note.title = 'Jumpers are ordered by quantity; length does not apply.';
                cell.appendChild(note);
            }
            note.hidden = false;
        } else {
            if (input) {
                input.hidden = false;
                input.disabled = false;
            }
            if (note) note.hidden = true;
        }
    }

    /* ---- the changelist grid ------------------------------------------ */

    function initChangelist() {
        var table = document.getElementById('result_list');
        if (!table) return;
        var rows = table.querySelectorAll('tbody tr');
        Array.prototype.forEach.call(rows, function (row) {
            var marker = row.querySelector('.pa-cable-type');
            if (!marker) return;
            var cell = row.querySelector('.field-length');
            paintLength(cell, marker.dataset.jumper === 'true');
        });
    }

    /* ---- the add / change form ---------------------------------------- */

    function initForm() {
        var select = document.getElementById('id_cable');
        if (!select) return;

        var jumperValues = [];
        try {
            jumperValues = JSON.parse(
                select.getAttribute('data-jumper-values') || '[]');
        } catch (e) {
            jumperValues = [];
        }

        var row = document.querySelector('.form-row.field-length')
            || (document.getElementById('id_length')
                && document.getElementById('id_length').closest('.form-row'));
        if (!row) return;

        function repaint() {
            var isJumper = jumperValues.indexOf(select.value) !== -1;
            /* Hide the whole row on the form -- the label "Length (ft)" is
               as misleading as the input. The changelist keeps its cell
               because the column header is shared by every row. */
            row.hidden = isJumper;
            paintLength(row, isJumper);
        }

        select.addEventListener('change', repaint);
        repaint();
    }

    function init() {
        initChangelist();
        initForm();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
