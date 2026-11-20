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


ALERT_KOREAN = {"NONE": "정상", "CAUTION": "주의", "PREPARE": "대피준비",
                "IMMEDIATE": "즉시대피", "ISOLATED": "고립"}


@dataclass
class HikerEvacuation:
    """등산객 한 팀의 대피 결과 (evacuation.json 의 hikers 항목)"""
    id: int
    name: str
    group_size: int
    speed_kmh: float
    start_name: str
    needs_evacuation: bool
    depart_time: float          # 출발 시각 (분), 대피 불필요면 -1
    finish_time: float          # 대피 완료·고립 시각 (분), 없으면 -1
    status: str                 # HIKING, SAFE, TRAPPED ...
    at_risk: bool
    route_found: bool
    route_node_ids: list[int]
    exit_name: str
    travel_time: float
    min_margin: float | None    # None 이면 경로 근처에 불이 오지 않음
    samples: np.ndarray         # [시각, x, y, 경보 번호, 남은 시간, 상태 번호] × 1분 간격

    def _index_at(self, t: float) -> int:
        times = self.samples[:, 0]
        return int(np.clip(np.searchsorted(times, t, side="right") - 1, 0, len(times) - 1))

    def position_at(self, t: float) -> tuple[float, float]:
        """시각 t 의 위치 (1분 간격 기록 사이를 선형 보간)"""
        times = self.samples[:, 0]
        return float(np.interp(t, times, self.samples[:, 1])), float(np.interp(t, times, self.samples[:, 2]))

    def alert_at(self, t: float, levels: list[str]) -> str:
        return levels[int(self.samples[self._index_at(t), 3])]

    def remaining_at(self, t: float) -> float:
        """주변에 불이 오기까지 남은 시간 (분), 불이 오지 않으면 -1"""
        return float(self.samples[self._index_at(t), 4])

    def status_at(self, t: float, names: list[str]) -> str:
        return names[int(self.samples[self._index_at(t), 5])]


@dataclass
class EvacuationData:
    settings: dict
    summary: dict
    alert_levels: list[str]
    status_names: list[str]
    hikers: list[HikerEvacuation]


def load_evacuation(path: Path) -> EvacuationData:
    """evacuation.json 읽기"""
    data = json.loads(path.read_text(encoding="utf-8"))
    hikers = []
    for h in data["hikers"]:
        route = h["route"]
        hikers.append(HikerEvacuation(
            id=h["id"], name=h["name"], group_size=h["group_size"], speed_kmh=h["speed_kmh"],
            start_name=h["start_name"], needs_evacuation=h["needs_evacuation"],
            depart_time=h["depart_time_min"], finish_time=h["finish_time_min"], status=h["status"],
            at_risk=h["at_risk"], route_found=route["found"], route_node_ids=route.get("nodes", []),
            exit_name=route.get("exit_name", ""), travel_time=route.get("travel_time_min", 0.0),
            min_margin=route.get("min_margin_min"),
            samples=np.asarray(h["samples"], dtype=np.float64).reshape(-1, 6),
        ))
    return EvacuationData(data["settings"], data["summary"], data["alert_levels"], data["status_names"], hikers)


@dataclass
class StrategyResult:
    """진화 전략 하나의 결과 (suppression.json 의 strategies 항목)"""
    key: str
    name: str
    use_firebreak: bool
    use_helicopters: bool
    burned_area_ha: float
    reduction_pct: float
    trail_burned_km: float
    spot_fires: int
    at_risk_hikers: int
    at_risk_people: int
    trapped_hikers: int
    arrival: np.ndarray
    burnout: np.ndarray
    drops: np.ndarray            # [시각, x, y] × 살수 횟수


@dataclass
class SuppressionData:
    settings: dict
    firebreak_cells: list[tuple[int, int]]
    firebreak_steps: list[dict]
    strategies: list[StrategyResult]

    def by_key(self, key: str) -> StrategyResult | None:
        return next((s for s in self.strategies if s.key == key), None)


def load_suppression(path: Path) -> SuppressionData:
    """suppression.json 과 전략별 도착·전소 격자 CSV 읽기"""
    data = json.loads(path.read_text(encoding="utf-8"))
    folder = path.parent
    strategies = []
    for s in data["strategies"]:
        strategies.append(StrategyResult(
            key=s["key"], name=s["name"], use_firebreak=s["use_firebreak"],
            use_helicopters=s["use_helicopters"], burned_area_ha=s["burned_area_ha"],
            reduction_pct=s["reduction_pct"], trail_burned_km=s["trail_burned_km"],
            spot_fires=s["spot_fires"], at_risk_hikers=s["at_risk_hikers"],
            at_risk_people=s["at_risk_people"], trapped_hikers=s["trapped_hikers"],
            arrival=read_grid_csv(folder / s["arrival_file"]),
            burnout=read_grid_csv(folder / s["burnout_file"]),
            drops=np.asarray(s["drops"], dtype=np.float64).reshape(-1, 3),
        ))
    firebreak = data["firebreak"]
    return SuppressionData(
        settings=data["settings"],
        firebreak_cells=[(int(x), int(y)) for x, y in firebreak["cells"]],
        firebreak_steps=firebreak["steps"],
        strategies=strategies,
    )


@dataclass
class SimulationResult:
    """시뮬레이션 결과 (summary.json 과 CSV 파일들)"""
    map: MapData
    summary: dict
    output_dir: Path
    arrival: np.ndarray          # 불 도착 시각 (분), 없으면 -1
    burnout: np.ndarray          # 전소 시각 (분), 없으면 -1
    stats: dict[str, np.ndarray]
    evacuation: EvacuationData | None = None
    suppression: SuppressionData | None = None

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
    evacuation = load_evacuation(out_dir / files["evacuation"]) if "evacuation" in files else None
    suppression = load_suppression(out_dir / files["suppression"]) if "suppression" in files else None
    return SimulationResult(
        map=data,
        summary=summary,
        output_dir=out_dir,
        arrival=read_grid_csv(out_dir / files["arrival_time"]),
        burnout=read_grid_csv(out_dir / files["burnout_time"]),
        stats=read_stats_csv(out_dir / files["stats"]),
        evacuation=evacuation,
        suppression=suppression,
    )


def format_clock(start: datetime | None, minutes: float) -> str:
    """시작 시각 + 경과 분 → '15:03' (시작 시각을 모르면 빈 문자열)"""
    if start is None:
        return ""
    return (start + timedelta(minutes=minutes)).strftime("%H:%M")
