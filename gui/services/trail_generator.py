"""
가상 등산로·등산객 파일 생성기

terrain_generator.py 가 만드는 가상 산(기본 200 x 200 칸)에 맞춘 등산로 그래프와
등산객 목록을 C 엔진이 읽는 텍스트 형식으로 저장한다.

    - <이름>_trails.txt : NODE / EDGE 줄
    - <이름>_hikers.txt : HIKER 줄

다른 크기의 지도를 쓰면 좌표를 비율에 맞춰 바꾼다.
나중에 실제 등산로(산림청 등산로 데이터, OpenStreetMap 등)로 바꿀 때도 같은 형식으로 쓰면 된다.

실행 예:
    python gui/services/trail_generator.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

BASE_SIZE = 200

# (번호, 종류, x, y, 이름)
NODES = [
    (1, "PARKING", 30, 185, "남문주차장"),
    (2, "PARKING", 172, 182, "동문주차장"),
    (3, "JUNCTION", 55, 150, "솔밭삼거리"),
    (4, "SHELTER", 88, 118, "계곡대피소"),
    (5, "JUNCTION", 75, 95, "서쪽능선갈림길"),
    (6, "SUMMIT", 60, 88, "서봉"),
    (7, "SUMMIT", 110, 60, "주봉"),
    (8, "JUNCTION", 135, 55, "동쪽능선"),
    (9, "SHELTER", 150, 85, "동봉대피소"),
    (10, "JUNCTION", 140, 130, "참나무쉼터"),
    (11, "POINT", 95, 80, "전망바위"),
]

# (시작번호, 끝번호, [중간 경유점 (x, y), ...])
EDGES = [
    (1, 3, [(40, 170)]),
    (3, 4, [(70, 135)]),
    (3, 5, [(60, 120)]),
    (6, 3, [(52, 110), (50, 130)]),   # 서봉에서 바로 내려오는 가파른 길
    (5, 6, []),
    (5, 11, [(85, 88)]),
    (4, 11, [(92, 100)]),
    (11, 7, [(100, 70)]),
    (7, 8, [(122, 55)]),
    (8, 9, [(145, 70)]),
    (9, 10, [(148, 110)]),
    (10, 2, [(160, 160)]),
    (4, 10, [(115, 128)]),            # 계곡을 건너는 길 (다리)
]

# (번호, 이름, 현재 노드 번호, 평지 보행 속도 km/h, 인원)
HIKERS = [
    (1, "김씨일행", 7, 3.5, 3),
    (2, "산악회", 6, 3.0, 12),
    (3, "혼자등산", 9, 4.5, 1),
    (4, "가족", 4, 2.5, 4),
    (5, "트레일러너", 8, 6.0, 1),
]


def scale(value: int, size: int) -> int:
    """기준 크기(200) 좌표를 실제 지도 크기에 맞게 바꾼다."""
    return min(size - 1, round(value * size / BASE_SIZE))


def write_trails(path: Path, size: int) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 가상 등산로 그래프 (trail_generator.py 로 생성)\n")
        f.write("# NODE 번호 종류 x y 이름\n")
        f.write("#   종류: JUNCTION 갈림길, SHELTER 대피소, PARKING 주차장, SUMMIT 정상, POINT 기타\n")
        for node_id, kind, x, y, name in NODES:
            f.write(f"NODE {node_id:2d} {kind:<8} {scale(x, size):3d} {scale(y, size):3d} {name}\n")
        f.write("\n# EDGE 시작번호 끝번호 경유점개수 [x1 y1 x2 y2 ...]\n")
        f.write("#   경유점: 길이 꺾이는 중간 지점 (노드 좌표는 자동으로 앞뒤에 붙음)\n")
        for start, end, waypoints in EDGES:
            coords = " ".join(f"{scale(x, size)} {scale(y, size)}" for x, y in waypoints)
            f.write(f"EDGE {start:2d} {end:2d} {len(waypoints)} {coords}".rstrip() + "\n")


def write_hikers(path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 가상 등산객 목록 (trail_generator.py 로 생성)\n")
        f.write("# HIKER 번호 이름(공백 없이) 현재노드번호 평지보행속도(km/h) 인원\n")
        f.write("#   보행 속도 3~4 km/h 는 일반 성인 평지 보행 속도 [근거: 일반 통계], 산행 속도는 엔진이 경사로 보정\n")
        for hiker_id, name, node_id, speed, people in HIKERS:
            f.write(f"HIKER {hiker_id} {name} {node_id} {speed:.1f} {people}\n")


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="가상 등산로·등산객 파일 생성기")
    parser.add_argument("--size", type=int, default=200, help="지도 격자 크기 (기본 200)")
    parser.add_argument("--name", default="virtual", help="파일 이름 앞부분")
    parser.add_argument("--out", type=Path, default=project_root / "data" / "trails", help="저장 폴더")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    trails_path = args.out / f"{args.name}_trails.txt"
    hikers_path = args.out / f"{args.name}_hikers.txt"
    write_trails(trails_path, args.size)
    write_hikers(hikers_path)
    print(f"저장 완료: {trails_path}")
    print(f"저장 완료: {hikers_path}")


if __name__ == "__main__":
    main()
