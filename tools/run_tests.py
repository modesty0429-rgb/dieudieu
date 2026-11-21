"""
자동 테스트: C 엔진과 Python 도우미가 제대로 동작하는지 한 번에 확인한다.

실행 (프로젝트 폴더에서, C 엔진을 먼저 빌드해 둘 것):
    python tools/run_tests.py

시험 항목
  [엔진]  정상 시나리오 4개가 종료 코드 0으로 끝나고 결과 파일을 만드는지
          오류 시나리오 5개가 종료 코드 1로 끝나고 [ERROR] 메시지를 내는지
          같은 시드로 두 번 실행하면 결과가 같은지 (재현성)
          경계 조건 (등산객 없음, 진화 자원 0, 불이 안 붙음, 젖은 연료)
  [Python] 기상청 격자 변환, 기상 응답 해석, 시나리오 파일 쓰기, 결과 읽기, 리포트 만들기

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


def main() -> int:
    exe = app_config.engine_path()
    print(f"엔진: {exe}")
    if not exe.exists():
        print("엔진 실행 파일이 없습니다. c_core 폴더에서 build.bat (또는 build.sh)을 먼저 실행하세요.")
        return 1
    with tempfile.TemporaryDirectory(prefix="wildfire_test_") as folder:
        tmp = Path(folder)
        test_engine_scenarios(tmp)
        test_engine_errors(tmp)
        test_reproducibility(tmp)
        test_edge_cases(tmp)
        test_python_helpers(tmp)

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} 통과")
    if failed:
        print("실패한 시험: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
