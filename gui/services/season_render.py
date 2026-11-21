"""
계절별 지도 색 (9단계)

C 엔진의 계절(season.c)과 같은 계절 키(spring/summer/autumn/winter)를 받아
바탕 지도의 숲 색을 계절에 맞게 바꾼다. Qt와 상관없는 numpy 계산만 있다.

    봄   : 연두색 새잎 + 진달래 분홍 점
    여름 : 짙은 초록
    가을 : 단풍 (활엽수는 주황·적갈색, 침엽수는 초록 그대로)
    겨울 : 잎 진 회갈색 숲 + 눈 경계(snow_line_m)보다 높은 곳은 흰 눈

불(노랑→빨강)이 잘 보이도록 단풍·진달래 색은 채도를 조금 낮췄다. [가정: 디자인 선택]
"""

from __future__ import annotations

import numpy as np

SEASON_KEYS = ("spring", "summer", "autumn", "winter")
SEASON_LABELS = {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울"}
SEASON_ICONS = {"spring": "🌸", "summer": "🌿", "autumn": "🍁", "winter": "❄"}

# 연료 코드 → 계절 색 (theme.FUEL_COLORS 를 덮어씀. 없는 코드는 기본 색 그대로)
#   1 초지, 2 관목, 3 침엽수, 4 활엽수, 5 혼효림, 8 물
SEASON_FUEL_COLORS: dict[str, dict[int, tuple[int, int, int]]] = {
    "spring": {1: (176, 196, 104), 2: (150, 178, 88), 3: (44, 112, 66),
               4: (142, 196, 106), 5: (96, 156, 86)},
    "summer": {1: (112, 166, 72), 2: (72, 136, 56), 3: (26, 90, 50),
               4: (46, 126, 52), 5: (36, 108, 50)},
    "autumn": {1: (204, 178, 108), 2: (176, 124, 64), 3: (40, 100, 60),
               4: (198, 138, 62), 5: (128, 120, 62)},
    "winter": {1: (186, 176, 146), 2: (148, 134, 114), 3: (54, 90, 70),
               4: (150, 136, 122), 5: (112, 114, 96), 8: (178, 204, 224)},
}

# 점 무늬 (색, 대상 연료, 비율) — 숲이 한 가지 색으로 보이지 않게
ACCENTS: dict[str, list[tuple[tuple[int, int, int], tuple[int, ...], float]]] = {
    "spring": [((222, 128, 172), (2, 4), 0.06)],          # 진달래·벚꽃
    "autumn": [((166, 80, 50), (4,), 0.35),               # 붉은 단풍
               ((206, 160, 70), (5,), 0.30),              # 혼효림의 노란 잎
               ((176, 96, 52), (5,), 0.15)],
}

SNOW_COLOR = (246, 249, 253)
SNOW_SHADOW = (170, 186, 212)      # 눈의 그늘진 사면 (푸르스름하게)
WATER_CODE = 8


def season_noise(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
    """점 무늬용 0~1 값. 같은 지도는 항상 같은 무늬가 나오도록 시드를 고정한다."""
    return np.random.default_rng(seed).random(shape)


def snow_mask(elevation: np.ndarray, fuel: np.ndarray, snow_line_m: float) -> np.ndarray:
    """눈에 덮인 셀 (C 엔진 cell_has_snow 와 같은 기준: 고도 ≥ 눈 경계, 물 제외)"""
    if snow_line_m <= 0.0:
        return np.zeros(elevation.shape, dtype=bool)
    return (elevation >= snow_line_m) & (fuel != WATER_CODE)


def season_colors(base: np.ndarray, fuel: np.ndarray, season: str | None) -> np.ndarray:
    """
    기본 연료 색(base, [y, x, 3] float)을 계절 색으로 바꾼다.
    season 이 None 이거나 모르는 값이면 그대로 돌려준다.
    """
    if season not in SEASON_FUEL_COLORS:
        return base
    colors = base.copy()
    for code, rgb in SEASON_FUEL_COLORS[season].items():
        colors[fuel == code] = rgb
    noise = season_noise(fuel.shape)
    start = 0.0
    for rgb, codes, ratio in ACCENTS.get(season, []):
        pick = np.isin(fuel, codes) & (noise >= start) & (noise < start + ratio)
        colors[pick] = rgb
        start += ratio
    return colors


def apply_snow(rgb: np.ndarray, shade: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """눈 덮인 셀을 흰색으로 칠한다. 그늘진 사면은 푸르스름하게 해서 산 모양이 보이게 한다."""
    if not mask.any():
        return rgb
    light = np.array(SNOW_COLOR, dtype=np.float64)
    dark = np.array(SNOW_SHADOW, dtype=np.float64)
    s = shade[mask][:, None]
    rgb = rgb.copy()
    rgb[mask] = dark + (light - dark) * s
    return rgb
