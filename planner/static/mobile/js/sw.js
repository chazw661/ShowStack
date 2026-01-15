/**
 * ShowStack Service Worker
 * Phase 1: Basic PWA install capability
 * Phase 4 will add full offline caching
 */

const CACHE_NAME = 'showstack-v1';
const STATIC_CACHE = 'showstack-static-v1';
const DYNAMIC_CACHE = 'showstack-dynamic-v1';

// Assets to pre-cache (add more in Phase 4)
const PRECACHE_ASSETS = [
    '/static/mobile/css/mobile.css',
    '/static/mobile/js/mobile.js',
    '/static/mobile/icons/icon-192.png',
    '/static/mobile/icons/icon-512.png',
];

// Install event - pre-cache essential assets
self.addEventListener('install', (event) => {
    console.log('[SW] Installing ShowStack Service Worker');
    
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => {
                console.log('[SW] Pre-caching static assets');
                // For Phase 1, just skip if assets aren't available yet
                return cache.addAll(PRECACHE_ASSETS).catch(err => {
                    console.log('[SW] Pre-cache skipped (assets not yet available):', err);
                });
            })
            .then(() => {
                console.log('[SW] Install complete');
                return self.skipWaiting();
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[SW] Activating ShowStack Service Worker');
    
    event.waitUntil(
        caches.keys()
            .then(cacheNames => {
                return Promise.all(
                    cacheNames
                        .filter(cacheName => {
                            // Delete old version caches
                            return cacheName.startsWith('showstack-') && 
                                   cacheName !== STATIC_CACHE && 
                                   cacheName !== DYNAMIC_CACHE;
                        })
                        .map(cacheName => {
                            console.log('[SW] Deleting old cache:', cacheName);
                            return caches.delete(cacheName);
                        })
                );
            })
            .then(() => {
                console.log('[SW] Activation complete');
                return self.clients.claim();
            })
    );
});

// Fetch event - network first with fallback
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests
    if (request.method !== 'GET') {
        return;
    }
    
    // Skip cross-origin requests
    if (url.origin !== location.origin) {
        return;
    }
    
    // For Phase 1: Network first, no caching
    // Full offline support will be added in Phase 4
    event.respondWith(
        fetch(request)
            .then(response => {
                // Clone response for potential caching
                const responseClone = response.clone();
                
                // Cache static assets
                if (request.url.includes('/static/')) {
                    caches.open(STATIC_CACHE)
                        .then(cache => cache.put(request, responseClone));
                }
                
                return response;
            })
            .catch(() => {
                // Try to serve from cache if network fails
                return caches.match(request)
                    .then(cachedResponse => {
                        if (cachedResponse) {
                            return cachedResponse;
                        }
                        
                        // If it's a navigation request, could show offline page
                        // (Will be implemented in Phase 4)
                        if (request.mode === 'navigate') {
                            return new Response(
                                '<html><body style="background:#1a1a2e;color:#fff;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;"><div style="text-align:center"><h1>Offline</h1><p>ShowStack requires an internet connection.</p></div></body></html>',
                                {
                                    headers: { 'Content-Type': 'text/html' }
                                }
                            );
                        }
                        
                        return new Response('Offline', { status: 503 });
                    });
            })
    );
});

// Handle messages from the main app
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data && event.data.type === 'CLEAR_CACHE') {
        caches.keys().then(cacheNames => {
            cacheNames.forEach(cacheName => {
                if (cacheName.startsWith('showstack-')) {
                    caches.delete(cacheName);
                }
            });
        });
    }
});

// Background sync (for Phase 4)
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-data') {
        console.log('[SW] Background sync triggered');
        // Will implement data sync in Phase 4
    }
});

// Push notifications (future feature)
self.addEventListener('push', (event) => {
    if (event.data) {
        const data = event.data.json();
        const options = {
            body: data.body,
            icon: '/static/mobile/icons/icon-192.png',
            badge: '/static/mobile/icons/icon-192.png',
            vibrate: [100, 50, 100],
            data: {
                url: data.url || '/m/'
            }
        };
        
        event.waitUntil(
            self.registration.showNotification(data.title || 'ShowStack', options)
        );
    }
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    const url = event.notification.data?.url || '/m/';
    
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(windowClients => {
                // Check if there's already a window open
                for (const client of windowClients) {
                    if (client.url.includes('/m/') && 'focus' in client) {
                        return client.focus();
                    }
                }
                // Open new window if needed
                if (clients.openWindow) {
                    return clients.openWindow(url);
                }
            })
    );
});

console.log('[SW] ShowStack Service Worker loaded');
