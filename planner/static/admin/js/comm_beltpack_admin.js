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