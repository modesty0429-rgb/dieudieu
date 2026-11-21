"""
지도 이미지 계산 (numpy)

Qt와 상관없는 순수 계산만 모았다. 배열 모양은 모두 [y, x] (y = 0 이 북쪽).

    hillshade()        : 음영기복 (산의 입체감)
    terrain_image()    : 음영기복 + 연료 색을 합친 바탕 지도 (RGB)
    fire_state_at()    : 시각 t 의 셀 상태 (0 정상, 1 연소 중, 2 전소)
    fire_overlay()     : 시각 t 의 불 레이어 (RGBA, 투명 배경)
"""

from __future__ import annotations

import numpy as np

import theme
from services import season_render

STATE_UNBURNED = 0
STATE_BURNING = 1
STATE_BURNED = 2


def hillshade(elevation: np.ndarray, cell_size: float,
              azimuth_deg: float = 315.0, altitude_deg: float = 45.0) -> np.ndarray:
    """
    음영기복: 북서쪽(315°) 45° 높이에서 빛을 비췄을 때 각 셀의 밝기 (0 ~ 1).
    빛을 정면으로 받는 사면은 밝고, 반대쪽 사면은 어둡다.
    (C 엔진의 경사 계산과 같은 원리. 출처: Horn 1981)
    """
    dz_south, dz_east = np.gradient(elevation, cell_size)
    slope = np.arctan(np.hypot(dz_east, dz_south))
    aspect = np.arctan2(-dz_east, dz_south)            # 내리막 방향 (북 = 0)
    az = np.radians(azimuth_deg)
    alt = np.radians(altitude_deg)
    shade = (np.sin(alt) * np.cos(slope) +
             np.cos(alt) * np.sin(slope) * np.cos(az - aspect))
    return np.clip(shade, 0.0, 1.0)


def fuel_color_table() -> np.ndarray:
    """연료 코드(0~31) → RGB 색 표. 표에 없는 코드는 회색."""
    table = np.full((32, 3), 90, dtype=np.float64)
    for code, rgb in theme.FUEL_COLORS.items():
        table[code] = rgb
    return table


def terrain_image(elevation: np.ndarray, fuel: np.ndarray, cell_size: float,
                  show_fuel: bool = True, season: str | None = None,
                  snow_line_m: float = 0.0) -> np.ndarray:
    """
    바탕 지도 RGB (uint8, [y, x, 3]).
    연료 색에 음영을 곱해 입체감을 준다. show_fuel 이 False 면 회색 음영만.
    (9단계) season 을 주면 숲 색을 계절 색으로 바꾸고, snow_line_m 보다 높은 곳은 눈으로 덮는다.
    """
    shade = hillshade(elevation, cell_size)
    brightness = 0.35 + 0.65 * shade                     # 너무 어둡지 않게
    if show_fuel:
        colors = fuel_color_table()[np.clip(fuel, 0, 31)]
        colors = season_render.season_colors(colors, fuel, season)
    else:
        colors = np.full(elevation.shape + (3,), 175.0)
    rgb = colors * brightness[..., None]
    rgb = season_render.apply_snow(rgb, shade, season_render.snow_mask(elevation, fuel, snow_line_m))
    return np.clip(rgb, 0, 255).astype(np.uint8)


def fire_state_at(arrival: np.ndarray, burnout: np.ndarray, t: float) -> np.ndarray:
    """
    시각 t 의 셀 상태.
      불 도착 시각 ≤ t < 전소 시각 → 연소 중
      전소 시각 ≤ t               → 전소
    (도착·전소 시각이 -1 이면 아직 일어나지 않은 것)
    """
    state = np.zeros(arrival.shape, dtype=np.uint8)
    arrived = (arrival >= 0) & (arrival <= t)
    burned = (burnout >= 0) & (burnout <= t)
    state[arrived] = STATE_BURNING
    state[burned] = STATE_BURNED
    return state


def fire_overlay(arrival: np.ndarray, burnout: np.ndarray, t: float,
                 burned_alpha: int = 200) -> np.ndarray:
    """
    불 레이어 RGBA (uint8, [y, x, 4]).
    연소 중인 셀은 막 붙었을수록 노랗고 오래 탈수록 빨갛게, 전소 셀은 어두운 회색.
    """
    height, width = arrival.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    state = fire_state_at(arrival, burnout, t)

    burning = state == STATE_BURNING
    if burning.any():
        # 연소 진행 비율 0(막 붙음) ~ 1(곧 꺼짐)
        duration = np.where(burnout > arrival, burnout - arrival, 30.0)
        progress = np.clip((t - arrival) / duration, 0.0, 1.0)[burning]
        new = np.array(theme.FIRE_NEW, dtype=np.float64)
        old = np.array(theme.FIRE_OLD, dtype=np.float64)
        rgba[burning, :3] = (new + (old - new) * progress[:, None]).astype(np.uint8)
        rgba[burning, 3] = 235

    burned = state == STATE_BURNED
    rgba[burned, :3] = theme.BURNED
    rgba[burned, 3] = burned_alpha
    return rgba


def arrival_contours(arrival: np.ndarray, step_min: float) -> list[float]:
    """도착 시각 등시선에 쓸 값 목록 (step_min 분 간격)."""
    reached = arrival[arrival >= 0]
    if reached.size == 0:
        return []
    return list(np.arange(step_min, reached.max() + step_min, step_min))
