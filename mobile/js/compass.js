// ============================================================
// compass.js — 휴대폰이 바라보는 방향(나침반)을 실시간으로 읽고, 대피로까지 몇 도 돌아야 하는지 계산한다.
//   방향 센서는 인터넷이 없어도 동작한다. 지도는 위쪽이 북쪽이므로 방위각(북 0°, 동 90°)을 그대로 쓴다.
//   - 아이폰(iOS 13 이상): 'deviceorientation' 의 webkitCompassHeading (처음에 사용자 허락 필요)
//   - 안드로이드(크롬): 'deviceorientationabsolute' 의 alpha (북쪽 기준) → 방위각 = 360 − alpha
//   화면을 가로로 돌리면 화면 각도(screen.orientation.angle)만큼 더한다.
// ============================================================

/** 각도를 0 이상 360 미만으로 */
export function normalizeDeg(deg) {
  return ((deg % 360) + 360) % 360;
}

/** a → b 로 돌아야 하는 각도 (−180 초과 ~ 180 이하, + 는 오른쪽) */
export function turnDeg(fromDeg, toDeg) {
  const d = normalizeDeg(toDeg - fromDeg);
  return d > 180 ? d - 360 : d;
}

/** 칸 (x1, y1) 에서 (x2, y2) 를 보는 방위각. 지도 위쪽(y 감소)이 북쪽 0°, 오른쪽이 동쪽 90° */
export function bearingDeg(x1, y1, x2, y2) {
  return normalizeDeg((Math.atan2(x2 - x1, -(y2 - y1)) * 180) / Math.PI);
}

const DIRS = ['북', '북동', '동', '남동', '남', '남서', '서', '북서'];
/** 방위각 → '북동' 같은 8방위 이름 */
export function directionName(deg) {
  return DIRS[Math.round(normalizeDeg(deg) / 45) % 8];
}

/**
 * 대피로에서 지금 향해야 할 점: 내 위치에서 가장 가까운 경로 점보다 앞쪽으로 aheadCells 칸 이상 떨어진 첫 점.
 * (바로 옆 점을 보면 방향이 흔들리므로 조금 앞을 본다) 경로가 없거나 이미 끝이면 null
 */
export function routeTarget(route, me, aheadCells = 4) {
  if (!route || route.length < 2 || !me) return null;
  let nearest = 0;
  let best = Infinity;
  route.forEach(([x, y], i) => {
    const d = (x - me.x) ** 2 + (y - me.y) ** 2;
    if (d < best) { best = d; nearest = i; }
  });
  for (let i = nearest; i < route.length; i++) {
    const [x, y] = route[i];
    if (Math.hypot(x - me.x, y - me.y) >= aheadCells) return { x, y };
  }
  const [ex, ey] = route.at(-1);
  return Math.hypot(ex - me.x, ey - me.y) >= 1 ? { x: ex, y: ey } : null;
}

/** 대피로까지 돌아야 할 각도를 안내 문장으로. 예: '오른쪽으로 40° (북동쪽)' */
export function turnText(turn, bearing) {
  const a = Math.round(Math.abs(turn));
  const where = `${directionName(bearing)}쪽`;
  if (a <= 15) return `앞으로 계속 (${where})`;
  if (a >= 165) return `뒤로 돌기 (${where})`;
  return `${turn > 0 ? '오른쪽' : '왼쪽'}으로 ${a}° (${where})`;
}

/** 센서 값 → 방위각 (없으면 null) */
export function headingFromEvent(e, screenAngle = 0) {
  let h = null;
  if (typeof e.webkitCompassHeading === 'number' && !Number.isNaN(e.webkitCompassHeading)) {
    h = e.webkitCompassHeading;                       // 아이폰: 이미 북쪽 기준 시계 방향
  } else if (e.absolute && typeof e.alpha === 'number') {
    h = 360 - e.alpha;                                // 안드로이드: alpha 는 반시계 방향
  }
  return h === null ? null : normalizeDeg(h + screenAngle);
}

/**
 * 나침반 시작. onHeading(방위각) 을 실시간으로 부른다 (흔들림은 부드럽게 줄임).
 * 아이폰·최신 크롬은 센서 허락을 물어보므로 버튼을 누를 때(사용자 동작 안에서) 불러야 한다.
 * 허락 결과와 관계없이 센서를 듣기 시작하고, 실제로 값이 오는지는 부른 쪽이 잠시 뒤 확인한다.
 * 방향 센서 기능 자체가 없는 브라우저면 false
 */
export async function startCompass(onHeading) {
  if (typeof window === 'undefined' || !('DeviceOrientationEvent' in window)) return false;
  const DOE = window.DeviceOrientationEvent;
  if (typeof DOE.requestPermission === 'function') {
    try { await DOE.requestPermission(); } catch { /* 거절·미지원: 값이 오지 않으면 부른 쪽이 안내 */ }
  }
  let sx = 0;
  let sy = 0;
  const handler = (e) => {
    const angle = (screen.orientation && screen.orientation.angle) || window.orientation || 0;
    const h = headingFromEvent(e, angle);
    if (h === null) return;
    // 각도는 359° 와 1° 가 가까우므로 단위 벡터로 평균 (지수 이동 평균)
    const r = (h * Math.PI) / 180;
    sx = sx * 0.7 + Math.sin(r) * 0.3;
    sy = sy * 0.7 + Math.cos(r) * 0.3;
    onHeading(normalizeDeg((Math.atan2(sx, sy) * 180) / Math.PI));
  };
  if ('ondeviceorientationabsolute' in window) window.addEventListener('deviceorientationabsolute', handler);
  else window.addEventListener('deviceorientation', handler);
  return true;
}
