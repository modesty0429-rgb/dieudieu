"""
OpenStreetMap 등산로 받기 (Overture Maps 경유)

산림청 등산로에 없는 길(예: 국립공원 안쪽의 한라산 정상 탐방로)을 OpenStreetMap(OSM)에서 가져온다.
OSM 서버에 직접 접속하는 대신, OSM 자료를 정리해 AWS 에 공개하는 Overture Maps 의 교통(transportation) 자료를 읽는다.

    Overture Maps Foundation, transportation/segment (출처: OpenStreetMap, 라이선스 ODbL 1.0)
    s3://overturemaps-us-west-2/release/<버전>/theme=transportation/type=segment/

  - 등산로로 쓰는 길 종류: path(오솔길), footway(보행로), steps(계단), track(임도)
  - 이름에 '비법정'이 들어간 길(출입 금지 탐방로)은 뺀다
  - 산의 9 km 지도 범위만 받아 SHP(위경도, EPSG:4326)로 저장 → forest_import.py trails 로 변환

실행 예 (저장소 폴더에서, 인터넷 필요, 약 1~2분):
    python gui/services/overture_trails.py --id hallasan
    python gui/services/forest_import.py trails --id hallasan --lines data/raw/한라산/osm_trails.shp

필요한 라이브러리 (이 도구를 쓸 때만): pyarrow, pyshp
OSM 자료를 쓰면 화면·문서에 "© OpenStreetMap contributors" 를 표시해야 한다 (ODbL).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # gui 폴더 (직접 실행할 때)

from services import app_config  # noqa: E402
from services import mountain_builder as mb  # noqa: E402

BUCKET = "overturemaps-us-west-2"
REGION = "us-west-2"
TRAIL_CLASSES = ("path", "footway", "steps", "track")
EXCLUDE_NAME_WORDS = ("비법정",)
ATTRIBUTION = "© OpenStreetMap contributors (ODbL 1.0), Overture Maps Foundation"


def s3_filesystem():
    """익명 S3 접속 (AWS 계정 필요 없음). 프록시·인증서 설정이 있으면 따른다."""
    import pyarrow.fs as pafs

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    return pafs.S3FileSystem(anonymous=True, region=REGION, proxy_options=proxy or None)


def latest_release(s3) -> str:
    """가장 최근 Overture 배포 버전 (예: 2026-11-18.0)"""
    import pyarrow.fs as pafs

    infos = s3.get_file_info(pafs.FileSelector(f"{BUCKET}/release/"))
    versions = sorted(i.base_name for i in infos if i.type == pafs.FileType.Directory)
    if not versions:
        raise RuntimeError("Overture 배포 버전을 찾지 못함")
    return versions[-1]


def map_bounds(mountain: dict, margin_deg: float = 0.005) -> tuple[float, float, float, float]:
    """산 지도의 (서, 동, 남, 북) 경계 + 약간의 여유"""
    lat, lon = mb.grid_cell_latlon(mb.grid_spec(mountain))
    return (float(lon.min()) - margin_deg, float(lon.max()) + margin_deg,
            float(lat.min()) - margin_deg, float(lat.max()) + margin_deg)


def overlapping_row_groups(s3, files: list[str], bounds) -> list[tuple[str, int]]:
    """
    파일마다 끝부분(메타데이터)만 읽어, 경계 상자 통계가 지도와 겹치는 묶음(row group)만 고른다.
    Overture 파일은 위치 순서로 정렬돼 있어 전체(수십 GB)를 받지 않고 몇 MB 만 읽으면 된다.
    """
    import pyarrow.parquet as pq

    west, east, south, north = bounds
    hits = []
    for path in files:
        meta = pq.ParquetFile(s3.open_input_file(path)).metadata
        names = [meta.schema.column(i).path for i in range(meta.num_columns)]
        index = {k: names.index(f"bbox.{k}") for k in ("xmin", "xmax", "ymin", "ymax")}
        for g in range(meta.num_row_groups):
            stats = {k: meta.row_group(g).column(i).statistics for k, i in index.items()}
            if (stats["xmin"].min <= east and stats["xmax"].max >= west
                    and stats["ymin"].min <= north and stats["ymax"].max >= south):
                hits.append((path, g))
    return hits


def fetch_segments(mountain: dict, release: str | None = None, log=print) -> tuple[list[dict], str]:
    """지도 범위의 교통 구간(segment) 목록과 사용한 배포 버전"""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.fs as pafs
    import pyarrow.parquet as pq

    s3 = s3_filesystem()
    release = release or latest_release(s3)
    base = f"{BUCKET}/release/{release}/theme=transportation/type=segment/"
    files = [i.path for i in s3.get_file_info(pafs.FileSelector(base)) if i.path.endswith(".parquet")]
    bounds = map_bounds(mountain)
    log(f"Overture {release}: 파일 {len(files)}개의 목차를 읽는 중 (약 1분)")
    hits = overlapping_row_groups(s3, files, bounds)
    west, east, south, north = bounds
    tables = []
    for path, group in hits:
        table = pq.ParquetFile(s3.open_input_file(path)).read_row_group(
            group, columns=["id", "subtype", "class", "names", "bbox", "geometry"])
        box = table.column("bbox")
        inside = pc.and_(
            pc.and_(pc.less_equal(pc.struct_field(box, "xmin"), east), pc.greater_equal(pc.struct_field(box, "xmax"), west)),
            pc.and_(pc.less_equal(pc.struct_field(box, "ymin"), north), pc.greater_equal(pc.struct_field(box, "ymax"), south)))
        tables.append(table.filter(inside))
    rows = pa.concat_tables(tables).to_pylist() if tables else []
    return rows, release


def is_trail(row: dict) -> bool:
    if row.get("subtype") != "road" or row.get("class") not in TRAIL_CLASSES:
        return False
    name = (row.get("names") or {}).get("primary") or ""
    return not any(word in name for word in EXCLUDE_NAME_WORDS)


def wkb_lines(data: bytes) -> list[list[tuple[float, float]]]:
    """
    WKB(도형을 바이트로 적는 표준 형식)에서 선 좌표 목록을 읽는다. LineString, MultiLineString 만 다룬다.
    구조: [바이트 순서 1][종류 4][점 개수 4][x y 8바이트씩 ...]
    """
    import struct

    def read_line(offset: int) -> tuple[list[tuple[float, float]], int]:
        order = "<" if data[offset] == 1 else ">"
        kind, = struct.unpack_from(order + "I", data, offset + 1)
        dims = 3 if kind in (1002, 0x80000002) else 2                  # Z 값이 있으면 3개씩
        count, = struct.unpack_from(order + "I", data, offset + 5)
        values = struct.unpack_from(order + "d" * (count * dims), data, offset + 9)
        points = [(values[i], values[i + 1]) for i in range(0, len(values), dims)]
        return points, offset + 9 + 8 * count * dims

    order = "<" if data[0] == 1 else ">"
    kind, = struct.unpack_from(order + "I", data, 1)
    if kind % 1000 == 2:
        return [read_line(0)[0]]
    if kind % 1000 == 5:
        count, = struct.unpack_from(order + "I", data, 5)
        lines, offset = [], 9
        for _ in range(count):
            line, offset = read_line(offset)
            lines.append(line)
        return lines
    return []


def write_trail_shapefile(rows: list[dict], path: Path, release: str) -> int:
    """등산로 구간을 선 SHP(위경도)로 저장. 저장한 개수"""
    import shapefile

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = shapefile.Writer(str(path.with_suffix("")), shapeType=shapefile.POLYLINE, encoding="utf-8")
    writer.field("OSM_CLASS", "C", 12)
    writer.field("PMNTN_NM", "C", 80)
    count = 0
    for row in rows:
        if not is_trail(row):
            continue
        parts = [part for part in wkb_lines(row["geometry"]) if len(part) >= 2]
        if not parts:
            continue
        writer.line(parts)
        writer.record(row["class"], ((row.get("names") or {}).get("primary") or "")[:80])
        count += 1
    writer.close()
    path.with_suffix(".prj").write_text(
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]', encoding="utf-8")
    path.with_suffix(".txt").write_text(f"{ATTRIBUTION}\nOverture 배포 {release}, 길 종류 {', '.join(TRAIL_CLASSES)}\n",
                                        encoding="utf-8")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenStreetMap 등산로 받기 (Overture Maps, 인터넷 필요)")
    parser.add_argument("--id", required=True, help="산 id (mountains.json)")
    parser.add_argument("--release", help="Overture 배포 버전 (기본: 가장 최근)")
    parser.add_argument("--out", type=Path, help="저장할 SHP (기본: data/raw/<산 이름>/osm_trails.shp)")
    args = parser.parse_args()
    mountain = mb.find_mountain(args.id)
    out = args.out or app_config.DATA_DIR / "raw" / mountain["name"].split("(")[0] / "osm_trails.shp"
    rows, release = fetch_segments(mountain, args.release)
    count = write_trail_shapefile(rows, out, release)
    print(f"OSM 등산로 {count}개 구간 저장 → {out}  ({ATTRIBUTION})")
    print(f"다음: python gui/services/forest_import.py trails --id {args.id} --lines {out}")


if __name__ == "__main__":
    main()
