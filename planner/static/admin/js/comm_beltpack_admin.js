// planner/static/admin/js/comm_beltpack_admin.js

(function() {
    // Wait for DOM to be ready
    if (typeof django !== 'undefined' && django.jQuery) {
        django.jQuery(document).ready(function($) {
            // Add system-type data attributes to rows based on BP # icon
            $('#result_list tbody tr').each(function() {
                var bpCell = $(this).find('.field-display_bp_number');
                var bpText = bpCell.text().trim();
                
                if (bpText.indexOf('📡') !== -1 || bpText.indexOf('W-') !== -1) {
                    $(this).attr('data-system-type', 'WIRELESS');
                } else if (bpText.indexOf('🔌') !== -1 || bpText.indexOf('H-') !== -1) {
                    $(this).attr('data-system-type', 'HARDWIRED');
                }
            });
            
            // Add thick divider before first hardwired pack
            var firstHardwired = $('#result_list tbody tr[data-system-type="HARDWIRED"]').first();
            if (firstHardwired.length) {
                firstHardwired.addClass('first-hardwired-pack');
            }
            
            console.log('Belt pack system type classes applied');
        });
    }
})();

/* ----------------------------------------------------------------------
 * Comm device form: show IP Address only for Hardwired, "Checked out" only
 * for Wireless, and switch the moment the Model changes.
 *
 * There is no System Type select any more -- it follows from the chosen
 * model's device type -- so this reads data-system-type off the selected
 * option, which the server put there (see _DeviceModelSelect in admin.py).
 *
 * All the hiding is done by CSS (comm_admin_v2.css); the server already put
 * bp-sys-WIRELESS / bp-sys-HARDWIRED on the fieldsets from the saved value,
 * so this only keeps that class in step with the dropdown. The correct field
 * is therefore hidden on first paint even if this file never loads.
 *
 * Plain DOM rather than django.jQuery: Media can load this before
 * jquery.init.js, and there is nothing here that needs jQuery.
 * -------------------------------------------------------------------- */
(function () {
    var CLASSES = { WIRELESS: 'bp-sys-WIRELESS', HARDWIRED: 'bp-sys-HARDWIRED' };

    function apply(value) {
        var cls = CLASSES[value] || CLASSES.WIRELESS;
        var targets = document.querySelectorAll(
            'fieldset.bp-sys-WIRELESS, fieldset.bp-sys-HARDWIRED');
        Array.prototype.forEach.call(targets, function (fs) {
            fs.classList.remove(CLASSES.WIRELESS, CLASSES.HARDWIRED);
            fs.classList.add(cls);
        });
    }

    function systemTypeOf(select) {
        var option = select.options[select.selectedIndex];
        /* No model chosen yet: leave the server's class alone rather than
           flipping the form to Wireless under the user. */
        if (!option || !option.value) return null;
        return option.getAttribute('data-system-type');
    }

    function init() {
        var select = document.getElementById('id_device_model');
        if (!select) return;   /* not the single-device add/change form */
        select.addEventListener('change', function () {
            var type = systemTypeOf(this);
            if (type) apply(type);
        });
        /* Browsers restore the previously selected value on a back/forward
           navigation after the server has already rendered the class, so sync
           once on load rather than trusting the two to agree. */
        var current = systemTypeOf(select);
        if (current) apply(current);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
