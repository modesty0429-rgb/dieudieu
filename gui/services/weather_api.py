"""
기상청 단기예보 API 연동

공공데이터포털의 "기상청_단기예보 ((구)_동네예보) 조회서비스" 중 단기예보(getVilageFcst)를 불러와
C 엔진이 읽는 기상 CSV(datetime,temp_c,rh_pct,wind_speed_ms,wind_dir_deg)로 저장한다.

    1) 위도·경도 → 기상청 격자 좌표(nx, ny)  : latlon_to_grid()   (기상청 활용가이드의 LCC 투영 공식)
    2) 가장 최근 발표 시각 고르기              : latest_base_time()
    3) API 호출                                : fetch_forecast()
    4) 시각별로 기온(TMP)·습도(REH)·풍속(WSD)·풍향(VEC) 묶기 : parse_forecast()
    5) CSV 저장                                : save_weather_csv()

API 키는 코드에 쓰지 않고 config/api_keys.ini 의 [kma] service_key 에 넣는다. (.gitignore 로 올라가지 않음)
참고: 공공데이터포털 "기상청_단기예보 조회서비스 활용가이드" (격자 변환 공식, 응답 항목 코드)
"""

from __future__ import annotations

import configparser
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from services import app_config

KMA_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
API_KEY_FILE = app_config.CONFIG_DIR / "api_keys.ini"
BASE_HOURS = [2, 5, 8, 11, 14, 17, 20, 23]     # 단기예보 발표 시각 (하루 8번)
RELEASE_DELAY_MIN = 15                          # 발표 후 API 로 받을 수 있기까지 여유 [가정]

# 산불 위험이 자주 언급되는 국내 산 (위도, 경도) — 위치 고르기용 예시
MOUNTAIN_PRESETS = {
    "북한산 (서울)": (37.6584, 126.9779),
    "설악산 (강원 속초)": (38.1194, 128.4656),
    "오대산 (강원 평창)": (37.7944, 128.5433),
    "지리산 (경남 산청)": (35.3369, 127.7306),
    "팔공산 (대구)": (36.0164, 128.6947),
    "한라산 (제주)": (33.3617, 126.5292),
}


class WeatherApiError(Exception):
    """API 키 없음, 네트워크 오류, 응답 오류 등을 사용자에게 알리기 위한 예외"""


@dataclass
class WeatherRow:
    time: datetime
    temp_c: float
    rh_pct: float
    wind_speed_ms: float
    wind_dir_deg: float


# ----------------------------------------------------------------------
# 1) 위경도 → 격자
# ----------------------------------------------------------------------
def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """
    위도·경도를 기상청 5 km 격자 좌표 (nx, ny) 로 바꾼다. (람베르트 정각원추도법)
    상수는 기상청 단기예보 활용가이드의 값: 지구 반경 6371.00877 km, 격자 5 km,
    표준위도 30°·60°, 기준점 (126°E, 38°N) = 격자 (43, 136)
    """
    re_km, grid_km = 6371.00877, 5.0
    slat1, slat2 = math.radians(30.0), math.radians(60.0)
    olon, olat = math.radians(126.0), math.radians(38.0)
    xo, yo = 43, 136

    re = re_km / grid_km
    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = re * sf / (math.tan(math.pi * 0.25 + olat * 0.5) ** sn)

    ra = re * sf / (math.tan(math.pi * 0.25 + math.radians(lat) * 0.5) ** sn)
    theta = math.radians(lon) - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    nx = math.floor(ra * math.sin(theta) + xo + 0.5)
    ny = math.floor(ro - ra * math.cos(theta) + yo + 0.5)
    return nx, ny


# ----------------------------------------------------------------------
# 2) 발표 시각
# ----------------------------------------------------------------------
def latest_base_time(now: datetime) -> tuple[str, str]:
    """지금 받을 수 있는 가장 최근 발표의 (base_date 'YYYYMMDD', base_time 'HH00')"""
    ready = now - timedelta(minutes=RELEASE_DELAY_MIN)
    hours = [h for h in BASE_HOURS if h <= ready.hour]
    if hours:
        return ready.strftime("%Y%m%d"), f"{hours[-1]:02d}00"
    yesterday = ready - timedelta(days=1)
    return yesterday.strftime("%Y%m%d"), "2300"


# ----------------------------------------------------------------------
# 3) API 호출
# ----------------------------------------------------------------------
def load_api_key(path: Path = API_KEY_FILE) -> str | None:
    """config/api_keys.ini 에서 기상청 API 키를 읽는다. 없으면 None"""
    if not path.exists():
        return None
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8-sig")
    key = parser.get("kma", "service_key", fallback="").strip()
    return key or None


def fetch_forecast(service_key: str, nx: int, ny: int, now: datetime | None = None,
                   timeout_sec: float = 15.0) -> list[dict]:
    """단기예보 항목 목록(JSON item 리스트)을 받아 온다. 실패하면 WeatherApiError"""
    import requests   # 6단계에서만 필요하므로 여기서 불러온다

    base_date, base_time = latest_base_time(now or datetime.now())
    params = {"pageNo": 1, "numOfRows": 1000, "dataType": "JSON",
              "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny}
    # 공공데이터포털은 "인코딩된 키"와 "디코딩된 키"를 함께 준다.
    # 인코딩된 키(%가 들어 있음)를 requests 에 넘기면 한 번 더 인코딩되므로 주소에 직접 붙인다.
    url = KMA_URL
    if "%" in service_key:
        url = f"{KMA_URL}?serviceKey={service_key}"
    else:
        params["serviceKey"] = service_key

    try:
        response = requests.get(url, params=params, timeout=timeout_sec)
    except requests.RequestException as error:
        # 오류 메시지에 요청 주소(키 포함)가 들어 있으므로 키를 가린 뒤 보여 준다
        message = str(error).replace(service_key, "***")
        raise WeatherApiError(f"기상청 서버에 연결할 수 없습니다 (인터넷 연결 확인): {message}") from None
    if response.status_code != 200:
        raise WeatherApiError(f"기상청 서버 응답 오류 (HTTP {response.status_code})")
    return extract_items(response.text)


def extract_items(text: str) -> list[dict]:
    """응답 본문에서 item 목록을 꺼낸다. 키 오류 등은 XML 로 오기도 하므로 함께 처리한다."""
    import json

    if text.lstrip().startswith("<"):
        # 예: <returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
        start, end = text.find("<returnAuthMsg>"), text.find("</returnAuthMsg>")
        message = text[start + 15:end] if start >= 0 and end > start else text[:200]
        raise WeatherApiError(f"API 키 또는 요청 오류: {message} (공공데이터포털에서 활용 신청·승인 여부를 확인하세요)")
    try:
        data = json.loads(text)
        header = data["response"]["header"]
    except (ValueError, KeyError) as error:
        raise WeatherApiError(f"응답 형식을 해석할 수 없습니다: {text[:200]}") from error
    if header.get("resultCode") != "00":
        raise WeatherApiError(f"기상청 응답 오류 {header.get('resultCode')}: {header.get('resultMsg')}")
    return data["response"]["body"]["items"]["item"]


# ----------------------------------------------------------------------
# 4) 해석과 5) 저장
# ----------------------------------------------------------------------
NEEDED = {"TMP": "temp_c", "REH": "rh_pct", "WSD": "wind_speed_ms", "VEC": "wind_dir_deg"}


def parse_forecast(items: list[dict]) -> list[WeatherRow]:
    """
    항목을 예보 시각별로 묶는다. 한 시각에 기온·습도·풍속·풍향 네 값이 모두 있는 것만 쓴다.
    (단기예보 코드: TMP 1시간 기온 °C, REH 습도 %, WSD 풍속 m/s, VEC 풍향 °)
    """
    by_time: dict[datetime, dict[str, float]] = {}
    for item in items:
        category = item.get("category")
        if category not in NEEDED:
            continue
        when = datetime.strptime(item["fcstDate"] + item["fcstTime"], "%Y%m%d%H%M")
        try:
            by_time.setdefault(when, {})[NEEDED[category]] = float(item["fcstValue"])
        except (TypeError, ValueError):
            continue
    rows = []
    for when in sorted(by_time):
        values = by_time[when]
        if len(values) == len(NEEDED):
            rows.append(WeatherRow(when, values["temp_c"], values["rh_pct"],
                                   values["wind_speed_ms"], values["wind_dir_deg"] % 360.0))
    if not rows:
        raise WeatherApiError("예보에서 기온·습도·풍속·풍향을 모두 갖춘 시각을 찾지 못했습니다.")
    return rows


def save_weather_csv(rows: list[WeatherRow], path: Path, source_note: str) -> Path:
    """C 엔진 기상 CSV 형식으로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# source={source_note}\n")
        f.write("# 기상청 단기예보를 GUI(weather_api.py)가 변환한 파일. 풍향 = 바람이 불어오는 방향\n")
        f.write("datetime,temp_c,rh_pct,wind_speed_ms,wind_dir_deg\n")
        for r in rows:
            f.write(f"{r.time:%Y-%m-%d %H:%M},{r.temp_c:.1f},{r.rh_pct:.0f},{r.wind_speed_ms:.1f},"
                    f"{r.wind_dir_deg:.0f}\n")
    return path


def download_weather(lat: float, lon: float, out_dir: Path = app_config.DATA_DIR / "weather",
                     now: datetime | None = None) -> tuple[Path, list[WeatherRow]]:
    """위치의 단기예보를 받아 CSV로 저장하고 (파일 경로, 행 목록)을 돌려준다."""
    key = load_api_key()
    if key is None:
        raise WeatherApiError(f"API 키가 없습니다. {API_KEY_FILE} 에 [kma] service_key 를 넣어 주세요. "
                              f"(양식: config/api_keys.example.ini)")
    nx, ny = latlon_to_grid(lat, lon)
    rows = parse_forecast(fetch_forecast(key, nx, ny, now))
    base_date, base_time = latest_base_time(now or datetime.now())
    path = out_dir / f"kma_{nx}_{ny}_{base_date}{base_time}.csv"
    note = f"KMA_VilageFcst base={base_date}{base_time} nx={nx} ny={ny} lat={lat:.4f} lon={lon:.4f}"
    return save_weather_csv(rows, path, note), rows


def read_weather_csv(path: Path) -> list[WeatherRow]:
    """저장된 기상 CSV(엔진 형식)를 다시 읽는다. (미리보기, 시작 시각 확인용)"""
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("datetime"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 5:
            continue
        try:
            rows.append(WeatherRow(datetime.strptime(parts[0], "%Y-%m-%d %H:%M"), float(parts[1]),
                                   float(parts[2]), float(parts[3]), float(parts[4])))
        except ValueError:
            continue
    return rows
