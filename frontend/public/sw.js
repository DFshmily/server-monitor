/* DFshmily server-monitor service worker: app-shell cache + network-first API. */
const CACHE = "dfshmily-monitor-v1";
const SHELL = [
  "/",
  "/manifest.json",
  "/pwa-icon-192.png",
  "/pwa-icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // Never cache realtime data / websocket / auth
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws")) return;

  // Static assets (hashed by Vite): cache-first
  if (url.pathname.startsWith("/assets/")) {
    e.respondWith(
      caches.match(e.request).then(
        (hit) =>
          hit ||
          fetch(e.request).then((resp) => {
            const copy = resp.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy));
            return resp;
          })
      )
    );
    return;
  }

  // Navigation & everything else: network-first with cache fallback (offline hint)
  if (e.request.mode === "navigate" || url.origin === self.location.origin) {
    e.respondWith(
      fetch(e.request)
        .then((resp) => {
          if (resp.ok && url.pathname === "/") {
            const copy = resp.clone();
            caches.open(CACHE).then((c) => c.put("/", copy));
          }
          return resp;
        })
        .catch(() => caches.match("/"))
    );
  }
});
