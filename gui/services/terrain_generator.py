"""
가상 산 지형 생성기

능선과 계곡이 있는 가상의 산을 만들고, 지형에 맞춰 연료(숲 종류)를 배치한 뒤
C 엔진이 읽는 ESRI ASCII Grid(.asc) 파일 두 개로 저장한다.

    - <이름>_elev.asc : 고도 (m)
    - <이름>_fuel.asc : 연료 코드 (fuel_models.csv 참고)

지형 요소는 기본 크기 200 x 200 칸 기준 좌표로 정의하고, 다른 크기로 만들면 비율에 맞춰 늘린다.

실행 예:
    python gui/services/terrain_generator.py
    python gui/services/terrain_generator.py --size 300 --cell 20 --seed 7 --name test_mountain
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------------
# 연료 코드 (C의 wf_config.h, data/scenarios/fuel_models.csv 와 같아야 함)
# ----------------------------------------------------------------------
FUEL_NONE = 0
FUEL_GRASS = 1
FUEL_SHRUB = 2
FUEL_CONIFER = 3
FUEL_BROADLEAF = 4
FUEL_MIXED = 5
FUEL_ROAD = 7
FUEL_WATER = 8
FUEL_ROCK = 9

BASE_SIZE = 200  # 아래 좌표들이 기준으로 삼는 격자 크기

# 봉우리: (x, y, 높이 m, 퍼짐 정도(칸))
PEAKS = [
    (110, 60, 550, 28),   # 주봉
    (60, 90, 380, 22),    # 서봉
    (160, 45, 400, 24),   # 동봉
]

# 능선: 두 점을 잇는 높은 띠 (x1, y1, x2, y2, 높이 m, 폭(칸))
RIDGES = [
    (110, 60, 60, 90, 250, 10),    # 주봉-서봉 능선
    (110, 60, 160, 45, 280, 10),   # 주봉-동봉 능선
    (110, 60, 130, 150, 150, 12),  # 남쪽으로 뻗은 지능선
]

# 계곡(하천): 꺾은선 좌표, 깊이 m, 폭(칸)
STREAM = [(100, 108), (106, 150), (112, 199)]
STREAM_DEPTH = 70
STREAM_WIDTH = 7

# 저수지: (x, y, 반지름(칸))
POND = (125, 186, 5)

# 산 아래 도로 (꺾은선)
ROAD = [(0, 192), (30, 185), (100, 190), (172, 182), (199, 178)]


# ----------------------------------------------------------------------
# 기하 도우미
# ----------------------------------------------------------------------
def distance_to_segment(x: np.ndarray, y: np.ndarray,
                        x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    """모든 격자 점에서 선분 (x1,y1)-(x2,y2)까지의 최단 거리(칸)."""
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return np.hypot(x - x1, y - y1)
    # 선분 위로 수선을 내린 위치 t (0~1로 제한)
    t = np.clip(((x - x1) * dx + (y - y1) * dy) / length_sq, 0.0, 1.0)
    return np.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def distance_to_polyline(x: np.ndarray, y: np.ndarray, points: list[tuple[float, float]]) -> np.ndarray:
    """꺾은선(여러 선분)까지의 최단 거리."""
    result = np.full(x.shape, np.inf)
    for (x1, y1), (x2, y2) in zip(points[:-1], points[1:]):
        result = np.minimum(result, distance_to_segment(x, y, x1, y1, x2, y2))
    return result


def smooth(values: np.ndarray, times: int) -> np.ndarray:
    """주변 3x3 평균을 여러 번 적용해 울퉁불퉁한 잡음을 부드럽게 만든다."""
    for _ in range(times):
        total = np.zeros_like(values)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                total += np.roll(np.roll(values, dy, axis=0), dx, axis=1)
        values = total / 9.0
    return values


def smooth_noise(rng: np.random.Generator, size: int, times: int) -> np.ndarray:
    """-1 ~ 1 범위의 부드러운 잡음."""
    noise = smooth(rng.normal(size=(size, size)), times)
    return noise / (np.abs(noise).max() + 1e-12)


def scale_points(points, s: float):
    return [(px * s, py * s) for px, py in points]


# ----------------------------------------------------------------------
# 고도 만들기
# ----------------------------------------------------------------------
def generate_elevation(size: int, rng: np.random.Generator,
                       low_m: float = 120.0, high_m: float = 950.0) -> np.ndarray:
    """
    봉우리 + 능선 + 계곡 + 잡음을 더해 고도 격자(m)를 만든다. 배열[y, x], y=0이 북쪽.
    마지막에 전체 고도를 low_m ~ high_m 범위로 맞춘다. (기본 950 m: 한국의 흔한 중간 높이 산)
    """
    s = size / BASE_SIZE
    y, x = np.mgrid[0:size, 0:size].astype(float)

    # 1) 북쪽이 조금 더 높은 기본 경사면
    elevation = 150.0 + 200.0 * (1.0 - y / (size - 1))

    # 2) 봉우리 (가우스 종 모양)
    for px, py, height, spread in PEAKS:
        d_sq = (x - px * s) ** 2 + (y - py * s) ** 2
        elevation += height * np.exp(-d_sq / (2.0 * (spread * s) ** 2))

    # 3) 능선 (선분 주변으로 높아지는 띠)
    for x1, y1, x2, y2, height, width in RIDGES:
        d = distance_to_segment(x, y, x1 * s, y1 * s, x2 * s, y2 * s)
        elevation += height * np.exp(-d ** 2 / (2.0 * (width * s) ** 2))

    # 4) 계곡 (하천을 따라 파인 골짜기)
    d_stream = distance_to_polyline(x, y, scale_points(STREAM, s))
    elevation -= STREAM_DEPTH * np.exp(-d_stream ** 2 / (2.0 * (STREAM_WIDTH * s) ** 2))

    # 5) 자연스러운 굴곡 (±25 m)
    elevation += 25.0 * smooth_noise(rng, size, times=int(6 * s) + 2)

    # 6) 높이 범위 맞추기 (가장 낮은 곳 = low_m, 가장 높은 곳 = high_m)
    ratio = (elevation - elevation.min()) / (elevation.max() - elevation.min())
    return low_m + ratio * (high_m - low_m)


# ----------------------------------------------------------------------
# 연료 배치
# ----------------------------------------------------------------------
def slope_and_aspect(elevation: np.ndarray, cell_size: float) -> tuple[np.ndarray, np.ndarray]:
    """경사(도)와 내리막 방위(북=0, 시계방향)."""
    dz_south, dz_east = np.gradient(elevation, cell_size)   # axis0 = 남쪽(y 증가), axis1 = 동쪽
    slope = np.degrees(np.arctan(np.hypot(dz_east, dz_south)))
    aspect = np.degrees(np.arctan2(-dz_east, dz_south)) % 360.0
    return slope, aspect


def generate_fuel(elevation: np.ndarray, cell_size: float, rng: np.random.Generator) -> np.ndarray:
    """
    지형에 맞춰 연료를 배치한다. (실제 산림 분포를 단순화한 규칙 — 가정)
      - 남향 사면과 높은 능선: 침엽수(소나무)  — 건조하고 척박한 곳
      - 북향 사면과 계곡 주변: 활엽수          — 습하고 토양이 깊은 곳
      - 그 사이: 혼효림, 군데군데 관목
      - 정상 부근: 초지와 바위
      - 하천·저수지: 물, 산 아래: 도로와 초지
    """
    size = elevation.shape[0]
    s = size / BASE_SIZE
    y, x = np.mgrid[0:size, 0:size].astype(float)
    _, aspect = slope_and_aspect(elevation, cell_size)
    relative = (elevation - elevation.min()) / (elevation.max() - elevation.min())
    patch = smooth_noise(rng, size, times=int(4 * s) + 2)       # 숲 조각 모양을 만드는 잡음
    d_stream = distance_to_polyline(x, y, scale_points(STREAM, s))

    fuel = np.full((size, size), FUEL_MIXED, dtype=int)

    south_facing = (aspect >= 125) & (aspect <= 235)
    north_facing = (aspect >= 290) | (aspect <= 70)
    fuel[south_facing] = FUEL_CONIFER                            # 남향 사면 소나무
    fuel[north_facing] = FUEL_BROADLEAF                          # 북향 사면 참나무 등
    fuel[(patch < -0.4) & ~north_facing] = FUEL_CONIFER          # 군데군데 소나무 숲
    fuel[relative > 0.65] = FUEL_CONIFER                         # 능선 소나무
    fuel[d_stream < 12 * s] = FUEL_BROADLEAF                     # 계곡 활엽수
    fuel[(patch > 0.45) & (relative > 0.25) & (relative < 0.75)] = FUEL_SHRUB

    # 산 아래 초지(풀밭) 조각
    fuel[(y > 165 * s) & (patch < -0.35)] = FUEL_GRASS

    # 정상 부근
    fuel[relative > 0.88] = FUEL_GRASS
    fuel[(relative > 0.95) & (patch > 0.0)] = FUEL_ROCK
    for px, py, _, _ in PEAKS:
        fuel[np.hypot(x - px * s, y - py * s) <= 2 * s] = FUEL_ROCK

    # 물과 도로 (마지막에 덮어써서 항상 보이게)
    fuel[d_stream < 1.2 * s] = FUEL_WATER
    pond_x, pond_y, pond_r = POND
    fuel[np.hypot(x - pond_x * s, y - pond_y * s) <= pond_r * s] = FUEL_WATER
    fuel[distance_to_polyline(x, y, scale_points(ROAD, s)) < 1.0 * max(s, 1.0)] = FUEL_ROAD
    return fuel


# ----------------------------------------------------------------------
# 파일 저장
# ----------------------------------------------------------------------
def write_asc(path: Path, values: np.ndarray, cell_size: float, value_format: str) -> None:
    """ESRI ASCII Grid 형식으로 저장한다. 첫 데이터 줄이 북쪽 행."""
    rows, cols = values.shape
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"ncols        {cols}\n")
        f.write(f"nrows        {rows}\n")
        f.write("xllcorner    0.0\n")
        f.write("yllcorner    0.0\n")
        f.write(f"cellsize     {cell_size}\n")
        f.write("NODATA_value -9999\n")
        for row in values:
            f.write(" ".join(value_format.format(v) for v in row))
            f.write("\n")


def generate(out_dir: Path, name: str, size: int, cell_size: float, seed: int,
             max_elev: float = 950.0) -> tuple[Path, Path]:
    """지형과 연료를 만들어 저장하고, 저장한 두 파일 경로를 돌려준다."""
    rng = np.random.default_rng(seed)
    elevation = generate_elevation(size, rng, high_m=max_elev)
    fuel = generate_fuel(elevation, cell_size, rng)

    out_dir.mkdir(parents=True, exist_ok=True)
    elev_path = out_dir / f"{name}_elev.asc"
    fuel_path = out_dir / f"{name}_fuel.asc"
    write_asc(elev_path, elevation, cell_size, "{:.1f}")
    write_asc(fuel_path, fuel, cell_size, "{:d}")
    return elev_path, fuel_path


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="가상 산 지형·연료 격자 생성기")
    parser.add_argument("--size", type=int, default=200, help="격자 가로·세로 칸 수 (기본 200)")
    parser.add_argument("--cell", type=float, default=30.0, help="칸 크기 m (기본 30)")
    parser.add_argument("--seed", type=int, default=2026, help="난수 시드 (기본 2026)")
    parser.add_argument("--max-elev", type=float, default=950.0, help="가장 높은 봉우리 고도 m (기본 950)")
    parser.add_argument("--name", default="virtual_mountain", help="파일 이름 앞부분")
    parser.add_argument("--out", type=Path, default=project_root / "data" / "maps", help="저장 폴더")
    args = parser.parse_args()

    if not 20 <= args.size <= 2000:
        parser.error("--size 는 20 ~ 2000 이어야 합니다")
    if not 200 <= args.max_elev <= 3000:
        parser.error("--max-elev 는 200 ~ 3000 이어야 합니다")
    elev_path, fuel_path = generate(args.out, args.name, args.size, args.cell, args.seed, args.max_elev)
    print(f"저장 완료: {elev_path}")
    print(f"저장 완료: {fuel_path}")


if __name__ == "__main__":
    main()
