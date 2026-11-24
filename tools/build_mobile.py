"""
휴대폰 앱(mobile/)용 자료 만들기

    python tools/build_mobile.py

산 6곳마다 mobile/assets/<산 id>/ 에
  - terrain_none.png, terrain_spring.png … terrain_winter.png : 계절별 바탕 지도 (GUI 와 같은 색, season_render)
  - meta.json : 이름, 지도 가운데 위경도, 칸 크기, 정상 위치, 겨울 눈 경계, 일출·일몰 계산용 위치
를 만들고, mobile/assets/mountains.json 에 목록을 쓴다.

지형(elev.asc)·연료(fuel.asc)·등산로(trails.txt)·시나리오(.ini)는 저장소의 data/ 파일을 앱이 그대로 읽는다.
(GitHub Pages 로 저장소 전체를 올리므로 같은 파일을 두 번 두지 않는다)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gui"))

from services import map_render, mountain_builder  # noqa: E402
from services.result_loader import read_asc  # noqa: E402

OUT = ROOT / "mobile" / "assets"
SEASONS = ("none", "spring", "summer", "autumn", "winter")


def build_one(mountain: dict) -> dict:
    mid = mountain["id"]
    folder = mountain_builder.mountain_folder(mid)
    elevation = read_asc(folder / "elev.asc")[1]
    fuel = read_asc(folder / "fuel.asc")[1].astype(int)
    spec = mountain_builder.grid_spec(mountain)
    snow_line = float(mountain.get("winter_snow_line_m", 600))
    out = OUT / mid
    out.mkdir(parents=True, exist_ok=True)
    for season in SEASONS:
        image = map_render.terrain_image(elevation, fuel, mountain_builder.CELL_SIZE_M,
                                         season=None if season == "none" else season,
                                         snow_line_m=snow_line if season == "winter" else 0.0)
        Image.fromarray(image).save(out / f"terrain_{season}.png", optimize=True)
    sx, sy = mountain_builder.summit_grid(mountain)
    summit = mountain.get("summit") or mountain["center"]
    meta = {
        "id": mid,
        "name": mountain_builder.display_name(mountain),
        "peak": mountain["peak"],
        "center": [spec[0], spec[1]],
        "width": spec.width,
        "height": spec.height,
        "cell_m": mountain_builder.CELL_SIZE_M,
        "earth_radius_m": mountain_builder.EARTH_RADIUS_M,
        "summit_latlon": list(summit),
        "summit_cell": [sx, sy],
        "winter_snow_line_m": snow_line,
        "elevation_range_m": [float(np.min(elevation)), float(np.max(elevation))],
        "files": {
            "elevation": f"../data/mountains/{mid}/elev.asc",
            "fuel": f"../data/mountains/{mid}/fuel.asc",
            "trails": f"../data/mountains/{mid}/trails.txt",
            "scenario": f"../data/scenarios/mountain_{mid}.ini",
        },
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": mid, "name": meta["name"], "center": meta["center"]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    items = [build_one(m) for m in mountain_builder.load_registry()]
    (OUT / "mountains.json").write_text(json.dumps({"mountains": items}, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"[완료] 산 {len(items)}곳, mobile/assets {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
