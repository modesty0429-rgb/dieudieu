"""
자동 테스트: C 엔진과 Python 도우미가 제대로 동작하는지 한 번에 확인한다.

실행 (프로젝트 폴더에서, C 엔진을 먼저 빌드해 둘 것):
    python tools/run_tests.py

시험 항목
  [엔진]  정상 시나리오 4개가 종료 코드 0으로 끝나고 결과 파일을 만드는지
          오류 시나리오 5개가 종료 코드 1로 끝나고 [ERROR] 메시지를 내는지
          같은 시드로 두 번 실행하면 결과가 같은지 (재현성)
          경계 조건 (등산객 없음, 진화 자원 0, 불이 안 붙음, 젖은 연료)
          줄바꿈 형식 (LF / CRLF 입력 파일에서 같은 결과)
          낮/밤 (일몰 시각, 밤 헬기 출동 중지, 밤 보행 기록, 잘못된 설정값)
          사계절 (여름이 봄보다 습하고 덜 탐, 겨울 눈 위로는 안 탐, 눈 위 발화·잘못된 계절은 오류)
  [Python] 기상청 격자 변환, 기상 응답 해석, 시나리오 파일 쓰기, 결과 읽기, 리포트 만들기,
           계절 지도 색

결과는 항목마다 "통과 / 실패"로 출력되고, 하나라도 실패하면 종료 코드 1.
(외부 테스트 도구 없이 표준 라이브러리 + numpy 만 사용)
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "gui"))

from services import app_config  # noqa: E402

SCENARIOS = app_config.SCENARIO_DIR
results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    """시험 하나의 결과를 기록하고 출력한다."""
    results.append((name, condition, detail))
    mark = "통과" if condition else "실패"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not condition else ""))
    return condition


def run_engine(scenario: Path, mode: str, out_dir: Path | None = None, extra: list[str] | None = None):
    """엔진을 실행하고 (종료 코드, 출력 문자열)을 돌려준다."""
    command = [str(app_config.engine_path()), str(scenario), "--mode", mode]
    if out_dir is not None:
        command += ["--out", str(out_dir)]
    command += extra or []
    done = subprocess.run(command, cwd=app_config.ENGINE_DIR, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)
    return done.returncode, done.stdout + done.stderr


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ----------------------------------------------------------------------
# 엔진 시험
# ----------------------------------------------------------------------
def test_engine_scenarios(tmp: Path) -> None:
    print("\n[엔진] 정상 시나리오")
    cases = [("spring_dry_base.ini", "all", ["summary.json", "evacuation.json", "suppression.json",
                                              "mc_summary.json", "burn_probability.csv"]),
             ("spring_danger_valley.ini", "evac", ["summary.json", "evacuation.json"]),
             ("calm_fixed_weather.ini", "run", ["summary.json", "arrival_time.csv", "stats.csv"]),
             ("spring_dry_base.ini", "printmap", [])]
    for name, mode, files in cases:
        out = tmp / f"{Path(name).stem}_{mode}"
        extra = ["--seed", "7"] if mode == "all" else []
        code, text = run_engine(SCENARIOS / name, mode, out, extra)
        missing = [f for f in files if not (out / f).exists()]
        check(f"{name} --mode {mode}", code == 0 and not missing and "[ERROR]" not in text,
              f"종료 코드 {code}, 없는 파일 {missing}")


def test_engine_errors(tmp: Path) -> None:
    print("\n[엔진] 오류 시나리오 (종료 코드 1 + [ERROR] 메시지가 나와야 함)")
    for name in ["bad_values", "bad_ignition", "missing_file", "bad_trail", "bad_weather"]:
        code, text = run_engine(SCENARIOS / "tests" / f"{name}.ini", "run", tmp / name)
        check(f"tests/{name}.ini", code == 1 and "[ERROR]" in text, f"종료 코드 {code}")
    code, text = run_engine(SCENARIOS / "spring_dry_base.ini", "run", None, ["--seed", "-3"])
    check("잘못된 명령줄 인자 (--seed -3)", code == 1 and "사용법" in text, f"종료 코드 {code}")


def test_reproducibility(tmp: Path) -> None:
    print("\n[엔진] 재현성 (같은 시드 → 같은 결과)")
    hashes = []
    for i in range(2):
        out = tmp / f"repeat{i}"
        run_engine(SCENARIOS / "spring_dry_base.ini", "run", out)
        hashes.append([file_hash(out / f) for f in ("arrival_time.csv", "burnout_time.csv", "stats.csv")])
    check("두 번 실행한 결과 CSV 3개가 같음", hashes[0] == hashes[1])
    out = tmp / "seed99"
    run_engine(SCENARIOS / "spring_dry_base.ini", "run", out, ["--seed", "99"])
    check("시드를 바꾸면 결과가 달라짐", file_hash(out / "arrival_time.csv") != hashes[0][0])


def write_edge_scenario(tmp: Path, name: str, extra: str, with_trails: bool = True) -> Path:
    data = app_config.DATA_DIR
    trails = (f"[trails]\ntrail_file = {data / 'trails' / 'virtual_trails.txt'}\n"
              f"hiker_file = {data / 'trails' / 'virtual_hikers.txt'}\n") if with_trails else ""
    text = (f"[general]\nname = {name}\n[map]\nelevation_file = {data / 'maps' / 'virtual_mountain_elev.asc'}\n"
            f"fuel_file = {data / 'maps' / 'virtual_mountain_fuel.asc'}\n"
            f"fuel_models = {SCENARIOS / 'fuel_models.csv'}\n{trails}"
            f"[weather]\nmode = fixed\n[time]\nduration_min = 120\n[montecarlo]\nruns = 5\n{extra}")
    path = tmp / f"{name}.ini"
    path.write_text(text, encoding="utf-8")
    return path


def test_edge_cases(tmp: Path) -> None:
    print("\n[엔진] 경계 조건 (--mode all)")
    cases = [
        ("no_trails", "[ignition]\npoint1 = 120, 80\n", False, "불이 꺼짐|연소 중"),
        ("zero_resources", "[ignition]\npoint1 = 120, 80\n[suppression]\nfirebreak_cells = 0\nhelicopters = 0\n",
         True, "연소 중|불이 꺼짐"),
        ("no_fire", "[ignition]\npoint1 = 120, 80, 500\n", True, "불이 붙지 않음"),
        ("too_wet", "[ignition]\npoint1 = 120, 80\n[moisture]\ninitial_dead_moisture_pct = 40\n"
                    "live_moisture_factor = 3\n", True, "불이 꺼짐"),
    ]
    for name, extra, trails, expected in cases:
        scenario = write_edge_scenario(tmp, name, extra, trails)
        code, text = run_engine(scenario, "all", tmp / name)
        ok_message = any(word in text for word in expected.split("|"))
        check(f"{name}", code == 0 and ok_message, f"종료 코드 {code}, 기대한 문구 '{expected}' 없음")


def test_line_endings(tmp: Path) -> None:
    """
    입력 파일의 줄바꿈이 LF(리눅스식)여도 CRLF(Windows식)여도 같은 결과가 나와야 한다.
    (Windows 에서 git 으로 받으면 CRLF, ZIP 으로 받으면 LF 인 경우가 많다.
     실제로 Windows 에서 LF 지도 파일을 텍스트 모드로 읽다가 첫 숫자를 건너뛴 버그가 있었다.)
    """
    print("\n[엔진] 줄바꿈 형식 (LF / CRLF 입력 파일)")
    results_by_style = {}
    for style, newline in (("lf", "\n"), ("crlf", "\r\n")):
        data = tmp / f"data_{style}"
        shutil.copytree(app_config.DATA_DIR, data, ignore=shutil.ignore_patterns("gui_custom.ini"))
        for path in data.rglob("*"):
            if path.suffix in (".asc", ".ini", ".csv", ".txt"):
                text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
                path.write_bytes(text.replace("\n", newline).encode("utf-8"))
        out = tmp / f"out_{style}"
        code, text = run_engine(data / "scenarios" / "spring_dry_base.ini", "evac", out)
        ok = code == 0 and (out / "arrival_time.csv").exists()
        check(f"{style.upper()} 입력 파일로 실행", ok, f"종료 코드 {code} {text[-200:] if not ok else ''}")
        if ok:
            results_by_style[style] = file_hash(out / "arrival_time.csv")
    check("LF·CRLF 결과가 같음", len(results_by_style) == 2 and len(set(results_by_style.values())) == 1)


def test_daylight(tmp: Path) -> None:
    """
    (8단계) 낮/밤: 일몰 시각 계산, 밤 헬기 출동 중지, 밤 보행 속도, 잘못된 설정값.
    evening_valley.ini 를 [daylight] enabled = 1 / 0 으로 각각 실행해 비교한다.
    """
    import json
    print("\n[엔진] 낮/밤 (8단계)")

    out_on = tmp / "daylight_on"
    code, text = run_engine(SCENARIOS / "evening_valley.ini", "optimize", out_on)
    summary = json.loads((out_on / "summary.json").read_text(encoding="utf-8")) if code == 0 else {}
    events = summary.get("daylight", {}).get("events", [])
    sunset = next((e for e in events if e["type"] == "sunset"), None)
    # 2026-04-05, 북위 37.5° 동경 127° 의 일몰은 약 18:57 (천문 계산 라이브러리 astral 과 1분 이내로 일치)
    check("일몰 시각 계산 (4월 5일 중부 지방 약 18:57)",
          sunset is not None and "18:54" <= sunset["clock"] <= "19:00", f"계산 결과 {sunset}")

    off_copy = SCENARIOS / "zz_test_daylight_off.ini"
    try:
        text_off = (SCENARIOS / "evening_valley.ini").read_text(encoding="utf-8")
        off_copy.write_text(text_off.replace("enabled           = 1", "enabled           = 0"), encoding="utf-8")
        out_off = tmp / "daylight_off"
        run_engine(off_copy, "optimize", out_off)
    finally:
        off_copy.unlink(missing_ok=True)

    def strategy(out: Path, key: str) -> dict:
        data = json.loads((out / "suppression.json").read_text(encoding="utf-8"))
        return next(s for s in data["strategies"] if s["key"] == key)

    def hikers(out: Path) -> list[dict]:
        return json.loads((out / "evacuation.json").read_text(encoding="utf-8"))["hikers"]

    try:
        on_heli, off_heli = strategy(out_on, "helicopter"), strategy(out_off, "helicopter")
        check("해가 지면 헬기 출동 중지 (낮/밤 끄면 중지 0회)",
              on_heli["heli_grounded"] > 0 and off_heli["heli_grounded"] == 0
              and len(on_heli["drops"]) < len(off_heli["drops"]))
        dark = [h["dark_walk_min"] for h in hikers(out_on) if h["needs_evacuation"]]
        dark_off = [h["dark_walk_min"] for h in hikers(out_off)]
        check("밤에 걸은 시간 기록 (낮/밤 끄면 0분)", dark and max(dark) > 0 and max(dark_off) == 0)
    except (OSError, KeyError, StopIteration, ValueError) as error:
        check("낮/밤 결과 파일 읽기", False, str(error))

    bad = write_edge_scenario(tmp, "bad_daylight", "[ignition]\npoint1 = 120, 80\n[daylight]\nnight_walk_factor = 5\n")
    code, text = run_engine(bad, "run", tmp / "bad_daylight")
    check("잘못된 낮/밤 설정값은 오류 (night_walk_factor = 5)", code == 1 and "night_walk_factor" in text,
          f"종료 코드 {code}")


def test_season(tmp: Path) -> None:
    """
    (9단계) 사계절 날씨: 계절 평년 날씨로 하루 기상을 만들고, 겨울엔 높은 곳이 눈에 덮인다.
    같은 발화 지점·시드로 봄/여름/가을/겨울을 각각 돌려 비교한다.
    """
    import csv
    import json

    import numpy as np
    print("\n[엔진] 사계절 날씨 (9단계)")
    from services.result_loader import load_result

    def run_season(key: str, extra: str = ""):
        scenario = write_edge_scenario(
            tmp, f"season_{key}",
            f"[ignition]\npoint1 = 120, 80\n[weather]\nmode = season\n[season]\nseason = {key}\n{extra}")
        out = tmp / f"season_{key}"
        code, text = run_engine(scenario, "run", out)
        return code, text, out

    found = {}
    for key in ("spring", "summer", "autumn", "winter"):
        code, text, out = run_season(key)
        if code != 0:
            check(f"{key} 계절 실행", False, text[-300:])
            continue
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        with open(out / "stats.csv", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        found[key] = {
            "season": summary.get("season", {}),
            "area": summary["result"]["burned_area_ha"],
            "rh": [float(r["rh_pct"]) for r in rows],
            "temp": [float(r["temp_c"]) for r in rows],
            "out": out,
        }
    if len(found) < 4:
        return
    sp, su, wi = found["spring"], found["summer"], found["winter"]
    check("summary.json 에 계절 정보 기록 (season.key, 평년 기후)",
          sp["season"].get("key") == "spring" and sp["season"].get("weather_from_season") is True)
    check("여름이 봄보다 습함 (평균 습도)",
          sum(su["rh"]) / len(su["rh"]) > sum(sp["rh"]) / len(sp["rh"]) + 10,
          f"봄 {sum(sp['rh']) / len(sp['rh']):.1f}%, 여름 {sum(su['rh']) / len(su['rh']):.1f}%")
    check("여름이 봄보다 덜 탐 (같은 발화 지점)", su["area"] < sp["area"],
          f"봄 {sp['area']} ha, 여름 {su['area']} ha")
    check("겨울은 영하 근처로 춥다 (최저 기온 < 2℃)", min(wi["temp"]) < 2.0, f"최저 {min(wi['temp'])}")
    check("겨울엔 눈 셀이 있고 봄엔 없다",
          wi["season"].get("snow_cells", 0) > 0 and sp["season"].get("snow_cells", 1) == 0)
    try:
        result = load_result(wi["out"] / "summary.json")
        line = float(wi["season"]["snow_line_m"])
        snowy = result.map.elevation >= line
        burned_on_snow = int(((result.arrival >= 0) & snowy).sum())
        check("눈 덮인 곳(해발 600 m 이상)으로는 불이 번지지 않음", burned_on_snow == 0,
              f"눈 위에 탄 셀 {burned_on_snow}개")
        check("결과 읽기: 지도에 계절·눈 경계 반영", result.map.season == "winter" and result.map.snow_line_m == line)
        # 눈 위 발화 지점은 오류
        y, x = (int(v) for v in np.argwhere(snowy)[0])
        bad = write_edge_scenario(tmp, "season_snow_ignition",
                                  f"[ignition]\npoint1 = {x}, {y}\n[season]\nseason = winter\n")
        code, text = run_engine(bad, "run", tmp / "season_snow_ignition")
        check("눈 덮인 곳에 발화 지점을 두면 오류", code == 1 and "눈" in text, f"종료 코드 {code}")
    except (OSError, KeyError, ValueError, IndexError) as error:
        check("겨울 결과 읽기", False, str(error))

    bad = write_edge_scenario(tmp, "bad_season", "[ignition]\npoint1 = 120, 80\n[season]\nseason = monsoon\n")
    code, text = run_engine(bad, "run", tmp / "bad_season")
    check("잘못된 계절 이름은 오류 (season = monsoon)", code == 1 and "season" in text, f"종료 코드 {code}")


# ----------------------------------------------------------------------
# Python 시험
# ----------------------------------------------------------------------
def test_python_helpers(tmp: Path) -> None:
    print("\n[Python] 도우미 함수")
    from services import weather_api
    from services.result_loader import load_result, load_scenario_preview
    from services.report_builder import build_report_html
    from services.scenario_writer import ScenarioOverrides, write_scenario

    check("기상청 격자: 서울 (60, 127)", weather_api.latlon_to_grid(37.5665, 126.9780) == (60, 127))
    check("기상청 격자: 부산 (98, 76)", weather_api.latlon_to_grid(35.1796, 129.0756) == (98, 76))

    items = [{"category": c, "fcstDate": "20260405", "fcstTime": "1300", "fcstValue": v}
             for c, v in (("TMP", "18"), ("REH", "25"), ("WSD", "6"), ("VEC", "270"), ("SKY", "1"))]
    rows = weather_api.parse_forecast(items)
    check("단기예보 응답 해석", len(rows) == 1 and rows[0].wind_dir_deg == 270.0)
    try:
        weather_api.extract_items("<OpenAPI_ServiceResponse><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
                                  "</returnAuthMsg></OpenAPI_ServiceResponse>")
        check("API 키 오류 응답을 알아챔", False)
    except weather_api.WeatherApiError as error:
        check("API 키 오류 응답을 알아챔", "SERVICE_KEY" in str(error))

    # 시나리오 쓰기: 임시 폴더에 원본을 복사해 바꾸고, 미리보기로 다시 읽어 확인
    scenario_copy = SCENARIOS / "zz_test_copy.ini"
    try:
        shutil.copy(SCENARIOS / "spring_dry_base.ini", scenario_copy)
        o = ScenarioOverrides()
        o.ignitions = [(100, 90, 0.0)]
        o.set("weather", "mode", "fixed")
        o.set("spread", "random_seed", 5)
        written = write_scenario(scenario_copy, o, name="zz_test_written")
        preview = load_scenario_preview(written)
        text = written.read_text(encoding="utf-8")
        check("시나리오 쓰기 (발화 지점·값 교체, 주석 유지)",
              preview.ignitions == [(100, 90, 0.0)] and "mode = fixed" in text and "[가정]" in text)
        written.unlink()
    finally:
        scenario_copy.unlink(missing_ok=True)

    summary = tmp / "spring_dry_base_all" / "summary.json"
    if summary.exists():
        result = load_result(summary)
        check("결과 읽기 (대피·진화·몬테카를로 포함)",
              result.evacuation is not None and result.suppression is not None and result.montecarlo is not None)
        html_text = build_report_html(result, {})
        check("리포트 HTML 만들기", "진화 전략 비교" in html_text and "몬테카를로" in html_text)
    else:
        check("결과 읽기", False, "앞의 엔진 시험 결과가 없음")

    from services import daylight_render
    spans = daylight_render.night_spans({"start_sun_elevation_deg": 20.0,
                                         "events": [{"type": "sunset", "time_min": 120.0},
                                                    {"type": "sunrise", "time_min": 800.0}]}, 1000.0)
    day_tint = daylight_render.night_tint(1.0, 40.0)
    night_tint = daylight_render.night_tint(0.0, -30.0)
    check("낮/밤 화면 계산 (밤 구간, 낮엔 투명·밤엔 어둡게)",
          spans == [(120.0, 800.0)] and day_tint[3] == 0 and night_tint[3] > 150)

    import numpy as np
    from services import map_render
    from services.result_loader import season_from_ini
    from services.scenario_writer import load_season_presets
    from configparser import ConfigParser
    elevation = np.array([[100.0, 300.0], [650.0, 900.0]])
    fuel = np.array([[4, 4], [3, 8]])
    summer = map_render.terrain_image(elevation, fuel, 30.0, season="summer")
    autumn = map_render.terrain_image(elevation, fuel, 30.0, season="autumn")
    winter = map_render.terrain_image(elevation, fuel, 30.0, season="winter", snow_line_m=600.0)
    plain = map_render.terrain_image(elevation, fuel, 30.0)
    check("계절 지도 색 (가을 활엽수는 붉은 쪽, 겨울 눈 위는 흰색, 물은 눈 없음)",
          autumn[0, 0, 0] > summer[0, 0, 0] and winter[1, 0].min() > 150
          and winter[1, 1, 2] > winter[1, 1, 0] and not np.array_equal(summer, plain))
    parser = ConfigParser()
    parser.read_string("[weather]\nmode = season\n[season]\nseason = auto\n")
    from datetime import datetime
    check("계절 해석 (auto + 1월 → 겨울, 눈 경계 600 m)",
          season_from_ini(parser, datetime(2026, 1, 15, 13, 0)) == ("winter", 600.0))
    presets = {p.key: p for p in load_season_presets()}
    check("계절 프리셋 (장마 없음, 대표 날짜·겨울 눈)",
          set(presets) == {"spring", "summer", "autumn", "winter"}
          and all(p.date for p in presets.values()) and presets["winter"].snow_line_m > 0
          and not any("장마" in p.note or "장마" in p.label for p in presets.values()))


def main() -> int:
    exe = app_config.engine_path()
    print(f"엔진: {exe}")
    if not exe.exists():
        from services.engine_runner import engine_missing_help
        print("\n".join(engine_missing_help(exe)))
        return 1
    with tempfile.TemporaryDirectory(prefix="wildfire_test_") as folder:
        tmp = Path(folder)
        test_engine_scenarios(tmp)
        test_engine_errors(tmp)
        test_reproducibility(tmp)
        test_edge_cases(tmp)
        test_line_endings(tmp)
        test_daylight(tmp)
        test_season(tmp)
        test_python_helpers(tmp)

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} 통과")
    if failed:
        print("실패한 시험: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
