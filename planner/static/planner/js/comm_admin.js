// planner/static/planner/js/comm_admin.js

django.jQuery(document).ready(function($) {
    'use strict';
    
    // Handle position dropdown/text field combination
    $('.position-select').on('change', function() {
        var selectedText = $(this).find('option:selected').text();
        var $positionInput = $(this).closest('.form-row').find('.position-input');
        
        if (selectedText && selectedText !== '-- Select Position --') {
            $positionInput.val(selectedText);
        }
    });
    
    // Handle name dropdown/text field combination
    $('.name-select').on('change', function() {
        var selectedText = $(this).find('option:selected').text();
        var $nameInput = $(this).closest('.form-row').find('.name-input');
        
        if (selectedText && selectedText !== '-- Select Name --') {
            $nameInput.val(selectedText);
        }
    });
    
    // Add quick fill buttons for common configurations
    function addQuickFillButtons() {
        var $channelSection = $('.channel-grid');
        if ($channelSection.length && !$('#quick-fill-buttons').length) {
            var quickFillHtml = `
                <div id="quick-fill-buttons" style="margin: 10px 0;">
                    <label style="margin-right: 10px;">Quick Fill:</label>
                    <button type="button" class="quick-fill-btn" data-config="production">
                        Production Team
                    </button>
                    <button type="button" class="quick-fill-btn" data-config="audio">
                        Audio Team
                    </button>
                    <button type="button" class="quick-fill-btn" data-config="video">
                        Video Team
                    </button>
                    <button type="button" class="quick-fill-btn" data-config="all-call">
                        All Call
                    </button>
                    <button type="button" class="quick-fill-btn" data-config="clear">
                        Clear Channels
                    </button>
                </div>
            `;
            $channelSection.prepend(quickFillHtml);
        }
    }
    
    // Handle quick fill button clicks
    $(document).on('click', '.quick-fill-btn', function(e) {
        e.preventDefault();
        var config = $(this).data('config');
        
        // Get channel dropdowns
        var $chA = $('#id_channel_a');
        var $chB = $('#id_channel_b');
        var $chC = $('#id_channel_c');
        var $chD = $('#id_channel_d');
        var $group = $('#id_group');
        
        switch(config) {
            case 'production':
                // Production: PROD on A, ALL on B
                setChannelByName($chA, 'Production');
                setChannelByName($chB, 'ALL');
                $chC.val('');
                $chD.val('');
                $group.val('PROD');
                break;
                
            case 'audio':
                // Audio: AUDIO on A, ALL on B, PGM on C
                setChannelByName($chA, 'Audio');
                setChannelByName($chB, 'ALL');
                setChannelByName($chC, 'Program');
                $chD.val('');
                $group.val('AUDIO');
                break;
                
            case 'video':
                // Video: VIDEO on A, ALL on B, CAMS on C
                setChannelByName($chA, 'Video');
                setChannelByName($chB, 'ALL');
                setChannelByName($chC, 'Camera');
                $chD.val('');
                $group.val('VIDEO');
                break;
                
            case 'all-call':
                // All Call configuration
                setChannelByName($chA, 'ALL');
                $chB.val('');
                $chC.val('');
                $chD.val('');
                break;
                
            case 'clear':
                // Clear all channels
                $chA.val('');
                $chB.val('');
                $chC.val('');
                $chD.val('');
                break;
        }
    });
    
    // Helper function to set channel by name
    function setChannelByName($select, channelName) {
        $select.find('option').each(function() {
            if ($(this).text().indexOf(channelName) !== -1) {
                $select.val($(this).val());
                return false;
            }
        });
    }
    
    // Add visual feedback for checked out status
    function updateCheckedOutStatus() {
        var $checkedOut = $('#id_checked_out');
        var $form = $checkedOut.closest('form');
        
        if ($checkedOut.is(':checked')) {
            $form.addClass('checked-out');
        } else {
            $form.removeClass('checked-out');
        }
    }
    
    $('#id_checked_out').on('change', updateCheckedOutStatus);
    
    // Initialize on page load
    addQuickFillButtons();
    updateCheckedOutStatus();
    
    // Show/hide unit location field based on system type
    function toggleUnitLocation() {
        var systemType = $('#id_system_type').val();
        var $unitLocationRow = $('.field-unit_location').closest('.form-row');
        
        if (systemType === 'WIRELESS') {
            $unitLocationRow.show();
        } else {
            $unitLocationRow.hide();
        }
    }
    
    $('#id_system_type').on('change', toggleUnitLocation);
    toggleUnitLocation(); // Initialize on page load
    
    // Auto-increment BP number for new records (considering system type)
    if ($('#id_bp_number').val() === '') {
        var systemType = $('#id_system_type').val() || 'WIRELESS';
        
        // Make AJAX call to get next available BP number for this system type
        $.get('/admin/planner/commbeltpack/get_next_bp_number/', 
            { system_type: systemType }, 
            function(data) {
                if (data.next_bp_number) {
                    $('#id_bp_number').val(data.next_bp_number);
                }
            }
        );
    }
    
    // Update BP number when system type changes
    $('#id_system_type').on('change', function() {
        if (!$('#id_bp_number').val() || confirm('Update BP number for the new system type?')) {
            var systemType = $(this).val();
            $.get('/admin/planner/commbeltpack/get_next_bp_number/', 
                { system_type: systemType }, 
                function(data) {
                    if (data.next_bp_number) {
                        $('#id_bp_number').val(data.next_bp_number);
                    }
                }
            );
        }
    });
    
    // Add channel color coding
    $('.field-channel_a select').addClass('channel-a');
    $('.field-channel_b select').addClass('channel-b');
    $('.field-channel_c select').addClass('channel-c');
    $('.field-channel_d select').addClass('channel-d');
    
    // Add tooltips for channel types
    $('select[id^="id_channel_"]').each(function() {
        $(this).find('option').each(function() {
            var text = $(this).text();
            if (text.indexOf('4W') !== -1) {
                $(this).addClass('four-wire');
            } else if (text.indexOf('2W') !== -1) {
                $(this).addClass('two-wire');
            }
        });
    });
});

