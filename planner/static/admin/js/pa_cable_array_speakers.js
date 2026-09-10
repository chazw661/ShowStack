// PA Cable Schedule — array speaker reference panel (issue #73, Phase 2).
//
// When a cable is linked (entry_mode = "From Soundvision / Amps") and an
// Array/Speaker is selected, this lists every speaker in that array (e.g.
// KARA II 1 / KARA II 2 / KARA II 3, top to bottom) on the left, with the
// cable assigned to the array shown on the right. It updates live as the
// engineer changes the array, cable type, or count — no save required.
//
// Speaker data comes from the read-only endpoint seeded on the container via
// data-endpoint-base (mount-path aware). The panel is hidden in free-text mode.
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        const container = document.getElementById('pa-array-ref');
        if (!container) return; // not on the PA cable change form

        const modeSelect = document.getElementById('id_entry_mode');
        const arraySelect = document.getElementById('id_speaker_array');
        const cableSelect = document.getElementById('id_cable');
        const countInput = document.getElementById('id_count');
        const row = container.closest('.form-row');

        let cache = {}; // arrayId -> {array_name, speakers}

        function currentMode() {
            return modeSelect ? modeSelect.value : 'text';
        }
        function currentArrayId() {
            if (arraySelect && arraySelect.value) return arraySelect.value;
            return container.dataset.arrayId || '';
        }
        function cableLabel() {
            if (cableSelect && cableSelect.selectedIndex >= 0) {
                return cableSelect.options[cableSelect.selectedIndex].text;
            }
            return container.dataset.cable || '';
        }
        function cableCount() {
            if (countInput && countInput.value) return countInput.value;
            return container.dataset.count || '';
        }

        function refresh() {
            const linked = currentMode() === 'linked';
            const arrayId = currentArrayId();

            // Hide the whole row in free-text mode — it only applies to linked cables.
            if (row) row.style.display = linked ? '' : 'none';
            if (!linked || !arrayId) {
                showHint();
                return;
            }
            if (cache[arrayId]) {
                render(cache[arrayId]);
                return;
            }
            const url = container.dataset.endpointBase + arrayId + '/speakers/';
            fetch(url, { credentials: 'same-origin' })
                .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
                .then(function (data) { cache[arrayId] = data; render(data); })
                .catch(function () {
                    container.innerHTML =
                        '<em class="pa-array-ref__hint">Could not load speakers for this array.</em>';
                });
        }

        function showHint() {
            container.innerHTML =
                '<em class="pa-array-ref__hint">Select an Array/Speaker in linked mode ' +
                'to list its speakers here.</em>';
        }

        function render(data) {
            const speakers = (data && data.speakers) || [];
            const items = speakers.length
                ? speakers.map(function (s) {
                    return '<li>' + escapeHtml(s.label) + '</li>';
                }).join('')
                : '<li class="pa-array-ref__empty">(no speakers in this array)</li>';

            const cbl = cableLabel();
            const cnt = cableCount();
            const cableLine = cbl
                ? escapeHtml(cbl) + (cnt ? ' &times; ' + escapeHtml(String(cnt)) : '')
                : '<span class="pa-array-ref__empty">(no cable set)</span>';
            const fanout = container.dataset.fanout;
            const fanLine = fanout
                ? '<div class="pa-array-ref__fanout">Fan-outs / couplers: ' +
                    escapeHtml(fanout) + '</div>'
                : '';

            container.innerHTML =
                '<div class="pa-array-ref__grid">' +
                    '<div class="pa-array-ref__speakers">' +
                        '<div class="pa-array-ref__arrayname">' +
                            escapeHtml((data && data.array_name) || '') + '</div>' +
                        '<ul class="pa-array-ref__list">' + items + '</ul>' +
                    '</div>' +
                    '<div class="pa-array-ref__cable">' +
                        '<div class="pa-array-ref__cablehdr">Assigned cable</div>' +
                        '<div class="pa-array-ref__cableval">' + cableLine + '</div>' +
                        fanLine +
                    '</div>' +
                '</div>';
        }

        function escapeHtml(s) {
            return String(s)
                .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }

        if (modeSelect) modeSelect.addEventListener('change', refresh);
        if (arraySelect) arraySelect.addEventListener('change', refresh);
        // Live-update the "assigned cable" side as the engineer edits it.
        if (cableSelect) cableSelect.addEventListener('change', refresh);
        if (countInput) countInput.addEventListener('input', refresh);

        refresh();
    });
})();
