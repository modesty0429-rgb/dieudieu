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
  [Python] 기상청 격자 변환, 기상 응답 해석, 시나리오 파일 쓰기, 결과 읽기, 리포트 만들기
  [실제 산] 산 시나리오 6개 실행, 격자↔위경도, [임시] 연료 규칙,
          시험용 산림청 SHP(등산로·임상도) 변환 → 엔진 실행 (pyshp·pyproj·pillow 가 있을 때)

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
        shutil.copytree(app_config.DATA_DIR, data, ignore=shutil.ignore_patterns("gui_custom.ini", "raw", "_cache"))
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


# ----------------------------------------------------------------------
# 실제 산 (기능 브랜치 feature/mountain-types)
# ----------------------------------------------------------------------
def test_real_mountains(tmp: Path) -> None:
    print("\n[실제 산] 지형·변환 도구")
    import numpy as np
    from services import mountain_builder as mb

    failed = []
    for ini in sorted(SCENARIOS.glob("mountain_*.ini")):
        code, text = run_engine(ini, "run", tmp / ini.stem)
        if code != 0 or "[ERROR]" in text:
            failed.append(ini.stem)
    check("실제 산 시나리오 6개 실행", not failed and len(list(SCENARIOS.glob("mountain_*.ini"))) >= 6, f"실패: {failed}")

    center = (37.6584, 126.9779)
    lat, lon = mb.grid_cell_latlon(center)
    gx, gy = mb.latlon_to_grid(lat, lon, center)
    check("격자 ↔ 위경도 왕복", float(np.abs(gx - np.arange(300)[None, :]).max()) < 1e-6
          and float(np.abs(gy - np.arange(300)[:, None]).max()) < 1e-6)

    yy, xx = np.mgrid[0:300, 0:300]
    cone = 1000.0 - 3.0 * np.hypot(xx - 150, yy - 150)          # 원뿔 산: 남쪽(y 큰 쪽) 사면은 남향
    fuel = mb.rule_based_fuel(cone)
    check("[임시] 사면 규칙: 남향 침엽수·북향 활엽수", fuel[220, 150] == mb.FUEL_CONIFER and fuel[80, 150] == mb.FUEL_BROADLEAF)

    try:
        import shapefile  # noqa: F401
        import pyproj  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        check("산림청 SHP 변환 (pyshp·pyproj·pillow 없음 → 건너뜀)", True)
        return
    mountain_sandbox_import(tmp)


def mountain_sandbox_import(tmp: Path) -> None:
    """시험용 SHP(EPSG:5186, cp949)를 만들어 임시 폴더의 북한산 데이터에 반영하고 엔진으로 실행"""
    from services import forest_import as fi
    from services import mountain_builder as mb
    from services.result_loader import read_asc

    root = tmp / "sandbox"
    shutil.copytree(PROJECT_ROOT / "data" / "mountains", root / "mountains", ignore=shutil.ignore_patterns("_cache"))
    shutil.copytree(PROJECT_ROOT / "data" / "weather", root / "weather")
    (root / "scenarios").mkdir()
    shutil.copy(SCENARIOS / "fuel_models.csv", root / "scenarios")
    shp = tmp / "shp"
    done = subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "make_test_shp.py"), "--out", str(shp)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not check("시험용 SHP 만들기", done.returncode == 0, done.stderr[-300:]):
        return

    saved = (mb.MOUNTAIN_DIR, mb.REGISTRY_FILE, app_config.SCENARIO_DIR)
    mb.MOUNTAIN_DIR, mb.REGISTRY_FILE = root / "mountains", root / "mountains" / "mountains.json"
    app_config.SCENARIO_DIR = root / "scenarios"
    try:
        trails = fi.import_trails("bukhansan", shp / "test_trails.shp", shp / "test_spots.shp")
        text = (root / "mountains" / "bukhansan" / "trails.txt").read_text(encoding="utf-8")
        check("등산로 변환: 노드·간선·지점 이름", trails["nodes"] >= 8 and trails["edges"] >= 8
              and "SUMMIT   149 149 백운대" in text and "SHELTER" in text and "지도경계동" in text, text[:400])
        check("등산로 변환: 길에서 먼 지점은 붙이지 않음", "길에서먼쉼터" not in text)
        forest = fi.import_forest("bukhansan", shp / "test_forest.shp",
                                  fuel_map_path=root / "mountains" / "forest_fuel_map.csv")
        fuel = read_asc(root / "mountains" / "bukhansan" / "fuel.asc")[1]
        rule = mb.rule_based_fuel(read_asc(root / "mountains" / "bukhansan" / "elev.asc")[1])
        check("임상도 변환: 임종 코드 → 연료 코드, 구멍, 덮지 않은 곳은 [임시] 규칙",
              fuel[100, 200] == 3 and fuel[100, 100] == 4 and fuel[230, 120] == 5 and fuel[216, 83] == 1
              and fuel[180, 200] == 2 and fuel[260, 260] == rule[260, 260], str(forest))
        from services.forest_import import sheet_number
        check("1:5,000 도엽 번호 계산 (육지·제주)", sheet_number(37.09, 128.69) == "37815068" and sheet_number(37.09, 128.76) == "37816061"
              and sheet_number(33.3375, 126.654) == "33611030")      # 제주는 기준점이 다름
        scenario = root / "scenarios" / "mountain_bukhansan.ini"
        code, out = run_engine(scenario, "evac", tmp / "sandbox_out")
        check("변환한 데이터로 엔진 대피 계산", code == 0 and "등산객 읽기 완료: 5팀" in out, out[-300:])
    finally:
        mb.MOUNTAIN_DIR, mb.REGISTRY_FILE, app_config.SCENARIO_DIR = saved


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
        test_python_helpers(tmp)
        test_real_mountains(tmp)

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} 통과")
    if failed:
        print("실패한 시험: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
