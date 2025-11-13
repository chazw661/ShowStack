document.addEventListener('DOMContentLoaded', function() {
    console.log('Global navigation loaded');
    
    // Function to find the next input in the same column (for vertical navigation)
    function findVerticalInput(currentInput, direction) {
        const currentRow = currentInput.closest('tr');
        if (!currentRow) return null;
        
        const currentCell = currentInput.closest('td, th');
        if (!currentCell) return null;
        
        const cellIndex = Array.from(currentRow.children).indexOf(currentCell);
        
        let targetRow = direction > 0 ? currentRow.nextElementSibling : currentRow.previousElementSibling;
        
        while (targetRow && (targetRow.classList.contains('empty-form') || 
               targetRow.querySelector('th') || 
               !targetRow.querySelector('input, select, textarea'))) {
            targetRow = direction > 0 ? targetRow.nextElementSibling : targetRow.previousElementSibling;
        }
        
        if (!targetRow) return null;
        
        const targetCell = targetRow.children[cellIndex];
        if (!targetCell) return null;
        
        return targetCell.querySelector('input:not([type="hidden"]):not([readonly]):not([disabled]), select, textarea');
    }
    
    // Function to find next/previous input in same row
    function findHorizontalInput(currentInput, direction) {
        const currentRow = currentInput.closest('tr');
        if (!currentRow) return null;
        
        const rowInputs = Array.from(currentRow.querySelectorAll(
            'input:not([type="hidden"]):not([readonly]):not([disabled]):not([type="submit"]):not([type="button"]), select, textarea'
        )).filter(el => el.offsetParent !== null);
        
        const currentIndex = rowInputs.indexOf(currentInput);
        if (currentIndex === -1) return null;
        
        let targetIndex = currentIndex + direction;
        if (targetIndex >= 0 && targetIndex < rowInputs.length) {
            return rowInputs[targetIndex];
        }
        return null;
    }
    
    document.addEventListener('keydown', function(e) {
        const inputs = Array.from(document.querySelectorAll(
            'input:not([type="hidden"]):not([readonly]):not([disabled]):not([type="submit"]):not([type="button"]), select, textarea'
        )).filter(el => el.offsetParent !== null);
        
        const current = inputs.indexOf(e.target);
        if (current === -1) return;
        
        // Enter key - move vertically (down/up in same column)
        if (e.key === 'Enter' && 
            e.target.matches('input:not([type="submit"]):not([type="button"]), select') &&
            e.target.tagName !== 'TEXTAREA') {
            
            e.preventDefault();
            e.stopPropagation();
            
            const direction = e.shiftKey ? -1 : 1;
            const verticalTarget = findVerticalInput(e.target, direction);
            
            if (verticalTarget) {
                verticalTarget.focus();
                if (verticalTarget.select && verticalTarget.type !== 'select-one') {
                    verticalTarget.select();
                }
            } else {
                // No vertical navigation possible, move to next/prev field generally
                let next = e.shiftKey ? current - 1 : current + 1;
                if (next >= inputs.length) next = 0;
                if (next < 0) next = inputs.length - 1;
                
                if (inputs[next]) {
                    inputs[next].focus();
                    if (inputs[next].select && inputs[next].type !== 'select-one') {
                        inputs[next].select();
                    }
                }
            }
            return false;
        }
        
        // Tab key - move horizontally (left/right in same row)
        if (e.key === 'Tab') {
            e.preventDefault();
            
            const direction = e.shiftKey ? -1 : 1;
            const horizontalTarget = findHorizontalInput(e.target, direction);
            
            if (horizontalTarget) {
                horizontalTarget.focus();
                if (horizontalTarget.select && horizontalTarget.type !== 'select-one') {
                    horizontalTarget.select();
                }
            } else {
                // No horizontal navigation in row, move to next/prev field generally
                let next = e.shiftKey ? current - 1 : current + 1;
                if (next >= inputs.length) next = 0;
                if (next < 0) next = inputs.length - 1;
                
                if (inputs[next]) {
                    inputs[next].focus();
                    if (inputs[next].select && inputs[next].type !== 'select-one') {
                        inputs[next].select();
                    }
                }
            }
            return false;
        }
        
    }, true);
    
    // Add visual indicator
    const indicator = document.createElement('div');
    indicator.style.cssText = `
        position: fixed;
        bottom: 10px;
        right: 10px;
        background: rgba(0,0,0,0.85);
        color: white;
        padding: 10px 14px;
        border-radius: 5px;
        font-size: 11px;
        z-index: 9999;
        line-height: 1.5;
    `;
    
    indicator.innerHTML = `
        ⌨️ Navigation:<br>
        <strong>Enter:</strong> Next row ↓<br>
        <strong>Shift+Enter:</strong> Previous row ↑<br>
        <strong>Tab:</strong> Next field →<br>
        <strong>Shift+Tab:</strong> Previous field ←
    `;
    
    document.body.appendChild(indicator);
    
    setTimeout(() => {
        indicator.style.opacity = '0';
        indicator.style.transition = 'opacity 1s';
        setTimeout(() => indicator.remove(), 1000);
    }, 7000);
});