/* DFshmily server-monitor service worker: app-shell cache + network-first API. */
/* v2: 导航请求(network/HTML)永不回退到可能过期的缓存 HTML —— 避免 iOS PWA
   加载旧 index.html 引用已失效的 assets hash 而报
   "The string did not match the expected pattern"。 */
const CACHE = "dfshmily-monitor-v2";
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

  // Navigation & everything else: network-first; on failure redirect to live origin
  // (do NOT serve a cached HTML shell — stale asset hashes break the app on iOS PWA)
  if (e.request.mode === "navigate" || url.origin === self.location.origin) {
    e.respondWith(
      fetch(e.request).catch(() => {
        if (url.pathname === "/") {
          return caches.match("/").then((hit) => hit || Response.error());
        }
        return Response.error();
      })
    );
  }
});
