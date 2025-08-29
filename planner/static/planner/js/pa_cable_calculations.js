// planner/static/planner/js/pa_cable_calculations.js

// Defensive jQuery loading
window.addEventListener('load', function() {
    (function($) {
        'use strict';
        
        function updateCableCalculations(row) {
            // Get input values
            var quantity = parseFloat(row.find('[id$="-quantity"]').val()) || 0;
            var lengthPerRun = parseFloat(row.find('[id$="-length_per_run"]').val()) || 0;
            var serviceLoop = parseFloat(row.find('[id$="-service_loop"]').val()) || 10.0;
            
            // Calculate totals
            var totalPerRun = lengthPerRun + serviceLoop;
            var totalLength = totalPerRun * quantity;
            
            // Update display fields
            row.find('[id$="-total_per_run"]').val(totalPerRun.toFixed(1));
            row.find('[id$="-total_length"]').val(totalLength.toFixed(1));
            
            // Update visual indicators
            if (totalLength > 0) {
                row.find('[id$="-total_length"]').css('background-color', '#e8f4f8');
            }
        }
        
        function updateGrandTotals() {
            var cableTotals = {};
            var grandTotal = 0;
            var totalRuns = 0;
            
            // Iterate through all rows
            $('.dynamic-pacableschedule_set').find('.form-row:not(.empty-form)').each(function() {
                var row = $(this);
                var cableType = row.find('[id$="-cable_type"] option:selected').text();
                var quantity = parseInt(row.find('[id$="-quantity"]').val()) || 0;
                var totalLength = parseFloat(row.find('[id$="-total_length"]').val()) || 0;
                
                if (cableType && totalLength > 0) {
                    if (!cableTotals[cableType]) {
                        cableTotals[cableType] = {
                            runs: 0,
                            length: 0
                        };
                    }
                    cableTotals[cableType].runs += quantity;
                    cableTotals[cableType].length += totalLength;
                    grandTotal += totalLength;
                    totalRuns += quantity;
                }
            });
            
            // Update summary display (if exists)
            if ($('#cable-summary').length) {
                var summaryHtml = '<h3>Cable Summary</h3><table class="cable-summary-table">';
                summaryHtml += '<tr><th>Cable Type</th><th>Runs</th><th>Total Length (ft)</th></tr>';
                
                for (var type in cableTotals) {
                    summaryHtml += '<tr>';
                    summaryHtml += '<td>' + type + '</td>';
                    summaryHtml += '<td>' + cableTotals[type].runs + '</td>';
                    summaryHtml += '<td>' + cableTotals[type].length.toFixed(1) + '</td>';
                    summaryHtml += '</tr>';
                }
                
                summaryHtml += '<tr class="total-row">';
                summaryHtml += '<td><strong>TOTAL</strong></td>';
                summaryHtml += '<td><strong>' + totalRuns + '</strong></td>';
                summaryHtml += '<td><strong>' + grandTotal.toFixed(1) + '</strong></td>';
                summaryHtml += '</tr></table>';
                
                $('#cable-summary').html(summaryHtml);
            }
        }
        
        function initializeRow(row) {
            // Add change handlers
            row.find('[id$="-quantity"], [id$="-length_per_run"], [id$="-service_loop"]').on('input change', function() {
                updateCableCalculations(row);
                updateGrandTotals();
            });
            
            // Set default service loop if empty
            var serviceLoopField = row.find('[id$="-service_loop"]');
            if (!serviceLoopField.val()) {
                serviceLoopField.val('10.0');
            }
            
            // Initial calculation
            updateCableCalculations(row);
        }
        
        $(document).ready(function() {
            // Initialize existing rows
            $('.dynamic-pacableschedule_set .form-row:not(.empty-form)').each(function() {
                initializeRow($(this));
            });
            
            // Handle new rows added
            $('.add-row a').on('click', function() {
                setTimeout(function() {
                    $('.dynamic-pacableschedule_set .form-row:not(.empty-form)').each(function() {
                        var row = $(this);
                        if (!row.data('initialized')) {
                            initializeRow(row);
                            row.data('initialized', true);
                        }
                    });
                }, 100);
            });
            
            // Add summary container if in change form
            if ($('.change-form').length && !$('#cable-summary').length) {
                $('<div id="cable-summary" class="module"></div>').insertAfter('.submit-row');
            }
            
            // Initial grand total calculation
            updateGrandTotals();
            
            // Auto-populate common patterns
            $('body').on('change', '[id$="-zone"]', function() {
                var row = $(this).closest('.form-row');
                var zone = $(this).val();
                var toField = row.find('[id$="-to_location"]');
                
                // Auto-fill destination based on zone
                var destinations = {
                    'MAIN_L': 'MAIN LEFT ARRAY',
                    'MAIN_R': 'MAIN RIGHT ARRAY',
                    'MAIN_C': 'MAIN CENTER ARRAY',
                    'SUB_L': 'SUB LEFT ARRAY',
                    'SUB_R': 'SUB RIGHT ARRAY',
                    'SUB_C': 'SUB CENTER ARRAY',
                    'FRONT_FILL': 'FRONT FILL',
                    'OUT_FILL_L': 'OUT FILL LEFT',
                    'OUT_FILL_R': 'OUT FILL RIGHT',
                    'DELAY_1': 'DELAY TOWER 1',
                    'DELAY_2': 'DELAY TOWER 2',
                    'LIP_FILL': 'LIP FILL',
                    'UNDER_BALC': 'UNDER BALCONY',
                    'BALCONY': 'BALCONY FILL'
                };
                
                if (destinations[zone] && !toField.val()) {
                    toField.val(destinations[zone]);
                }
            });
        });
        
    })(django.jQuery);
});