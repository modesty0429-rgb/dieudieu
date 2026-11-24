"""
프로그램 경로 설정

GUI가 사용하는 폴더 위치를 한 곳에서 정한다.
C 엔진은 항상 c_core 폴더를 작업 폴더(cwd)로 실행하므로,
엔진이 출력하는 상대 경로도 c_core 폴더 기준으로 해석한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

# 묶은 앱(make_app.bat 으로 만든 exe)이면 exe 가 있는 폴더, 아니면 저장소 폴더
FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[2]
ENGINE_DIR = PROJECT_ROOT / "c_core"
DATA_DIR = PROJECT_ROOT / "data"
SCENARIO_DIR = DATA_DIR / "scenarios"
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_DIR = PROJECT_ROOT / "config"

DEFAULT_SCENARIO = SCENARIO_DIR / "mountain_bukhansan.ini"     # GUI 를 처음 열 때 고르는 산
SEASON_PRESET_FILE = SCENARIO_DIR / "season_presets.ini"
GUI_SCENARIO_NAME = "gui_custom"            # GUI에서 바꾼 설정으로 만드는 시나리오 이름


ENGINE_NAME = "wildfire.exe" if sys.platform.startswith("win") else "wildfire"


def expected_engine_path() -> Path:
    """build.bat 이 엔진을 만드는 위치: c_core/bin/wildfire.exe"""
    return ENGINE_DIR / "bin" / ENGINE_NAME


def engine_path() -> Path:
    """
    실제로 쓸 C 엔진 실행 파일 경로.
      1) c_core/bin/wildfire.exe (build.bat 결과)
      2) 없으면 c_core 안의 다른 곳에서 찾은 wildfire.exe 중 가장 최근 것
         (Visual Studio 빈 프로젝트로 빌드하면 x64/Debug 같은 폴더에 생기기 때문)
    어디에도 없으면 1)의 경로를 돌려준다. (오류 메시지에 이 경로를 보여 줌)
    """
    expected = expected_engine_path()
    if expected.exists():
        return expected
    found = [p for p in ENGINE_DIR.rglob(ENGINE_NAME) if p.is_file()]
    if found:
        return max(found, key=lambda p: p.stat().st_mtime)
    return expected


def resolve_engine_path(path_text: str) -> Path:
    """엔진이 출력한 경로(c_core 기준 상대 경로일 수 있음)를 실제 경로로 바꾼다."""
    path = Path(path_text)
    if not path.is_absolute():
        path = ENGINE_DIR / path
    return path.resolve()


def list_scenarios() -> list[Path]:
    """GUI에서 고를 수 있는 시나리오 목록 (테스트용·GUI 생성 파일 제외)."""
    # 실제 산(mountain_<id>.ini)만, data/mountains/mountains.json 의 순서대로.
    # 처음에 만든 가상 산 시나리오(spring_dry_base 등)는 자동 테스트·명령줄 예시용으로만 남겨 두고 목록에서는 뺀다.
    import json

    order: list[str] = []
    registry = DATA_DIR / "mountains" / "mountains.json"
    if registry.exists():
        order = [m["id"] for m in json.loads(registry.read_text(encoding="utf-8"))["mountains"]]
    files = list(SCENARIO_DIR.glob("mountain_*.ini"))
    rank = {f"mountain_{mid}": i for i, mid in enumerate(order)}
    return sorted(files, key=lambda f: (rank.get(f.stem, len(rank)), f.stem))
