@echo off
chcp 65001 >nul
rem ============================================================
rem  실행.bat — 더블클릭하면 산불 확산 예측·대피 안내 시스템(PC 관제용)을 연다
rem    1) Python 확인 → 2) 필요한 라이브러리 설치(처음 한 번) → 3) C 엔진 빌드(없거나 C 코드가 바뀌었을 때)
rem    → 4) 프로그램 실행
rem  필요한 것: Python 3.12, Visual Studio 2022 ("C++를 사용한 데스크톱 개발")
rem  Python·Visual Studio 없이 쓰려면 make_app.bat 으로 만든 앱(dist\WildfireResponse)을 쓰면 된다.
rem ============================================================
setlocal
cd /d "%~dp0"
title 산불 확산 예측 및 대피 안내 시스템

rem ---- 1) Python ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [오류] Python 을 찾을 수 없습니다. python.org 에서 Python 3.12 를 설치하세요.
    echo        설치할 때 "Add python.exe to PATH" 를 체크해야 합니다.
    pause
    exit /b 1
)

rem ---- 2) 라이브러리 (처음 한 번) ----
%PY% -c "import PySide6, pyqtgraph, numpy, requests, PIL" >nul 2>nul
if errorlevel 1 (
    echo [준비] 필요한 라이브러리를 설치합니다. 처음 한 번만 몇 분 걸립니다...
    %PY% -m pip install --disable-pip-version-check -r tools\app\requirements_app.txt
    if errorlevel 1 (
        echo [오류] 라이브러리 설치에 실패했습니다. 인터넷 연결을 확인하세요.
        pause
        exit /b 1
    )
)

rem ---- 3) C 엔진 (없거나, C 코드가 엔진보다 새로우면 다시 빌드) ----
set "NEED_BUILD="
if not exist c_core\bin\wildfire.exe set "NEED_BUILD=1"
if not defined NEED_BUILD (
    powershell -NoProfile -Command "$e=(Get-Item 'c_core\bin\wildfire.exe').LastWriteTime; if (Get-ChildItem c_core\src,c_core\include -File | Where-Object { $_.LastWriteTime -gt $e }) { exit 1 }"
    if errorlevel 1 set "NEED_BUILD=1"
)
if defined NEED_BUILD (
    echo [준비] C 엔진을 빌드합니다...
    call c_core\build.bat
    if errorlevel 1 (
        pause
        exit /b 1
    )
)

rem ---- 4) 실행 ----
echo [실행] 프로그램을 엽니다. 이 창은 닫아도 됩니다.
start "" %PY:py -3=pyw -3% gui\main.py
if errorlevel 1 %PY% gui\main.py
endlocal
