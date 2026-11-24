"""
시나리오 설정 패널 (왼쪽)

    - 기본 시나리오 선택
    - 발화 지점 (숫자 입력 또는 지도 클릭)
    - 계절 프리셋
    - 기상: 시나리오의 기상 파일 / 직접 입력(풍속·풍향·습도·기온 슬라이더)
    - 시뮬레이션 시간, 난수 시드, 비화 사용
    - 진화 자원 (방화선 칸 수, 완성 시각, 헬기 대수, 출동 간격)과 전략 비교 포함 여부
    - 몬테카를로 반복 횟수와 포함 여부
    - 실제 기상 데이터 불러오기 (weather_dialog.py) → 기상 파일·시작 시각 교체
    - 실행 / 중지 버튼

"실행"을 누르면 바꾼 값을 ScenarioOverrides 로 모아 run_requested 시그널을 보낸다.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QRadioButton, QScrollArea, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from services import app_config, mountain_builder
from services.result_loader import parse_datetime, season_from_ini
from views.hiker_group import HikerGroup
from services.scenario_writer import ScenarioOverrides, SeasonPreset, load_season_presets, read_ini
from views.daylight_group import DaylightGroup
from views.weather_dialog import WeatherDialog

WIND_NAMES = ["북풍", "북동풍", "동풍", "남동풍", "남풍", "남서풍", "서풍", "북서풍"]


def wind_direction_name(deg: float) -> str:
    """풍향 각도(불어오는 방향) → '서풍' 같은 이름 (8방위)"""
    return WIND_NAMES[int(((deg % 360) + 22.5) // 45) % 8]


class LabeledSlider(QWidget):
    """슬라이더 + 현재 값 표시. 정수 슬라이더를 scale 로 나눠 실수 값을 만든다."""

    def __init__(self, minimum: float, maximum: float, value: float, scale: int = 1,
                 formatter=None, parent=None):
        super().__init__(parent)
        self.setObjectName("transparent")    # 그룹 상자 배경색이 그대로 보이게
        self.scale = scale
        self.formatter = formatter or (lambda v: f"{v:g}")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(minimum * scale), int(maximum * scale))
        self.label = QLabel()
        self.label.setMinimumWidth(92)
        self.slider.valueChanged.connect(self._update_label)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.label)
        self.set_value(value)

    def value(self) -> float:
        return self.slider.value() / self.scale

    def set_value(self, value: float) -> None:
        self.slider.setValue(int(round(value * self.scale)))
        self._update_label()

    def _update_label(self) -> None:
        self.label.setText(self.formatter(self.value()))


class ScenarioPanel(QScrollArea):
    scenario_changed = Signal(object)          # Path: 기본 시나리오가 바뀜
    season_preview_changed = Signal(object, float)   # (9단계) 계절 키(None 가능), 눈 경계 m
    ignition_changed = Signal(int, int)        # 발화 지점이 바뀜
    run_requested = Signal(object, object)     # (기본 시나리오 Path, ScenarioOverrides)
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setMinimumWidth(360)
        self.presets: list[SeasonPreset] = load_season_presets()
        self.weather_override: tuple[Path, str] | None = None   # (기상 파일, 시작 시각 "YYYY-MM-DD HH:MM")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self._build_scenario_group())
        layout.addWidget(self._build_ignition_group())
        self.hiker_group = HikerGroup()                # (10단계) 등산객 팀 수·위치
        layout.addWidget(self.hiker_group)
        layout.addWidget(self._build_weather_group())
        layout.addWidget(self._build_simulation_group())
        self.daylight_group = DaylightGroup()          # (8단계) 낮/밤
        layout.addWidget(self.daylight_group)
        layout.addWidget(self._build_suppression_group())
        layout.addWidget(self._build_montecarlo_group())
        layout.addWidget(self._build_run_buttons())
        layout.addStretch(1)
        self.setWidget(content)

        self._load_scenario_values(self.current_scenario())
        self._update_mountain_note()

    # ------------------------------------------------------------------
    # 화면 구성
    # ------------------------------------------------------------------
    def _build_scenario_group(self) -> QGroupBox:
        group = QGroupBox("시나리오")
        form = QFormLayout(group)
        self.scenario_combo = QComboBox()
        for path in app_config.list_scenarios():
            self.scenario_combo.addItem(mountain_builder.scenario_label(path), str(path))
        index = self.scenario_combo.findData(str(app_config.DEFAULT_SCENARIO))
        self.scenario_combo.setCurrentIndex(max(index, 0))
        self.scenario_combo.currentIndexChanged.connect(self._on_scenario_combo)
        form.addRow("기본 설정", self.scenario_combo)
        self.mountain_note = QLabel("")          # 실제 산이면 지형·연료·등산로 반영 상태
        self.mountain_note.setObjectName("dim")
        self.mountain_note.setWordWrap(True)
        form.addRow(self.mountain_note)

        self.season_combo = QComboBox()
        self.season_combo.addItem("시나리오 파일 값 그대로", None)
        for preset in self.presets:
            self.season_combo.addItem(preset.label, preset.key)
        self.season_combo.currentIndexChanged.connect(self._on_season_changed)
        form.addRow("계절", self.season_combo)
        self.season_note = QLabel("")
        self.season_note.setObjectName("dim")
        self.season_note.setWordWrap(True)
        form.addRow(self.season_note)
        return group

    def _build_ignition_group(self) -> QGroupBox:
        group = QGroupBox("발화 지점")
        layout = QVBoxLayout(group)
        row = QHBoxLayout()
        self.ignition_x = QSpinBox()
        self.ignition_y = QSpinBox()
        for box in (self.ignition_x, self.ignition_y):
            box.setRange(0, 199)
            box.valueChanged.connect(self._emit_ignition)
        row.addWidget(QLabel("x"))
        row.addWidget(self.ignition_x)
        row.addWidget(QLabel("y"))
        row.addWidget(self.ignition_y)
        row.addStretch(1)
        layout.addLayout(row)
        hint = QLabel("지도를 클릭해도 발화 지점이 바뀝니다.")
        hint.setObjectName("dim")
        layout.addWidget(hint)
        return group

    def _build_weather_group(self) -> QGroupBox:
        group = QGroupBox("기상")
        layout = QVBoxLayout(group)

        self.weather_file_radio = QRadioButton("시나리오의 기상 파일 (시간별 변화)")
        self.weather_season_radio = QRadioButton("계절 평년 날씨 (하루 동안 기온·습도·바람 변화)")
        self.weather_season_radio.setToolTip("기상청 서울 평년값(1991~2020)으로 C 엔진이 하루 날씨를 만듭니다.\n"
                                             "오후엔 덥고 건조하며 바람이 세고, 밤엔 서늘하고 습해집니다.")
        self.weather_fixed_radio = QRadioButton("직접 입력 (일정한 값)")
        self.weather_mode_group = QButtonGroup(self)
        self.weather_mode_group.addButton(self.weather_file_radio)
        self.weather_mode_group.addButton(self.weather_season_radio)
        self.weather_mode_group.addButton(self.weather_fixed_radio)
        self.weather_file_radio.setChecked(True)
        self.weather_fixed_radio.toggled.connect(self._update_weather_enabled)
        layout.addWidget(self.weather_file_radio)
        layout.addWidget(self.weather_season_radio)
        layout.addWidget(self.weather_fixed_radio)

        form = QFormLayout()
        self.wind_speed = LabeledSlider(0, 20, 6, scale=2, formatter=lambda v: f"{v:.1f} m/s")
        self.wind_dir = LabeledSlider(0, 359, 270,
                                      formatter=lambda v: f"{wind_direction_name(v)} {v:.0f}°")
        self.humidity = LabeledSlider(5, 100, 25, formatter=lambda v: f"{v:.0f} %")
        self.temperature = LabeledSlider(-10, 40, 18, formatter=lambda v: f"{v:.0f} °C")
        form.addRow("풍속", self.wind_speed)
        form.addRow("풍향", self.wind_dir)
        form.addRow("습도", self.humidity)
        form.addRow("기온", self.temperature)
        layout.addLayout(form)

        self.weather_file_label = QLabel("")
        self.weather_file_label.setObjectName("dim")
        self.weather_file_label.setWordWrap(True)
        layout.addWidget(self.weather_file_label)
        self.real_weather_button = QPushButton("☁ 실제 기상 데이터 불러오기")
        self.real_weather_button.clicked.connect(self._open_weather_dialog)
        layout.addWidget(self.real_weather_button)
        self._update_weather_enabled()
        return group

    def _build_simulation_group(self) -> QGroupBox:
        group = QGroupBox("시뮬레이션")
        form = QFormLayout(group)
        self.duration = QSpinBox()
        self.duration.setRange(30, 1440)
        self.duration.setSingleStep(30)
        self.duration.setSuffix(" 분")
        self.seed = QSpinBox()
        self.seed.setRange(0, 999999)
        self.spotting = QCheckBox("비화(불티 날림) 사용")
        form.addRow("진행 시간", self.duration)
        form.addRow("난수 시드", self.seed)
        form.addRow(self.spotting)
        return group

    def _build_suppression_group(self) -> QGroupBox:
        group = QGroupBox("진화 자원")
        form = QFormLayout(group)
        self.include_suppression = QCheckBox("진화 전략 비교 포함 (약 15~35초 더 걸림)")
        self.include_suppression.setChecked(True)
        self.firebreak_cells = QSpinBox()
        self.firebreak_cells.setRange(0, 500)
        self.firebreak_cells.setSingleStep(5)
        self.firebreak_cells.setSuffix(" 칸")
        self.firebreak_ready = QSpinBox()
        self.firebreak_ready.setRange(0, 600)
        self.firebreak_ready.setSingleStep(10)
        self.firebreak_ready.setSuffix(" 분")
        self.helicopters = QSpinBox()
        self.helicopters.setRange(0, 20)
        self.helicopters.setSuffix(" 대")
        self.heli_interval = QSpinBox()
        self.heli_interval.setRange(5, 240)
        self.heli_interval.setSingleStep(5)
        self.heli_interval.setSuffix(" 분")
        form.addRow(self.include_suppression)
        form.addRow("방화선 길이", self.firebreak_cells)
        form.addRow("방화선 완성", self.firebreak_ready)
        form.addRow("헬기", self.helicopters)
        form.addRow("헬기 출동 간격", self.heli_interval)
        self.include_suppression.toggled.connect(self._update_suppression_enabled)
        return group

    def _update_suppression_enabled(self) -> None:
        enabled = self.include_suppression.isChecked()
        for widget in (self.firebreak_cells, self.firebreak_ready, self.helicopters, self.heli_interval):
            widget.setEnabled(enabled)

    def _build_montecarlo_group(self) -> QGroupBox:
        group = QGroupBox("몬테카를로")
        form = QFormLayout(group)
        self.include_montecarlo = QCheckBox("반복 실험 포함 (100회 약 30~45초)")
        self.mc_runs = QSpinBox()
        self.mc_runs.setRange(10, 1000)
        self.mc_runs.setSingleStep(10)
        self.mc_runs.setSuffix(" 회")
        self.include_montecarlo.toggled.connect(self.mc_runs.setEnabled)
        form.addRow(self.include_montecarlo)
        form.addRow("반복 횟수", self.mc_runs)
        self.mc_runs.setEnabled(False)
        return group

    def run_mode(self) -> str:
        """
        엔진 실행 모드
          진화 전략 + 몬테카를로 → all / 진화 전략만 → optimize / 몬테카를로만 → mc / 둘 다 아님 → evac
        """
        suppression = self.include_suppression.isChecked()
        montecarlo = self.include_montecarlo.isChecked()
        if suppression and montecarlo:
            return "all"
        if suppression:
            return "optimize"
        if montecarlo:
            return "mc"
        return "evac"

    def _build_run_buttons(self) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 6, 0, 0)
        self.run_button = QPushButton("🔥 시뮬레이션 실행")
        self.run_button.setObjectName("primary")
        self.run_button.setMinimumHeight(38)
        self.run_button.clicked.connect(self._on_run)
        self.stop_button = QPushButton("중지")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.reset_button = QPushButton("↺ 초기화")
        self.reset_button.setToolTip("시뮬레이션 결과를 지우고, 이 산의 처음 설정(발화 지점·기상·등산객 팀 등)으로 되돌립니다.")
        self.reset_button.clicked.connect(self.reset_all)
        layout.addWidget(self.run_button, 1)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.reset_button)
        return box

    def reset_all(self) -> None:
        """
        초기화: 지금 고른 산의 시나리오 파일 값으로 모든 입력을 되돌리고(발화 지점·기상·진화 자원·계절·낮밤),
        scenario_changed 를 보내 지도에서 결과를 지우고 등산객 팀도 처음 배치로 다시 읽게 한다.
        """
        self._on_scenario_combo()

    # ------------------------------------------------------------------
    # 값 읽기·쓰기
    # ------------------------------------------------------------------
    def current_scenario(self) -> Path:
        return Path(self.scenario_combo.currentData())

    def set_map_size(self, width: int, height: int) -> None:
        self.ignition_x.setRange(0, width - 1)
        self.ignition_y.setRange(0, height - 1)

    def set_ignition(self, x: int, y: int) -> None:
        """지도 클릭 등 바깥에서 발화 지점을 바꿀 때"""
        self.ignition_x.blockSignals(True)
        self.ignition_y.blockSignals(True)
        self.ignition_x.setValue(x)
        self.ignition_y.setValue(y)
        self.ignition_x.blockSignals(False)
        self.ignition_y.blockSignals(False)
        self._emit_ignition()

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.reset_button.setEnabled(not running)          # 실행 중에는 초기화하지 않음
        self.run_button.setText("실행 중..." if running else "🔥 시뮬레이션 실행")

    def _load_scenario_values(self, path: Path) -> None:
        """기본 시나리오 파일의 값으로 입력 칸을 채운다."""
        ini = read_ini(path)
        self.duration.setValue(int(ini.getfloat("time", "duration_min", fallback=600)))
        self.seed.setValue(ini.getint("spread", "random_seed", fallback=42))
        self.spotting.setChecked(ini.getint("spread", "spotting_enabled", fallback=1) == 1)
        mode = ini.get("weather", "mode", fallback="file").strip().lower()
        {"fixed": self.weather_fixed_radio, "season": self.weather_season_radio}.get(
            mode, self.weather_file_radio).setChecked(True)
        self.wind_speed.set_value(ini.getfloat("weather", "fixed_wind_speed_ms", fallback=6))
        self.wind_dir.set_value(ini.getfloat("weather", "fixed_wind_dir_deg", fallback=270))
        self.humidity.set_value(ini.getfloat("weather", "fixed_rh_pct", fallback=25))
        self.temperature.set_value(ini.getfloat("weather", "fixed_temp_c", fallback=18))
        self.firebreak_cells.setValue(ini.getint("suppression", "firebreak_cells", fallback=40))
        self.firebreak_ready.setValue(int(ini.getfloat("suppression", "firebreak_ready_min", fallback=60)))
        self.helicopters.setValue(ini.getint("suppression", "helicopters", fallback=2))
        self.heli_interval.setValue(int(ini.getfloat("suppression", "heli_interval_min", fallback=30)))
        self.mc_runs.setValue(ini.getint("montecarlo", "runs", fallback=100))
        self.daylight_group.load(ini)
        self.set_weather_override(None)
        for key, value in ini.items("ignition") if ini.has_section("ignition") else []:
            if key.startswith("point"):
                parts = [p.strip() for p in value.split(",")]
                self.set_ignition(int(parts[0]), int(parts[1]))
                break
        self.season_combo.setCurrentIndex(0)

    def build_overrides(self) -> ScenarioOverrides:
        """화면의 값을 시나리오에 적용할 변경 목록으로 만든다."""
        o = ScenarioOverrides()
        o.ignitions = [(self.ignition_x.value(), self.ignition_y.value(), 0.0)]
        o.set("time", "duration_min", self.duration.value())
        o.set("spread", "random_seed", self.seed.value())
        o.set("spread", "spotting_enabled", 1 if self.spotting.isChecked() else 0)
        if self.weather_season_radio.isChecked():
            o.set("weather", "mode", "season")
        elif self.weather_fixed_radio.isChecked():
            o.set("weather", "mode", "fixed")
            o.set("weather", "fixed_wind_speed_ms", self.wind_speed.value())
            o.set("weather", "fixed_wind_dir_deg", self.wind_dir.value())
            o.set("weather", "fixed_rh_pct", self.humidity.value())
            o.set("weather", "fixed_temp_c", self.temperature.value())
        else:
            o.set("weather", "mode", "file")
        o.set("suppression", "firebreak_cells", self.firebreak_cells.value())
        o.set("suppression", "firebreak_ready_min", self.firebreak_ready.value())
        o.set("suppression", "helicopters", self.helicopters.value())
        o.set("suppression", "heli_interval_min", self.heli_interval.value())
        o.set("montecarlo", "runs", self.mc_runs.value())
        if self.weather_override is not None and self.weather_file_radio.isChecked():
            path, start = self.weather_override
            # 시나리오 파일이 있는 폴더 기준 상대 경로 (Windows 에서도 / 로 저장)
            relative = os.path.relpath(path, self.current_scenario().parent).replace("\\", "/")
            o.set("weather", "file", relative)
        self.daylight_group.apply(o)
        self.hiker_group.apply(o, self.current_scenario().parent)
        if self.weather_override is not None and self.weather_file_radio.isChecked():
            o.set("time", "start_datetime", self.weather_override[1])   # 실제 기상의 시작 시각이 우선
        preset = self._current_preset()
        if preset is not None:
            o.set("moisture", "live_moisture_factor", preset.live_moisture_factor)
            o.set("moisture", "initial_dead_moisture_pct", preset.initial_dead_moisture_pct)
            o.set("season", "season", preset.key)                 # (9단계) 계절 날씨·눈·지도 색
            o.set("season", "snow_line_m", float(preset.snow_line_m))
        return o

    # ------------------------------------------------------------------
    # 이벤트
    # ------------------------------------------------------------------
    def _current_preset(self) -> SeasonPreset | None:
        key = self.season_combo.currentData()
        return next((p for p in self.presets if p.key == key), None)

    def _on_scenario_combo(self) -> None:
        path = self.current_scenario()
        self._load_scenario_values(path)
        self._update_mountain_note()
        self.scenario_changed.emit(path)

    def _update_mountain_note(self) -> None:
        text = mountain_builder.data_status_text(self.current_scenario())
        self.mountain_note.setText(text)
        self.mountain_note.setVisible(bool(text))

    def _on_season_changed(self) -> None:
        """
        계절을 고르면
          - 기상을 '계절 평년 날씨'로 바꾸고 (직접 입력 슬라이더도 그 계절의 오후 대표값으로)
          - 시작 날짜를 계절 대표 날짜로 (해 뜨고 지는 시각이 계절마다 다름)
          - 지도 색을 계절 색으로 (미리보기)
        """
        preset = self._current_preset()
        if preset is None:
            self.season_note.setText("")
            self.daylight_group.set_date(None)
            ini = read_ini(self.current_scenario())
            start = parse_datetime(ini.get("time", "start_datetime", fallback=""))
            season, snow = season_from_ini(ini, start)
            self.season_preview_changed.emit(season, snow)
            return
        snow = f", 해발 {preset.snow_line_m:g} m 이상 눈" if preset.snow_line_m > 0 else ""
        self.season_note.setText(f"{preset.note}  (수분 배율 {preset.live_moisture_factor:g}, "
                                 f"초기 연료 수분 {preset.initial_dead_moisture_pct:g}%{snow}, {preset.date})")
        self.wind_speed.set_value(preset.wind_speed_ms)
        self.wind_dir.set_value(preset.wind_dir_deg)
        self.humidity.set_value(preset.rh_pct)
        self.temperature.set_value(preset.temp_c)
        if self.weather_override is None:
            self.weather_season_radio.setChecked(True)
        if preset.date:
            self.daylight_group.set_date(preset.date)
        self.season_preview_changed.emit(preset.key, float(preset.snow_line_m))

    def _open_weather_dialog(self) -> None:
        mid = mountain_builder.scenario_mountain_id(self.current_scenario())
        info = mountain_builder.read_info(mid) if mid else {}
        dialog = WeatherDialog(self, mountain_builder.display_name(info) if info else None)
        if dialog.exec() and dialog.selected_path is not None and dialog.rows:
            self.set_weather_override((dialog.selected_path, f"{dialog.rows[0].time:%Y-%m-%d %H:%M}"))

    def set_weather_override(self, override: tuple[Path, str] | None) -> None:
        """불러온 기상 파일을 쓰도록 설정한다. (None 이면 시나리오 파일의 기상 그대로)"""
        self.weather_override = override
        self.daylight_group.set_start_locked(override[1] if override is not None else None)
        if override is None:
            self.weather_file_label.setText("")
            return
        path, start = override
        self.weather_file_label.setText(f"사용할 기상 파일: {path.name} (시작 {start})")
        self.season_combo.setCurrentIndex(0)
        self.weather_file_radio.setChecked(True)

    def _update_weather_enabled(self) -> None:
        enabled = self.weather_fixed_radio.isChecked()
        for widget in (self.wind_speed, self.wind_dir, self.humidity, self.temperature):
            widget.setEnabled(enabled)

    def _emit_ignition(self) -> None:
        self.ignition_changed.emit(self.ignition_x.value(), self.ignition_y.value())

    def _on_run(self) -> None:
        self.run_requested.emit(self.current_scenario(), self.build_overrides())
