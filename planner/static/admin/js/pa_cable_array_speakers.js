// PA Cable Schedule — array speaker reference panel (issue #73, Phase 2).
//
// For each speaker array linked to the run (the "Linked speaker arrays"
// picker), this lists every speaker in that array (e.g. KARA II 1 / KARA II 2
// / KARA II 3, top to bottom), with the cable assigned to the run beside it.
// It updates live as the engineer links arrays or changes the cable type or
// count — no save required.
//
// The picker is Django's filter_horizontal widget: the linked arrays are the
// options in #id_speaker_arrays_to, and moving one fires no change event, so
// a MutationObserver watches that list. Without the widget (no JS filter),
// the plain <select multiple> is read instead.
//
// Speaker data comes from the read-only endpoint seeded on the container via
// data-endpoint-base (mount-path aware). Every name is escaped.
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        const container = document.getElementById('pa-array-ref');
        if (!container) return; // not on the PA cable change form, or no arrays

        const cableSelect = document.getElementById('id_cable');
        const countInput = document.getElementById('id_count');

        const cache = {}; // arrayId -> {array_name, speakers}

        function linkedIds() {
            const chosen = document.getElementById('id_speaker_arrays_to');
            if (chosen) return Array.from(chosen.options).map(function (o) { return o.value; });
            const plain = document.getElementById('id_speaker_arrays');
            if (!plain) return [];
            return Array.from(plain.selectedOptions).map(function (o) { return o.value; });
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

        function load(arrayId) {
            if (cache[arrayId]) return Promise.resolve(cache[arrayId]);
            const url = container.dataset.endpointBase + encodeURIComponent(arrayId) + '/speakers/';
            return fetch(url, { credentials: 'same-origin' })
                .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
                .then(function (data) { cache[arrayId] = data; return data; })
                .catch(function () { return null; });
        }

        let generation = 0;
        function refresh() {
            const ids = linkedIds();
            const mine = ++generation;
            if (!ids.length) {
                container.innerHTML =
                    '<em class="pa-array-ref__hint">Link a speaker array to list its speakers here.</em>';
                return;
            }
            Promise.all(ids.map(load)).then(function (all) {
                if (mine !== generation) return;   // a newer refresh is on its way
                container.innerHTML = all.map(block).join('');
            });
        }

        function block(data) {
            if (!data) {
                return '<em class="pa-array-ref__hint">Could not load speakers for this array.</em>';
            }
            const speakers = data.speakers || [];
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

            return '<div class="pa-array-ref__grid">' +
                    '<div class="pa-array-ref__speakers">' +
                        '<div class="pa-array-ref__arrayname">' +
                            escapeHtml(data.array_name || '') + '</div>' +
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
                .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        }

        // SelectFilter2 builds #id_speaker_arrays_to on window load, after
        // this runs, so start watching once it exists.
        function watch() {
            const chosen = document.getElementById('id_speaker_arrays_to');
            if (chosen) {
                new MutationObserver(refresh).observe(chosen, { childList: true });
            } else {
                const plain = document.getElementById('id_speaker_arrays');
                if (plain) plain.addEventListener('change', refresh);
            }
            refresh();
        }
        if (cableSelect) cableSelect.addEventListener('change', refresh);
        if (countInput) countInput.addEventListener('input', refresh);
        if (document.readyState === 'complete') watch();
        else window.addEventListener('load', watch);
    });
})();
