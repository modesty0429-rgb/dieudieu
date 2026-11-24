// ============================================================
// fuel.js — 연료(숲) 지도에서 "탈 수 있는 곳" 찾기
//   지도에서 찍은 발화 지점이 바위·물·도로·마을이면 엔진이 거절하므로,
//   가장 가까운 숲(주변 3×3칸이 모두 탈 수 있는 곳)으로 옮긴다.
// ============================================================

/** ESRI ASCII Grid 글 → { width, height, data: Int16Array } */
export function parseAscInts(text) {
  const lines = text.split(/\r?\n/);
  const head = {};
  let i = 0;
  for (; i < lines.length; i++) {
    const m = lines[i].trim().match(/^([A-Za-z_]+)\s+(-?[\d.]+)$/);
    if (!m) break;
    head[m[1].toLowerCase()] = +m[2];
  }
  const width = head.ncols;
  const height = head.nrows;
  const data = new Int16Array(width * height);
  let k = 0;
  for (; i < lines.length && k < data.length; i++) {
    for (const v of lines[i].trim().split(/\s+/)) if (v !== '') data[k++] = Math.round(+v);
  }
  return { width, height, data };
}

/** 연료 모델 표(CSV) → 탈 수 있는 연료 코드 집합 */
export function burnableCodes(csv) {
  const set = new Set();
  for (const line of csv.split(/\r?\n/)) {
    const p = line.split(',');
    if (/^\d+$/.test(p[0]) && p[2] === '1') set.add(+p[0]);
  }
  return set;
}

/** (x, y) 에서 가장 가까운 "숲 한가운데" 칸 (주변 3×3 모두 탈 수 있음). 없으면 null */
export function nearestForest(fuel, burnable, x, y, maxR = 60) {
  const ok = (cx, cy) => {
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        const xx = cx + dx;
        const yy = cy + dy;
        if (xx < 0 || yy < 0 || xx >= fuel.width || yy >= fuel.height) return false;
        if (!burnable.has(fuel.data[yy * fuel.width + xx])) return false;
      }
    }
    return true;
  };
  const x0 = Math.round(x);
  const y0 = Math.round(y);
  for (let r = 0; r <= maxR; r++) {
    let best = null;
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
        if (ok(x0 + dx, y0 + dy) && (!best || dx * dx + dy * dy < best.d)) best = { x: x0 + dx, y: y0 + dy, d: dx * dx + dy * dy };
      }
    }
    if (best) return { x: best.x, y: best.y };
  }
  return null;
}
