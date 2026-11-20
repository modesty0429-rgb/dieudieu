# 변경 기록 (CHANGELOG)

## 1단계 — C 데이터 구조, 지도·설정 읽기, 콘솔 지도 출력 (2026-11-20)

### 만든 것
- **구조체 정의** (`wf_types.h`): `Cell`, `Grid`, `FuelModel`, `WeatherRecord`/`WeatherSeries`, `TrailNode`/`TrailEdge`/`TrailGraph`, `Route`, `Hiker`, 설정 구조체들, 이것을 모두 묶는 `Scenario`. 이후 단계에서 쓸 구조체도 미리 정의.
- **공통 유틸**
  - `util.c`: 안전한 문자열 복사·자르기·나누기, 엄격한 숫자 변환(`parse_int_strict` 등), 날짜 검사, 경로 합치기, 각도 계산
  - `dynarray.c`: 자동으로 늘어나는 정수·실수 배열
  - `log.c`: `[INFO] [WARN] [ERROR] [PROGRESS] [RESULT] [DONE]` 형식 출력 (Python GUI 연동 규칙), Windows 콘솔 한글 출력 설정
  - `grid.c`: `Cell **` 2차원 동적 배열 생성·해제, 8방향 이웃 표
- **입력**
  - `scenario_io.c`: INI 시나리오 읽기. 오류를 한 번에 모두 찾아 "파일 몇 번째 줄, 어떤 키, 왜 틀렸는지" 출력. 설정끼리 맞지 않는 경우(경보 기준 순서 등)와 파일이 없는 경우도 검사.
  - `map_io.c`: ESRI ASCII Grid(.asc) 고도·연료 격자 읽기, 두 격자 크기 일치 검사, NODATA 처리, **Horn 방법으로 경사·경사 방향 계산**
  - `trail_io.c`: 등산로 그래프(노드·간선) 읽기, **Bresenham 직선으로 간선이 지나는 셀 계산**, 간선 실제 길이·오르막·내리막 계산, **BFS로 모든 노드에서 대피소·주차장에 갈 수 있는지 검사**, 등산객 파일 읽기
- **출력**: `console_view.c` — 시나리오 요약, 지형 통계, 고도 지도, 연료 지도(등산로·노드·등산객·발화 지점 겹쳐 그리기)
- **main.c**: 명령줄 인자(`--mode --out --seed --step`) 해석, `printmap` 모드
- **빌드**: `build.bat` (MSVC `/std:c11 /W4 /utf-8`), `build.sh` (확인용)
- **데이터**
  - `gui/services/terrain_generator.py`: 봉우리 3개·능선·계곡·저수지·도로가 있는 가상 산 생성(최고 950 m), 사면 방향에 따라 침엽수/활엽수/혼효림 배치
  - `gui/services/trail_generator.py`: 노드 11개, 간선 13개 등산로 + 등산객 5팀
  - `data/scenarios/spring_dry_base.ini`, `fuel_models.csv`, `data/weather/sample_spring_dry.csv` (근거/가정 표시)
  - `data/scenarios/tests/`: 오류 메시지 확인용 시나리오 4개
- **도구**: `tools/count_lines.py` → `docs/LINE_COUNT.md` 자동 생성

### 발표용 핵심 함수 (1단계)
| 함수 | 설명 |
|---|---|
| `load_scenario` (scenario_io.c) | 시나리오 .ini를 한 줄씩 읽어 `[구역]`과 `키 = 값`을 해석해 Scenario 구조체에 채운다. 설정 검사 후 지형 → 연료 → 경사 → 등산로 → 등산객 순서로 파일을 불러오며, 틀린 곳은 줄 번호와 함께 알려 준다. |
| `load_asc_grid` (map_io.c) | .asc 파일의 헤더(크기, 칸 크기)를 읽고, 그 크기만큼 메모리를 할당해 숫자를 하나씩 읽는다. 숫자가 아니거나 개수가 모자라면 몇 행 몇 열인지 알려 준다. |
| `compute_slope_aspect` (map_io.c) | 각 셀 주변 3×3 고도의 차이로 동쪽·남쪽 방향 기울기를 구해 경사(도)와 내리막 방향(방위각)을 계산한다. 경사는 3단계 확산 속도 계산에 쓰인다. |
| `grid_create` / `grid_free` (grid.c) | 행 포인터 배열을 먼저 할당하고 각 행을 할당해 `cells[y][x]`로 쓰는 2차원 동적 배열을 만든다. 해제는 그 반대 순서로 한다. |
| `load_trail_graph` (trail_io.c) | 파일을 세 번 읽어(개수 세기 → 노드 → 간선) 등산로 그래프를 만든다. 간선마다 지나는 셀을 Bresenham 직선으로 구하고 길이·오르막을 계산한 뒤, BFS로 고립된 노드가 없는지 검사한다. |

### 검증
- gcc `-std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow`: 경고 0개
- clang `-Weverything` (일부 스타일 경고 제외): 경고 0개
- valgrind: 정상 실행과 오류 시나리오 4개 모두 **메모리 누수 0**
- AddressSanitizer: 메모리 오류 0 (작업 중 Bresenham 구현의 배열 범위 초과 버그를 발견해 수정)
- **MSVC 빌드는 Windows PC에서 확인 필요**

### 명세서와 달라진 점
- `log.c`를 2단계에서 1단계로 당김 (오류 메시지 출력에 필요)
- 등산로 `EDGE` 줄의 경유점은 **중간 지점만** 적도록 함 (시작·끝 노드 좌표는 자동으로 붙음)
- C 줄 수가 1단계 예상(약 2,900줄)보다 많은 3,810줄. 입력 검사와 오류 메시지를 꼼꼼히 넣은 영향이며, 전체 C 분량은 목표보다 다소 많아질 수 있음.

## 2단계 — 확산 엔진 + 결과 파일 저장 (2026-11-20)

### 만든 것
- **`rng.c`**: 시드 고정 난수 xorshift32, 균등·정규(Box-Muller)·지수 분포
- **`weather.c`**: 기상 CSV 읽기(값 범위·시간 순서 검사), 선형 보간, 풍향 원형 보간, 고정 기상 모드, 몬테카를로용 기상 오차(`WeatherOffset`)
- **`fuel_moisture.c`**: 연료 모델 표 읽기와 검사, 지도의 연료 코드가 표에 모두 있는지 검사, Simard 평형 수분, 시간 지연, 남향 사면 보정, Rothermel 수분 감쇠
- **`spread_rate.c`**: `R = R0 × η_M × (1 + φw + φs)`, 각 요소를 `SpreadFactors`로 돌려줄 수 있음
- **`spread_sim.c`**: 누적 거리 셀룰러 오토마타, 화선/연소 목록 분리, 대각선 차단, 점화 트리(`parent_index`) 기록, 출력 간격 통계, 불이 꺼지면 조기 종료
- **`spotting.c`**: 바람·연료에 따른 비화 확률, 지수 분포 거리, 방향 오차, 착화 확률
- **`output_csv.c`**, **`output_json.c`**: 도착/전소 시각 격자, 시간순 이벤트, 통계 CSV, 직접 만든 JSON 작성기로 `summary.json`
- **`console_view.c`**: 화재 지도(`@` 연소 중, `x` 전소), 시간별 통계 표
- **`main.c`**: `--mode run`, `--map-every`, 결과 폴더 자동 생성, `run.log`
- **`util.c`**: 날짜 → 분 변환, 중간 폴더까지 만드는 `make_directories`, `time_is_set`
- **데이터**: `calm_fixed_weather.ini`(무풍 비교 실험), `tests/bad_weather.ini`
- **문서**: `docs/model.md` (수식, 단순화한 부분, 근거/가정 표시, 계산 예)

### 발표용 핵심 함수 (2단계)
| 함수 | 설명 |
|---|---|
| `compute_spread_rate` (spread_rate.c) | 한 셀에서 이웃 방향으로 불이 번지는 속도를 `기본 속도 × 수분 감쇠 × (1 + 바람 계수 + 경사 계수)`로 계산한다. 바람은 그 방향의 바람 성분, 경사는 두 셀의 고도 차이로 구한다. |
| `simulate_fire_step` (spread_sim.c) | 1분 동안 화선의 각 셀이 8방향으로 불을 밀어내고, 이웃까지 거리를 넘으면 점화를 예약한다. 비화를 처리하고, 예약된 셀에 한꺼번에 불을 붙인 뒤, 연소 시간이 끝난 셀을 전소로 바꾼다. |
| `run_fire_simulation` (spread_sim.c) | 매 분 기상 보간 → 연료 수분 갱신 → `simulate_fire_step`을 반복하고, 10분마다 통계를 기록한다. 불이 완전히 꺼지면 일찍 끝낸다. |
| `update_fuel_moisture` (fuel_moisture.c) | 기온·습도로 평형 수분을 구하고, 연료 수분이 그 값을 향해 1시간 지연으로 천천히 따라가게 한다. 남향 사면은 더 건조하게 보정한다. |
| `try_spotting` (spotting.c) | 연소 중인 셀마다 바람과 연료로 비화 확률을 계산한다. 비화가 생기면 바람 방향으로 난수 거리만큼 떨어진 셀에 불을 예약한다. |

### 검증
- gcc 엄격 옵션, clang `-Weverything`: 경고 0개 (실수 `==` 비교를 `time_is_set`으로 바꿈)
- 같은 시드로 두 번 실행 → CSV 4개 md5 동일 (재현성)
- valgrind: run 모드와 오류 시나리오 5개 모두 메모리 누수 0
- 실행 시간: 200×200, 360분 → 약 0.05초 (최적화 빌드)
- 결과 타당성: 서풍에서 동쪽으로 길쭉하게 번짐, 무풍에서는 오르막(북쪽 주봉) 방향으로 더 번짐
- **MSVC 빌드는 Windows PC에서 확인 필요**

### 명세서와 달라진 점
- `compute_spread_rate`, `simulate_fire_step`의 인자를 바꿈 (Scenario 전체를 받음, 화재 상태 `FireState` 추가)
- 화선/연소 목록 분리, 대각선 차단 규칙 추가 (`docs/model.md` 7장)

## 3단계 — Python GUI 기본 화면 + 결과 재생 애니메이션 (2026-11-20)

### 만든 것
- **`gui/main.py`**: 프로그램 시작점
- **`gui/theme.py`**: 다크 테마 스타일시트, 연료·불·노드·경보·로그 색상표
- **`services/app_config.py`**: 프로젝트·엔진·데이터·결과 폴더 경로, 엔진 실행 파일 위치
- **`services/engine_runner.py`**: `QThread` + `subprocess.Popen`으로 `wildfire.exe` 실행, stdout을 한 줄씩 `[태그]`·진행률로 해석해 시그널로 전달, Windows에서 콘솔 창 숨김, 중지 기능
- **`services/scenario_writer.py`**: 원본 .ini를 한 줄씩 복사하며 바꿀 값만 교체(주석 유지), 없는 키·구역 추가, 발화 지점 교체, 계절 프리셋 읽기
- **`services/result_loader.py`**: .asc, 등산로, 등산객, 격자 CSV, 통계 CSV, summary.json 읽기, 실행 전 미리보기, 시각별 피해 면적·연소 셀 계산
- **`services/map_render.py`**: 음영기복(Horn), 연료 색 합성, 시각 t의 불 레이어(막 붙은 불 노랑 → 오래 탄 불 빨강 → 전소 검정)
- **`views/map_view.py`**: PyQtGraph 지도, 레이어 6종 켜기/끄기, 등고선(100 m), 불 도착 등시선(60분), 노드 이름, 마우스 정보, 클릭으로 발화 지점 선택
- **`views/playback_bar.py`**: 재생/일시정지, 0.1분 단위 타임라인, 재생 속도 5단계, 실제 시각 표시
- **`views/scenario_panel.py`**: 시나리오·계절·발화 지점·기상(파일/직접 입력)·진행 시간·시드·비화 설정, 실행/중지
- **`views/log_console.py`**: 태그별 색 로그, 경고·오류 개수
- **`views/main_window.py`**: 상단 엔진 상태 표시줄, 왼쪽 설정 패널, 지도/로그 탭, 메뉴, 실행 → 결과 자동 재생 흐름
- **데이터**: `data/scenarios/season_presets.ini` (봄·여름·가을·겨울, 모두 [가정])

### 검증 (화면 없는 offscreen 모드에서 자동 테스트)
- 실행 버튼 → 시나리오 저장 → C 엔진 실행 → 결과 불러오기 → 재생까지 전체 흐름 확인
- 지도 클릭 → 발화 지점 변경, 계절 프리셋 → 기상 슬라이더 변경 확인
- 잘못된 시나리오 → 종료 코드 1, 상태 표시줄 빨간 메시지, 로그 탭 자동 이동 확인
- 화면 캡처로 레이아웃·색 확인 (체크박스 표시, 배경색 문제 수정)
- **Windows에서 실제 창으로 실행 확인 필요**

### 명세서와 달라진 점
- 대피·진화·통계·리포트 탭은 각 단계(4~6단계)에서 추가 (빈 탭을 미리 만들지 않음)
- 지도 그리기 계산을 `services/map_render.py`로 분리 (Qt 없이 numpy만으로 테스트 가능)

## 4단계 — 대피 경로 + 경보 (2026-11-20)

### 만든 것 (C)
- **`pqueue.c`**: 키 두 개(key1, key2)로 비교하는 이진 힙 우선순위 큐
- **`evac_route.c`**:
  - 위험 지도: 불이 지나간 셀에서 반경 안으로 도착 시각을 퍼뜨림
  - `find_safest_route`: 다익스트라 변형. 최소 안전 여유가 가장 큰 경로를 고르되 30분 이상이면 빠른 길 우선. `goto cleanup`으로 메모리를 한 곳에서 해제
  - 불이 오는 대피소는 목적지에서 제외
- **`hiker.c`**: Tobler 보행 속도, 셀 단위 이동 기록, 불에 막히면 고립, 시각별 위치 보간
- **`evac_alert.c`**:
  - 경보 단계 판정(정상/주의/대피준비/즉시대피/고립), 출발 시각 계산
  - 1분 간격 상태 기록, 위험 등산객 판정
  - 전체 실행 `run_evacuation`
- **`output_json.c`**: `evacuation.json` (설정, 요약, 팀별 경로·출발·도착·여유, 1분 간격 기록), `summary.json`에 결과 파일 목록(`ResultFlags`)
- **`console_view.c`**: 등산객 대피 안내 표
- **`main.c`**: `--mode evac`
- **설정**: `[evacuation]`에 `notify_delay_min`, `safe_margin_min`, `danger_radius_m` 추가
- **시나리오**: `spring_danger_valley.ini` (늦은 신고로 2팀이 고립되는 사례)

### 만든 것 (Python)
- **`views/evacuation_view.py`**:
  - 오른쪽 "대피 안내" 패널: 팀별 경보 배지, 상태, 남은 시간, 최소 여유, 목적지(재생 시각에 따라 갱신)
  - 상세 경로와 고립 원인 안내
- **`views/map_view.py`**:
  - 등산객(◆)이 경보 단계 색으로 경로를 따라 이동
  - 팀별 대피 경로(초록 = 안전, 빨강 = 위험), 선택한 팀 강조
  - 노드 이름 마우스 정보
- **`services/result_loader.py`**: `evacuation.json` 읽기, 시각별 위치·경보·상태 계산
- GUI 실행 모드를 `run` → `evac`으로 변경

### 발표용 핵심 함수 (4단계)
| 함수 | 설명 |
|---|---|
| `find_safest_route` (evac_route.c) | 등산로 그래프에서 노드마다 (경로 최소 안전 여유, 도착 시각)을 기록하며, 우선순위 큐로 여유가 큰 노드부터 확정하는 다익스트라 변형이다. 안전한 목적지 중 가장 좋은 기록을 가진 곳까지 경로를 거꾸로 따라가 만든다. |
| `build_danger_map` (evac_route.c) | 불이 지나간 셀마다 반경 안의 모든 셀에 "이 시각에 근처까지 불이 온다"를 기록한다. 경로 탐색과 경보 판정이 이 지도를 사용한다. |
| `assess_alert_level` (evac_alert.c) | 등산객의 현재 위치 주변 500 m 안에 불이 오기까지 남은 시간을 설정의 기준(120/60/30분)과 비교해 경보 단계를 정한다. 안전한 경로가 없으면 고립이다. |
| `build_hiker_track` (hiker.c) | 추천 경로의 셀을 하나씩 걸으며 Tobler 보행 속도로 시각을 계산한다. 다음 셀에 불이 먼저 와 있으면 그 자리에서 멈추고 고립으로 처리한다. |
| `pq_push` / `pq_pop` (pqueue.c) | 배열을 이진 트리처럼 사용하는 최소 힙이다. 넣을 때는 부모와 비교하며 위로, 꺼낼 때는 자식과 비교하며 아래로 옮겨 항상 맨 앞에 가장 좋은 원소가 오게 한다. |

### 검증
- gcc 엄격 옵션 / clang `-Weverything`: 경고 0개
- valgrind (`spring_dry_base`, `spring_danger_valley` evac 모드): 메모리 누수 0
- 확산 결과는 2단계와 같음 (CSV md5 동일)
- 결과 타당성:
  - 바람이 불어오는 쪽(서봉, 계곡대피소)의 팀은 대피가 필요 없다고 나온다.
  - 위험 사례에서 대피 준비 기준을 60분에서 120분으로 늘리면 고립 2팀이 0팀이 된다.
- GUI offscreen 테스트: 위험 시나리오 실행 → 대피 표·경로 강조·상세 안내 확인
- **MSVC 빌드, Windows 화면 확인 필요**

### 명세서와 달라진 점
- `find_safest_route`, `assess_alert_level`의 인자 변경 (위험 지도를 받음)
- 대피 결과를 별도 탭 대신 지도 옆 오른쪽 패널에 배치 (재생하면서 지도와 함께 보도록)
