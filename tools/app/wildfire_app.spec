# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 설정: GUI(gui/main.py)를 WildfireResponse.exe 로 묶는다.  사용: make_app.bat
# C 엔진(wildfire.exe)과 산 자료(data/)는 묶지 않고 exe 옆 폴더에 둔다 (엔진이 파일을 읽고 결과를 써야 하므로).
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]
GUI = ROOT / "gui"
ICON = ROOT / "mobile" / "icons" / "icon-192.png"

a = Analysis(
    [str(GUI / "main.py")],
    pathex=[str(GUI)],
    # pyqtgraph 는 일부 모듈을 실행 중에 불러오므로 미리 모두 넣는다 (예제·3D·주피터는 쓰지 않으므로 뺌).
    # 화면·서비스 모듈(gui/views, gui/services)은 main.py 에서 따라가며 자동으로 찾는다.
    hiddenimports=collect_submodules(
        "pyqtgraph", filter=lambda name: not any(part in name for part in (".examples", ".opengl", ".jupyter"))),
    excludes=["pyqtgraph.examples", "pyqtgraph.opengl", "pyqtgraph.jupyter", "tkinter", "matplotlib", "pyarrow", "pyproj", "shapefile", "PyQt5", "PyQt6", "PySide2", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="WildfireResponse",
    console=False,                      # 콘솔 창 없이 GUI 만
    icon=str(ICON) if ICON.exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="WildfireResponse")
