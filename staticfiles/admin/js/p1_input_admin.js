// staticfiles/admin/js/p1_input_admin.js

(function($) {
    'use strict';
    
    $(document).ready(function() {
        // Function to update origin field visibility based on input type
        function updateOriginFieldVisibility() {
            $('#p1input_set-group tbody tr').each(function() {
                var $row = $(this);
                var inputType = $row.find('select[name$="-input_type"]').val() || 
                               $row.find('input[name$="-input_type"]').val();
                
                // Get the text if it's a readonly field
                if (!inputType) {
                    var typeText = $row.find('.field-input_type').text().trim();
                    if (typeText.includes('AVB')) {
                        inputType = 'AVB';
                    } else if (typeText.includes('AES')) {
                        inputType = 'AES';
                    } else if (typeText.includes('Analog')) {
                        inputType = 'ANALOG';
                    }
                }
                
                // Add class to row for styling
                $row.removeClass('input-type-analog input-type-aes input-type-avb');
                if (inputType) {
                    $row.addClass('input-type-' + inputType.toLowerCase());
                }
                
                // Hide/show origin field
                var $originField = $row.find('.field-origin_device_output');
                if (inputType === 'AVB') {
                    $originField.hide();
                    // Clear the value for AVB inputs
                    $originField.find('select').val('');
                } else {
                    $originField.show();
                }
            });
        }
        
        // Run on page load
        updateOriginFieldVisibility();
        
        // Run when input type changes (for editable forms)
        $(document).on('change', 'select[name$="-input_type"]', function() {
            updateOriginFieldVisibility();
        });
        
        // Group inputs by type visually
        function groupInputsByType() {
            var $tbody = $('#p1input_set-group tbody');
            var groups = {
                'ANALOG': [],
                'AES': [],
                'AVB': []
            };
            
            // Collect rows by type
            $tbody.find('tr').each(function() {
                var $row = $(this);
                var inputType = $row.find('select[name$="-input_type"]').val() || 
                               $row.find('input[name$="-input_type"]').val();
                
                if (!inputType) {
                    var typeText = $row.find('.field-input_type').text().trim();
                    if (typeText.includes('AVB')) {
                        inputType = 'AVB';
                    } else if (typeText.includes('AES')) {
                        inputType = 'AES';
                    } else if (typeText.includes('Analog')) {
                        inputType = 'ANALOG';
                    }
                }
                
                if (inputType && groups[inputType]) {
                    groups[inputType].push($row);
                }
            });
            
            // Clear tbody and add back grouped rows
            $tbody.empty();
            
            // Add Analog inputs
            if (groups['ANALOG'].length > 0) {
                $tbody.append('<tr class="p1-input-group-header input-type-analog"><td colspan="5">Analog Inputs</td></tr>');
                $.each(groups['ANALOG'], function(i, $row) {
                    $tbody.append($row);
                });
            }
            
            // Add AES inputs
            if (groups['AES'].length > 0) {
                $tbody.append('<tr class="p1-input-group-header input-type-aes"><td colspan="5">AES/EBU Inputs</td></tr>');
                $.each(groups['AES'], function(i, $row) {
                    $tbody.append($row);
                });
            }
            
            // Add AVB inputs
            if (groups['AVB'].length > 0) {
                $tbody.append('<tr class="p1-input-group-header input-type-avb"><td colspan="5">AVB Inputs</td></tr>');
                $.each(groups['AVB'], function(i, $row) {
                    $tbody.append($row);
                });
            }
        }
        
        // Group outputs by type visually
        function groupOutputsByType() {
            var $tbody = $('#p1output_set-group tbody');
            var groups = {
                'ANALOG': [],
                'AES': [],
                'AVB': []
            };
            
            // Similar grouping logic for outputs
            $tbody.find('tr').each(function() {
                var $row = $(this);
                var outputType = $row.find('select[name$="-output_type"]').val() || 
                                $row.find('input[name$="-output_type"]').val();
                
                if (!outputType) {
                    var typeText = $row.find('.field-output_type').text().trim();
                    if (typeText.includes('AVB')) {
                        outputType = 'AVB';
                    } else if (typeText.includes('AES')) {
                        outputType = 'AES';
                    } else if (typeText.includes('Analog')) {
                        outputType = 'ANALOG';
                    }
                }
                
                if (outputType && groups[outputType]) {
                    groups[outputType].push($row);
                }
            });
            
            // Clear tbody and add back grouped rows
            $tbody.empty();
            
            // Add grouped outputs
            $.each(['ANALOG', 'AES', 'AVB'], function(i, type) {
                if (groups[type].length > 0) {
                    var label = type === 'ANALOG' ? 'Analog Outputs' : 
                               type === 'AES' ? 'AES/EBU Outputs' : 'AVB Outputs';
                    $tbody.append('<tr class="p1-output-group-header"><td colspan="5">' + label + '</td></tr>');
                    $.each(groups[type], function(j, $row) {
                        $tbody.append($row);
                    });
                }
            });
        }
        
        // Run grouping on page load
        setTimeout(function() {
            groupInputsByType();
            groupOutputsByType();
            updateOriginFieldVisibility();
        }, 100);
    });
})(django.jQuery);