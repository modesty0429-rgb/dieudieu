"""
시나리오 파일 읽기·쓰기

GUI에서 바꾼 설정(발화 지점, 계절, 바람, 습도 ...)을 C 엔진이 읽는 .ini 파일로 저장한다.

원본 시나리오 파일을 한 줄씩 복사하면서 바꿀 값만 교체하므로
원본의 주석([근거]/[가정] 표시)이 그대로 남는다.
"""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path

from services import app_config

SECTION_PATTERN = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*$")
KEY_PATTERN = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_]+)(?P<sep>\s*=\s*)(?P<value>[^#]*?)(?P<comment>\s*#.*)?$")


def read_ini(path: Path) -> configparser.ConfigParser:
    """C 엔진과 같은 규칙(# 주석, 키 = 값)으로 .ini 파일을 읽는다."""
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",), interpolation=None)
    parser.read(path, encoding="utf-8-sig")
    return parser


@dataclass
class SeasonPreset:
    """계절 프리셋 (data/scenarios/season_presets.ini 한 구역)"""
    key: str
    label: str
    live_moisture_factor: float
    initial_dead_moisture_pct: float
    temp_c: float
    rh_pct: float
    wind_speed_ms: float
    wind_dir_deg: float
    note: str = ""
    date: str = ""            # 계절 대표 날짜 YYYY-MM-DD (일출·일몰, 평년 기후 선택)
    snow_line_m: float = 0.0  # 눈 경계 고도 (0 이면 눈 없음)


def load_season_presets(path: Path = app_config.SEASON_PRESET_FILE) -> list[SeasonPreset]:
    """계절 프리셋 목록을 읽는다. 파일이 없으면 빈 목록."""
    if not path.exists():
        return []
    parser = read_ini(path)
    presets = []
    for key in parser.sections():
        s = parser[key]
        presets.append(SeasonPreset(
            key=key,
            label=s.get("label", key),
            live_moisture_factor=s.getfloat("live_moisture_factor", 1.0),
            initial_dead_moisture_pct=s.getfloat("initial_dead_moisture_pct", 8.0),
            temp_c=s.getfloat("temp_c", 18.0),
            rh_pct=s.getfloat("rh_pct", 30.0),
            wind_speed_ms=s.getfloat("wind_speed_ms", 5.0),
            wind_dir_deg=s.getfloat("wind_dir_deg", 270.0),
            note=s.get("note", ""),
            date=s.get("date", ""),
            snow_line_m=s.getfloat("snow_line_m", 0.0),
        ))
    return presets


@dataclass
class ScenarioOverrides:
    """
    원본 시나리오에서 바꿀 값들. 값이 None 이면 원본 그대로 둔다.
    키는 (구역, 키) 형태로 C 엔진의 .ini 와 같다.
    """
    values: dict[tuple[str, str], str] = field(default_factory=dict)
    ignitions: list[tuple[int, int, float]] | None = None   # None 이면 원본 발화 지점 유지

    def set(self, section: str, key: str, value) -> None:
        if isinstance(value, float):
            value = f"{value:g}"
        self.values[(section.lower(), key.lower())] = str(value)


def apply_overrides(lines: list[str], overrides: ScenarioOverrides) -> list[str]:
    """
    .ini 줄 목록에 바꿀 값을 적용한다.
      1) 이미 있는 키 → 값만 교체 (뒤의 주석은 유지)
      2) 없는 키 → 해당 구역 끝에 추가 (구역이 없으면 파일 끝에 구역을 새로 만듦)
      3) 발화 지점을 바꾸면 [ignition] 구역의 pointN 줄을 모두 새로 쓴다
    """
    remaining = dict(overrides.values)
    result: list[str] = []
    section = ""

    def flush_section(name: str) -> None:
        """구역이 끝나기 직전에, 그 구역에 아직 못 넣은 키를 추가한다."""
        if name == "ignition" and overrides.ignitions is not None:
            for i, (x, y, t) in enumerate(overrides.ignitions, start=1):
                result.append(f"point{i} = {x}, {y}, {t:g}\n")
        for (sec, key) in [k for k in remaining if k[0] == name]:
            result.append(f"{key} = {remaining.pop((sec, key))}\n")

    for line in lines:
        match = SECTION_PATTERN.match(line)
        if match:
            flush_section(section)
            section = match.group("name").strip().lower()
            result.append(line)
            continue

        key_match = KEY_PATTERN.match(line.rstrip("\n"))
        if key_match and section:
            key = key_match.group("key").lower()
            if section == "ignition" and overrides.ignitions is not None and key.startswith("point"):
                continue   # 원본 발화 지점은 지우고 flush_section 에서 새로 씀
            if (section, key) in remaining:
                comment = key_match.group("comment") or ""
                new_value = remaining.pop((section, key))
                result.append(f"{key_match.group('indent')}{key_match.group('key')}"
                              f"{key_match.group('sep')}{new_value}{comment}\n")
                continue
        result.append(line)
    flush_section(section)

    # 원본에 아예 없던 구역
    missing_sections = sorted({sec for sec, _ in remaining})
    if overrides.ignitions is not None and not any(SECTION_PATTERN.match(l) and "ignition" in l.lower()
                                                   for l in lines):
        missing_sections.append("ignition")
    for name in missing_sections:
        result.append(f"\n[{name}]\n")
        flush_section(name)
    return result


def write_scenario(base_path: Path, overrides: ScenarioOverrides,
                   name: str = app_config.GUI_SCENARIO_NAME) -> Path:
    """
    원본 시나리오에 바꿀 값을 적용해 같은 폴더에 <name>.ini 로 저장하고 그 경로를 돌려준다.
    같은 폴더에 저장하므로 원본의 상대 경로(../maps/...)가 그대로 동작한다.
    """
    overrides.set("general", "name", name)
    overrides.set("general", "output_dir", f"../../output/{name}")
    lines = base_path.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    new_lines = [f"# GUI가 '{base_path.name}'을 바탕으로 자동 생성한 파일 (직접 고쳐도 다음 실행 때 덮어씀)\n"]
    new_lines += apply_overrides(lines, overrides)
    out_path = base_path.parent / f"{name}.ini"
    out_path.write_text("".join(new_lines), encoding="utf-8")
    return out_path
