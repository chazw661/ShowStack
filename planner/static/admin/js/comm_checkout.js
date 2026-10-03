/* Check-out toggle for the Comm Devices list.
 *
 * The Mic Tracker's lesson, applied: there is ONE renderer. The server sends
 * a bare <span class="comm-checkout"> carrying the device's state in data-*
 * attributes and nothing else; `paintCell` turns that into the button and the
 * row accent. It runs over every cell on page load, and again on the one cell
 * that changed after a toggle. A reloaded page and a toggled page therefore
 * cannot disagree -- there is no second piece of markup to drift.
 *
 * The counters work the same way: `paintCounters` reads the numbers the
 * server put on #comm-wireless-counters at load, and the numbers the toggle
 * endpoint returns afterwards. Same function, same markup, both times.
 */
(function () {
    'use strict';

    var ENDPOINT = '/admin/planner/commbeltpack/toggle-checkout/';

    function csrfToken() {
        var hit = document.cookie.split(';')
            .map(function (c) { return c.trim(); })
            .filter(function (c) { return c.indexOf('csrftoken=') === 0; })[0];
        return hit ? hit.split('=')[1] : '';
    }

    /* ---- the one renderer ------------------------------------------- */

    function paintCell(cell) {
        var isWireless = cell.dataset.systemType === 'WIRELESS';
        var isOut = cell.dataset.checkedOut === 'true';
        var row = cell.closest('tr');

        cell.textContent = '';

        if (!isWireless) {
            /* A hardwired device is cabled to the system; there is nothing to
               check out, so it gets a dash rather than a disabled button. */
            var dash = document.createElement('span');
            dash.className = 'comm-checkout__na';
            dash.textContent = '—';
            cell.appendChild(dash);
            if (row) row.classList.remove('comm-row-out');
            return;
        }

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'comm-checkout__btn' + (isOut ? ' is-out' : '');
        button.textContent = isOut ? 'OUT' : 'IN';
        button.setAttribute('aria-pressed', isOut ? 'true' : 'false');
        button.title = isOut ? 'Checked out - tap to check in'
                             : 'Available - tap to check out';
        cell.appendChild(button);

        if (row) row.classList.toggle('comm-row-out', isOut);
    }

    function paintCounters(values) {
        var box = document.getElementById('comm-wireless-counters');
        if (!box) return;
        ['total', 'out', 'avail'].forEach(function (key) {
            var el = box.querySelector('[data-counter="' + key + '"]');
            if (el) el.textContent = values[key];
        });
    }

    function countersFromDom() {
        var box = document.getElementById('comm-wireless-counters');
        if (!box) return null;
        return {
            total: box.dataset.total || '0',
            out: box.dataset.out || '0',
            avail: box.dataset.avail || '0'
        };
    }

    /* ---- toggling ---------------------------------------------------- */

    function toggle(cell) {
        if (cell.dataset.busy === '1') return;   /* ignore a double tap */
        cell.dataset.busy = '1';
        cell.classList.add('is-busy');

        fetch(ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            body: JSON.stringify({device_id: cell.dataset.deviceId})
        })
        .then(function (r) { return r.json().then(function (d) { return {ok: r.ok, data: d}; }); })
        .then(function (res) {
            if (!res.ok || !res.data.ok) {
                /* Leave the cell showing what the server still believes. */
                window.console && console.error('Check-out toggle refused:',
                                                res.data && res.data.error);
                return;
            }
            cell.dataset.checkedOut = res.data.checked_out ? 'true' : 'false';
            cell.dataset.systemType = res.data.system_type;
            paintCell(cell);
            if (res.data.counters) paintCounters(res.data.counters);
        })
        .catch(function (e) {
            window.console && console.error('Check-out toggle failed:', e);
        })
        .finally(function () {
            cell.dataset.busy = '';
            cell.classList.remove('is-busy');
        });
    }

    /* ---- wiring ------------------------------------------------------ */

    function init() {
        var cells = document.querySelectorAll('.comm-checkout');
        if (!cells.length) return;
        Array.prototype.forEach.call(cells, paintCell);

        var counters = countersFromDom();
        if (counters) paintCounters(counters);

        /* Delegated, so it keeps working for rows the grouping script moves
           around, and stops the row-click handler opening the edit page. */
        document.addEventListener('click', function (e) {
            var button = e.target.closest
                ? e.target.closest('.comm-checkout__btn') : null;
            if (!button) return;
            e.preventDefault();
            e.stopPropagation();
            var cell = button.closest('.comm-checkout');
            if (cell) toggle(cell);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
