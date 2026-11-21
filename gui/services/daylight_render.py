"""
낮/밤 화면 표현 (8단계)

Qt와 상관없는 순수 계산만 모았다. (map_render.py 와 같은 방식)

    sun_phase()       : 태양 고도 → 낮 / 노을 / 박명 / 밤 이름과 아이콘
    night_tint()      : 지도 전체에 덮을 어둠(+노을) 색 RGBA
    fire_glow()       : 어두울 때 불 주변이 환하게 번져 보이는 빛 레이어 RGBA
    night_spans()     : 시뮬레이션 기간 중 해가 진 구간 목록 (그래프 음영용)

C 엔진이 계산한 태양 고도·밝기(stats.csv)와 일몰·일출 시각(summary.json)을 쓴다.
"""

from __future__ import annotations

import numpy as np

SUN_HORIZON_DEG = -0.833      # C 엔진 daylight.h 와 같은 값 (일출·일몰 기준)
CIVIL_TWILIGHT_DEG = -6.0     # 시민박명 끝 (이보다 낮으면 밤)

NIGHT_COLOR = np.array((8, 14, 46), dtype=np.float64)       # 밤하늘 남색
SUNSET_COLOR = np.array((255, 115, 40), dtype=np.float64)   # 노을 주황
GLOW_COLOR = (255, 150, 50)                                 # 불빛
MAX_NIGHT_ALPHA = 175                                       # 한밤중 어둠의 진하기 (0~255)


def sun_phase(elevation_deg: float) -> tuple[str, str, str]:
    """태양 고도 → (키, 한국어 이름, 아이콘)"""
    if elevation_deg > 6.0:
        return "day", "낮", "☀"
    if elevation_deg > SUN_HORIZON_DEG:
        return "golden", "해 질 녘", "🌅"
    if elevation_deg > CIVIL_TWILIGHT_DEG:
        return "twilight", "박명", "🌆"
    return "night", "밤", "🌙"


def night_tint(level: float, elevation_deg: float) -> tuple[int, int, int, int]:
    """
    지도 위에 덮을 반투명 색 하나 (R, G, B, A).
      level 1(낮) → 투명,  level 0(밤) → 진한 남색
      해가 지평선 근처(+6° ~ −4°)이면 주황 노을빛을 섞는다.
    """
    darkness = float(np.clip(1.0 - level, 0.0, 1.0))
    warm = float(np.clip(1.0 - abs(elevation_deg - 1.0) / 5.0, 0.0, 1.0))   # 고도 1°에서 가장 붉음
    color = warm * SUNSET_COLOR + (1.0 - warm) * NIGHT_COLOR
    alpha = max(MAX_NIGHT_ALPHA * darkness, 55.0 * warm)
    r, g, b = (int(round(c)) for c in color)
    return r, g, b, int(round(alpha))


def _box_blur(mask: np.ndarray, radius: int) -> np.ndarray:
    """정사각형 평균 필터 (scipy 없이 누적 합으로 계산). 값 범위는 0 ~ 1"""
    size = 2 * radius + 1
    padded = np.pad(mask.astype(np.float64), radius + 1, mode="constant")
    total = padded.cumsum(axis=0).cumsum(axis=1)
    window = (total[size:, size:] - total[:-size, size:] - total[size:, :-size] + total[:-size, :-size])
    return window[:mask.shape[0], :mask.shape[1]] / (size * size)


def fire_glow(arrival: np.ndarray, burnout: np.ndarray, t: float, darkness: float,
              radius: int = 3) -> np.ndarray:
    """
    어두울수록 연소 중인 불 주변이 환하게 보이도록 하는 빛 레이어 RGBA (uint8, [y, x, 4]).
    낮(darkness 0)에는 완전히 투명하다.
    """
    height, width = arrival.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    if darkness <= 0.05:
        return rgba
    burning = (arrival >= 0) & (arrival <= t) & ((burnout < 0) | (burnout > t))
    if not burning.any():
        return rgba
    glow = np.clip(_box_blur(burning, radius) * 2.2, 0.0, 1.0)
    rgba[..., :3] = GLOW_COLOR
    rgba[..., 3] = (glow * 200.0 * darkness).astype(np.uint8)
    return rgba


def night_spans(daylight: dict, end_time: float) -> list[tuple[float, float]]:
    """해가 진(일몰 ~ 일출) 구간 목록 [(시작 분, 끝 분), ...]"""
    spans = []
    dark_since = 0.0 if daylight.get("start_sun_elevation_deg", 90.0) <= SUN_HORIZON_DEG else None
    for event in daylight.get("events", []):
        if event["type"] == "sunset" and dark_since is None:
            dark_since = float(event["time_min"])
        elif event["type"] == "sunrise" and dark_since is not None:
            spans.append((dark_since, float(event["time_min"])))
            dark_since = None
    if dark_since is not None and dark_since < end_time:
        spans.append((dark_since, end_time))
    return spans
