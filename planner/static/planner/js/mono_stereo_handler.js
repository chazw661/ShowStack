document.addEventListener("DOMContentLoaded", function () {
  console.log('mono_stereo_handler.js loaded - stereo pair styling version');

  const selects = document.querySelectorAll('select[id$="mono_stereo"]');

  selects.forEach((select) => {
    const match = select.id.match(/-(\d+)-mono_stereo$/);
    if (!match) return;

    const index = parseInt(match[1]);
    const rowNumber = index + 1;  // The actual aux/matrix number
    const isEvenRow = rowNumber % 2 === 0;

    // Even rows have no Mono/Stereo control of their own: the odd row above
    // owns the setting for the stereo pair. Replace the dropdown with a note
    // so the cell reads as "covered by the row above" rather than as blank.
    if (isEvenRow) {
      const td = select.closest('td');
      if (td) {
        td.textContent = '';
        const note = document.createElement('span');
        note.className = 'stereo-linked-note';
        note.textContent = '\u21b3 linked';
        note.title = `Paired with row ${rowNumber - 1} above`;
        td.appendChild(note);
      }
      return; // Skip attaching event listener
    }

    // Only odd rows have the stereo dropdown
    select.addEventListener('change', function () {
      const value = select.value.trim().toUpperCase();
      const currentRow = select.closest('tr');
      const evenRow = currentRow?.nextElementSibling;
      
      if (!evenRow) return;

      if (value === 'STEREO' || value === 'ST') {
        // Apply stereo styling
        currentRow.classList.add('stereo-pair-odd');
        evenRow.classList.add('stereo-pair-even');
        
        // Hide or modify the even row's number
        const evenNumberField = evenRow.querySelector('input[name$="aux_number"], input[name$="matrix_number"]');
        if (evenNumberField) {
          evenNumberField.style.visibility = 'hidden'; // Hide the number
          // Or alternatively, change it to show pairing:
          // evenNumberField.value = `↑${rowNumber}`;
        }
        
        // Add L/R indicators
        const oddNumberField = currentRow.querySelector('input[name$="aux_number"], input[name$="matrix_number"]');
        if (oddNumberField) {
          oddNumberField.classList.add('stereo-left');
        }
        
        console.log(`Created stereo pair: ${rowNumber}-${rowNumber + 1}`);
      } else {
        // MONO - remove stereo styling
        currentRow.classList.remove('stereo-pair-odd');
        evenRow.classList.remove('stereo-pair-even');
        
        // Restore the even row's number
        const evenNumberField = evenRow.querySelector('input[name$="aux_number"], input[name$="matrix_number"]');
        if (evenNumberField) {
          evenNumberField.style.visibility = 'visible';
          evenNumberField.value = rowNumber + 1; // Restore the original number
        }
        
        // Remove L indicator
        const oddNumberField = currentRow.querySelector('input[name$="aux_number"], input[name$="matrix_number"]');
        if (oddNumberField) {
          oddNumberField.classList.remove('stereo-left');
        }
        
        console.log(`Removed stereo styling from rows ${rowNumber}-${rowNumber + 1}`);
      }
    });

    // Trigger change once on load to apply initial state
    select.dispatchEvent(new Event('change'));
  });
});