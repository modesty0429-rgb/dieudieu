// ============================================================
// app.js — 산불 대피 안내 휴대폰 앱 (화면과 흐름)
//
//   1. 산 자료(지형·숲·등산로·시나리오)를 받아 둔다 → 서비스 워커가 저장해 오프라인에서도 열림
//   2. 내 위치: GPS (인터넷 없이 됨) 또는 데모 모드에서 지도에 찍기
//   3. 불 정보: 링크·문자(관제가 보냄) / 지도에서 연기 위치 찍기
//   4. C 엔진(wildfire.wasm)을 휴대폰 안에서 실행 → 불 도착 시각, 내 대피 경로
//   5. 시각이 흐르면 경보 단계를 다시 판정하고, 단계가 올라가면 진동·알림
// ============================================================

import { MapView } from './mapview.js';
import { latLonToCell, cellToLatLon, insideMap, distanceM, distanceText } from './geo.js';
import { parseIni, buildScenario, writeIni } from './ini.js';
import { parseTrails, attachMe, writeTrailFile, writeHikerFile, routePolyline } from './trails.js';
import { encodeFire, decodeFire, windName } from './fireinfo.js';
import { LEVELS, parseGrid, assessAlert, dangerTime, nightLevel, sampleAt, seasonOf, SEASON_NAMES, minutesText } from './status.js';
import { parseAscInts, burnableCodes, nearestForest } from './fuel.js';

const $ = (id) => document.getElementById(id);
const app = {
  mountains: [],
  meta: null,
  base: null,          // 산 시나리오 (.ini 를 읽은 것)
  texts: null,         // 엔진에 넘길 파일 글 (지형·연료·연료표)
  graph: null,         // 등산로
  terrains: {},        // 계절별 바탕 지도
  me: null,            // { x, y, acc, source: 'gps' | 'demo', lat, lon }
  fire: null,          // { cell:{x,y}, time: Date, weather, source, receivedAt, noticeMin }
  result: null,        // 엔진 결과
  tapMode: null,       // 'me' | 'fire'
  speed: 30,           // 데모 시간 배속
  follow: false,       // 안내대로 걸어서 대피 (데모)
  lastLevel: 0,
  gpsWatch: null,
  computing: false,
  pending: false,
};

// ------------------------------------------------------------ 엔진 (Web Worker)
const worker = new Worker(new URL('./engine_worker.js', import.meta.url), { type: 'module' });
let jobId = 0;
const jobs = new Map();
worker.onmessage = (e) => {
  const msg = e.data;
  const job = jobs.get(msg.id);
  if (!job) return;
  if (msg.progress !== undefined) $('busy-text').textContent = `계산 중… ${msg.progress}%`;
  if (msg.done) { jobs.delete(msg.id); job(msg); }
};
function runEngine(files, args) {
  return new Promise((resolve) => {
    const id = ++jobId;
    jobs.set(id, resolve);
    worker.postMessage({ id, files, args });
  });
}

// ------------------------------------------------------------ 지도
const map = new MapView($('map'), (cell) => onMapTap(cell));

function toast(text, ms = 3500) {
  const t = $('toast');
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), ms);
}

function setTapMode(mode, hint) {
  app.tapMode = mode;
  $('tap-hint').hidden = !mode;
  $('tap-hint').textContent = hint || '';
}

// ------------------------------------------------------------ 산 자료 받기
async function fetchText(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} (${r.status})`);
  return r.text();
}
function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(url));
    img.src = url;
  });
}

async function loadMountain(id) {
  const meta = JSON.parse(await fetchText(`assets/${id}/meta.json`));
  const [ini, elev, fuel, models, trails] = await Promise.all([
    fetchText(meta.files.scenario), fetchText(meta.files.elevation), fetchText(meta.files.fuel),
    fetchText('../data/scenarios/fuel_models.csv'), fetchText(meta.files.trails)]);
  app.meta = meta;
  app.base = parseIni(ini);
  app.texts = { 'elev.asc': elev, 'fuel.asc': fuel, 'fuel_models.csv': models };
  app.graph = parseTrails(trails);
  app.fuel = parseAscInts(fuel);
  app.burnable = burnableCodes(models);
  app.terrains = {};
  app.result = null;
  app.fire = null;
  const season = seasonOf(new Date());
  map.setMountain(meta, await terrainFor(season), app.graph);
  $('mountain').value = id;
  localStorage.setItem('mountain', id);
  if (app.me && app.me.source === 'gps') applyGps(app.me.lat, app.me.lon, app.me.acc);
  else app.me = null;
  refresh();
}

async function terrainFor(season) {
  if (!app.terrains[season]) app.terrains[season] = await loadImage(`assets/${app.meta.id}/terrain_${season}.png`);
  return app.terrains[season];
}

// ------------------------------------------------------------ 내 위치
function startGps() {
  if (!('geolocation' in navigator)) return toast('이 휴대폰은 위치(GPS)를 지원하지 않습니다.');
  if (app.gpsWatch !== null) navigator.geolocation.clearWatch(app.gpsWatch);
  toast('GPS 위치를 찾는 중… (인터넷이 없어도 됩니다)');
  app.gpsWatch = navigator.geolocation.watchPosition(
    (p) => applyGps(p.coords.latitude, p.coords.longitude, p.coords.accuracy),
    (err) => toast(`위치를 받지 못했습니다: ${err.message}`),
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 30000 });
}

function applyGps(lat, lon, acc) {
  const cell = latLonToCell(app.meta, lat, lon);
  if (!insideMap(app.meta, cell)) {
    // 다른 산 지도 안이면 그 산으로 바꿀지 묻는다
    for (const m of app.mountains) {
      if (m.id === app.meta.id) continue;
      if (distanceM(lat, lon, m.center[0], m.center[1]) < 4500 && confirm(`${m.name} 근처에 있습니다. 이 산 지도로 바꿀까요?`)) {
        app.me = { lat, lon, acc, source: 'gps' };
        loadMountain(m.id);
        return;
      }
    }
    const [slat, slon] = app.meta.summit_latlon;
    app.me = null;
    $('info-me').textContent = `📍 GPS ${lat.toFixed(5)}, ${lon.toFixed(5)} — 지도 밖 (${app.meta.peak}에서 ${distanceText(distanceM(lat, lon, slat, slon))}). 시연은 ▶ 데모에서 위치를 찍으세요.`;
    refresh();
    return;
  }
  setMe({ x: cell.x, y: cell.y, acc, source: 'gps', lat, lon });
}

function setMe(me) {
  const moved = !app.me || Math.hypot(app.me.x - me.x, app.me.y - me.y) > 3;
  app.me = me;
  if (moved && app.fire && !app.follow) compute();
  refresh();
}

// ------------------------------------------------------------ 불 정보
function setFire(info) {
  const forest = nearestForest(app.fuel, app.burnable, info.cell.x, info.cell.y, 20);
  if (!forest) return toast('그 근처(600 m 안)에 탈 수 있는 숲이 없습니다. 숲을 찍어 주세요.');
  if (forest.x !== Math.round(info.cell.x) || forest.y !== Math.round(info.cell.y)) {
    toast('찍은 곳이 바위·물·마을이라 가장 가까운 숲을 발화 지점으로 했습니다.');
  }
  info.cell = forest;
  info.receivedAt = Date.now();
  info.noticeMin = Math.max(0, (info.receivedAt - info.time.getTime()) / 60000);
  app.fire = info;
  app.lastLevel = 0;
  compute();
}

async function applyFireLink(text) {
  const info = decodeFire(text);
  if (!info) return toast('발화 정보가 들어 있는 링크가 아닙니다.');
  if (info.mountain !== app.meta.id) {
    if (!app.mountains.some((m) => m.id === info.mountain)) return toast(`모르는 산입니다: ${info.mountain}`);
    await loadMountain(info.mountain);
  }
  const cell = latLonToCell(app.meta, info.lat, info.lon);
  if (!insideMap(app.meta, cell)) return toast('발화 지점이 이 산 지도 밖입니다.');
  setFire({ cell, time: info.time, weather: info.weather, source: '관제 정보' });
}

function manualWeather() {
  if ($('w-normal').checked) return null;
  return { windMs: +$('w-speed').value, windDir: +$('w-dir').value, rhPct: +$('w-rh').value, tempC: +$('w-temp').value };
}

// 예시 산불 (데모): 봄철 건조·강풍 날, 내 위치의 바람 불어오는 쪽(서남서) 숲에서 발화.
//   불이 1~3시간 뒤에 내 주변에 오는 곳을 골라, 경보가 주의 → 대피 준비 → 즉시 대피로 올라가는 것을 보여 준다.
const EXAMPLE_WEATHER = { windMs: 8, windDir: 250, rhPct: 20, tempC: 20 };     // [가정] 봄철 건조·강풍 날
async function exampleFire() {
  const me = app.me || { x: app.meta.summit_cell[0], y: app.meta.summit_cell[1] };
  const th = (EXAMPLE_WEATHER.windDir * Math.PI) / 180;
  const ux = Math.sin(th);
  const uy = -Math.cos(th);
  let best = null;
  $('busy').hidden = false;
  for (const dist of [40, 30, 50, 25, 60]) {
    const cell = nearestForest(app.fuel, app.burnable, me.x + ux * dist, me.y + uy * dist, 8);
    if (!cell) continue;
    const time = new Date();
    const r = await simulate({ cell, time, weather: EXAMPLE_WEATHER, noticeMin: 5 });
    if (!r) continue;
    const danger = dangerTime(r.arrival, app.meta, me.x, me.y, 500);
    const score = Number.isFinite(danger) ? Math.abs(danger - 100) : 1e6;
    if (!best || score < best.score) best = { cell, score };
    if (danger > 50 && danger < 180) break;
  }
  $('busy').hidden = true;
  if (!best) {
    const [x, y] = app.base.ignition.point1.split(',').map(Number);
    best = { cell: { x, y } };
  }
  return { cell: best.cell, time: new Date(Date.now() - 5 * 60000), weather: EXAMPLE_WEATHER, source: '예시: 봄철 건조·강풍' };
}

// ------------------------------------------------------------ 계산 (휴대폰 안의 C 엔진)
/** fire 로 엔진을 한 번 돌려 결과를 정리한다 (실패하면 null) */
async function simulate(fire) {
  const meCell = app.me || { x: app.meta.summit_cell[0], y: app.meta.summit_cell[1] };
  const attached = attachMe(app.graph, meCell.x, meCell.y);
  const graph = attached ? attached.graph : app.graph;
  const startId = attached ? attached.startId : nearestNode(meCell).id;
  const scenario = buildScenario(app.base, { fire, weather: fire.weather, meta: app.meta, noticeMin: fire.noticeMin });
  const files = {
    ...app.texts,
    'scenario.ini': writeIni(scenario),
    'trails.txt': writeTrailFile(graph),
    'hikers.txt': writeHikerFile(startId, +$('set-speed').value || 3.5, +$('set-people').value || 1),
  };
  const r = await runEngine(files, ['--mode', 'evac']);
  if (r.code !== 0) {
    app.lastError = r.error || '엔진 오류';
    return null;
  }
  const evac = JSON.parse(r.outputs['evacuation.json']);
  const summary = JSON.parse(r.outputs['summary.json']);
  const hiker = evac.hikers[0];
  return {
    evac, summary, hiker, graph, offTrail: !attached, meAt: { ...meCell },
    arrival: parseGrid(r.outputs['arrival_time.csv'], app.meta.width, app.meta.height),
    burnout: parseGrid(r.outputs['burnout_time.csv'], app.meta.width, app.meta.height),
    route: hiker.route.found ? routePolyline(graph, hiker.route.nodes) : null,
    ms: r.ms,
  };
}

async function compute() {
  if (!app.fire) return;
  if (app.computing) { app.pending = true; return; }
  app.computing = true;
  $('busy').hidden = false;
  $('busy-text').textContent = '계산 중…';
  const result = await simulate(app.fire);
  app.computing = false;
  $('busy').hidden = true;
  if (!result) {
    toast(`계산 실패: ${app.lastError}`, 6000);
  } else {
    app.result = result;
    if (!app.fire.clockStarted) {          // 시계는 첫 계산이 끝난 뒤부터 흐름 (빠른 배속에서 첫 단계를 건너뛰지 않게)
      app.fire.receivedAt = Date.now();
      app.fire.clockStarted = true;
    }
    const ig = result.summary.ignitions[0];
    app.fire.cell = { x: ig.x, y: ig.y };      // 겨울: 눈 위 발화 지점은 엔진이 눈 아래 숲으로 옮김
    const key = result.summary.season.key;
    map.setTerrain(await terrainFor(key !== 'none' ? key : seasonOf(app.fire.time)));
    const pts = [app.fire.cell, result.meAt];
    if (result.route) pts.push({ x: result.route.at(-1)[0], y: result.route.at(-1)[1] });
    map.frame(pts);
    toast(`휴대폰에서 계산 완료 (${result.ms} ms, 인터넷 사용 안 함)`);
  }
  if (app.pending) { app.pending = false; compute(); }
  refresh();
}

function nearestNode(p) {
  return app.graph.nodes.reduce((a, b) => (Math.hypot(a.x - p.x, a.y - p.y) <= Math.hypot(b.x - p.x, b.y - p.y) ? a : b));
}

// ------------------------------------------------------------ 시각과 화면 갱신
function currentT() {
  if (!app.fire) return null;
  if (!app.fire.clockStarted) return app.fire.noticeMin;
  return app.fire.noticeMin + ((Date.now() - app.fire.receivedAt) / 60000) * app.speed;
}

function refresh() {
  const t = currentT();
  const res = app.result;
  const now = app.fire ? new Date(app.fire.time.getTime() + t * 60000) : new Date();
  $('clock').textContent = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}${app.speed > 1 && app.fire ? ` ×${app.speed}` : ''}`;

  let walkStatus = null;
  if (app.follow && res && res.hiker) {
    const p = sampleAt(res.hiker.samples, t);
    if (p) { app.me = { ...app.me, x: p.x, y: p.y, source: 'demo', acc: 0 }; walkStatus = p.status; }
  }
  map.update({
    arrival: res ? res.arrival : null, burnout: res ? res.burnout : null, t: res ? Math.floor(t) : null,
    route: res ? res.route : null, fire: app.fire ? app.fire.cell : null, me: app.me,
    night: res ? nightLevel(res.summary.daylight, t) : 0,
  });

  if (app.me) {
    const where = app.me.source === 'gps' ? `GPS (오차 ${Math.round(app.me.acc || 0)} m)` : '데모 위치';
    const ll = cellToLatLon(app.meta, app.me.x, app.me.y);
    $('info-me').textContent = `📍 내 위치: ${where} · ${ll.lat.toFixed(4)}, ${ll.lon.toFixed(4)}`;
  } else if (!$('info-me').textContent.includes('지도 밖')) {
    $('info-me').textContent = '📍 내 위치: 아직 모름 (📍 내 위치 또는 ▶ 데모)';
  }

  const box = $('alert');
  if (!app.fire) {
    box.className = 'alert lvl-none';
    $('alert-level').textContent = '산불 정보 없음';
    $('alert-remaining').textContent = '';
    $('alert-advice').textContent = '불 정보를 받으면 휴대폰이 직접 계산해 대피 경로를 알려 줍니다.';
    ['info-route', 'info-weather', 'info-sun'].forEach((id) => ($(id).textContent = ''));
    return;
  }
  if (!res) {
    $('alert-level').textContent = '계산 중…';
    return;
  }
  const me = app.me || res.meAt;
  const { level, remaining } = assessAlert(res.arrival, app.meta, me, t, res.evac.settings, res.hiker.route.found);
  const L = LEVELS[level];
  box.className = `alert lvl-${L.key}`;
  $('alert-level').textContent = `경보: ${L.name}`;
  $('alert-remaining').textContent = Number.isFinite(remaining) ? `불까지 ${minutesText(remaining)}` : '';
  const route = res.hiker.route;
  let advice = L.advice;
  if (route.found && level >= 1 && level <= 3) advice += ` 👉 ${route.exit_name} 방향, 걸어서 약 ${Math.round(route.travel_time_min)}분.`;
  if (res.offTrail) advice += ' (지금 위치가 등산로에서 멀어 가장 가까운 등산로 기준으로 계산했습니다)';
  if (walkStatus === 2) {
    box.className = 'alert lvl-none';
    $('alert-level').textContent = '✓ 대피 완료';
    advice = `${route.exit_name}에 도착했습니다. 산에서 벗어나 불이 오지 않는 곳에 머무르세요.`;
  } else if (walkStatus === 1) {
    advice = `대피 중 👉 ${route.exit_name} 방향. ${advice}`;
  }
  $('alert-advice').textContent = advice;
  $('info-route').textContent = route.found
    ? `🧭 추천 대피: ${route.exit_name}까지 ${Math.round(route.travel_time_min)}분${route.min_margin_min !== null ? ` · 가장 위험한 곳에서도 불보다 ${Math.round(route.min_margin_min)}분 먼저 지나감` : ''}`
    : '🧭 안전한 대피 경로 없음';
  const w = app.fire.weather;
  const season = res.summary.season;
  $('info-weather').textContent = w
    ? `🌬 ${windName(w.windDir)} ${w.windMs} m/s · 습도 ${w.rhPct}% · ${w.tempC}℃ (${app.fire.source})`
    : `🌬 날씨 정보 없음 → ${SEASON_NAMES[season.key] || ''} 평년 날씨로 추정${season.snow_line_m > 0 ? ` · 해발 ${season.snow_line_m} m 위 눈` : ''}`;
  const sunset = (res.summary.daylight.events || []).find((e) => e.type === 'sunset');
  $('info-sun').textContent = `🔥 발화 ${app.fire.time.getHours()}:${String(app.fire.time.getMinutes()).padStart(2, '0')} · 경과 ${Math.floor(t)}분 · 피해 예상 ${res.summary.result.burned_area_ha.toFixed(1)} ha${sunset ? ` · 일몰 ${sunset.clock}` : ''}`;

  if (level > app.lastLevel && level >= 1) notify(L, remaining, route);
  app.lastLevel = level;
}

// ------------------------------------------------------------ 경보 알림 (진동·알림·깜빡임)
async function notify(L, remaining, route) {
  $('alert').classList.remove('flash');
  void $('alert').offsetWidth;
  $('alert').classList.add('flash');
  if (navigator.vibrate) navigator.vibrate(L.key === 'caution' ? [200] : [400, 150, 400, 150, 600]);
  const body = `${Number.isFinite(remaining) ? `불까지 ${minutesText(remaining)}. ` : ''}${route.found ? `${route.exit_name} 방향으로 대피` : '119 구조 요청'}`;
  if ('Notification' in window && Notification.permission === 'granted') {
    try {
      const reg = await navigator.serviceWorker?.getRegistration();
      if (reg) reg.showNotification(`🔥 산불 경보: ${L.name}`, { body, tag: 'wildfire', renotify: true, icon: 'icons/icon-192.png' });
      else new Notification(`🔥 산불 경보: ${L.name}`, { body });
    } catch (e) { /* 알림을 못 띄워도 화면 경보는 그대로 */ }
  }
}

// ------------------------------------------------------------ 지도 터치
function onMapTap(cell) {
  if (app.tapMode === 'me') {
    setTapMode(null);
    app.follow = false;
    $('demo-follow').checked = false;
    const ll = cellToLatLon(app.meta, cell.x, cell.y);
    setMe({ x: cell.x, y: cell.y, acc: 0, source: 'demo', lat: ll.lat, lon: ll.lon });
    toast(attachMe(app.graph, cell.x, cell.y) ? '데모 위치를 정했습니다.' : '등산로에서 500 m 넘게 떨어진 곳입니다. 가장 가까운 등산로 기준으로 계산합니다.');
  } else if (app.tapMode === 'fire') {
    setTapMode(null);
    setFire({ cell, time: new Date(), weather: manualWeather(), source: '직접 입력' });
  }
}

// ------------------------------------------------------------ 버튼
function bindUi() {
  $('mountain').addEventListener('change', (e) => loadMountain(e.target.value));
  $('btn-gps').onclick = () => {
    if (app.me && app.me.source !== 'gps') { app.follow = false; $('demo-follow').checked = false; }
    startGps();
    if (app.me) map.centerOn(app.me.x, app.me.y);
  };
  $('btn-fire').onclick = () => $('dlg-fire').showModal();
  $('btn-demo').onclick = () => $('dlg-demo').showModal();
  $('btn-more').onclick = () => $('dlg-more').showModal();

  $('fire-apply').onclick = async () => { $('dlg-fire').close(); await applyFireLink($('fire-text').value); };
  $('fire-pick').onclick = () => { $('dlg-fire').close(); setTapMode('fire', '🔥 연기가 보이는 곳을 지도에서 누르세요'); };

  $('demo-me').onclick = () => { $('dlg-demo').close(); setTapMode('me', '📍 내 위치(등산로 위)를 지도에서 누르세요'); };
  $('demo-fire').onclick = async () => { $('dlg-demo').close(); setFire(await exampleFire()); };
  $('demo-link').onclick = async () => {
    const f = await exampleFire();
    const ll = cellToLatLon(app.meta, f.cell.x, f.cell.y);
    const link = `${location.origin}${location.pathname}#${encodeFire({ mountain: app.meta.id, lat: ll.lat, lon: ll.lon, time: f.time, weather: f.weather })}`;
    try { await navigator.clipboard.writeText(link); toast('예시 링크를 복사했습니다. 문자·카톡으로 보내 보세요.'); }
    catch (e) { prompt('이 링크를 복사하세요', link); }
  };
  $('demo-speed').onchange = (e) => {
    const t = currentT();
    app.speed = +e.target.value;
    if (app.fire && t !== null) { app.fire.noticeMin = t; app.fire.receivedAt = Date.now(); }
  };
  $('demo-follow').onchange = (e) => { app.follow = e.target.checked; if (!app.follow && app.me) compute(); };

  $('set-notify').onclick = async () => {
    if (!('Notification' in window)) return toast('이 브라우저는 알림을 지원하지 않습니다. 진동과 화면 경보로 알려 드립니다.');
    const p = await Notification.requestPermission();
    toast(p === 'granted' ? '경보 알림을 켰습니다.' : '알림이 꺼져 있습니다. 진동과 화면 경보로 알려 드립니다.');
  };
  $('set-offline').onclick = () => saveOffline();
  $('set-speed').onchange = () => compute();
  $('set-people').onchange = () => compute();

  window.addEventListener('hashchange', () => applyFireLink(location.hash));
  const net = () => { $('net').textContent = navigator.onLine ? '온라인' : '오프라인 ✓'; $('net').classList.toggle('off', !navigator.onLine); };
  window.addEventListener('online', net);
  window.addEventListener('offline', net);
  net();
}

// ------------------------------------------------------------ 오프라인 저장 (서비스 워커)
function mountainFiles(meta) {
  return [`assets/${meta.id}/meta.json`, ...['none', 'spring', 'summer', 'autumn', 'winter'].map((s) => `assets/${meta.id}/terrain_${s}.png`),
          meta.files.scenario, meta.files.elevation, meta.files.fuel, meta.files.trails];
}
async function saveOffline() {
  const reg = await navigator.serviceWorker?.ready;
  if (!reg || !reg.active) return toast('오프라인 저장은 https 주소에서만 됩니다.');
  $('set-status').textContent = '저장 중…';
  const urls = mountainFiles(app.meta).map((u) => new URL(u, location.href).href);
  const channel = new MessageChannel();
  channel.port1.onmessage = (e) => {
    $('set-status').textContent = e.data.ok ? `✓ ${app.meta.name} 저장 완료 (${e.data.count}개 파일). 비행기 모드에서도 열립니다.` : `저장 실패: ${e.data.error}`;
  };
  reg.active.postMessage({ type: 'cache-urls', urls }, [channel.port2]);
}

// ------------------------------------------------------------ 시작
async function main() {
  bindUi();
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
  const list = JSON.parse(await fetchText('assets/mountains.json')).mountains;
  app.mountains = list;
  $('mountain').innerHTML = list.map((m) => `<option value="${m.id}">${m.name}</option>`).join('');
  const linked = decodeFire(location.hash);
  const first = (linked && list.some((m) => m.id === linked.mountain) && linked.mountain) || localStorage.getItem('mountain') || 'bukhansan';
  await loadMountain(list.some((m) => m.id === first) ? first : list[0].id);
  if (linked) await applyFireLink(location.hash);
  setInterval(refresh, 250);      // 1초에 4번: 빠른 배속(×600)에서도 불이 부드럽게 번지게
}

main().catch((e) => toast(`시작 실패: ${e.message}`, 10000));
window.__app = app;     // 자동 화면 테스트용
window.__map = map;
