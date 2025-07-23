console.log('mono_stereo_handler.js loaded');

document.addEventListener('DOMContentLoaded', function () {
    console.log('DOM fully loaded');

    // Select all Mono/Stereo dropdowns
    const selects = document.querySelectorAll('select[id$="-mono_stereo"]');
    selects.forEach((select, index) => {
        console.log('Found dropdown:', select.id);

        // Add change listener
        select.addEventListener('change', function () {
            const row = select.closest('tr');
            const evenRow = row?.nextElementSibling;

            console.log(`Dropdown changed: ${select.id}, value: ${select.value}`);
            console.log(`Even row candidate: ${evenRow?.id}`);

            if (!evenRow) return;

            if (select.value.trim().toUpperCase() === 'STEREO' || select.value.trim().toUpperCase() === 'ST') {
                console.log(`Hiding row below: ${evenRow.id}`);
                evenRow.style.display = 'none';

                // Clear inputs in the hidden even row
                const inputs = evenRow.querySelectorAll('input, select, textarea');
                inputs.forEach(input => {
                    if (input.type === 'checkbox' || input.type === 'radio') {
                        input.checked = false;
                    } else {
                        input.value = '';
                    }
                });
            } else {
                console.log(`Showing row below: ${evenRow.id}`);
                evenRow.style.display = '';
            }
        });

        // Trigger change once on load to apply initial state
        select.dispatchEvent(new Event('change'));
    });
});