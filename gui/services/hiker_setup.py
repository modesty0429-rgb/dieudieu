"""
등산객 팀 설정 (10단계)

GUI에서 등산객 팀 수(1~10)와 팀마다 이름·인원·걷는 속도·위치를 바꿀 수 있게 한다.
Qt와 상관없는 순수 계산만 모았다.

위치는 두 가지로 정할 수 있다.
  1) 등산로 노드(정상·갈림길·대피소 등) 하나를 고른다.
  2) 지도에서 등산로 위 아무 곳이나 찍는다.
     → 가장 가까운 등산로 위 점으로 옮기고(snap), 그 자리에서 등산로(간선)를 둘로 나눠
       새 노드(POINT)를 만든다. C 엔진은 노드에서 출발하는 등산객만 알기 때문에,
       이렇게 나눈 등산로 파일과 등산객 파일을 새로 써서 엔진에 넘긴다.
       (C 엔진은 파일만 바뀔 뿐 그대로 동작한다: 간선 경로·길이·오르막은 엔진이 다시 계산)

파일 형식은 C 엔진(trail_io.c)과 같다.
    NODE 번호 종류 x y 이름
    EDGE 시작번호 끝번호 경유점개수 [x1 y1 ...]
    HIKER 번호 이름 노드번호 보행속도(km/h) 인원
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from pathlib import Path

from services.result_loader import Hiker, TrailEdge, TrailNode

MAX_TEAMS = 10
MIN_TEAMS = 1
SNAP_NODE_CELLS = 2.0        # 찍은 곳이 노드에서 이 거리(칸) 안이면 노드로 본다
MAX_SNAP_CELLS = 12.0        # 등산로에서 이보다 멀리 찍으면 무시 (360 m)
NEW_NODE_START_ID = 100      # 나눠서 생긴 노드 번호는 100부터
NAME_MAX_CHARS = 10          # C 엔진 이름 칸(64바이트)에 한글 10자는 여유 있게 들어감

DEFAULT_SPEED_KMH = 3.5      # [근거] 일반 성인 평지 보행 속도 3~4 km/h
DEFAULT_PEOPLE = 3
EXTRA_TEAM_NAMES = ("동호회", "커플", "대학산악부", "외국인관광객", "어르신모임",
                    "직장동료", "사진동호회", "등산학교", "부부", "친구들")


@dataclass
class TeamSpec:
    """GUI에서 정한 등산객 한 팀"""
    name: str
    people: int
    speed_kmh: float
    node_id: int | None        # 노드에 있으면 그 번호, 지도에서 찍은 곳이면 None
    x: int                     # 위치 (칸)
    y: int

    def position_text(self, nodes: list[TrailNode]) -> str:
        if self.node_id is not None:
            node = next((n for n in nodes if n.id == self.node_id), None)
            return node.name if node else f"노드 {self.node_id}"
        return f"📍 찍은 곳 ({self.x},{self.y})"


def clean_name(text: str, fallback: str) -> str:
    """파일에 쓸 수 있는 이름 (공백·# 없이, 최대 10자)"""
    name = re.sub(r"[\s#]+", "_", text.strip()).strip("_")
    return (name or fallback)[:NAME_MAX_CHARS]


# ----------------------------------------------------------------------
# 처음 값
# ----------------------------------------------------------------------
def teams_from_hikers(hikers: list[Hiker], nodes: list[TrailNode]) -> list[TeamSpec]:
    """시나리오 파일의 등산객을 팀 설정으로 바꾼다."""
    by_id = {n.id: n for n in nodes}
    teams = []
    for h in hikers:
        node = by_id.get(h.node_id)
        if node is not None:
            teams.append(TeamSpec(h.name, h.people, h.speed_kmh, node.id, node.x, node.y))
    return teams


def start_nodes(nodes: list[TrailNode]) -> list[TrailNode]:
    """새 팀을 둘 기본 위치 후보: 정상 → 갈림길·기타 (대피소·주차장은 이미 안전하므로 뒤로)"""
    order = {"SUMMIT": 0, "POINT": 1, "JUNCTION": 2, "SHELTER": 3, "PARKING": 4}
    return sorted(nodes, key=lambda n: (order.get(n.kind, 5), n.id))


def new_team(index: int, teams: list[TeamSpec], nodes: list[TrailNode]) -> TeamSpec:
    """팀을 늘릴 때 붙는 새 팀: 아직 팀이 가장 적은 노드(정상·갈림길 우선)에 둔다."""
    used = {n.id: 0 for n in nodes}
    for t in teams:
        if t.node_id in used:
            used[t.node_id] += 1
    candidates = [n for n in start_nodes(nodes) if n.kind not in ("SHELTER", "PARKING")] or nodes
    node = min(candidates, key=lambda n: used.get(n.id, 0))
    taken = {t.name for t in teams}
    name = next((n for n in EXTRA_TEAM_NAMES if n not in taken), f"팀{index + 1}")
    return TeamSpec(name, DEFAULT_PEOPLE, DEFAULT_SPEED_KMH, node.id, node.x, node.y)


def resize_teams(teams: list[TeamSpec], count: int, nodes: list[TrailNode]) -> list[TeamSpec]:
    """팀 수를 count(1~10)로 맞춘다. 줄이면 뒤에서부터 빼고, 늘리면 new_team 을 붙인다."""
    count = max(MIN_TEAMS, min(MAX_TEAMS, count))
    out = list(teams[:count])
    while len(out) < count:
        out.append(new_team(len(out), out, nodes))
    return out


# ----------------------------------------------------------------------
# 등산로 위 가장 가까운 점
# ----------------------------------------------------------------------
@dataclass
class SnapResult:
    x: int
    y: int
    distance: float            # 찍은 곳에서 등산로까지 거리 (칸)
    node_id: int | None        # 노드 근처면 그 노드
    edge_index: int = -1       # 노드가 아니면 어느 간선 위인지
    segment: int = -1          # 간선의 몇 번째 조각(points[i] → points[i+1]) 위인지


def _project(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> tuple[float, float, float]:
    """점 P 를 선분 AB 에 수직으로 내린 점과 그 거리"""
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    qx, qy = ax + t * dx, ay + t * dy
    return qx, qy, math.hypot(px - qx, py - qy)


def snap_to_trail(nodes: list[TrailNode], edges: list[TrailEdge], x: float, y: float) -> SnapResult | None:
    """(x, y) 에서 가장 가까운 등산로 위 점. 너무 멀면 None."""
    best: SnapResult | None = None
    for node in nodes:
        d = math.hypot(node.x - x, node.y - y)
        if d <= SNAP_NODE_CELLS and (best is None or d < best.distance):
            best = SnapResult(node.x, node.y, d, node.id)
    if best is not None:
        return best
    for ei, edge in enumerate(edges):
        for si in range(len(edge.points) - 1):
            (ax, ay), (bx, by) = edge.points[si], edge.points[si + 1]
            qx, qy, d = _project(x, y, ax, ay, bx, by)
            if best is None or d < best.distance:
                best = SnapResult(int(round(qx)), int(round(qy)), d, None, ei, si)
    if best is None or best.distance > MAX_SNAP_CELLS:
        return None
    # 반올림한 점이 노드와 겹치거나 아주 가까우면 노드로
    for node in nodes:
        if math.hypot(node.x - best.x, node.y - best.y) <= SNAP_NODE_CELLS:
            return SnapResult(node.x, node.y, best.distance, node.id)
    return best


# ----------------------------------------------------------------------
# 등산로 나누기 + 파일 쓰기
# ----------------------------------------------------------------------
def _dedupe(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for p in points:
        if not out or out[-1] != p:
            out.append(p)
    return out


def split_edge(nodes: list[TrailNode], edges: list[TrailEdge], snap: SnapResult,
               new_id: int, name: str) -> tuple[list[TrailNode], list[TrailEdge], int]:
    """snap 위치에서 간선을 둘로 나누고 새 노드(POINT)를 만든다. → (노드, 간선, 새 노드 번호)"""
    edge = edges[snap.edge_index]
    point = (snap.x, snap.y)
    before = edge.points[:snap.segment + 1]
    after = edge.points[snap.segment + 1:]
    # 나누는 점 바로 옆(1칸 안)의 경유점은 빼서 길이 꺾이지 않게 (노드 자체는 남김)
    if len(before) > 1 and math.dist(before[-1], point) <= 1.5:
        before = before[:-1]
    if len(after) > 1 and math.dist(after[0], point) <= 1.5:
        after = after[1:]
    first = _dedupe(before + [point])
    second = _dedupe([point] + after)
    node = TrailNode(new_id, "POINT", snap.x, snap.y, name)
    new_edges = edges[:snap.edge_index] + [TrailEdge(edge.start_id, new_id, first),
                                           TrailEdge(new_id, edge.end_id, second)] + edges[snap.edge_index + 1:]
    return nodes + [node], new_edges, new_id


def build_layout(nodes: list[TrailNode], edges: list[TrailEdge],
                 teams: list[TeamSpec]) -> tuple[list[TrailNode], list[TrailEdge], list[Hiker]]:
    """
    팀 설정으로 엔진에 넘길 등산로·등산객을 만든다.
    지도에서 찍은 팀은 그 자리에서 등산로를 나눠 새 노드에 둔다. (같은 자리의 팀은 같은 노드를 씀)
    """
    nodes, edges = list(nodes), list(edges)
    next_id = max([NEW_NODE_START_ID - 1] + [n.id for n in nodes]) + 1
    hikers: list[Hiker] = []
    for i, team in enumerate(teams, start=1):
        node_id = team.node_id
        if node_id is None:
            snap = snap_to_trail(nodes, edges, team.x, team.y)
            if snap is None:
                raise ValueError(f"{team.name} 팀 위치 ({team.x}, {team.y}) 가 등산로에서 너무 멂")
            if snap.node_id is not None:
                node_id = snap.node_id
            else:
                nodes, edges, node_id = split_edge(nodes, edges, snap, next_id, f"{clean_name(team.name, f'팀{i}')}_위치")
                next_id += 1
        hikers.append(Hiker(i, clean_name(team.name, f"팀{i}"), node_id,
                            round(float(team.speed_kmh), 1), int(team.people)))
    return nodes, edges, hikers


def write_trail_file(path: Path, nodes: list[TrailNode], edges: list[TrailEdge]) -> None:
    lines = ["# GUI가 등산객 팀 위치에 맞춰 자동 생성한 등산로 (지도에서 찍은 곳은 등산로를 나눠 POINT 노드를 만듦)",
             "# NODE 번호 종류 x y 이름"]
    lines += [f"NODE {n.id:3d} {n.kind:<9} {n.x:3d} {n.y:3d} {n.name}" for n in nodes]
    lines += ["", "# EDGE 시작번호 끝번호 경유점개수 [x1 y1 x2 y2 ...]"]
    for e in edges:
        waypoints = e.points[1:-1]
        coords = " ".join(f"{x} {y}" for x, y in waypoints)
        lines.append(f"EDGE {e.start_id:3d} {e.end_id:3d} {len(waypoints)} {coords}".rstrip())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_hiker_file(path: Path, hikers: list[Hiker]) -> None:
    lines = ["# GUI가 만든 등산객 팀 목록 (팀 수·이름·인원·속도·위치)",
             "# HIKER 번호 이름 노드번호 평지보행속도(km/h) 인원"]
    lines += [f"HIKER {h.id} {h.name} {h.node_id} {h.speed_kmh:.1f} {h.people}" for h in hikers]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_team(team: TeamSpec, **changes) -> TeamSpec:
    return replace(team, **changes)
