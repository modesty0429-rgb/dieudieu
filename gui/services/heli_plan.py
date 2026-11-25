"""
헬기 살수 계획표 (관공서용)

C 엔진이 계산한 헬기 살수 기록([시각, x, y])을 현장에서 바로 쓸 수 있는 표로 바꾼다.
    출동 차수 · 헬기 번호 · 시각(실제 시각, 발화 후 몇 분) · 위도·경도 · 이름 있는 지점 기준 위치 · 해발 · 숲 종류 · 목적

엔진이 살수 지점을 고르는 방법 (suppression.c plan_helicopter_drops):
    출동 간격마다 헬기마다 불길 가장자리(화선)에서 "아직 안 탄 숲 쪽으로, 불이 가면 피해가 커지는 곳"을
    가장 높은 점수로 고르고, 헬기끼리는 살수 범위가 겹치지 않게 떨어진 곳을 고른다.
    같은 시각에 기록된 순서가 헬기 번호 순서다.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np

from services.result_loader import MapData, StrategyResult

FUEL_NAMES = {1: "초지", 2: "관목", 3: "침엽수림", 4: "활엽수림", 5: "혼효림", 7: "도로", 8: "물", 9: "바위·시가지"}
DIRS = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]
AUTO_NAME = re.compile(r"(갈림길|들머리|끝지점|지도경계[동서남북]|지도밖연결[동서남북]|최고점\d+m)\d*")


@dataclass
class DropRow:
    order: int            # 전체 순서 (1부터)
    wave: int             # 출동 차수 (같은 시각 = 같은 차수)
    heli: int             # 헬기 번호 (차수 안에서 1부터)
    t_min: float          # 발화 후 분
    clock: str            # 실제 시각 (시작 시각을 알면 "14:10")
    x: int
    y: int
    lat: float | None
    lon: float | None
    elevation_m: float
    fuel: str
    landmark: str         # "백운대에서 남서쪽 1.2 km"
    purpose: str          # "불길이 북동쪽으로 번지는 앞부분 (발화 지점에서 0.9 km)"


def direction_name(dx: float, dy: float) -> str:
    """격자 방향 (dx 오른쪽 +, dy 아래쪽 +) → 8방위 이름. 지도 위쪽이 북쪽"""
    bearing = math.degrees(math.atan2(dx, -dy)) % 360.0
    return DIRS[int(round(bearing / 45.0)) % 8]


def distance_text(cells: float, cell_m: float) -> str:
    meters = cells * cell_m
    return f"{meters / 1000:.1f} km" if meters >= 1000 else f"{meters:.0f} m"


def mountain_grid(map_data: MapData):
    """실제 산이면 위경도 격자 (위도 배열, 경도 배열), 아니면 None"""
    path = map_data.elevation_path
    if path is None or path.parent.parent.name != "mountains":
        return None
    try:
        from services import mountain_builder as mb
        mountain = mb.find_mountain(path.parent.name)
        return mb.grid_cell_latlon(mb.grid_spec(mountain))
    except (KeyError, OSError, ValueError):
        return None


def landmarks(map_data: MapData) -> list[tuple[str, int, int]]:
    """위치 설명에 쓸 이름 있는 지점: 정상과 자료에 이름이 있는 등산로 지점 (자동 이름 '갈림길12' 등은 제외)"""
    marks = [(n.name, n.x, n.y) for n in map_data.nodes if n.kind == "SUMMIT"]
    marks += [(n.name, n.x, n.y) for n in map_data.nodes
              if n.kind != "SUMMIT" and not AUTO_NAME.fullmatch(n.name)]
    return marks


def landmark_text(x: int, y: int, marks: list[tuple[str, int, int]], cell_m: float) -> str:
    """가장 가까운 이름 있는 지점 기준 위치. 지점이 없으면 빈 글자"""
    if not marks:
        return ""
    name, mx, my = min(marks, key=lambda m: (m[1] - x) ** 2 + (m[2] - y) ** 2)
    dist = math.hypot(x - mx, y - my)
    if dist < 1.5:
        return f"{name} 바로 옆"
    return f"{name}에서 {direction_name(x - mx, y - my)}쪽 {distance_text(dist, cell_m)}"


def build_drop_plan(map_data: MapData, strategy: StrategyResult | None) -> list[DropRow]:
    """한 전략의 헬기 살수 기록 → 계획표 행 목록 (시각 순서)"""
    if strategy is None or strategy.drops is None or len(strategy.drops) == 0:
        return []
    grid = mountain_grid(map_data)
    marks = landmarks(map_data)
    cell_m = map_data.cell_size
    ix, iy = (map_data.ignitions[0][0], map_data.ignitions[0][1]) if map_data.ignitions else (None, None)
    rows: list[DropRow] = []
    wave, heli, last_t = 0, 0, None
    drops = np.asarray(strategy.drops, dtype=float).reshape(-1, 3)
    for k, (t, xf, yf) in enumerate(drops):
        x, y = int(xf), int(yf)
        if last_t is None or abs(t - last_t) > 0.01:
            wave, heli, last_t = wave + 1, 0, t
        heli += 1
        clock = (map_data.start_time + timedelta(minutes=float(t))).strftime("%H:%M") if map_data.start_time else ""
        lat = lon = None
        if grid is not None:
            lat, lon = float(grid[0][y, x]), float(grid[1][y, x])
        if ix is not None and (x, y) != (ix, iy):
            purpose = (f"불길이 {direction_name(x - ix, y - iy)}쪽으로 번지는 앞부분 "
                       f"(발화 지점에서 {distance_text(math.hypot(x - ix, y - iy), cell_m)})")
        else:
            purpose = "발화 지점 바로 주변"
        rows.append(DropRow(k + 1, wave, heli, float(t), clock, x, y, lat, lon,
                            float(map_data.elevation[y, x]), FUEL_NAMES.get(int(map_data.fuel[y, x]), "-"),
                            landmark_text(x, y, marks, cell_m), purpose))
    return rows


def summary_text(rows: list[DropRow], settings: dict) -> str:
    """계획표 위에 붙일 한 줄 설명"""
    if not rows:
        return "헬기 살수 기록이 없습니다."
    side = (2 * int(settings.get("heli_radius_cells", 2)) + 1) * 30
    return (f"헬기 {settings.get('helicopters', '?')}대가 {settings.get('heli_interval_min', 30):.0f}분 간격으로 "
            f"{rows[-1].wave}차례 출동, 모두 {len(rows)}회 살수. 한 번에 약 {side} m × {side} m 를 적시고 "
            f"{settings.get('heli_effect_min', 45):.0f}분 동안 그곳으로 불이 번지지 않게 함. "
            f"위치는 불길 가장자리 중 불이 가면 피해가 커지는 곳을 헬기마다 겹치지 않게 고른 것.")


def save_csv(rows: list[DropRow], path: Path) -> Path:
    """엑셀에서 바로 열리도록 UTF-8(BOM) CSV 로 저장"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["순서", "출동 차수", "헬기", "시각", "발화 후(분)", "위도", "경도", "위치", "해발(m)", "숲", "목적",
                    "격자 x", "격자 y"])
        for r in rows:
            w.writerow([r.order, r.wave, f"{r.heli}호기", r.clock, f"{r.t_min:.0f}",
                        f"{r.lat:.5f}" if r.lat is not None else "", f"{r.lon:.5f}" if r.lon is not None else "",
                        r.landmark, f"{r.elevation_m:.0f}", r.fuel, r.purpose, r.x, r.y])
    return path
