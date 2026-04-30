/**
 * Service Worker for Awareness Web Portal PWA
 * Enables offline functionality and caching
 */

const CACHE_NAME = 'awareness-v1.0.0';
const urlsToCache = [
    '/',
    '/static/css/site.css',
    '/static/js/dashboard-charts.js',
    '/dashboard/',
    '/training/',
    '/quizzes/',
];

// Install event - cache resources
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Opened cache');
                return cache.addAll(urlsToCache);
            })
    );
});

// Fetch event - serve from cache when offline
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // Cache hit - return response
                if (response) {
                    return response;
                }
                
                // Clone the request
                const fetchRequest = event.request.clone();
                
                return fetch(fetchRequest).then(response => {
                    // Check if valid response
                    if (!response || response.status !== 200 || response.type !== 'basic') {
                        return response;
                    }
                    
                    // Clone the response
                    const responseToCache = response.clone();
                    
                    caches.open(CACHE_NAME)
                        .then(cache => {
                            cache.put(event.request, responseToCache);
                        });
                    
                    return response;
                });
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// Background sync for offline submissions
self.addEventListener('sync', event => {
    if (event.tag === 'sync-quiz-answers') {
        event.waitUntil(syncQuizAnswers());
    }
    if (event.tag === 'sync-training-progress') {
        event.waitUntil(syncTrainingProgress());
    }
});

async function syncQuizAnswers() {
    // Sync quiz answers when back online
    console.log('Syncing quiz answers...');
    // Implementation would sync local storage data to server
}

async function syncTrainingProgress() {
    // Sync training progress when back online
    console.log('Syncing training progress...');
    // Implementation would sync local storage data to server
}

// Push notifications
self.addEventListener('push', event => {
    const data = event.data ? event.data.json() : {};
    const title = data.title || 'Awareness Portal Notification';
    const options = {
        body: data.body || 'You have a new notification',
        icon: '/static/icons/icon-192x192.png',
        badge: '/static/icons/badge-72x72.png',
        vibrate: [200, 100, 200],
        data: data.url || '/',
        actions: [
            {
                action: 'view',
                title: 'View',
                icon: '/static/icons/view.png'
            },
            {
                action: 'close',
                title: 'Close',
                icon: '/static/icons/close.png'
            }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

// Notification click handler
self.addEventListener('notificationclick', event => {
    event.notification.close();
    
    if (event.action === 'view') {
        event.waitUntil(
            clients.openWindow(event.notification.data)
        );
    }
});
