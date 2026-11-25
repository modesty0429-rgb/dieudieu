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
          등산객 팀 (10팀, 등산로 가운데 찍은 위치에서 출발)
  [휴대폰] WebAssembly 엔진·발화 정보 링크·등산로 붙이기 (node tools/mobile_test.mjs), PC 링크 → 휴대폰 좌표
  [Python] 기상청 격자 변환, 기상 응답 해석, 시나리오 파일 쓰기, 결과 읽기, 리포트 만들기,
           계절 지도 색
  [과거 날씨] 가까운 관측소, 기간 검사, ASOS 응답 해석·빈 값 채우기, 저장 → 엔진 실행
  [실제 산] 산 시나리오 6개 실행, 격자↔위경도, [임시] 연료 규칙, OSM 선 좌표, 등산로 빈틈 잇기,
          시험용 산림청 SHP(등산로·임상도) 변환 → 엔진 실행 (pyshp·pyproj·pillow 가 있을 때)

결과는 항목마다 "통과 / 실패"로 출력되고, 하나라도 실패하면 종료 코드 1.
(외부 테스트 도구 없이 표준 라이브러리 + numpy 만 사용)
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import re
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "gui"))

from services import app_config  # noqa: E402

SCENARIOS = app_config.SCENARIO_DIR
BASE = SCENARIOS / "mountain_bukhansan.ini"                 # 시험 기준: 북한산 (실제 지형·임상도·산림청 등산로)
BUKHANSAN = app_config.DATA_DIR / "mountains" / "bukhansan"
IGNITION = "98, 142"                                      # 북한산 기본 발화 지점 (숲 한가운데)
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


def write_variant(name: str, extra: str) -> Path:
    """
    북한산 시나리오에 설정을 덧붙인 시험용 시나리오 (data/scenarios/zz_test_<name>.ini, 쓰고 나면 지울 것).
    산 시나리오의 상대 경로(../mountains/...)가 그대로 맞도록 같은 폴더에 만든다. 같은 구역을 다시 쓰면 뒤의 값이 이긴다.
    """
    path = SCENARIOS / f"zz_test_{name}.ini"
    path.write_text(BASE.read_text(encoding="utf-8") + "\n" + extra, encoding="utf-8")
    return path


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# ----------------------------------------------------------------------
# 엔진 시험
# ----------------------------------------------------------------------
def test_engine_scenarios(tmp: Path) -> None:
    print("\n[엔진] 정상 시나리오")
    calm = write_variant("calm", "[weather]\nmode = fixed\nfixed_wind_speed_ms = 0\n")   # 무풍: 경사 효과만
    cases = [(BASE, "all", ["summary.json", "evacuation.json", "suppression.json",
                            "mc_summary.json", "burn_probability.csv"]),
             (BASE, "evac", ["summary.json", "evacuation.json"]),
             (calm, "run", ["summary.json", "arrival_time.csv", "stats.csv"]),
             (BASE, "printmap", [])]
    try:
        for path, mode, files in cases:
            out = tmp / f"{path.stem}_{mode}"
            extra = ["--seed", "7"] if mode == "all" else []
            code, text = run_engine(path, mode, out, extra)
            missing = [f for f in files if not (out / f).exists()]
            check(f"{path.stem} --mode {mode}", code == 0 and not missing and "[ERROR]" not in text,
                  f"종료 코드 {code}, 없는 파일 {missing}")
    finally:
        calm.unlink(missing_ok=True)


def test_engine_errors(tmp: Path) -> None:
    print("\n[엔진] 오류 시나리오 (종료 코드 1 + [ERROR] 메시지가 나와야 함)")
    for name in ["bad_values", "bad_ignition", "missing_file", "bad_trail", "bad_weather"]:
        code, text = run_engine(SCENARIOS / "tests" / f"{name}.ini", "run", tmp / name)
        check(f"tests/{name}.ini", code == 1 and "[ERROR]" in text, f"종료 코드 {code}")
    code, text = run_engine(BASE, "run", None, ["--seed", "-3"])
    check("잘못된 명령줄 인자 (--seed -3)", code == 1 and "사용법" in text, f"종료 코드 {code}")


def test_reproducibility(tmp: Path) -> None:
    print("\n[엔진] 재현성 (같은 시드 → 같은 결과)")
    # 비화(불씨 날림)가 생겨야 난수가 결과에 영향을 주므로 강풍·건조한 날로 시험
    windy = write_variant("windy", "[weather]\nmode = fixed\nfixed_wind_speed_ms = 11\nfixed_rh_pct = 15\n")
    try:
        hashes = []
        for i in range(2):
            out = tmp / f"repeat{i}"
            run_engine(windy, "run", out)
            hashes.append([file_hash(out / f) for f in ("arrival_time.csv", "burnout_time.csv", "stats.csv")])
        check("두 번 실행한 결과 CSV 3개가 같음", hashes[0] == hashes[1])
        out = tmp / "seed99"
        run_engine(windy, "run", out, ["--seed", "99"])
        check("시드를 바꾸면 결과가 달라짐 (강풍으로 비화가 생기는 날)", file_hash(out / "arrival_time.csv") != hashes[0][0])
    finally:
        windy.unlink(missing_ok=True)


def write_edge_scenario(tmp: Path, name: str, extra: str, with_trails: bool = True) -> Path:
    trails = (f"[trails]\ntrail_file = {BUKHANSAN / 'trails.txt'}\n"
              f"hiker_file = {BUKHANSAN / 'hikers.txt'}\n") if with_trails else ""
    text = (f"[general]\nname = {name}\n[map]\nelevation_file = {BUKHANSAN / 'elev.asc'}\n"
            f"fuel_file = {BUKHANSAN / 'fuel.asc'}\n"
            f"fuel_models = {SCENARIOS / 'fuel_models.csv'}\n{trails}"
            f"[weather]\nmode = fixed\n[time]\nduration_min = 120\n[montecarlo]\nruns = 5\n{extra}")
    path = tmp / f"{name}.ini"
    path.write_text(text, encoding="utf-8")
    return path


def test_edge_cases(tmp: Path) -> None:
    print("\n[엔진] 경계 조건 (--mode all)")
    cases = [
        ("no_trails", "[ignition]\npoint1 = " + IGNITION + "\n", False, "불이 꺼짐|연소 중"),
        ("zero_resources", "[ignition]\npoint1 = " + IGNITION + "\n[suppression]\nfirebreak_cells = 0\nhelicopters = 0\n",
         True, "연소 중|불이 꺼짐"),
        ("no_fire", "[ignition]\npoint1 = " + IGNITION + ", 500\n", True, "불이 붙지 않음"),
        ("too_wet", "[ignition]\npoint1 = " + IGNITION + "\n[moisture]\ninitial_dead_moisture_pct = 40\n"
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
        code, text = run_engine(data / "scenarios" / BASE.name, "evac", out)
        ok = code == 0 and (out / "arrival_time.csv").exists()
        check(f"{style.upper()} 입력 파일로 실행", ok, f"종료 코드 {code} {text[-200:] if not ok else ''}")
        if ok:
            results_by_style[style] = file_hash(out / "arrival_time.csv")
    check("LF·CRLF 결과가 같음", len(results_by_style) == 2 and len(set(results_by_style.values())) == 1)


def test_daylight(tmp: Path) -> None:
    """
    (8단계) 낮/밤: 일몰 시각 계산, 밤 헬기 출동 중지, 밤 보행 속도, 잘못된 설정값.
    북한산에서 저녁(18:00)에 불이 난 상황을 [daylight] enabled = 1 / 0 으로 각각 실행해 비교한다.
    """
    import json
    print("\n[엔진] 낮/밤 (8단계)")

    evening = ("[time]\nstart_datetime = 2026-04-05 18:00\nduration_min = 360\n"      # 18:00 ~ 24:00
               "[weather]\nmode = fixed\nfixed_temp_c = 16\nfixed_rh_pct = 15\n"
               "fixed_wind_speed_ms = 11\nfixed_wind_dir_deg = 225\n"                   # 밤까지 이어지는 남서 강풍
               "[evacuation]\nnotify_delay_min = 30\n[daylight]\nenabled = 1\n")
    on_path = write_variant("daylight_on", evening)
    out_on = tmp / "daylight_on"
    try:
        code, text = run_engine(on_path, "optimize", out_on)
    finally:
        on_path.unlink(missing_ok=True)
    summary = json.loads((out_on / "summary.json").read_text(encoding="utf-8")) if code == 0 else {}
    events = summary.get("daylight", {}).get("events", [])
    sunset = next((e for e in events if e["type"] == "sunset"), None)
    # 2026-04-05, 북위 37.5° 동경 127° 의 일몰은 약 18:57 (천문 계산 라이브러리 astral 과 1분 이내로 일치)
    check("일몰 시각 계산 (4월 5일 중부 지방 약 18:57)",
          sunset is not None and "18:54" <= sunset["clock"] <= "19:00", f"계산 결과 {sunset}")

    off_copy = write_variant("daylight_off", evening.replace("enabled = 1", "enabled = 0"))
    try:
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

    bad = write_edge_scenario(tmp, "bad_daylight", "[ignition]\npoint1 = " + IGNITION + "\n[daylight]\nnight_walk_factor = 5\n")
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
            f"[ignition]\npoint1 = {IGNITION}\n[weather]\nmode = season\n[season]\nseason = {key}\n{extra}")
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
        # 눈 위 발화 지점은 가장 가까운 눈 없는 숲으로 옮겨서 실행
        y, x = (int(v) for v in np.argwhere(snowy)[0])
        moved = write_edge_scenario(tmp, "season_snow_ignition",
                                    f"[ignition]\npoint1 = {x}, {y}\n[season]\nseason = winter\n")
        code, text = run_engine(moved, "run", tmp / "season_snow_ignition")
        ok = code == 0 and "옮김" in text
        if ok:
            moved_summary = json.loads((tmp / "season_snow_ignition" / "summary.json").read_text(encoding="utf-8"))
            point = moved_summary["ignitions"][0]
            ok = result.map.elevation[point["y"], point["x"]] < line
        check("눈 덮인 곳의 발화 지점은 눈 아래 숲으로 옮겨 실행", ok, f"종료 코드 {code}")
    except (OSError, KeyError, ValueError, IndexError) as error:
        check("겨울 결과 읽기", False, str(error))

    bad = write_edge_scenario(tmp, "bad_season", "[ignition]\npoint1 = " + IGNITION + "\n[season]\nseason = monsoon\n")
    code, text = run_engine(bad, "run", tmp / "bad_season")
    check("잘못된 계절 이름은 오류 (season = monsoon)", code == 1 and "season" in text, f"종료 코드 {code}")


def test_mountain_winter(tmp: Path) -> None:
    """실제 산 6곳 모두 겨울로 실행된다 (산마다 다른 눈 경계, 눈 위 발화 지점은 옮김)"""
    import json
    print("\n[엔진] 실제 산 겨울 (산마다 눈 경계)")
    results = []
    for path in sorted(SCENARIOS.glob("mountain_*.ini")):
        scenario = SCENARIOS / f"zz_test_winter_{path.stem}.ini"
        scenario.write_text(path.read_text(encoding="utf-8") +
                            "\n[weather]\nmode = season\n[time]\nduration_min = 120\n"
                            "[season]\nseason = winter\n", encoding="utf-8")
        try:
            code, _text = run_engine(scenario, "run", tmp / scenario.stem)
        finally:
            scenario.unlink()
        if code != 0:
            results.append((path.stem, None))
            continue
        season = json.loads((tmp / scenario.stem / "summary.json").read_text(encoding="utf-8"))["season"]
        results.append((path.stem, season["snow_line_m"]))
    failed = [name for name, line in results if line is None]
    check("실제 산 6곳 모두 겨울로 실행됨", len(results) == 6 and not failed, f"실패: {failed}")
    lines = dict(results)
    check("산마다 눈 경계가 다름 (지리산 > 북한산)",
          (lines.get("mountain_jirisan") or 0) > (lines.get("mountain_bukhansan") or 0) > 0, str(lines))


def test_mobile(tmp: Path) -> None:
    """(11단계) 휴대폰 앱: 같은 C 코드를 WebAssembly 로 돌려 PC 와 같은 결과인지, PC 가 만든 링크를 휴대폰이 읽는지"""
    import shutil
    import subprocess
    print("\n[휴대폰] 오프라인 대피 안내 앱 (11단계)")
    ROOT = app_config.PROJECT_ROOT
    node = shutil.which("node")
    wasm = ROOT / "mobile" / "engine" / "wildfire.wasm"
    if node is None or not wasm.exists():
        print("  [건너뜀] node 또는 mobile/engine/wildfire.wasm 이 없음 (tools/build_wasm.sh)")
        return
    out = subprocess.run([node, str(ROOT / "tools" / "mobile_test.mjs")], capture_output=True, text=True,
                         encoding="utf-8", timeout=300)
    for line in out.stdout.splitlines():
        if line.strip().startswith(("[통과]", "[실패]")):
            check("휴대폰 " + line.strip()[5:].strip(), line.strip().startswith("[통과]"))

    from datetime import datetime
    from services import mobile_link
    message = mobile_link.build_message(SCENARIOS / "mountain_bukhansan.ini", 98, 142,
                                        datetime(2026, 4, 5, 13, 0), (6, 270, 25, 18))
    script = ("const R=process.argv[1];const {decodeFire}=await import(R+'/mobile/js/fireinfo.js');"
              "const {latLonToCell}=await import(R+'/mobile/js/geo.js');const fs=await import('node:fs');"
              "const meta=JSON.parse(fs.readFileSync(R+'/mobile/assets/bukhansan/meta.json','utf8'));"
              "const f=decodeFire(process.argv[2]);const c=latLonToCell(meta,f.lat,f.lon);"
              "console.log(Math.round(c.x),Math.round(c.y),f.time.getHours(),f.weather.windDir);")
    rt = subprocess.run([node, "--input-type=module", "-e", script, str(ROOT), message.sms_text()],
                        capture_output=True, text=True, timeout=60)
    check("PC 가 만든 문자·링크 → 휴대폰이 같은 발화 칸·시각·바람으로 읽음", rt.stdout.split() == ["98", "142", "13", "270"],
          rt.stdout.strip() or rt.stderr[-200:])

    # WebAssembly 엔진과 PC 엔진이 같은 결과인지 (같은 C 코드)
    run_wasm = ("import fs from 'node:fs';const R=process.argv[1];"
                "const {runEngine}=await import(R+'/mobile/js/engine_core.js');"
                "const m=await WebAssembly.compile(fs.readFileSync(R+'/mobile/engine/wildfire.wasm'));"
                "const rd=(p)=>fs.readFileSync(R+'/'+p);"
                "const files={'scenario.ini':rd('data/scenarios/mountain_bukhansan.ini'),'fuel_models.csv':rd('data/scenarios/fuel_models.csv'),"
                "'elev.asc':rd('data/mountains/bukhansan/elev.asc'),'fuel.asc':rd('data/mountains/bukhansan/fuel.asc'),"
                "'trails.txt':rd('data/mountains/bukhansan/trails.txt'),'hikers.txt':rd('data/mountains/bukhansan/hikers.txt'),"
                "'sample_spring_dry.csv':rd('data/weather/sample_spring_dry.csv')};"
                "const r=await runEngine(m,files,['--mode','evac']);fs.writeFileSync(process.argv[2],r.outputs['arrival_time.csv']||'');")
    ini = BASE.read_text(encoding="utf-8")
    flat = re.sub(r"=\s*(\.\./)+[\w/]*?([\w.]+\.(asc|txt|csv))", r"= \2", ini)
    work = tmp / "wasm_compare"
    work.mkdir(exist_ok=True)
    (work / BASE.name).write_text(flat, encoding="utf-8")
    script2 = run_wasm.replace("rd('data/scenarios/mountain_bukhansan.ini')", f"fs.readFileSync({str(work / BASE.name)!r})")
    wasm_csv = work / "wasm_arrival.csv"
    subprocess.run([node, "--input-type=module", "-e", script2, str(ROOT), str(wasm_csv)],
                   capture_output=True, text=True, timeout=120)
    code, _ = run_engine(BASE, "evac", work / "native")
    native = (work / "native" / "arrival_time.csv")
    check("휴대폰(WebAssembly) 엔진 = PC 엔진 (불 도착 시각 9만 칸이 모두 같음)",
          code == 0 and wasm_csv.exists() and native.exists()
          and wasm_csv.read_text().strip() == native.read_text().strip())


def test_hiker_teams(tmp: Path) -> None:
    """
    (10단계) 등산객 팀 수 1~10, 팀마다 위치 바꾸기.
    GUI와 같은 방법(hiker_setup)으로 10팀 + 등산로 가운데 위치를 만들고 엔진이 그대로 받는지 본다.
    """
    import json
    print("\n[엔진] 등산객 팀 (10단계)")
    from services import hiker_setup as hs
    from services.result_loader import load_scenario_preview

    preview = load_scenario_preview(BASE)
    teams = hs.resize_teams(hs.teams_from_hikers(preview.hikers, preview.nodes), 12, preview.nodes)
    check("팀 수는 최대 10팀", len(teams) == hs.MAX_TEAMS)
    check("팀 수는 최소 1팀", len(hs.resize_teams(teams, 0, preview.nodes)) == hs.MIN_TEAMS)

    # 북한산 등산로에서 시험 좌표 고르기: 노드에서 멀리 떨어진 간선 가운데 점 2개, 노드 바로 옆, 등산로에서 먼 곳
    def mid_points():
        for edge in preview.edges:
            for x, y in edge.points[1:-1]:
                if min((n.x - x) ** 2 + (n.y - y) ** 2 for n in preview.nodes) >= 6 ** 2:
                    yield x, y
                    break
    (mx1, my1), (mx2, my2) = list(mid_points())[:2]
    node7 = next(n for n in preview.nodes if n.kind == "JUNCTION")
    far_xy = next((x, y) for x in range(0, 300, 7) for y in range(0, 300, 7)
                  if hs.snap_to_trail(preview.nodes, preview.edges, x, y) is None)
    snap = hs.snap_to_trail(preview.nodes, preview.edges, mx1, my1)
    far = hs.snap_to_trail(preview.nodes, preview.edges, *far_xy)
    near_node = hs.snap_to_trail(preview.nodes, preview.edges, node7.x + 1, node7.y)
    check("등산로 위 가장 가까운 점 (가운데 / 노드 근처 / 너무 멂)",
          snap is not None and snap.node_id is None and far is None
          and near_node is not None and near_node.node_id == node7.id)

    teams[5] = hs.copy_team(teams[5], node_id=None, x=mx1, y=my1)
    teams[6] = hs.copy_team(teams[6], node_id=None, x=mx2, y=my2)
    teams[7] = hs.copy_team(teams[7], node_id=None, x=mx1, y=my1)       # 6번 팀과 같은 자리
    nodes, edges, hikers = hs.build_layout(preview.nodes, preview.edges, teams)
    new_ids = {n.id for n in nodes} - {n.id for n in preview.nodes}
    check("찍은 곳에서 등산로를 나눔 (새 지점 2개, 간선 +2, 같은 자리는 같은 지점)",
          len(new_ids) == 2 and len(edges) == len(preview.edges) + 2 and hikers[5].node_id == hikers[7].node_id)

    trail_file, hiker_file = tmp / "teams_trails.txt", tmp / "teams_hikers.txt"
    hs.write_trail_file(trail_file, nodes, edges)
    hs.write_hiker_file(hiker_file, hikers)
    scenario = write_edge_scenario(tmp, "teams10", f"[ignition]\npoint1 = {IGNITION}\n", with_trails=False)
    scenario.write_text(scenario.read_text(encoding="utf-8") +
                        f"[trails]\ntrail_file = {trail_file}\nhiker_file = {hiker_file}\n", encoding="utf-8")
    code, text = run_engine(scenario, "evac", tmp / "teams10")
    ok = code == 0 and (tmp / "teams10" / "evacuation.json").exists()
    check("엔진이 10팀 + 나눈 등산로를 받음", ok, f"종료 코드 {code} {text[-300:] if not ok else ''}")
    if ok:
        evac = json.loads((tmp / "teams10" / "evacuation.json").read_text(encoding="utf-8"))
        starts = [h.get("start_node") for h in evac["hikers"]]
        check("대피 결과 10팀, 찍은 지점에서 출발",
              len(evac["hikers"]) == 10 and any(s in new_ids for s in starts), f"출발 노드 {starts}")


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
        shutil.copy(BASE, scenario_copy)
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

    summary = tmp / f"{BASE.stem}_all" / "summary.json"
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

    import struct
    from services.forest_import import Edge, Node, bridge_gaps
    from services.overture_trails import wkb_lines
    line = struct.pack("<BII", 1, 2, 2) + struct.pack("<4d", 126.5, 33.3, 126.6, 33.4)
    multi = struct.pack("<BII", 1, 5, 2) + line + line
    check("OSM 선 좌표(WKB) 읽기", wkb_lines(line) == [[(126.5, 33.3), (126.6, 33.4)]] and len(wkb_lines(multi)) == 2)
    nodes = [Node(0, 0), Node(10, 0), Node(15, 0), Node(30, 0)]
    edges = [Edge(0, 1, [(0, 0), (10, 0)]), Edge(2, 3, [(15, 0), (30, 0)])]
    check("등산로 빈틈 잇기 (5칸 → 이음)", bridge_gaps(nodes, edges) == 1 and len(edges) == 3)

    try:
        import shapefile  # noqa: F401
        import pyproj  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        check("산림청 SHP 변환 (pyshp·pyproj·pillow 없음 → 건너뜀)", True)
        return
    mountain_sandbox_import(tmp)


def mountain_sandbox_import(tmp: Path) -> None:
    """시험용 SHP(EPSG:5186, cp949)를 만들어 임시 폴더의 설악산(300×300칸) 데이터에 반영하고 엔진으로 실행"""
    from services import forest_import as fi
    from services import mountain_builder as mb
    from services.result_loader import read_asc

    root = tmp / "sandbox"
    shutil.copytree(PROJECT_ROOT / "data" / "mountains", root / "mountains", ignore=shutil.ignore_patterns("_cache"))
    shutil.copytree(PROJECT_ROOT / "data" / "weather", root / "weather")
    (root / "scenarios").mkdir()
    shutil.copy(SCENARIOS / "fuel_models.csv", root / "scenarios")
    shp = tmp / "shp"
    done = subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "make_test_shp.py"), "--id", "seoraksan", "--out", str(shp)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not check("시험용 SHP 만들기", done.returncode == 0, done.stderr[-300:]):
        return

    saved = (mb.MOUNTAIN_DIR, mb.REGISTRY_FILE, app_config.SCENARIO_DIR)
    mb.MOUNTAIN_DIR, mb.REGISTRY_FILE = root / "mountains", root / "mountains" / "mountains.json"
    app_config.SCENARIO_DIR = root / "scenarios"
    try:
        trails = fi.import_trails("seoraksan", shp / "test_trails.shp", shp / "test_spots.shp")
        text = (root / "mountains" / "seoraksan" / "trails.txt").read_text(encoding="utf-8")
        check("등산로 변환: 노드·간선·지점 이름", trails["nodes"] >= 8 and trails["edges"] >= 8
              and "SUMMIT   149 149 백운대" in text and "SHELTER" in text and "지도경계동" in text, text[:400])
        check("등산로 변환: 길에서 먼 지점은 붙이지 않음", "길에서먼쉼터" not in text)
        forest = fi.import_forest("seoraksan", shp / "test_forest.shp",
                                  fuel_map_path=root / "mountains" / "forest_fuel_map.csv")
        fuel = read_asc(root / "mountains" / "seoraksan" / "fuel.asc")[1]
        rule = mb.rule_based_fuel(read_asc(root / "mountains" / "seoraksan" / "elev.asc")[1])
        check("임상도 변환: 임종 코드 → 연료 코드, 구멍, 덮지 않은 곳은 [임시] 규칙",
              fuel[100, 200] == 3 and fuel[100, 100] == 4 and fuel[230, 120] == 5 and fuel[216, 83] == 1
              and fuel[180, 200] == 2 and fuel[260, 260] == rule[260, 260], str(forest))
        from services.forest_import import sheet_number
        check("1:5,000 도엽 번호 계산 (육지·제주)", sheet_number(37.09, 128.69) == "37815068" and sheet_number(37.09, 128.76) == "37816061"
              and sheet_number(33.3375, 126.654) == "33611030")      # 제주는 기준점이 다름
        scenario = root / "scenarios" / "mountain_seoraksan.ini"
        code, out = run_engine(scenario, "evac", tmp / "sandbox_out")
        check("변환한 데이터로 엔진 대피 계산", code == 0 and "등산객 읽기 완료" in out and "[ERROR]" not in out, out[-300:])
    finally:
        mb.MOUNTAIN_DIR, mb.REGISTRY_FILE, app_config.SCENARIO_DIR = saved


def test_past_weather(tmp: Path) -> None:
    """과거 관측(ASOS) 받기: 가짜 응답(공식 응답 형식)으로 해석·빈 값 채우기·저장·엔진 실행까지"""
    print("\n[과거 날씨] 기상청 ASOS 시간자료")
    import json
    from datetime import datetime
    from services import weather_api as w

    near = w.nearest_stations(37.6584, 126.9779)
    check("가까운 관측소 (북한산 → 서울)", near[0][0].name == "서울" and near[0][1] < 15)
    try:
        w.check_past_period(datetime(2026, 11, 21, 13), 10, now=datetime(2026, 11, 21, 15))
        future_ok = False
    except w.WeatherApiError:
        future_ok = True
    check("오늘 이후 기간은 거절", future_ok)

    items = []
    for h in range(10):
        items.append({"tm": f"2025-04-05 {13 + h:02d}:00", "stnId": "108", "stnNm": "서울",
                      "ta": f"{20 - h * 0.5:.1f}", "hm": str(20 + h), "ws": f"{5 + h * 0.2:.1f}", "wd": "270"})
    items[3]["ta"] = ""          # 빈 값: 앞뒤로 보간
    items[4]["wd"] = ""          # 빈 풍향: 앞 값 유지
    body = json.dumps({"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                                    "body": {"dataType": "JSON", "items": {"item": items}, "totalCount": 10}}})
    rows, name, gaps = w.parse_asos(w.extract_items(body))
    check("ASOS 응답 해석 (빈 값 보간)", len(rows) == 10 and name == "서울" and gaps == 2
          and abs(rows[3].temp_c - 18.5) < 1e-6 and rows[4].wind_dir_deg == 270)
    no_data = json.dumps({"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}})
    try:
        w.extract_items(no_data)
        nodata_ok = False
    except w.WeatherApiError as error:
        nodata_ok = "자료가 없습니다" in str(error)
    check("자료 없음(03) 안내", nodata_ok)

    saved = (w.request_items, w.load_api_key)
    w.request_items = lambda url, key, params, timeout_sec=15.0: w.extract_items(body)
    w.load_api_key = lambda path=None: "TEST_KEY"
    try:
        path, rows, text = w.download_past_weather(108, datetime(2025, 4, 5, 13), 10, out_dir=tmp)
    finally:
        w.request_items, w.load_api_key = saved
    ini = (SCENARIOS / "mountain_bukhansan.ini").read_text(encoding="utf-8")
    ini = ini.replace("file = ../weather/sample_spring_dry.csv", f"file = {path.as_posix()}")
    ini = ini.replace("start_datetime      = 2026-04-05 13:00", "start_datetime      = 2025-04-05 13:00")
    scenario = SCENARIOS / "_test_past_weather.ini"
    scenario.write_text(ini, encoding="utf-8")
    try:
        code, out = run_engine(scenario, "run", tmp / "past_weather")
    finally:
        scenario.unlink()
    check("받은 과거 날씨로 엔진 실행", code == 0 and len(w.read_weather_csv(path)) == 10 and "[ERROR]" not in out,
          out[-300:])


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
        test_mountain_winter(tmp)
        test_hiker_teams(tmp)
        test_mobile(tmp)
        test_python_helpers(tmp)
        test_real_mountains(tmp)
        test_past_weather(tmp)

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n결과: {len(results) - len(failed)}/{len(results)} 통과")
    if failed:
        print("실패한 시험: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
