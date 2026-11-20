"""
프로그램 경로 설정

GUI가 사용하는 폴더 위치를 한 곳에서 정한다.
C 엔진은 항상 c_core 폴더를 작업 폴더(cwd)로 실행하므로,
엔진이 출력하는 상대 경로도 c_core 폴더 기준으로 해석한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = PROJECT_ROOT / "c_core"
DATA_DIR = PROJECT_ROOT / "data"
SCENARIO_DIR = DATA_DIR / "scenarios"
OUTPUT_DIR = PROJECT_ROOT / "output"
CONFIG_DIR = PROJECT_ROOT / "config"

DEFAULT_SCENARIO = SCENARIO_DIR / "spring_dry_base.ini"
SEASON_PRESET_FILE = SCENARIO_DIR / "season_presets.ini"
GUI_SCENARIO_NAME = "gui_custom"            # GUI에서 바꾼 설정으로 만드는 시나리오 이름


def engine_path() -> Path:
    """C 엔진 실행 파일 경로. (Windows: wildfire.exe, 그 외: wildfire)"""
    name = "wildfire.exe" if sys.platform.startswith("win") else "wildfire"
    return ENGINE_DIR / "bin" / name


def resolve_engine_path(path_text: str) -> Path:
    """엔진이 출력한 경로(c_core 기준 상대 경로일 수 있음)를 실제 경로로 바꾼다."""
    path = Path(path_text)
    if not path.is_absolute():
        path = ENGINE_DIR / path
    return path.resolve()


def list_scenarios() -> list[Path]:
    """GUI에서 고를 수 있는 시나리오 목록 (테스트용·GUI 생성 파일 제외)."""
    files = sorted(SCENARIO_DIR.glob("*.ini"))
    return [f for f in files if f.stem != GUI_SCENARIO_NAME and f.name != SEASON_PRESET_FILE.name]
