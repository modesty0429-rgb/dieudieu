@echo off
chcp 65001 >nul
rem ============================================================
rem  make_app.bat — PC 관제용 프로그램을 Windows 앱 하나로 묶는다 (Python 없이 실행되는 폴더 + zip)
rem    결과: dist\WildfireResponse\WildfireResponse.exe  (폴더째 복사·압축해서 배포)
rem          dist\WildfireResponse.zip
rem    1) Python 가상환경(.venv_app)에 라이브러리 + PyInstaller 설치
rem    2) C 엔진 빌드 (c_core\build.bat)
rem    3) PyInstaller 로 GUI 를 exe 로 묶기 (tools\app\wildfire_app.spec)
rem    4) 엔진·산 자료·설정 예시·사용법을 옆에 복사 → 5) zip
rem  필요한 것: Python 3.12, Visual Studio 2022 (이 PC 에서만. 앱을 받는 사람은 아무것도 필요 없음)
rem ============================================================
setlocal
cd /d "%~dp0"
set "APP=WildfireResponse"
set "OUT=dist\%APP%"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [오류] Python 3.12 를 찾을 수 없습니다.
    pause
    exit /b 1
)

echo [1/5] 가상환경과 라이브러리 준비...
if not exist .venv_app\Scripts\python.exe %PY% -m venv .venv_app
if errorlevel 1 goto :fail
.venv_app\Scripts\python.exe -m pip install --disable-pip-version-check -q -r tools\app\requirements_app.txt pyinstaller
if errorlevel 1 goto :fail

echo [2/5] C 엔진 빌드...
call c_core\build.bat
if errorlevel 1 goto :fail

echo [3/5] 프로그램을 exe 로 묶는 중... (몇 분 걸림)
if exist "%OUT%" rmdir /s /q "%OUT%"
.venv_app\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller tools\app\wildfire_app.spec
if errorlevel 1 goto :fail

echo [4/5] 엔진·산 자료 복사...
mkdir "%OUT%\c_core\bin" >nul 2>nul
copy /y c_core\bin\wildfire.exe "%OUT%\c_core\bin\" >nul
robocopy data "%OUT%\data" /e /xd raw _cache /xf gui_custom.ini gui_trails.txt gui_hikers.txt kma_*.csv /njh /njs /nfl /ndl >nul
mkdir "%OUT%\config" >nul 2>nul
copy /y config\api_keys.example.ini "%OUT%\config\" >nul
copy /y tools\app\사용법.txt "%OUT%\" >nul
if not exist "%OUT%\c_core\bin\wildfire.exe" (
    echo [오류] 엔진이 복사되지 않았습니다. 백신 프로그램이 격리했는지 확인하세요.
    goto :fail
)

echo [5/5] 압축...
if exist "dist\%APP%.zip" del /q "dist\%APP%.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\%APP%' -DestinationPath 'dist\%APP%.zip'"
if errorlevel 1 goto :fail

echo.
echo [완성] %CD%\%OUT%\%APP%.exe
echo        배포용 압축 파일: %CD%\dist\%APP%.zip
echo        (API 키 파일 config\api_keys.ini 는 넣지 않았습니다. 받는 사람이 필요하면 직접 넣습니다)
pause
exit /b 0

:fail
echo.
echo [실패] 위의 오류 메시지를 확인하세요.
pause
exit /b 1
