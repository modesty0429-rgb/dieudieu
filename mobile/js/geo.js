// ============================================================
// geo.js — 위도·경도 ↔ 지도 칸 좌표
//   GUI(mountain_builder.latlon_to_grid)와 같은 공식: 9 km 지도라 지구를 평면으로 봐도 오차가 1 m 미만
//   칸 좌표: x 는 동쪽(+), y 는 남쪽(+), 칸 중심이 정수
// ============================================================

const RAD = Math.PI / 180;

/** 위경도 → 칸 좌표 (실수) */
export function latLonToCell(meta, lat, lon) {
  const [lat0, lon0] = meta.center;
  const north = (lat - lat0) * RAD * meta.earth_radius_m;
  const east = (lon - lon0) * RAD * meta.earth_radius_m * Math.cos(lat0 * RAD);
  return {
    x: east / meta.cell_m + (meta.width - 1) / 2,
    y: -north / meta.cell_m + (meta.height - 1) / 2,
  };
}

/** 칸 좌표 → 위경도 */
export function cellToLatLon(meta, x, y) {
  const [lat0, lon0] = meta.center;
  const east = (x - (meta.width - 1) / 2) * meta.cell_m;
  const north = -(y - (meta.height - 1) / 2) * meta.cell_m;
  return {
    lat: lat0 + north / meta.earth_radius_m / RAD,
    lon: lon0 + east / (meta.earth_radius_m * Math.cos(lat0 * RAD)) / RAD,
  };
}

export function insideMap(meta, cell) {
  return cell.x >= 0 && cell.y >= 0 && cell.x <= meta.width - 1 && cell.y <= meta.height - 1;
}

/** 두 위경도 사이 거리 (m, 하버사인 공식) */
export function distanceM(lat1, lon1, lat2, lon2) {
  const R = 6371008.8;
  const dLat = (lat2 - lat1) * RAD;
  const dLon = (lon2 - lon1) * RAD;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/** "북한산 (백운대)에서 약 12.3 km" 같은 안내용 문구 */
export function distanceText(m) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
}
