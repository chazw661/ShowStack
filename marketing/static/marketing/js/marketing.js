/**
 * ShowStack Marketing JavaScript
 */

(function() {
    'use strict';

    // ============================================
    // Mobile Menu Toggle
    // ============================================
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const navbarMenu = document.getElementById('navbar-menu');

    if (mobileMenuBtn && navbarMenu) {
        mobileMenuBtn.addEventListener('click', () => {
            navbarMenu.classList.toggle('active');
            mobileMenuBtn.classList.toggle('active');
        });

        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!navbarMenu.contains(e.target) && !mobileMenuBtn.contains(e.target)) {
                navbarMenu.classList.remove('active');
                mobileMenuBtn.classList.remove('active');
            }
        });

        // Close menu when clicking a link
        navbarMenu.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                navbarMenu.classList.remove('active');
                mobileMenuBtn.classList.remove('active');
            });
        });
    }

    // ============================================
    // Smooth Scroll for Anchor Links
    // ============================================
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            if (href === '#') return;
            
            const target = document.querySelector(href);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // ============================================
    // Navbar Background on Scroll
    // ============================================
    const navbar = document.querySelector('.navbar');
    
    if (navbar) {
        const handleScroll = () => {
            if (window.scrollY > 10) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        };

        window.addEventListener('scroll', handleScroll, { passive: true });
        handleScroll(); // Check initial state
    }

    // ============================================
    // Auto-dismiss Alerts
    // ============================================
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });

    // ============================================
    // Form Validation Enhancement
    // ============================================
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="loading">Processing...</span>';
            }
        });
    });

    // ============================================
    // Intersection Observer for Animations
    // ============================================
    const animateOnScroll = () => {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('animate-in');
                }
            });
        }, {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        });

        document.querySelectorAll('.feature-card, .step, .pricing-card, .value-card').forEach(el => {
            observer.observe(el);
        });
    };

    animateOnScroll();

    // ============================================
    // AJAX Waitlist Form (Optional Enhancement)
    // ============================================
    const waitlistForms = document.querySelectorAll('.hero-form, .cta-form');
    
    waitlistForms.forEach(form => {
        form.addEventListener('submit', async function(e) {
            // Only intercept if AJAX endpoint exists
            const ajaxEndpoint = '/api/waitlist/';
            
            // For now, let forms submit normally
            // Uncomment below to enable AJAX submission
            /*
            e.preventDefault();
            
            const formData = new FormData(form);
            const email = formData.get('email');
            
            try {
                const response = await fetch(ajaxEndpoint, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-CSRFToken': formData.get('csrfmiddlewaretoken')
                    }
                });
                
                const data = await response.json();
                
                if (data.success) {
                    form.innerHTML = '<p class="success-message">✓ ' + data.message + '</p>';
                } else {
                    alert(data.message);
                }
            } catch (error) {
                console.error('Error:', error);
                form.submit(); // Fallback to normal submission
            }
            */
        });
    });

    // ============================================
    // Copy to Clipboard (for future use)
    // ============================================
    window.copyToClipboard = function(text) {
        navigator.clipboard.writeText(text).then(() => {
            // Show success feedback
            console.log('Copied to clipboard');
        }).catch(err => {
            console.error('Failed to copy:', err);
        });
    };

    console.log('ShowStack Marketing initialized');

})();
