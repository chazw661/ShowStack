document.addEventListener("DOMContentLoaded", function () {
  console.log('mono_stereo_handler.js loaded');

  const selects = document.querySelectorAll('select[id$="mono_stereo"]');

  selects.forEach((select) => {
    const match = select.id.match(/-(\d+)-mono_stereo$/);
    if (!match) return;

    const index = parseInt(match[1]);
    const isEvenRow = (index + 1) % 2 === 0;

    // ✅ Remove even-numbered dropdowns
    if (isEvenRow) {
      const td = select.closest('td');
      if (td) {
        td.innerHTML = ''; // safest to just wipe the dropdown cell
        console.log(`Removed dropdown from even row ${index + 1}`);
      }
      return; // skip attaching event listener
    }

    // ✅ Attach change handler only to odd-numbered dropdowns
    select.addEventListener('change', function () {
      const value = select.value.trim().toUpperCase();
      const evenRow = select.closest('tr')?.nextElementSibling;
      if (!evenRow) return;

      const evenIndexMatch = evenRow.id.match(/-(\d+)$/);
      const evenIndex = evenIndexMatch ? parseInt(evenIndexMatch[1]) : null;

      if (value === 'STEREO' || value === 'ST') {
        evenRow.style.display = 'none';
        console.log(`Hiding even row: ${evenRow.id}`);

        const inputs = evenRow.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
          if (input.type === 'checkbox' || input.type === 'radio') {
            input.checked = false;
          } else {
            input.value = '';
          }
        });
      } else {
        evenRow.style.display = '';
        console.log(`Showing even row: ${evenRow.id}`);

        if (evenIndex !== null) {
          const numberInput = evenRow.querySelector('input[name$="aux_number"], input[name$="matrix_number"]');
          if (numberInput && numberInput.value.trim() === '') {
            const restoredValue = evenIndex + 1; // This is the true visible number
            numberInput.value = restoredValue;
            console.log(`Restored even number: ${restoredValue}`);
          }
        }
      }
    });

    // Trigger change once on load
    select.dispatchEvent(new Event('change'));
  });
});