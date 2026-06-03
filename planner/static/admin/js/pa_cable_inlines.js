/* PA Cable inline UX (issue #23):
 *  - Replace the default DELETE? checkbox on saved inline rows with an ✕
 *    button so PA Fan Outs / Fan-out Extensions / PA Couplers all use the
 *    same delete affordance regardless of whether the row is saved or new.
 *  - Show a hint under Fan-out Extensions explaining the save-then-pick
 *    flow, with an embedded "Save now" link that submits the form.
 *  - After a save+reload (response_post_save_change appends ?saved=1),
 *    pop a big green confirmation banner pointing at the extensions
 *    section, scroll to it, and briefly highlight it so the engineer
 *    sees the dropdown is now populated.
 */
(function () {
    'use strict';

    function xify(checkbox) {
        if (checkbox.dataset.xified) return;
        checkbox.dataset.xified = '1';
        checkbox.style.display = 'none';
        var td = checkbox.closest('td.delete') || checkbox.parentNode;
        var label = td.querySelector && td.querySelector('label');
        if (label) label.style.display = 'none';

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'inline-deletelink pa-x-delete';
        btn.textContent = '✕';
        btn.style.cssText =
            'background:transparent;border:0;color:#c66;font-size:16px;' +
            'cursor:pointer;padding:2px 6px;font-weight:bold;line-height:1;';

        var row = checkbox.closest('tr');
        function apply() {
            if (row) {
                row.style.opacity = checkbox.checked ? '0.4' : '';
                row.style.textDecoration = checkbox.checked ? 'line-through' : '';
            }
            btn.title = checkbox.checked
                ? 'Click again to keep this row'
                : 'Mark this row for deletion';
        }
        btn.addEventListener('click', function () {
            checkbox.checked = !checkbox.checked;
            apply();
        });
        td.insertBefore(btn, checkbox);
        apply();
    }

    // Locate an inline group by its rendered <h2> title. Robust against
    // Django's formset-prefix naming (which uses the FK related_name, not
    // the model name — easy to get wrong from the outside).
    function findInlineGroupByTitle(titleSubstring) {
        var t = titleSubstring.toLowerCase();
        var candidates = document.querySelectorAll('.inline-related, .inline-group');
        for (var i = 0; i < candidates.length; i++) {
            var h2 = candidates[i].querySelector('fieldset h2, h2');
            if (h2 && h2.textContent.toLowerCase().indexOf(t) !== -1) {
                return candidates[i];
            }
        }
        return null;
    }

    function maybeShowSavedBanner() {
        if (window.location.search.indexOf('saved=1') === -1) return;

        var banner = document.createElement('div');
        banner.style.cssText =
            'position:fixed;top:20px;left:50%;transform:translateX(-50%);' +
            'z-index:9999;background:#1f6f3b;color:#e6ffe6;' +
            'padding:14px 22px;border-radius:6px;border:1px solid #3aa05a;' +
            'box-shadow:0 8px 24px rgba(0,0,0,0.4);font-size:14px;' +
            'max-width:560px;text-align:center;';
        banner.innerHTML =
            '<strong>Cable saved.</strong> Newly-added fan-outs are now ' +
            'selectable in the <em>Fan-out Extensions</em> section below.';
        document.body.appendChild(banner);

        var extGroup = findInlineGroupByTitle('extension');
        if (extGroup) {
            extGroup.style.transition = 'background-color 0.4s ease';
            var fieldset = extGroup.querySelector('fieldset');
            var target = fieldset || extGroup;
            target.style.boxShadow = '0 0 0 3px #4a9eff';
            target.style.borderRadius = '4px';
            setTimeout(function () {
                target.style.boxShadow = '';
            }, 2500);
            setTimeout(function () {
                extGroup.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 200);
        }
        setTimeout(function () {
            banner.style.transition = 'opacity 0.6s ease';
            banner.style.opacity = '0';
            setTimeout(function () { banner.remove(); }, 700);
        }, 4500);

        // Strip ?saved=1 from URL without reloading
        if (window.history && window.history.replaceState) {
            window.history.replaceState({}, '', window.location.pathname);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var checkboxes = document.querySelectorAll(
            '.inline-related input[type="checkbox"][name$="-DELETE"]'
        );
        for (var i = 0; i < checkboxes.length; i++) xify(checkboxes[i]);

        maybeShowSavedBanner();
    });
})();
