"""
다크 테마와 색상표

화면 전체의 색을 한 곳에서 관리한다. (연료 색, 불 색, 경보 단계 색, 위젯 스타일)
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# 기본 색
# ----------------------------------------------------------------------
BACKGROUND = "#1e1f22"
PANEL = "#2b2d31"
PANEL_LIGHT = "#35373c"
BORDER = "#45474d"
TEXT = "#e3e5e8"
TEXT_DIM = "#9a9ca3"
ACCENT = "#e8743b"        # 강조색 (주황, 산불 느낌)
ACCENT_HOVER = "#f08a55"
ERROR = "#f05454"
WARNING = "#f0b429"
SUCCESS = "#4caf7a"

# ----------------------------------------------------------------------
# 지도 색 (R, G, B)
# ----------------------------------------------------------------------
# 연료 코드 → 색. fuel_models.csv 의 코드와 같다.
FUEL_COLORS = {
    0: (70, 70, 70),       # 연료 없음
    1: (214, 200, 90),     # 초지
    2: (160, 165, 75),     # 관목
    3: (38, 105, 62),      # 침엽수
    4: (100, 160, 75),     # 활엽수
    5: (68, 132, 72),      # 혼효림
    7: (165, 165, 165),    # 도로
    8: (60, 125, 210),     # 물
    9: (125, 115, 105),    # 바위
}

FUEL_NAMES = {
    0: "연료 없음", 1: "초지", 2: "관목", 3: "침엽수", 4: "활엽수",
    5: "혼효림", 7: "도로", 8: "물", 9: "바위·나지",
}

FIRE_NEW = (255, 230, 80)     # 막 붙은 불 (노랑)
FIRE_OLD = (215, 40, 20)      # 오래 탄 불 (빨강)
BURNED = (28, 26, 26)         # 전소 (검정에 가까운 회색)
FIREBREAK = (250, 250, 250)   # 방화선

TRAIL_COLOR = (245, 245, 235)
IGNITION_COLOR = (255, 60, 200)

NODE_COLORS = {
    "PARKING": (90, 170, 255),
    "SHELTER": (90, 220, 140),
    "SUMMIT": (240, 240, 240),
    "JUNCTION": (200, 200, 200),
    "POINT": (200, 200, 200),
}

# 경보 단계 색 (4단계에서 사용)
ALERT_COLORS = {
    "NONE": "#4caf7a",
    "CAUTION": "#f0d43a",
    "PREPARE": "#f09a3a",
    "IMMEDIATE": "#f05454",
    "ISOLATED": "#b05cf0",
}

# 로그 태그별 글자색
LOG_COLORS = {
    "INFO": TEXT,
    "WARN": WARNING,
    "ERROR": ERROR,
    "PROGRESS": TEXT_DIM,
    "RESULT": SUCCESS,
    "DONE": SUCCESS,
    "TEXT": "#b8bac0",
    "GUI": ACCENT,
}

MONO_FONT = "Consolas, 'D2Coding', 'Courier New', monospace"

# ----------------------------------------------------------------------
# Qt 스타일시트 (CSS와 비슷한 문법)
# ----------------------------------------------------------------------
STYLE_SHEET = f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT};
    font-size: 10pt;
}}
QMainWindow::separator {{ background: {BORDER}; width: 2px; height: 2px; }}
QDockWidget::title {{ background: {PANEL}; padding: 6px; }}
QGroupBox {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {ACCENT};
    font-weight: bold;
}}
QPushButton {{
    background-color: {PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 6px 12px;
}}
QPushButton:hover {{ background-color: {BORDER}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; }}
QPushButton#primary {{
    background-color: {ACCENT};
    border: none;
    color: white;
    font-weight: bold;
}}
QPushButton#primary:hover {{ background-color: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background-color: {PANEL_LIGHT}; color: {TEXT_DIM}; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background-color: {PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 3px 6px;
}}
QSlider::groove:horizontal {{ height: 6px; background: {PANEL_LIGHT}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; margin: -5px 0; border-radius: 7px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 4px; }}
QTabBar::tab {{
    background: {PANEL};
    padding: 7px 16px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{ background: {PANEL_LIGHT}; color: {ACCENT}; }}
QProgressBar {{
    background-color: {PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    height: 16px;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 3px; }}
QPlainTextEdit, QTextEdit {{
    background-color: #17181a;
    border: 1px solid {BORDER};
    font-family: {MONO_FONT};
    font-size: 9pt;
}}
QLabel#statusText {{ font-weight: bold; }}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#infoBar {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    font-family: {MONO_FONT};
}}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QLabel, QCheckBox, QRadioButton, QSlider, QWidget#transparent {{ background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 13px; height: 13px;
    border: 1px solid #6a6d75;
    background: {PANEL_LIGHT};
}}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
}}
QScrollArea {{ border: none; }}
QToolTip {{ background-color: {PANEL_LIGHT}; color: {TEXT}; border: 1px solid {BORDER}; }}
"""


def apply_theme(app) -> None:
    """QApplication 에 다크 테마를 적용한다."""
    app.setStyleSheet(STYLE_SHEET)
