"""
시험용 산림청 형식 SHP 만들기 (forest_import.py 검증용)

진짜 산림청 자료와 같은 좌표계(EPSG:5186, GRS80 중부원점)·인코딩(cp949)·필드 이름으로
가짜 등산로(선 + 지점)와 임상도(다각형, 구멍 포함)를 만든다. 진짜 자료가 아니므로 결과를 실제 산으로 믿으면 안 된다.

    python tools/make_test_shp.py --id bukhansan --out 폴더
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gui"))

import shapefile  # noqa: E402
from pyproj import CRS, Transformer  # noqa: E402

from services import mountain_builder as mb  # noqa: E402

TARGET_CRS = CRS.from_epsg(5186)


def make_projector(center):
    """정상 기준 (동쪽 m, 북쪽 m) → EPSG:5186 좌표"""
    to_tm = Transformer.from_crs("EPSG:4326", TARGET_CRS, always_xy=True)
    lat0, lon0 = center

    def project(east: float, north: float) -> tuple[float, float]:
        lat = lat0 + math.degrees(north / mb.EARTH_RADIUS_M)
        lon = lon0 + math.degrees(east / (mb.EARTH_RADIUS_M * math.cos(math.radians(lat0))))
        return to_tm.transform(lon, lat)
    return project


def write_prj(path: Path) -> None:
    path.with_suffix(".prj").write_text(TARGET_CRS.to_wkt(version="WKT1_ESRI"), encoding="utf-8")


def make_trails(out: Path, project) -> None:
    # 정상(0,0)에서 사방으로 내려가는 등산로 + 능선 연결 + 지도 밖(동쪽 6 km)으로 나가는 길
    routes = {
        "남쪽코스": [(0, 0), (-300, -900), (-200, -2000), (-600, -3400)],
        "서쪽코스": [(0, 0), (-1000, 200), (-2200, 100), (-3600, -300)],
        "북쪽코스": [(0, 0), (300, 1200), (800, 2600)],
        "동쪽능선": [(0, 0), (1200, -300), (2500, -200), (6000, 100)],
        "중턱연결": [(-200, -2000), (-1100, -1500), (-2200, 100)],
    }
    writer = shapefile.Writer(str(out / "test_trails"), shapeType=shapefile.POLYLINE, encoding="cp949")
    writer.field("PMNTN_NM", "C", 40)
    for name, points in routes.items():
        writer.line([[project(e, n) for e, n in points]])
        writer.record(name)
    writer.close()
    write_prj(out / "test_trails.shp")

    spots = [((0, 0), "정상", "백운대"), ((-600, -3400), "시종점", "남쪽탐방지원센터"),
             ((-1100, -1500), "대피소", "중턱대피소"), ((-3600, -300), "시종점", "서쪽주차장"),
             ((1200, -300), "갈림길", "동쪽갈림길"), ((-1050, 1700), "쉼터", "길에서먼쉼터")]
    writer = shapefile.Writer(str(out / "test_spots"), shapeType=shapefile.POINT, encoding="cp949")
    writer.field("MANAGE_SP2", "C", 20)
    writer.field("DETAIL_SPO", "C", 40)
    for (e, n), kind, name in spots:
        writer.point(*project(e, n))
        writer.record(kind, name)
    writer.close()
    write_prj(out / "test_spots.shp")


def make_forest(out: Path, project) -> None:
    # 사분면 4개: 북동 침엽수(1), 북서 활엽수(2), 남서 혼효림(3, 가운데 무립목지 구멍), 남동 죽림(4)
    # 남동쪽 바깥 띠는 다각형 없음 → 비산림
    half = 4000
    quads = [
        ("1", [(0, 0), (0, half), (half, half), (half, 0)]),
        ("2", [(0, 0), (-half, 0), (-half, half), (0, half)]),
        ("3", [(0, 0), (0, -half), (-half, -half), (-half, 0)]),
        ("4", [(0, 0), (half, 0), (half, -2000), (0, -2000)]),
    ]
    hole = [(-1500, -1500), (-2500, -1500), (-2500, -2500), (-1500, -2500)]
    writer = shapefile.Writer(str(out / "test_forest"), shapeType=shapefile.POLYGON, encoding="cp949")
    writer.field("FRTP_CD", "C", 2)
    writer.field("KOFTR_GROU", "C", 10)
    for code, ring in quads:
        rings = [[project(e, n) for e, n in ring + ring[:1]]]
        if code == "3":
            rings.append([project(e, n) for e, n in hole[::-1] + hole[-1:]])
        writer.poly(rings)
        writer.record(code, "시험")
    writer.poly([[project(e, n) for e, n in hole + hole[:1]]])
    writer.record("0", "무립목")
    writer.close()
    write_prj(out / "test_forest.shp")


def main() -> None:
    parser = argparse.ArgumentParser(description="시험용 산림청 형식 SHP 만들기")
    parser.add_argument("--id", default="bukhansan")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    project = make_projector(tuple(mb.find_mountain(args.id)["center"]))
    make_trails(args.out, project)
    make_forest(args.out, project)
    print(f"시험용 SHP → {args.out}")


if __name__ == "__main__":
    main()
