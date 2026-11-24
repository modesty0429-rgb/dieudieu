"""
휴대폰 앱으로 보낼 "발화 정보" 링크 만들기 (11단계)

PC 프로그램이 관제 역할을 한다: 발화 지점(지도 칸) → 위경도, 발화 시각, 바람·습도·기온을
짧은 링크 하나로 만들어 문자·카카오톡·QR 로 보낸다. 형식은 mobile/js/fireinfo.js 와 같다.
    https://…/mobile/#m=bukhansan&fire=37.64512,126.96001&t=2026-04-05T13:00&w=6,270,25,18

기상청 API 인증키는 PC(config/api_keys.ini)에만 있다. 휴대폰 앱에는 키가 없고, 날씨는 이 링크의 숫자로만 받는다.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from services import mountain_builder
from services.weather_api import WeatherRow, read_weather_csv

# GitHub Pages 주소 (저장소 Settings → Pages 에서 켠 뒤). 다른 곳에 올렸으면 환경 변수로 바꿀 수 있다.
MOBILE_APP_URL = os.environ.get("DIEUDIEU_MOBILE_URL", "https://modesty0429-rgb.github.io/dieudieu/mobile/")


@dataclass
class FireMessage:
    mountain: str
    lat: float
    lon: float
    time: datetime
    weather: tuple[float, float, float, float] | None = None    # 풍속, 풍향, 습도, 기온

    def query(self) -> str:
        parts = [f"m={self.mountain}", f"fire={self.lat:.5f},{self.lon:.5f}", f"t={self.time:%Y-%m-%dT%H:%M}"]
        if self.weather is not None:
            parts.append("w=" + ",".join(f"{v:g}" for v in self.weather))
        return "&".join(parts)

    def link(self, base: str = MOBILE_APP_URL) -> str:
        return f"{base}#{self.query()}"

    def sms_text(self, base: str = MOBILE_APP_URL) -> str:
        return f"[산불 대피 안내] {self.time:%H:%M} 발화. 링크를 누르면 휴대폰이 대피 경로를 계산합니다: {self.link(base)}"


def cell_to_latlon(mountain: dict, x: float, y: float) -> tuple[float, float]:
    """지도 칸 → 위경도 (mountain_builder.latlon_to_grid 의 반대)"""
    spec = mountain_builder.grid_spec(mountain)
    lat0, lon0 = spec[0], spec[1]
    east = (x - (spec.width - 1) / 2.0) * mountain_builder.CELL_SIZE_M
    north = -(y - (spec.height - 1) / 2.0) * mountain_builder.CELL_SIZE_M
    lat = lat0 + math.degrees(north / mountain_builder.EARTH_RADIUS_M)
    lon = lon0 + math.degrees(east / (mountain_builder.EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    return lat, lon


def weather_at(path: Path, when: datetime) -> tuple[float, float, float, float] | None:
    """기상 CSV 에서 when 에 가장 가까운 시각의 값 (풍속, 풍향, 습도, 기온)"""
    try:
        rows: list[WeatherRow] = read_weather_csv(path)
    except (OSError, ValueError):
        return None
    if not rows:
        return None
    r = min(rows, key=lambda row: abs((row.time - when).total_seconds()))
    return (round(r.wind_speed_ms, 1), round(r.wind_dir_deg), round(r.rh_pct), round(r.temp_c, 1))


def build_message(scenario_path: Path, x: int, y: int, when: datetime,
                  weather: tuple[float, float, float, float] | None) -> FireMessage:
    mid = mountain_builder.scenario_mountain_id(scenario_path)
    if mid is None:
        raise ValueError("실제 산 시나리오에서만 휴대폰으로 보낼 수 있습니다 (가상 산은 위경도가 없음)")
    lat, lon = cell_to_latlon(mountain_builder.find_mountain(mid), x, y)
    return FireMessage(mid, lat, lon, when, weather)
