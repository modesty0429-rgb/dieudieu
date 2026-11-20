"""
메인 창

    ┌─────────────────────────────────────────────────────────┐
    │ 엔진 상태: [INFO] ...                       [■■■■□□ 60%] │  ← C 엔진 stdout 실시간 표시
    ├──────────────┬──────────────────────────────────────────┤
    │ 시나리오      │  [지도] [엔진 로그]                       │
    │ 설정 패널     │   지도 (MapView)                          │
    │ (왼쪽 도킹)   │   ▶ ━━━━━━●━━━━━ T+120분 (15:00)  속도   │
    └──────────────┴──────────────────────────────────────────┘

실행 흐름: 설정 패널 "실행" → 시나리오 파일 저장 → C 엔진 실행(별도 스레드)
          → stdout 한 줄씩 상태 표시 → 끝나면 summary.json 읽기 → 지도 애니메이션 재생
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressBar, QTabWidget, QVBoxLayout, QWidget)

import theme
from services import app_config
from services.engine_runner import EngineLine, EngineRunner
from services.result_loader import SimulationResult, load_result, load_scenario_preview
from services.scenario_writer import ScenarioOverrides, write_scenario
from views.log_console import LogConsole
from views.map_view import MapView
from views.playback_bar import PlaybackBar
from views.scenario_panel import ScenarioPanel


class EngineStatusBar(QFrame):
    """화면 맨 위: C 엔진의 최신 출력 한 줄과 진행률"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("infoBar")
        self.label = QLabel("대기 중")
        self.label.setObjectName("statusText")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFixedWidth(220)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(QLabel("엔진 상태:"))
        layout.addWidget(self.label, 1)
        layout.addWidget(self.progress)

    def show_line(self, line: EngineLine) -> None:
        if line.tag == "TEXT" or not line.text.strip():
            return                         # 콘솔 지도·표는 상단에 표시하지 않음
        color = theme.LOG_COLORS.get(line.tag, theme.TEXT)
        self.label.setStyleSheet(f"color: {color};")
        self.label.setText(f"[{line.tag}] {line.text}")
        if line.percent >= 0:
            self.progress.setValue(line.percent)

    def show_message(self, text: str, color: str = theme.TEXT) -> None:
        self.label.setStyleSheet(f"color: {color};")
        self.label.setText(text)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("산불 확산 예측 및 등산객 대피 안내 시스템")
        self.resize(1400, 900)
        self.result: SimulationResult | None = None
        self.runner = EngineRunner(self)

        self._build_widgets()
        self._build_menu()
        self._connect_signals()
        self._load_initial_data()

    # ------------------------------------------------------------------
    # 화면 구성
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        self.status_bar = EngineStatusBar()
        self.map_view = MapView()
        self.playback = PlaybackBar()
        self.log_console = LogConsole()

        map_tab = QWidget()
        map_layout = QVBoxLayout(map_tab)
        map_layout.addWidget(self.map_view, 1)
        map_layout.addWidget(self.playback)

        self.tabs = QTabWidget()
        self.tabs.addTab(map_tab, "🗺 지도")
        self.tabs.addTab(self.log_console, "📄 엔진 로그")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.status_bar)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.panel = ScenarioPanel()
        dock = QDockWidget("시나리오 설정", self)
        dock.setWidget(self.panel)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("파일")
        open_action = QAction("결과 불러오기 (summary.json)...", self)
        open_action.triggered.connect(self._open_result_dialog)
        folder_action = QAction("결과 폴더 열기", self)
        folder_action.triggered.connect(self._open_output_folder)
        quit_action = QAction("종료", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(open_action)
        file_menu.addAction(folder_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("도움말")
        about_action = QAction("프로그램 정보", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _connect_signals(self) -> None:
        self.panel.run_requested.connect(self.run_simulation)
        self.panel.stop_requested.connect(self.runner.stop)
        self.panel.scenario_changed.connect(self.load_preview)
        self.panel.ignition_changed.connect(self._on_ignition_changed)
        self.map_view.cell_clicked.connect(self.panel.set_ignition)
        self.playback.time_changed.connect(self.map_view.set_time)
        self.runner.line_received.connect(self._on_engine_line)
        self.runner.finished.connect(self._on_engine_finished)

    def _load_initial_data(self) -> None:
        """시작할 때: 기본 시나리오 지도를 보여 주고, 이전 실행 결과가 있으면 불러온다."""
        self.load_preview(self.panel.current_scenario())
        previous = app_config.OUTPUT_DIR / app_config.GUI_SCENARIO_NAME / "summary.json"
        if not previous.exists():
            previous = app_config.OUTPUT_DIR / app_config.DEFAULT_SCENARIO.stem / "summary.json"
        if previous.exists():
            self.load_result_file(previous, autoplay=False)

    # ------------------------------------------------------------------
    # 동작
    # ------------------------------------------------------------------
    def load_preview(self, scenario_path: Path) -> None:
        """시나리오 파일만 읽어 지도·등산로·발화 지점을 보여 준다."""
        try:
            preview = load_scenario_preview(scenario_path)
        except (OSError, ValueError, KeyError) as error:
            self.status_bar.show_message(f"시나리오 미리보기 실패: {error}", theme.ERROR)
            return
        self.result = None
        self.map_view.set_map(preview)
        self.panel.set_map_size(preview.width, preview.height)
        self._on_ignition_changed(self.panel.ignition_x.value(), self.panel.ignition_y.value())
        self.playback.set_range(0.0, preview.start_time)
        self.status_bar.show_message(f"시나리오 '{preview.name}' 지도 ({preview.width}×{preview.height}칸)")

    def load_result_file(self, summary_path: Path, autoplay: bool = True) -> bool:
        """summary.json 을 읽어 지도에 결과를 붙이고 재생을 준비한다."""
        try:
            result = load_result(summary_path)
        except (OSError, ValueError, KeyError) as error:
            self.status_bar.show_message(f"결과 읽기 실패: {error}", theme.ERROR)
            self.log_console.append_gui_message(f"결과 읽기 실패: {summary_path} ({error})")
            return False
        self.result = result
        self.map_view.set_result(result)
        self.panel.set_map_size(result.map.width, result.map.height)
        self.playback.set_range(result.end_time, result.map.start_time)
        r = result.summary["result"]
        self.status_bar.show_message(
            f"결과 '{result.map.name}': 피해 {r['burned_area_ha']:.1f} ha, 비화 {r['spot_fires']}회, "
            f"최대 확산 속도 {r['max_spread_rate_m_min']:.1f} m/분", theme.SUCCESS)
        if autoplay:
            self.playback.play()
        return True

    def run_simulation(self, base_path: Path, overrides: ScenarioOverrides) -> None:
        """설정 패널의 값으로 시나리오 파일을 만들고 C 엔진을 실행한다."""
        if self.runner.is_running():
            return
        try:
            scenario_path = write_scenario(base_path, overrides)
        except OSError as error:
            self.status_bar.show_message(f"시나리오 저장 실패: {error}", theme.ERROR)
            return
        self.log_console.append_gui_message(f"시나리오 저장: {scenario_path}")
        self.playback.pause()
        if self.runner.start(scenario_path, "run"):
            self.panel.set_running(True)
            self.status_bar.progress.setValue(0)

    # ------------------------------------------------------------------
    # 엔진 시그널
    # ------------------------------------------------------------------
    def _on_engine_line(self, line: EngineLine) -> None:
        self.log_console.append_line(line)
        self.status_bar.show_line(line)

    def _on_engine_finished(self, code: int, result_path: str) -> None:
        self.panel.set_running(False)
        if code == 0 and result_path:
            self.status_bar.progress.setValue(100)
            self.load_result_file(Path(result_path))
        else:
            self.status_bar.show_message(
                f"엔진이 오류로 끝났습니다 (종료 코드 {code}). '엔진 로그' 탭에서 [ERROR] 줄을 확인하세요.",
                theme.ERROR)
            self.tabs.setCurrentWidget(self.log_console)

    def _on_ignition_changed(self, x: int, y: int) -> None:
        self.map_view.set_ignitions([(x, y, 0.0)])

    # ------------------------------------------------------------------
    # 메뉴
    # ------------------------------------------------------------------
    def _open_result_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "결과 불러오기", str(app_config.OUTPUT_DIR),
                                              "summary.json (summary.json);;JSON (*.json)")
        if path:
            self.load_result_file(Path(path))

    def _open_output_folder(self) -> None:
        folder = self.result.output_dir if self.result is not None else app_config.OUTPUT_DIR
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _show_about(self) -> None:
        QMessageBox.about(self, "프로그램 정보",
                          "산불 확산 예측 및 등산객 대피 안내 시스템\n\n"
                          "C 계산 엔진(wildfire.exe) + Python GUI(PySide6, PyQtGraph)\n"
                          "C언어기초 팀 프로젝트")

    def closeEvent(self, event) -> None:
        self.runner.stop()
        self.runner.wait(3000)
        super().closeEvent(event)
