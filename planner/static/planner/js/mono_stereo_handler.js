console.log('mono_stereo_handler.js loaded');

document.addEventListener('DOMContentLoaded', function () {
  console.log('DOM fully loaded');

  const selects = document.querySelectorAll('select[id$="-mono_stereo"]');
  selects.forEach((select) => {
    console.log(`Found dropdown: ${select.id}`);

    select.addEventListener('change', function () {
      const row = select.closest('tr');
      const evenRow = row?.nextElementSibling;
      if (!evenRow) return;

      const isStereo = select.value.trim().toUpperCase() === 'STEREO' || select.value.trim().toUpperCase() === 'ST';

      if (isStereo) {
        console.log(`Hiding row below: ${evenRow.id}`);
        evenRow.style.display = 'none';

        // Clear all input/select/textarea in evenRow
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

        // Restore aux_number or matrix_number if empty
        const numberInput = evenRow.querySelector('input[name$="aux_number"], input[name$="matrix_number"]');
        if (numberInput && numberInput.value.trim() === '') {
          const idMatch = evenRow.id.match(/-(\d+)$/);
          if (idMatch) {
            const evenIndex = parseInt(idMatch[1]);
            numberInput.value = evenIndex + 1;
            console.log(`Restored number in ${numberInput.name} to: ${numberInput.value}`);
          }
        }
      }
    });

    // Trigger initial state
    select.dispatchEvent(new Event('change'));
  });
});