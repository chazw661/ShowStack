// planner/static/admin/js/comm_beltpack_admin.js - COMPLETE FILE

(function() {
    if (typeof django !== 'undefined' && django.jQuery) {
        django.jQuery(document).ready(function($) {
            // Color code rows by system type using inline styles (overrides any CSS)
            $('#changelist-form table tbody tr').each(function() {
                var bpCell = $(this).find('.field-display_bp_number');
                var bpText = bpCell.text().trim();
                
                // Check if hardwired (plug emoji or H-)
                if (bpText.indexOf('🔌') !== -1 || bpText.indexOf('H-') !== -1) {
                    $(this).find('td').css({
                        'background-color': 'rgba(255, 152, 0, 0.2)',
                        'border-left': '5px solid #FF9800'
                    });
                } 
                // Check if wireless (antenna emoji or W-)
                else if (bpText.indexOf('📡') !== -1 || bpText.indexOf('W-') !== -1) {
                    $(this).find('td').css({
                        'background-color': 'rgba(33, 150, 243, 0.2)',
                        'border-left': '5px solid #2196F3'
                    });
                }
            });
            
            console.log('Belt pack colors applied via inline styles');
        });
    }
})();