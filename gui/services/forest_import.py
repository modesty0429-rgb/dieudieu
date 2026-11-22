"""
산림청 자료(SHP) → 시뮬레이션 데이터 변환

산림청이 공개하는 SHP(Shapefile) 자료를 실제 산 지도(mountain_builder.py 가 만든 300×300칸)에 맞춰 바꾼다.

  1) 등산로 (산림청 "등산로" 자료: 선 레이어 + 지점(spot) 레이어)
       → data/mountains/<id>/trails.txt, hikers.txt
     선을 격자 칸으로 바꾼 뒤, 선의 끝점·두 선이 만나는 점·이름 있는 지점을 노드로 삼아 그래프를 만든다.

  2) 임상도 (산림청 "임상도": 숲 종류 다각형, 임종 코드 FRTP_CD)
       → data/mountains/<id>/fuel.asc
     다각형을 격자에 칠하고(래스터화) 임종 코드를 연료 코드로 바꾼다 (forest_fuel_map.csv).

좌표계는 SHP 옆의 .prj 파일을 읽어 자동으로 판단한다 (산림청 자료는 보통 EPSG:5186 또는 5179).
.prj 가 없으면 --crs 5186 처럼 직접 지정한다. 글자 인코딩은 cp949 → utf-8 순서로 시도한다.

실행 예 (저장소 폴더에서):
    python gui/services/forest_import.py fields  data/raw/등산로_북한산.shp
    python gui/services/forest_import.py trails  --id seoraksan --lines data/raw/설악산/PMNTN_설악산_대청봉_428302602.shp
                                                 --spots data/raw/설악산/PMNTN_SPOT_설악산_대청봉_428302602.shp
    (큰 산은 시·군·구별 파일 여러 개를 --lines a.shp b.shp --spots c.shp d.shp 처럼 함께 넣는다)
    python gui/services/forest_import.py forest  --id bukhansan --shp data/raw/임상도_서울.shp

필요한 라이브러리 (변환할 때만): pyshp, pyproj, pillow  →  python -m pip install pyshp pyproj pillow
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # gui 폴더 (직접 실행할 때)

from services import mountain_builder as mb  # noqa: E402
from services.result_loader import read_asc  # noqa: E402
from services.terrain_generator import write_asc  # noqa: E402

FUEL_MAP_FILE = mb.MOUNTAIN_DIR / "forest_fuel_map.csv"
MAX_WAYPOINTS = 64           # C 엔진 WF_MAX_WAYPOINTS 와 같음
NAME_MAX_CHARS = 18          # C 엔진 이름 칸이 64바이트 (한글 3바이트) 이므로 넉넉히 자름
SPOT_SNAP_CELLS = 5          # 지점이 등산로에서 이만큼(150 m) 안에 있어야 노드로 붙인다 [가정]

# 지점 종류(산림청 MANAGE_SP2) → 노드 종류. 표에 없는 지점(가로등·벤치·계단·안내판 등)은 쓰지 않는다.
#   AUTO: 노드로 두되 종류는 그래프 모양으로 정함 (시종점이 막다른 끝이면 들머리=주차장, 아니면 갈림길)
#   [근거: 산림청 등산로 자료 설명 — 시종점 = 등산로 구간의 시작·끝, 분기점 = 갈림길]
SPOT_KIND_TYPES = [
    ("SHELTER", ("대피소", "산장")),
    ("PARKING", ("주차장", "탐방지원센터", "탐방안내소", "매표소")),
    ("SUMMIT", ("정상", "봉우리")),
    ("JUNCTION", ("분기점", "갈림길", "삼거리", "사거리")),
    ("AUTO", ("시종점", "들머리", "등산로시점")),
]
# 종류가 표에 없어도 이름에 이 글자가 있으면 사용 (예: 기타 / "지리산정상,정상부표지석")
SPOT_NAME_TYPES = [("SHELTER", ("대피소", "산장")), ("PARKING", ("주차장", "탐방지원센터")), ("SUMMIT", ("정상",))]
# 지점 상세 설명에서 이름으로 쓰지 않을 글자 (예: "시종점,등산안내플랜카드,내지마을" → "내지마을")
GENERIC_NAME_WORDS = ("시종점", "분기점", "기타", "방향", "갈래", "표지", "계단", "난간", "전경", "플랜카드",
                      "안내도", "등산로시점", "로프", "훼손")

# 필드 자동 찾기 후보 (산림청 자료에서 쓰이는 이름 + 일반적인 이름)
NAME_FIELD_HINTS = ("DETAIL_SPO", "DETAIL_SP", "SPOT_NM", "POI_NM", "NAME", "NM", "명칭", "이름")
TYPE_FIELD_HINTS = ("MANAGE_SP2", "MANAGE_SP1", "SPOT_SE", "SPOT_TY", "TYPE", "구분", "종류")
FOREST_FIELD_HINTS = ("FRTP_CD", "FRTP", "임종", "FROR_CD")


# ----------------------------------------------------------------------
# SHP 읽기 공통
# ----------------------------------------------------------------------
def open_shapefile(path: Path, encoding: str | None = None):
    """SHP 열기. 인코딩을 지정하지 않으면 cp949(산림청 자료 대부분) → utf-8 순서로 시도"""
    import shapefile

    for enc in ([encoding] if encoding else ["cp949", "utf-8"]):
        try:
            reader = shapefile.Reader(str(path), encoding=enc)
            reader.records()                      # 글자가 제대로 읽히는지 미리 확인
            return reader
        except (UnicodeDecodeError, shapefile.ShapefileException):   # 필드 이름이 다른 인코딩일 때
            continue
    raise ValueError(f"{path.name}: 글자 인코딩을 알 수 없음 (--encoding cp949 또는 utf-8 지정)")


def make_transformer(path: Path, crs_text: str | None):
    """SHP 좌표계 → 위경도(WGS84) 변환기. .prj 가 있으면 그것을, 없으면 --crs 값을 쓴다."""
    from pyproj import CRS, Transformer

    if crs_text:
        source = CRS.from_user_input(int(crs_text) if crs_text.isdigit() else crs_text)
    else:
        prj = path.with_suffix(".prj")
        if not prj.exists():
            raise ValueError(f"{path.name}: 좌표계 파일(.prj)이 없음. --crs 5186 처럼 직접 지정하세요")
        source = CRS.from_wkt(prj.read_text(encoding="utf-8", errors="ignore"))
    return Transformer.from_crs(source, "EPSG:4326", always_xy=True), source


def field_names(reader) -> list[str]:
    return [f[0] for f in reader.fields[1:]]       # 첫 필드는 삭제 표시용


def find_field(reader, hints: tuple[str, ...], wanted: str | None) -> str | None:
    """사용자가 지정한 필드, 없으면 후보 이름 중 처음 맞는 필드"""
    names = field_names(reader)
    if wanted:
        if wanted not in names:
            raise ValueError(f"필드 '{wanted}' 가 없음. 있는 필드: {', '.join(names)}")
        return wanted
    upper = {n.upper(): n for n in names}
    for hint in hints:
        if hint.upper() in upper:
            return upper[hint.upper()]
    return None


def describe_fields(path: Path, encoding: str | None = None, samples: int = 5) -> str:
    """SHP 의 도형 종류, 좌표계, 필드와 예시 값 (어떤 필드를 쓸지 정할 때 참고)"""
    reader = open_shapefile(path, encoding)
    lines = [f"{path.name}: {reader.shapeTypeName}, 도형 {len(reader)}개"]
    try:
        _, crs = make_transformer(path, None)
        lines.append(f"좌표계: {crs.name} (EPSG:{crs.to_epsg()})")
    except ValueError as error:
        lines.append(str(error))
    records = reader.records()
    for i, name in enumerate(field_names(reader)):
        values = []
        for rec in records:
            text = str(rec[i]).strip()
            if text and text not in values:
                values.append(text)
            if len(values) >= samples:
                break
        lines.append(f"  {name:<12} 예: {', '.join(values)}")
    return "\n".join(lines)


def shape_parts_grid(shape, transformer, center) -> list[np.ndarray]:
    """도형의 각 부분(선 조각·다각형 고리)을 격자 좌표 (실수) 배열 [[x, y], ...] 로"""
    points = np.asarray(shape.points, dtype=float)
    if len(points) == 0:
        return []
    lon, lat = transformer.transform(points[:, 0], points[:, 1])
    gx, gy = mb.latlon_to_grid(np.asarray(lat), np.asarray(lon), center)
    bounds = list(shape.parts) + [len(points)]
    return [np.column_stack([gx[a:b], gy[a:b]]) for a, b in zip(bounds[:-1], bounds[1:]) if b - a >= 2]


# ----------------------------------------------------------------------
# 등산로: 선 → 격자 칸 경로
# ----------------------------------------------------------------------
@dataclass
class TrailLine:
    cells: list[tuple[int, int]]
    cut_start: bool = False      # 지도 경계에서 잘린 쪽 끝인가
    cut_end: bool = False


def densify_cells(part: np.ndarray) -> list[tuple[int, int] | None]:
    """선을 반 칸 간격으로 따라가며 지나는 칸 목록. 지도 밖은 None"""
    cells: list[tuple[int, int] | None] = []
    for (x0, y0), (x1, y1) in zip(part[:-1], part[1:]):
        steps = max(1, int(np.ceil(max(abs(x1 - x0), abs(y1 - y0)) * 2)))
        for s in range(steps + 1):
            t = s / steps
            x, y = int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t))
            cell = (x, y) if 0 <= x < mb.GRID_SIZE and 0 <= y < mb.GRID_SIZE else None
            if not cells or cells[-1] != cell:
                cells.append(cell)
    return cells


def split_inside_runs(cells: list[tuple[int, int] | None]) -> list[TrailLine]:
    """지도 안에 있는 연속 구간마다 TrailLine 하나. 지도 밖으로 나간 쪽 끝은 cut 표시"""
    lines, run, cut_start = [], [], False
    for i, cell in enumerate(cells):
        if cell is None:
            if len(run) >= 2:
                lines.append(TrailLine(run, cut_start, True))
            run, cut_start = [], True
        else:
            if not run and i > 0:
                cut_start = cells[i - 1] is None
            run.append(cell)
    if len(run) >= 2:
        lines.append(TrailLine(run, cut_start, False))
    return lines


def read_trail_lines(path: Path, center, crs: str | None, encoding: str | None) -> list[TrailLine]:
    reader = open_shapefile(path, encoding)
    if reader.shapeType not in (3, 13, 23):        # POLYLINE (Z, M 포함)
        raise ValueError(f"{path.name}: 선(POLYLINE) 레이어가 아님 ({reader.shapeTypeName})")
    transformer, _ = make_transformer(path, crs)
    lines: list[TrailLine] = []
    for shape in reader.shapes():
        for part in shape_parts_grid(shape, transformer, center):
            lines.extend(split_inside_runs(densify_cells(part)))
    return lines


# ----------------------------------------------------------------------
# 등산로: 지점(spot)
# ----------------------------------------------------------------------
@dataclass
class Spot:
    x: float
    y: float
    name: str
    kind: str        # 지점 종류 글자 (없으면 "")


def read_spots(path: Path, center, crs: str | None, encoding: str | None,
               name_field: str | None, type_field: str | None) -> list[Spot]:
    reader = open_shapefile(path, encoding)
    if reader.shapeType not in (1, 11, 21, 8, 18, 28):   # POINT, MULTIPOINT
        raise ValueError(f"{path.name}: 점(POINT) 레이어가 아님 ({reader.shapeTypeName})")
    transformer, _ = make_transformer(path, crs)
    nf = find_field(reader, NAME_FIELD_HINTS, name_field)
    tf = find_field(reader, TYPE_FIELD_HINTS, type_field)
    names = field_names(reader)
    spots = []
    for shape_rec in reader.shapeRecords():
        if not shape_rec.shape.points:
            continue
        px, py = shape_rec.shape.points[0][:2]
        lon, lat = transformer.transform(px, py)
        gx, gy = mb.latlon_to_grid(np.array([lat]), np.array([lon]), center)
        rec = shape_rec.record
        name = str(rec[names.index(nf)]).strip() if nf else ""
        kind = str(rec[names.index(tf)]).strip() if tf else ""
        spots.append(Spot(float(gx[0]), float(gy[0]), name, kind))
    return spots


def spot_node_type(spot: Spot) -> str | None:
    """지점 종류 글자(없으면 이름)로 노드 종류를 정한다. 쓰지 않는 지점이면 None"""
    for node_type, words in SPOT_KIND_TYPES:
        if any(word in spot.kind for word in words):
            return node_type
    for node_type, words in SPOT_NAME_TYPES:
        if any(word in spot.name for word in words):
            return node_type
    return None


def spot_display_name(spot: Spot) -> str:
    """지점 상세 설명에서 고유한 이름만 뽑는다. "지리산정상,정상부표지석" → "지리산정상", "시종점" → "" """
    for token in spot.name.replace("/", ",").split(","):
        token = "".join(ch for ch in token if not ch.isspace() and ch not in "\"'()[]")
        if token and token != spot.kind and not any(w in token for w in GENERIC_NAME_WORDS):
            return token
    return ""


# ----------------------------------------------------------------------
# 등산로: 그래프 만들기
# ----------------------------------------------------------------------
@dataclass
class Node:
    x: int
    y: int
    type: str = "JUNCTION"
    name: str = ""
    cut: bool = False            # 지도 경계에서 잘린 끝
    spot: bool = False           # 지점 자료로 이름·종류를 받음


@dataclass
class Edge:
    a: int
    b: int
    cells: list[tuple[int, int]] = field(default_factory=list)   # a → b 순서, 양 끝 포함


def node_cells_from_lines(lines: list[TrailLine]) -> dict[tuple[int, int], bool]:
    """노드가 될 칸 → 경계에서 잘렸는지. 선의 끝점과 둘 이상의 선이 지나는 칸"""
    users: dict[tuple[int, int], set[int]] = defaultdict(set)
    for i, line in enumerate(lines):
        for cell in line.cells:
            users[cell].add(i)
    nodes: dict[tuple[int, int], bool] = {}
    for line in lines:
        nodes[line.cells[0]] = nodes.get(line.cells[0], False) or line.cut_start
        nodes[line.cells[-1]] = nodes.get(line.cells[-1], False) or line.cut_end
    for cell, ids in users.items():
        if len(ids) >= 2:
            nodes.setdefault(cell, False)
    return nodes


def cluster_cells(cells: list[tuple[int, int]]) -> dict[tuple[int, int], int]:
    """붙어 있는(8방향) 노드 칸들을 하나로 묶는다. 칸 → 묶음 번호"""
    cell_set, label, count = set(cells), {}, 0
    for start in cells:
        if start in label:
            continue
        stack = [start]
        label[start] = count
        while stack:
            cx, cy = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nb = (cx + dx, cy + dy)
                    if nb in cell_set and nb not in label:
                        label[nb] = count
                        stack.append(nb)
        count += 1
    return label


SPOT_PRIORITY = ["SHELTER", "SUMMIT", "PARKING", "AUTO", "JUNCTION"]    # 같은 칸에 여러 지점이면 앞쪽 우선


def snap_spots(lines: list[TrailLine], spots: list[Spot]) -> dict[tuple[int, int], Spot]:
    """각 지점을 가장 가까운 등산로 칸에 붙인다 (SPOT_SNAP_CELLS 안쪽만)"""
    trail_cells = np.array(sorted({c for line in lines for c in line.cells}))
    snapped: dict[tuple[int, int], Spot] = {}
    if len(trail_cells) == 0:
        return snapped
    for spot in spots:
        if spot_node_type(spot) is None:
            continue
        d2 = (trail_cells[:, 0] - spot.x) ** 2 + (trail_cells[:, 1] - spot.y) ** 2
        k = int(np.argmin(d2))
        if d2[k] <= SPOT_SNAP_CELLS ** 2:
            cell = (int(trail_cells[k, 0]), int(trail_cells[k, 1]))
            if cell not in snapped or SPOT_PRIORITY.index(spot_node_type(spot)) < \
                    SPOT_PRIORITY.index(spot_node_type(snapped[cell])):
                snapped[cell] = spot
    return snapped


def build_graph(lines: list[TrailLine], snapped: dict[tuple[int, int], Spot]) -> tuple[list[Node], list[Edge]]:
    """선 목록 → 노드·간선. 노드 칸에서 선을 끊어 간선을 만들고, 겹치는 간선은 짧은 것만 남긴다."""
    node_cells = node_cells_from_lines(lines)
    for cell in snapped:
        node_cells.setdefault(cell, False)
    label = cluster_cells(list(node_cells))

    # 묶음마다 노드 하나 (지점이 붙은 칸이 있으면 그 칸, 없으면 묶음의 첫 칸)
    nodes: dict[int, Node] = {}
    for cell, group in label.items():
        node = nodes.get(group)
        if node is None:
            node = nodes[group] = Node(cell[0], cell[1])
        node.cut = node.cut or node_cells[cell]
        if cell in snapped and not node.spot:
            spot = snapped[cell]
            node.x, node.y, node.spot = cell[0], cell[1], True
            node.name = spot_display_name(spot)
            node.type = spot_node_type(spot) or "POINT"
        elif cell in snapped and SPOT_PRIORITY.index(spot_node_type(snapped[cell])) < SPOT_PRIORITY.index(node.type):
            spot = snapped[cell]                       # 같은 묶음에 더 중요한 지점이 있으면 그것으로
            node.x, node.y = cell
            node.name, node.type = spot_display_name(spot), spot_node_type(spot)

    best: dict[tuple[int, int], Edge] = {}
    for line in lines:
        start_group, run = None, []
        for cell in line.cells:
            group = label.get(cell)
            if group is None:
                run.append(cell)
                continue
            if start_group is not None and group != start_group:
                edge = Edge(start_group, group, [(nodes[start_group].x, nodes[start_group].y)] + run
                            + [(nodes[group].x, nodes[group].y)])
                key = (min(edge.a, edge.b), max(edge.a, edge.b))
                if key not in best or len(edge.cells) < len(best[key].cells):
                    best[key] = edge
            start_group, run = group, []

    used = sorted({e.a for e in best.values()} | {e.b for e in best.values()})
    remap = {old: new for new, old in enumerate(used)}
    node_list = [nodes[old] for old in used]
    edges = [Edge(remap[e.a], remap[e.b], e.cells) for e in best.values()]
    return merge_degree_two(node_list, edges)


def merge_degree_two(nodes: list[Node], edges: list[Edge]) -> tuple[list[Node], list[Edge]]:
    """이름 없는 '그냥 이어지는 점'(간선 2개, 지점 아님, 경계 아님)을 없애고 두 간선을 하나로 잇는다"""
    changed = True
    while changed:
        changed = False
        degree: dict[int, list[int]] = defaultdict(list)
        for i, e in enumerate(edges):
            degree[e.a].append(i)
            degree[e.b].append(i)
        for n, incident in degree.items():
            node = nodes[n]
            if len(incident) != 2 or node.spot or node.cut:
                continue
            e1, e2 = edges[incident[0]], edges[incident[1]]
            if e1 is e2:
                continue
            path1 = e1.cells if e1.b == n else e1.cells[::-1]       # ... → n
            path2 = e2.cells if e2.a == n else e2.cells[::-1]       # n → ...
            a, b = (e1.a if e1.b == n else e1.b), (e2.b if e2.a == n else e2.a)
            if a == b:
                continue                                          # 고리가 되면 그대로 둔다
            merged = Edge(a, b, path1 + path2[1:])
            edges = [e for i, e in enumerate(edges) if i not in incident] + [merged]
            changed = True
            break
    used = sorted({e.a for e in edges} | {e.b for e in edges})
    remap = {old: new for new, old in enumerate(used)}
    return [nodes[i] for i in used], [Edge(remap[e.a], remap[e.b], e.cells) for e in edges]


def simplify_path(cells: list[tuple[int, int]], tolerance: float = 1.0) -> list[tuple[int, int]]:
    """더글러스-포이커 단순화: 직선에서 tolerance 칸 이상 벗어나는 꺾인 점만 남긴다"""
    if len(cells) <= 2:
        return list(cells)
    pts = np.asarray(cells, dtype=float)
    a, b = pts[0], pts[-1]
    ab = b - a
    length = float(np.hypot(*ab))
    if length == 0:
        dist = np.hypot(*(pts - a).T)
    else:
        dist = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / length
    k = int(np.argmax(dist))
    if dist[k] <= tolerance:
        return [cells[0], cells[-1]]
    return simplify_path(cells[:k + 1], tolerance)[:-1] + simplify_path(cells[k:], tolerance)


def edge_waypoints(edge: Edge) -> list[tuple[int, int]]:
    """간선의 중간 경유점 (양 끝 노드 제외, 최대 MAX_WAYPOINTS 개)"""
    middle = simplify_path(edge.cells)[1:-1]
    if len(middle) > MAX_WAYPOINTS:
        index = np.linspace(0, len(middle) - 1, MAX_WAYPOINTS).round().astype(int)
        middle = [middle[i] for i in index]
    return middle


# ----------------------------------------------------------------------
# 등산로: 노드 이름·종류 마무리
# ----------------------------------------------------------------------
def boundary_side(node: Node) -> str:
    size = mb.GRID_SIZE - 1
    distances = {"북": node.y, "남": size - node.y, "서": node.x, "동": size - node.x}
    return min(distances, key=distances.get)


def finish_nodes(nodes: list[Node], edges: list[Edge], elevation: np.ndarray, mountain: dict) -> None:
    """
    이름·종류가 없는 노드를 규칙으로 채운다.
      지도 경계에서 잘린 끝     → PARKING "지도경계(방향)"  [가정: 9 km 지도 밖은 안전 지역]
      막다른 끝 중 '시종점' 지점이거나 낮은 곳 → PARKING "들머리"  [가정: 등산로 끝의 낮은 곳은 보통 들머리]
      막다른 끝 중 높은 곳      → POINT
      정상 위치 근처(300 m)     → SUMMIT 정상 이름 (지점 자료에 정상이 없을 때)
      나머지                    → JUNCTION "갈림길"
    """
    degree = defaultdict(int)
    for e in edges:
        degree[e.a] += 1
        degree[e.b] += 1
    node_elev = [float(elevation[n.y, n.x]) for n in nodes]
    low_line = float(np.percentile(node_elev, 35)) if nodes else 0.0
    counters: dict[str, int] = defaultdict(int)

    def numbered(base: str) -> str:
        counters[base] += 1
        return f"{base}{counters[base]}"

    generic = {"SHELTER": "대피소", "PARKING": "주차장", "SUMMIT": "봉우리", "JUNCTION": "갈림길"}
    for i, node in enumerate(nodes):
        if node.spot and node.type != "AUTO":
            node.name = node.name or numbered(generic.get(node.type, "지점"))
            continue
        trailhead = node.spot                          # 산림청 '시종점' 지점
        if node.cut:
            node.type, base = "PARKING", f"지도경계{boundary_side(node)}"
        elif degree[i] == 1 and (trailhead or node_elev[i] <= low_line):
            node.type, base = "PARKING", "들머리"
        elif degree[i] == 1:
            node.type, base = "POINT", "끝지점"
        else:
            node.type, base = "JUNCTION", "갈림길"
        node.name = node.name if node.spot and node.name else numbered(base)

    if nodes and not any(n.type == "SUMMIT" for n in nodes):
        sx, sy = mb.summit_grid(mountain)
        k = int(np.argmin([(n.x - sx) ** 2 + (n.y - sy) ** 2 for n in nodes]))
        if (nodes[k].x - sx) ** 2 + (nodes[k].y - sy) ** 2 <= 10 ** 2 and nodes[k].type != "PARKING":
            nodes[k].type, nodes[k].name = "SUMMIT", mountain["peak"]
    for node in nodes:
        node.name = "".join(node.name.split())[:NAME_MAX_CHARS] or "지점"


# ----------------------------------------------------------------------
# 등산로: 파일 쓰기
# ----------------------------------------------------------------------
HIKER_TEMPLATES = [("정상팀", 3.5, 3), ("산악회", 3.0, 12), ("혼자등산", 4.5, 1), ("가족", 2.5, 4), ("트레일러너", 6.0, 1)]


def write_trails_file(path: Path, nodes: list[Node], edges: list[Edge], source: str) -> None:
    lines = [f"# 실제 등산로 그래프 (forest_import.py 로 변환, 출처: {source})",
             "# NODE 번호 종류 x y 이름",
             "#   종류: JUNCTION 갈림길, SHELTER 대피소, PARKING 주차장(지도 경계·들머리 포함), SUMMIT 정상, POINT 기타"]
    for i, n in enumerate(nodes, start=1):
        lines.append(f"NODE {i:3d} {n.type:<8} {n.x:3d} {n.y:3d} {n.name}")
    lines += ["", "# EDGE 시작번호 끝번호 경유점개수 [x1 y1 x2 y2 ...]"]
    for e in edges:
        waypoints = edge_waypoints(e)
        coords = " ".join(f"{x} {y}" for x, y in waypoints)
        lines.append(f"EDGE {e.a + 1:3d} {e.b + 1:3d} {len(waypoints)} {coords}".rstrip())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def choose_hiker_nodes(nodes: list[Node], elevation: np.ndarray) -> list[int]:
    """등산객을 둘 노드: 정상 먼저, 그다음 높은 곳부터 (서로 1 km 이상 떨어지게, 대피 목적지는 제외) [가정]"""
    candidates = [i for i, n in enumerate(nodes) if n.type not in ("PARKING", "SHELTER")]
    candidates.sort(key=lambda i: (nodes[i].type != "SUMMIT", -float(elevation[nodes[i].y, nodes[i].x])))
    chosen: list[int] = []
    for min_gap in (33, 15, 0):                       # 1 km → 450 m → 제한 없음 순서로 완화
        for i in candidates:
            if len(chosen) >= len(HIKER_TEMPLATES):
                return chosen
            if i in chosen:
                continue
            if all((nodes[i].x - nodes[j].x) ** 2 + (nodes[i].y - nodes[j].y) ** 2 >= min_gap ** 2 for j in chosen):
                chosen.append(i)
    return chosen


def write_hikers_file(path: Path, nodes: list[Node], elevation: np.ndarray) -> int:
    lines = ["# 등산객 목록 (forest_import.py 가 정상·높은 지점에 자동 배치) [가정]",
             "# HIKER 번호 이름(공백 없이) 현재노드번호 평지보행속도(km/h) 인원"]
    chosen = choose_hiker_nodes(nodes, elevation)
    for k, node_index in enumerate(chosen):
        name, speed, people = HIKER_TEMPLATES[k]
        lines.append(f"HIKER {k + 1} {name} {node_index + 1} {speed} {people}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(chosen)


def data_location_hint(path: Path, mountain: dict, crs: str | None, encoding: str | None) -> str:
    """자료가 실제로 있는 위치와 정상까지 거리 (이름만 같은 다른 지역 산 자료인지 알려 주기 위함)"""
    import math

    reader = open_shapefile(path, encoding)
    transformer, _ = make_transformer(path, crs)
    x0, y0, x1, y1 = reader.bbox
    lon, lat = transformer.transform((x0 + x1) / 2, (y0 + y1) / 2)
    lat0, lon0 = mountain["center"]
    north = math.radians(lat - lat0) * mb.EARTH_RADIUS_M / 1000
    east = math.radians(lon - lon0) * mb.EARTH_RADIUS_M * math.cos(math.radians(lat0)) / 1000
    distance = math.hypot(north, east)
    hint = (f"  자료 위치: 위도 {lat:.4f}, 경도 {lon:.4f} → {mountain['name']} {mountain['peak']}에서 {distance:.1f} km "
            f"({'북' if north > 0 else '남'}쪽 {abs(north):.1f} km, {'동' if east > 0 else '서'}쪽 {abs(east):.1f} km)")
    if distance > 30:
        hint += "\n  이름만 같은 다른 지역의 산 자료일 가능성이 큼. 파일 이름의 산 코드 앞 5자리는 시·군·구 코드"
    else:
        hint += "\n  같은 산의 다른 구역 자료일 수 있음 (큰 산은 시·군·구별로 나뉘어 있음)"
    return hint


def add_high_points(nodes: list[Node], edges: list[Edge], elevation: np.ndarray, wanted: int = 2) -> None:
    """
    등산객을 둘 노드(대피 목적지가 아닌 곳)가 wanted 개보다 적으면 (예: 등산로가 한 줄뿐인 산)
    간선 위에서 가장 높은 칸을 노드 "최고점"으로 추가해 간선을 둘로 나눈다. [가정: 등산객은 높은 곳에 있음]
    """
    for _ in range(wanted):
        if sum(1 for n in nodes if n.type not in ("PARKING", "SHELTER")) >= wanted:
            return
        best = None
        for ei, e in enumerate(edges):
            for ci in range(3, len(e.cells) - 3):                 # 양 끝 노드와 너무 가까운 칸 제외
                x, y = e.cells[ci]
                if any((n.x - x) ** 2 + (n.y - y) ** 2 < 15 ** 2 for n in nodes):
                    continue                                       # 기존 노드와 450 m 이상 떨어진 곳만
                if best is None or elevation[y, x] > best[0]:
                    best = (float(elevation[y, x]), ei, ci)
        if best is None:
            return
        _, ei, ci = best
        e = edges.pop(ei)
        x, y = e.cells[ci]
        nodes.append(Node(x, y, "SUMMIT" if not any(n.type == "SUMMIT" for n in nodes) else "POINT",
                          f"최고점{int(round(best[0]))}m", spot=True))
        k = len(nodes) - 1
        edges += [Edge(e.a, k, e.cells[:ci + 1]), Edge(k, e.b, e.cells[ci:])]


def ignition_near_trails(ignition: tuple[int, int], nodes: list[Node], folder: Path) -> tuple[int, int]:
    """
    기본 발화 지점이 등산로에서 3 km(100칸)보다 멀면 대피 상황이 생기지 않으므로,
    등산로 노드 무게중심에서 남서쪽 약 1 km 의 탈 수 있는 칸으로 옮긴다. [가정]
    """
    xs = np.array([n.x for n in nodes])
    ys = np.array([n.y for n in nodes])
    if float(np.min((xs - ignition[0]) ** 2 + (ys - ignition[1]) ** 2)) <= 100 ** 2:
        return ignition
    fuel = read_asc(folder / "fuel.asc")[1]
    target_x, target_y = float(xs.mean()) - 24, float(ys.mean()) + 24
    fy, fx = np.where(np.isin(fuel, (1, 2, 3, 4, 5)))
    k = int(np.argmin((fx - target_x) ** 2 + (fy - target_y) ** 2))
    return int(fx[k]), int(fy[k])


def as_path_list(value) -> list[Path]:
    """파일 하나 또는 여러 개 → 목록"""
    if value is None:
        return []
    return [Path(v) for v in value] if isinstance(value, (list, tuple)) else [Path(value)]


def import_trails(mountain_id: str, lines_path, spots_path=None, crs: str | None = None,
                  encoding: str | None = None, name_field: str | None = None,
                  type_field: str | None = None) -> dict:
    """
    산림청 등산로 SHP → trails.txt, hikers.txt. 반영 결과 요약을 돌려준다.
    lines_path, spots_path 는 파일 하나 또는 여러 개 (큰 산은 시·군·구별로 파일이 나뉘어 있으므로 함께 넣는다)
    """
    line_files, spot_files = as_path_list(lines_path), as_path_list(spots_path)
    mountain = mb.find_mountain(mountain_id)
    folder = mb.mountain_folder(mountain_id)
    center = tuple(mountain["center"])
    elevation = read_asc(folder / "elev.asc")[1]

    lines: list[TrailLine] = []
    for path in line_files:
        found = read_trail_lines(path, center, crs, encoding)
        if not found:
            print(f"[경고] {path.name}: 이 산의 9 km 지도 안에 들어오는 등산로가 없어 건너뜀\n"
                  + data_location_hint(path, mountain, crs, encoding), file=sys.stderr)
        lines.extend(found)
    if not lines:
        raise ValueError("넣은 파일 모두 이 산의 9 km 지도 안에 들어오는 등산로가 없음 (위 경고의 자료 위치 참고)")
    spots = [s for path in spot_files for s in read_spots(path, center, crs, encoding, name_field, type_field)]
    snapped = snap_spots(lines, spots)
    nodes, edges = build_graph(lines, snapped)
    finish_nodes(nodes, edges, elevation, mountain)
    add_high_points(nodes, edges, elevation)
    if not any(n.type in ("PARKING", "SHELTER") for n in nodes):
        raise ValueError("대피 목적지(주차장·대피소·지도 경계)를 하나도 찾지 못함")

    source = "산림청 등산로 " + ", ".join(p.name for p in line_files + spot_files)
    write_trails_file(folder / "trails.txt", nodes, edges, source)
    hikers = write_hikers_file(folder / "hikers.txt", nodes, elevation)
    length_km = sum(len(e.cells) for e in edges) * mb.CELL_SIZE_M / 1000.0

    info = mb.read_info(mountain_id)
    info["ignition"] = list(ignition_near_trails(tuple(info["ignition"]), nodes, folder))
    info["trail_source"] = {"files": [p.name for p in line_files + spot_files], "imported": str(date.today()),
                            "nodes": len(nodes), "edges": len(edges), "length_km": round(length_km, 1),
                            "spots_used": sum(1 for n in nodes if n.spot), "hikers": hikers}
    mb.write_info(mountain_id, info)
    mb.write_scenario(mountain, tuple(info["ignition"]))
    return info["trail_source"]


# ----------------------------------------------------------------------
# 임상도 → 연료 지도
# ----------------------------------------------------------------------
def load_fuel_map(path: Path = FUEL_MAP_FILE) -> tuple[dict[str, int], int]:
    """
    임종 코드 → 연료 코드 표와, 받은 도엽 안인데 다각형이 없는 곳(시가지·농경지 등 산림 밖)의 연료 코드('*')
    키는 '임종코드' 또는 '임종코드/세부이름' (세부이름 = 비고(ETC_PCMTT) 또는 수종(KOFTR_NM), 예: 0/제지)
    """
    mapping, default = {}, mb.FUEL_ROCK
    with open(path, encoding="utf-8") as f:
        for row in csv.reader(line for line in f if not line.lstrip().startswith("#")):
            if len(row) < 2 or row[0].strip() in ("", "frtp_cd"):
                continue
            key, value = row[0].strip(), int(row[1])
            if key == "*":
                default = value
            else:
                mapping[key] = value
    return mapping, default


def normalize_code(value) -> str:
    """'1', 1, 1.0, ' 01' 을 모두 '1' 로"""
    text = str(value).strip()
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def rasterize_polygon(rings: list[np.ndarray]) -> tuple[np.ndarray, int, int] | None:
    """
    다각형(바깥 고리 + 구멍)을 격자에 칠한 마스크. 칸 중심이 다각형 안이면 칠한다.
    짝홀 규칙을 쓰므로 구멍 고리는 자동으로 빠진다. (마스크, 왼쪽 x, 위쪽 y) 또는 지도 밖이면 None
    """
    from PIL import Image, ImageDraw

    allpts = np.vstack(rings)
    x0 = max(int(np.floor(allpts[:, 0].min())), 0)
    y0 = max(int(np.floor(allpts[:, 1].min())), 0)
    x1 = min(int(np.ceil(allpts[:, 0].max())), mb.GRID_SIZE - 1)
    y1 = min(int(np.ceil(allpts[:, 1].max())), mb.GRID_SIZE - 1)
    if x0 > x1 or y0 > y1:
        return None
    width, height = x1 - x0 + 1, y1 - y0 + 1
    mask = np.zeros((height, width), dtype=bool)
    for ring in rings:
        image = Image.new("1", (width, height), 0)
        # PIL 픽셀 i 는 [i, i+1) 영역 → 칸 중심(정수)이 픽셀 가운데에 오도록 0.5 를 더한다
        ImageDraw.Draw(image).polygon([(float(x - x0 + 0.5), float(y - y0 + 0.5)) for x, y in ring], fill=1)
        mask ^= np.asarray(image, dtype=bool)
    return mask, x0, y0


def sheet_number(lat: float, lon: float) -> str:
    """
    위경도가 들어가는 1:5,000 지도(임상도) 도엽 번호 (8자리, 예: 37815068)
      앞 2자리: 위도 정수, 3번째: 경도 정수의 끝자리,
      다음 2자리: 1°×1° 를 4×4 로 나눈 1:50,000 도엽(15′, 북서쪽부터 01~16),
      끝 3자리: 1:50,000 도엽을 10×10 으로 나눈 1:5,000 도엽(1.5′, 북서쪽부터 001~100)
    (받은 도엽 37815068 이 위도 37.075~37.100°, 경도 128.675~128.700° 인 것으로 확인)
    """
    eps = 1e-9
    lat_deg, lon_deg = int(lat), int(lon)
    row50 = min(int((lat_deg + 1 - lat + eps) / 0.25), 3)
    col50 = min(int((lon - lon_deg + eps) / 0.25), 3)
    top, left = lat_deg + 1 - row50 * 0.25, lon_deg + col50 * 0.25
    row5 = min(int((top - lat + eps) / 0.025), 9)
    col5 = min(int((lon - left + eps) / 0.025), 9)
    return f"{lat_deg}{lon_deg % 10}{row50 * 4 + col50 + 1:02d}{row5 * 10 + col5 + 1:03d}"


def sheet_bounds(number: str) -> tuple[float, float, float, float] | None:
    """도엽 번호(8자리) → (남, 북, 서, 동) 위경도. 번호가 아니면 None (sheet_number 의 반대)"""
    if len(number) != 8 or not number.isdigit():
        return None
    lat_deg, last = int(number[:2]), int(number[2])
    lon_deg = 120 + last if last >= 4 else 130 + last        # 한국 경도 124~131°
    n50, n5 = int(number[3:5]), int(number[5:])
    if not (1 <= n50 <= 16 and 1 <= n5 <= 100):
        return None
    north = lat_deg + 1 - ((n50 - 1) // 4) * 0.25 - ((n5 - 1) // 10) * 0.025
    west = lon_deg + ((n50 - 1) % 4) * 0.25 + ((n5 - 1) % 10) * 0.025
    return north - 0.025, north, west, west + 0.025


def sheet_mask(path: Path, center) -> np.ndarray | None:
    """파일 이름이 도엽 번호이면, 그 도엽이 덮는 격자 칸 마스크"""
    bounds = sheet_bounds(path.stem)
    if bounds is None:
        return None
    south, north, west, east = bounds
    lat, lon = mb.grid_cell_latlon(center)
    return (lat >= south) & (lat < north) & (lon >= west) & (lon < east)


def sheets_for_mountain(mountain_id: str) -> list[str]:
    """이 산의 9 km 지도를 모두 덮는 1:5,000 임상도 도엽 번호 목록"""
    mountain = mb.find_mountain(mountain_id)
    lat, lon = mb.grid_cell_latlon(tuple(mountain["center"]))
    picks = list(range(0, mb.GRID_SIZE, 10)) + [mb.GRID_SIZE - 1]
    return sorted({sheet_number(float(lat[y, x]), float(lon[y, x])) for y in picks for x in picks})


def shapefile_overlaps(path: Path, center, crs: str | None, encoding: str | None) -> bool:
    """SHP 전체 범위가 이 산의 9 km 지도와 겹치는가 (빠른 검사)"""
    reader = open_shapefile(path, encoding)
    transformer, _ = make_transformer(path, crs)
    x0, y0, x1, y1 = reader.bbox
    lon, lat = transformer.transform([x0, x1, x0, x1], [y0, y0, y1, y1])
    gx, gy = mb.latlon_to_grid(np.asarray(lat), np.asarray(lon), center)
    return gx.max() >= 0 and gx.min() <= mb.GRID_SIZE - 1 and gy.max() >= 0 and gy.min() <= mb.GRID_SIZE - 1


def paint_forest_file(path: Path, center, fuel: np.ndarray, covered: np.ndarray, mapping: dict[str, int],
                      counts: dict[str, int], unknown: set[str], crs: str | None, encoding: str | None,
                      code_field: str | None) -> str:
    """임상도 SHP 하나의 다각형을 연료 지도에 칠한다. 쓴 필드 이름을 돌려준다."""
    reader = open_shapefile(path, encoding)
    if reader.shapeType not in (5, 15, 25):
        raise ValueError(f"{path.name}: 다각형(POLYGON) 레이어가 아님 ({reader.shapeTypeName})")
    cf = find_field(reader, FOREST_FIELD_HINTS, code_field)
    if cf is None:
        raise ValueError(f"{path.name}: 임종 코드 필드를 찾지 못함. --field 로 지정 (필드: {', '.join(field_names(reader))})")
    transformer, _ = make_transformer(path, crs)
    names = field_names(reader)
    index = names.index(cf)
    detail_index = [names.index(n) for n in ("ETC_PCMTT", "KOFTR_NM") if n in names]   # 비고, 수종
    for shape_rec in reader.shapeRecords():
        code = normalize_code(shape_rec.record[index])
        for i in detail_index:                         # '0/제지' 처럼 세부 이름까지 맞는 줄이 있으면 우선
            detail = str(shape_rec.record[i]).strip()
            if detail and f"{code}/{detail}" in mapping:
                code = f"{code}/{detail}"
                break
        rings = shape_parts_grid(shape_rec.shape, transformer, center)
        result = rasterize_polygon(rings) if rings else None
        if result is None:
            continue
        mask, x0, y0 = result
        if code not in mapping:
            unknown.add(code)
            continue
        region = (slice(y0, y0 + mask.shape[0]), slice(x0, x0 + mask.shape[1]))
        fuel[region][mask] = mapping[code]
        covered[region] |= mask
        counts[code] += int(mask.sum())
    return cf


def import_forest(mountain_id: str, shp_paths, crs: str | None = None, encoding: str | None = None,
                  code_field: str | None = None, fuel_map_path: Path = FUEL_MAP_FILE) -> dict:
    """
    산림청 임상도 SHP(여러 도엽 가능) → fuel.asc. 이 산의 지도와 겹치는 파일만 골라 쓴다.
    임상도가 덮지 않은 곳(받지 않은 도엽)은 [임시] 사면 규칙 연료를 그대로 쓴다.
    """
    mountain = mb.find_mountain(mountain_id)
    folder = mb.mountain_folder(mountain_id)
    center = tuple(mountain["center"])
    files = [p for p in as_path_list(shp_paths) if shapefile_overlaps(p, center, crs, encoding)]
    if not files:
        raise ValueError(f"넣은 임상도 파일 중 {mountain['name']} 지도와 겹치는 것이 없음 "
                         f"(필요한 도엽: forest_import.py sheets --id {mountain_id})")
    mapping, outside_forest = load_fuel_map(fuel_map_path)
    elevation = read_asc(folder / "elev.asc")[1]
    fuel = mb.rule_based_fuel(elevation)                 # 받지 않은 도엽 자리는 [임시] 규칙
    covered = np.zeros(fuel.shape, dtype=bool)
    for path in files:                                   # 받은 도엽 안은 먼저 '산림 밖'으로 칠하고 다각형을 덮는다
        mask = sheet_mask(path, center)
        if mask is not None:
            fuel[mask] = outside_forest
            covered |= mask
    counts: dict[str, int] = defaultdict(int)
    unknown: set[str] = set()
    fields = {paint_forest_file(p, center, fuel, covered, mapping, counts, unknown, crs, encoding, code_field)
              for p in files}
    if not counts:
        raise ValueError("겹치는 파일은 있지만 지도 안에 칠할 임상도 다각형이 없음")
    outside = int(covered.sum()) - int(sum(counts.values()))
    fuel[elevation <= 0.5] = mb.FUEL_WATER               # 바다(고도 0)는 물
    write_asc(folder / "fuel.asc", fuel, mb.CELL_SIZE_M, "{:d}")

    info = mb.read_info(mountain_id)
    info["forest_source"] = {"files": [p.name for p in files], "field": ", ".join(sorted(fields)),
                             "imported": str(date.today()),
                             "covered_pct": round(100.0 * float(covered.mean()), 1),
                             "cells_by_code": dict(sorted(counts.items())), "outside_forest_cells": max(outside, 0),
                             "unknown_codes": sorted(unknown)}
    mb.write_info(mountain_id, info)
    mb.write_scenario(mountain, tuple(info["ignition"]))
    return info["forest_source"]


# ----------------------------------------------------------------------
# 명령줄
# ----------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="산림청 SHP(등산로·임상도) → 시뮬레이션 데이터")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fields = sub.add_parser("fields", help="SHP 의 필드와 예시 값 보기")
    p_fields.add_argument("shp", type=Path)

    p_trails = sub.add_parser("trails", help="등산로 → trails.txt, hikers.txt")
    p_trails.add_argument("--id", required=True, help="산 id (mountains.json)")
    p_trails.add_argument("--lines", required=True, type=Path, nargs="+", help="등산로 선 SHP (여러 개 가능)")
    p_trails.add_argument("--spots", type=Path, nargs="+", help="등산로 지점 SHP (여러 개 가능)")
    p_trails.add_argument("--name-field", help="지점 이름 필드 (자동 찾기 대신)")
    p_trails.add_argument("--type-field", help="지점 종류 필드 (자동 찾기 대신)")

    p_sheets = sub.add_parser("sheets", help="산마다 필요한 1:5,000 임상도 도엽 번호")
    p_sheets.add_argument("--id", help="산 id (생략하면 모든 산)")

    p_forest = sub.add_parser("forest", help="임상도 → fuel.asc")
    p_forest.add_argument("--id", help="산 id (생략하면 파일과 겹치는 모든 산에 반영)")
    p_forest.add_argument("--shp", required=True, type=Path, nargs="+", help="임상도 SHP (도엽 여러 개 가능)")
    p_forest.add_argument("--field", help="임종 코드 필드 (기본: FRTP_CD 자동 찾기)")
    p_forest.add_argument("--fuel-map", type=Path, default=FUEL_MAP_FILE, help="임종 코드 → 연료 코드 표")

    for p in (p_fields, p_trails, p_forest):
        p.add_argument("--encoding", help="글자 인코딩 (기본: cp949 → utf-8 자동)")
    for p in (p_trails, p_forest):
        p.add_argument("--crs", help="좌표계 (.prj 가 없을 때, 예: 5186)")
    args = parser.parse_args()

    try:
        if args.command == "fields":
            print(describe_fields(args.shp, args.encoding))
        elif args.command == "trails":
            r = import_trails(args.id, args.lines, args.spots, args.crs, args.encoding, args.name_field, args.type_field)
            print(f"등산로 반영: 노드 {r['nodes']}개(지점 이름 {r['spots_used']}개), 간선 {r['edges']}개, "
                  f"총 {r['length_km']} km, 등산객 {r['hikers']}팀 → data/mountains/{args.id}/trails.txt")
        elif args.command == "sheets":
            for mid in ([args.id] if args.id else [m["id"] for m in mb.load_registry()]):
                sheets = sheets_for_mountain(mid)
                print(f"{mb.find_mountain(mid)['name']} ({mid}): 도엽 {len(sheets)}장\n  " + " ".join(sheets))
        else:
            ids = [args.id] if args.id else [m["id"] for m in mb.load_registry()]
            applied = 0
            for mid in ids:
                try:
                    r = import_forest(mid, args.shp, args.crs, args.encoding, args.field, args.fuel_map)
                except ValueError as error:
                    if args.id:
                        raise
                    continue                     # 산을 지정하지 않았으면 겹치지 않는 산은 조용히 건너뜀
                applied += 1
                print(f"{mid}: 임상도 반영 — 지도의 {r['covered_pct']}% 를 덮음 (도엽 {len(r['files'])}장), "
                      f"임종 코드별 칸 수 {r['cells_by_code']}"
                      + (f", 표에 없는 코드(건너뜀) {r['unknown_codes']}" if r["unknown_codes"] else "")
                      + ("" if r["covered_pct"] >= 99 else ", 나머지는 [임시] 규칙"))
            if not applied:
                raise ValueError("넣은 임상도 파일과 겹치는 산이 없음 (필요한 도엽: forest_import.py sheets)")
    except (ValueError, KeyError, FileNotFoundError) as error:
        print(f"[오류] {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
