/*
 * wf_types.h
 * 프로그램 전체에서 쓰는 구조체를 한 곳에 모아 정의한다.
 *
 * 큰 그림:
 *   Scenario (시나리오 하나 = 시뮬레이션 한 번에 필요한 모든 것)
 *     ├─ 설정값들 (SimSettings, AlertSettings, ...)
 *     ├─ Grid      : 지형·연료 격자 (Cell의 2차원 배열)
 *     ├─ FuelModel : 연료 종류별 파라미터 표
 *     ├─ WeatherSeries : 시각별 기상
 *     ├─ TrailGraph    : 등산로 그래프 (TrailNode, TrailEdge)
 *     └─ Hiker 배열    : 등산객
 *
 * 실수는 모두 double로 통일했다. (float를 섞으면 형 변환 경고가 많아진다.)
 */
#ifndef WF_TYPES_H
#define WF_TYPES_H

#include "wf_config.h"
#include "dynarray.h"

/* ================================================================
 * 1. 격자 (지형·연료·화재 상태)
 * ================================================================ */

/* 셀의 상태 */
typedef enum {
    CELL_UNBURNED = 0,   /* 정상: 아직 타지 않음 */
    CELL_BURNING,        /* 연소 중 */
    CELL_BURNED,         /* 전소: 다 타서 꺼짐 */
    CELL_FIREBREAK,      /* 방화선: 사람이 연료를 제거해 타지 않음 */
    CELL_WATER,          /* 물: 타지 않음 */
    CELL_ROCK            /* 바위·나지: 타지 않음 */
} CellState;

/* 격자 한 칸의 정보 */
typedef struct {
    double    elevation;      /* 고도 (m) */
    double    slope_deg;      /* 경사 (도, 0 = 평지) */
    double    aspect_deg;     /* 경사 방향: 내리막이 향하는 방위 (북=0, 시계방향), 평지면 -1 */
    int       fuel_code;      /* 연료 코드 (fuel_models.csv 와 연결) */
    double    fuel_moisture;  /* 연료 수분 (%) */
    CellState state;          /* 현재 상태 */
    double    arrival_time;   /* 불이 도착한 시각 (분), 아직이면 WF_NO_TIME */
    double    burnout_time;   /* 다 타서 꺼진 시각 (분), 아직이면 WF_NO_TIME */
    double    progress[8];    /* 이 셀에서 8방향 이웃으로 불이 나아간 거리 (m) */
    int       parent_index;   /* 이 셀에 불을 붙인 셀 번호 (y * width + x), 없으면 -1 */
    int       ignited_by_spot;/* 비화(날아온 불티)로 붙은 불이면 1 */
    double    wet_until;      /* 헬기 살수 효과가 끝나는 시각 (분), 효과 없으면 WF_NO_TIME */
} Cell;

/* 2차원 격자. cells[y][x] 로 접근한다. (y = 0 이 지도의 북쪽 끝) */
typedef struct {
    int     width;        /* 가로 칸 수 (x 방향, 서→동) */
    int     height;       /* 세로 칸 수 (y 방향, 북→남) */
    double  cell_size_m;  /* 한 칸의 실제 길이 (m) */
    double  xll;          /* 좌하단 x 좌표 (실제 지도와 연결할 때 사용) */
    double  yll;          /* 좌하단 y 좌표 */
    Cell  **cells;        /* 행 포인터 배열: cells[y]는 y번째 행(Cell 배열)을 가리킨다 */
} Grid;

/* ================================================================
 * 2. 연료와 기상
 * ================================================================ */

/* 연료 종류별 확산 계산 파라미터 (fuel_models.csv 한 줄) */
typedef struct {
    int    code;               /* 연료 코드 */
    char   name[32];           /* 이름 (예: "conifer") */
    int    burnable;           /* 탈 수 있으면 1 */
    double base_rate_m_min;    /* 평지·무풍·건조 기준 기본 확산 속도 (m/분) */
    double moisture_ext_pct;   /* 소화 수분: 이 수분 이상이면 번지지 않음 (%) */
    double burn_duration_min;  /* 한 칸이 타는 데 걸리는 시간 (분) */
    double wind_coef;          /* 바람 계수 kw */
    double wind_exp;           /* 바람 지수 bw */
    double slope_coef;         /* 경사 계수 ks */
    double spot_factor;        /* 비화 발생 가중치 (0이면 비화 없음) */
} FuelModel;

/* 한 시각의 기상 */
typedef struct {
    double time_min;       /* 시뮬레이션 시작 기준 경과 시간 (분) */
    double temp_c;         /* 기온 (°C) */
    double rh_pct;         /* 상대습도 (%) */
    double wind_speed_ms;  /* 풍속 (m/s) */
    double wind_dir_deg;   /* 풍향: 바람이 "불어오는" 방위 (기상 관례, 북=0) */
} WeatherRecord;

/* 시각별 기상 기록 목록 */
typedef struct {
    WeatherRecord *records;  /* 시간순 정렬된 기록 (동적 할당) */
    int            count;
} WeatherSeries;

/* 기상 입력 방식 */
typedef enum {
    WEATHER_FROM_FILE = 0,   /* 기상 CSV 파일 사용 */
    WEATHER_FIXED            /* 시나리오에 적힌 고정값 사용 */
} WeatherMode;

/* ================================================================
 * 3. 등산로 그래프
 * ================================================================ */

/* 등산로 노드 종류 */
typedef enum {
    NODE_JUNCTION = 0,  /* 갈림길 */
    NODE_SHELTER,       /* 대피소 (대피 목적지) */
    NODE_PARKING,       /* 주차장 (대피 목적지) */
    NODE_SUMMIT,        /* 정상 */
    NODE_POINT          /* 그 밖의 지점 (전망대 등) */
} NodeType;

/* 격자 좌표 한 점 */
typedef struct {
    int x;
    int y;
} GridPoint;

/* 등산로 노드 (교차점·대피소·주차장 등) */
typedef struct {
    int      id;              /* 파일에 적힌 번호 */
    NodeType type;            /* 종류 */
    int      x, y;            /* 격자 좌표 */
    char     name[WF_NAME_MAX];
    int      is_exit;         /* 대피 목적지(대피소·주차장)면 1 */
} TrailNode;

/* 등산로 간선 (두 노드를 잇는 길). 양방향으로 다닐 수 있다. */
typedef struct {
    int        from;        /* 시작 노드의 배열 인덱스 */
    int        to;          /* 끝 노드의 배열 인덱스 */
    double     length_m;    /* 실제 길이 (고도 차이 포함, m) */
    double     climb_m;     /* from → to 방향으로 걸을 때 오르막 합계 (m) */
    double     descent_m;   /* from → to 방향으로 걸을 때 내리막 합계 (m) */
    GridPoint *path;        /* 간선이 지나가는 셀 목록 (from 노드 → to 노드 순서, 동적 할당) */
    int        path_count;  /* path 원소 수 */
} TrailEdge;

/* 등산로 전체 그래프 */
typedef struct {
    TrailNode *nodes;       /* 노드 배열 (동적 할당) */
    int        node_count;
    TrailEdge *edges;       /* 간선 배열 (동적 할당) */
    int        edge_count;
    IntArray  *adjacent;    /* adjacent[i] = i번 노드에 연결된 간선 번호 목록 */
} TrailGraph;

/* ================================================================
 * 4. 등산객과 대피 경로
 * ================================================================ */

/* 경보 단계 (숫자가 클수록 위험) */
typedef enum {
    ALERT_NONE = 0,     /* 정상 */
    ALERT_CAUTION,      /* 주의 */
    ALERT_PREPARE,      /* 대피 준비 */
    ALERT_IMMEDIATE,    /* 즉시 대피 */
    ALERT_ISOLATED      /* 고립: 안전한 대피 경로 없음 (구조 요청) */
} AlertLevel;

/* 등산객 상태 */
typedef enum {
    HIKER_HIKING = 0,   /* 산행 중 */
    HIKER_EVACUATING,   /* 대피 중 */
    HIKER_SAFE,         /* 대피 완료 */
    HIKER_TRAPPED       /* 고립 */
} HikerStatus;

/* 대피 경로 */
typedef struct {
    int    *nodes;            /* 지나는 노드 인덱스 순서 (동적 할당) */
    int     node_count;
    int     exit_node;        /* 도착하는 대피소/주차장 인덱스 */
    double  travel_time_min;  /* 걸리는 시간 (분) */
    double  min_margin_min;   /* 경로 전체에서 가장 작은 안전 여유 (분) */
    int     found;            /* 경로를 찾았으면 1 */
} Route;

/* 등산객 (또는 함께 움직이는 일행) */
typedef struct {
    int         id;
    char        name[WF_NAME_MAX];
    int         start_node;       /* 시작 노드 인덱스 */
    double      speed_kmh;        /* 평지 보행 속도 (km/h) */
    int         group_size;       /* 인원 */
    double      depart_time_min;  /* 대피 출발 시각 (분) */
    double      pos_x, pos_y;     /* 현재 위치 (격자 좌표, 실수) */
    HikerStatus status;
    AlertLevel  alert;
    Route       route;
} Hiker;

/* ================================================================
 * 5. 설정 묶음
 * ================================================================ */

/* 날짜와 시각 */
typedef struct {
    int year, month, day;
    int hour, minute;
} DateTime;

/* 시뮬레이션 진행 설정 */
typedef struct {
    double       duration_min;         /* 전체 시뮬레이션 시간 (분) */
    double       time_step_min;        /* 한 단계 시간 (분) */
    double       output_interval_min;  /* 결과 저장 간격 (분) */
    unsigned int random_seed;          /* 난수 시드 (같으면 같은 결과) */
    int          spotting_enabled;     /* 비화 사용 여부 */
    double       spot_base_prob;       /* 비화 기본 확률 */
    double       spot_mean_dist_m;     /* 비화 평균 거리 (m) */
} SimSettings;

/* 경보 단계 기준 (화선 도착까지 남은 시간) */
typedef struct {
    double caution_min;     /* 이보다 적게 남으면 주의 */
    double prepare_min;     /* 이보다 적게 남으면 대피 준비 */
    double immediate_min;   /* 이보다 적게 남으면 즉시 대피 */
    double check_radius_m;  /* 등산객 주변 몇 m 안의 불을 볼지 */
} AlertSettings;

/* 진화 자원 설정 */
typedef struct {
    int    firebreak_cells;       /* 만들 방화선 칸 수 K */
    double firebreak_ready_min;   /* 방화선이 완성되는 시각 (분) */
    int    helicopters;           /* 헬기 대수 M */
    int    heli_radius_cells;     /* 한 번 살수할 때 반경 (칸) */
    double heli_interval_min;     /* 헬기 1회 왕복 시간 (분) */
    double heli_effect_min;       /* 살수 효과 지속 시간 (분) */
} SuppressionSettings;

/* 몬테카를로 반복 실험 설정 */
typedef struct {
    int    runs;              /* 반복 횟수 N */
    double wind_speed_sd;     /* 풍속 오차 표준편차 (m/s) */
    double wind_dir_sd_deg;   /* 풍향 오차 표준편차 (도) */
    double rh_sd;             /* 습도 오차 표준편차 (%) */
} MonteCarloSettings;

/* 연료 수분 설정 */
typedef struct {
    double initial_dead_moisture_pct;  /* 시작 시 죽은 연료 수분 (%) */
    double live_moisture_factor;       /* 계절에 따른 수분 배율 */
    double south_slope_drying_pct;     /* 남향 사면 수분 감소량 (%) */
    double timelag_min;                /* 연료 수분 반응 시간 τ (분) */
} MoistureSettings;

/* 발화 지점 */
typedef struct {
    int    x, y;       /* 격자 좌표 */
    double time_min;   /* 발화 시각 (분) */
} IgnitionPoint;

/* ================================================================
 * 6. 시나리오: 위의 모든 것을 묶은 구조체
 * ================================================================ */
typedef struct {
    /* --- 이름과 파일 경로 (경로는 모두 실제로 열 수 있게 정리된 경로) --- */
    char name[WF_NAME_MAX];
    char scenario_path[WF_PATH_MAX];    /* 시나리오 파일 자체 경로 */
    char base_dir[WF_PATH_MAX];         /* 시나리오 파일이 있는 폴더 */
    char elevation_file[WF_PATH_MAX];
    char fuel_file[WF_PATH_MAX];
    char fuel_model_file[WF_PATH_MAX];
    char trail_file[WF_PATH_MAX];       /* 비어 있으면 등산로 없음 */
    char hiker_file[WF_PATH_MAX];       /* 비어 있으면 등산객 없음 */
    char weather_file[WF_PATH_MAX];
    char output_dir[WF_PATH_MAX];

    /* --- 설정값 --- */
    DateTime            start_time;     /* 시뮬레이션 시작 날짜·시각 */
    SimSettings         sim;
    AlertSettings       alert;
    SuppressionSettings supp;
    MonteCarloSettings  mc;
    MoistureSettings    moisture;
    WeatherMode         weather_mode;
    WeatherRecord       fixed_weather;  /* weather_mode == WEATHER_FIXED 일 때 사용 */
    IgnitionPoint       ignitions[WF_MAX_IGNITIONS];
    int                 ignition_count;

    /* --- 파일에서 읽어 온 데이터 --- */
    Grid          grid;
    FuelModel     fuels[WF_MAX_FUELS];
    int           fuel_count;
    int           fuel_index[WF_MAX_FUELS]; /* fuel_index[연료코드] = fuels 배열 위치, 없으면 -1 */
    WeatherSeries weather;
    TrailGraph    trails;
    Hiker        *hikers;       /* 등산객 배열 (동적 할당) */
    int           hiker_count;
} Scenario;

/* ================================================================
 * 7. 시뮬레이션 결과
 * ================================================================ */

/* 출력 간격마다 기록하는 통계 한 줄 */
typedef struct {
    double time_min;               /* 시각 (분) */
    int    burning_cells;          /* 연소 중인 셀 수 */
    int    burned_cells;           /* 불이 지나간 셀 수 (연소 중 + 전소) */
    double burned_area_ha;         /* 피해 면적 (ha) */
    double max_spread_rate_m_min;  /* 이번 구간에서 가장 빠른 확산 속도 (m/분) */
    int    spot_fires;             /* 지금까지 비화로 생긴 불 수 */
    double dead_moisture_pct;      /* 죽은 연료 수분 (%) */
    WeatherRecord weather;         /* 이 시각의 기상 */
} StepStats;

/* 셀 상태가 바뀐 사건 하나 (애니메이션 재생용) */
typedef struct {
    double    time_min;
    int       x, y;
    CellState new_state;
} FireEvent;

/* 몬테카를로에서 기상에 더할 오차 (일반 실행에서는 모두 0) */
typedef struct {
    double wind_speed_ms;
    double wind_dir_deg;
    double rh_pct;
} WeatherOffset;

/* 시뮬레이션 실행 옵션 */
typedef struct {
    WeatherOffset offset;          /* 기상 오차 */
    int           record_events;   /* 1이면 FireEvent 기록 */
    int           quiet;           /* 1이면 진행 로그 생략 (반복 실험용) */
    double        map_every_min;   /* 0보다 크면 이 간격(분)마다 콘솔에 화재 지도 출력 */
} SimOptions;

/* 시뮬레이션 한 번의 결과 */
typedef struct {
    StepStats *steps;              /* 출력 간격별 통계 (동적 배열) */
    int        step_count;
    int        step_capacity;
    FireEvent *events;             /* 상태 변화 기록 (동적 배열) */
    int        event_count;
    int        event_capacity;
    int        burned_cells;       /* 최종 피해 셀 수 */
    double     final_area_ha;      /* 최종 피해 면적 (ha) */
    int        spot_fire_count;    /* 비화로 생긴 불 수 */
    double     max_spread_rate;    /* 전체에서 가장 빠른 확산 속도 (m/분) */
    double     end_time_min;       /* 시뮬레이션이 끝난 시각 */
    int        fire_out;           /* 시간 안에 불이 완전히 꺼졌으면 1 */
} SimResult;

#endif /* WF_TYPES_H */
