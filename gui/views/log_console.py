"""
엔진 로그 창

C 엔진의 표준출력 전체를 태그별 색으로 보여 준다. (콘솔 지도·표도 그대로 보임)
"""

from __future__ import annotations

import html

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

import theme
from services.engine_runner import EngineLine

MAX_LINES = 20000   # 너무 많이 쌓이면 오래된 줄부터 지움


class LogConsole(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(MAX_LINES)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.count_label = QLabel("")
        self.count_label.setObjectName("dim")
        clear_button = QPushButton("지우기")
        clear_button.clicked.connect(self.clear)

        top = QHBoxLayout()
        top.addWidget(QLabel("C 엔진 출력 (stdout)"))
        top.addStretch(1)
        top.addWidget(self.count_label)
        top.addWidget(clear_button)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.text)

        self._warnings = 0
        self._errors = 0

    def append_line(self, line: EngineLine) -> None:
        """엔진 출력 한 줄을 색을 입혀 추가한다."""
        color = theme.LOG_COLORS.get(line.tag, theme.TEXT)
        if line.tag == "TEXT":
            body = line.text
        elif line.tag == "PROGRESS":
            body = f"[PROGRESS] {line.percent:3d}% {line.text}"
        else:
            body = f"[{line.tag}] {line.text}"
        if line.tag == "WARN":
            self._warnings += 1
        elif line.tag == "ERROR":
            self._errors += 1
        # appendHtml 은 공백을 줄이므로 &nbsp; 로 바꿔 콘솔 지도의 칸 맞춤을 유지한다
        escaped = html.escape(body).replace(" ", "&nbsp;")
        self.text.appendHtml(f'<span style="color:{color}">{escaped}</span>')
        self._update_count()

    def append_gui_message(self, message: str) -> None:
        self.append_line(EngineLine("GUI", message))

    def clear(self) -> None:
        self.text.clear()
        self._warnings = self._errors = 0
        self._update_count()

    def _update_count(self) -> None:
        self.count_label.setText(f"경고 {self._warnings} · 오류 {self._errors}")
