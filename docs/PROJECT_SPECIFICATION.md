# 프로젝트 명세서: 산불 확산 예측 및 등산객 대피 안내 시스템

> 상태: **v1.0 구현 완료 (2026-11-21, 7단계)** — 10장의 결정 사항은 모두 추천안으로 확정, Python 3.12, GitHub 사용.
> 이 문서의 1~9장은 개발 전에 세운 계획이다. **실제 구현과 달라진 점은 11장**에 모았다. (단계별 자세한 기록: `docs/CHANGELOG.md`)

---

## 0. 한눈에 보기

| 항목 | 내용 |
|---|---|
| 과목 / 팀 | C언어기초 팀 프로젝트, 1학년 2인 |
| 핵심 언어 | C11 (계산 엔진 `wildfire.exe`) |
| 보조 언어 | Python 3.12 (PySide6 + PyQtGraph GUI, 기상 API, 가상 지형 생성) |
| 빌드 환경 | Windows + Visual Studio 2022 MSVC, `/W4`에서 경고 0개 목표 |
| 목표 분량 | C 약 8,300줄 + Python 약 4,200줄 = **약 12,500줄** (파일별 예상은 9장) |
| 목적 | ① 산불 확산 예측 ② 등산객 대피 경로·경보 ③ 방화선·헬기 배치 최적화 ④ (보조) 몬테카를로 연소 확률 지도 |

### 블록 다이어그램

```
 ┌──────────────────────── Python GUI (PySide6 + PyQtGraph) ────────────────────────┐
 │  시나리오 설정 패널 ─▶ scenario_writer ─▶ data/scenarios/*.ini                      │
 │  기상 불러오기 버튼 ─▶ weather_api (기상청 API) ─▶ data/weather/*.csv               │
 │  실행 버튼 ─▶ engine_runner ─(subprocess)─▶ wildfire.exe <시나리오> --mode ...      │
 │                         ▲  stdout 한 줄씩 ([PROGRESS] / [INFO] / [ERROR] ...)        │
 │  상단 상태 표시줄 ◀──────┘                                                          │
 │  지도·재생·대피·진화·통계·리포트 화면 ◀─ result_loader ◀─ output/<실행이름>/*       │
 └───────────────────────────────────────────────────────────────────────────────────┘
 ┌──────────────────────────── C 계산 엔진 (wildfire.exe) ───────────────────────────┐
 │ [입력] scenario_io · map_io · trail_io                                             │
 │    ▼                                                                                │
 │ [기상·연료] weather(보간) → fuel_moisture(수분 계산)                                 │
 │    ▼                                                                                │
 │ [확산] spread_rate(속도 공식) → spread_sim(시간 단계 진행) + spotting(비화)          │
 │    ├──▶ [몬테카를로] montecarlo (N회 반복 → 연소 확률)                               │
 │    ├──▶ [대피] evac_route(안전 경로) · evac_alert(경보) · hiker(이동)                │
 │    └──▶ [진화] suppression(탐욕 배치) · suppression_eval(전후 비교)                  │
 │    ▼                                                                                │
 │ [출력] output_json · output_csv · log                                               │
 │ [공통] util · dynarray · pqueue · rng · grid                                        │
 └───────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. 전체 폴더 구조와 파일 역할

```
wildfire_project/
├── c_core/
│   ├── include/
│   │   ├── wf_config.h        # 상수(최대 크기, 파일 경로 길이 등)와 열거형
│   │   ├── wf_types.h         # 모든 구조체 정의 (Cell, Grid, FuelModel, Weather, Trail..., Scenario)
│   │   ├── util.h             # 문자열·수학·메모리 도우미
│   │   ├── dynarray.h         # 동적 배열 (IntArray, DoubleArray)
│   │   ├── pqueue.h           # 우선순위 큐 (최소 힙)
│   │   ├── rng.h              # 시드 고정 난수
│   │   ├── grid.h             # 2차원 격자 할당/해제/이웃 접근
│   │   ├── scenario_io.h
│   │   ├── map_io.h
│   │   ├── trail_io.h
│   │   ├── console_view.h
│   │   ├── weather.h
│   │   ├── fuel_moisture.h
│   │   ├── spread_rate.h
│   │   ├── spread_sim.h
│   │   ├── spotting.h
│   │   ├── montecarlo.h
│   │   ├── evac_route.h
│   │   ├── evac_alert.h
│   │   ├── hiker.h
│   │   ├── suppression.h
│   │   ├── suppression_eval.h
│   │   ├── output_json.h
│   │   ├── output_csv.h
│   │   └── log.h
│   ├── src/                   # 위 헤더와 같은 이름의 .c 파일 + main.c (역할은 아래 표)
│   └── build.bat              # Developer Command Prompt에서 cl로 빌드
├── gui/
│   ├── main.py                # 프로그램 시작점
│   ├── theme.py               # 다크 테마 스타일시트, 색상표(연료·불·경보 단계)
│   ├── requirements.txt       # PySide6, pyqtgraph, numpy, requests
│   ├── views/
│   │   ├── main_window.py     # 탭 구성, 상단 엔진 상태 표시줄, 메뉴
│   │   ├── map_view.py        # 메인 지도 (음영기복+연료+불+등산로+등산객+경로 레이어)
│   │   ├── playback_bar.py    # Play/Pause, 타임라인 슬라이더, 재생 속도
│   │   ├── scenario_panel.py  # 발화 지점 클릭, 계절 프리셋, 바람·습도 슬라이더, 기상 불러오기
│   │   ├── evacuation_view.py # 등산객 목록, 경보 배지, 추천 경로, 남은 안전 시간
│   │   ├── suppression_view.py# 배치 전/후 지도 나란히 + 비교 표
│   │   ├── stats_view.py      # 시간별 피해 면적·확산 속도 그래프, 연소 확률 지도
│   │   ├── report_view.py     # 요약 보기 + HTML/PNG 저장 버튼
│   │   └── log_console.py     # C 엔진 stdout 전체 로그 창
│   └── services/
│       ├── app_config.py      # 경로, API 키 파일(config/api_keys.ini) 읽기
│       ├── engine_runner.py   # wildfire.exe 실행 (QThread + subprocess.Popen), stdout 줄 단위 전달
│       ├── result_loader.py   # output/ 폴더의 CSV/JSON → numpy 배열·파이썬 객체
│       ├── scenario_writer.py # GUI 설정값 → .ini 시나리오 파일
│       ├── weather_api.py     # 기상청 단기예보 API 호출, 위경도→격자(nx,ny) 변환, CSV 저장
│       ├── terrain_generator.py # 가상 산(능선·계곡) + 연료 구역 생성 → .asc 파일
│       ├── trail_generator.py # 가상 등산로 그래프 + 등산객 파일 생성
│       └── report_builder.py  # 리포트 HTML 문서 조립
├── config/
│   └── api_keys.example.ini   # 키 입력 양식 (실제 api_keys.ini는 .gitignore)
├── data/
│   ├── maps/                  # virtual_mountain_elev.asc, virtual_mountain_fuel.asc
│   ├── trails/                # virtual_trails.txt, virtual_hikers.txt
│   ├── weather/               # sample_spring_dry.csv 등 (인터넷 없을 때용)
│   └── scenarios/             # *.ini 시나리오, fuel_models.csv, season_presets.ini
├── output/                    # C가 저장하는 결과 (실행 이름별 하위 폴더)
├── docs/
│   ├── PROJECT_SPECIFICATION.md   # (이 문서)
│   ├── model.md               # 확산·수분·대피·진화 모델 수식, 단순화, 근거/가정 표시, 참고문헌
│   ├── CHANGELOG.md           # 단계별 작업 기록
│   ├── LINE_COUNT.md          # 언어별·파일별 줄 수
│   ├── presentation_notes.md  # (마지막 단계) 발표 준비 자료
│   └── prompts/               # 프롬프트 기록 (00_project_instructions.md 등)
├── tools/
│   └── count_lines.py         # LINE_COUNT.md 자동 생성 (빈 줄·주석 줄 따로 집계)
├── .gitignore
└── README.md                  # 설치·빌드(build.bat / VS 빈 프로젝트)·실행 방법
```

### 1-1. C 소스 파일 역할 (`c_core/src/`)

| 모듈 | 파일 | 역할 |
|---|---|---|
| 시작점 | `main.c` | 명령줄 인자 해석, 모드(`printmap`/`run`/`mc`/`evac`/`optimize`/`all`)별 흐름 실행, 전체 해제 |
| 공통 유틸 | `util.c` | 문자열 trim/분리, 안전한 숫자 변환, 경로 합치기, 각도 계산, `wf_malloc`(실패 시 메시지) |
| | `dynarray.c` | 늘어나는 정수/실수 배열 (`push`, `get`, `free`) |
| | `pqueue.c` | 최소 힙 우선순위 큐 (다익스트라용) |
| | `rng.c` | 시드 고정 난수 (xorshift32 직접 구현), 균등/정규/지수 분포 |
| | `grid.c` | `Cell **` 2차원 격자 할당·해제, 8방향 이웃 표, 범위 검사, 화재 상태 초기화 |
| 입력 | `scenario_io.c` | `.ini` 시나리오 읽기, 값 범위 검사, 친절한 오류 메시지(파일명:줄번호) |
| | `map_io.c` | ESRI ASCII Grid(`.asc`) 고도·연료 격자 읽기, 크기 일치 검사, 경사·경사방향 계산 |
| | `trail_io.c` | 등산로 노드·간선·등산객 파일 읽기, 간선 경유 셀 계산(Bresenham 직선) |
| | `console_view.c` | 콘솔에 지도를 문자로 출력 (1단계 확인용, 디버그용) |
| 기상·연료 | `weather.c` | 기상 CSV 읽기, 시각별 선형 보간(풍향은 원형 보간), 고정 기상 모드 |
| | `fuel_moisture.c` | 연료 모델 표(`fuel_models.csv`) 읽기, 평형수분(EMC) 계산, 시간 지연 반영, 사면 방향 보정 |
| 확산 | `spread_rate.c` | **`compute_spread_rate`**: 연료·수분·바람·경사로 특정 방향 확산 속도 계산 |
| | `spread_sim.c` | 점화, **`simulate_fire_step`**(1단계 진행), `run_fire_simulation`(전체 반복), 통계 수집 |
| | `spotting.c` | 비화(불티가 날아가 새 불 생성) 확률·거리 계산 |
| 몬테카를로 | `montecarlo.c` | 시드·기상 오차를 바꿔 N회 반복, 셀별 연소 확률·도달시각 분위수·평균 피해 면적 |
| 대피 | `evac_route.c` | **`find_safest_route`**: 불 도착 시각을 고려한 안전 여유 최대 경로 탐색 |
| | `evac_alert.c` | 등산객 위치별 경보 단계 판정, 경보 시각표 생성 |
| | `hiker.c` | 등산객을 경로 따라 시간별로 이동, 대피 완료/고립 판정, Tobler 보행 속도 |
| 진화 | `suppression.c` | **`optimize_firebreak`**(방화선 K칸), `plan_helicopter_drops`(헬기 M대) 탐욕 배치 |
| | `suppression_eval.c` | 배치 전/후 시뮬레이션 실행, 피해 면적·위험 등산객 수·등산로 소실 길이 비교 |
| 출력 | `output_json.c` | 직접 만든 작은 JSON 작성기(들여쓰기, 문자열 이스케이프), 요약·대피·진화 결과 저장 |
| | `output_csv.c` | 격자 CSV(도달 시각, 연소 확률), 화재 이벤트 CSV, 시간별 통계 CSV |
| | `log.c` | 표준출력 진행 로그 (`[PROGRESS] 35 ...` 형식), 로그 파일 동시 기록 |

---

## 2. C ↔ Python 연결 규칙

### 2-1. 실행 명령

```
wildfire.exe <시나리오.ini> [--mode printmap|run|mc|evac|optimize|all] [--out <폴더>] [--seed <정수>]
```

- `--mode` 기본값은 `run`. `all`은 run → evac → optimize → mc 순서로 모두 실행.
- 종료 코드: `0` 성공, `1` 입력 오류(파일 없음·형식 오류), `2` 메모리 부족, `3` 기타.

### 2-2. 표준출력 형식 (Python이 한 줄씩 읽음)

```
[INFO] 시나리오 '봄철_건조_기본' 읽기 완료 (격자 200x200, 셀 30m)
[PROGRESS] 35 확산 시뮬레이션 126/360분
[WARN] 기상 데이터가 300분까지만 있어 이후는 마지막 값 사용
[ERROR] data/maps/a.asc 12번째 줄: 숫자가 아닌 값 'abc'
[RESULT] output/봄철_건조_기본/summary.json
[DONE] 3.2초
```

- 앞의 태그는 ASCII 고정 → Python은 태그만 보고 분기. `[PROGRESS]` 다음 숫자는 0~100 진행률.
- **한글 깨짐 대책**: C 소스는 UTF-8로 저장하고 MSVC `/utf-8` 옵션으로 빌드, `main`에서 `SetConsoleOutputCP(CP_UTF8)` 호출(Windows 기본 라이브러리), Python은 `encoding="utf-8"`로 읽음.
- 출력마다 `fflush(stdout)` → GUI에 실시간 표시.

---

## 3. 구조체 정의 (`wf_types.h` 초안)

> 실수는 모두 `double`로 통일합니다. (`float`를 섞으면 MSVC `/W4`에서 형 변환 경고가 많이 나고, 1학년이 설명하기에도 단순함.)

```c
/* ===== 셀 상태 ===== */
typedef enum {
    CELL_UNBURNED = 0,   /* 정상: 아직 타지 않음 */
    CELL_BURNING,        /* 연소 중 */
    CELL_BURNED,         /* 전소 */
    CELL_FIREBREAK,      /* 방화선 (타지 않음) */
    CELL_WATER,          /* 물 (타지 않음) */
    CELL_ROCK            /* 바위·나지 (타지 않음) */
} CellState;

/* ===== 격자 한 칸 ===== */
typedef struct {
    double elevation;        /* 고도 (m) */
    double slope_deg;        /* 경사 (도) */
    double aspect_deg;       /* 경사 방향: 내리막이 향하는 방위 (북=0, 시계방향) */
    int    fuel_code;        /* 연료 코드 (FuelModel 표와 연결) */
    double fuel_moisture;    /* 연료 수분 (%) */
    CellState state;         /* 현재 상태 */
    double arrival_time;     /* 불이 도착한 시각 (분), 아직이면 -1 */
    double burnout_time;     /* 다 타서 꺼진 시각 (분), 아직이면 -1 */
    double progress[8];      /* 이 셀에서 8방향 이웃으로 불이 나아간 거리 (m) */
    int    parent_index;     /* 이 셀에 불을 붙인 셀 번호 (y*width+x), 없으면 -1 */
    int    ignited_by_spot;  /* 비화로 붙은 불이면 1 */
    double wet_until;        /* 헬기 살수 효과가 끝나는 시각 (분) */
} Cell;

/* ===== 2차원 격자 ===== */
typedef struct {
    int    width, height;    /* 가로·세로 칸 수 */
    double cell_size_m;      /* 한 칸의 실제 길이 (m) */
    double xll, yll;         /* 좌하단 실제 좌표 (실제 지도와 연결할 때 사용) */
    Cell **cells;            /* cells[y][x] 형태로 접근 */
} Grid;

/* ===== 연료 모델 (연료 종류별 파라미터) ===== */
typedef struct {
    int    code;              /* 연료 코드 */
    char   name[32];          /* 이름 (예: "침엽수") */
    int    burnable;          /* 탈 수 있으면 1 */
    double base_rate_m_min;   /* 평지·무풍·건조 기준 기본 확산 속도 (m/분) */
    double moisture_ext_pct;  /* 소화 수분: 이 수분 이상이면 불이 번지지 않음 (%) */
    double burn_duration_min; /* 한 칸이 타는 시간 (분) */
    double wind_coef;         /* 바람 계수 kw */
    double wind_exp;          /* 바람 지수 bw */
    double slope_coef;        /* 경사 계수 ks */
    double spot_factor;       /* 비화 발생 가중치 (0이면 비화 없음) */
} FuelModel;

/* ===== 기상 ===== */
typedef struct {
    double time_min;        /* 시뮬레이션 시작 기준 경과 분 */
    double temp_c;          /* 기온 (°C) */
    double rh_pct;          /* 상대습도 (%) */
    double wind_speed_ms;   /* 풍속 (m/s) */
    double wind_dir_deg;    /* 풍향: 바람이 불어오는 방위 (기상 관례, 북=0) */
} WeatherRecord;

typedef struct {
    WeatherRecord *records;  /* 시간순 정렬된 기록 (동적 할당) */
    int count;
} WeatherSeries;

/* ===== 등산로 그래프 ===== */
typedef enum { NODE_JUNCTION, NODE_SHELTER, NODE_PARKING, NODE_SUMMIT, NODE_POINT } NodeType;

typedef struct { int x, y; } GridPoint;

typedef struct {
    int      id;
    NodeType type;
    int      x, y;           /* 격자 좌표 */
    char     name[48];
    int      is_exit;        /* 대피 목적지(대피소·주차장)면 1 */
} TrailNode;

typedef struct {
    int        from, to;     /* 노드 배열 인덱스 */
    double     length_m;     /* 길이 */
    double     climb_m;      /* from→to 방향 오르막 합계 */
    double     descent_m;    /* from→to 방향 내리막 합계 */
    GridPoint *path;         /* 간선이 지나가는 셀 목록 (동적 할당) */
    int        path_count;
} TrailEdge;

typedef struct {
    TrailNode *nodes;   int node_count;
    TrailEdge *edges;   int edge_count;
    IntArray  *adjacent; /* adjacent[노드] = 연결된 간선 번호 목록 */
} TrailGraph;

/* ===== 대피 경로와 등산객 ===== */
typedef enum { ALERT_NONE, ALERT_CAUTION, ALERT_PREPARE, ALERT_IMMEDIATE, ALERT_ISOLATED } AlertLevel;
typedef enum { HIKER_HIKING, HIKER_EVACUATING, HIKER_SAFE, HIKER_TRAPPED } HikerStatus;

typedef struct {
    int   *nodes;            /* 지나는 노드 순서 (동적 할당) */
    int    node_count;
    int    exit_node;        /* 도착 대피소/주차장 */
    double travel_time_min;  /* 걸리는 시간 */
    double min_margin_min;   /* 경로 전체에서 가장 작은 안전 여유 (분) */
    int    found;            /* 경로를 찾았으면 1 */
} Route;

typedef struct {
    int         id;
    char        name[32];
    int         start_node;       /* 시작 노드 */
    double      speed_kmh;        /* 평지 보행 속도 */
    int         group_size;       /* 인원 */
    double      depart_time_min;  /* 대피 출발 시각 */
    double      pos_x, pos_y;     /* 현재 위치 (격자 좌표, 실수) */
    HikerStatus status;
    AlertLevel  alert;
    Route       route;
} Hiker;

/* ===== 설정 묶음 ===== */
typedef struct {
    double duration_min, time_step_min, output_interval_min;
    unsigned int random_seed;
    int    spotting_enabled;
    double spot_base_prob, spot_mean_dist_m;
} SimSettings;

typedef struct { double caution_min, prepare_min, immediate_min, check_radius_m; } AlertSettings;
typedef struct { int firebreak_cells; double firebreak_ready_min;
                 int helicopters; int heli_radius_cells; double heli_interval_min, heli_effect_min; } SuppressionSettings;
typedef struct { int runs; double wind_speed_sd, wind_dir_sd_deg, rh_sd; } MonteCarloSettings;
typedef struct { double initial_dead_moisture_pct, live_moisture_factor,
                        south_slope_drying_pct, timelag_min; } MoistureSettings;

typedef struct { int x, y; double time_min; } IgnitionPoint;

/* ===== 시나리오 (모든 것을 묶은 구조체) ===== */
typedef struct {
    char name[64];
    char base_dir[WF_PATH_MAX];                  /* 시나리오 파일이 있는 폴더 */
    char elevation_file[WF_PATH_MAX], fuel_file[WF_PATH_MAX], fuel_model_file[WF_PATH_MAX];
    char trail_file[WF_PATH_MAX], hiker_file[WF_PATH_MAX], weather_file[WF_PATH_MAX];
    char output_dir[WF_PATH_MAX];

    SimSettings sim;  AlertSettings alert;  SuppressionSettings supp;
    MonteCarloSettings mc;  MoistureSettings moisture;
    IgnitionPoint ignitions[WF_MAX_IGNITIONS];  int ignition_count;

    /* 파일에서 읽어 온 데이터 */
    Grid          grid;
    FuelModel     fuels[WF_MAX_FUELS];  int fuel_count;
    WeatherSeries weather;
    TrailGraph    trails;
    Hiker        *hikers;  int hiker_count;
} Scenario;

/* ===== 시뮬레이션 결과 통계 ===== */
typedef struct {
    double time_min;
    int    burning_cells, burned_cells;
    double burned_area_ha;
    double max_spread_rate_m_min;
} StepStats;

typedef struct {
    StepStats *steps;  int step_count, step_capacity;
    double final_area_ha;
    int    spot_fire_count;
} SimResult;
```

**2차원 배열 설명용 포인트**: `Grid.cells`는 "행 포인터 배열 + 각 행 배열" 방식으로 `malloc`합니다. `grid->cells[y][x]`로 직관적으로 접근하고, 해제는 `free(행)`을 반복한 뒤 `free(행 포인터 배열)`.

---

## 4. 주요 함수 목록

### 4-1. 발표용 핵심 함수 (8개)

| 함수 | 파일 | 하는 일 (2~3줄) |
|---|---|---|
| `int load_scenario(const char *path, Scenario *sc)` | scenario_io.c | `.ini`를 한 줄씩 읽어 `[구역]`과 `키 = 값`을 해석해 구조체에 채운다. 이어서 지도·연료·기상·등산로 파일을 차례로 불러오고, 범위를 벗어난 값이 있으면 줄 번호와 함께 오류를 알린다. |
| `void compute_slope_aspect(Grid *g)` | map_io.c | 각 셀의 주변 고도 차이로 경사(도)와 경사 방향을 계산한다 (Horn 방법). |
| `void update_fuel_moisture(Scenario *sc, double t, double dt)` | fuel_moisture.c | 현재 기온·습도로 평형수분을 구하고, 연료 수분이 그 값을 향해 천천히 따라가게 한다. 남향 사면은 더 건조하게 보정한다. |
| `double compute_spread_rate(const Scenario*, int x, int y, int dir, const WeatherRecord*, SpreadFactors*)` | spread_rate.c | 한 셀에서 이웃 방향으로 불이 번지는 속도(m/분)를 `기본 속도 × 수분 감쇠 × (1 + 바람 계수 + 경사 계수)`로 계산한다. |
| `int simulate_fire_step(Scenario*, FireState*, double t, double dt, const WeatherRecord*, Rng*, SimResult*, const SimOptions*)` | spread_sim.c | 연소 중인 모든 셀이 8방향으로 `속도×dt`만큼 불을 밀어내고, 누적 거리가 이웃까지의 거리를 넘으면 그 이웃에 불을 붙이며 도착 시각을 기록한다. 다 탄 셀은 전소로 바꾸고, 비화를 확률적으로 처리한다. |
| `int run_monte_carlo(Scenario *sc, MonteCarloResult *mc)` | montecarlo.c | 시드와 기상 오차를 바꿔 같은 시나리오를 N번 반복하고, 셀별로 "탄 횟수 / N"을 연소 확률로 저장한다. |
| `int find_safest_route(const Scenario*, const DangerMap*, int start, double start_time, double speed_kmh, Route*)` | evac_route.c | 등산로 그래프에서 대피소·주차장까지 경로를 찾는다. 각 지점에서 "불 도착 시각 − 내가 지나는 시각"(안전 여유)을 계산해, 여유의 최솟값이 가장 큰 경로를 고른다(같으면 빠른 경로). |
| `AlertLevel assess_alert_level(const Scenario*, const Hiker*, const DangerMap*, double now, double *remaining)` | evac_alert.c | 등산객 주변에 불이 도착하기까지 남은 시간을 설정값과 비교해 주의/대피 준비/즉시 대피/고립 단계를 판정한다. |
| `int optimize_firebreak(Scenario *sc, const double *weights, unsigned int seed, FirebreakPlan *plan)` | suppression.c | 기준 시뮬레이션에서 "이 셀을 막으면 뒤따라 타는 셀 수"(점화 트리의 하위 셀 수)가 큰 칸부터 방화선을 고른다. 몇 칸 고를 때마다 다시 시뮬레이션해 점수를 갱신한다. |
| `int compare_strategies(Scenario *sc, unsigned int seed, SuppressionReport *report)` | suppression_eval.c | 아무것도 안 했을 때 / 방화선 / 헬기 / 둘 다 배치했을 때를 각각 시뮬레이션해 피해 면적과 위험 등산객 수를 표로 만든다. |

### 4-2. 그 외 함수 (모듈별)

- **util**: `str_trim`, `str_split`, `parse_int_strict`, `parse_double_strict`, `join_path`, `deg_to_rad`, `angle_diff_deg`, `clamp_double`, `wf_malloc`, `wf_calloc`
- **dynarray**: `intarray_init/push/free`, `doublearray_init/push/free`
- **pqueue**: `pq_create`, `pq_push`, `pq_pop_min`, `pq_is_empty`, `pq_free`
- **rng**: `rng_seed`, `rng_next_u32`, `rng_uniform`, `rng_normal`(Box–Muller), `rng_exponential`
- **grid**: `grid_create`, `grid_free`, `grid_in_bounds`, `grid_neighbor_dx/dy`, `grid_neighbor_distance`, `grid_reset_fire_state`, `grid_copy_fire_state`
- **map_io**: `load_asc_grid`, `load_terrain`, `load_fuel_map`, `validate_maps`
- **trail_io**: `load_trail_graph`, `load_hikers`, `trace_edge_cells`(Bresenham), `find_nearest_node`, `free_trail_graph`
- **console_view**: `print_map_fuel`, `print_map_elevation`, `print_map_fire`, `print_scenario_summary`
- **weather**: `load_weather_csv`, `parse_datetime_minutes`, `get_weather_at`(보간), `interpolate_angle_deg`
- **fuel_moisture**: `load_fuel_models`, `find_fuel_model`, `equilibrium_moisture`, `moisture_damping`, `init_fuel_moisture`
- **spread_rate**: `wind_factor`, `slope_factor`, `direction_angle_deg`
- **spread_sim**: `ignite_cell`, `ignite_scenario_points`, `run_fire_simulation`, `collect_step_stats`, `burnout_cells`
- **spotting**: `try_spotting`, `sample_spot_distance`
- **montecarlo**: `perturb_weather`, `accumulate_burn_counts`, `compute_arrival_percentile`
- **evac_route**: `edge_travel_time`(Tobler), `edge_min_margin`, `fire_arrival_at_cell`, `route_free`
- **evac_alert**: `time_to_fire_near`, `build_alert_timeline`
- **hiker**: `hiker_init_all`, `hiker_move_step`, `hiker_position_on_route`, `count_hikers_at_risk`
- **suppression**: `compute_subtree_sizes`, `select_firebreak_cells`, `apply_firebreak`, `plan_helicopter_drops`, `apply_water_drop`
- **output_json**: `json_begin_object`, `json_key_string/number/int`, `json_end_object`, `write_summary_json`, `write_evacuation_json`, `write_suppression_json`
- **output_csv**: `write_grid_csv`, `write_fire_events_csv`, `write_stats_csv`, `write_burn_probability_csv`
- **log**: `log_info`, `log_warn`, `log_error`, `log_progress`, `log_open_file`, `log_close`

### 4-3. `main` 함수 흐름 (순서도 개요)

```
시작
 → 콘솔 UTF-8 설정, 명령줄 인자 해석 (실패 시 사용법 출력 후 종료)
 → load_scenario()  ── 실패 → 오류 출력 → free_scenario() → 종료(1)
 → mode == printmap ? → 콘솔 지도 출력
 → mode에 run 포함 ? → run_fire_simulation() → 결과 저장
 → mode에 evac 포함 ? → 모든 등산객 find_safest_route() + 경보 판정 + 이동 시뮬 → 저장
 → mode에 optimize 포함 ? → optimize_firebreak() + plan_helicopter_drops() + compare_strategies() → 저장
 → mode에 mc 포함 ? → run_monte_carlo() → 확률 지도 저장
 → free_scenario() (모든 동적 메모리 해제)
 → [DONE] 출력, 종료(0)
```

---

## 5. 데이터 파일 형식

모든 입력 파일은 **UTF-8 텍스트**, `#`으로 시작하는 줄은 주석입니다. 상대 경로는 "시나리오 파일이 있는 폴더" 기준.

### 5-1. 시나리오 파일 (`data/scenarios/spring_dry_base.ini`)

```ini
# 봄철 건조 기본 시나리오
# 표시: [근거] = 문헌·통계 근거 있음, [가정] = 팀이 정한 값

[general]
name = 봄철_건조_기본
output_dir = ../../output/spring_dry_base

[map]
elevation_file = ../maps/virtual_mountain_elev.asc
fuel_file      = ../maps/virtual_mountain_fuel.asc
fuel_models    = fuel_models.csv

[trails]
trail_file = ../trails/virtual_trails.txt
hiker_file = ../trails/virtual_hikers.txt

[time]
start_datetime      = 2026-04-05 13:00
duration_min        = 360      # [가정]
time_step_min       = 1        # [가정] 1분 단위
output_interval_min = 10

[ignition]
point1 = 120, 80, 0     # x, y, 발화 시각(분)

[weather]
mode = file             # file 또는 fixed
file = ../weather/sample_spring_dry.csv
fixed_temp_c = 18
fixed_rh_pct = 25
fixed_wind_speed_ms = 6
fixed_wind_dir_deg  = 270

[moisture]
initial_dead_moisture_pct = 8     # [가정]
live_moisture_factor      = 1.0   # 계절 프리셋에서 덮어씀 [가정]
south_slope_drying_pct    = 2     # [가정] 남향 사면 수분 감소량
timelag_min               = 60    # [근거] 1시간 지연 연료 정의

[spread]
random_seed       = 42
spotting_enabled  = 1
spot_base_prob    = 0.002   # [가정]
spot_mean_dist_m  = 150     # [가정]

[evacuation]
caution_min    = 120   # [가정] 화선 도착 2시간 전 → 주의
prepare_min    = 60    # [가정]
immediate_min  = 30    # [가정]
check_radius_m = 500   # [가정]

[suppression]
firebreak_cells     = 40
firebreak_ready_min = 60     # 방화선 완성 시각 [가정]
helicopters         = 2
heli_radius_cells   = 2
heli_interval_min   = 30     # [가정] 1회 왕복 시간
heli_effect_min     = 45     # [가정] 살수 효과 지속

[montecarlo]
runs            = 100
wind_speed_sd   = 1.0   # m/s [가정]
wind_dir_sd_deg = 15    # [가정]
rh_sd           = 5     # % [가정]
```

계절 프리셋(`season_presets.ini`)은 `[spring] live_moisture_factor=..., default_rh=...` 같은 구역을 두고 GUI가 선택값을 시나리오에 써 넣습니다.

### 5-2. 지형·연료 격자: ESRI ASCII Grid (`.asc`)

GIS 표준 텍스트 형식이라 **QGIS에서 실제 DEM·임상도를 "다른 이름으로 저장 → .asc"만 하면 그대로 사용 가능**합니다.

```
ncols        200
nrows        200
xllcorner    0.0
yllcorner    0.0
cellsize     30.0
NODATA_value -9999
512.3 515.0 518.2 ...   ← 맨 윗줄 = 북쪽 끝 행
...
```

연료 격자는 같은 형식에 정수 코드를 넣습니다. 두 파일의 `ncols/nrows/cellsize`가 다르면 오류.

### 5-3. 연료 모델 표 (`data/scenarios/fuel_models.csv`)

```
# code,name,burnable,base_rate_m_min,moisture_ext_pct,burn_duration_min,wind_coef,wind_exp,slope_coef,spot_factor,source
0,none,0,0,0,0,0,0,0,0,-
1,grass,1,4.0,15,3,0.45,1.3,5.0,0.2,가정
2,shrub,1,2.0,25,10,0.40,1.3,5.0,0.5,가정
3,conifer,1,1.2,25,30,0.35,1.3,5.0,1.0,가정
4,broadleaf,1,0.6,30,25,0.30,1.3,5.0,0.3,가정
5,mixed,1,0.9,28,28,0.33,1.3,5.0,0.6,가정
7,road,0,0,0,0,0,0,0,0,-
8,water,0,0,0,0,0,0,0,0,-
9,rock,0,0,0,0,0,0,0,0,-
```

> 숫자는 초안이며 "침엽수(소나무림)가 활엽수보다 잘 번지고 비화가 많다"는 정성적 사실에 맞춘 **가정값**입니다. `docs/model.md`에 근거/가정을 표로 정리합니다.

### 5-4. 기상 파일 (`data/weather/*.csv`)

```
# datetime,temp_c,rh_pct,wind_speed_ms,wind_dir_deg
# source=sample (또는 source=KMA_VilageFcst nx=61 ny=125)
2026-04-05 12:00,17.0,30,4.5,270
2026-04-05 13:00,18.5,25,6.2,280
```

C는 시나리오 `start_datetime` 기준 경과 분으로 바꾸고 사이 시각은 선형 보간합니다(풍향은 359°→1° 같은 경계를 고려한 원형 보간).

### 5-5. 등산로 그래프 (`data/trails/virtual_trails.txt`)

```
# NODE id type x y name
NODE 1 PARKING  15 185 북문주차장
NODE 2 JUNCTION 40 150 삼거리A
NODE 3 SHELTER  90 100 중턱대피소
NODE 4 SUMMIT  110  60 정상
# EDGE from to 경유점개수 x1 y1 x2 y2 ...
#   경유점 = 길이 꺾이는 "중간" 지점만 적는다. 시작·끝 노드 좌표는 엔진이 자동으로 앞뒤에 붙인다.
#   점과 점 사이는 Bresenham 직선 알고리즘으로 셀을 채운다.
EDGE 1 2 1  28 170
EDGE 2 3 0
EDGE 3 4 0
```

`type`: `JUNCTION`, `SHELTER`, `PARKING`, `SUMMIT`, `POINT`. `SHELTER`/`PARKING`은 자동으로 대피 목적지. 간선 길이·오르막·내리막은 C가 경유 셀의 고도로 계산합니다.

### 5-6. 등산객 파일 (`data/trails/virtual_hikers.txt`)

```
# HIKER id name node_id speed_kmh group_size
HIKER 1 김씨일행 4 3.5 3
HIKER 2 단체산악회 2 3.0 12
```

### 5-7. 출력 파일 (`output/<실행이름>/`)

| 파일 | 형식 | 내용 |
|---|---|---|
| `summary.json` | JSON | 시나리오 이름, 격자 정보, 최종 피해 면적, 비화 횟수, 실행 시간, 생성된 파일 목록 |
| `arrival_time.csv` | 격자 CSV | 셀별 불 도착 시각(분), 미도착 `-1` |
| `burnout_time.csv` | 격자 CSV | 셀별 전소 시각 |
| `fire_events.csv` | CSV | `time_min,x,y,new_state` — 상태가 바뀐 셀만 시간순 기록 (애니메이션 재생용) |
| `stats.csv` | CSV | `time_min,burning,burned,area_ha,max_rate` |
| `evacuation.json` | JSON | 등산객별 경로(노드·셀 좌표), 출발/도착 시각, 최소 안전 여유, 경보 단계 시간표, 이동 위치 |
| `suppression.json` | JSON | 방화선 셀 목록, 헬기 투하 시각·위치, 전략별 비교 표 |
| `suppression_<전략>_arrival.csv` | 격자 CSV | 전략별 도착 시각 격자 (비교 화면용) |
| `burn_probability.csv` | 격자 CSV | 몬테카를로 셀별 연소 확률 (0~1) |
| `mc_summary.json` | JSON | 반복 횟수, 피해 면적 평균·표준편차·최소·최대, 회차별 면적 |
| `run.log` | 텍스트 | stdout과 같은 로그 |

GUI는 어느 시각 t의 격자를 `도착시각 ≤ t < 전소시각 → 연소 중`, `전소시각 ≤ t → 전소`로 바로 복원할 수 있어서, 슬라이더를 자유롭게 움직여도 빠릅니다.

---

## 6. 계산 모델 요약 (자세한 내용은 `docs/model.md`)

### 6-1. 연료 수분
- **평형수분(EMC)**: Simard(1968) 식 — 기온(°F)·상대습도로 구간별 1차/2차식. [근거]
- **시간 지연**: `M ← M + (EMC − M) × (1 − e^(−dt/τ))`, τ = 60분 (1시간 지연 연료). [근거: 연료 시간 지연 개념]
- **사면 보정**: 남향(경사 방향 135°~225°) 셀은 수분을 `south_slope_drying_pct`만큼 낮춤. [가정]

### 6-2. 확산 속도 (Rothermel 단순화)
```
R(방향) = R0(연료) × η_M × (1 + φ_w + φ_s)
```
- `R0`: 연료별 기본 속도 (fuel_models.csv). [가정]
- `η_M = 1 − 2.59r + 5.11r² − 3.52r³`, `r = 수분 / 소화수분` (0~1로 제한) — Rothermel(1972)의 수분 감쇠 계수. [근거]
- `φ_w`: 이 방향으로의 바람 성분 `U·cosθ`가 양수면 `kw × (U·cosθ)^bw`, 음수(맞바람)면 감소시키되 `1+φ_w+φ_s ≥ 0.05`로 제한. [형태 근거 / 계수 가정]
- `φ_s`: 오르막이면 `ks × tan²(경사각)` (Rothermel의 경사 항 형태), 내리막이면 절반 감소. [형태 근거 / 계수 가정]

### 6-3. 격자 확산 (시간 단계 방식)

> 2단계 구현 시 추가: 화선(front)과 연소(burning) 목록을 분리, 대각선 차단 규칙 — 자세한 내용은 `docs/model.md` 7장
- 매 단계(`dt` = 1분) 연소 중인 셀이 8방향으로 `R × dt`씩 `progress[dir]`를 늘림.
- `progress ≥ 이웃까지 거리`(직선 30m, 대각선 42.4m)가 되면 이웃 점화, 넘친 거리만큼 시각을 보정해 `arrival_time` 기록.
- 점화 후 `burn_duration_min`이 지나면 전소. 방화선·물·바위·살수 중인 셀은 점화 안 됨.
- **비화**: 연소 중 셀마다 `p = spot_base_prob × spot_factor × (U/10)²` 확률로 불티 발생, 거리는 지수분포(평균 ∝ 풍속), 방향은 풍하 방향 ± 정규분포 오차. 시드 고정 난수로 재현 가능. [가정]

### 6-4. 대피 경로

> 4단계 구현 시 추가: 위험 지도 2종(경보 500 m / 경로 60 m), 충분한 여유(30분) 상한, 불이 오는 대피소는 목적지에서 제외, 출발 시점에 여유 < 0 이면 고립 — 자세한 내용은 `docs/model.md` 10장
- 보행 속도: **Tobler 보행 함수** `v = 6·e^(−3.5·|기울기+0.05|)` km/h를 등산객 평지 속도에 비례 조정. [근거: Tobler 1993]
- 안전 여유(지점) = 그 셀의 불 도착 시각 − 등산객 통과 시각. 경로 여유 = 경로 위 최솟값.
- 알고리즘: 직접 만든 우선순위 큐로 **다익스트라 변형**. 라벨 = (경로 최소 여유, 도착 시각), 여유가 큰 것 우선·같으면 빠른 것 우선. 여유가 음수인 간선은 통과 불가.
- 한계(문서화): 도착 시각이 경로에 따라 달라지므로 엄밀한 최적은 아님 → 예제로 검증.

### 6-5. 진화 전략

> 5단계 구현 시 변경: 셀 단위가 아니라 5칸 방화선 조각 단위로 배치, 상위 3개 후보는 실제 시뮬레이션으로 비교, 비화를 사건별 난수(공통 난수)로 변경 — 자세한 내용은 `docs/model.md` 9·11장
- **방화선**: 기준 시뮬레이션에서 각 셀의 `parent_index`로 "점화 트리"를 만들고, 하위 셀 수(= 막으면 막을 수 있는 셀 수의 추정)가 큰 칸 중 `도착 시각 ≥ 방화선 완성 시각`인 칸을 골라 한 번에 5칸씩 추가 → 재시뮬레이션 → 반복(K칸까지). 등산로 셀은 가중치를 높게. [탐욕법]
- **헬기**: `heli_interval_min`마다 헬기 M대가 각각 현재 화선 중 점수가 가장 높은 지점에 반경 r칸 살수(`wet_until` 갱신). [탐욕법]
- 비교 지표: 최종 피해 면적(ha), 위험 등산객 수(경로 여유 < 0 또는 고립), 소실된 등산로 길이(km).

### 참고 문헌 (주석·문서에 출처 표기)
- Rothermel, R.C. (1972). *A mathematical model for predicting fire spread in wildland fuels.* USDA Forest Service INT-115.
- Simard, A.J. (1968). *The moisture content of forest fuels.* Canadian Dept. of Forestry.
- Tobler, W. (1993). *Three presentations on geographical analysis and modeling.* (Hiking function)
- Horn, B.K.P. (1981). *Hill shading and the reflectance map.* (경사 계산)
- 기상청 단기예보 조회서비스 활용가이드 (위경도 ↔ 격자 nx,ny 변환식, 공공데이터포털)

---

## 7. Python GUI 설계

- **라이브러리**: PySide6, pyqtgraph, numpy, requests (모두 `pip install` 가능)
- **화면 배치** (`QMainWindow`)
  - 상단: 엔진 상태 표시줄 (현재 단계 텍스트 + 진행 막대, `[ERROR]`는 빨간색)
  - 왼쪽 도킹: 시나리오 설정 패널
  - 가운데 탭: ① 지도 ② 대피 ③ 진화 전략 ④ 통계 ⑤ 리포트 ⑥ 로그
  - 지도 탭 하단: 재생 컨트롤
- **지도 레이어** (pyqtgraph `ImageItem` 여러 겹): 음영기복(numpy로 계산) → 연료색(반투명) → 불(연소 중 주황·빨강 / 전소 검회색) → 방화선 → 등산로(`PlotDataItem` 선) → 등산객(`ScatterPlotItem`, 경보 색) → 대피 경로(굵은 선). 레이어별 체크박스.
- **실행 중 GUI가 멈추지 않게**: `engine_runner`가 `QThread` 안에서 `subprocess.Popen`을 실행하고 줄마다 Qt Signal로 전달.

---

## 8. 개발 단계 계획

| 단계 | 내용 | 완료 확인 방법 (여러분이 직접 실행) |
|---|---|---|
| 0 | 명세서 작성 (현재) | 이 문서 검토·승인 |
| 1 | 헤더·구조체, 유틸, `dynarray`, `log`, `grid`, `scenario_io`, `map_io`, `trail_io`, `console_view`, `main(printmap)`, `build.bat`, 샘플 지도·등산로 1세트 (가상 지형·등산로 생성기 Python 스크립트 포함), 오류 확인용 테스트 시나리오 | `build.bat` → `wildfire.exe ..\data\scenarios\spring_dry_base.ini --mode printmap`으로 콘솔에 지도·요약 출력, 일부러 틀린 파일로 오류 메시지 확인 |
| 2 | `weather`, `fuel_moisture`, `spread_rate`, `spread_sim`, `spotting`, `output_csv/json`, `log` | `--mode run` → `output/`에 CSV/JSON 생성, 콘솔에 시간별 지도 출력, 같은 시드 = 같은 결과 확인 |
| 3 | GUI 기본: 메인 창, 테마, 지도 레이어, 재생 컨트롤, 엔진 실행·상태 표시, 시나리오 패널 기본 | `python gui/main.py` → 실행 버튼 → 애니메이션 재생 |
| 4 | `evac_route`, `evac_alert`, `hiker` + 대피 화면 | 등산객별 경보 배지·경로·남은 시간 표시, 경로가 불을 피하는지 확인 |
| 5 | `suppression`, `suppression_eval` + 진화 비교 화면 | 전/후 지도 나란히, 피해 면적 감소 확인 |
| 6 | 기상 API, `montecarlo`, 통계 그래프, 리포트 | API 키 넣고 실제 예보로 실행 / 키 없이 샘플로 실행, 확률 지도·리포트 저장 |
| 7 | 오류 처리 보강, 메모리 누수 점검, 문서(model.md, README, presentation_notes.md) | 잘못된 입력 모음으로 테스트, 최종 줄 수 확인 |

**검증 방식 안내**: 저는 클라우드 리눅스 환경에서 작업하므로 MSVC를 직접 돌릴 수 없습니다. 대신 매 단계 `gcc`/`clang`의 엄격 옵션(`-std=c11 -Wall -Wextra -Wpedantic -Wconversion`)으로 경고 0개 확인 + AddressSanitizer/메모리 검사로 누수 확인을 하고, MSVC 전용 차이(예: `M_PI` 미정의, VLA 미지원)는 코드에서 피합니다. **MSVC 최종 확인은 여러분 PC에서** 해 주시고 경고가 나오면 알려주세요.

각 단계 끝에 `docs/CHANGELOG.md`, `docs/LINE_COUNT.md` 갱신, 새 핵심 함수 2~3줄 설명을 드립니다.

### build.bat 초안

```bat
@echo off
rem Developer Command Prompt for VS 2022에서 실행
cd /d %~dp0
if not exist bin mkdir bin
cl /nologo /std:c11 /W4 /utf-8 /O2 /D_CRT_SECURE_NO_WARNINGS ^
   /I include src\*.c /Fo:bin\ /Fe:bin\wildfire.exe
```

Visual Studio 빈 프로젝트 방법(README에 그림 순서로 정리): 빈 프로젝트 생성 → `include`/`src` 파일 추가 → 속성에서 C 언어 표준 `/std:c11`, 추가 포함 디렉터리 `include`, 전처리기 `_CRT_SECURE_NO_WARNINGS`, 추가 옵션 `/utf-8`, 경고 수준 `/W4` → 디버깅 명령 인수에 시나리오 경로.

---

## 9. 파일별 예상 줄 수

> 주석·빈 줄 포함. 실제 구현하면서 ±15% 변동 가능하며, 줄 수를 맞추려고 의미 없는 코드는 넣지 않습니다.

### C (약 8,300줄)

| 모듈 | 파일 | 예상 줄 수 | 모듈 합계 (지시서 목표) |
|---|---|---:|---|
| 헤더 | `include/*.h` (25개) | 600 | 600 |
| 시작점 | `main.c` | 280 | 280 |
| 설정·지도 입출력 | `scenario_io.c` 500, `map_io.c` 400, `trail_io.c` 300, `console_view.c` 180 | 1,380 | 1,380 (~1,200) |
| 기상·연료 수분 | `weather.c` 350, `fuel_moisture.c` 350 | 700 | 700 (~800) |
| 확산 엔진 | `grid.c` 180, `spread_rate.c` 450, `spread_sim.c` 600, `spotting.c` 250 | 1,480 | 1,480 (~1,600) |
| 몬테카를로 | `montecarlo.c` | 450 | 450 (~600) |
| 대피 경로 | `evac_route.c` 700, `evac_alert.c` 300, `hiker.c` 300 | 1,300 | 1,300 (~1,500) |
| 진화 전략 | `suppression.c` 550, `suppression_eval.c` 350 | 900 | 900 (~1,000) |
| 결과 출력·로그 | `output_json.c` 400, `output_csv.c` 250, `log.c` 120 | 770 | 770 (~800) |
| 공통 유틸 | `util.c` 220, `dynarray.c` 110, `pqueue.c` 140, `rng.c` 90 | 560 | 560 (~500) |
| **합계** | | | **약 8,420** |

### Python (약 4,200줄)

| 구분 | 파일 | 예상 줄 수 |
|---|---|---:|
| 시작·테마 | `main.py` 60, `theme.py` 110 | 170 |
| 화면 | `main_window.py` 300, `map_view.py` 420, `playback_bar.py` 180, `scenario_panel.py` 350, `evacuation_view.py` 300, `suppression_view.py` 300, `stats_view.py` 300, `report_view.py` 220, `log_console.py` 100 | 2,470 |
| 서비스 | `app_config.py` 70, `engine_runner.py` 220, `result_loader.py` 250, `scenario_writer.py` 160, `weather_api.py` 300, `terrain_generator.py` 280, `trail_generator.py` 180, `report_builder.py` 160 | 1,620 |
| 도구 | `tools/count_lines.py` | 60 |
| **합계** | | **약 4,320** |

**전체 약 12,700줄** (목표 12,000줄 대비 +6%, 구현하며 조정)

---

## 10. 결정이 필요한 사항 (답변 부탁드립니다)

각 항목에서 **(추천)** 표시를 기본안으로 명세서를 썼습니다. 다르게 하고 싶은 것만 알려주셔도 됩니다.

### D1. 시나리오 설정 파일 형식
| 선택지 | 장점 | 단점 |
|---|---|---|
| **A. INI (`키 = 값`)** (추천) | C로 읽기 쉬움(`fgets`+`sscanf`), 발표에서 설명 쉬움, 사람이 직접 고치기 쉬움 | 중첩 구조 표현 불가 (필요 없음) |
| B. JSON | Python과 주고받기 편함 | C에 JSON 파서를 직접 만들어야 함(+500줄, 1학년이 설명하기 어려움) |

### D2. 확산 계산 방식
| 선택지 | 장점 | 단점 |
|---|---|---|
| **A. 시간 단계 방식 (1분마다 전체 갱신)** (추천) | `simulate_fire_step`으로 설명이 직관적, 기상 변화·비화·헬기 처리 쉬움 | 계산량 더 많음 (200×200, 6시간이면 1초 내외라 문제 없음) |
| B. 이벤트 방식 (최소 도달시간 다익스트라) | 빠르고 정밀 | 시간에 따라 바뀌는 바람·비화 처리 복잡, 설명 어려움 |

### D3. 지도 크기·해상도
| 선택지 | 장점 | 단점 |
|---|---|---|
| A. 100×100, 50m (5km) | 가장 빠름 | 등산로가 거칠게 보임 |
| **B. 200×200, 30m (6km)** (추천) | 실제 DEM(30m)과 해상도 같음, 몬테카를로 100회도 수십 초 | — |
| C. 400×400, 15m | 그림이 정교 | 몬테카를로 느림 (수 분) |

(C 코드는 크기를 파일에서 읽으므로 나중에 바꿀 수 있습니다. 기본 샘플을 무엇으로 만들지의 문제입니다.)

### D4. 실제 기상 데이터 출처
| 선택지 | 장점 | 단점 |
|---|---|---|
| **A. 기상청 단기예보 API (공공데이터포털)** (추천) | 전국 어디나 3일치 시간별 기온·습도·풍속·풍향 예보, 문서 풍부 → "앞으로" 예측 가능 | 5km 격자라 산 정상 기상과 차이 있음 |
| B. 국립산림과학원 산악기상관측 API | 산에 설치된 관측소라 실제 산악 기상 | 관측값(과거·현재)이라 예측용으로는 한계, 관측소 위치 제한 |
| C. 둘 다 | 가장 풍부 | 작업량 증가 (+150줄 정도) |

API 키 발급은 여러분이 공공데이터포털에서 직접 하셔야 합니다(무료, 승인에 시간이 걸릴 수 있음).

### D5. 결과 저장 방식 (애니메이션용)
| 선택지 | 장점 | 단점 |
|---|---|---|
| **A. 도착/전소 시각 격자 + 변화 이벤트 CSV + JSON 요약** (추천) | 파일이 작고, 아무 시각으로나 즉시 이동 가능 | "프레임 파일" 개념보다 설명이 한 단계 더 필요 |
| B. 출력 간격마다 전체 격자 프레임 파일 저장 (`frame_0010.csv` ...) | 이해하기 가장 쉬움 | 파일 수십 개·수십 MB, 슬라이더 이동 시 로딩 |

### D6. 대피 판단에 쓸 "불 도착 시각"
| 선택지 | 장점 | 단점 |
|---|---|---|
| A. 단일 시뮬레이션 결과만 사용 | 단순 | 예측이 빗나가면 위험 |
| **B. 기본은 단일, 6단계에서 "몬테카를로 보수 모드"(N회 중 가장 이른 10% 도착 시각) 옵션 추가** (추천) | 불확실성까지 고려한 안전한 안내 → 차별점 | 대피 모듈이 몬테카를로 결과에 의존(옵션) |

### D7. 진화 전략 탐색 방식
| 선택지 | 장점 | 단점 |
|---|---|---|
| **A. 점화 트리 점수 + 5칸마다 재시뮬레이션 (탐욕)** (추천) | 빠름(수 초), 설명 가능("이 칸을 막으면 뒤에 탈 셀이 몇 개인가") | 최적해 보장 없음 |
| B. 후보 칸마다 실제 재시뮬레이션해 가장 좋은 칸 선택 | 결과가 더 정확 | 후보 수 × K번 시뮬레이션 → 수 분~수십 분 |

### D8. 리포트 저장 형식
| 선택지 | 장점 | 단점 |
|---|---|---|
| **A. HTML + PNG 이미지** (추천) | 추가 라이브러리 없음, 브라우저로 열고 인쇄→PDF 가능 | — |
| B. PDF 직접 생성 | 바로 제출 가능 | `reportlab` 등 추가 의존성 |
| C. 텍스트(.txt) + PNG | 가장 단순 | 보기 덜 좋음 |

### 확정 결과 (2026-11-20)
- D1~D8: 모두 **(추천)** 안으로 확정
- Python 버전: 3.12
- 발표 분담: 아직 정하지 않음 (나중에 결정)
- GitHub 사용: 단계마다 커밋

---

## 11. 최종 구현 요약 — 계획과 달라진 점

### 11-1. 분량
| 언어 | 계획 | 실제 |
|---|---:|---:|
| C | 약 8,400줄 | 약 9,000줄 |
| Python | 약 4,300줄 | 약 4,400줄 (자동 테스트 포함) |

- 입력 검사와 오류 메시지, 대피·진화 계산의 세부 단계가 계획보다 길어졌다.
- 줄 수를 맞추려고 넣은 코드는 없다. 최신 값은 `docs/LINE_COUNT.md` 참고.

### 11-2. 구조·함수
| 계획 | 실제 | 이유 |
|---|---|---|
| `log.c`는 2단계 | 1단계로 당김 | 오류 메시지 출력에 필요 |
| 등산로 `EDGE` 줄에 모든 꼭짓점 | 중간 경유점만 (노드 좌표는 자동) | 파일 작성이 쉬움 |
| `compute_spread_rate(Grid*, ..., FuelModel*, ...)` | `compute_spread_rate(const Scenario*, x, y, dir, weather, SpreadFactors*)` | 연료·수분을 이웃 셀에서 찾기 위해 시나리오 전체가 필요. 계산 요소를 돌려줘 설명에 활용 |
| `simulate_fire_step(sc, t, dt, rng, res)` | 화재 상태 `FireState`(화선·연소 목록)와 실행 옵션 추가 | 화선과 연소를 분리 (풀밭 불이 꺼지는 문제 해결) |
| 셀 단위 방화선 | 불 진행 방향에 수직인 5칸 조각, 상위 3개 후보는 실제 시뮬레이션으로 비교 | 셀 하나만 막으면 불이 옆으로 돌아감 |
| `find_safest_route`가 Route 반환 | 위험 지도를 받고 결과를 인자로 돌려줌, 내부를 `relax_neighbors`·`pick_best_exit`로 나눔 | 메모리 부족을 알리기 위해, 발표 설명을 위해 |
| 대피·진화·통계를 각각 탭으로 | 대피 안내는 지도 옆 오른쪽 패널 | 재생하면서 지도와 함께 보기 위해 |
| (계획에 없음) | 대각선 차단 규칙, 공통 난수(사건별 난수), 보수적 대피(몬테카를로), 자동 테스트 `tools/run_tests.py` | 구현 중 발견한 문제 해결과 검증을 위해 |

### 11-3. 데이터·결과
- **비화 난수 변경 (5단계)**: 사건별 난수로 바꾸면서 2~4단계에서 적었던 결과 수치가 바뀌었다.
  - 기본 시나리오 피해: 233.6 → 277.6 ha
- **위험 시나리오 다시 정함 (5단계)**: `spring_danger_valley.ini`를 신고 지연 100분 조건으로 다시 정하고, 결론을 "조기 발견이 핵심"으로 바로잡았다.
- **기상청 API**: 개발 환경에서는 접속이 막혀 응답 형식·격자 변환·오류 처리만 시험했다. 실제 호출은 API 키가 있는 PC에서 확인해야 한다.

### 11-4. 검증 방법
- 매 단계 gcc(`-Wall -Wextra -Wpedantic -Wconversion -Wshadow`)와 clang(`-Weverything`)으로 경고 0개를 확인했다.
- valgrind와 AddressSanitizer로 메모리 누수·오류가 없음을 확인했다(모든 모드와 오류 경로).
- MSVC 빌드는 1단계에서 팀이 확인했다. 이후 단계는 팀 PC에서 다시 확인해야 한다.
- 자동 테스트 23개(`python tools/run_tests.py`)

