// ============================================================
// trails.js — 등산로 그래프 읽기, 내 위치를 등산로에 붙이기, 엔진용 파일 쓰기
//   GUI 의 hiker_setup.py 와 같은 방법:
//     내 위치에서 가장 가까운 등산로 위 점을 찾고(선분에 수직으로 내린 점),
//     그 자리에서 등산로를 둘로 나눠 "내 위치" 지점(POINT)을 만든다.
//     C 엔진은 지점에서 출발하는 등산객만 알기 때문이다.
// ============================================================

export const ME_NODE_ID = 9000;          // 내 위치로 만든 지점 번호
const SNAP_NODE_CELLS = 2;               // 지점에서 2칸(60 m) 안이면 그 지점으로
export const MAX_SNAP_CELLS = 17;        // 등산로에서 500 m 넘게 떨어지면 등산로 밖으로 봄

/** trails.txt → { nodes: [{id, kind, x, y, name}], edges: [{a, b, points:[[x,y]...]}] } */
export function parseTrails(text) {
  const nodes = [];
  const edges = [];
  const byId = new Map();
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const p = line.split(/\s+/);
    if (p[0] === 'NODE') {
      const node = { id: +p[1], kind: p[2], x: +p[3], y: +p[4], name: p.slice(5).join(' ') };
      nodes.push(node);
      byId.set(node.id, node);
    }
  }
  for (const raw of text.split(/\r?\n/)) {
    const p = raw.trim().split(/\s+/);
    if (p[0] !== 'EDGE') continue;
    const a = byId.get(+p[1]);
    const b = byId.get(+p[2]);
    if (!a || !b) continue;
    const n = +p[3];
    const points = [[a.x, a.y]];
    for (let i = 0; i < n; i++) points.push([+p[4 + 2 * i], +p[5 + 2 * i]]);
    points.push([b.x, b.y]);
    edges.push({ a: a.id, b: b.id, points });
  }
  return { nodes, edges };
}

function project(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
  const qx = ax + t * dx;
  const qy = ay + t * dy;
  return { qx, qy, d: Math.hypot(px - qx, py - qy) };
}

/** (x, y) 에서 가장 가까운 등산로 위 점. 너무 멀면 null */
export function snapToTrail(graph, x, y) {
  let best = null;
  for (const n of graph.nodes) {
    const d = Math.hypot(n.x - x, n.y - y);
    if (d <= SNAP_NODE_CELLS && (!best || d < best.distance)) best = { x: n.x, y: n.y, distance: d, nodeId: n.id };
  }
  if (best) return best;
  graph.edges.forEach((e, ei) => {
    for (let si = 0; si < e.points.length - 1; si++) {
      const [ax, ay] = e.points[si];
      const [bx, by] = e.points[si + 1];
      const { qx, qy, d } = project(x, y, ax, ay, bx, by);
      if (!best || d < best.distance) best = { x: Math.round(qx), y: Math.round(qy), distance: d, nodeId: null, edge: ei, segment: si };
    }
  });
  if (!best || best.distance > MAX_SNAP_CELLS) return null;
  for (const n of graph.nodes) {
    if (Math.hypot(n.x - best.x, n.y - best.y) <= SNAP_NODE_CELLS) return { x: n.x, y: n.y, distance: best.distance, nodeId: n.id };
  }
  return best;
}

function dedupe(points) {
  return points.filter((p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1]);
}

/** 내 위치를 등산로에 붙인 그래프와 출발 지점 번호. 등산로에서 너무 멀면 null */
export function attachMe(graph, x, y) {
  const snap = snapToTrail(graph, x, y);
  if (!snap) return null;
  if (snap.nodeId !== null) return { graph, startId: snap.nodeId, snap };
  const e = graph.edges[snap.edge];
  const point = [snap.x, snap.y];
  let before = e.points.slice(0, snap.segment + 1);
  let after = e.points.slice(snap.segment + 1);
  if (before.length > 1 && Math.hypot(before.at(-1)[0] - snap.x, before.at(-1)[1] - snap.y) <= 1.5) before = before.slice(0, -1);
  if (after.length > 1 && Math.hypot(after[0][0] - snap.x, after[0][1] - snap.y) <= 1.5) after = after.slice(1);
  const me = { id: ME_NODE_ID, kind: 'POINT', x: snap.x, y: snap.y, name: '내_위치' };
  const edges = graph.edges.slice();
  edges.splice(snap.edge, 1,
    { a: e.a, b: ME_NODE_ID, points: dedupe([...before, point]) },
    { a: ME_NODE_ID, b: e.b, points: dedupe([point, ...after]) });
  return { graph: { nodes: [...graph.nodes, me], edges }, startId: ME_NODE_ID, snap };
}

/** 그래프 → trails.txt (C 엔진 trail_io.c 형식) */
export function writeTrailFile(graph) {
  const lines = ['# 휴대폰 앱이 내 위치에 맞춰 만든 등산로', '# NODE 번호 종류 x y 이름'];
  for (const n of graph.nodes) lines.push(`NODE ${n.id} ${n.kind} ${n.x} ${n.y} ${n.name}`);
  lines.push('', '# EDGE 시작번호 끝번호 경유점개수 [x1 y1 ...]');
  for (const e of graph.edges) {
    const mid = e.points.slice(1, -1);
    lines.push(`EDGE ${e.a} ${e.b} ${mid.length} ${mid.map(([x, y]) => `${x} ${y}`).join(' ')}`.trim());
  }
  return lines.join('\n') + '\n';
}

/** 등산객 파일: 나(우리 일행) 한 팀 */
export function writeHikerFile(startId, speedKmh, people) {
  return `# 휴대폰 사용자\n# HIKER 번호 이름 노드번호 평지보행속도(km/h) 인원\nHIKER 1 나 ${startId} ${speedKmh.toFixed(1)} ${people}\n`;
}

/** 그림용: 지점 번호 → 지점 */
export function nodeMap(graph) {
  return new Map(graph.nodes.map((n) => [n.id, n]));
}

/** 경로(지점 번호 목록)를 지나는 칸 좌표 목록으로 (그래프 간선의 모양을 따라감) */
export function routePolyline(graph, nodeIds) {
  const out = [];
  for (let i = 0; i < nodeIds.length - 1; i++) {
    const a = nodeIds[i];
    const b = nodeIds[i + 1];
    const e = graph.edges.find((g) => (g.a === a && g.b === b) || (g.a === b && g.b === a));
    if (!e) continue;
    const pts = e.a === a ? e.points : e.points.slice().reverse();
    out.push(...(out.length ? pts.slice(1) : pts));
  }
  return out;
}
