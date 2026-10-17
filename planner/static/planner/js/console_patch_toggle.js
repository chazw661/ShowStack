/* Console page: "Hardware | Patch" view switch for the channel grids.
 *
 * Patch view shows the read-only Patch column (which I/O device port feeds
 * each channel) in place of a 150px select -- Source Hardware on inputs, Bus
 * Type on aux, Mono/Stereo on matrix -- so no grid gets wider. All the hiding
 * is CSS keyed on `body.ss-patch-on` (planner/css/console_patch.css); this only
 * flips the class and draws the buttons. A grid wide enough to show Patch beside
 * everything else does so, and the CSS hides its buttons and ignores the class.
 *
 * One state for the whole page, with a switch in every grid that has the
 * column, so it can be flipped wherever the engineer is. Remembered in this
 * browser only; if storage is unavailable it simply starts in Hardware view.
 */
(function () {
    'use strict';

    var KEY = 'ss.consolePatchView';
    var groups = ['consoleinput_set-group', 'consoleauxoutput_set-group',
                  'consolematrixoutput_set-group', 'consolestereooutput_set-group'];
    var buttons = [];

    function load() {
        try { return window.localStorage.getItem(KEY) === 'patch'; } catch (e) { return false; }
    }
    function save(on) {
        try { window.localStorage.setItem(KEY, on ? 'patch' : 'hardware'); } catch (e) { /* per-browser nicety only */ }
    }

    function apply(on) {
        document.body.classList.toggle('ss-patch-on', on);
        buttons.forEach(function (pair) {
            pair.hw.classList.toggle('is-active', !on);
            pair.patch.classList.toggle('is-active', on);
            pair.hw.setAttribute('aria-pressed', String(!on));
            pair.patch.setAttribute('aria-pressed', String(on));
        });
    }

    function makeBtn(text) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'ss-patch-toggle__btn';
        b.textContent = text;
        return b;
    }

    function build(group) {
        var wrap = document.createElement('div');
        wrap.className = 'ss-patch-toggle';
        var label = document.createElement('span');
        label.className = 'ss-patch-toggle__label';
        label.textContent = 'Show:';
        var hw = makeBtn('Hardware');
        var patch = makeBtn('Patch');
        hw.title = 'Show the source hardware / bus type columns';
        patch.title = 'Show which I/O device port each channel is patched to';
        hw.addEventListener('click', function (e) { e.preventDefault(); apply(false); save(false); });
        patch.addEventListener('click', function (e) { e.preventDefault(); apply(true); save(true); });
        wrap.appendChild(label);
        wrap.appendChild(hw);
        wrap.appendChild(patch);
        buttons.push({ hw: hw, patch: patch });

        var heading = group.querySelector('h2');
        if (heading && heading.parentNode) {
            heading.parentNode.insertBefore(wrap, heading.nextSibling);
        } else {
            group.insertBefore(wrap, group.firstChild);
        }
    }

    function init() {
        groups.forEach(function (id) {
            var group = document.getElementById(id);
            // Only grids that render the column: the add page has none.
            if (group && group.querySelector('th.column-patch')) build(group);
        });
        if (buttons.length) apply(load());
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
