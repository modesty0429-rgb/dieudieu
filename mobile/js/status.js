// ============================================================
// status.js — 지금 시각의 경보 단계·밤 정도·내 위치 (화면 없이 계산만, 테스트 가능)
//   경보 기준은 C 엔진(evac_alert.c)과 같다:
//     내 주변 500 m 안에 불이 오기까지 남은 시간 < 120분 주의, < 60분 대피준비, < 30분 즉시대피,
//     안전한 대피 경로가 없으면 고립(구조 요청)
// ============================================================

export const LEVELS = [
  { key: 'none', name: '정상', advice: '주변 500 m 안으로 불이 올 예정은 없습니다. 상황을 계속 확인하세요.' },
  { key: 'caution', name: '주의', advice: '불이 다가오고 있습니다. 대피 경로를 확인하고 준비하세요.' },
  { key: 'prepare', name: '대피 준비', advice: '지금 대피를 시작하세요.' },
  { key: 'immediate', name: '즉시 대피', advice: '바로 아래 경로로 이동하세요.' },
  { key: 'isolated', name: '고립 위험', advice: '안전한 길이 없습니다. 119 에 구조를 요청하고 바위·물가 등 탈 것이 없는 곳으로 피하세요.' },
];

/** CSV(엔진 출력, 칸마다 분, 안 타면 -1) → Float32Array */
export function parseGrid(csv, width, height) {
  const out = new Float32Array(width * height).fill(-1);
  const rows = csv.trim().split(/\r?\n/);
  for (let y = 0; y < Math.min(rows.length, height); y++) {
    const cells = rows[y].split(',');
    for (let x = 0; x < Math.min(cells.length, width); x++) out[y * width + x] = +cells[x];
  }
  return out;
}

/** 내 위치 주변(반경 m)에 불이 처음 오는 시각 (분). 끝까지 안 오면 Infinity */
export function dangerTime(arrival, meta, x, y, radiusM) {
  const r = radiusM / meta.cell_m;
  const cx = Math.round(x);
  const cy = Math.round(y);
  const ri = Math.ceil(r);
  let best = Infinity;
  for (let dy = -ri; dy <= ri; dy++) {
    const yy = cy + dy;
    if (yy < 0 || yy >= meta.height) continue;
    for (let dx = -ri; dx <= ri; dx++) {
      const xx = cx + dx;
      if (xx < 0 || xx >= meta.width || dx * dx + dy * dy > r * r) continue;
      const a = arrival[yy * meta.width + xx];
      if (a >= 0 && a < best) best = a;
    }
  }
  return best;
}

/**
 * 지금(발화 후 t분) 경보 단계
 *   settings: evacuation.json 의 settings (caution_min, prepare_min, immediate_min, check_radius_m)
 *   routeFound: 안전한 대피 경로가 있는지
 */
export function assessAlert(arrival, meta, me, t, settings, routeFound) {
  const remaining = dangerTime(arrival, meta, me.x, me.y, settings.check_radius_m || 500) - t;
  let level = 0;
  if (remaining < settings.immediate_min) level = 3;
  else if (remaining < settings.prepare_min) level = 2;
  else if (remaining < settings.caution_min) level = 1;
  if (!routeFound && level >= 2) level = 4;
  return { level, remaining };
}

/** 밤 정도 0(낮) ~ 1(밤): 엔진이 계산한 일몰·일출 사건으로 */
export function nightLevel(daylight, t) {
  if (!daylight || !daylight.enabled) return 0;
  const e0 = daylight.start_sun_elevation_deg;
  let level = e0 > -0.833 ? 0 : e0 > -6 ? 0.5 : 1;
  for (const ev of daylight.events || []) {
    if (ev.time_min > t) break;
    if (ev.type === 'sunset' || ev.type === 'dawn') level = 0.5;
    if (ev.type === 'dusk') level = 1;
    if (ev.type === 'sunrise') level = 0;
  }
  return level;
}

/** 엔진이 계산한 내 이동 기록(samples)에서 t분의 위치 (안내대로 걸을 때) */
export function sampleAt(samples, t) {
  if (!samples || !samples.length) return null;
  // samples 한 줄: [시각, x, y, 경보, 남은 시간, 상태(0 산행 1 대피 중 2 대피 완료 3 고립)]
  if (t <= samples[0][0]) return { x: samples[0][1], y: samples[0][2], status: samples[0][5] };
  for (let i = 1; i < samples.length; i++) {
    if (samples[i][0] >= t) {
      const [t0, x0, y0] = samples[i - 1];
      const [t1, x1, y1] = samples[i];
      const f = t1 > t0 ? (t - t0) / (t1 - t0) : 0;
      return { x: x0 + (x1 - x0) * f, y: y0 + (y1 - y0) * f, status: samples[i - 1][5] };
    }
  }
  const last = samples.at(-1);
  return { x: last[1], y: last[2], status: last[5] };
}

/** 계절 키 (C season_from_month 과 같음) */
export function seasonOf(date) {
  return ['winter', 'winter', 'spring', 'spring', 'spring', 'summer', 'summer', 'summer', 'autumn', 'autumn', 'autumn', 'winter'][date.getMonth()];
}
export const SEASON_NAMES = { spring: '봄', summer: '여름', autumn: '가을', winter: '겨울' };

export function minutesText(m) {
  if (!Number.isFinite(m)) return '';
  if (m < 0) return '이미 불이 가까움';
  if (m >= 60) return `약 ${Math.floor(m / 60)}시간 ${Math.round(m % 60)}분`;
  return `약 ${Math.max(0, Math.round(m))}분`;
}
