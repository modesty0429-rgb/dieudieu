// ============================================================
// ini.js — 시나리오(.ini) 읽기·쓰기
//   산마다 있는 data/scenarios/mountain_<산>.ini 를 읽어, 휴대폰에서 정한 값(발화 지점·시각·날씨·
//   내 위치 등산로 파일)으로 바꾼 시나리오를 만든다. C 엔진(scenario_io.c)이 읽는 형식 그대로.
// ============================================================

/** .ini 글 → { 구역: { 키: 값 } } (값 뒤의 # 주석은 뺌) */
export function parseIni(text) {
  const out = {};
  let section = '';
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\s+#.*$/, '').trim();
    if (!line || line.startsWith('#') || line.startsWith(';')) continue;
    const head = line.match(/^\[(.+)\]$/);
    if (head) {
      section = head[1].trim().toLowerCase();
      out[section] = out[section] || {};
      continue;
    }
    const eq = line.indexOf('=');
    if (eq < 0 || !section) continue;
    out[section][line.slice(0, eq).trim().toLowerCase()] = line.slice(eq + 1).trim();
  }
  return out;
}

/** { 구역: { 키: 값 } } → .ini 글 */
export function writeIni(sections) {
  const lines = ['# 휴대폰 앱이 만든 시나리오 (mobile/js/ini.js)'];
  for (const [name, values] of Object.entries(sections)) {
    lines.push('', `[${name}]`);
    for (const [key, value] of Object.entries(values)) lines.push(`${key} = ${value}`);
  }
  return lines.join('\n') + '\n';
}

const pad = (n) => String(n).padStart(2, '0');

/** Date → "2026-11-24 14:30" (휴대폰 현지 시각) */
export function iniDateTime(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * 휴대폰용 시나리오 만들기
 *   base     : 산 시나리오를 parseIni 한 것 (연료 수분·확산·경보 기준 등은 그대로 씀)
 *   fire     : { cell:{x,y}, time: Date }
 *   weather  : { windMs, windDir, rhPct, tempC } 또는 null (→ 계절 평년 날씨)
 *   meta     : 산 meta.json (위치 → 일출·일몰)
 *   noticeMin: 불이 난 뒤 몇 분 만에 정보를 받았는지 (경보를 낼 수 있는 가장 이른 시각)
 */
export function buildScenario(base, { fire, weather, meta, noticeMin, durationMin = 360 }) {
  const s = JSON.parse(JSON.stringify(base));
  s.general = { name: 'mobile', output_dir: 'out' };
  s.map = { elevation_file: 'elev.asc', fuel_file: 'fuel.asc', fuel_models: 'fuel_models.csv' };
  s.trails = { trail_file: 'trails.txt', hiker_file: 'hikers.txt' };
  s.time = { ...(s.time || {}), start_datetime: iniDateTime(fire.time), duration_min: durationMin,
             time_step_min: 1, output_interval_min: 10 };
  s.ignition = { point1: `${Math.round(fire.cell.x)}, ${Math.round(fire.cell.y)}, 0` };
  if (weather) {
    s.weather = { mode: 'fixed', fixed_temp_c: weather.tempC, fixed_rh_pct: weather.rhPct,
                  fixed_wind_speed_ms: weather.windMs, fixed_wind_dir_deg: weather.windDir };
  } else {
    s.weather = { mode: 'season' };       // 날씨를 못 받으면 그 계절 평년 날씨 (season.c 가 하루 날씨를 만듦)
  }
  s.season = { ...(s.season || {}), season: 'auto' };   // 날짜로 계절 자동 (겨울이면 산마다 다른 눈 경계)
  const [lat, lon] = meta.summit_latlon;
  s.daylight = { enabled: 1, latitude_deg: lat.toFixed(4), longitude_deg: lon.toFixed(4), utc_offset_h: 9 };
  s.evacuation = { ...(s.evacuation || {}), notify_delay_min: Math.max(0, Math.round(noticeMin)) };
  delete s.montecarlo;
  delete s.suppression;
  return s;
}
