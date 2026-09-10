// PA Cable Schedule — entry-mode toggle (issue #73).
//
// A cable's Array/Speaker + Destination can be entered two ways, chosen by the
// `entry_mode` field on the change form:
//   * "From Soundvision / Amps" (linked) -> show the speaker_array + amp
//     dropdowns (driven by the imported Soundvision report and the Amplifier
//     Reference module); hide the free-text label + destination fields.
//   * "Free text" (text) -> show the original label (zone) + destination
//     fields; hide the linked dropdowns.
//
// Existing cables default to "Free text", so nothing about their editing UI
// changes. This is purely a show/hide affordance; whichever fields are hidden
// simply aren't used by array_speaker_display / destination_display server-side.
(function () {
    'use strict';

    const LINKED_FIELDS = ['speaker_array', 'amp'];
    const TEXT_FIELDS = ['label', 'destination'];

    document.addEventListener('DOMContentLoaded', function () {
        const modeSelect = document.getElementById('id_entry_mode');
        if (!modeSelect) return; // not on the PA cable change form
        apply(modeSelect.value);
        modeSelect.addEventListener('change', function () {
            apply(modeSelect.value);
        });
    });

    function apply(mode) {
        const linked = mode === 'linked';
        LINKED_FIELDS.forEach(function (name) { setRowVisible(name, linked); });
        TEXT_FIELDS.forEach(function (name) { setRowVisible(name, !linked); });
    }

    function setRowVisible(fieldName, visible) {
        const row = findRow(fieldName);
        if (row) row.style.display = visible ? '' : 'none';
    }

    function findRow(fieldName) {
        // Django admin renders each field in a `.form-row.field-<name>` wrapper.
        let row = document.querySelector('.form-row.field-' + fieldName);
        if (row) return row;
        // Fallback: locate the input/select and climb to its row container.
        const input = document.getElementById('id_' + fieldName);
        return input ? input.closest('.form-row') : null;
    }
})();
