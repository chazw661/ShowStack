(function() {
    'use strict';
    
    let lastChecksum = null;
    let lastActivity = Date.now();
    let hasUnseenUpdates = false;
    const CHECK_INTERVAL = 5000; // 5 seconds
    const IDLE_THRESHOLD = 30000; // 30 seconds
    
    // Track user activity
    function updateActivity() {
        lastActivity = Date.now();
        hideUpdateBanner();
    }
    
    // Listen for user interactions
    document.addEventListener('click', updateActivity);
    document.addEventListener('keypress', updateActivity);
    document.addEventListener('input', updateActivity);
    document.addEventListener('change', updateActivity);
    
    // Create update banner
    function createBanner() {
        const banner = document.createElement('div');
        banner.id = 'mic-tracker-update-banner';
        banner.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: #4a9eff;
            color: white;
            padding: 12px;
            text-align: center;
            z-index: 99999;
            display: none;
            font-size: 14px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        `;
        banner.innerHTML = `
            <strong>Updates available!</strong> 
            <button onclick="location.reload()" style="
                margin-left: 15px;
                background: white;
                color: #4a9eff;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                cursor: pointer;
                font-weight: bold;
            ">Refresh Now</button>
            <button onclick="document.getElementById('mic-tracker-update-banner').style.display='none'" style="
                margin-left: 8px;
                background: transparent;
                color: white;
                border: 1px solid white;
                padding: 6px 16px;
                border-radius: 4px;
                cursor: pointer;
            ">Dismiss</button>
        `;
        document.body.insertBefore(banner, document.body.firstChild);
        return banner;
    }
    
    function showUpdateBanner() {
        let banner = document.getElementById('mic-tracker-update-banner');
        if (!banner) {
            banner = createBanner();
        }
        banner.style.display = 'block';
        hasUnseenUpdates = true;
    }
    
    function hideUpdateBanner() {
        const banner = document.getElementById('mic-tracker-update-banner');
        if (banner) {
            banner.style.display = 'none';
        }
        hasUnseenUpdates = false;
    }
    
    function isUserIdle() {
        return (Date.now() - lastActivity) > IDLE_THRESHOLD;
    }
    
    async function checkForUpdates() {
        try {
            const response = await fetch('/api/mic-tracker-checksum/');
            const data = await response.json();
            
            if (!data.checksum) {
                return; // No project selected
            }
            
            // First load - store checksum
            if (lastChecksum === null) {
                lastChecksum = data.checksum;
                return;
            }
            
            // Check if data changed
            if (data.checksum !== lastChecksum) {
                lastChecksum = data.checksum;
                
                if (isUserIdle() && !hasUnseenUpdates) {
                    // User is idle - auto refresh
                    console.log('Mic Tracker: Auto-refreshing (user idle)');
                    location.reload();
                } else {
                    // User is active - show banner
                    console.log('Mic Tracker: Updates available');
                    showUpdateBanner();
                }
            }
        } catch (error) {
            console.error('Mic Tracker: Error checking for updates', error);
        }
    }
    
    // Start polling
    console.log('Mic Tracker: Auto-refresh enabled (checking every 5 seconds)');
    setInterval(checkForUpdates, CHECK_INTERVAL);
    
    // Initial check after 5 seconds
    setTimeout(checkForUpdates, CHECK_INTERVAL);
})();