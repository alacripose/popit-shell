// A returning visitor must never be shown an older landing page than the one this deployment serves.
// The document and the contour files are network-first and never read from the HTTP cache, the cache
// is only the offline fallback, and a new build takes over immediately and drops the old caches.
const BUILD = "3ae7a2d285";
const CACHE = `popit-landing-${BUILD}`;

self.addEventListener("install", () => {
  // A waiting worker would leave the previous build in charge for one more visit.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name !== CACHE).map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // The page, its module and its drawing are the build; an image is content that may be reused.
  const isBuild = request.destination === "document" || /\.(?:js|json|css|html)$/.test(url.pathname);
  event.respondWith((async () => {
    try {
      const fresh = await fetch(request, { cache: isBuild ? "no-store" : "default" });
      if (isBuild && fresh.ok) {
        const cache = await caches.open(CACHE);
        cache.put(request, fresh.clone());
      }
      return fresh;
    } catch (error) {
      const cached = await caches.match(request);
      if (cached) return cached;
      throw error;
    }
  })());
});
