// ============================================================
// sw.js — 서비스 워커: 앱·엔진·산 자료를 휴대폰에 저장해 두고, 인터넷이 없어도 열리게 한다.
//   처음 한 번 인터넷으로 열면 앱 화면 + C 엔진(wasm) + 북한산 자료를 저장한다.
//   다른 산은 설정의 '이 산 오프라인 저장'으로 저장한다.
//   요청이 오면 저장된 것을 먼저 쓰고(오프라인에서도 바로 열림), 인터넷이 되면 뒤에서 새것으로 바꿔 둔다.
// ============================================================
const CACHE = 'dieudieu-mobile-v2';   // 엔진·등산로가 바뀌면 숫자를 올려 휴대폰에 저장된 옛 파일을 한 번에 바꾼다
const SHELL = [
  './', 'index.html', 'style.css', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png',
  'js/app.js', 'js/mapview.js', 'js/geo.js', 'js/ini.js', 'js/trails.js', 'js/fireinfo.js', 'js/status.js', 'js/fuel.js',
  'js/engine_core.js', 'js/engine_worker.js', 'engine/wildfire.wasm',
  'vendor/browser_wasi_shim/wasi.js', 'vendor/browser_wasi_shim/wasi_defs.js', 'vendor/browser_wasi_shim/fd.js',
  'vendor/browser_wasi_shim/fs_mem.js', 'vendor/browser_wasi_shim/debug.js',
  'assets/mountains.json', '../data/scenarios/fuel_models.csv',
  // 처음 화면의 산 (북한산)
  'assets/bukhansan/meta.json', 'assets/bukhansan/terrain_none.png', 'assets/bukhansan/terrain_spring.png',
  'assets/bukhansan/terrain_summer.png', 'assets/bukhansan/terrain_autumn.png', 'assets/bukhansan/terrain_winter.png',
  '../data/scenarios/mountain_bukhansan.ini', '../data/mountains/bukhansan/elev.asc',
  '../data/mountains/bukhansan/fuel.asc', '../data/mountains/bukhansan/trails.txt',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  event.respondWith(caches.open(CACHE).then(async (cache) => {
    const url = req.mode === 'navigate' ? new URL('index.html', self.registration.scope).href : req.url;
    const saved = await cache.match(url, { ignoreSearch: true });
    const fresh = fetch(req).then((res) => {
      if (res.ok && req.mode !== 'navigate') cache.put(req, res.clone());
      return res;
    }).catch(() => null);
    if (saved) { event.waitUntil(fresh); return saved; }
    return (await fresh) || new Response('오프라인이라 아직 저장되지 않은 파일은 열 수 없습니다.', { status: 503 });
  }));
});

// 앱이 '이 산 오프라인 저장'을 누르면 그 산의 파일 목록을 받아 저장한다
self.addEventListener('message', (event) => {
  if (!event.data || event.data.type !== 'cache-urls') return;
  const port = event.ports[0];
  event.waitUntil(caches.open(CACHE)
    .then((c) => c.addAll(event.data.urls))
    .then(() => port.postMessage({ ok: true, count: event.data.urls.length }))
    .catch((e) => port.postMessage({ ok: false, error: String(e) })));
});
