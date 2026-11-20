"""
지도·등산로·시뮬레이션 결과 읽기

C 엔진과 같은 파일 형식을 Python으로 읽어 numpy 배열과 작은 데이터 클래스로 만든다.

    load_scenario_preview(ini) : 시나리오 파일만으로 지도·등산로·발화 지점 읽기 (실행 전 미리보기)
    load_result(summary.json)  : 실행 결과(도착·전소 시각, 통계)까지 읽기
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from services import app_config
from services.scenario_writer import read_ini


# ----------------------------------------------------------------------
# 데이터 클래스
# ----------------------------------------------------------------------
@dataclass
class TrailNode:
    id: int
    kind: str          # PARKING, SHELTER, SUMMIT, JUNCTION, POINT
    x: int
    y: int
    name: str

    @property
    def is_exit(self) -> bool:
        return self.kind in ("PARKING", "SHELTER")


@dataclass
class TrailEdge:
    start_id: int
    end_id: int
    points: list[tuple[int, int]]     # 시작 노드 → 경유점 → 끝 노드 좌표


@dataclass
class Hiker:
    id: int
    name: str
    node_id: int
    speed_kmh: float
    people: int


@dataclass
class MapData:
    """지형·연료·등산로 (실행 전에도 알 수 있는 정보)"""
    name: str
    elevation: np.ndarray
    fuel: np.ndarray
    cell_size: float
    nodes: list[TrailNode] = field(default_factory=list)
    edges: list[TrailEdge] = field(default_factory=list)
    hikers: list[Hiker] = field(default_factory=list)
    ignitions: list[tuple[int, int, float]] = field(default_factory=list)
    start_time: datetime | None = None

    @property
    def height(self) -> int:
        return self.elevation.shape[0]

    @property
    def width(self) -> int:
        return self.elevation.shape[1]

    def node_by_id(self, node_id: int) -> TrailNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)


@dataclass
class SimulationResult:
    """시뮬레이션 결과 (summary.json 과 CSV 파일들)"""
    map: MapData
    summary: dict
    output_dir: Path
    arrival: np.ndarray          # 불 도착 시각 (분), 없으면 -1
    burnout: np.ndarray          # 전소 시각 (분), 없으면 -1
    stats: dict[str, np.ndarray]

    @property
    def end_time(self) -> float:
        return float(self.summary["result"]["end_time_min"])

    @property
    def cell_area_ha(self) -> float:
        return self.map.cell_size ** 2 / 10000.0

    def burned_area_at(self, t: float) -> float:
        """시각 t 까지 불이 지나간 면적 (ha)"""
        return float(np.count_nonzero((self.arrival >= 0) & (self.arrival <= t))) * self.cell_area_ha

    def burning_cells_at(self, t: float) -> int:
        """시각 t 에 연소 중인 셀 수"""
        arrived = (self.arrival >= 0) & (self.arrival <= t)
        not_out = (self.burnout < 0) | (self.burnout > t)
        return int(np.count_nonzero(arrived & not_out))


# ----------------------------------------------------------------------
# 파일 읽기
# ----------------------------------------------------------------------
def read_asc(path: Path) -> tuple[dict, np.ndarray]:
    """ESRI ASCII Grid 읽기 → (헤더, 배열[y, x]). 첫 데이터 줄이 북쪽."""
    header: dict[str, float] = {}
    header_lines = 0
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            parts = line.split()
            if not parts:
                header_lines += 1
                continue
            if not parts[0][0].isalpha():
                break
            header[parts[0].lower()] = float(parts[1])
            header_lines += 1
    data = np.loadtxt(path, skiprows=header_lines, dtype=np.float64, ndmin=2)
    return header, data


def read_trails(path: Path) -> tuple[list[TrailNode], list[TrailEdge]]:
    """등산로 파일(NODE / EDGE 줄)을 읽는다."""
    nodes: list[TrailNode] = []
    raw_edges: list[tuple[int, int, list[tuple[int, int]]]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        tokens = line.split("#", 1)[0].split()
        if not tokens:
            continue
        if tokens[0].upper() == "NODE":
            nodes.append(TrailNode(int(tokens[1]), tokens[2].upper(), int(tokens[3]),
                                   int(tokens[4]), " ".join(tokens[5:])))
        elif tokens[0].upper() == "EDGE":
            count = int(tokens[3])
            coords = [int(v) for v in tokens[4:4 + 2 * count]]
            waypoints = list(zip(coords[0::2], coords[1::2]))
            raw_edges.append((int(tokens[1]), int(tokens[2]), waypoints))

    by_id = {n.id: n for n in nodes}
    edges = []
    for start, end, waypoints in raw_edges:
        a, b = by_id[start], by_id[end]
        edges.append(TrailEdge(start, end, [(a.x, a.y), *waypoints, (b.x, b.y)]))
    return nodes, edges


def read_hikers(path: Path) -> list[Hiker]:
    """등산객 파일(HIKER 줄)을 읽는다."""
    hikers = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        tokens = line.split("#", 1)[0].split()
        if len(tokens) == 6 and tokens[0].upper() == "HIKER":
            hikers.append(Hiker(int(tokens[1]), tokens[2], int(tokens[3]), float(tokens[4]), int(tokens[5])))
    return hikers


def read_grid_csv(path: Path) -> np.ndarray:
    """C 엔진이 저장한 격자 CSV (arrival_time.csv 등)"""
    return np.loadtxt(path, delimiter=",", dtype=np.float64, ndmin=2)


def read_stats_csv(path: Path) -> dict[str, np.ndarray]:
    """stats.csv → {열 이름: 배열}"""
    table = np.genfromtxt(path, delimiter=",", names=True, dtype=np.float64)
    table = np.atleast_1d(table)
    return {name: np.asarray(table[name]) for name in table.dtype.names}


def parse_datetime(text: str) -> datetime | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None


# ----------------------------------------------------------------------
# 시나리오 미리보기와 결과 읽기
# ----------------------------------------------------------------------
def _load_map(name: str, elevation_path: Path, fuel_path: Path,
              trail_path: Path | None, hiker_path: Path | None) -> MapData:
    header, elevation = read_asc(elevation_path)
    _, fuel = read_asc(fuel_path)
    fuel = np.where(fuel < 0, 0, fuel).astype(np.int32)        # NODATA → 0
    data = MapData(name=name, elevation=elevation, fuel=fuel, cell_size=header.get("cellsize", 30.0))
    if trail_path and trail_path.exists():
        data.nodes, data.edges = read_trails(trail_path)
    if hiker_path and hiker_path.exists():
        data.hikers = read_hikers(hiker_path)
    return data


def load_scenario_preview(ini_path: Path) -> MapData:
    """시나리오 .ini 를 읽어 지도·등산로·발화 지점을 불러온다. (C 엔진을 실행하지 않음)"""
    parser = read_ini(ini_path)
    base = ini_path.parent

    def path_of(section: str, key: str) -> Path | None:
        value = parser.get(section, key, fallback="").strip()
        return (base / value).resolve() if value else None

    data = _load_map(parser.get("general", "name", fallback=ini_path.stem),
                     path_of("map", "elevation_file"), path_of("map", "fuel_file"),
                     path_of("trails", "trail_file"), path_of("trails", "hiker_file"))
    if parser.has_section("ignition"):
        for key, value in parser.items("ignition"):
            if key.startswith("point"):
                parts = [p.strip() for p in value.split(",")]
                t = float(parts[2]) if len(parts) > 2 else 0.0
                data.ignitions.append((int(parts[0]), int(parts[1]), t))
    data.start_time = parse_datetime(parser.get("time", "start_datetime", fallback=""))
    return data


def load_result(summary_path: Path) -> SimulationResult:
    """summary.json 과 같은 폴더의 결과 파일들을 읽는다."""
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    out_dir = summary_path.parent
    grid = summary["grid"]
    trails = summary.get("trails", {})

    def engine_path(text: str) -> Path | None:
        return app_config.resolve_engine_path(text) if text else None

    data = _load_map(summary["scenario"]["name"], engine_path(grid["elevation_file"]),
                     engine_path(grid["fuel_file"]), engine_path(trails.get("trail_file", "")),
                     engine_path(trails.get("hiker_file", "")))
    data.ignitions = [(p["x"], p["y"], p["time_min"]) for p in summary.get("ignitions", [])]
    data.start_time = parse_datetime(summary["scenario"].get("start_datetime", ""))

    files = summary["files"]
    return SimulationResult(
        map=data,
        summary=summary,
        output_dir=out_dir,
        arrival=read_grid_csv(out_dir / files["arrival_time"]),
        burnout=read_grid_csv(out_dir / files["burnout_time"]),
        stats=read_stats_csv(out_dir / files["stats"]),
    )


def format_clock(start: datetime | None, minutes: float) -> str:
    """시작 시각 + 경과 분 → '15:03' (시작 시각을 모르면 빈 문자열)"""
    if start is None:
        return ""
    return (start + timedelta(minutes=minutes)).strftime("%H:%M")
