/*
 * spread_sim.c
 * 격자 위에서 산불이 시간에 따라 번지는 과정을 시뮬레이션한다.
 *
 * [기본 아이디어] — "누적 거리" 방식의 셀룰러 오토마타
 *   - 불이 붙은 셀은 8방향 이웃을 향해 매 단계 (확산 속도 × dt) 만큼 불을 밀어낸다.
 *   - 밀어낸 거리가 이웃 셀 중심까지의 거리(30 m, 대각선 42.4 m)를 넘으면 이웃에 불이 붙는다.
 *   - 넘친 거리만큼 시각을 앞당겨 "불이 도착한 시각"을 분 단위 소수까지 기록한다.
 *
 * [두 가지 목록]
 *   front  (화선) : 아직 타지 않은 이웃이 남아 있어 불을 밀어내는 중인 셀
 *   burning(연소) : 불꽃이 남아 있는 셀. 연료별 연소 시간이 지나면 "전소"가 된다.
 *   두 목록을 나눈 이유: 불꽃이 짧은 초지도 화선은 계속 나아가야 하기 때문이다.
 *   (불꽃이 꺼지면 확산도 멈추게 만들면, 풀밭 불이 다음 칸에 닿기 전에 꺼지는 문제가 생긴다.)
 *
 * [한 단계의 순서] simulate_fire_step
 *   1) 화선의 각 셀 → 8방향으로 불 밀어내기 → 도착한 이웃은 점화 예약
 *   2) 연소 중인 셀 → 비화 시도 → 떨어진 곳 점화 예약
 *   3) 예약된 셀에 불 붙이기 (모든 셀이 같은 시점 상태를 보고 계산하도록 마지막에 한꺼번에)
 *   4) 연소 시간이 끝난 셀 → 전소
 */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

#include "spread_sim.h"
#include "spread_rate.h"
#include "spotting.h"
#include "fuel_moisture.h"
#include "weather.h"
#include "console_view.h"
#include "suppression.h"
#include "grid.h"
#include "util.h"
#include "log.h"

#define TIME_EPSILON 1e-9   /* 실수 시각 비교 오차 */

/* ================================================================
 * 결과·상태 구조체 준비와 해제
 * ================================================================ */

void sim_result_init(SimResult *res)
{
    res->steps = NULL;
    res->step_count = 0;
    res->step_capacity = 0;
    res->events = NULL;
    res->event_count = 0;
    res->event_capacity = 0;
    res->burned_cells = 0;
    res->final_area_ha = 0.0;
    res->spot_fire_count = 0;
    res->max_spread_rate = 0.0;
    res->end_time_min = 0.0;
    res->fire_out = 0;
    res->drops = NULL;
    res->drop_count = 0;
    res->drop_capacity = 0;
}

void sim_result_free(SimResult *res)
{
    free(res->steps);
    free(res->events);
    free(res->drops);
    sim_result_init(res);
}

/* 기본 실행 옵션: 기상 오차 없음, 이벤트 기록, 로그 출력, 중간 지도 없음 */
void sim_options_default(SimOptions *opts)
{
    opts->offset.wind_speed_ms = 0.0;
    opts->offset.wind_dir_deg = 0.0;
    opts->offset.rh_pct = 0.0;
    opts->record_events = 1;
    opts->quiet = 0;
    opts->map_every_min = 0.0;
    opts->use_helicopters = 0;
    opts->heli_guide = NULL;
}

int fire_state_init(FireState *state)
{
    intarray_init(&state->front);
    intarray_init(&state->burning);
    intarray_init(&state->scheduled);
    state->ignited_count = 0;
    state->seed = 0;
    state->dead_moisture = 0.0;
    state->interval_max_rate = 0.0;
    return 1;
}

void fire_state_free(FireState *state)
{
    intarray_free(&state->front);
    intarray_free(&state->burning);
    intarray_free(&state->scheduled);
}

/* 통계 한 줄을 결과에 추가한다. 공간이 모자라면 2배로 늘린다. */
static int push_step_stats(SimResult *res, const StepStats *stats)
{
    if (res->step_count == res->step_capacity) {
        int        new_capacity = (res->step_capacity == 0) ? 64 : res->step_capacity * 2;
        StepStats *grown = (StepStats *)realloc(res->steps, (size_t)new_capacity * sizeof(StepStats));
        if (grown == NULL) {
            log_error("메모리 부족: 통계 기록 %d개", new_capacity);
            return 0;
        }
        res->steps = grown;
        res->step_capacity = new_capacity;
    }
    res->steps[res->step_count] = *stats;
    res->step_count++;
    return 1;
}

/* 상태 변화 사건 하나를 결과에 추가한다. */
static int push_event(SimResult *res, double time_min, int x, int y, CellState new_state)
{
    if (res->event_count == res->event_capacity) {
        int        new_capacity = (res->event_capacity == 0) ? 1024 : res->event_capacity * 2;
        FireEvent *grown = (FireEvent *)realloc(res->events, (size_t)new_capacity * sizeof(FireEvent));
        if (grown == NULL) {
            log_error("메모리 부족: 화재 이벤트 %d개", new_capacity);
            return 0;
        }
        res->events = grown;
        res->event_capacity = new_capacity;
    }
    res->events[res->event_count].time_min = time_min;
    res->events[res->event_count].x = x;
    res->events[res->event_count].y = y;
    res->events[res->event_count].new_state = new_state;
    res->event_count++;
    return 1;
}

/* ================================================================
 * 셀 판정 도우미
 * ================================================================ */

/* 아직 타지 않았고 탈 수 있는 연료가 있는 셀이면 1 */
int cell_is_receptive(const Scenario *sc, const Cell *cell)
{
    return cell->state == CELL_UNBURNED && cell_fuel_is_burnable(sc, cell);
}

/* 불이 지나갈 수 없는 장벽(방화선·물·바위·도로 등 타지 않는 연료)이면 1 */
static int cell_is_barrier(const Scenario *sc, const Cell *cell)
{
    if (cell->state == CELL_FIREBREAK || cell->state == CELL_WATER || cell->state == CELL_ROCK) {
        return 1;
    }
    return !cell_fuel_is_burnable(sc, cell);
}

/*
 * 대각선 방향 확산이 막혔는지 검사한다.
 * 대각선 양옆의 두 칸이 모두 장벽이면 불이 그 "모서리 틈"으로 빠져나갈 수 없다고 본다.
 * (한 칸 두께의 대각선 방화선·도로를 불이 뚫고 지나가는 것을 막기 위함)
 */
static int diagonal_blocked(const Scenario *sc, int x, int y, int dir)
{
    const Grid *grid = &sc->grid;
    int         dx = grid_neighbor_dx(dir);
    int         dy = grid_neighbor_dy(dir);

    if (dx == 0 || dy == 0) {
        return 0;   /* 상하좌우는 해당 없음 */
    }
    return cell_is_barrier(sc, &grid->cells[y][x + dx]) &&
           cell_is_barrier(sc, &grid->cells[y + dy][x]);
}

/* ================================================================
 * 점화
 * ================================================================ */

/*
 * (x, y) 셀에 time_min 시각 점화를 예약한다.
 * 같은 단계에 여러 이웃에서 불이 도착하면 가장 이른 시각과 그 출발 셀(parent)을 남긴다.
 * 반환값: 새로 예약했으면 1, 이미 예약돼 있었거나 탈 수 없으면 0, 메모리 부족 -1
 */
int schedule_ignition(Scenario *sc, FireState *state, int x, int y, double time_min,
                      int parent_index, int by_spot)
{
    Cell *cell = &sc->grid.cells[y][x];

    if (!cell_is_receptive(sc, cell)) {
        return 0;
    }
    if (!time_is_set(cell->arrival_time)) {
        /* 처음 예약 */
        cell->arrival_time = time_min;
        cell->parent_index = parent_index;
        cell->ignited_by_spot = by_spot;
        if (intarray_push(&state->scheduled, grid_cell_index(&sc->grid, x, y)) != 0) {
            return -1;
        }
        return 1;
    }
    if (time_min < cell->arrival_time) {
        /* 이미 예약됐지만 더 이른 도착이면 갱신 */
        cell->arrival_time = time_min;
        cell->parent_index = parent_index;
        cell->ignited_by_spot = by_spot;
    }
    return 0;
}

/* 예약된 셀에 실제로 불을 붙인다. (상태를 "연소 중"으로 바꾸고 두 목록에 넣는다) */
static int ignite_scheduled_cells(Scenario *sc, FireState *state, SimResult *res, const SimOptions *opts)
{
    int i;

    for (i = 0; i < state->scheduled.count; i++) {
        int   index = state->scheduled.data[i];
        int   x = index % sc->grid.width;
        int   y = index / sc->grid.width;
        Cell *cell = &sc->grid.cells[y][x];

        cell->state = CELL_BURNING;
        state->ignited_count++;
        if (intarray_push(&state->front, index) != 0 || intarray_push(&state->burning, index) != 0) {
            return 0;
        }
        if (opts->record_events && !push_event(res, cell->arrival_time, x, y, CELL_BURNING)) {
            return 0;
        }
    }
    intarray_clear(&state->scheduled);
    return 1;
}

/* 시나리오의 발화 지점 중 [t, t + dt) 시각에 해당하는 것을 예약한다. */
static int schedule_ignition_points(Scenario *sc, FireState *state, double t, double dt)
{
    int i;

    for (i = 0; i < sc->ignition_count; i++) {
        const IgnitionPoint *p = &sc->ignitions[i];
        if (p->time_min >= t - TIME_EPSILON && p->time_min < t + dt - TIME_EPSILON) {
            if (schedule_ignition(sc, state, p->x, p->y, p->time_min, -1, 0) < 0) {
                return 0;
            }
        }
    }
    return 1;
}

/* 아직 시각이 오지 않은 발화 지점이 남아 있으면 1 */
static int has_pending_ignitions(const Scenario *sc, double t)
{
    int i;
    for (i = 0; i < sc->ignition_count; i++) {
        if (sc->ignitions[i].time_min >= t - TIME_EPSILON) {
            return 1;
        }
    }
    return 0;
}

/* ================================================================
 * 한 단계 진행
 * ================================================================ */

/*
 * 화선의 셀 하나가 8방향으로 불을 밀어낸다.
 * 반환값: 아직 불이 가야 할 이웃이 남아 있으면 1 (다음 단계에도 화선에 남김), 아니면 0
 */
static int spread_from_cell(Scenario *sc, FireState *state, int index, double t, double dt,
                            const WeatherRecord *weather)
{
    Grid *grid = &sc->grid;
    int   x = index % grid->width;
    int   y = index / grid->width;
    Cell *cell = &grid->cells[y][x];
    int   still_active = 0;
    int   dir;

    if (cell->wet_until > t) {
        return 1;   /* 헬기 살수로 젖은 곳의 불은 효과가 끝날 때까지 번지지 못함 (화선에는 남김) */
    }
    for (dir = 0; dir < 8; dir++) {
        int    nx = x + grid_neighbor_dx(dir);
        int    ny = y + grid_neighbor_dy(dir);
        Cell  *neighbor;
        double rate, distance;

        if (!grid_in_bounds(grid, nx, ny)) {
            continue;
        }
        neighbor = &grid->cells[ny][nx];
        if (!cell_is_receptive(sc, neighbor) || diagonal_blocked(sc, x, y, dir)) {
            continue;
        }
        still_active = 1;
        if (neighbor->wet_until > t) {
            continue;   /* 헬기 살수로 젖어 있는 동안은 불이 나아가지 못함 */
        }

        rate = compute_spread_rate(sc, x, y, dir, weather, NULL);
        if (rate <= 0.0) {
            continue;
        }
        if (rate > state->interval_max_rate) {
            state->interval_max_rate = rate;
        }

        cell->progress[dir] += rate * dt;
        distance = grid_neighbor_distance(grid, dir);
        if (cell->progress[dir] >= distance) {
            /* 넘친 거리만큼 도착 시각을 앞당긴다: 넘친 거리 / 속도 = 남는 시간 */
            double arrival = t + dt - (cell->progress[dir] - distance) / rate;
            if (arrival < t) {
                arrival = t;
            }
            if (schedule_ignition(sc, state, nx, ny, arrival, index, 0) < 0) {
                return -1;
            }
        }
    }
    return still_active;
}

/*
 * simulate_fire_step: 시각 t 에서 dt 분 동안 불을 진행시킨다.
 *   1) 화선 셀마다 8방향으로 불 밀어내기 (불이 갈 곳이 없어진 셀은 화선에서 뺌)
 *   2) 연소 중인 셀마다 비화 시도
 *   3) 예약된 셀 점화
 *   4) 연소 시간이 끝난 셀은 전소 처리
 * 성공 1, 메모리 부족 0
 */
int simulate_fire_step(Scenario *sc, FireState *state, double t, double dt,
                       const WeatherRecord *weather, SimResult *res, const SimOptions *opts)
{
    int i;
    int kept;

    /* 1) 화선 진행: 남길 셀만 앞으로 당겨 담는다 (목록을 새로 만들지 않고 제자리에서 정리) */
    kept = 0;
    for (i = 0; i < state->front.count; i++) {
        int index = state->front.data[i];
        int active = spread_from_cell(sc, state, index, t, dt, weather);
        if (active < 0) {
            return 0;
        }
        if (active) {
            state->front.data[kept] = index;
            kept++;
        }
    }
    state->front.count = kept;

    /* 2) 비화 */
    for (i = 0; i < state->burning.count; i++) {
        int spotted = try_spotting(sc, state, state->burning.data[i], t, dt, weather);
        if (spotted < 0) {
            return 0;
        }
        res->spot_fire_count += spotted;
    }

    /* 3) 점화 */
    if (!ignite_scheduled_cells(sc, state, res, opts)) {
        return 0;
    }

    /* 4) 전소 처리 */
    kept = 0;
    for (i = 0; i < state->burning.count; i++) {
        int              index = state->burning.data[i];
        int              x = index % sc->grid.width;
        int              y = index / sc->grid.width;
        Cell            *cell = &sc->grid.cells[y][x];
        const FuelModel *fm = find_fuel_model(sc, cell->fuel_code);
        double           end_time = cell->arrival_time + fm->burn_duration_min;

        if (end_time <= t + dt + TIME_EPSILON) {
            cell->state = CELL_BURNED;
            cell->burnout_time = end_time;
            if (opts->record_events && !push_event(res, end_time, x, y, CELL_BURNED)) {
                return 0;
            }
        } else {
            state->burning.data[kept] = index;
            kept++;
        }
    }
    state->burning.count = kept;
    return 1;
}

/* ================================================================
 * 전체 실행
 * ================================================================ */

/* 현재 상태를 통계 한 줄로 기록한다. */
static int record_stats(const Scenario *sc, FireState *state, double t,
                        const WeatherRecord *weather, SimResult *res)
{
    StepStats stats;
    double    cell_area_ha = sc->grid.cell_size_m * sc->grid.cell_size_m / 10000.0;

    stats.time_min = t;
    stats.burning_cells = state->burning.count;
    stats.burned_cells = state->ignited_count;
    stats.burned_area_ha = state->ignited_count * cell_area_ha;
    stats.max_spread_rate_m_min = state->interval_max_rate;
    stats.spot_fires = res->spot_fire_count;
    stats.dead_moisture_pct = state->dead_moisture;
    stats.weather = *weather;

    if (state->interval_max_rate > res->max_spread_rate) {
        res->max_spread_rate = state->interval_max_rate;
    }
    state->interval_max_rate = 0.0;
    return push_step_stats(res, &stats);
}

/*
 * run_fire_simulation: 시나리오 전체 시간 동안 산불 확산을 시뮬레이션한다.
 *   - 격자의 화재 기록을 지우고 연료 수분을 초기화한 뒤
 *   - 매 단계: 기상 구하기 → 연료 수분 갱신 → 발화 지점 예약 → simulate_fire_step
 *   - 출력 간격마다 통계를 기록하고, 불이 완전히 꺼지면 일찍 끝낸다.
 * seed: 비화용 난수 시드. 성공 1, 실패(메모리 부족) 0
 */
int run_fire_simulation(Scenario *sc, const SimOptions *opts, unsigned int seed, SimResult *res)
{
    FireState     state;
    WeatherRecord weather;
    double        dt = sc->sim.time_step_min;
    double        next_output = sc->sim.output_interval_min;
    double        next_map = opts->map_every_min;
    double        next_drop = first_helicopter_time(sc);
    double        t = 0.0;
    long          step = 0;
    int           ok = 1;

    grid_reset_fire_state(&sc->grid);
    fire_state_init(&state);
    state.seed = seed;
    init_fuel_moisture(sc, &state.dead_moisture);

    get_weather_at(sc, 0.0, &opts->offset, &weather);
    ok = record_stats(sc, &state, 0.0, &weather, res);

    while (ok && t < sc->sim.duration_min - TIME_EPSILON) {
        double t_end;

        /* 1) 이번 단계의 기상과 연료 수분 */
        get_weather_at(sc, t, &opts->offset, &weather);
        update_fuel_moisture(sc, &state.dead_moisture, &weather, dt);

        /* (5단계) 헬기 출동 간격마다 살수 지점을 정해 물을 뿌린다 */
        if (opts->use_helicopters && sc->supp.helicopters > 0 && t >= next_drop - TIME_EPSILON) {
            ok = plan_helicopter_drops(sc, &state, t, opts->heli_guide, res);
            next_drop += sc->supp.heli_interval_min;
        }

        /* 2) 발화 지점 예약 → 3) 한 단계 진행 */
        ok = ok && schedule_ignition_points(sc, &state, t, dt) &&
             simulate_fire_step(sc, &state, t, dt, &weather, res, opts);

        /* 시각은 더하기를 반복하지 않고 단계 번호로 계산 (실수 오차 누적 방지) */
        step++;
        t_end = (double)step * dt;
        t = t_end;

        /* 4) 출력 간격마다 통계 기록 */
        if (ok && t_end >= next_output - TIME_EPSILON) {
            ok = record_stats(sc, &state, t_end, &weather, res);
            next_output += sc->sim.output_interval_min;
            if (!opts->quiet) {
                log_progress(20 + (int)(60.0 * t_end / sc->sim.duration_min),
                             "확산 %.0f/%.0f분, 피해 %.1f ha, 연소 중 %d칸",
                             t_end, sc->sim.duration_min, res->steps[res->step_count - 1].burned_area_ha,
                             state.burning.count);
            }
        }
        if (opts->map_every_min > 0.0 && t_end >= next_map - TIME_EPSILON) {
            print_map_fire(sc, choose_map_step(&sc->grid, 100), t_end);
            next_map += opts->map_every_min;
        }

        /* 5) 불이 완전히 꺼졌으면 끝 */
        if (state.front.count == 0 && state.burning.count == 0 && !has_pending_ignitions(sc, t)) {
            res->fire_out = 1;
            if (res->steps[res->step_count - 1].time_min < t_end - TIME_EPSILON) {
                ok = ok && record_stats(sc, &state, t_end, &weather, res);
            }
            break;
        }
    }

    res->end_time_min = t;
    res->burned_cells = state.ignited_count;
    res->final_area_ha = state.ignited_count * sc->grid.cell_size_m * sc->grid.cell_size_m / 10000.0;
    fire_state_free(&state);
    return ok;
}
