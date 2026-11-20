/*
 * montecarlo.c
 * 몬테카를로 반복 실험
 *
 * [왜 필요한가]
 *   기상 예보에는 오차가 있고, 비화는 우연에 좌우된다. 시뮬레이션 한 번의 결과만 믿으면
 *   "운 좋은 한 번" 또는 "운 나쁜 한 번"을 보고 판단할 수 있다.
 *   같은 조건을 N번(기본 100번) 조금씩 다르게 실행하면 결과의 "분포"를 알 수 있다.
 *
 * [회차마다 바꾸는 것]
 *   - 비화 난수 시드
 *   - 기상 오차: 풍속 + N(0, wind_speed_sd), 풍향 + N(0, wind_dir_sd_deg), 습도 + N(0, rh_sd)
 *     (회차 안에서는 같은 오차가 계속 유지됨 = "예보가 이만큼 빗나간 날")
 *
 * [결과]
 *   - 셀별 연소 확률 = 그 셀이 탄 회차 수 / N
 *   - 셀별 보수적 도착 시각 = 가장 이른 10% 회차에서의 도착 시각
 *       → 셀마다 "지금까지 나온 도착 시각 중 가장 작은 k개"만 정렬된 작은 배열로 유지한다.
 *         (모든 회차의 값을 저장하면 N × 셀 수만큼 메모리가 들지만, k개만 유지하면 훨씬 적다)
 *   - 피해 면적의 평균·표준편차·최솟값·10/50/90% 분위·최댓값
 */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#include "montecarlo.h"
#include "spread_sim.h"
#include "rng.h"
#include "util.h"
#include "log.h"

#define NO_ARRIVAL 1.0e18   /* "아직 도착 기록 없음"을 뜻하는 큰 값 */

void montecarlo_init(MonteCarloResult *mc)
{
    mc->runs = 0;
    mc->width = mc->height = 0;
    mc->base_seed = 0;
    mc->areas = NULL;
    mc->seeds = NULL;
    mc->offsets = NULL;
    mc->burn_probability = NULL;
    mc->arrival_early = NULL;
    mc->early_rank = 1;
    mc->mean_area = mc->sd_area = 0.0;
    mc->min_area = mc->p10_area = mc->p50_area = mc->p90_area = mc->max_area = 0.0;
}

void free_monte_carlo(MonteCarloResult *mc)
{
    free(mc->areas);
    free(mc->seeds);
    free(mc->offsets);
    free(mc->burn_probability);
    free(mc->arrival_early);
    montecarlo_init(mc);
}

/*
 * 셀 하나의 "가장 작은 k개" 목록(오름차순)에 새 값을 넣는다. — 삽입 정렬의 한 단계
 * 목록의 마지막(k번째로 작은 값)보다 크면 버리고, 작으면 알맞은 자리에 끼워 넣는다.
 */
static void insert_smallest(double *list, int k, double value)
{
    int i;

    if (value >= list[k - 1]) {
        return;
    }
    i = k - 1;
    while (i > 0 && list[i - 1] > value) {
        list[i] = list[i - 1];   /* 큰 값을 한 칸씩 뒤로 */
        i--;
    }
    list[i] = value;
}

/* 실수 오름차순 비교 (qsort 용) */
static int compare_double(const void *a, const void *b)
{
    double da = *(const double *)a;
    double db = *(const double *)b;
    if (da < db) return -1;
    if (da > db) return 1;
    return 0;
}

/* 정렬된 배열에서 fraction(0 ~ 1) 분위 값 (가장 가까운 순위 방식) */
double percentile_of_sorted(const double *sorted, int count, double fraction)
{
    double rank = ceil(fraction * count);
    int    index = (int)rank - 1;

    if (count <= 0) {
        return 0.0;
    }
    if (index < 0) {
        index = 0;
    }
    if (index >= count) {
        index = count - 1;
    }
    return sorted[index];
}

/* 피해 면적 통계(평균, 표준편차, 분위수)를 계산한다. */
static int compute_area_statistics(MonteCarloResult *mc)
{
    double *sorted = (double *)wf_malloc((size_t)mc->runs * sizeof(double), "면적 정렬");
    double  sum = 0.0, sum_sq = 0.0;
    int     i;

    if (sorted == NULL) {
        return 0;
    }
    for (i = 0; i < mc->runs; i++) {
        sorted[i] = mc->areas[i];
        sum += mc->areas[i];
    }
    mc->mean_area = sum / mc->runs;
    for (i = 0; i < mc->runs; i++) {
        double diff = mc->areas[i] - mc->mean_area;
        sum_sq += diff * diff;
    }
    mc->sd_area = (mc->runs > 1) ? sqrt(sum_sq / (mc->runs - 1)) : 0.0;

    qsort(sorted, (size_t)mc->runs, sizeof(double), compare_double);
    mc->min_area = sorted[0];
    mc->max_area = sorted[mc->runs - 1];
    mc->p10_area = percentile_of_sorted(sorted, mc->runs, 0.10);
    mc->p50_area = percentile_of_sorted(sorted, mc->runs, 0.50);
    mc->p90_area = percentile_of_sorted(sorted, mc->runs, 0.90);
    free(sorted);
    return 1;
}

/* 결과 배열을 모두 할당한다. 성공 1, 실패 0 */
static int allocate_mc_arrays(MonteCarloResult *mc, int cells, double **smallest, int **burn_count)
{
    int i;

    mc->areas = (double *)wf_malloc((size_t)mc->runs * sizeof(double), "회차별 면적");
    mc->seeds = (unsigned int *)wf_malloc((size_t)mc->runs * sizeof(unsigned int), "회차별 시드");
    mc->offsets = (WeatherOffset *)wf_malloc((size_t)mc->runs * sizeof(WeatherOffset), "회차별 기상 오차");
    mc->burn_probability = (double *)wf_malloc((size_t)cells * sizeof(double), "연소 확률");
    mc->arrival_early = (double *)wf_malloc((size_t)cells * sizeof(double), "보수적 도착 시각");
    *smallest = (double *)wf_malloc((size_t)cells * (size_t)mc->early_rank * sizeof(double), "가장 이른 도착 목록");
    *burn_count = (int *)wf_calloc((size_t)cells, sizeof(int), "연소 횟수");
    if (mc->areas == NULL || mc->seeds == NULL || mc->offsets == NULL || mc->burn_probability == NULL ||
        mc->arrival_early == NULL || *smallest == NULL || *burn_count == NULL) {
        return 0;
    }
    for (i = 0; i < cells * mc->early_rank; i++) {
        (*smallest)[i] = NO_ARRIVAL;
    }
    return 1;
}

/*
 * run_monte_carlo: 시나리오를 sc->mc.runs 번 반복 실행해 연소 확률, 보수적 도착 시각, 면적 통계를 구한다.
 * 회차 i 의 비화 시드 = 기본 시드 + 1 + i, 기상 오차는 기본 시드로 시작한 난수에서 뽑는다.
 * (따라서 같은 시나리오·같은 시드면 몬테카를로 결과도 항상 같다)
 * 성공 1, 실패(메모리 부족) 0
 */
int run_monte_carlo(Scenario *sc, MonteCarloResult *mc)
{
    Grid      *grid = &sc->grid;
    int        cells = grid->width * grid->height;
    double    *smallest = NULL;
    int       *burn_count = NULL;
    Rng        weather_rng;
    SimOptions opts;
    int        ok = 1;
    int        run, i;

    montecarlo_init(mc);
    mc->runs = sc->mc.runs;
    mc->width = grid->width;
    mc->height = grid->height;
    mc->base_seed = sc->sim.random_seed;
    {
        double rank = ceil(MC_EARLY_PERCENTILE * mc->runs);   /* 100회면 10번째 */
        mc->early_rank = (int)rank;
    }
    if (mc->early_rank < 1) {
        mc->early_rank = 1;
    }
    if (!allocate_mc_arrays(mc, cells, &smallest, &burn_count)) {
        free(smallest);
        free(burn_count);
        return 0;
    }

    rng_seed(&weather_rng, mc->base_seed);
    sim_options_default(&opts);
    opts.quiet = 1;
    opts.record_events = 0;

    for (run = 0; run < mc->runs && ok; run++) {
        SimResult res;

        /* 1) 이번 회차의 기상 오차와 시드 */
        opts.offset.wind_speed_ms = rng_normal(&weather_rng, 0.0, sc->mc.wind_speed_sd);
        opts.offset.wind_dir_deg = rng_normal(&weather_rng, 0.0, sc->mc.wind_dir_sd_deg);
        opts.offset.rh_pct = rng_normal(&weather_rng, 0.0, sc->mc.rh_sd);
        mc->offsets[run] = opts.offset;
        mc->seeds[run] = mc->base_seed + 1u + (unsigned int)run;

        /* 2) 시뮬레이션 */
        sim_result_init(&res);
        ok = run_fire_simulation(sc, &opts, mc->seeds[run], &res);
        mc->areas[run] = res.final_area_ha;
        sim_result_free(&res);

        /* 3) 셀별 기록 누적 */
        for (i = 0; i < cells && ok; i++) {
            double arrival = grid->cells[i / grid->width][i % grid->width].arrival_time;
            if (time_is_set(arrival)) {
                burn_count[i]++;
                insert_smallest(&smallest[i * mc->early_rank], mc->early_rank, arrival);
            }
        }

        if ((run + 1) % 10 == 0 || run + 1 == mc->runs) {
            log_progress(90 + (int)(5.0 * (run + 1) / mc->runs), "몬테카를로 %d/%d회 (이번 회차 %.1f ha)",
                         run + 1, mc->runs, mc->areas[run]);
        }
    }

    /* 4) 셀별 결과: 연소 확률, k번째로 이른 도착 시각 */
    for (i = 0; i < cells && ok; i++) {
        double kth = smallest[i * mc->early_rank + mc->early_rank - 1];
        mc->burn_probability[i] = (double)burn_count[i] / mc->runs;
        mc->arrival_early[i] = (kth < NO_ARRIVAL) ? kth : WF_NO_TIME;
    }
    ok = ok && compute_area_statistics(mc);

    free(smallest);
    free(burn_count);
    return ok;
}

/* 몬테카를로 요약과 피해 면적 분포(글자 막대그래프)를 출력한다. */
void print_monte_carlo_summary(const MonteCarloResult *mc)
{
    int    counts[MC_HISTOGRAM_BINS] = { 0 };
    double width = (mc->max_area - mc->min_area) / MC_HISTOGRAM_BINS;
    int    max_count = 1;
    int    i, k;

    for (i = 0; i < mc->runs; i++) {
        int bin = (width > 0.0) ? (int)((mc->areas[i] - mc->min_area) / width) : 0;
        if (bin >= MC_HISTOGRAM_BINS) {
            bin = MC_HISTOGRAM_BINS - 1;
        }
        counts[bin]++;
    }
    for (i = 0; i < MC_HISTOGRAM_BINS; i++) {
        if (counts[i] > max_count) {
            max_count = counts[i];
        }
    }

    printf("\n================ 몬테카를로 %d회 ================\n", mc->runs);
    printf(" 피해 면적: 평균 %.1f ha (표준편차 %.1f), 최소 %.1f, 10%% %.1f, 중앙값 %.1f, 90%% %.1f, 최대 %.1f\n",
           mc->mean_area, mc->sd_area, mc->min_area, mc->p10_area, mc->p50_area, mc->p90_area, mc->max_area);
    printf(" 보수적 도착 시각: 가장 이른 %d회(%.0f%%)의 도착 시각 사용\n", mc->early_rank,
           100.0 * MC_EARLY_PERCENTILE);
    printf("\n 피해 면적 분포\n");
    for (i = 0; i < MC_HISTOGRAM_BINS; i++) {
        int bar = counts[i] * 40 / max_count;
        printf(" %7.1f ~ %7.1f ha | ", mc->min_area + i * width, mc->min_area + (i + 1) * width);
        for (k = 0; k < bar; k++) {
            putchar('#');
        }
        printf(" %d\n", counts[i]);
    }
    printf("=================================================\n");
    fflush(stdout);
}
