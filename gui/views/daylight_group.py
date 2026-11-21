"""
낮/밤 설정 묶음 (8단계) — 시나리오 설정 패널 안에 들어가는 상자

    ☑ 낮/밤 반영
    시작 시각   [17:00]        (실제 기상을 불러오면 그 예보 시각으로 고정)
    밤 보행 속도 [60 %]
    ☑ 해가 진 뒤 헬기 출동 중지

일몰·일출 시각은 C 엔진이 날짜·위도로 계산한다. (c_core/src/daylight.c)
"""

from __future__ import annotations

from configparser import ConfigParser

from PySide6.QtCore import QTime
from PySide6.QtWidgets import QCheckBox, QFormLayout, QGroupBox, QLabel, QSpinBox, QTimeEdit

from services.scenario_writer import ScenarioOverrides


class DaylightGroup(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("낮/밤", parent)
        self._date = "2026-04-05"          # 시나리오 파일의 시작 날짜 (시각만 바꿈)
        self._start_locked = False         # 실제 기상 파일을 쓰면 그 시작 시각으로 고정

        self.enabled = QCheckBox("낮/밤 반영 (밤: 걷는 속도↓, 헬기 철수)")
        self.enabled.setChecked(True)
        self.start_time = QTimeEdit()
        self.start_time.setDisplayFormat("HH:mm")
        self.night_walk = QSpinBox()
        self.night_walk.setRange(20, 100)
        self.night_walk.setSuffix(" %")
        self.night_walk.setToolTip("어두운 산길에서는 헤드랜턴에 의지해 낮보다 천천히 걷는다고 가정")
        self.heli_day_only = QCheckBox("해가 진 뒤 헬기 출동 중지")
        self.heli_day_only.setChecked(True)
        self.note = QLabel("저녁(17시 전후)에 시작하면 일몰 후 효과를 볼 수 있습니다.")
        self.note.setObjectName("dim")
        self.note.setWordWrap(True)

        form = QFormLayout(self)
        form.addRow(self.enabled)
        form.addRow("시작 시각", self.start_time)
        form.addRow("밤 보행 속도", self.night_walk)
        form.addRow(self.heli_day_only)
        form.addRow(self.note)
        self.enabled.toggled.connect(self._update_enabled)

    def load(self, ini: ConfigParser) -> None:
        """시나리오 파일의 값으로 채운다."""
        start = ini.get("time", "start_datetime", fallback="2026-04-01 13:00").strip()
        date, _, clock = start.partition(" ")
        self._date = date
        self.start_time.setTime(QTime.fromString(clock or "13:00", "HH:mm"))
        self.enabled.setChecked(ini.getint("daylight", "enabled", fallback=1) == 1)
        self.night_walk.setValue(int(round(ini.getfloat("daylight", "night_walk_factor", fallback=0.6) * 100)))
        self.heli_day_only.setChecked(ini.getint("daylight", "heli_day_only", fallback=1) == 1)
        self.set_start_locked(None)

    def set_start_locked(self, start: str | None) -> None:
        """실제 기상 파일을 쓰면 시작 시각을 그 예보 시각으로 고정한다. (None 이면 풀기)"""
        self._start_locked = start is not None
        if start is not None:
            self.start_time.setTime(QTime.fromString(start.partition(" ")[2], "HH:mm"))
        self._update_enabled()

    def apply(self, o: ScenarioOverrides) -> None:
        """화면 값을 시나리오 변경 목록에 넣는다."""
        o.set("daylight", "enabled", 1 if self.enabled.isChecked() else 0)
        o.set("daylight", "night_walk_factor", round(self.night_walk.value() / 100.0, 2))
        o.set("daylight", "heli_day_only", 1 if self.heli_day_only.isChecked() else 0)
        if not self._start_locked:
            o.set("time", "start_datetime", f"{self._date} {self.start_time.time().toString('HH:mm')}")

    def _update_enabled(self) -> None:
        on = self.enabled.isChecked()
        self.night_walk.setEnabled(on)
        self.heli_day_only.setEnabled(on)
        self.start_time.setEnabled(not self._start_locked)
