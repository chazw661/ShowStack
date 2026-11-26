/* Daisy-chain links on a PA cable run.
 *
 * The run's own Length and Cable are the home run, amp to the first
 * speaker. A linked run carries on from speaker to speaker, and each of
 * those links is a row in the "Links" inline (PACableLink): Qty, Cable,
 * Length, Note.
 *
 * The chain-icon "Linked" button (PACableAdmin.linked_toggle) shows and
 * hides those rows, and this file moves the Links group up to sit under it.
 * Nothing is stored for the button: a run is linked when it has links.
 *
 *   on   shows the rows; with none yet, adds the first.
 *   off  drops rows not saved yet and marks saved ones for deletion. They
 *        stay on the page, greyed, under a line saying so, until Save. On
 *        again takes the marks back off.
 *
 * A new link starts at the run's Count and the run's cable type. Count
 * does not multiply links afterwards: Qty is the link's own.
 *
 * Order is the order on the page. The arrows swap two rows' VALUES, never
 * the rows: Django's formset re-numbers every row by page position when an
 * unsaved one is removed, and a new row moved above a saved one would be
 * dropped on save. Each row's position goes into its hidden `order` input
 * on submit; the server renumbers 1..N.
 *
 * Every text here is set with textContent. Notes are user-typed and are
 * only ever moved between inputs by .value.
 *
 * Plain DOM, on DOMContentLoaded: admin Media can load this before
 * jquery.init.js.
 */
(function () {
    'use strict';

    var PREFIX = 'links';
    var SWAPPED = ['quantity', 'cable', 'length', 'note'];

    function init() {
        var toggle = document.getElementById('pa-linked-toggle');
        var group = document.getElementById(PREFIX + '-group');
        if (!toggle || !group) return;

        /* A viewer's form has no inputs: the button only reports. */
        var editable = !!document.getElementById('id_count');
        var runCable = document.getElementById('id_cable');
        var runCount = document.getElementById('id_count');

        var fieldset = toggle.closest('fieldset');
        if (fieldset && fieldset.parentNode) {
            fieldset.parentNode.insertBefore(group, fieldset.nextSibling);
        }
        group.classList.add('pa-links-group');

        var offNote = document.createElement('p');
        offNote.className = 'pa-links-off-note';
        offNote.setAttribute('role', 'status');
        group.insertBefore(offNote, group.firstChild);

        function rows() {
            return Array.prototype.filter.call(
                group.querySelectorAll('tbody tr.form-row'),
                function (row) { return !row.classList.contains('empty-form'); });
        }
        function field(row, name) {
            return row.querySelector(
                'input[name$="-' + name + '"], select[name$="-' + name + '"]');
        }
        function deleteBox(row) {
            return row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        }
        function marked(row) {
            var box = deleteBox(row);
            return !!(box && box.checked);
        }
        function live() {
            return rows().filter(function (row) { return !marked(row); });
        }

        /* ---- a jumper link has no length ------------------------------ */

        function paintLength(row) {
            var select = field(row, 'cable');
            var input = field(row, 'length');
            if (!select || !input) return;
            var values = [];
            try {
                values = JSON.parse(select.getAttribute('data-jumper-values') || '[]');
            } catch (e) {
                values = [];
            }
            var jumper = values.indexOf(select.value) !== -1;
            var cell = input.parentNode;
            var note = cell.querySelector('.pa-length-na');
            input.hidden = jumper;
            input.disabled = jumper;
            if (jumper && !note) {
                note = document.createElement('span');
                note.className = 'pa-length-na';
                note.textContent = '—';
                note.title = 'Jumpers are ordered by quantity; length does not apply.';
                cell.appendChild(note);
            }
            if (note) note.hidden = !jumper;
        }

        /* ---- position label and the reorder arrows --------------------- */

        function arrow(row, label, title, step) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'pa-link-move';
            button.textContent = label;
            button.title = title;
            button.setAttribute('aria-label', title);
            button.addEventListener('click', function () { move(row, step); });
            return button;
        }

        function dress(row) {
            var cell = row.querySelector('td.original') || row.cells[0];
            if (!cell) return;
            var pos = cell.querySelector('.pa-link-pos');
            if (!pos) {
                pos = document.createElement('span');
                pos.className = 'pa-link-pos';
                cell.appendChild(pos);
                if (editable) {
                    cell.appendChild(arrow(row, '▲', 'Move this link earlier in the chain', -1));
                    cell.appendChild(arrow(row, '▼', 'Move this link later in the chain', 1));
                }
                var select = field(row, 'cable');
                if (select) {
                    select.addEventListener('change', function () { paintLength(row); });
                }
            }
            paintLength(row);
        }

        function relabel() {
            var n = 0;
            var chain = live();
            rows().forEach(function (row) {
                dress(row);
                var pos = row.querySelector('.pa-link-pos');
                var here = chain.indexOf(row);
                if (here === -1) {
                    pos.textContent = '';
                } else {
                    n = here + 1;
                    pos.textContent = 'Spk ' + n + ' → ' + (n + 1);
                }
                var moves = row.querySelectorAll('.pa-link-move');
                if (moves.length === 2) {
                    moves[0].disabled = here <= 0;
                    moves[1].disabled = here === -1 || here === chain.length - 1;
                }
            });
        }

        function move(row, step) {
            var chain = live();
            var other = chain[chain.indexOf(row) + step];
            if (!other) return;
            SWAPPED.forEach(function (name) {
                var a = field(row, name);
                var b = field(other, name);
                if (!a || !b) return;
                var kept = a.value;
                a.value = b.value;
                b.value = kept;
            });
            paintLength(row);
            paintLength(other);
            var focus = other.querySelectorAll('.pa-link-move')[step < 0 ? 0 : 1];
            if (focus && !focus.disabled) focus.focus();
        }

        /* ---- the toggle ------------------------------------------------- */

        function paint(on) {
            var all = rows();
            var doomed = all.filter(marked).length;
            toggle.setAttribute('aria-pressed', on ? 'true' : 'false');
            toggle.classList.toggle('is-on', on);
            group.classList.toggle('pa-links-hidden', !on && all.length === 0);
            group.classList.toggle('pa-links-off', !on && all.length > 0);
            offNote.textContent = (!on && doomed)
                ? (doomed === 1
                    ? 'This link will be removed when you save. Turn Linked back on to keep it.'
                    : 'These ' + doomed + ' links will be removed when you save. '
                      + 'Turn Linked back on to keep them.')
                : '';
            offNote.hidden = !offNote.textContent;
            relabel();
        }

        function isOn() {
            return toggle.getAttribute('aria-pressed') === 'true';
        }

        function turnOn() {
            rows().forEach(function (row) {
                var box = deleteBox(row);
                if (box && box.dataset.byLinkedToggle) {
                    box.checked = false;
                    delete box.dataset.byLinkedToggle;
                }
            });
            paint(true);
            if (!rows().length) {
                var add = group.querySelector('tr.add-row a');
                if (add) add.click();       /* formset:added finishes the row */
            }
        }

        function turnOff() {
            rows().forEach(function (row) {
                var box = deleteBox(row);
                if (box) {
                    if (!box.checked) {
                        box.checked = true;
                        box.dataset.byLinkedToggle = '1';
                    }
                    return;
                }
                var remove = row.querySelector('a.inline-deletelink');
                if (remove) remove.click();
            });
            paint(false);
        }

        if (editable) {
            toggle.addEventListener('click', function () {
                if (isOn()) turnOff(); else turnOn();
            });
        } else {
            toggle.disabled = true;
        }

        document.addEventListener('formset:added', function (event) {
            if (!event.detail || event.detail.formsetName !== PREFIX) return;
            var row = event.target;
            var qty = field(row, 'quantity');
            var cable = field(row, 'cable');
            if (qty && runCount && parseInt(runCount.value, 10) >= 1) {
                qty.value = parseInt(runCount.value, 10);
            }
            if (cable && runCable && runCable.value) cable.value = runCable.value;
            paint(true);
        });
        document.addEventListener('formset:removed', function (event) {
            if (!event.detail || event.detail.formsetName !== PREFIX) return;
            paint(isOn() && rows().length > 0);
        });
        /* The ✕ on a saved row (pa_cable_inlines.js) ticks or clears its
           DELETE box: linked while any link is left to keep. */
        group.addEventListener('click', function () {
            window.setTimeout(function () {
                if (rows().length) paint(live().length > 0);
            }, 0);
        });

        var form = toggle.closest('form');
        if (form) {
            form.addEventListener('submit', function () {
                rows().forEach(function (row, i) {
                    var order = field(row, 'order');
                    if (order) order.value = i + 1;
                });
            });
        }

        /* Linked when it has links: saved ones, or rows a failed save sent back. */
        paint(rows().length > 0);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
