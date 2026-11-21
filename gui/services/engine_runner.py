"""
C 엔진 실행기

wildfire.exe 를 subprocess 로 실행하고, 표준출력을 한 줄씩 읽어 Qt 시그널로 화면에 전달한다.
엔진이 오래 걸려도 화면이 멈추지 않도록 별도 스레드(QThread)에서 실행한다.

C 엔진 출력 규칙 (c_core/src/log.c):
    [INFO] 메시지      [WARN] 메시지      [ERROR] 메시지
    [PROGRESS] 35 메시지                 [RESULT] 결과 파일 경로
    [DONE] 걸린 시간                     (태그가 없는 줄: 콘솔 지도·표)
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from services import app_config

LINE_PATTERN = re.compile(r"^\[(?P<tag>[A-Z]+)\]\s?(?P<text>.*)$")


@dataclass
class EngineLine:
    """엔진 출력 한 줄을 해석한 결과"""
    tag: str            # INFO, WARN, ERROR, PROGRESS, RESULT, DONE, TEXT(태그 없음)
    text: str
    percent: int = -1   # PROGRESS 줄일 때 진행률


def parse_engine_line(line: str) -> EngineLine:
    """'[PROGRESS] 35 확산 ...' 같은 한 줄을 태그·진행률·내용으로 나눈다."""
    line = line.rstrip("\r\n")
    match = LINE_PATTERN.match(line)
    if not match:
        return EngineLine("TEXT", line)
    tag, text = match.group("tag"), match.group("text")
    if tag == "PROGRESS":
        first, _, rest = text.partition(" ")
        if first.isdigit():
            return EngineLine(tag, rest, int(first))
    return EngineLine(tag, text)


def engine_missing_help(exe: Path) -> list[str]:
    """엔진 실행 파일이 없을 때 보여 줄 안내 (어디를 찾았는지, 무엇을 확인할지)"""
    return [
        f"엔진 실행 파일이 없습니다: {exe}",
        f"→ 이 GUI 가 쓰는 c_core 폴더: {app_config.ENGINE_DIR}",
        "→ 바로 이 c_core 폴더에서 build.bat 을 실행하세요. (다른 폴더에 압축을 푼 복사본에서 빌드하면 그 복사본에 exe 가 생깁니다)",
        "→ 빌드가 끝났는데도 없으면 백신 프로그램이 wildfire.exe 를 격리했는지 확인하세요.",
    ]


class _EngineWorker(QObject):
    """별도 스레드에서 실제로 엔진을 실행하는 일꾼"""

    line_received = Signal(object)    # EngineLine
    finished = Signal(int)            # 종료 코드

    def __init__(self, command: list[str], cwd: Path):
        super().__init__()
        self.command = command
        self.cwd = cwd
        self.process: subprocess.Popen | None = None

    @Slot()
    def run(self) -> None:
        # Windows 에서 엔진을 실행할 때 검은 콘솔 창이 뜨지 않게 한다
        flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
        try:
            self.process = subprocess.Popen(
                self.command, cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=flags)
        except OSError as error:
            self.line_received.emit(EngineLine("ERROR", f"엔진을 실행할 수 없음: {error}"))
            self.finished.emit(-1)
            return

        assert self.process.stdout is not None
        for raw in self.process.stdout:          # 엔진이 한 줄 출력할 때마다 바로 읽힘
            self.line_received.emit(parse_engine_line(raw))
        self.finished.emit(self.process.wait())

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()


class EngineRunner(QObject):
    """
    화면에서 쓰는 엔진 실행 관리자.

    사용법:
        runner = EngineRunner()
        runner.line_received.connect(...)   # 한 줄마다
        runner.finished.connect(...)        # (종료 코드, 결과 파일 경로)
        runner.start(scenario_path, "run")
    """

    line_received = Signal(object)        # EngineLine
    finished = Signal(int, str)           # 종료 코드, [RESULT] 경로 (없으면 "")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _EngineWorker | None = None
        self._result_path = ""

    def is_running(self) -> bool:
        return self._thread is not None

    def start(self, scenario_path: Path, mode: str, extra_args: list[str] | None = None) -> bool:
        """엔진을 실행한다. 실행 파일이 없거나 이미 실행 중이면 False."""
        if self.is_running():
            return False
        exe = app_config.engine_path()
        if not exe.exists():
            for text in engine_missing_help(exe):
                self.line_received.emit(EngineLine("ERROR", text))
            return False
        if exe != app_config.expected_engine_path():
            self.line_received.emit(EngineLine("WARN", f"c_core/bin 에 엔진이 없어 다른 위치의 엔진을 사용합니다: {exe}"))

        command = [str(exe), str(scenario_path.resolve()), "--mode", mode, *(extra_args or [])]
        self.line_received.emit(EngineLine("GUI", "실행: " + " ".join(command)))
        self._result_path = ""

        self._thread = QThread()
        self._worker = _EngineWorker(command, app_config.ENGINE_DIR)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.line_received.connect(self._on_line)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()

    def wait(self, timeout_ms: int = 5000) -> None:
        """(테스트·종료용) 실행이 끝날 때까지 기다린다."""
        if self._thread is not None:
            self._thread.wait(timeout_ms)

    @Slot(object)
    def _on_line(self, line: EngineLine) -> None:
        if line.tag == "RESULT":
            self._result_path = str(app_config.resolve_engine_path(line.text.strip()))
        self.line_received.emit(line)

    @Slot(int)
    def _on_finished(self, code: int) -> None:
        thread = self._thread
        self._thread = None
        self._worker = None
        if thread is not None:
            thread.quit()
            thread.wait()
        self.finished.emit(code, self._result_path)
