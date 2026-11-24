@echo off
chcp 65001 >nul
rem ============================================================
rem  wildfire.exe 빌드 스크립트 (Windows + Visual Studio 2022)
rem  사용법: "Developer Command Prompt for VS 2022" 를 열고
rem          이 파일이 있는 c_core 폴더에서  build.bat  실행
rem ============================================================
setlocal
cd /d "%~dp0"

where cl >nul 2>nul
if errorlevel 1 call :find_visual_studio
where cl >nul 2>nul
if errorlevel 1 (
    echo [오류] cl.exe 를 찾을 수 없습니다. Visual Studio 2022 의 "C++를 사용한 데스크톱 개발"이 설치돼 있는지 확인하세요.
    echo        또는 시작 메뉴에서 "Developer Command Prompt for VS 2022" 를 열고 다시 실행하세요.
    exit /b 1
)

if not exist bin mkdir bin

rem  /std:c11   C11 표준          /W4    경고 수준 4 (가장 엄격한 일반 수준)
rem  /utf-8     소스·출력 모두 UTF-8 (한글 주석·메시지)
rem  /D_CRT_SECURE_NO_WARNINGS   fopen 등 보안 경고 끄기
cl /nologo /std:c11 /W4 /utf-8 /O2 /D_CRT_SECURE_NO_WARNINGS /I include src\*.c /Fobin\ /Febin\wildfire.exe
if errorlevel 1 (
    echo.
    echo [빌드 실패] 위의 오류 메시지를 확인하세요.
    exit /b 1
)

if not exist bin\wildfire.exe (
    echo.
    echo [경고] 컴파일은 끝났지만 bin\wildfire.exe 가 없습니다. 백신 프로그램이 격리했는지 확인하세요.
    exit /b 1
)

echo.
echo [빌드 성공] %CD%\bin\wildfire.exe
echo GUI 는 이 폴더의 exe 를 사용합니다. GUI 를 실행하는 저장소 폴더와 같은 곳인지 확인하세요.
echo 실행 예: bin\wildfire.exe ..\data\scenarios\mountain_bukhansan.ini --mode printmap
endlocal
exit /b 0

rem ------------------------------------------------------------
rem  일반 명령 창에서 실행했을 때: vswhere 로 Visual Studio 를 찾아 컴파일러 환경(vcvars64)을 불러온다
rem ------------------------------------------------------------
:find_visual_studio
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" exit /b 0
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSDIR=%%i"
if not defined VSDIR exit /b 0
if exist "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" call "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" >nul
exit /b 0
