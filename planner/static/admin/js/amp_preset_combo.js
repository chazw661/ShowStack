/* Issue #26: combobox behaviour for Amp.preset.
 * The HTML5 <datalist> filters to match the current value, which made it
 * look like the dropdown only had one entry. This replaces it with a
 * simple click-to-open list that always shows every option.
 */
(function () {
    'use strict';

    function init(combo) {
        if (combo.dataset.ampPresetInit) return;
        combo.dataset.ampPresetInit = '1';

        var input = combo.querySelector('input');
        var toggle = combo.querySelector('.amp-preset-toggle');
        var menu = combo.querySelector('.amp-preset-menu');
        if (!input || !toggle || !menu) return;

        function open() {
            // Close any other open menus first.
            document.querySelectorAll('.amp-preset-menu:not([hidden])').forEach(function (m) {
                if (m !== menu) m.setAttribute('hidden', '');
            });
            menu.removeAttribute('hidden');
        }
        function close() { menu.setAttribute('hidden', ''); }

        toggle.addEventListener('mousedown', function (e) {
            e.preventDefault();
            if (menu.hasAttribute('hidden')) {
                open();
                input.focus();
            } else {
                close();
            }
        });

        input.addEventListener('focus', open);

        menu.addEventListener('mousedown', function (e) {
            var opt = e.target.closest('.amp-preset-option');
            if (!opt) return;
            e.preventDefault();
            input.value = opt.dataset.value || opt.textContent;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            close();
        });

        // Close when clicking outside.
        document.addEventListener('mousedown', function (e) {
            if (!combo.contains(e.target)) close();
        });

        // Esc closes the menu without changing the value.
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') close();
        });
    }

    function scan() {
        document.querySelectorAll('.amp-preset-combo').forEach(init);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scan);
    } else {
        scan();
    }
})();
