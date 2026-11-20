/*
 * main.c
 * 산불 확산 예측 및 등산객 대피 안내 시스템 — C 계산 엔진의 시작점
 *
 * 사용법:
 *   wildfire.exe <시나리오.ini> [--mode 모드] [--out 결과폴더] [--seed 난수시드]
 *                [--step 지도출력간격] [--map-every 분]
 *
 * 모드:
 *   printmap : 시나리오를 읽고 지도·요약을 콘솔에 출력 (1단계)
 *   run      : 산불 확산 시뮬레이션 → output 폴더에 CSV/JSON 저장 (2단계)
 *   evac     : 확산 시뮬레이션 + 등산객 대피 경로·경보 → evacuation.json (4단계)
 *   optimize : 확산 + 대피 + 방화선·헬기 배치 최적화와 전략 비교 → suppression.json (5단계)
 *   mc       : 몬테카를로 반복 실험 (6단계 예정)
 *   all      : run → evac → optimize (6단계에서 mc 추가)
 *
 * main 함수의 흐름:
 *   1) 로그 준비 → 2) 명령줄 인자 해석 → 3) 시나리오 읽기
 *   → 4) 모드별 작업 → 5) 메모리 해제 → 6) 종료 코드 반환
 */
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "wf_config.h"
#include "wf_types.h"
#include "scenario_io.h"
#include "console_view.h"
#include "spread_sim.h"
#include "output_csv.h"
#include "output_json.h"
#include "evac_alert.h"
#include "suppression_eval.h"
#include "util.h"
#include "log.h"

/* 실행 모드 */
typedef enum {
    MODE_PRINTMAP = 0,
    MODE_RUN,
    MODE_EVAC,
    MODE_OPTIMIZE,
    MODE_MC,
    MODE_ALL
} RunMode;

/* 명령줄 인자를 해석한 결과 */
typedef struct {
    const char  *scenario_path;  /* 시나리오 파일 경로 */
    RunMode      mode;           /* 실행 모드 */
    const char  *out_dir;        /* --out 으로 지정한 결과 폴더 (없으면 NULL) */
    int          has_seed;       /* --seed 를 지정했으면 1 */
    unsigned int seed;
    int          map_step;       /* --step 으로 지정한 지도 출력 간격 (0이면 자동) */
    double       map_every_min;  /* --map-every: 시뮬레이션 중 몇 분마다 콘솔 화재 지도를 찍을지 (0이면 안 찍음) */
} CommandLine;

/* 사용법을 출력한다. */
static void print_usage(void)
{
    printf("사용법: wildfire.exe <시나리오.ini> [옵션]\n");
    printf("옵션:\n");
    printf("  --mode <모드>   printmap | run | evac | optimize | mc | all  (기본: run)\n");
    printf("  --out <폴더>    결과를 저장할 폴더 (시나리오의 output_dir 대신 사용)\n");
    printf("  --seed <정수>   난수 시드 (시나리오의 random_seed 대신 사용)\n");
    printf("  --step <정수>   콘솔 지도에서 몇 칸마다 한 글자를 찍을지 (기본: 자동)\n");
    printf("  --map-every <분> run 모드에서 이 간격마다 콘솔에 화재 지도 출력 (기본: 마지막에만)\n");
    printf("예: wildfire.exe ..\\data\\scenarios\\spring_dry_base.ini --mode printmap\n");
    fflush(stdout);
}

/* 모드 이름 문자열을 RunMode로 바꾼다. 성공 1, 실패 0 */
static int parse_mode(const char *text, RunMode *mode)
{
    static const char *names[] = { "printmap", "run", "evac", "optimize", "mc", "all" };
    int i;

    for (i = 0; i < (int)(sizeof(names) / sizeof(names[0])); i++) {
        if (str_equals_ignore_case(text, names[i])) {
            *mode = (RunMode)i;
            return 1;
        }
    }
    return 0;
}

/*
 * 명령줄 인자(argc, argv)를 해석한다.
 * argv[0]은 프로그램 이름, argv[1]부터가 사용자가 입력한 값이다.
 * 성공 1, 실패 0
 */
static int parse_command_line(int argc, char *argv[], CommandLine *cmd)
{
    int i;

    cmd->scenario_path = NULL;
    cmd->mode = MODE_RUN;
    cmd->out_dir = NULL;
    cmd->has_seed = 0;
    cmd->seed = 0;
    cmd->map_step = 0;
    cmd->map_every_min = 0.0;

    for (i = 1; i < argc; i++) {
        const char *arg = argv[i];
        int         has_value = (i + 1 < argc);

        if (strcmp(arg, "--help") == 0 || strcmp(arg, "-h") == 0) {
            return 0;
        } else if (strcmp(arg, "--mode") == 0 && has_value) {
            i++;
            if (!parse_mode(argv[i], &cmd->mode)) {
                log_error("알 수 없는 모드 '%s'", argv[i]);
                return 0;
            }
        } else if (strcmp(arg, "--out") == 0 && has_value) {
            i++;
            cmd->out_dir = argv[i];
        } else if (strcmp(arg, "--seed") == 0 && has_value) {
            int seed;
            i++;
            if (!parse_int_strict(argv[i], &seed) || seed < 0) {
                log_error("--seed 값 '%s'는 0 이상의 정수여야 함", argv[i]);
                return 0;
            }
            cmd->has_seed = 1;
            cmd->seed = (unsigned int)seed;
        } else if (strcmp(arg, "--step") == 0 && has_value) {
            i++;
            if (!parse_int_strict(argv[i], &cmd->map_step) || cmd->map_step < 1 || cmd->map_step > 100) {
                log_error("--step 값 '%s'는 1 ~ 100 정수여야 함", argv[i]);
                return 0;
            }
        } else if (strcmp(arg, "--map-every") == 0 && has_value) {
            i++;
            if (!parse_double_strict(argv[i], &cmd->map_every_min) || cmd->map_every_min < 1.0) {
                log_error("--map-every 값 '%s'는 1 이상의 숫자(분)여야 함", argv[i]);
                return 0;
            }
        } else if (arg[0] == '-') {
            log_error("알 수 없는 옵션이거나 값이 빠짐: '%s'", arg);
            return 0;
        } else if (cmd->scenario_path == NULL) {
            cmd->scenario_path = arg;
        } else {
            log_error("시나리오 파일은 하나만 지정할 수 있음 ('%s')", arg);
            return 0;
        }
    }

    if (cmd->scenario_path == NULL) {
        log_error("시나리오 파일 경로가 필요함");
        return 0;
    }
    return 1;
}

/* printmap 모드: 시나리오 요약, 지형 통계, 고도 지도, 연료 지도를 출력한다. */
static int run_print_map(const Scenario *sc, int map_step)
{
    int step = (map_step > 0) ? map_step : choose_map_step(&sc->grid, 100);

    print_scenario_summary(sc);
    print_terrain_statistics(sc);
    print_map_elevation(sc, step);
    print_map_fuel(sc, step);
    return WF_OK;
}

/* 결과 폴더 안의 파일 경로를 만든다. 예: output/spring + arrival_time.csv */
static void output_path(const Scenario *sc, const char *file_name, char *out, size_t out_size)
{
    int length = snprintf(out, out_size, "%s/%s", sc->output_dir, file_name);
    if (length < 0 || (size_t)length >= out_size) {
        log_warn("결과 파일 경로가 너무 길어 잘림: %s/%s", sc->output_dir, file_name);
    }
}

/*
 * 확산 결과 파일 4개(도착·전소 시각 격자, 이벤트, 통계)를 저장한다.
 * 진화 전략 비교가 격자를 다시 계산하기 전에, 기준 시뮬레이션 직후 바로 저장해야 한다.
 */
static int save_fire_files(const Scenario *sc, const SimResult *res)
{
    char path[WF_PATH_MAX];
    int  ok = 1;

    output_path(sc, "arrival_time.csv", path, sizeof(path));
    ok = ok && write_grid_csv(path, &sc->grid, GRID_VALUE_ARRIVAL);
    output_path(sc, "burnout_time.csv", path, sizeof(path));
    ok = ok && write_grid_csv(path, &sc->grid, GRID_VALUE_BURNOUT);
    output_path(sc, "fire_events.csv", path, sizeof(path));
    ok = ok && write_fire_events_csv(path, res);
    output_path(sc, "stats.csv", path, sizeof(path));
    ok = ok && write_stats_csv(path, res);
    return ok;
}

/* summary.json 을 저장하고 GUI에 경로를 알린다. (마지막에 저장: 어떤 결과 파일이 있는지 적어야 하므로) */
static int save_summary(const Scenario *sc, const SimResult *res, const ResultFlags *flags, double elapsed_sec)
{
    char path[WF_PATH_MAX];

    output_path(sc, "summary.json", path, sizeof(path));
    if (!write_summary_json(path, sc, res, flags, elapsed_sec)) {
        return 0;
    }
    log_result(path);   /* GUI는 summary.json 경로를 받아 나머지 파일을 찾는다 */
    return 1;
}

/* 대피 안내 단계: 계산 → 콘솔 표 → evacuation.json. 반환값: 종료 코드 */
static int evacuation_step(Scenario *sc, ResultFlags *flags)
{
    EvacSummary evac;
    char        path[WF_PATH_MAX];

    log_progress(82, "등산객 대피 경로 계산 중 (%d팀)", sc->hiker_count);
    if (!run_evacuation(sc, &evac)) {
        return WF_ERR_MEMORY;
    }
    print_evacuation_table(sc, &evac);
    log_info("대피 안내: %d팀 중 대피 완료 %d팀, 고립 %d팀, 위험 %d팀 %d명",
             evac.hikers, evac.safe, evac.trapped, evac.at_risk_hikers, evac.at_risk_people);
    output_path(sc, "evacuation.json", path, sizeof(path));
    if (!write_evacuation_json(path, sc, &evac)) {
        return WF_ERR_OTHER;
    }
    flags->evacuation = 1;
    return WF_OK;
}

/* 진화 전략 단계: 방화선 최적화 + 전략 4가지 비교 → 콘솔 표 → suppression.json. 반환값: 종료 코드 */
static int suppression_step(Scenario *sc, ResultFlags *flags)
{
    SuppressionReport report;
    char              path[WF_PATH_MAX];
    int               exit_code = WF_OK;

    log_progress(83, "진화 전략 계산 시작");
    if (!compare_strategies(sc, sc->sim.random_seed, &report)) {
        free_suppression_report(&report);
        return WF_ERR_MEMORY;
    }
    print_strategy_table(sc, &report);
    log_info("진화 전략: 대응 없음 %.1f ha → 방화선+헬기 %.1f ha (%.1f%% 감소)",
             report.strategies[0].burned_area_ha, report.strategies[STRATEGY_COUNT - 1].burned_area_ha,
             report.strategies[STRATEGY_COUNT - 1].reduction_pct);
    output_path(sc, "suppression.json", path, sizeof(path));
    if (!write_suppression_json(path, sc, &report)) {
        exit_code = WF_ERR_OTHER;
    }
    flags->suppression = 1;
    free_suppression_report(&report);
    return exit_code;
}

/*
 * run / evac / optimize 모드: 산불 확산 시뮬레이션 + (대피 안내) + (진화 전략)
 *   1) 결과 폴더 만들기, 로그 파일 열기
 *   2) 기준 시뮬레이션(대응 없음) → 콘솔 통계·지도 → 확산 결과 파일 저장
 *   3) (evac 이상) 대피 안내
 *   4) (optimize) 진화 전략 — 시뮬레이션을 여러 번 다시 돌리므로 2) 의 파일을 먼저 저장해 둠
 *   5) summary.json
 */
static int run_fire_mode(Scenario *sc, const CommandLine *cmd, clock_t start_clock,
                         int with_evacuation, int with_suppression)
{
    SimOptions  opts;
    SimResult   res;
    ResultFlags flags = { 0, 0, 0 };
    char        log_path[WF_PATH_MAX];
    int         exit_code = WF_OK;

    if (!make_directories(sc->output_dir)) {
        log_error("결과 폴더를 만들 수 없음: %s", sc->output_dir);
        return WF_ERR_OTHER;
    }
    output_path(sc, "run.log", log_path, sizeof(log_path));
    if (!log_open_file(log_path)) {
        log_warn("로그 파일을 열 수 없음: %s (화면 출력만 함)", log_path);
    }

    sim_options_default(&opts);
    opts.map_every_min = cmd->map_every_min;
    sim_result_init(&res);

    log_info("확산 시뮬레이션 시작: %.0f분, 한 단계 %.1f분, 시드 %u",
             sc->sim.duration_min, sc->sim.time_step_min, sc->sim.random_seed);
    if (!run_fire_simulation(sc, &opts, sc->sim.random_seed, &res)) {
        sim_result_free(&res);
        return WF_ERR_MEMORY;
    }
    print_sim_statistics(&res, 30.0);
    print_map_fire(sc, (cmd->map_step > 0) ? cmd->map_step : choose_map_step(&sc->grid, 100), res.end_time_min);
    if (!save_fire_files(sc, &res)) {
        exit_code = WF_ERR_OTHER;
    }

    if (exit_code == WF_OK && with_evacuation) {
        exit_code = evacuation_step(sc, &flags);
    }
    if (exit_code == WF_OK && with_suppression) {
        exit_code = suppression_step(sc, &flags);
    }

    log_progress(95, "결과 저장 중: %s", sc->output_dir);
    if (exit_code == WF_OK && !save_summary(sc, &res, &flags, (double)(clock() - start_clock) / CLOCKS_PER_SEC)) {
        exit_code = WF_ERR_OTHER;
    }
    sim_result_free(&res);
    return exit_code;
}

int main(int argc, char *argv[])
{
    CommandLine cmd;
    Scenario    sc;
    clock_t     start_clock;
    int         exit_code = WF_OK;

    /* 1) 로그 준비 (Windows 콘솔 한글 출력 설정 포함) */
    log_init();
    start_clock = clock();

    /* 2) 명령줄 인자 해석 */
    if (!parse_command_line(argc, argv, &cmd)) {
        print_usage();
        return WF_ERR_INPUT;
    }
    log_info("wildfire 계산 엔진 %s 시작", WF_VERSION);
    log_progress(0, "시나리오 읽는 중: %s", cmd.scenario_path);

    /* 3) 시나리오 읽기 (설정, 지형, 연료, 등산로, 등산객) */
    if (!load_scenario(cmd.scenario_path, &sc)) {
        free_scenario(&sc);
        return WF_ERR_INPUT;
    }
    if (cmd.out_dir != NULL) {
        copy_string(sc.output_dir, sizeof(sc.output_dir), cmd.out_dir);
    }
    if (cmd.has_seed) {
        sc.sim.random_seed = cmd.seed;
    }
    log_progress(20, "시나리오 읽기 완료");

    /* 4) 모드별 작업 */
    switch (cmd.mode) {
    case MODE_PRINTMAP:
        exit_code = run_print_map(&sc, cmd.map_step);
        break;
    case MODE_RUN:
        exit_code = run_fire_mode(&sc, &cmd, start_clock, 0, 0);
        break;
    case MODE_EVAC:
        exit_code = run_fire_mode(&sc, &cmd, start_clock, 1, 0);
        break;
    case MODE_OPTIMIZE:
    case MODE_ALL:
        exit_code = run_fire_mode(&sc, &cmd, start_clock, 1, 1);
        break;
    case MODE_MC:
    default:
        log_error("이 모드는 아직 구현되지 않았습니다. 몬테카를로(mc)는 6단계에서 추가됩니다.");
        exit_code = WF_ERR_OTHER;
        break;
    }

    /* 5) 메모리 해제 */
    free_scenario(&sc);

    /* 6) 종료 */
    if (exit_code == WF_OK) {
        log_progress(100, "완료");
        log_done((double)(clock() - start_clock) / CLOCKS_PER_SEC);
    }
    log_close();
    return exit_code;
}
