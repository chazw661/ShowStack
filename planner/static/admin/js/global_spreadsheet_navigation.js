(function() {
    'use strict';
    
    document.addEventListener('DOMContentLoaded', function() {
        // Only run on admin change/add pages
        if (!document.body.classList.contains('change-form')) return;
        
        console.log('📊 Global spreadsheet navigation activated');
        
        // Get all focusable inputs
        function getFocusableInputs() {
            const selectors = [
                'input[type="text"]:not([readonly]):not([disabled]):visible',
                'input[type="number"]:not([readonly]):not([disabled]):visible',
                'input[type="email"]:not([readonly]):not([disabled]):visible',
                'input[type="url"]:not([readonly]):not([disabled]):visible',
                'textarea:not([readonly]):not([disabled]):visible',
                'select:not([disabled]):visible'
            ];
            
            return Array.from(document.querySelectorAll(selectors.join(', ')))
                .filter(el => el.offsetParent !== null && !el.closest('.empty-form'));
        }
        
        // Navigate to next/previous input
        function navigateInput(current, direction) {
            const inputs = getFocusableInputs();
            const currentIndex = inputs.indexOf(current);
            if (currentIndex === -1) return;
            
            let nextIndex = currentIndex + direction;
            if (nextIndex >= inputs.length) nextIndex = 0;
            if (nextIndex < 0) nextIndex = inputs.length - 1;
            
            const nextInput = inputs[nextIndex];
            if (nextInput) {
                nextInput.focus();
                if (nextInput.select && nextInput.type !== 'select-one') {
                    setTimeout(() => nextInput.select(), 10);
                }
                nextInput.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
        
        // Add keyboard event listener
        document.addEventListener('keydown', function(e) {
            const target = e.target;
            const isInput = target.matches('input, select, textarea');
            
            if (!isInput) return;
            
            // Enter key navigation (except in textareas unless Shift is held)
            if (e.key === 'Enter') {
                if (target.tagName === 'TEXTAREA' && !e.shiftKey) {
                    return; // Allow normal line breaks in textarea
                }
                
                e.preventDefault();
                navigateInput(target, e.shiftKey ? -1 : 1);
            }
            
            // Tab key already works, but we can enhance with vertical navigation
            if (e.key === 'ArrowDown' && e.altKey) {
                e.preventDefault();
                navigateInput(target, 1);
            }
            
            if (e.key === 'ArrowUp' && e.altKey) {
                e.preventDefault();
                navigateInput(target, -1);
            }
        });
        
        // Add visual feedback
        const style = document.createElement('style');
        style.textContent = `
            input:focus, select:focus, textarea:focus {
                box-shadow: 0 0 5px rgba(100, 181, 246, 0.5) !important;
                border-color: #64B5F6 !important;
            }
        `;
        document.head.appendChild(style);
    });
})();