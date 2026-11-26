// Bumped when the home's script changes: a tile's launch proof lives in phone.js, and a cached
// copy would keep showing a refusal the shell no longer makes.
const CACHE = "popit-springboard-v5";
const SHELL = [
  "/phone.html", "/phone.css", "/phone.js", "/phone-calls.js",
  "/phone-manifest.webmanifest", "/popit-icon-512.png", "/popit-icon.svg",
];

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
  // The phone's offline guarantee is kept: a cached asset is still served when the network is
  // gone. Only a navigation may be answered with the shell document, because answering a
  // module script with HTML is how a window loses its contour and looks refused. A script
  // that is not cached fails as a script; it is never replaced by a page.
  event.respondWith(
    fetch(request).catch(() => caches.match(request).then((hit) => {
      if (hit) return hit;
      return request.mode === "navigate" ? caches.match("/phone.html") : Response.error();
    }))
  );
});
