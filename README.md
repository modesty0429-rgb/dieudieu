# 산불 확산 예측 및 등산객 대피 안내 시스템

실제 기상 데이터를 받아 산불이 어떻게 번질지 예측하고, 산에 있는 등산객에게 가장 안전한 대피 경로를 안내하며,
방화선·진화 헬기를 어디에 배치하면 피해가 가장 줄어드는지 계산하는 시스템입니다.

- **C 계산 엔진** (`c_core/`, `wildfire.exe`): 지도 읽기, 확산 시뮬레이션, 대피 경로, 진화 전략 등 모든 계산
- **Python GUI** (`gui/`): 화면, 애니메이션, 기상 API 다운로드, 가상 지형 생성

> 현재 진행 상황: **3단계 완료** (Python GUI 기본 화면 + 결과 재생 애니메이션)
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

## 4. 실행

`c_core` 폴더에서 실행합니다.

### 4-1. 지도 확인 (printmap)

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
| `--mode printmap` | 지도·요약 출력 |
| `--mode run` | 산불 확산 시뮬레이션 + 결과 저장 |
| `--mode evac / optimize / mc / all` | 4단계 이후에 구현 |
| `--map-every <분>` | run 모드에서 이 간격마다 콘솔에 화재 지도 출력 |
| `--out <폴더>` | 결과 폴더 지정 |
| `--seed <정수>` | 난수 시드 지정 |
| `--step <정수>` | 콘솔 지도에서 몇 칸마다 한 글자를 찍을지 |

종료 코드: `0` 성공, `1` 입력 오류, `2` 메모리 부족, `3` 기타(미구현 모드 등)

### 4-2. 확산 시뮬레이션 (run)

```bat
bin\wildfire.exe ..\data\scenarios\spring_dry_base.ini --mode run
```

콘솔에 30분 간격 통계 표와 마지막 시각의 화재 지도(`@` 연소 중, `x` 전소)가 나오고,
결과는 시나리오의 `output_dir`(기본: `output/spring_dry_base/`)에 저장됩니다.

| 파일 | 내용 |
|---|---|
| `summary.json` | 시나리오·격자 정보, 최종 피해 면적, 비화 횟수, 다른 결과 파일 이름 |
| `arrival_time.csv` | 셀별 불 도착 시각(분), 도착하지 않았으면 -1 (한 줄 = 격자 한 행, 첫 줄이 북쪽) |
| `burnout_time.csv` | 셀별 전소 시각(분) |
| `fire_events.csv` | `time_min,x,y,state` — 상태가 바뀐 셀만 시간순 |
| `stats.csv` | 10분 간격 통계 (연소 중 셀, 피해 면적, 최대 확산 속도, 비화, 기상, 연료 수분) |
| `run.log` | 콘솔 로그 사본 |

다른 실험:

```bat
bin\wildfire.exe ..\data\scenarios\spring_dry_base.ini --mode run --map-every 60
bin\wildfire.exe ..\data\scenarios\spring_dry_base.ini --mode run --seed 7 --out ..\output\seed7
bin\wildfire.exe ..\data\scenarios\calm_fixed_weather.ini --mode run
```

- `--map-every 60`: 1시간마다 화재 지도 출력
- `--seed 7`: 비화 난수가 바뀌어 결과가 달라짐 (같은 시드는 항상 같은 결과)
- `calm_fixed_weather.ini`: 바람이 없을 때 → 오르막(북쪽 주봉) 방향으로 더 번지는 것을 확인

계산 모델(수식, 근거/가정 구분)은 [`docs/model.md`](docs/model.md)에 정리했습니다.

### 4-3. 오류 메시지 확인 (일부러 틀린 시나리오)

```bat
bin\wildfire.exe ..\data\scenarios\tests\bad_values.ini --mode printmap
bin\wildfire.exe ..\data\scenarios\tests\bad_ignition.ini --mode printmap
bin\wildfire.exe ..\data\scenarios\tests\missing_file.ini --mode printmap
bin\wildfire.exe ..\data\scenarios\tests\bad_trail.ini --mode printmap
bin\wildfire.exe ..\data\scenarios\tests\bad_weather.ini --mode run
```

각각 "몇 번째 줄의 어떤 값이 왜 틀렸는지"를 `[ERROR]` 줄로 알려 주고 종료 코드 1로 끝납니다.

## 5. GUI 실행

먼저 3장대로 C 엔진을 빌드하고, Python 패키지를 설치합니다. (프로젝트 폴더에서)

```bash
python -m pip install -r gui/requirements.txt
```

```bash
python gui/main.py
```

| 화면 | 사용법 |
|---|---|
| 맨 위 "엔진 상태" | C 엔진이 출력하는 `[INFO]`, `[PROGRESS]` 줄과 진행률이 실시간으로 표시됨 |
| 왼쪽 "시나리오 설정" | 기본 시나리오, 계절, 발화 지점, 기상(파일 / 직접 입력), 진행 시간, 시드를 고르고 **🔥 시뮬레이션 실행** |
| 지도 | 음영기복 + 연료 색 + 등고선 위에 불(노랑 → 빨강 → 검정), 등산로, 대피소·주차장, 등산객(▲), 발화 지점(★). **지도를 클릭하면 발화 지점이 바뀜**. 마우스를 올리면 셀 정보 표시 |
| 레이어 체크박스 | 연료 색, 등고선, 불, 도착 등시선(60분 간격), 등산로, 등산객 켜기/끄기 |
| 재생 컨트롤 | ▶ 재생 / ⏸ 일시정지, 타임라인 슬라이더로 원하는 시각으로 이동, 재생 속도 |
| "엔진 로그" 탭 | C 엔진 출력 전체 (콘솔 지도·통계 표 포함). 엔진이 오류로 끝나면 자동으로 이 탭으로 이동 |
| 파일 메뉴 | 예전 결과(`summary.json`) 불러오기, 결과 폴더 열기 |

GUI는 설정을 `data/scenarios/gui_custom.ini` 로 저장한 뒤 `c_core` 폴더에서 엔진을 실행하고,
결과는 `output/gui_custom/` 에 저장됩니다. 계절 프리셋 값은 `data/scenarios/season_presets.ini` 에 있습니다.

## 6. 샘플 데이터 다시 만들기

가상 산(200 × 200칸, 30 m, 최고 950 m)과 등산로는 Python 생성기로 만듭니다. 프로젝트 폴더에서:

```bash
python gui/services/terrain_generator.py
```

```bash
python gui/services/trail_generator.py
```

`--size`, `--cell`, `--seed`, `--max-elev` 옵션으로 다른 산을 만들 수 있습니다. (`--help` 참고)
실제 지형을 쓰려면 QGIS 등에서 DEM을 **ESRI ASCII Grid (.asc)** 로 내보내 `data/maps/` 에 넣고 시나리오의 `elevation_file` 을 바꾸면 됩니다.

## 7. 줄 수 집계

```bash
python tools/count_lines.py
```

결과는 `docs/LINE_COUNT.md` 에 저장됩니다.

## 8. 참고 알고리즘 출처

| 알고리즘 | 사용 위치 | 출처 |
|---|---|---|
| Horn 경사 계산 | `map_io.c` `compute_slope_aspect` | Horn, B.K.P. (1981). Hill shading and the reflectance map. *Proc. IEEE* 69(1) |
| Bresenham 직선 | `trail_io.c` `add_line_cells` | Bresenham, J.E. (1965). Algorithm for computer control of a digital plotter. *IBM Systems Journal* 4(1) |
| 너비 우선 탐색(BFS) | `trail_io.c` `check_exits_reachable` | 일반적인 그래프 알고리즘 (자료구조 교과서) |
| Rothermel 확산 모델 (단순화) | `spread_rate.c` | Rothermel, R.C. (1972). USDA Forest Service INT-115 |
| Simard 평형 수분 | `fuel_moisture.c` | Simard, A.J. (1968). The moisture content of forest fuels |
| xorshift32 난수 | `rng.c` | Marsaglia, G. (2003). Xorshift RNGs. *J. Stat. Software* 8(14) |
| Box-Muller 정규 난수 | `rng.c` | Box, G.E.P. & Muller, M.E. (1958). *Ann. Math. Stat.* 29(2) |

이후 단계에서 쓸 모델(Tobler 보행 함수 등)의 출처는 `docs/PROJECT_SPECIFICATION.md` 6장에 있습니다.
