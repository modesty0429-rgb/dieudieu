/*
 * suppression_eval.c
 * 진화 전략 4가지를 같은 조건(같은 난수 시드)으로 시뮬레이션해 피해를 비교한다.
 *
 *   1) 대응 없음       2) 방화선만       3) 헬기만       4) 방화선 + 헬기
 *
 * 비교 지표: 피해 면적(ha), 감소율(%), 불이 지나간 등산로 길이(km),
 *            위험 등산객 수(고립 또는 안전 여유 부족), 비화 횟수
 *
 * 전략마다 도착·전소 시각 격자를 suppression_<전략>_arrival.csv / _burnout.csv 로 저장해
 * GUI가 전후 화면을 나란히 재생할 수 있게 한다.
 */
#include <stdio.h>
#include <stdlib.h>

#include "suppression_eval.h"
#include "suppression.h"
#include "spread_sim.h"
#include "evac_alert.h"
#include "output_csv.h"
#include "grid.h"
#include "util.h"
#include "log.h"

/* 전략 정의 표: 영문 키, 한국어 이름, 방화선 사용, 헬기 사용 */
static const struct {
    const char *key;
    const char *name;
    int         use_firebreak;
    int         use_helicopters;
} STRATEGIES[STRATEGY_COUNT] = {
    { "none",       "대응 없음",     0, 0 },
    { "firebreak",  "방화선",        1, 0 },
    { "helicopter", "헬기",          0, 1 },
    { "both",       "방화선 + 헬기", 1, 1 },
};

/* 불이 지나간 등산로 셀 수 × 칸 크기 → 등산로 소실 길이 (km, 근사) */
static double burned_trail_km(const Grid *grid, const double *weights)
{
    int count = 0;
    int x, y;

    for (y = 0; y < grid->height; y++) {
        for (x = 0; x < grid->width; x++) {
            if (weights[grid_cell_index(grid, x, y)] >= TRAIL_CELL_WEIGHT &&
                time_is_set(grid->cells[y][x].arrival_time)) {
                count++;
            }
        }
    }
    return count * grid->cell_size_m / 1000.0;
}

/* 결과 폴더 안의 전략 파일 경로. 경로가 너무 길면 0 */
static int strategy_file_path(const Scenario *sc, const char *key, const char *kind, char *out, size_t size)
{
    int length = snprintf(out, size, "%s/suppression_%s_%s.csv", sc->output_dir, key, kind);
    if (length < 0 || (size_t)length >= size) {
        log_error("결과 파일 경로가 너무 김: %s", sc->output_dir);
        return 0;
    }
    return 1;
}

/* 전략 결과 파일(도착·전소 시각 격자)을 저장한다. */
static int save_strategy_grids(const Scenario *sc, const char *key)
{
    char path[WF_PATH_MAX];

    return strategy_file_path(sc, key, "arrival", path, sizeof(path)) &&
           write_grid_csv(path, &sc->grid, GRID_VALUE_ARRIVAL) &&
           strategy_file_path(sc, key, "burnout", path, sizeof(path)) &&
           write_grid_csv(path, &sc->grid, GRID_VALUE_BURNOUT);
}

/* 살수 기록을 결과 구조체로 복사한다. (SimResult 는 곧 해제되므로) */
static int copy_drops(const SimResult *res, StrategyResult *out)
{
    int i;

    out->drop_count = 0;
    out->drops = NULL;
    if (res->drop_count == 0) {
        return 1;
    }
    out->drops = (HeliDrop *)wf_malloc((size_t)res->drop_count * sizeof(HeliDrop), "헬기 살수 기록");
    if (out->drops == NULL) {
        return 0;
    }
    for (i = 0; i < res->drop_count; i++) {
        out->drops[i] = res->drops[i];
    }
    out->drop_count = res->drop_count;
    return 1;
}

/* 전략 하나를 시뮬레이션하고 결과를 채운다. */
static int evaluate_strategy(Scenario *sc, unsigned int seed, const double *weights,
                             SuppressionReport *report, int which)
{
    StrategyResult *out = &report->strategies[which];
    SimOptions      opts;
    SimResult       res;
    int             ok;

    out->key = STRATEGIES[which].key;
    out->name = STRATEGIES[which].name;
    out->use_firebreak = STRATEGIES[which].use_firebreak;
    out->use_helicopters = STRATEGIES[which].use_helicopters;

    if (out->use_firebreak) {
        apply_firebreak(&sc->grid, &report->firebreak);
    }
    sim_options_default(&opts);
    opts.quiet = 1;
    opts.record_events = 0;
    opts.use_helicopters = out->use_helicopters;
    opts.heli_guide = report->guide;
    sim_result_init(&res);

    ok = run_fire_simulation(sc, &opts, seed, &res) && run_evacuation(sc, &out->evac) &&
         copy_drops(&res, out) && save_strategy_grids(sc, out->key);

    out->burned_area_ha = res.final_area_ha;
    out->burned_cells = res.burned_cells;
    out->spot_fires = res.spot_fire_count;
    out->trail_burned_km = burned_trail_km(&sc->grid, weights);

    if (out->use_firebreak) {
        remove_firebreak(&sc->grid, &report->firebreak);
    }
    sim_result_free(&res);
    return ok;
}

/*
 * compare_strategies: 진화 전략 4가지를 비교한다.
 *   1) 셀 가치(등산로 가중) 만들기
 *   2) 기준 시뮬레이션 → 점화 트리 하위 가치 (헬기 목표 선택의 길잡이)
 *   3) optimize_firebreak 로 방화선 K칸 배치
 *   4) 전략 4가지를 각각 시뮬레이션 + 대피 계산 + 파일 저장
 * 성공 1, 실패 0
 */
int compare_strategies(Scenario *sc, unsigned int seed, SuppressionReport *report)
{
    double    *weights = NULL;
    SimOptions opts;
    SimResult  res;
    int        total = sc->grid.width * sc->grid.height;
    int        ok;
    int        i;

    firebreak_plan_init(&report->firebreak);
    report->guide = NULL;
    for (i = 0; i < STRATEGY_COUNT; i++) {
        report->strategies[i].drops = NULL;
        report->strategies[i].drop_count = 0;
    }

    /* 1) 셀 가치, 2) 기준 시뮬레이션의 하위 가치 */
    report->guide = (double *)wf_malloc((size_t)total * sizeof(double), "헬기 길잡이 가치");
    if (report->guide == NULL || !build_cell_weights(sc, &weights)) {
        free(weights);
        return 0;
    }
    sim_options_default(&opts);
    opts.quiet = 1;
    opts.record_events = 0;
    sim_result_init(&res);
    ok = run_fire_simulation(sc, &opts, seed, &res) && compute_subtree_values(&sc->grid, weights, report->guide);
    sim_result_free(&res);

    /* 3) 방화선 최적화 */
    if (ok && sc->supp.firebreak_cells > 0) {
        log_progress(84, "방화선 %d칸 배치 탐색 중 (탐욕법)", sc->supp.firebreak_cells);
        ok = optimize_firebreak(sc, weights, seed, &report->firebreak);
    }

    /* 4) 전략 비교 */
    for (i = 0; i < STRATEGY_COUNT && ok; i++) {
        log_progress(86 + i, "진화 전략 비교: %s", STRATEGIES[i].name);
        ok = evaluate_strategy(sc, seed, weights, report, i);
    }
    for (i = 0; i < STRATEGY_COUNT && ok; i++) {
        double base = report->strategies[0].burned_area_ha;
        report->strategies[i].reduction_pct =
            (base > 0.0) ? 100.0 * (base - report->strategies[i].burned_area_ha) / base : 0.0;
    }

    free(weights);
    return ok;
}

void free_suppression_report(SuppressionReport *report)
{
    int i;

    firebreak_plan_free(&report->firebreak);
    for (i = 0; i < STRATEGY_COUNT; i++) {
        free(report->strategies[i].drops);
        report->strategies[i].drops = NULL;
        report->strategies[i].drop_count = 0;
    }
    free(report->guide);
    report->guide = NULL;
}

/* 전략 비교표를 콘솔에 출력한다. */
void print_strategy_table(const Scenario *sc, const SuppressionReport *report)
{
    int i;

    printf("\n================ 진화 전략 비교 ================\n");
    printf(" 방화선: %d칸 (%d개 조각, %.0f분 완성)   헬기: %d대 (반경 %d칸, %.0f분 간격, 효과 %.0f분)\n",
           report->firebreak.cells.count, report->firebreak.step_count, sc->supp.firebreak_ready_min,
           sc->supp.helicopters, sc->supp.heli_radius_cells, sc->supp.heli_interval_min,
           sc->supp.heli_effect_min);
    printf("----------------+-----------+--------+-----------+-----------+------+------\n");
    printf(" 전략           | 피해 (ha) | 감소율 | 등산로 km | 위험 팀/명 | 비화 | 살수\n");
    printf("----------------+-----------+--------+-----------+-----------+------+------\n");
    for (i = 0; i < STRATEGY_COUNT; i++) {
        const StrategyResult *s = &report->strategies[i];
        printf(" %-15s| %9.1f | %5.1f%% | %9.2f | %4d / %-3d | %4d | %4d\n",
               s->name, s->burned_area_ha, s->reduction_pct, s->trail_burned_km,
               s->evac.at_risk_hikers, s->evac.at_risk_people, s->spot_fires, s->drop_count);
    }
    printf("------------------------------------------------\n");
    fflush(stdout);
}
