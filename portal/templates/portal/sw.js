// Service Worker von Drive: zeigt ohne Verbindung die Offline-Seite.
// Gespeichert werden nur diese Seite, CSS und Logo – keine Daten aus dem Fahrtenbuch.
const CACHE = "drive-offline-{{ version }}";
const OFFLINE = "{{ offline }}";
const DATEIEN = [OFFLINE{% for d in dateien %}, "{{ d }}"{% endfor %}];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(DATEIEN)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((namen) => Promise.all(namen.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const anfrage = e.request;
  if (anfrage.mode === "navigate") {
    e.respondWith(fetch(anfrage).catch(() => caches.match(OFFLINE)));
  } else if (anfrage.method === "GET" && DATEIEN.includes(new URL(anfrage.url).pathname)) {
    e.respondWith(caches.match(anfrage).then((r) => r || fetch(anfrage)));
  }
});
