/*
 * main.c
 * 산불 확산 예측 및 등산객 대피 안내 시스템 — C 계산 엔진의 시작점
 *
 * 사용법:
 *   wildfire.exe <시나리오.ini> [--mode 모드] [--out 결과폴더] [--seed 난수시드] [--step 출력간격]
 *
 * 모드:
 *   printmap : 시나리오를 읽고 지도·요약을 콘솔에 출력 (1단계)
 *   run      : 산불 확산 시뮬레이션 (2단계 예정)
 *   evac     : 등산객 대피 경로·경보 (4단계 예정)
 *   optimize : 방화선·헬기 배치 최적화 (5단계 예정)
 *   mc       : 몬테카를로 반복 실험 (6단계 예정)
 *   all      : run → evac → optimize → mc 모두
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
    case MODE_EVAC:
    case MODE_OPTIMIZE:
    case MODE_MC:
    case MODE_ALL:
    default:
        log_error("이 모드는 아직 구현되지 않았습니다. 1단계에서는 --mode printmap 만 사용할 수 있습니다.");
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
    return exit_code;
}
