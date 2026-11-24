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


def self_test(app: QApplication) -> int:
    """
    --selftest: 묶은 앱(exe)이 제대로 만들어졌는지 스스로 점검한다. (make_app.bat 뒤 확인용)
    화면을 띄우지 않고 산 목록·지도 읽기 → C 엔진 실행(대피 계산) → 결과 읽기까지 해 보고,
    결과를 output/selftest.txt 에 쓴 뒤 종료 코드(0 = 성공)로 돌려준다.
    """
    import subprocess

    from services import app_config
    from services.result_loader import load_result

    lines = [f"프로그램 폴더: {app_config.PROJECT_ROOT}"]
    ok = False
    try:
        scenarios = app_config.list_scenarios()
        lines.append(f"산 {len(scenarios)}곳: " + ", ".join(p.stem for p in scenarios))
        window = MainWindow()                                   # 화면 모듈이 모두 들어 있는지
        window.close()
        out_dir = app_config.OUTPUT_DIR / "selftest"
        command = [str(app_config.engine_path()), str(app_config.DEFAULT_SCENARIO), "--mode", "evac",
                   "--out", str(out_dir)]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
        done = subprocess.run(command, cwd=app_config.ENGINE_DIR, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=300, creationflags=flags)
        lines.append(f"엔진 종료 코드 {done.returncode}: {command[0]}")
        result = load_result(out_dir / "summary.json")
        evac = result.evacuation.summary if result.evacuation else {}
        lines.append(f"피해 {result.summary['result']['burned_area_ha']:.1f} ha, "
                     f"대피 {evac.get('evacuated', 0)}팀 / 완료 {evac.get('safe', 0)}팀")
        ok = done.returncode == 0
    except Exception as error:                                  # 점검용이므로 모든 오류를 기록
        lines.append(f"오류: {type(error).__name__}: {error}")
    lines.append("결과: " + ("성공" if ok else "실패"))
    app_config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (app_config.OUTPUT_DIR / "selftest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 1


def main() -> int:
    app = QApplication(sys.argv)
    if "--selftest" in sys.argv:
        return self_test(app)
    app.setApplicationName("Wildfire Simulator")
    theme.apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
