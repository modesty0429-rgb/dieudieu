"""
계절별 지도 색 (9단계)

C 엔진의 계절(season.c)과 같은 계절 키(spring/summer/autumn/winter)를 받아
바탕 지도의 숲 색을 계절에 맞게 바꾼다. Qt와 상관없는 numpy 계산만 있다.

    봄   : 연두 새잎 + 꽃 군락 (진달래 분홍 · 벚꽃 연분홍 · 길가 개나리 노랑)
    여름 : 짙고 싱그러운 초록 (숲마다 초록 농도가 조금씩 다름)
    가을 : 단풍 (활엽수는 주황·적갈·노랑이 무리 지어, 침엽수는 초록 그대로)
    겨울 : 600 m 위 흰 눈 (햇빛 받는 사면은 따뜻한 분홍빛, 그늘은 보라·하늘빛),
           눈 아래로 내려가며 서리 낀 숲, 눈 덮인 소나무, 금빛 억새, 얼음 호수

꽃·단풍은 점을 하나씩 흩뿌리지 않고 "부드러운 잡음(smooth noise)"으로 군락을 만든 뒤
그 안에 점점이 찍어, 실제 산처럼 모여 피어 보이게 했다.
불(노랑→빨강)과 헷갈리지 않도록 노랑·빨강 계열은 채도와 밝기를 조금 낮췄다. [가정: 디자인 선택]
"""

from __future__ import annotations

import numpy as np

SEASON_KEYS = ("spring", "summer", "autumn", "winter")
SEASON_LABELS = {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울"}
SEASON_ICONS = {"spring": "🌸", "summer": "🌿", "autumn": "🍁", "winter": "❄"}

# 연료 코드: 1 초지, 2 관목, 3 침엽수, 4 활엽수, 5 혼효림, 7 도로, 8 물, 9 바위
GRASS, SHRUB, CONIFER, BROADLEAF, MIXED, ROAD, WATER, ROCK = 1, 2, 3, 4, 5, 7, 8, 9

# 연료마다 (밝은 색, 짙은 색) — 부드러운 잡음으로 두 색 사이를 섞어 숲이 얼룩덜룩 자연스럽게 보이게 한다
SEASON_FUEL_COLORS: dict[str, dict[int, tuple[tuple[int, int, int], tuple[int, int, int]]]] = {
    "spring": {GRASS: ((196, 220, 120), (160, 200, 100)), SHRUB: ((168, 206, 110), (132, 182, 92)),
               CONIFER: ((58, 130, 78), (40, 108, 64)), BROADLEAF: ((176, 224, 128), (130, 198, 104)),
               MIXED: ((120, 186, 100), (84, 150, 82))},
    "summer": {GRASS: ((128, 184, 80), (100, 160, 66)), SHRUB: ((86, 154, 66), (62, 128, 54)),
               CONIFER: ((30, 98, 56), (20, 80, 46)), BROADLEAF: ((64, 150, 66), (36, 118, 52)),
               MIXED: ((48, 126, 60), (30, 102, 50))},
    "autumn": {GRASS: ((214, 190, 120), (196, 166, 98)), SHRUB: ((186, 128, 70), (160, 104, 60)),
               CONIFER: ((44, 104, 64), (34, 88, 56)), BROADLEAF: ((206, 146, 66), (186, 118, 56)),
               MIXED: ((140, 128, 66), (104, 112, 62))},
    "winter": {GRASS: ((226, 192, 112), (204, 164, 92)), SHRUB: ((176, 132, 122), (150, 110, 118)),
               CONIFER: ((28, 118, 98), (20, 92, 82)), BROADLEAF: ((182, 140, 128), (150, 116, 136)),
               MIXED: ((96, 130, 118), (120, 108, 128)), ROAD: ((176, 176, 186), (160, 160, 172)),
               WATER: ((150, 226, 236), (120, 200, 226))},
}

# 군락 무늬: (이름, 색, 대상 연료, 군락 비율, 군락 안 점 밀도, 조건)
#   군락 비율 = 대상 셀 중 군락이 되는 비율, 점 밀도 = 군락 안에서 실제로 색이 찍히는 비율
#   조건: "low" 낮은 곳(산 아래), "mid" 중턱, "road" 길가, None 어디든
ACCENTS: dict[str, list[tuple[str, tuple[int, int, int], tuple[int, ...], float, float, str | None]]] = {
    "spring": [
        ("진달래", (244, 118, 184), (SHRUB, BROADLEAF, MIXED, CONIFER), 0.24, 0.80, "mid"),
        ("벚꽃", (255, 222, 236), (BROADLEAF, MIXED, GRASS, SHRUB), 0.34, 0.85, "low"),
        ("개나리", (246, 214, 84), (GRASS, SHRUB, BROADLEAF, MIXED), 0.75, 0.75, "road"),
        ("철쭉", (226, 92, 168), (SHRUB, BROADLEAF), 0.12, 0.70, None),
    ],
    "summer": [
        ("수국", (130, 150, 220), (GRASS, SHRUB), 0.10, 0.35, "low"),
    ],
    "autumn": [
        ("붉은 단풍", (172, 72, 52), (BROADLEAF, MIXED), 0.30, 0.75, None),
        ("노란 은행", (214, 176, 64), (BROADLEAF, MIXED), 0.22, 0.70, "low"),
        ("갈색 참나무", (150, 104, 62), (BROADLEAF,), 0.25, 0.60, None),
    ],
    "winter": [
        ("눈 얹은 소나무", (226, 236, 250), (CONIFER,), 0.30, 0.35, "mid"),
        ("자줏빛 겨울숲", (150, 104, 140), (BROADLEAF, MIXED), 0.35, 0.80, None),
        ("붉은 산수유 열매", (196, 70, 110), (SHRUB, BROADLEAF), 0.08, 0.35, "low"),
    ],
}

# 눈: 햇빛 받는 사면은 살짝 분홍·살구빛(알펜글로), 그늘은 보라·하늘빛
SNOW_SUN = (255, 246, 244)
SNOW_MID = (232, 238, 252)
SNOW_SHADE = (156, 164, 222)
SNOW_SPARKLE = (255, 255, 255)
FROST_BAND_M = 120.0       # 눈 경계 아래 이 높이까지 서리가 점점 옅게 낀 것처럼 보이게 (장식, 계산과 무관)

# 범례에 쓸 계절 색
LEGEND: dict[str, list[tuple[str, tuple[int, int, int]]]] = {
    "spring": [("새잎", (176, 224, 128)), ("진달래", (238, 120, 178)), ("벚꽃", (252, 214, 230)),
               ("개나리", (238, 212, 92)), ("소나무", (58, 130, 78))],
    "summer": [("활엽수", (64, 150, 66)), ("소나무", (30, 98, 56)), ("풀밭", (128, 184, 80)),
               ("수국", (130, 150, 220))],
    "autumn": [("단풍", (206, 146, 66)), ("붉은 단풍", (172, 72, 52)), ("은행", (214, 176, 64)),
               ("억새", (214, 190, 120)), ("소나무", (44, 104, 64))],
    "winter": [("눈(해 받는 곳)", SNOW_SUN), ("눈(그늘)", SNOW_SHADE), ("소나무", (28, 118, 98)),
               ("자줏빛 겨울숲", (150, 104, 140)), ("산수유 열매", (196, 70, 110)), ("억새", (226, 192, 112)),
               ("얼음", (150, 226, 236))],
}

WATER_CODE = WATER


# ----------------------------------------------------------------------
# 잡음
# ----------------------------------------------------------------------
def season_noise(shape: tuple[int, int], seed: int = 7) -> np.ndarray:
    """칸마다 따로 노는 0~1 값 (점 찍기용). 같은 지도는 항상 같은 무늬가 나오도록 시드 고정."""
    return np.random.default_rng(seed).random(shape)


def smooth_noise(shape: tuple[int, int], scale: float, seed: int) -> np.ndarray:
    """
    부드러운 잡음 (0~1, 고르게 퍼진 값): 굵은 격자에 난수를 놓고 쌍선형 보간으로 늘린다.
    scale 칸 정도 크기의 얼룩(군락)이 생긴다. 값은 순위로 바꿔서 "상위 20 %" 같은 비율이 정확하다.
    """
    h, w = shape
    gh, gw = int(h / scale) + 2, int(w / scale) + 2
    coarse = np.random.default_rng(seed).random((gh, gw))
    ys = np.linspace(0, gh - 1.001, h)
    xs = np.linspace(0, gw - 1.001, w)
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)     # 부드러운 보간 (smoothstep)
    a = coarse[np.ix_(y0, x0)]
    b = coarse[np.ix_(y0, x0 + 1)]
    c = coarse[np.ix_(y0 + 1, x0)]
    d = coarse[np.ix_(y0 + 1, x0 + 1)]
    field = (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
    ranks = field.ravel().argsort().argsort().reshape(shape)
    return ranks / max(field.size - 1, 1)


def near_road(fuel: np.ndarray, radius: int = 3) -> np.ndarray:
    """도로에서 radius 칸 안 (개나리는 길가에 핀다)"""
    road = fuel == ROAD
    out = road.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            out |= np.roll(np.roll(road, dy, axis=0), dx, axis=1)
    return out & ~road


def _zone(kind: str | None, fuel: np.ndarray, elevation: np.ndarray | None) -> np.ndarray:
    """군락이 생길 수 있는 곳"""
    if kind is None or elevation is None or elevation.size < 16:
        return np.ones(fuel.shape, dtype=bool)
    lo, hi = np.percentile(elevation, 35), np.percentile(elevation, 80)
    if kind == "low":
        return elevation <= lo
    if kind == "mid":
        return (elevation > np.percentile(elevation, 25)) & (elevation <= hi)
    if kind == "road":
        return near_road(fuel)
    return np.ones(fuel.shape, dtype=bool)


# ----------------------------------------------------------------------
# 색 칠하기
# ----------------------------------------------------------------------
# 계절마다 음영 세기 (밝기 = 최소 + (1 − 최소) × 음영). 봄은 화사하게, 겨울은 맑게
SEASON_MIN_BRIGHTNESS = {"spring": 0.50, "summer": 0.40, "autumn": 0.45, "winter": 0.50}


def season_colors(base: np.ndarray, fuel: np.ndarray, season: str | None,
                  elevation: np.ndarray | None = None) -> np.ndarray:
    """기본 연료 색(base, [y, x, 3] float)을 계절 색으로 바꾼다. 모르는 계절이면 그대로."""
    return season_layers(base, fuel, season, elevation)[0]


def season_layers(base: np.ndarray, fuel: np.ndarray, season: str | None,
                  elevation: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """
    계절 색과 "꽃 세기"(0~1)를 함께 돌려준다.
    꽃 세기가 큰 셀(꽃·열매)은 음영을 덜 받게 해서 그늘진 사면에서도 꽃이 화사하게 보인다.
    """
    pop = np.zeros(fuel.shape)
    if season not in SEASON_FUEL_COLORS:
        return base, pop
    colors = base.copy()
    shape = fuel.shape
    blend = smooth_noise(shape, 9.0, seed=11)[..., None]          # 숲 얼룩 (밝은 숲 ↔ 짙은 숲)
    for code, (light, dark) in SEASON_FUEL_COLORS[season].items():
        pick = fuel == code
        if pick.any():
            lt, dk = np.array(light, float), np.array(dark, float)
            colors[pick] = (dk + (lt - dk) * blend)[pick]

    dots = season_noise(shape)
    for i, (_name, rgb, codes, ratio, density, zone) in enumerate(ACCENTS.get(season, [])):
        cluster = smooth_noise(shape, 6.0 + 2.0 * i, seed=23 + i) >= 1.0 - ratio
        dot = season_noise(shape, seed=101 + i) < density
        pick = np.isin(fuel, codes) & cluster & dot & _zone(zone, fuel, elevation)
        # 군락 가운데일수록 진하게, 가장자리는 바탕색과 섞어 부드럽게
        strength = np.clip(0.65 + 0.35 * dots, 0.0, 1.0)[pick][:, None]
        colors[pick] = colors[pick] * (1 - strength) + np.array(rgb, float) * strength
        if _name not in ("자줏빛 겨울숲", "갈색 참나무"):       # 꽃·열매·눈 얹은 가지만 반짝이게
            pop[pick] = np.maximum(pop[pick], strength[:, 0])
    return colors, pop


def snow_mask(elevation: np.ndarray, fuel: np.ndarray, snow_line_m: float) -> np.ndarray:
    """눈에 덮인 셀 (C 엔진 cell_has_snow 와 같은 기준: 고도 ≥ 눈 경계, 물 제외)"""
    if snow_line_m <= 0.0:
        return np.zeros(elevation.shape, dtype=bool)
    return (elevation >= snow_line_m) & (fuel != WATER_CODE)


def apply_snow(rgb: np.ndarray, shade: np.ndarray, mask: np.ndarray,
               elevation: np.ndarray | None = None, fuel: np.ndarray | None = None,
               snow_line_m: float = 0.0) -> np.ndarray:
    """
    눈 덮인 셀을 칠한다.
      햇빛 받는 사면 → 따뜻한 흰색(살구빛), 중간 → 푸른 흰색, 그늘 → 보라·하늘빛 (산 모양이 잘 보이게)
      군데군데 반짝이는 흰 점
    elevation 을 주면 눈 경계 바로 아래에 서리 낀 숲(점점 옅어짐)도 그린다. (장식일 뿐, 계산에는 영향 없음)
    """
    if not mask.any():
        return rgb
    rgb = rgb.copy()
    sun = np.array(SNOW_SUN, float)
    mid = np.array(SNOW_MID, float)
    dark = np.array(SNOW_SHADE, float)
    s = shade[mask]
    lo, hi = np.percentile(s, 8), np.percentile(s, 92)
    s = np.clip((s - lo) / max(hi - lo, 1e-6), 0.0, 1.0)[:, None]   # 눈 안에서 음영 차이를 크게 (산 모양이 보이게)
    low = dark + (mid - dark) * np.clip(s / 0.6, 0, 1)
    high = mid + (sun - mid) * np.clip((s - 0.6) / 0.4, 0, 1)
    rgb[mask] = np.where(s < 0.6, low, high)

    sparkle = mask & (season_noise(mask.shape, seed=303) < 0.04)
    rgb[sparkle] = SNOW_SPARKLE

    if elevation is not None and fuel is not None and snow_line_m > 0:
        below = (snow_line_m - elevation) / FROST_BAND_M          # 0 (눈 경계) ~ 1 (서리 끝)
        band = (~mask) & (below > 0) & (below < 1) & (fuel != WATER_CODE) & (fuel != ROAD)
        chance = np.clip(1 - below, 0.0, 1.0) ** 2 * 0.45
        frost = band & (season_noise(mask.shape, seed=404) < chance)
        rgb[frost] = rgb[frost] * 0.35 + np.array(SNOW_MID, float) * 0.65 * (0.75 + 0.25 * shade[frost][:, None])
    return rgb


def legend_html(season: str | None) -> str:
    """지도 아래 범례에 붙일 계절 색 (예: '🌸 봄  ■ 진달래 ■ 벚꽃 ...')"""
    if season not in LEGEND:
        return ""
    chips = "  ".join(f'<span style="color:rgb{rgb}">■</span> {name}' for name, rgb in LEGEND[season])
    return f"{SEASON_ICONS[season]} {SEASON_LABELS[season]}  {chips}"
