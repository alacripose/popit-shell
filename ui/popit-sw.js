const CACHE = "popit-shell-v1";
const SHELL = ["/", "/toast.html", "/toast.css", "/toast.js", "/contour.js", "/contour.json", "/manifest.webmanifest", "/popit-icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).catch(() => undefined));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/")) return;
  event.respondWith(
    fetch(request).catch(() => caches.match(request).then((hit) => hit || caches.match("/")))
  );
});
