/*
 * montecarlo.h
 * 몬테카를로 반복 실험: 같은 시나리오를 난수와 기상 오차를 바꿔 N번 실행한다.
 */
#ifndef MONTECARLO_H
#define MONTECARLO_H

#include "wf_types.h"

#define MC_EARLY_PERCENTILE 0.10   /* 보수적 도착 시각: 가장 이른 10% 회차의 도착 시각 */
#define MC_HISTOGRAM_BINS   10

typedef struct {
    int            runs;             /* 반복 횟수 N */
    int            width, height;
    unsigned int   base_seed;
    double        *areas;            /* 회차별 피해 면적 (ha) */
    unsigned int  *seeds;            /* 회차별 비화 시드 */
    WeatherOffset *offsets;          /* 회차별 기상 오차 */
    double        *burn_probability; /* 셀별 연소 확률 (0 ~ 1) */
    double        *arrival_early;    /* 셀별 보수적 도착 시각 (분), 그 비율만큼 타지 않았으면 -1 */
    int            early_rank;       /* 보수적 도착 시각에 쓴 순위 k (= ceil(N × 10%)) */
    double         mean_area, sd_area;
    double         min_area, p10_area, p50_area, p90_area, max_area;
} MonteCarloResult;

void montecarlo_init(MonteCarloResult *mc);
int  run_monte_carlo(Scenario *sc, MonteCarloResult *mc);
void free_monte_carlo(MonteCarloResult *mc);
double percentile_of_sorted(const double *sorted, int count, double fraction);
void print_monte_carlo_summary(const MonteCarloResult *mc);

#endif /* MONTECARLO_H */
