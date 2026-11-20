# 산불 확산 예측 및 등산객 대피 안내 시스템

실제 기상 데이터를 받아 산불이 어떻게 번질지 예측하고, 산에 있는 등산객에게 가장 안전한 대피 경로를 안내하며,
방화선·진화 헬기를 어디에 배치하면 피해가 가장 줄어드는지 계산하는 시스템입니다.

- **C 계산 엔진** (`c_core/`, `wildfire.exe`): 지도 읽기, 확산 시뮬레이션, 대피 경로, 진화 전략 등 모든 계산
- **Python GUI** (`gui/`): 화면, 애니메이션, 기상 API 다운로드, 가상 지형 생성

> 현재 진행 상황: **1단계 완료** (C 데이터 구조 + 지도·설정 읽기 + 콘솔 지도 출력)
> 전체 설계는 [`docs/PROJECT_SPECIFICATION.md`](docs/PROJECT_SPECIFICATION.md), 단계별 기록은 [`docs/CHANGELOG.md`](docs/CHANGELOG.md)

---

## 1. 폴더 구조

```
wildfire_project/
├── c_core/            C 계산 엔진
│   ├── include/       헤더 (구조체 정의: wf_types.h)
│   ├── src/           소스 (기능별 파일)
│   ├── build.bat      Windows 빌드 스크립트 (Visual Studio 2022)
│   └── build.sh       macOS/Linux 확인용 빌드 스크립트
├── gui/               Python (services/ 에 지형·등산로 생성기)
├── data/
│   ├── maps/          지형·연료 격자 (.asc)
│   ├── trails/        등산로 그래프, 등산객 목록
│   ├── weather/       기상 데이터 (CSV)
│   └── scenarios/     시나리오 설정 (.ini), 연료 모델 표, tests/ (오류 확인용)
├── output/            C가 저장하는 결과 (2단계부터)
├── tools/             count_lines.py (줄 수 집계)
└── docs/              설계 문서, 변경 기록, 줄 수, 프롬프트 기록
```

## 2. 준비물

| 항목 | 버전 | 용도 |
|---|---|---|
| Visual Studio 2022 | "C++를 사용한 데스크톱 개발" 워크로드 | C 엔진 빌드 (MSVC) |
| Python | 3.12 | GUI, 데이터 생성 |
| Python 패키지 | `python -m pip install -r gui/requirements.txt` | numpy, PySide6, pyqtgraph, requests |

## 3. C 엔진 빌드

### 방법 A: build.bat (추천)

1. 시작 메뉴에서 **"Developer Command Prompt for VS 2022"** 를 엽니다. (일반 cmd 에서는 `cl` 을 찾지 못합니다)
2. 프로젝트의 `c_core` 폴더로 이동해 빌드합니다.

```bat
cd 경로\wildfire_project\c_core
build.bat
```

성공하면 `c_core\bin\wildfire.exe` 가 만들어집니다.
사용하는 컴파일 옵션: `/std:c11 /W4 /utf-8 /O2 /D_CRT_SECURE_NO_WARNINGS`

### 방법 B: Visual Studio 빈 프로젝트

1. Visual Studio 2022 → **새 프로젝트 만들기** → **빈 프로젝트**(C++) → 이름 `wildfire`, 위치는 아무 곳이나.
2. 솔루션 탐색기에서 **소스 파일** 우클릭 → **추가 → 기존 항목** → `c_core\src\*.c` 를 모두 선택.
3. **헤더 파일** 우클릭 → **추가 → 기존 항목** → `c_core\include\*.h` 를 모두 선택.
4. 프로젝트 우클릭 → **속성** (위쪽 "구성"을 **모든 구성**, "플랫폼"을 **x64**로 선택한 뒤 아래를 설정)

   | 위치 | 항목 | 값 |
   |---|---|---|
   | C/C++ → 일반 | 추가 포함 디렉터리 | `...\wildfire_project\c_core\include` (실제 경로) |
   | C/C++ → 일반 | 경고 수준 | 수준 4 (`/W4`) |
   | C/C++ → 일반 | SDL 검사 | 아니요 (`/sdl-`) |
   | C/C++ → 언어 | C 언어 표준 | ISO C11 표준 (`/std:c11`) |
   | C/C++ → 전처리기 | 전처리기 정의 | 맨 앞에 `_CRT_SECURE_NO_WARNINGS;` 추가 |
   | C/C++ → 명령줄 | 추가 옵션 | `/utf-8` |
   | 링커 → 시스템 | 하위 시스템 | 콘솔 (`/SUBSYSTEM:CONSOLE`) |
   | 디버깅 | 명령 인수 | `..\data\scenarios\spring_dry_base.ini --mode printmap` |
   | 디버깅 | 작업 디렉터리 | `...\wildfire_project\c_core` (실제 경로) |

5. **Ctrl+Shift+B** 로 빌드, **Ctrl+F5** 로 실행.

> `/utf-8` 이 없으면 한글 주석·메시지 때문에 경고(C4819)나 글자 깨짐이 생깁니다.

### (참고) macOS / Linux

```bash
cd c_core && ./build.sh
```

## 4. 실행 (1단계)

`c_core` 폴더에서 실행합니다.

```bat
bin\wildfire.exe ..\data\scenarios\spring_dry_base.ini --mode printmap
```

출력 내용:
1. 시나리오 요약 (시작 시각, 발화 지점, 경보 기준, 진화 자원 …)
2. 지형 통계 (고도·경사, 연료 구성 비율, 등산로 노드·간선 목록, 등산객 목록)
3. 고도 지도와 연료 지도 (2칸마다 1글자, `--step 1` 로 바꾸면 모든 칸 출력)

명령줄 옵션:

| 옵션 | 설명 |
|---|---|
| `--mode printmap` | 지도·요약 출력 (1단계에서 사용할 수 있는 모드) |
| `--mode run / evac / optimize / mc / all` | 2단계 이후에 구현 |
| `--out <폴더>` | 결과 폴더 지정 |
| `--seed <정수>` | 난수 시드 지정 |
| `--step <정수>` | 콘솔 지도에서 몇 칸마다 한 글자를 찍을지 |

종료 코드: `0` 성공, `1` 입력 오류, `2` 메모리 부족, `3` 기타(미구현 모드 등)

### 오류 메시지 확인 (일부러 틀린 시나리오)

```bat
bin\wildfire.exe ..\data\scenarios\tests\bad_values.ini --mode printmap
bin\wildfire.exe ..\data\scenarios\tests\bad_ignition.ini --mode printmap
bin\wildfire.exe ..\data\scenarios\tests\missing_file.ini --mode printmap
bin\wildfire.exe ..\data\scenarios\tests\bad_trail.ini --mode printmap
```

각각 "몇 번째 줄의 어떤 값이 왜 틀렸는지"를 `[ERROR]` 줄로 알려 주고 종료 코드 1로 끝납니다.

## 5. 샘플 데이터 다시 만들기

가상 산(200 × 200칸, 30 m, 최고 950 m)과 등산로는 Python 생성기로 만듭니다. 프로젝트 폴더에서:

```bash
python gui/services/terrain_generator.py
```

```bash
python gui/services/trail_generator.py
```

`--size`, `--cell`, `--seed`, `--max-elev` 옵션으로 다른 산을 만들 수 있습니다. (`--help` 참고)
실제 지형을 쓰려면 QGIS 등에서 DEM을 **ESRI ASCII Grid (.asc)** 로 내보내 `data/maps/` 에 넣고 시나리오의 `elevation_file` 을 바꾸면 됩니다.

## 6. 줄 수 집계

```bash
python tools/count_lines.py
```

결과는 `docs/LINE_COUNT.md` 에 저장됩니다.

## 7. 참고 알고리즘 출처

| 알고리즘 | 사용 위치 | 출처 |
|---|---|---|
| Horn 경사 계산 | `map_io.c` `compute_slope_aspect` | Horn, B.K.P. (1981). Hill shading and the reflectance map. *Proc. IEEE* 69(1) |
| Bresenham 직선 | `trail_io.c` `add_line_cells` | Bresenham, J.E. (1965). Algorithm for computer control of a digital plotter. *IBM Systems Journal* 4(1) |
| 너비 우선 탐색(BFS) | `trail_io.c` `check_exits_reachable` | 일반적인 그래프 알고리즘 (자료구조 교과서) |

2단계 이후 사용할 모델(Rothermel, Simard, Tobler 등)의 출처는 `docs/PROJECT_SPECIFICATION.md` 6장에 있습니다.
