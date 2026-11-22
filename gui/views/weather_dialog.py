"""
실제 기상 데이터 불러오기 창

    1) 위치 고르기 (산 목록 또는 위도·경도 직접 입력) → 기상청 격자 (nx, ny) 표시
    2) 자료 종류 고르기
         단기예보: 지금부터 약 3일 → [기상청 예보 받기]
         과거 관측: 가까운 관측소, 날짜·시각·시간 수 → [과거 관측 받기] (실제 있었던 날의 날씨)
       → data/weather/kma_*.csv 저장
       또는 인터넷이 없을 때: 이미 저장된 기상 파일(샘플 포함) 고르기
    3) 미리보기 표 확인 후 [이 기상으로 설정] → 시나리오의 기상 파일과 시작 시각이 바뀜
"""

from __future__ import annotations

from pathlib import Path

from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

import theme
from services import app_config, mountain_builder, weather_api
from services.weather_api import WeatherApiError, WeatherRow

CUSTOM_LOCATION = "직접 입력"


class WeatherDialog(QDialog):
    def __init__(self, parent=None, mountain_name: str | None = None):
        super().__init__(parent)
        # 위치 목록: data/mountains/mountains.json (실제 산 데이터와 같은 위치), 읽지 못하면 기본 목록
        self.presets = mountain_builder.weather_presets() or weather_api.MOUNTAIN_PRESETS
        self.mountain_name = mountain_name
        self.setWindowTitle("실제 기상 데이터 불러오기")
        self.resize(660, 700)
        self.selected_path: Path | None = None
        self.rows: list[WeatherRow] = []

        layout = QVBoxLayout(self)
        layout.addWidget(self._build_download_group())
        layout.addWidget(self._build_file_group())
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["시각", "기온 (°C)", "습도 (%)", "풍속 (m/s)", "풍향 (°)"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("이 기상으로 설정")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_grid_label()

    # ------------------------------------------------------------------
    def _build_download_group(self) -> QGroupBox:
        group = QGroupBox("기상청 날씨 받기 (인터넷 + API 키 필요)")
        form = QFormLayout(group)
        self.location_combo = QComboBox()
        self.location_combo.addItems(list(self.presets) + [CUSTOM_LOCATION])
        for i, name in enumerate(self.presets):          # 실제 산 시나리오면 그 산을 먼저 고름
            if self.mountain_name and name.startswith(self.mountain_name):
                self.location_combo.setCurrentIndex(i)
        self.location_combo.currentIndexChanged.connect(self._on_location)
        self.lat = QDoubleSpinBox()
        self.lon = QDoubleSpinBox()
        for box, (low, high) in ((self.lat, (33.0, 39.0)), (self.lon, (124.0, 132.0))):
            box.setRange(low, high)
            box.setDecimals(4)
            box.setSingleStep(0.01)
            box.valueChanged.connect(self._update_grid_label)
        self.grid_label = QLabel("")
        self.grid_label.setObjectName("dim")
        row = QHBoxLayout()
        row.addWidget(QLabel("위도"))
        row.addWidget(self.lat)
        row.addWidget(QLabel("경도"))
        row.addWidget(self.lon)
        row.addWidget(self.grid_label, 1)

        key = weather_api.load_api_key()
        key_text = ("API 키: 설정됨" if key else
                    f"API 키 없음 — {weather_api.API_KEY_FILE.name} 에 키를 넣으세요 (양식: api_keys.example.ini)")
        key_label = QLabel(key_text)
        key_label.setStyleSheet(f"color: {theme.SUCCESS if key else theme.WARNING};")
        self.download_button = QPushButton("☁ 기상청 예보 받기")
        self.download_button.setObjectName("primary")
        self.download_button.clicked.connect(self._download)

        # 자료 종류: 단기예보(앞으로) / 과거 관측(실제 있었던 날)
        self.forecast_radio = QRadioButton("단기예보 (지금부터 약 3일)")
        self.past_radio = QRadioButton("과거 관측 (실제 있었던 날)")
        self.forecast_radio.setChecked(True)
        kinds = QButtonGroup(self)
        for radio in (self.forecast_radio, self.past_radio):
            kinds.addButton(radio)
            radio.toggled.connect(self._on_kind_changed)
        kind_row = QHBoxLayout()
        kind_row.addWidget(self.forecast_radio)
        kind_row.addWidget(self.past_radio)
        kind_row.addStretch(1)

        form.addRow("위치", self.location_combo)
        form.addRow(row)
        form.addRow("자료", kind_row)
        form.addRow(self._build_past_box())
        form.addRow(key_label)
        form.addRow(self.download_button)
        self._on_location()
        self._on_kind_changed()
        return group

    def _build_past_box(self) -> QWidget:
        """과거 관측 설정: 관측소, 시작 날짜·시각, 시간 수"""
        self.past_box = QWidget()
        form = QFormLayout(self.past_box)
        form.setContentsMargins(0, 0, 0, 0)
        self.station_combo = QComboBox()
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        yesterday = QDate.currentDate().addDays(-1)
        self.start_date.setMaximumDate(yesterday)
        self.start_date.setDate(QDate(yesterday.year() - 1, 4, 5))       # 기본: 작년 봄철 건조기 [예시]
        self.start_hour = QSpinBox()
        self.start_hour.setRange(0, 23)
        self.start_hour.setValue(13)
        self.start_hour.setSuffix(" 시")
        self.hours = QSpinBox()
        self.hours.setRange(1, weather_api.ASOS_MAX_HOURS)
        self.hours.setValue(10)
        self.hours.setSuffix(" 시간")
        when = QHBoxLayout()
        when.addWidget(self.start_date)
        when.addWidget(self.start_hour)
        when.addWidget(QLabel("부터"))
        when.addWidget(self.hours)
        when.addStretch(1)
        note = QLabel("관측소는 보통 산 아래 평지에 있어 산 위보다 바람이 약할 수 있습니다. 어제까지 받을 수 있습니다.")
        note.setObjectName("dim")
        note.setWordWrap(True)
        form.addRow("관측소", self.station_combo)
        form.addRow("기간", when)
        form.addRow(note)
        return self.past_box

    def _build_file_group(self) -> QGroupBox:
        group = QGroupBox("저장된 기상 파일 사용 (인터넷이 없을 때)")
        row = QHBoxLayout(group)
        self.file_combo = QComboBox()
        for path in sorted((app_config.DATA_DIR / "weather").glob("*.csv")):
            if path.name != weather_api.STATION_FILE.name:      # 관측소 목록은 기상 파일이 아님
                self.file_combo.addItem(path.name, str(path))
        use_button = QPushButton("불러오기")
        use_button.clicked.connect(lambda: self._load_file(Path(self.file_combo.currentData())))
        row.addWidget(self.file_combo, 1)
        row.addWidget(use_button)
        return group

    # ------------------------------------------------------------------
    def _on_location(self) -> None:
        name = self.location_combo.currentText()
        custom = name == CUSTOM_LOCATION
        self.lat.setEnabled(custom)
        self.lon.setEnabled(custom)
        if not custom:
            lat, lon = self.presets[name]
            self.lat.setValue(lat)
            self.lon.setValue(lon)
        self._update_grid_label()

    def _update_grid_label(self) -> None:
        nx, ny = weather_api.latlon_to_grid(self.lat.value(), self.lon.value())
        self.grid_label.setText(f"→ 기상청 격자 nx={nx}, ny={ny}")
        self._refill_stations()

    def _refill_stations(self) -> None:
        """위치에서 가까운 관측소 3곳 (가까운 순)"""
        if not hasattr(self, "station_combo"):
            return
        self.station_combo.clear()
        try:
            nearest = weather_api.nearest_stations(self.lat.value(), self.lon.value())
        except (OSError, ValueError):
            return
        for station, km in nearest:
            self.station_combo.addItem(f"{station.name} ({station.stn_id}) — {km:.1f} km", station.stn_id)

    def _on_kind_changed(self) -> None:
        past = self.past_radio.isChecked()
        self.past_box.setVisible(past)
        self.download_button.setText("☁ 과거 관측 받기" if past else "☁ 기상청 예보 받기")

    def _download(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        note = ""
        try:
            if self.past_radio.isChecked():
                day = self.start_date.date()
                start = datetime(day.year(), day.month(), day.day(), self.start_hour.value())
                path, _, note = weather_api.download_past_weather(int(self.station_combo.currentData()), start,
                                                                  self.hours.value())
            else:
                path, _ = weather_api.download_weather(self.lat.value(), self.lon.value())
        except (WeatherApiError, TypeError) as error:
            self._show_message(str(error), theme.ERROR)
            return
        finally:
            QApplication.restoreOverrideCursor()
        if self.file_combo.findData(str(path)) < 0:
            self.file_combo.addItem(path.name, str(path))
        self._load_file(path, note)

    def _load_file(self, path: Path, note: str = "") -> None:
        self.rows = weather_api.read_weather_csv(path)
        if not self.rows:
            self._show_message(f"{path.name}: 읽을 수 있는 기상 기록이 없습니다.", theme.ERROR)
            return
        self.selected_path = path
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            values = [f"{r.time:%m-%d %H:%M}", f"{r.temp_c:.1f}", f"{r.rh_pct:.0f}", f"{r.wind_speed_ms:.1f}",
                      f"{r.wind_dir_deg:.0f}"]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, column, item)
        self._show_message((f"{note}. " if note else "") +
                           f"{path.name}: {len(self.rows)}개 기록, {self.rows[0].time:%Y-%m-%d %H:%M} ~ "
                           f"{self.rows[-1].time:%m-%d %H:%M}. 시뮬레이션 시작 시각은 첫 기록 시각으로 설정됩니다.",
                           theme.SUCCESS)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def _show_message(self, text: str, color: str) -> None:
        self.message.setStyleSheet(f"color: {color};")
        self.message.setText(text)
