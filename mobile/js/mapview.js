// ============================================================
// mapview.js — 휴대폰 지도 (canvas)
//   바탕 지도(계절 색 PNG) 위에 불(지금 타는 곳·탄 곳·1시간 안에 올 곳), 등산로, 대피 경로,
//   발화 지점, 내 위치를 그린다. 손가락으로 끌어 이동, 두 손가락으로 확대, 톡 치면 onTap(칸 x, y).
// ============================================================

const COLORS = {
  burned: [40, 30, 28, 230],
  burning: [255, 92, 24, 255],
  soon: [255, 170, 40, 95],           // 앞으로 60분 안에 불이 올 곳
  trail: 'rgba(255,255,255,0.75)',
  route: '#38bdf8',
  me: '#2563eb',
};

export class MapView {
  constructor(canvas, onTap) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.onTap = onTap;
    this.meta = null;
    this.terrain = null;
    this.graph = null;
    this.fireLayer = document.createElement('canvas');
    this.fireT = null;
    this.view = { scale: 1, ox: 0, oy: 0 };
    this.state = {};
    this.pointers = new Map();
    this._bindInput();
    new ResizeObserver(() => this.resize()).observe(canvas);
  }

  // ---------------------------------------------------------- 자료
  setMountain(meta, terrainImage, graph) {
    this.meta = meta;
    this.terrain = terrainImage;
    this.graph = graph;
    this.fireLayer.width = meta.width;
    this.fireLayer.height = meta.height;
    this.fireT = null;
    this.fit();
  }

  setTerrain(image) { this.terrain = image; this.draw(); }

  /** 바라보는 방향만 바뀔 때: 센서가 1초에 수십 번 알려 주므로 화면은 다음 그리기 때 한 번만 다시 그림 */
  setHeading(deg) {
    this.state = { ...this.state, heading: deg };
    if (this._headingFrame) return;
    this._headingFrame = requestAnimationFrame(() => { this._headingFrame = null; this.draw(); });
  }

  /** state: { arrival, burnout (Float32Array), t (발화 후 분), route [[x,y]], fire {x,y}, me {x,y,acc}, night 0~1,
   *           heading (내가 바라보는 방위각 °, 북 0° — 없으면 null) } */
  update(state) {
    this.state = { ...this.state, ...state };
    if ('arrival' in state || 't' in state) this.fireT = null;
    this.draw();
  }

  // ---------------------------------------------------------- 보기 (확대·이동)
  resize() {
    const r = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.max(1, Math.round(r.width * dpr));
    this.canvas.height = Math.max(1, Math.round(r.height * dpr));
    if (!this._fitted) this.fit();
    this.draw();
  }

  fit() {
    if (!this.meta) return;
    const w = this.canvas.width;
    const h = this.canvas.height;
    // 세로로 긴 휴대폰 화면: 지도 높이를 화면에 맞추고(좌우는 밀어서 봄), 너무 크면 가로에 맞춤
    const scale = Math.min(h / this.meta.height, (w / this.meta.width) * 1.6);
    this.view = { scale, ox: (w - this.meta.width * scale) / 2, oy: (h - this.meta.height * scale) / 2 };
    this._fitted = w > 1;
    this.draw();
  }

  /** 여러 칸이 모두 보이게 확대·이동 (내 위치·발화 지점·대피 목적지) */
  frame(points, padCells = 25) {
    if (!points.length) return;
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const x0 = Math.min(...xs) - padCells;
    const x1 = Math.max(...xs) + padCells;
    const y0 = Math.min(...ys) - padCells;
    const y1 = Math.max(...ys) + padCells;
    const W = this.canvas.width;
    const H = this.canvas.height;
    const scale = Math.min(W / (x1 - x0), H / (y1 - y0));
    this.view = { scale, ox: W / 2 - ((x0 + x1) / 2 + 0.5) * scale, oy: H / 2 - ((y0 + y1) / 2 + 0.5) * scale };
    this.draw();
  }

  /** 칸 (x, y) 를 화면 가운데로 (확대는 최소 3배) */
  centerOn(x, y, minScale = 3) {
    const dpr = window.devicePixelRatio || 1;
    const scale = Math.max(this.view.scale, minScale * dpr);
    this.view = { scale, ox: this.canvas.width / 2 - (x + 0.5) * scale, oy: this.canvas.height / 2 - (y + 0.5) * scale };
    this.draw();
  }

  toCell(px, py) {
    const dpr = window.devicePixelRatio || 1;
    return { x: (px * dpr - this.view.ox) / this.view.scale - 0.5, y: (py * dpr - this.view.oy) / this.view.scale - 0.5 };
  }

  _bindInput() {
    const c = this.canvas;
    let moved = 0;
    let pinch = null;
    c.addEventListener('pointerdown', (e) => {
      c.setPointerCapture(e.pointerId);
      this.pointers.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
      moved = 0;
      if (this.pointers.size === 2) {
        const [a, b] = [...this.pointers.values()];
        pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), scale: this.view.scale };
      }
    });
    c.addEventListener('pointermove', (e) => {
      const prev = this.pointers.get(e.pointerId);
      if (!prev) return;
      const dpr = window.devicePixelRatio || 1;
      const cur = { x: e.offsetX, y: e.offsetY };
      this.pointers.set(e.pointerId, cur);
      if (this.pointers.size === 2 && pinch) {
        const [a, b] = [...this.pointers.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        const cx = ((a.x + b.x) / 2) * dpr;
        const cy = ((a.y + b.y) / 2) * dpr;
        this._zoomAt(cx, cy, (pinch.scale * d) / pinch.d / this.view.scale);
        moved += 10;
      } else if (this.pointers.size === 1) {
        this.view.ox += (cur.x - prev.x) * dpr;
        this.view.oy += (cur.y - prev.y) * dpr;
        moved += Math.abs(cur.x - prev.x) + Math.abs(cur.y - prev.y);
        this.draw();
      }
    });
    const end = (e) => {
      const wasSingle = this.pointers.size === 1;
      this.pointers.delete(e.pointerId);
      if (this.pointers.size < 2) pinch = null;
      if (wasSingle && moved < 8 && e.type === 'pointerup') {
        const cell = this.toCell(e.offsetX, e.offsetY);
        if (this.meta && cell.x >= 0 && cell.y >= 0 && cell.x < this.meta.width && cell.y < this.meta.height) this.onTap(cell);
      }
    };
    c.addEventListener('pointerup', end);
    c.addEventListener('pointercancel', end);
    c.addEventListener('wheel', (e) => {
      e.preventDefault();
      const dpr = window.devicePixelRatio || 1;
      this._zoomAt(e.offsetX * dpr, e.offsetY * dpr, e.deltaY < 0 ? 1.2 : 1 / 1.2);
    }, { passive: false });
  }

  _zoomAt(cx, cy, factor) {
    const min = Math.min(this.canvas.width / this.meta.width, this.canvas.height / this.meta.height) * 0.8;
    const scale = Math.min(Math.max(this.view.scale * factor, min), min * 30);
    const f = scale / this.view.scale;
    this.view = { scale, ox: cx - (cx - this.view.ox) * f, oy: cy - (cy - this.view.oy) * f };
    this.draw();
  }

  // ---------------------------------------------------------- 그리기
  _buildFireLayer() {
    const { arrival, burnout, t } = this.state;
    const w = this.meta.width;
    const h = this.meta.height;
    const ctx = this.fireLayer.getContext('2d');
    const img = ctx.createImageData(w, h);
    if (arrival && t !== undefined && t !== null) {
      for (let i = 0; i < w * h; i++) {
        const a = arrival[i];
        if (a < 0) continue;
        let c = null;
        if (a <= t) c = burnout[i] >= 0 && burnout[i] <= t ? COLORS.burned : COLORS.burning;
        else if (a <= t + 60) c = COLORS.soon;
        if (c) img.data.set(c, i * 4);
      }
    }
    ctx.putImageData(img, 0, 0);
    this.fireT = t;
  }

  draw() {
    const ctx = this.ctx;
    const { width: W, height: H } = this.canvas;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#0b1120';
    ctx.fillRect(0, 0, W, H);
    if (!this.meta || !this.terrain) return;
    const { scale, ox, oy } = this.view;
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(scale, 0, 0, scale, ox, oy);
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(this.terrain, 0, 0, this.meta.width, this.meta.height);
    const s = this.state;
    if (s.night > 0) {
      ctx.fillStyle = `rgba(8,12,40,${0.55 * s.night})`;
      ctx.fillRect(0, 0, this.meta.width, this.meta.height);
    }
    if (this.fireT !== s.t) this._buildFireLayer();
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(this.fireLayer, 0, 0);

    const lw = (px) => (px * dpr) / scale;               // 화면 픽셀 → 칸 단위 두께
    const line = (pts) => {
      ctx.beginPath();
      pts.forEach(([x, y], i) => (i ? ctx.lineTo(x + 0.5, y + 0.5) : ctx.moveTo(x + 0.5, y + 0.5)));
      ctx.stroke();
    };
    if (this.graph) {
      ctx.strokeStyle = COLORS.trail;
      ctx.lineWidth = lw(1.3);
      ctx.setLineDash([lw(4), lw(3)]);
      this.graph.edges.forEach((e) => line(e.points));
      ctx.setLineDash([]);
      for (const n of this.graph.nodes) {
        if (n.kind === 'SUMMIT') this._marker(n.x, n.y, '#f8fafc', '▲', lw(13), n.name);
        else if (n.kind === 'PARKING' || n.kind === 'SHELTER') this._dot(n.x, n.y, lw(3.5), '#22c55e', '#052e16');
      }
    }
    if (s.route && s.route.length > 1) {
      ctx.strokeStyle = 'rgba(2,6,23,0.8)';
      ctx.lineWidth = lw(7);
      line(s.route);
      ctx.strokeStyle = COLORS.route;
      ctx.lineWidth = lw(4);
      line(s.route);
      const [ex, ey] = s.route.at(-1);
      this._dot(ex, ey, lw(7), '#22c55e', '#f0fdf4');
    }
    if (s.fire) this._marker(s.fire.x, s.fire.y, '#fde047', '✸', lw(14));
    if (s.me) {
      if (s.me.acc) {
        ctx.fillStyle = 'rgba(37,99,235,0.18)';
        ctx.beginPath();
        ctx.arc(s.me.x + 0.5, s.me.y + 0.5, s.me.acc / this.meta.cell_m, 0, Math.PI * 2);
        ctx.fill();
      }
      if (typeof s.heading === 'number') this._headingCone(s.me.x, s.me.y, s.heading, lw(70), lw(1.5));
      this._dot(s.me.x, s.me.y, lw(8), COLORS.me, '#ffffff', lw(3));
    }
  }

  /** 내 위치에서 바라보는 방향으로 퍼지는 부채꼴 (지도 위쪽 = 북쪽, 방위각은 시계 방향) */
  _headingCone(x, y, heading, length, edge) {
    const ctx = this.ctx;
    const a = ((heading - 90) * Math.PI) / 180;          // 캔버스 각도: 오른쪽 0, 시계 방향
    const half = (28 * Math.PI) / 180;                  // 부채꼴 반각 28°
    const cx = x + 0.5;
    const cy = y + 0.5;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, length);
    grad.addColorStop(0, 'rgba(96,165,250,0.95)');
    grad.addColorStop(0.7, 'rgba(59,130,246,0.55)');
    grad.addColorStop(1, 'rgba(59,130,246,0.1)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, length, a - half, a + half);
    ctx.closePath();
    ctx.fill();
    ctx.lineWidth = edge;                               // 밝은 바탕(가을 단풍 등)에서도 보이도록 테두리
    ctx.strokeStyle = 'rgba(239,246,255,0.9)';
    ctx.stroke();
  }

  _dot(x, y, r, fill, stroke, width) {
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.arc(x + 0.5, y + 0.5, r, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.lineWidth = width || r * 0.35;
    ctx.strokeStyle = stroke;
    ctx.stroke();
  }

  _marker(x, y, color, symbol, size, label) {
    const ctx = this.ctx;
    ctx.font = `${size}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.lineWidth = size * 0.18;
    ctx.strokeStyle = 'rgba(2,6,23,0.85)';
    ctx.strokeText(symbol, x + 0.5, y + 0.5);
    ctx.fillStyle = color;
    ctx.fillText(symbol, x + 0.5, y + 0.5);
    if (label) {
      ctx.font = `600 ${size * 0.75}px sans-serif`;
      ctx.strokeText(label, x + 0.5, y + 0.5 + size);
      ctx.fillStyle = '#f8fafc';
      ctx.fillText(label, x + 0.5, y + 0.5 + size);
    }
  }
}
