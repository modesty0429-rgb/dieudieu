/*
 * suppression.c
 * 진화 전략: 방화선을 어디에 만들지(탐욕법), 헬기가 어디에 물을 뿌릴지 정한다.
 *
 * [점화 트리]
 *   확산 시뮬레이션은 셀마다 "누구에게서 불을 받았는지"(parent_index)를 기록한다.
 *   이 관계를 이으면 발화 지점을 뿌리로 하는 나무(트리)가 된다.
 *   어떤 셀의 "하위 가치" = 그 셀 + 그 셀을 거쳐 불이 붙은 모든 셀의 가치 합
 *   → 이 셀을 막으면 (불이 다른 길로 돌아가지 않는다면) 그만큼 피해를 줄일 수 있다는 추정치.
 *   셀의 가치는 1, 등산로 셀은 10 (등산로 보호를 더 중요하게) [가정]
 *
 * [방화선 최적화] optimize_firebreak — 탐욕법(greedy)
 *   매 단계:
 *     1) 현재 상태로 시뮬레이션 → 점화 트리 → 하위 가치 계산
 *     2) 후보: 방화선 완성 시각 이후에 불이 도착하는 셀을 중심으로,
 *        불이 들어온 방향에 수직인 5칸짜리 방화선 조각 (셀 하나만 막으면 불이 옆으로 돌아가므로)
 *     3) 조각 점수(하위 가치 합)가 높은 후보 3개를 실제로 시뮬레이션해 피해가 가장 작은 것을 선택
 *     4) 방화선 칸 수가 K가 되거나 더 이상 줄어들지 않을 때까지 반복
 *   탐욕법은 "지금 가장 좋아 보이는 것"을 고르는 방법이라 전체 최적을 보장하지는 않지만 빠르다.
 *
 * [헬기] plan_helicopter_drops — 시뮬레이션 도중 출동 간격마다 호출
 *   화선의 셀 중 "아직 타지 않은 이웃들의 하위 가치 합"이 가장 큰 곳(= 불이 가장 큰 피해를 향해 가는 곳)에
 *   반경 r칸 살수. 젖은 셀은 효과 시간 동안 불이 붙지도, 번지지도 않는다.
 */
#include <stdlib.h>
#include <math.h>

#include "suppression.h"
#include "fuel_moisture.h"
#include "grid.h"
#include "util.h"
#include "log.h"

/* ================================================================
 * 셀 가치와 점화 트리
 * ================================================================ */

/* 셀별 가치 배열을 만든다: 기본 1, 등산로가 지나는 셀은 TRAIL_CELL_WEIGHT. 성공 1, 실패 0 */
int build_cell_weights(const Scenario *sc, double **weights)
{
    int     total = sc->grid.width * sc->grid.height;
    double *w = (double *)wf_malloc((size_t)total * sizeof(double), "셀 가치");
    int     i, k;

    *weights = NULL;
    if (w == NULL) {
        return 0;
    }
    for (i = 0; i < total; i++) {
        w[i] = 1.0;
    }
    for (i = 0; i < sc->trails.edge_count; i++) {
        const TrailEdge *edge = &sc->trails.edges[i];
        for (k = 0; k < edge->path_count; k++) {
            w[grid_cell_index(&sc->grid, edge->path[k].x, edge->path[k].y)] = TRAIL_CELL_WEIGHT;
        }
    }
    *weights = w;
    return 1;
}

/* 불이 지나간 셀들의 가치 합 (피해 가치) */
double weighted_damage(const Grid *grid, const double *weights)
{
    double total = 0.0;
    int    x, y;

    for (y = 0; y < grid->height; y++) {
        for (x = 0; x < grid->width; x++) {
            if (time_is_set(grid->cells[y][x].arrival_time)) {
                total += weights[grid_cell_index(grid, x, y)];
            }
        }
    }
    return total;
}

/* 정렬용: 셀 번호와 도착 시각 */
typedef struct {
    int    index;
    double arrival;
} ArrivalEntry;

/* 도착 시각이 늦은 것이 앞으로 오도록 비교 (qsort 용) */
static int compare_arrival_desc(const void *a, const void *b)
{
    double ta = ((const ArrivalEntry *)a)->arrival;
    double tb = ((const ArrivalEntry *)b)->arrival;
    if (ta > tb) return -1;
    if (ta < tb) return 1;
    return 0;
}

/*
 * 점화 트리의 하위 가치를 계산한다.
 *   1) 불이 지나간 셀을 도착 시각이 늦은 순서로 정렬 (자식이 부모보다 항상 늦게 불이 붙으므로
 *      늦은 셀부터 처리하면 자식을 모두 더한 뒤에 부모를 처리하게 된다)
 *   2) 각 셀의 값을 부모 셀에 더한다
 * values: width × height 배열 (불이 오지 않은 셀은 0). 성공 1, 실패 0
 */
int compute_subtree_values(const Grid *grid, const double *weights, double *values)
{
    int           total = grid->width * grid->height;
    ArrivalEntry *order = (ArrivalEntry *)wf_malloc((size_t)total * sizeof(ArrivalEntry), "점화 트리 정렬");
    int           count = 0;
    int           i;

    if (order == NULL) {
        return 0;
    }
    for (i = 0; i < total; i++) {
        const Cell *cell = &grid->cells[i / grid->width][i % grid->width];
        values[i] = 0.0;
        if (time_is_set(cell->arrival_time)) {
            values[i] = weights[i];
            order[count].index = i;
            order[count].arrival = cell->arrival_time;
            count++;
        }
    }
    qsort(order, (size_t)count, sizeof(ArrivalEntry), compare_arrival_desc);

    for (i = 0; i < count; i++) {
        int index = order[i].index;
        int parent = grid->cells[index / grid->width][index % grid->width].parent_index;
        if (parent >= 0) {
            values[parent] += values[index];
        }
    }
    free(order);
    return 1;
}

/* ================================================================
 * 방화선 계획
 * ================================================================ */

void firebreak_plan_init(FirebreakPlan *plan)
{
    intarray_init(&plan->cells);
    plan->step_count = 0;
    plan->damage_without = 0.0;
    plan->damage_with = 0.0;
}

void firebreak_plan_free(FirebreakPlan *plan)
{
    intarray_free(&plan->cells);
    plan->step_count = 0;
}

/*
 * 계획의 방화선 셀을 격자에 표시한다.
 * 직전 시뮬레이션에서 탄 셀(연소 중·전소)이어도 방화선으로 바꾼다. (다음 시뮬레이션 시작 때
 * 화재 기록이 지워지므로 상관없음) 물·바위는 그대로 둔다.
 */
void apply_firebreak(Grid *grid, const FirebreakPlan *plan)
{
    int i;
    for (i = 0; i < plan->cells.count; i++) {
        int   index = plan->cells.data[i];
        Cell *cell = &grid->cells[index / grid->width][index % grid->width];
        if (cell->state == CELL_UNBURNED || cell->state == CELL_BURNING || cell->state == CELL_BURNED) {
            cell->state = CELL_FIREBREAK;
        }
    }
}

/* 방화선 표시를 지우고 원래 상태(정상)로 되돌린다. */
void remove_firebreak(Grid *grid, const FirebreakPlan *plan)
{
    int i;
    for (i = 0; i < plan->cells.count; i++) {
        int   index = plan->cells.data[i];
        Cell *cell = &grid->cells[index / grid->width][index % grid->width];
        if (cell->state == CELL_FIREBREAK) {
            cell->state = CELL_UNBURNED;
        }
    }
}

/* 조용히 시뮬레이션 한 번 실행하고 피해 가치를 돌려준다. (방화선은 격자에 이미 표시된 상태) */
static int simulate_damage(Scenario *sc, const double *weights, unsigned int seed, double *damage)
{
    SimOptions opts;
    SimResult  res;
    int        ok;

    sim_options_default(&opts);
    opts.quiet = 1;
    opts.record_events = 0;
    sim_result_init(&res);
    ok = run_fire_simulation(sc, &opts, seed, &res);
    *damage = weighted_damage(&sc->grid, weights);
    sim_result_free(&res);
    return ok;
}

/* 발화 지점 셀이면 1 (발화 지점에는 방화선을 만들 수 없음) */
static int is_ignition_cell(const Scenario *sc, int x, int y)
{
    int i;
    for (i = 0; i < sc->ignition_count; i++) {
        if (sc->ignitions[i].x == x && sc->ignitions[i].y == y) {
            return 1;
        }
    }
    return 0;
}

/* 방화선을 만들 수 있는 셀인가? (탈 수 있고, 방화선 완성 전에는 불이 오지 않는 셀) */
static int cell_can_be_firebreak(const Scenario *sc, int x, int y)
{
    const Cell *cell;

    if (!grid_in_bounds(&sc->grid, x, y) || is_ignition_cell(sc, x, y)) {
        return 0;
    }
    cell = &sc->grid.cells[y][x];
    if (cell->state != CELL_UNBURNED && cell->state != CELL_BURNED && cell->state != CELL_BURNING) {
        return 0;   /* 이미 방화선이거나 물·바위 */
    }
    if (!cell_fuel_is_burnable(sc, cell)) {
        return 0;
    }
    return !time_is_set(cell->arrival_time) || cell->arrival_time >= sc->supp.firebreak_ready_min;
}

static int sign_of(int value)
{
    return (value > 0) - (value < 0);
}

/* 방화선 조각 후보 */
typedef struct {
    int    center_x, center_y;
    int    cells[FIREBREAK_SEGMENT_LENGTH];   /* 가운데부터 바깥쪽 순서 */
    int    cell_count;
    double score;
} SegmentCandidate;

/*
 * (x, y)를 중심으로, 불이 들어온 방향(부모 → 이 셀)에 수직인 5칸 조각을 만든다.
 * 셀 순서는 가운데, +1, -1, +2, -2 (칸 수 예산이 모자라면 가운데부터 쓰기 위해).
 * 만들 수 없으면 0
 */
static int build_segment(const Scenario *sc, const double *values, int x, int y, SegmentCandidate *seg)
{
    static const int OFFSETS[FIREBREAK_SEGMENT_LENGTH] = { 0, 1, -1, 2, -2 };
    const Grid *grid = &sc->grid;
    int         parent = grid->cells[y][x].parent_index;
    int         dx, dy, perp_x, perp_y, k;

    if (parent < 0) {
        return 0;
    }
    /* 불이 들어온 방향 (부모 → 이 셀). 비화처럼 멀리서 온 경우도 방향만 쓴다 */
    dx = sign_of(x - parent % grid->width);
    dy = sign_of(y - parent / grid->width);
    /* 수직 방향: (dx, dy)를 90° 돌림 */
    perp_x = -dy;
    perp_y = dx;

    seg->center_x = x;
    seg->center_y = y;
    seg->cell_count = 0;
    seg->score = 0.0;
    for (k = 0; k < FIREBREAK_SEGMENT_LENGTH; k++) {
        int cx = x + OFFSETS[k] * perp_x;
        int cy = y + OFFSETS[k] * perp_y;
        if (cell_can_be_firebreak(sc, cx, cy)) {
            int index = grid_cell_index(grid, cx, cy);
            seg->cells[seg->cell_count] = index;
            seg->cell_count++;
            seg->score += values[index];
        }
    }
    return seg->cell_count >= 3;   /* 3칸 미만이면 조각 역할을 못함 */
}

/* 점수가 높은 후보를 최대 FIREBREAK_CANDIDATES 개, 서로 가깝지 않게 고른다. 고른 수를 돌려준다. */
static int pick_top_candidates(const Scenario *sc, const double *values, SegmentCandidate *top)
{
    const Grid *grid = &sc->grid;
    int         count = 0;
    int         x, y, i;

    for (y = 0; y < grid->height; y++) {
        for (x = 0; x < grid->width; x++) {
            SegmentCandidate seg;
            int              slot, too_close = 0;

            if (!time_is_set(grid->cells[y][x].arrival_time) || !cell_can_be_firebreak(sc, x, y) ||
                !build_segment(sc, values, x, y, &seg)) {
                continue;
            }
            /* 이미 고른 후보와 가까우면(같은 곳을 두 번 시험하지 않도록) 점수가 높은 쪽만 남긴다 */
            for (i = 0; i < count; i++) {
                if (abs_int(top[i].center_x - x) <= FIREBREAK_SEGMENT_LENGTH &&
                    abs_int(top[i].center_y - y) <= FIREBREAK_SEGMENT_LENGTH) {
                    too_close = 1;
                    if (seg.score > top[i].score) {
                        top[i] = seg;
                    }
                    break;
                }
            }
            if (too_close) {
                continue;
            }
            /* 점수 순서를 유지하며 끼워 넣기 */
            if (count < FIREBREAK_CANDIDATES) {
                count++;
            } else if (seg.score <= top[count - 1].score) {
                continue;
            }
            slot = count - 1;
            while (slot > 0 && top[slot - 1].score < seg.score) {
                top[slot] = top[slot - 1];
                slot--;
            }
            top[slot] = seg;
        }
    }
    /* 가까운 후보를 바꿔 넣는 과정에서 순서가 흐트러졌을 수 있으므로 다시 정렬 (최대 3개) */
    for (i = 1; i < count; i++) {
        int j = i;
        while (j > 0 && top[j - 1].score < top[j].score) {
            SegmentCandidate temp = top[j];
            top[j] = top[j - 1];
            top[j - 1] = temp;
            j--;
        }
    }
    return count;
}

/* 조각의 셀을 (최대 limit칸) 방화선으로 바꾸거나 되돌린다. */
static void set_segment(Grid *grid, const SegmentCandidate *seg, int limit, CellState state)
{
    int k;
    for (k = 0; k < seg->cell_count && k < limit; k++) {
        int index = seg->cells[k];
        grid->cells[index / grid->width][index % grid->width].state = state;
    }
}

/*
 * optimize_firebreak: 방화선 sc->supp.firebreak_cells 칸을 탐욕법으로 배치한다.
 * weights: 셀 가치, seed: 비교용 시뮬레이션의 난수 시드 (모든 후보를 같은 조건에서 비교)
 * 결과는 plan 에 저장되고, 함수가 끝나면 격자의 방화선 표시는 지워진다. 성공 1, 실패 0
 */
int optimize_firebreak(Scenario *sc, const double *weights, unsigned int seed, FirebreakPlan *plan)
{
    Grid   *grid = &sc->grid;
    int     total = grid->width * grid->height;
    int     budget = sc->supp.firebreak_cells;
    double *values = (double *)wf_malloc((size_t)total * sizeof(double), "하위 가치");
    double  current_damage;
    int     ok = 1;

    firebreak_plan_init(plan);
    if (values == NULL) {
        return 0;
    }
    ok = simulate_damage(sc, weights, seed, &current_damage);
    plan->damage_without = current_damage;

    while (ok && plan->cells.count < budget && plan->step_count < MAX_FIREBREAK_STEPS) {
        SegmentCandidate top[FIREBREAK_CANDIDATES];
        int              candidate_count, best = -1, i;
        int              limit = budget - plan->cells.count;
        double           best_damage = current_damage;

        /* 1) 현재 상태(지금까지의 방화선 포함)의 점화 트리 → 하위 가치 */
        if (!compute_subtree_values(grid, weights, values)) {
            ok = 0;
            break;
        }
        /* 2) 점수 상위 후보 고르기 */
        candidate_count = pick_top_candidates(sc, values, top);
        if (candidate_count == 0) {
            break;
        }
        /* 3) 후보마다 실제로 시뮬레이션해 보기 */
        for (i = 0; i < candidate_count && ok; i++) {
            double damage;
            set_segment(grid, &top[i], limit, CELL_FIREBREAK);
            ok = simulate_damage(sc, weights, seed, &damage);
            set_segment(grid, &top[i], limit, CELL_UNBURNED);
            if (damage < best_damage - 1e-9) {
                best_damage = damage;
                best = i;
            }
        }
        if (!ok || best < 0) {
            break;   /* 더 이상 피해가 줄지 않음 */
        }

        /* 4) 가장 좋은 조각을 확정 */
        {
            FirebreakStep *step = &plan->steps[plan->step_count];
            int            added = (top[best].cell_count < limit) ? top[best].cell_count : limit;
            int            k;

            for (k = 0; k < added; k++) {
                if (intarray_push(&plan->cells, top[best].cells[k]) != 0) {
                    ok = 0;
                }
            }
            step->center_x = top[best].center_x;
            step->center_y = top[best].center_y;
            step->cells_added = added;
            step->score = top[best].score;
            step->damage_before = current_damage;
            step->damage_after = best_damage;
            plan->step_count++;
            log_info("방화선 %d단계: (%d, %d) 중심 %d칸 → 피해 가치 %.0f → %.0f",
                     plan->step_count, step->center_x, step->center_y, added, current_damage, best_damage);
        }

        /* 확정한 방화선을 표시하고 다시 시뮬레이션 (다음 단계의 점화 트리를 위해) */
        apply_firebreak(grid, plan);
        ok = ok && simulate_damage(sc, weights, seed, &current_damage);
    }

    plan->damage_with = current_damage;
    remove_firebreak(grid, plan);
    grid_reset_fire_state(grid);
    free(values);
    return ok;
}

/* ================================================================
 * 헬기
 * ================================================================ */

/*
 * 첫 헬기 살수 시각 = 가장 이른 발화 + 경보 가능 시각(발견) + 출동 간격(이륙·이동·급수) [가정]
 */
double first_helicopter_time(const Scenario *sc)
{
    double first = sc->ignitions[0].time_min;
    int    i;

    for (i = 1; i < sc->ignition_count; i++) {
        if (sc->ignitions[i].time_min < first) {
            first = sc->ignitions[i].time_min;
        }
    }
    return first + sc->alert.notify_delay_min + sc->supp.heli_interval_min;
}

/* (x, y) 중심 반경 radius칸 안의 셀을 until 시각까지 젖게 한다. */
static void apply_water_drop(Grid *grid, int x, int y, int radius, double until)
{
    int dx, dy;
    for (dy = -radius; dy <= radius; dy++) {
        for (dx = -radius; dx <= radius; dx++) {
            int nx = x + dx;
            int ny = y + dy;
            if (dx * dx + dy * dy <= radius * radius && grid_in_bounds(grid, nx, ny) &&
                grid->cells[ny][nx].wet_until < until) {
                grid->cells[ny][nx].wet_until = until;
            }
        }
    }
}

/* 살수 기록을 결과에 추가한다. */
static int push_drop(SimResult *res, double t, int x, int y)
{
    if (res->drop_count == res->drop_capacity) {
        int       new_capacity = (res->drop_capacity == 0) ? 16 : res->drop_capacity * 2;
        HeliDrop *grown = (HeliDrop *)realloc(res->drops, (size_t)new_capacity * sizeof(HeliDrop));
        if (grown == NULL) {
            log_error("메모리 부족: 헬기 살수 기록");
            return 0;
        }
        res->drops = grown;
        res->drop_capacity = new_capacity;
    }
    res->drops[res->drop_count].time_min = t;
    res->drops[res->drop_count].x = x;
    res->drops[res->drop_count].y = y;
    res->drop_count++;
    return 1;
}

/* 화선 셀 하나의 살수 점수 = 아직 타지 않은 이웃들의 가치 합 (불이 향하는 곳이 중요할수록 큼) */
static double drop_score(const Scenario *sc, int x, int y, double t, const double *guide)
{
    double score = 0.0;
    int    dir;

    for (dir = 0; dir < 8; dir++) {
        int nx = x + grid_neighbor_dx(dir);
        int ny = y + grid_neighbor_dy(dir);
        const Cell *n;
        if (!grid_in_bounds(&sc->grid, nx, ny)) {
            continue;
        }
        n = &sc->grid.cells[ny][nx];
        if (cell_is_receptive(sc, n) && n->wet_until <= t) {
            score += 1.0 + ((guide != NULL) ? guide[grid_cell_index(&sc->grid, nx, ny)] : 0.0);
        }
    }
    return score;
}

/*
 * plan_helicopter_drops: 시각 t 에 헬기 M대의 살수 지점을 정하고 물을 뿌린다.
 * 헬기마다 화선에서 점수가 가장 높은 셀을 고르되, 앞 헬기와 겹치지 않게 떨어진 곳을 고른다.
 * guide: 기준 시뮬레이션(대응 없음)의 점화 트리 하위 가치 — "여기로 불이 가면 피해가 크다"
 * 성공 1, 메모리 부족 0
 */
int plan_helicopter_drops(Scenario *sc, FireState *state, double t, const double *guide, SimResult *res)
{
    int    radius = sc->supp.heli_radius_cells;
    int    spacing = 2 * radius + 1;
    double until = t + sc->supp.heli_effect_min;
    int    first_drop = res->drop_count;
    int    h, i, k;

    for (h = 0; h < sc->supp.helicopters; h++) {
        int    best_x = -1, best_y = -1;
        double best_score = 0.0;

        for (i = 0; i < state->front.count; i++) {
            int    index = state->front.data[i];
            int    x = index % sc->grid.width;
            int    y = index / sc->grid.width;
            int    too_close = 0;
            double score;

            if (sc->grid.cells[y][x].wet_until > t) {
                continue;   /* 이미 젖어 있음 */
            }
            for (k = first_drop; k < res->drop_count; k++) {
                if (abs_int(res->drops[k].x - x) < spacing && abs_int(res->drops[k].y - y) < spacing) {
                    too_close = 1;
                    break;
                }
            }
            if (too_close) {
                continue;
            }
            score = drop_score(sc, x, y, t, guide);
            if (score > best_score) {
                best_score = score;
                best_x = x;
                best_y = y;
            }
        }
        if (best_x < 0) {
            break;   /* 더 뿌릴 곳이 없음 */
        }
        apply_water_drop(&sc->grid, best_x, best_y, radius, until);
        if (!push_drop(res, t, best_x, best_y)) {
            return 0;
        }
    }
    return 1;
}
