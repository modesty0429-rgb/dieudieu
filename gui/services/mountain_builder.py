"""
실제 산 데이터 만들기

data/mountains/mountains.json 에 적힌 산(북한산, 설악산, 충남 오대산, 지리산, 전북 팔공산, 한라산)마다
정상(또는 등산로 자료)을 가운데로 하는 300×300칸(30 m) = 9 km × 9 km 지도를 만들어 C 엔진이 읽는 파일로 저장한다.

    data/mountains/<id>/elev.asc        실제 지형 (공개 지형 타일에서 내려받아 다시 샘플링)
    data/mountains/<id>/fuel.asc        연료(숲 종류): 산림청 임상도를 반영했으면 실제 값, 아니면 [임시] 사면 규칙
    data/mountains/<id>/trails.txt      산림청 등산로를 반영했을 때만 (forest_import.py)
    data/mountains/<id>/hikers.txt      등산로가 있을 때만
    data/mountains/<id>/info.json       출처, 반영 상태(임상도·등산로), 위치
    data/scenarios/mountain_<id>.ini    이 산의 시나리오

지형 출처: AWS Open Data "Terrain Tiles" (Mapzen/Tilezen, terrarium 형식).
           한국 지역은 주로 SRTM 30 m 를 바탕으로 한다. 확대 수준 13 (픽셀 약 15 m) 을 내려받아
           30 m 격자 셀 중심 위치의 고도를 양선형 보간으로 구한다.

실행 예 (저장소 폴더에서, 인터넷 필요):
    python gui/services/mountain_builder.py --all
    python gui/services/mountain_builder.py --id seoraksan
임상도·등산로 반영은 forest_import.py 참고.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # gui 폴더 (직접 실행할 때)

from services import app_config  # noqa: E402
from services.terrain_generator import write_asc  # noqa: E402

MOUNTAIN_DIR = app_config.DATA_DIR / "mountains"
REGISTRY_FILE = MOUNTAIN_DIR / "mountains.json"
CACHE_DIR = MOUNTAIN_DIR / "_cache"                 # 내려받은 타일 (git 제외)
TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
TILE_ZOOM = 13
TILE_SIZE = 256
EARTH_RADIUS_M = 6371008.8
GRID_SIZE = 300
CELL_SIZE_M = 30.0
DEM_SOURCE = "AWS Terrain Tiles (Mapzen/Tilezen terrarium, 한국은 주로 SRTM 30 m 기반), 확대 수준 13"

# 연료 코드 (fuel_models.csv 와 같음)
FUEL_GRASS, FUEL_SHRUB, FUEL_CONIFER, FUEL_BROADLEAF, FUEL_MIXED, FUEL_WATER, FUEL_ROCK = 1, 2, 3, 4, 5, 8, 9


# ----------------------------------------------------------------------
# 산 목록
# ----------------------------------------------------------------------
def load_registry() -> list[dict]:
    """mountains.json 의 산 목록"""
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["mountains"]


def find_mountain(mountain_id: str) -> dict:
    for m in load_registry():
        if m["id"] == mountain_id:
            return m
    raise KeyError(f"mountains.json 에 없는 산: {mountain_id}")


class GridSpec(tuple):
    """
    지도 격자 정보: (가운데 위도, 가운데 경도) 튜플이면서 가로·세로 칸 수(width, height)를 함께 가진다.
    대부분 300×300칸이지만, 산 모양에 맞춰 크기를 줄인 산(예: 북한산)도 있다. (mountains.json 의 "size")
    """
    def __new__(cls, lat: float, lon: float, width: int = GRID_SIZE, height: int = GRID_SIZE):
        spec = super().__new__(cls, (lat, lon))
        spec.width, spec.height = int(width), int(height)
        return spec


def grid_spec(mountain: dict) -> GridSpec:
    """산의 지도 격자 (가운데 위치 + 크기)"""
    width, height = mountain.get("size") or (GRID_SIZE, GRID_SIZE)
    return GridSpec(mountain["center"][0], mountain["center"][1], width, height)


def grid_shape(center, size=None) -> tuple[int, int]:
    """(가로, 세로) 칸 수. size 를 주면 그것(정수면 정사각형), 아니면 center 가 GridSpec 이면 그 크기"""
    if size is not None:
        return (size, size) if isinstance(size, int) else (int(size[0]), int(size[1]))
    if isinstance(center, GridSpec):
        return center.width, center.height
    return GRID_SIZE, GRID_SIZE


def summit_grid(mountain: dict) -> tuple[int, int]:
    """정상의 격자 좌표. 보통 지도 가운데지만, 등산로 자료에 맞춰 지도를 옮긴 산은 'summit' 위치"""
    lat, lon = mountain.get("summit") or mountain["center"]
    x, y = latlon_to_grid(np.array([lat]), np.array([lon]), grid_spec(mountain))
    return int(round(float(x[0]))), int(round(float(y[0])))


def mountain_folder(mountain_id: str) -> Path:
    return MOUNTAIN_DIR / mountain_id


# ----------------------------------------------------------------------
# 격자 ↔ 위경도
# ----------------------------------------------------------------------
def grid_cell_latlon(center, size=None, cell: float = CELL_SIZE_M) -> tuple[np.ndarray, np.ndarray]:
    """
    격자 각 셀 중심의 (위도, 경도) 배열 [y, x]. y = 0 이 북쪽.
    9 km 정도의 좁은 지역이므로 지도 가운데를 기준으로 한 등장방형(위경도를 m 로 바꾸는 간단한) 근사를 쓴다.
    (9 km 범위에서 거리 오차는 0.1% 미만)
    """
    lat0, lon0 = center[0], center[1]
    width, height = grid_shape(center, size)
    east = (np.arange(width) - (width - 1) / 2.0) * cell            # 가운데 기준 거리 (m)
    north = -(np.arange(height) - (height - 1) / 2.0) * cell       # y 가 커질수록 남쪽
    lat = lat0 + np.degrees(north[:, None] / EARTH_RADIUS_M) * np.ones((1, width))
    lon = lon0 + np.degrees(east[None, :] / (EARTH_RADIUS_M * math.cos(math.radians(lat0)))) * np.ones((height, 1))
    return lat, lon


def latlon_to_grid(lat: np.ndarray, lon: np.ndarray, center, size=None,
                   cell: float = CELL_SIZE_M) -> tuple[np.ndarray, np.ndarray]:
    """위경도 → 격자 좌표 (실수, 셀 중심 = 정수). grid_cell_latlon 의 반대"""
    lat0, lon0 = center[0], center[1]
    width, height = grid_shape(center, size)
    north = np.radians(np.asarray(lat) - lat0) * EARTH_RADIUS_M
    east = np.radians(np.asarray(lon) - lon0) * EARTH_RADIUS_M * math.cos(math.radians(lat0))
    x = east / cell + (width - 1) / 2.0
    y = -north / cell + (height - 1) / 2.0
    return x, y


# ----------------------------------------------------------------------
# 지형 타일
# ----------------------------------------------------------------------
def tile_coordinates(lat: np.ndarray, lon: np.ndarray, zoom: int) -> tuple[np.ndarray, np.ndarray]:
    """위경도 → 웹 메르카토르 타일 좌표 (실수, 정수 부분 = 타일 번호, 소수 부분 × 256 = 픽셀)"""
    n = 2.0 ** zoom
    x = (np.asarray(lon) + 180.0) / 360.0 * n
    lat_rad = np.radians(lat)
    y = (1.0 - np.arcsinh(np.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def load_tile(zoom: int, tx: int, ty: int) -> np.ndarray:
    """terrarium 타일 하나를 고도 배열(m)로. 내려받은 타일은 _cache 에 저장해 다시 쓰지 않는다."""
    from PIL import Image
    import requests

    cache = CACHE_DIR / f"{zoom}_{tx}_{ty}.png"
    if cache.exists():
        data = cache.read_bytes()
    else:
        response = requests.get(TILE_URL.format(z=zoom, x=tx, y=ty), timeout=30)
        response.raise_for_status()
        data = response.content
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB")).astype(np.float64)
    # terrarium 형식: 고도 = (R × 256 + G + B / 256) − 32768
    return rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0


def fetch_dem(center, size=None, cell: float = CELL_SIZE_M,
              zoom: int = TILE_ZOOM) -> np.ndarray:
    """정상을 가운데로 하는 격자의 고도(m) [y, x] — 필요한 타일을 이어 붙여 양선형 보간"""
    lat, lon = grid_cell_latlon(center, size, cell)
    tx, ty = tile_coordinates(lat, lon, zoom)
    x0, x1 = int(np.floor(tx.min())), int(np.floor(tx.max()))
    y0, y1 = int(np.floor(ty.min())), int(np.floor(ty.max()))

    # 타일 모자이크 (경계 보간을 위해 한 타일씩 여유)
    mosaic = np.zeros(((y1 - y0 + 1) * TILE_SIZE, (x1 - x0 + 1) * TILE_SIZE))
    for j, tile_y in enumerate(range(y0, y1 + 1)):
        for i, tile_x in enumerate(range(x0, x1 + 1)):
            mosaic[j * TILE_SIZE:(j + 1) * TILE_SIZE, i * TILE_SIZE:(i + 1) * TILE_SIZE] = load_tile(zoom, tile_x, tile_y)

    # 셀 중심의 모자이크 픽셀 좌표 (픽셀 중심이 +0.5 이므로 0.5 를 뺀다)
    px = (tx - x0) * TILE_SIZE - 0.5
    py = (ty - y0) * TILE_SIZE - 0.5
    px0 = np.clip(np.floor(px).astype(int), 0, mosaic.shape[1] - 2)
    py0 = np.clip(np.floor(py).astype(int), 0, mosaic.shape[0] - 2)
    fx = np.clip(px - px0, 0.0, 1.0)
    fy = np.clip(py - py0, 0.0, 1.0)
    top = mosaic[py0, px0] * (1 - fx) + mosaic[py0, px0 + 1] * fx
    bottom = mosaic[py0 + 1, px0] * (1 - fx) + mosaic[py0 + 1, px0 + 1] * fx
    elevation = top * (1 - fy) + bottom * fy
    return np.maximum(elevation, 0.0)    # 바다·결측값(음수)은 0 m 로


# ----------------------------------------------------------------------
# [임시] 연료: 임상도를 반영하기 전까지 사용
# ----------------------------------------------------------------------
def rule_based_fuel(elevation: np.ndarray, cell: float = CELL_SIZE_M) -> np.ndarray:
    """
    [임시·가정] 임상도가 없을 때 쓰는 연료 지도. 가상 산과 같은 사면 규칙:
      남향 사면 → 침엽수(소나무), 북향 사면 → 활엽수, 그 사이 → 혼효림,
      주변보다 높은 능선 → 침엽수, 아주 가파른 곳(40° 이상) → 바위,
      지도에서 가장 낮고 평평한 곳 → 초지(논밭·시가지일 수 있으나 구분 불가)
    실제 숲 분포와 다를 수 있으므로 화면·문서에 [임시]로 표시한다.
    """
    dz_south, dz_east = np.gradient(elevation, cell)
    slope = np.degrees(np.arctan(np.hypot(dz_east, dz_south)))
    aspect = np.degrees(np.arctan2(-dz_east, dz_south)) % 360.0

    # 주변(약 600 m)보다 얼마나 높은지: 능선·계곡 구분
    k = 10
    padded = np.pad(elevation, k, mode="edge")
    local_mean = np.zeros_like(elevation)
    for dy in range(-k, k + 1, 2):
        for dx in range(-k, k + 1, 2):
            local_mean += padded[k + dy:k + dy + elevation.shape[0], k + dx:k + dx + elevation.shape[1]]
    local_mean /= ((2 * k) // 2 + 1) ** 2
    relief = elevation - local_mean

    sea = elevation <= 0.5                            # 고도 0 m = 바다 (섬 산)
    fuel = np.full(elevation.shape, FUEL_MIXED, dtype=int)
    fuel[(aspect >= 125) & (aspect <= 235)] = FUEL_CONIFER
    fuel[(aspect >= 290) | (aspect <= 70)] = FUEL_BROADLEAF
    fuel[relief > 25] = FUEL_CONIFER                  # 능선
    fuel[relief < -25] = FUEL_BROADLEAF               # 계곡
    land = elevation[~sea] if (~sea).any() else elevation
    low = elevation < np.percentile(land, 12)
    fuel[low & (slope < 4)] = FUEL_GRASS              # 낮고 평평한 곳
    fuel[slope >= 40] = FUEL_ROCK                     # 절벽·암릉
    fuel[sea] = FUEL_WATER
    return fuel


# ----------------------------------------------------------------------
# 정보 파일과 시나리오
# ----------------------------------------------------------------------
def read_info(mountain_id: str) -> dict:
    path = mountain_folder(mountain_id) / "info.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_info(mountain_id: str, info: dict) -> None:
    folder = mountain_folder(mountain_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


def default_ignition(elevation: np.ndarray, fuel: np.ndarray, summit: tuple[int, int] | None = None,
                     burnable=(1, 2, 3, 4, 5)) -> tuple[int, int]:
    """
    기본 발화 지점: 정상에서 남서쪽으로 약 2.4 km 떨어진, 탈 수 있는 셀 중 가장 가까운 곳.
    (봄철 서풍·남서풍이 산 위쪽으로 불을 밀어 올리는 상황을 보여 주기 위함 [가정])
    """
    height, width = elevation.shape
    cx, cy = summit if summit else ((width - 1) // 2, (height - 1) // 2)
    target_x, target_y = min(max(cx - 57, 10), width - 11), min(max(cy + 57, 10), height - 11)
    ys, xs = np.where(np.isin(fuel, burnable))
    index = int(np.argmin((xs - target_x) ** 2 + (ys - target_y) ** 2))
    return int(xs[index]), int(ys[index])


def write_scenario(mountain: dict, ignition: tuple[int, int]) -> Path:
    """data/scenarios/mountain_<id>.ini — 기본 시나리오(spring_dry_base)와 같은 설정에 지도만 이 산으로"""
    mid = mountain["id"]
    folder = f"../mountains/{mid}"
    has_trails = (mountain_folder(mid) / "trails.txt").exists()
    info = read_info(mid)
    fuel_note = "산림청 임상도 반영" if info.get("forest_source") else "[임시] 사면 규칙 (임상도 반영 전)"
    trail_section = (f"[trails]\ntrail_file = {folder}/trails.txt\nhiker_file = {folder}/hikers.txt\n"
                     if has_trails else
                     "# [trails] 없음: 산림청 등산로를 아직 반영하지 않음 (forest_import.py trails 로 반영)\n")
    text = f"""# ============================================================
# 시나리오: {mountain['name']} ({mountain['peak']} 주변 9 km × 9 km, 실제 지형)
# 지형: {DEM_SOURCE}
# 연료: {fuel_note}
# mountain_builder.py 가 만든 파일 (다시 만들면 덮어씀)
# ============================================================

[general]
name = mountain_{mid}
output_dir = ../../output/mountain_{mid}

[map]
elevation_file = {folder}/elev.asc
fuel_file      = {folder}/fuel.asc
fuel_models    = fuel_models.csv

{trail_section}
[time]
start_datetime      = 2026-04-05 13:00
duration_min        = 600      # [가정] 10시간
time_step_min       = 1
output_interval_min = 10

[ignition]
point1 = {ignition[0]}, {ignition[1]}, 0         # 정상 남서쪽 약 2.4 km [가정]

[weather]
mode = file
file = ../weather/sample_spring_dry.csv
fixed_temp_c        = 18
fixed_rh_pct        = 25
fixed_wind_speed_ms = 6
fixed_wind_dir_deg  = 270

[moisture]
initial_dead_moisture_pct = 8     # [가정]
live_moisture_factor      = 1.0   # [가정]
south_slope_drying_pct    = 2     # [가정]
timelag_min               = 60    # [근거] 1시간 지연 연료

[spread]
random_seed      = 42
spotting_enabled = 1
spot_base_prob   = 0.002   # [가정]
spot_mean_dist_m = 150     # [가정]

[evacuation]
caution_min      = 120     # [가정]
prepare_min      = 60      # [가정]
immediate_min    = 30      # [가정]
check_radius_m   = 500     # [가정]
notify_delay_min = 10      # [가정]
safe_margin_min  = 30      # [가정]
danger_radius_m  = 60      # [가정]

[suppression]
firebreak_cells     = 60
firebreak_ready_min = 60
helicopters         = 3
heli_radius_cells   = 2
heli_interval_min   = 30
heli_effect_min     = 45

[montecarlo]
runs            = 100
wind_speed_sd   = 1.0
wind_dir_sd_deg = 15
rh_sd           = 5
"""
    path = app_config.SCENARIO_DIR / f"mountain_{mid}.ini"
    path.write_text(text, encoding="utf-8")
    return path


def build_mountain(mountain_id: str, keep_fuel: bool = True) -> dict:
    """
    산 하나의 지형을 내려받아 저장하고 시나리오를 만든다.
    keep_fuel: 이미 임상도를 반영한 fuel.asc 가 있으면 덮어쓰지 않는다.
    """
    mountain = find_mountain(mountain_id)
    folder = mountain_folder(mountain_id)
    folder.mkdir(parents=True, exist_ok=True)
    center = grid_spec(mountain)

    elevation = fetch_dem(center)
    write_asc(folder / "elev.asc", elevation, CELL_SIZE_M, "{:.1f}")

    info = read_info(mountain_id)
    if not (keep_fuel and info.get("forest_source") and (folder / "fuel.asc").exists()):
        fuel = rule_based_fuel(elevation)
        write_asc(folder / "fuel.asc", fuel, CELL_SIZE_M, "{:d}")
        info["forest_source"] = None
    else:
        from services.result_loader import read_asc
        fuel = read_asc(folder / "fuel.asc")[1].astype(int)

    info.update({
        "id": mountain_id, "name": mountain["name"], "peak": mountain["peak"], "center": list(center),
        "summit_xy": list(summit_grid(mountain)), "note": mountain.get("note", ""),
        "grid_size": list(grid_shape(center)), "cell_size_m": CELL_SIZE_M, "dem_source": DEM_SOURCE,
        "elevation_range_m": [round(float(elevation.min()), 1), round(float(elevation.max()), 1)],
    })
    info.setdefault("trail_source", None)
    write_info(mountain_id, info)
    ignition = tuple(info.get("ignition") or default_ignition(elevation, fuel, summit_grid(mountain)))
    info["ignition"] = list(ignition)
    write_info(mountain_id, info)
    write_scenario(mountain, ignition)
    return info


# ----------------------------------------------------------------------
# GUI 에서 쓰는 도우미
# ----------------------------------------------------------------------
def scenario_mountain_id(scenario_path: Path) -> str | None:
    """mountain_<id>.ini 시나리오면 산 id, 아니면 None"""
    stem = Path(scenario_path).stem
    return stem[len("mountain_"):] if stem.startswith("mountain_") else None


def scenario_label(scenario_path: Path) -> str:
    """시나리오 고르기 목록에 보일 이름 (실제 산은 '실제 산: 설악산 (대청봉)')"""
    mid = scenario_mountain_id(scenario_path)
    info = read_info(mid) if mid else {}
    if info:
        return f"실제 산: {info['name']} ({info['peak']})"
    return Path(scenario_path).stem


def data_status_text(scenario_path: Path) -> str:
    """실제 산 시나리오의 데이터 반영 상태 한 줄 (가상 산이면 빈 글자)"""
    mid = scenario_mountain_id(scenario_path)
    info = read_info(mid) if mid else {}
    if not info:
        return ""
    forest = info.get("forest_source")
    if not forest:
        fuel = "[임시] 사면 규칙 (임상도 반영 전)"
    elif forest.get("covered_pct", 100) >= 99:
        fuel = "산림청 임상도"
    else:
        fuel = f"산림청 임상도 {forest['covered_pct']:g}% + 나머지 [임시] 규칙"
    trails = info.get("trail_source")
    provider = "OpenStreetMap" if trails and "OpenStreetMap" in trails.get("provider", "") else "산림청"
    trail = (f"{provider} 등산로 {trails['length_km']} km, 등산객 {trails['hikers']}팀" if trails
             else "없음 (산림청 등산로 반영 전, 대피 안내 계산 안 함)")
    return f"지형: 실제 지형(SRTM 기반 30 m) · 연료: {fuel} · 등산로: {trail}"


def weather_presets() -> dict[str, tuple[float, float]]:
    """기상청 예보 받기 위치 목록 {'설악산 (대청봉)': (위도, 경도)} — mountains.json 에서"""
    try:
        return {f"{m['name']} ({m['peak']})": tuple(m.get("summit") or m["center"]) for m in load_registry()}
    except (OSError, ValueError, KeyError):
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="실제 산 지형 내려받기 + 시나리오 만들기 (인터넷 필요)")
    parser.add_argument("--id", help="산 id (mountains.json 참고)")
    parser.add_argument("--all", action="store_true", help="목록의 모든 산")
    parser.add_argument("--scenario-only", action="store_true", help="지형은 그대로 두고 시나리오 파일만 다시 만들기")
    args = parser.parse_args()
    ids = [m["id"] for m in load_registry()] if args.all else ([args.id] if args.id else [])
    if not ids:
        parser.error("--id 산이름 또는 --all 을 지정하세요")
    for mid in ids:
        if args.scenario_only:
            info = read_info(mid)
            path = write_scenario(find_mountain(mid), tuple(info["ignition"]))
            print(f"{mid}: 시나리오 다시 만듦 → {path.name}")
            continue
        info = build_mountain(mid)
        print(f"{info['name']}: 고도 {info['elevation_range_m'][0]:.0f} ~ {info['elevation_range_m'][1]:.0f} m, "
              f"연료 {'임상도' if info.get('forest_source') else '[임시] 사면 규칙'}, "
              f"등산로 {'있음' if info.get('trail_source') else '없음'} → data/mountains/{mid}/")


if __name__ == "__main__":
    main()
