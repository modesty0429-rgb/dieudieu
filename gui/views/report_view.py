"""
결과 리포트 화면

리포트 미리보기와 "HTML + PNG로 저장" 버튼.
저장하면 결과 폴더 안 report/ 에 report.html 과 화면 그림(map.png, suppression.png, stats.png)이 생긴다.
화면 그림은 메인 창이 넘겨준 위젯들을 캡처(grab)해서 만든다.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from services.report_builder import build_report_html
from services.result_loader import SimulationResult


class ReportView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result: SimulationResult | None = None
        self.capture_sources: dict[str, Callable[[], QWidget | None]] = {}
        self.saved_path: Path | None = None

        self.save_button = QPushButton("💾 리포트 저장 (HTML + PNG)")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_report)
        self.open_button = QPushButton("저장 폴더 열기")
        self.open_button.clicked.connect(self.open_folder)
        self.status = QLabel("")
        self.status.setObjectName("dim")
        top = QHBoxLayout()
        top.addWidget(self.save_button)
        top.addWidget(self.open_button)
        top.addWidget(self.status, 1)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        # 미리보기는 밝은 배경 (인쇄용 문서와 같은 모양)
        self.preview.setStyleSheet("background: #ffffff; color: #222222; font-family: sans-serif; font-size: 10pt;")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.preview, 1)
        self._update_buttons()

    def set_result(self, result: SimulationResult | None) -> None:
        self.result = result
        self.saved_path = None
        if result is None:
            self.preview.setHtml("<p>결과가 없습니다. 시뮬레이션을 실행하면 리포트를 만들 수 있습니다.</p>")
        else:
            self.preview.setHtml(build_report_html(result, {}))
        self.status.setText("")
        self._update_buttons()

    def save_report(self) -> Path | None:
        """화면을 캡처하고 report.html 을 저장한다. 저장한 HTML 경로를 돌려준다."""
        if self.result is None:
            return None
        folder = self.result.output_dir / "report"
        folder.mkdir(parents=True, exist_ok=True)
        images: dict[str, str] = {}
        for key, source in self.capture_sources.items():
            widget = source()
            if widget is None:
                continue
            name = f"{key}.png"
            if widget.grab().save(str(folder / name)):
                images[key] = name
        html_text = build_report_html(self.result, images)
        path = folder / "report.html"
        path.write_text(html_text, encoding="utf-8")
        self.saved_path = path
        self.preview.setSearchPaths([str(folder)])
        self.preview.setHtml(html_text)
        self.status.setText(f"저장: {path}  (브라우저로 열어 인쇄하면 PDF로 저장할 수 있습니다)")
        self._update_buttons()
        return path

    def open_folder(self) -> None:
        if self.saved_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.saved_path.parent)))

    def _update_buttons(self) -> None:
        self.save_button.setEnabled(self.result is not None)
        self.open_button.setEnabled(self.saved_path is not None)
