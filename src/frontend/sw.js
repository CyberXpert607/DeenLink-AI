const CACHE_NAME = 'deenlink-v1';
const STATIC_ASSETS = [
    './',                    // Changed from '/' to './' for relative path
    './deenai.html',         // Changed from '/index.html'
    './css/styles.css',
    './js/script.js',
    'https://cdn.jsdelivr.net/npm/marked/marked.min.js',
    'https://cdn.jsdelivr.net/npm/dompurify@3.0.5/dist/purify.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            // Load files individually so one missing file doesn't break everything
            return Promise.all(
                STATIC_ASSETS.map(url => {
                    return cache.add(url).catch(err => {
                        console.warn(`[SW] Failed to cache ${url}:`, err);
                    });
                })
            );
        }).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then(names => {
            return Promise.all(
                names.filter(name => name !== CACHE_NAME)
                    .map(name => caches.delete(name))
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    // Skip API calls
    if (event.request.url.includes('/api/') || 
        event.request.url.includes('/ask/stream')) {
        return;
    }

    event.respondWith(
        caches.match(event.request).then(response => {
            return response || fetch(event.request).then(fetchResponse => {
                return caches.open(CACHE_NAME).then(cache => {
                    cache.put(event.request, fetchResponse.clone());
                    return fetchResponse;
                });
            });
        }).catch(() => {
            // Fallback to deenai.html for navigation
            if (event.request.mode === 'navigate') {
                return caches.match('./deenai.html');
            }
        })
    );
});