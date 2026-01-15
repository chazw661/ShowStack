/**
 * ShowStack Mobile JavaScript
 * Core functionality for mobile PWA
 */

(function() {
    'use strict';

    // ============================================
    // Service Worker Registration
    // ============================================
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/static/mobile/js/sw.js')
                .then(registration => {
                    console.log('ShowStack SW registered:', registration.scope);
                    
                    // Check for updates
                    registration.addEventListener('updatefound', () => {
                        const newWorker = registration.installing;
                        newWorker.addEventListener('statechange', () => {
                            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                                // New content available, show refresh prompt if needed
                                console.log('New content available');
                            }
                        });
                    });
                })
                .catch(err => {
                    console.log('ShowStack SW registration failed:', err);
                });
        });
    }

    // ============================================
    // PWA Install Prompt
    // ============================================
    let deferredPrompt = null;

    window.addEventListener('beforeinstallprompt', (e) => {
        // Prevent Chrome's default install prompt
        e.preventDefault();
        deferredPrompt = e;
        
        // Show custom install button if you have one
        const installBtn = document.getElementById('install-btn');
        if (installBtn) {
            installBtn.classList.remove('hidden');
            installBtn.addEventListener('click', installApp);
        }
    });

    function installApp() {
        if (!deferredPrompt) return;
        
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then((choiceResult) => {
            if (choiceResult.outcome === 'accepted') {
                console.log('User installed ShowStack');
            }
            deferredPrompt = null;
            
            const installBtn = document.getElementById('install-btn');
            if (installBtn) {
                installBtn.classList.add('hidden');
            }
        });
    }

    // ============================================
    // Touch Feedback
    // ============================================
    // Add visual feedback for touch interactions
    document.addEventListener('touchstart', function(e) {
        const target = e.target.closest('.project-card, .module-tile, .btn, .list-item');
        if (target) {
            target.classList.add('touching');
        }
    }, { passive: true });

    document.addEventListener('touchend', function(e) {
        const touching = document.querySelectorAll('.touching');
        touching.forEach(el => el.classList.remove('touching'));
    }, { passive: true });

    document.addEventListener('touchcancel', function(e) {
        const touching = document.querySelectorAll('.touching');
        touching.forEach(el => el.classList.remove('touching'));
    }, { passive: true });

    // ============================================
    // Viewport Height Fix for iOS
    // ============================================
    // Fix for iOS Safari 100vh issue
    function setViewportHeight() {
        const vh = window.innerHeight * 0.01;
        document.documentElement.style.setProperty('--vh', `${vh}px`);
    }

    setViewportHeight();
    window.addEventListener('resize', setViewportHeight);
    window.addEventListener('orientationchange', () => {
        setTimeout(setViewportHeight, 100);
    });

    // ============================================
    // Form Enhancements
    // ============================================
    // Auto-focus first input on forms
    const firstInput = document.querySelector('form .input:not([type="hidden"])');
    if (firstInput && !isMobile()) {
        // Only auto-focus on non-mobile to avoid keyboard popup
        firstInput.focus();
    }

    // Helper to detect mobile
    function isMobile() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    }

    // ============================================
    // Pull to Refresh Prevention
    // ============================================
    // Prevent pull-to-refresh on scrollable areas
    let touchStartY = 0;
    
    document.addEventListener('touchstart', (e) => {
        touchStartY = e.touches[0].clientY;
    }, { passive: true });

    document.addEventListener('touchmove', (e) => {
        const touchY = e.touches[0].clientY;
        const touchDiff = touchY - touchStartY;
        
        // If at top of page and pulling down, prevent refresh
        if (window.scrollY === 0 && touchDiff > 0) {
            // Let it happen naturally, but could prevent if needed
        }
    }, { passive: true });

    // ============================================
    // Messages Auto-dismiss
    // ============================================
    // Auto-hide flash messages after 5 seconds
    const messages = document.querySelectorAll('.message');
    messages.forEach(msg => {
        setTimeout(() => {
            msg.style.opacity = '0';
            msg.style.transform = 'translateY(-10px)';
            setTimeout(() => msg.remove(), 300);
        }, 5000);
    });

    // ============================================
    // Network Status
    // ============================================
    // Monitor online/offline status
    function updateOnlineStatus() {
        const syncIndicator = document.querySelector('.sync-indicator');
        if (syncIndicator) {
            if (navigator.onLine) {
                syncIndicator.classList.remove('offline');
                syncIndicator.classList.add('synced');
                syncIndicator.title = 'Online';
            } else {
                syncIndicator.classList.remove('synced');
                syncIndicator.classList.add('offline');
                syncIndicator.title = 'Offline';
            }
        }
    }

    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);
    updateOnlineStatus();

    // ============================================
    // Keyboard Navigation
    // ============================================
    // Add keyboard support for cards
    document.querySelectorAll('.project-card, .module-tile.module-available').forEach(card => {
        if (!card.hasAttribute('tabindex')) {
            card.setAttribute('tabindex', '0');
        }
        
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                card.click();
            }
        });
    });

    // ============================================
    // Utility Functions (exposed globally)
    // ============================================
    window.ShowStack = {
        // Format date for display
        formatDate: function(dateStr) {
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric'
            });
        },
        
        // Format time for display
        formatTime: function(dateStr) {
            const date = new Date(dateStr);
            return date.toLocaleTimeString('en-US', {
                hour: 'numeric',
                minute: '2-digit'
            });
        },
        
        // Show loading state
        showLoading: function(element) {
            element.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
        },
        
        // Hide loading state
        hideLoading: function(element, content) {
            element.innerHTML = content;
        },
        
        // Debounce function
        debounce: function(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },
        
        // Check if element is in viewport
        isInViewport: function(element) {
            const rect = element.getBoundingClientRect();
            return (
                rect.top >= 0 &&
                rect.left >= 0 &&
                rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                rect.right <= (window.innerWidth || document.documentElement.clientWidth)
            );
        },
        
        // Scroll to element smoothly
        scrollTo: function(element, offset = 0) {
            const top = element.getBoundingClientRect().top + window.scrollY - offset;
            window.scrollTo({
                top: top,
                behavior: 'smooth'
            });
        }
    };

    // ============================================
    // Initialize
    // ============================================
    console.log('ShowStack Mobile initialized');

})();
