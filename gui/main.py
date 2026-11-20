"""
산불 확산 예측 및 등산객 대피 안내 시스템 — GUI 시작점

실행 (프로젝트 폴더에서):
    python gui/main.py

먼저 C 엔진을 빌드해 두어야 한다. (c_core/build.bat)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# gui 폴더를 import 경로에 넣어 'services', 'views', 'theme' 을 바로 import 할 수 있게 한다
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")    # pyqtgraph 가 PySide6 를 쓰도록

from PySide6.QtWidgets import QApplication  # noqa: E402

import theme  # noqa: E402
from views.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Wildfire Simulator")
    theme.apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
