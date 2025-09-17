// Create this file: audiopatch/planner/static/admin/js/comm_beltpack_admin.js

(function($) {
    $(document).ready(function() {
        // Function to toggle checked_out field visibility
        function toggleCheckedOutField() {
            var systemType = $('#id_system_type').val();
            var checkedOutField = $('.field-checked_out');
            
            if (systemType === 'HARDWIRED') {
                checkedOutField.hide();
                $('#id_checked_out').prop('checked', false);
            } else {
                checkedOutField.show();
            }
        }
        
        // Initial check on page load
        toggleCheckedOutField();
        
        // Listen for system type changes
        $('#id_system_type').on('change', function() {
            toggleCheckedOutField();
        });
    });
})(django.jQuery);