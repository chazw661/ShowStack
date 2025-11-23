(function($) {
    $(document).ready(function() {
        // Apply background colors to amp rows based on their color field
        $('#result_list tbody tr').each(function() {
            var $row = $(this);
            // Find the color preview cell (has the colored div)
            var $colorCell = $row.find('td').filter(function() {
                return $(this).find('div[style*="background-color"]').length > 0;
            });
            
            if ($colorCell.length > 0) {
                var $colorDiv = $colorCell.find('div[style*="background-color"]');
                var style = $colorDiv.attr('style');
                var colorMatch = style.match(/background-color:\s*(#[0-9A-Fa-f]{6})/);
                
                if (colorMatch && colorMatch[1]) {
                    var color = colorMatch[1];
                    // Apply semi-transparent version to the row
                    $row.css('background-color', color + '40'); // Add 40 for 25% opacity
                }
            }
        });
    });
})(django.jQuery);