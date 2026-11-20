"""
재생 컨트롤

Play/Pause 버튼, 타임라인 슬라이더, 재생 속도 선택.
QTimer 가 일정 간격(40 ms)마다 시각을 "속도"만큼 앞으로 보내고 time_changed 시그널을 보낸다.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from services.result_loader import format_clock

FRAME_INTERVAL_MS = 40                         # 초당 25프레임
SPEEDS = [(0.5, "0.5분/프레임"), (1, "1분/프레임"), (2, "2분/프레임"),
          (5, "5분/프레임"), (10, "10분/프레임")]
DEFAULT_SPEED_INDEX = 2


class PlaybackBar(QWidget):
    time_changed = Signal(float)   # 현재 시각 (분)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._end_time = 0.0
        self._time = 0.0
        self._start: datetime | None = None

        self.play_button = QPushButton("▶ 재생")
        self.play_button.setObjectName("primary")
        self.play_button.setFixedWidth(90)
        self.play_button.clicked.connect(self.toggle)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.valueChanged.connect(self._on_slider)   # 슬라이더 값 = 시각 × 10 (0.1분 단위)

        self.time_label = QLabel("0분")
        self.time_label.setMinimumWidth(150)

        self.speed_combo = QComboBox()
        for _, label in SPEEDS:
            self.speed_combo.addItem(label)
        self.speed_combo.setCurrentIndex(DEFAULT_SPEED_INDEX)

        self.timer = QTimer(self)
        self.timer.setInterval(FRAME_INTERVAL_MS)
        self.timer.timeout.connect(self._advance)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.play_button)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.time_label)
        layout.addWidget(QLabel("속도"))
        layout.addWidget(self.speed_combo)
        self.setEnabled(False)

    # ------------------------------------------------------------------
    def set_range(self, end_time: float, start: datetime | None) -> None:
        """새 결과를 불러왔을 때 타임라인 길이를 정한다."""
        self.pause()
        self._end_time = end_time
        self._start = start
        self.slider.setRange(0, int(round(end_time * 10)))
        self.setEnabled(end_time > 0)
        self.set_time(0.0)

    def set_time(self, t: float) -> None:
        """시각을 바꾸고 화면에 알린다."""
        self._time = max(0.0, min(t, self._end_time))
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(self._time * 10)))
        self.slider.blockSignals(False)
        clock = format_clock(self._start, self._time)
        self.time_label.setText(f"T+{self._time:5.1f}분" + (f"  ({clock})" if clock else ""))
        self.time_changed.emit(self._time)

    def current_time(self) -> float:
        return self._time

    def play(self) -> None:
        if self._time >= self._end_time:
            self.set_time(0.0)       # 끝에서 누르면 처음부터
        self.timer.start()
        self.play_button.setText("⏸ 일시정지")

    def pause(self) -> None:
        self.timer.stop()
        self.play_button.setText("▶ 재생")

    def toggle(self) -> None:
        if self.timer.isActive():
            self.pause()
        else:
            self.play()

    # ------------------------------------------------------------------
    def _advance(self) -> None:
        speed = SPEEDS[self.speed_combo.currentIndex()][0]
        next_time = self._time + speed
        if next_time >= self._end_time:
            self.set_time(self._end_time)
            self.pause()
        else:
            self.set_time(next_time)

    def _on_slider(self, value: int) -> None:
        self.set_time(value / 10.0)
