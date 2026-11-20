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
if errorlevel 1 (
    echo [오류] cl.exe 를 찾을 수 없습니다.
    echo        시작 메뉴에서 "Developer Command Prompt for VS 2022" 를 열고 다시 실행하세요.
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

echo.
echo [빌드 성공] bin\wildfire.exe
echo 실행 예: bin\wildfire.exe ..\data\scenarios\spring_dry_base.ini --mode printmap
endlocal
