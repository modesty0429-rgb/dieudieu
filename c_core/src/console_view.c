/*
 * console_view.c
 * 콘솔에 지도와 시나리오 요약을 글자로 출력한다.
 *
 * 200 x 200 격자를 그대로 찍으면 콘솔 폭을 넘기 때문에 step 칸마다 한 칸씩 골라 출력한다.
 * (step = 2 이면 가로·세로 2칸마다 1칸 → 100 x 100 글자)
 *
 * 출력할 글자를 먼저 2차원 문자 배열(canvas)에 그린 뒤 한 번에 출력한다.
 *   1) 바탕: 연료 기호 또는 고도 기호
 *   2) 그 위에: 등산로(+), 노드(P/S/T/J/V), 등산객(H), 발화 지점(*)
 */
#include <stdio.h>
#include <stdlib.h>

#include "console_view.h"
#include "trail_io.h"
#include "evac_route.h"
#include "grid.h"
#include "util.h"
#include "log.h"

/* 고도를 10단계 밝기로 표현하는 글자 (낮음 → 높음) */
static const char ELEVATION_SYMBOLS[] = " .:-=+*#%@";
#define ELEVATION_LEVELS 10

/* ================================================================
 * 기호 정하기
 * ================================================================ */

/* 연료 코드를 지도 기호 한 글자로 바꾼다. */
static char fuel_symbol(int fuel_code)
{
    switch (fuel_code) {
    case FUEL_CODE_NONE:      return ' ';
    case FUEL_CODE_GRASS:     return '"';
    case FUEL_CODE_SHRUB:     return ':';
    case FUEL_CODE_CONIFER:   return '^';
    case FUEL_CODE_BROADLEAF: return 'o';
    case FUEL_CODE_MIXED:     return '%';
    case FUEL_CODE_ROAD:      return '=';
    case FUEL_CODE_WATER:     return '~';
    case FUEL_CODE_ROCK:      return '#';
    default:                  return '?';
    }
}

/* 연료 코드의 한국어 이름 (2단계부터는 fuel_models.csv의 이름을 함께 쓴다) */
static const char *fuel_korean_name(int fuel_code)
{
    switch (fuel_code) {
    case FUEL_CODE_NONE:      return "연료 없음";
    case FUEL_CODE_GRASS:     return "초지";
    case FUEL_CODE_SHRUB:     return "관목";
    case FUEL_CODE_CONIFER:   return "침엽수";
    case FUEL_CODE_BROADLEAF: return "활엽수";
    case FUEL_CODE_MIXED:     return "혼효림";
    case FUEL_CODE_ROAD:      return "도로";
    case FUEL_CODE_WATER:     return "물";
    case FUEL_CODE_ROCK:      return "바위·나지";
    default:                  return "기타";
    }
}

/* 노드 종류를 지도 기호로 바꾼다. */
static char node_symbol(NodeType type)
{
    switch (type) {
    case NODE_PARKING:  return 'P';
    case NODE_SHELTER:  return 'S';
    case NODE_SUMMIT:   return 'T';
    case NODE_JUNCTION: return 'J';
    case NODE_POINT:    return 'V';
    default:            return '?';
    }
}

/* ================================================================
 * 문자 캔버스 (2차원 문자 배열)
 * ================================================================ */

/* rows × cols 크기의 2차원 문자 배열을 만든다. 각 행 끝에 '\0'을 넣어 문자열로 출력할 수 있게 한다. */
static char **create_canvas(int rows, int cols)
{
    char **canvas;
    int    r, c;

    canvas = (char **)wf_calloc((size_t)rows, sizeof(char *), "지도 출력 행 배열");
    if (canvas == NULL) {
        return NULL;
    }
    for (r = 0; r < rows; r++) {
        canvas[r] = (char *)wf_malloc((size_t)cols + 1, "지도 출력 행");
        if (canvas[r] == NULL) {
            int k;
            for (k = 0; k < r; k++) {
                free(canvas[k]);
            }
            free(canvas);
            return NULL;
        }
        for (c = 0; c < cols; c++) {
            canvas[r][c] = ' ';
        }
        canvas[r][cols] = '\0';
    }
    return canvas;
}

static void free_canvas(char **canvas, int rows)
{
    int r;
    if (canvas == NULL) {
        return;
    }
    for (r = 0; r < rows; r++) {
        free(canvas[r]);
    }
    free(canvas);
}

/* 격자 좌표 (x, y)에 해당하는 캔버스 칸에 글자를 쓴다. */
static void put_symbol(char **canvas, int rows, int cols, int step, int x, int y, char symbol)
{
    int r = y / step;
    int c = x / step;
    if (r >= 0 && r < rows && c >= 0 && c < cols) {
        canvas[r][c] = symbol;
    }
}

/*
 * 바탕 위에 등산로·노드·등산객·발화 지점을 겹쳐 그린다.
 * 나중에 그린 것이 위에 보이므로 중요한 것을 나중에 그린다.
 */
static void draw_overlays(const Scenario *sc, char **canvas, int rows, int cols, int step)
{
    const TrailGraph *g = &sc->trails;
    int i, k;

    /* 등산로 경로 */
    for (i = 0; i < g->edge_count; i++) {
        for (k = 0; k < g->edges[i].path_count; k++) {
            put_symbol(canvas, rows, cols, step, g->edges[i].path[k].x, g->edges[i].path[k].y, '+');
        }
    }
    /* 노드 */
    for (i = 0; i < g->node_count; i++) {
        put_symbol(canvas, rows, cols, step, g->nodes[i].x, g->nodes[i].y, node_symbol(g->nodes[i].type));
    }
    /* 등산객 */
    for (i = 0; i < sc->hiker_count; i++) {
        put_symbol(canvas, rows, cols, step, round_to_int(sc->hikers[i].pos_x),
                   round_to_int(sc->hikers[i].pos_y), 'H');
    }
    /* 발화 지점 */
    for (i = 0; i < sc->ignition_count; i++) {
        put_symbol(canvas, rows, cols, step, sc->ignitions[i].x, sc->ignitions[i].y, '*');
    }
}

/* 캔버스를 눈금과 함께 출력한다. 왼쪽 숫자는 y, 위쪽 숫자는 x (실제 격자 좌표) */
static void print_canvas(char **canvas, int rows, int cols, int step)
{
    int r, c;

    /* 위쪽 눈금: 10글자마다 x 좌표 */
    printf("      ");
    for (c = 0; c < cols; c += 10) {
        printf("%-10d", c * step);
    }
    printf("\n      ");
    for (c = 0; c < cols; c++) {
        putchar((c % 10 == 0) ? '|' : '-');
    }
    printf("\n");

    for (r = 0; r < rows; r++) {
        printf("%5d %s\n", r * step, canvas[r]);
    }
    fflush(stdout);
}

/* 가로 칸 수가 max_columns 이하가 되도록 출력 간격(step)을 정한다. */
int choose_map_step(const Grid *grid, int max_columns)
{
    int step;
    if (max_columns <= 0) {
        return 1;
    }
    step = (grid->width + max_columns - 1) / max_columns;   /* 올림 나눗셈 */
    return (step < 1) ? 1 : step;
}

/* ================================================================
 * 지도 출력
 * ================================================================ */

/* 연료 지도를 출력한다. step: 몇 칸마다 한 글자를 찍을지 */
void print_map_fuel(const Scenario *sc, int step)
{
    const Grid *grid = &sc->grid;
    int         rows = (grid->height + step - 1) / step;
    int         cols = (grid->width + step - 1) / step;
    char      **canvas = create_canvas(rows, cols);
    int         r, c;

    if (canvas == NULL) {
        return;
    }
    for (r = 0; r < rows; r++) {
        for (c = 0; c < cols; c++) {
            canvas[r][c] = fuel_symbol(grid->cells[r * step][c * step].fuel_code);
        }
    }
    draw_overlays(sc, canvas, rows, cols, step);

    printf("\n=== 연료 지도 (%d칸마다 1글자, 위쪽이 북쪽) ===\n", step);
    print_canvas(canvas, rows, cols, step);
    printf("범례: \"초지  :관목  ^침엽수  o활엽수  %%혼효림  =도로  ~물  #바위\n");
    printf("      +등산로  P주차장  S대피소  T정상  J갈림길  V기타지점  H등산객  *발화지점\n");
    fflush(stdout);
    free_canvas(canvas, rows);
}

/* 고도 지도를 10단계 글자로 출력한다. (어두운 글자 = 낮음, 진한 글자 = 높음) */
void print_map_elevation(const Scenario *sc, int step)
{
    const Grid *grid = &sc->grid;
    int         rows = (grid->height + step - 1) / step;
    int         cols = (grid->width + step - 1) / step;
    char      **canvas;
    double      min_e = grid->cells[0][0].elevation;
    double      max_e = min_e;
    double      range;
    int         x, y, r, c;

    for (y = 0; y < grid->height; y++) {
        for (x = 0; x < grid->width; x++) {
            double e = grid->cells[y][x].elevation;
            if (e < min_e) min_e = e;
            if (e > max_e) max_e = e;
        }
    }
    range = (max_e - min_e > 1e-9) ? (max_e - min_e) : 1.0;

    canvas = create_canvas(rows, cols);
    if (canvas == NULL) {
        return;
    }
    for (r = 0; r < rows; r++) {
        for (c = 0; c < cols; c++) {
            double ratio = (grid->cells[r * step][c * step].elevation - min_e) / range;
            int    level = (int)(ratio * ELEVATION_LEVELS);
            if (level >= ELEVATION_LEVELS) {
                level = ELEVATION_LEVELS - 1;
            }
            canvas[r][c] = ELEVATION_SYMBOLS[level];
        }
    }
    /* 고도 지도에는 위치 파악용으로 노드와 발화 지점만 표시 */
    for (r = 0; r < sc->trails.node_count; r++) {
        put_symbol(canvas, rows, cols, step, sc->trails.nodes[r].x, sc->trails.nodes[r].y,
                   node_symbol(sc->trails.nodes[r].type));
    }
    for (r = 0; r < sc->ignition_count; r++) {
        put_symbol(canvas, rows, cols, step, sc->ignitions[r].x, sc->ignitions[r].y, '*');
    }

    printf("\n=== 고도 지도 (%.0f m ~ %.0f m, %d칸마다 1글자) ===\n", min_e, max_e, step);
    print_canvas(canvas, rows, cols, step);
    printf("범례: 낮음 [%s] 높음   (P S T J V = 등산로 노드, * = 발화 지점)\n", ELEVATION_SYMBOLS);
    fflush(stdout);
    free_canvas(canvas, rows);
}

/*
 * 화재 지도를 출력한다. time_min 시각 기준으로
 *   불이 붙은 적 없는 셀 → 연료 기호, 연소 중 → '@', 전소 → 'x'
 * (시뮬레이션이 끝난 뒤에도 도착·전소 시각으로 아무 시각의 모습을 다시 그릴 수 있다)
 */
void print_map_fire(const Scenario *sc, int step, double time_min)
{
    const Grid *grid = &sc->grid;
    int         rows = (grid->height + step - 1) / step;
    int         cols = (grid->width + step - 1) / step;
    char      **canvas = create_canvas(rows, cols);
    int         r, c, i;

    if (canvas == NULL) {
        return;
    }
    for (r = 0; r < rows; r++) {
        for (c = 0; c < cols; c++) {
            const Cell *cell = &grid->cells[r * step][c * step];
            char        symbol = fuel_symbol(cell->fuel_code);

            if (cell->state == CELL_FIREBREAK) {
                symbol = '|';
            } else if (time_is_set(cell->arrival_time) && cell->arrival_time <= time_min) {
                int burned_out = time_is_set(cell->burnout_time) && cell->burnout_time <= time_min;
                symbol = burned_out ? 'x' : '@';
            }
            canvas[r][c] = symbol;
        }
    }
    for (i = 0; i < sc->trails.node_count; i++) {
        put_symbol(canvas, rows, cols, step, sc->trails.nodes[i].x, sc->trails.nodes[i].y,
                   node_symbol(sc->trails.nodes[i].type));
    }

    printf("\n=== 화재 지도: 발화 후 %.0f분 (%d칸마다 1글자) ===\n", time_min, step);
    print_canvas(canvas, rows, cols, step);
    printf("범례: @연소 중  x전소  |방화선  (나머지는 연료 기호)  P S T J V 등산로 노드\n");
    fflush(stdout);
    free_canvas(canvas, rows);
}

/* 시간별 통계를 every_min 분 간격으로 표로 출력한다. */
void print_sim_statistics(const SimResult *res, double every_min)
{
    double next = 0.0;
    int    i;

    printf("\n================ 시간별 확산 통계 ================\n");
    printf("  시각 | 연소 중 | 피해 면적 | 최대 속도 | 비화 | 풍속  풍향 | 습도 | 연료수분\n");
    printf(" (분)  |  (칸)   |   (ha)    |  (m/분)   | (개) | (m/s)  (°) | (%%)  |   (%%)\n");
    printf("-------+---------+-----------+-----------+------+------------+------+---------\n");
    for (i = 0; i < res->step_count; i++) {
        const StepStats *s = &res->steps[i];
        if (s->time_min + 1e-9 < next && i != res->step_count - 1) {
            continue;
        }
        printf(" %5.0f | %7d | %9.1f | %9.2f | %4d | %5.1f %4.0f | %4.0f | %7.1f\n",
               s->time_min, s->burning_cells, s->burned_area_ha, s->max_spread_rate_m_min,
               s->spot_fires, s->weather.wind_speed_ms, s->weather.wind_dir_deg,
               s->weather.rh_pct, s->dead_moisture_pct);
        next = s->time_min + every_min;
    }
    printf("-------------------------------------------------\n");
    printf(" 최종 피해 면적 %.1f ha (%d칸), 최대 확산 속도 %.2f m/분, 비화 %d회, %s\n",
           res->final_area_ha, res->burned_cells, res->max_spread_rate, res->spot_fire_count,
           (res->burned_cells == 0) ? "시간 안에 불이 붙지 않음"
           : res->fire_out ? "시간 안에 불이 꺼짐 (자연 소멸)" : "시뮬레이션 종료 시점에도 연소 중");
    fflush(stdout);
}

/* ================================================================
 * 요약 출력
 * ================================================================ */

/* 시나리오 설정을 보기 좋게 출력한다. */
void print_scenario_summary(const Scenario *sc)
{
    int i;

    printf("\n================ 시나리오 요약 ================\n");
    printf(" 이름        : %s\n", sc->name);
    printf(" 설정 파일   : %s\n", sc->scenario_path);
    printf(" 시작 시각   : %04d-%02d-%02d %02d:%02d\n", sc->start_time.year, sc->start_time.month,
           sc->start_time.day, sc->start_time.hour, sc->start_time.minute);
    printf(" 진행 시간   : %.0f분 (한 단계 %.1f분, 저장 간격 %.0f분)\n",
           sc->sim.duration_min, sc->sim.time_step_min, sc->sim.output_interval_min);
    printf(" 지도        : %d x %d 칸, 칸 크기 %.1f m\n", sc->grid.width, sc->grid.height, sc->grid.cell_size_m);
    if (sc->weather_mode == WEATHER_FIXED) {
        printf(" 기상        : 고정값 — 기온 %.1f°C, 습도 %.0f%%, 풍속 %.1f m/s, 풍향 %.0f°\n",
               sc->fixed_weather.temp_c, sc->fixed_weather.rh_pct,
               sc->fixed_weather.wind_speed_ms, sc->fixed_weather.wind_dir_deg);
    } else {
        printf(" 기상        : 파일 %s\n", sc->weather_file);
    }
    for (i = 0; i < sc->ignition_count; i++) {
        printf(" 발화 지점 %d : (%d, %d), %.0f분에 발화\n", i + 1,
               sc->ignitions[i].x, sc->ignitions[i].y, sc->ignitions[i].time_min);
    }
    printf(" 비화        : %s (기본 확률 %g, 평균 거리 %.0f m), 난수 시드 %u\n",
           sc->sim.spotting_enabled ? "사용" : "사용 안 함",
           sc->sim.spot_base_prob, sc->sim.spot_mean_dist_m, sc->sim.random_seed);
    printf(" 경보 기준   : 주의 < %.0f분, 대피 준비 < %.0f분, 즉시 대피 < %.0f분 (반경 %.0f m)\n",
           sc->alert.caution_min, sc->alert.prepare_min, sc->alert.immediate_min, sc->alert.check_radius_m);
    printf(" 진화 자원   : 방화선 %d칸(%.0f분 완성), 헬기 %d대(반경 %d칸, %.0f분 간격)\n",
           sc->supp.firebreak_cells, sc->supp.firebreak_ready_min, sc->supp.helicopters,
           sc->supp.heli_radius_cells, sc->supp.heli_interval_min);
    printf(" 몬테카를로  : %d회 반복\n", sc->mc.runs);
    printf(" 결과 폴더   : %s\n", sc->output_dir);
    printf("===============================================\n");
    fflush(stdout);
}

/* 지형 통계(고도·경사), 연료 구성, 등산로·등산객 목록을 출력한다. */
void print_terrain_statistics(const Scenario *sc)
{
    const Grid *grid = &sc->grid;
    int         fuel_counts[WF_MAX_FUELS] = { 0 };
    double      min_e = 1e30, max_e = -1e30, sum_e = 0.0;
    double      max_slope = 0.0, sum_slope = 0.0;
    double      cell_area_ha = grid->cell_size_m * grid->cell_size_m / 10000.0;
    int         total = grid->width * grid->height;
    int         x, y, i;

    for (y = 0; y < grid->height; y++) {
        for (x = 0; x < grid->width; x++) {
            const Cell *cell = &grid->cells[y][x];
            if (cell->elevation < min_e) min_e = cell->elevation;
            if (cell->elevation > max_e) max_e = cell->elevation;
            if (cell->slope_deg > max_slope) max_slope = cell->slope_deg;
            sum_e += cell->elevation;
            sum_slope += cell->slope_deg;
            fuel_counts[cell->fuel_code]++;
        }
    }

    printf("\n================ 지형 통계 ================\n");
    printf(" 고도 : 최저 %.0f m, 최고 %.0f m, 평균 %.0f m\n", min_e, max_e, sum_e / total);
    printf(" 경사 : 평균 %.1f°, 최대 %.1f°\n", sum_slope / total, max_slope);
    printf(" 연료 구성:\n");
    for (i = 0; i < WF_MAX_FUELS; i++) {
        if (fuel_counts[i] > 0) {
            printf("   [%c] 코드 %2d %-10s : %6d칸 (%7.1f ha, %5.1f%%)\n", fuel_symbol(i), i,
                   fuel_korean_name(i), fuel_counts[i], fuel_counts[i] * cell_area_ha,
                   100.0 * fuel_counts[i] / total);
        }
    }

    if (sc->trails.node_count > 0) {
        printf("\n 등산로 노드 %d개:\n", sc->trails.node_count);
        for (i = 0; i < sc->trails.node_count; i++) {
            const TrailNode *n = &sc->trails.nodes[i];
            printf("   [%c] %2d %-16s %-6s (%3d, %3d) 고도 %4.0f m%s\n", node_symbol(n->type), n->id,
                   n->name, node_type_name(n->type), n->x, n->y, grid->cells[n->y][n->x].elevation,
                   n->is_exit ? "  ← 대피 목적지" : "");
        }
        printf("\n 등산로 간선 %d개:\n", sc->trails.edge_count);
        for (i = 0; i < sc->trails.edge_count; i++) {
            const TrailEdge *e = &sc->trails.edges[i];
            printf("   %2d → %2d : 길이 %6.0f m, 오르막 %4.0f m, 내리막 %4.0f m (셀 %d개)\n",
                   sc->trails.nodes[e->from].id, sc->trails.nodes[e->to].id,
                   e->length_m, e->climb_m, e->descent_m, e->path_count);
        }
    }
    if (sc->hiker_count > 0) {
        printf("\n 등산객 %d팀:\n", sc->hiker_count);
        for (i = 0; i < sc->hiker_count; i++) {
            const Hiker *h = &sc->hikers[i];
            printf("   H%d %-12s : %2d명, 보행 %.1f km/h, 현재 위치 '%s'\n", h->id, h->name,
                   h->group_size, h->speed_kmh, sc->trails.nodes[h->start_node].name);
        }
    }
    printf("===========================================\n");
    fflush(stdout);
}

/* ================================================================
 * 대피 결과 표
 * ================================================================ */

/* 경로를 "계곡대피소 → 솔밭삼거리 → 남문주차장" 처럼 출력한다. */
static void print_route_names(const Scenario *sc, const Route *route)
{
    int i;
    for (i = 0; i < route->node_count; i++) {
        printf("%s%s", (i > 0) ? " → " : "", sc->trails.nodes[route->nodes[i]].name);
    }
}

/* 등산객별 대피 결과를 출력한다. */
void print_evacuation_table(const Scenario *sc, const EvacSummary *summary)
{
    int i;

    printf("\n================ 등산객 대피 안내 ================\n");
    printf(" 경보 기준: 주의 < %.0f분, 대피준비 < %.0f분(이때 출발), 즉시대피 < %.0f분, 판정 반경 %.0f m\n",
           sc->alert.caution_min, sc->alert.prepare_min, sc->alert.immediate_min, sc->alert.check_radius_m);
    printf(" 경보 가능 시각: 발화 후 %.0f분, 경로 위험 반경 %.0f m, 충분한 여유 %.0f분\n",
           sc->alert.notify_delay_min, sc->alert.danger_radius_m, sc->alert.safe_margin_min);
    for (i = 0; i < sc->hiker_count; i++) {
        const Hiker *h = &sc->hikers[i];

        printf("\n [H%d] %s (%d명, %.1f km/h) — 시작: %s\n", h->id, h->name, h->group_size, h->speed_kmh,
               sc->trails.nodes[h->start_node].name);
        if (!time_is_set(h->depart_time_min)) {
            printf("    결과: 주변에 불이 오지 않음 → 대피 불필요\n");
        } else {
            printf("    출발: %.0f분, 결과: %s", h->depart_time_min, hiker_status_korean(h->status));
            if (time_is_set(h->finish_time_min)) {
                printf(" (%.0f분)", h->finish_time_min);
            }
            printf("%s\n", hiker_is_at_risk(sc, h) ? "  ⚠ 위험" : "");
        }
        if (h->route.found) {
            printf("    경로: ");
            print_route_names(sc, &h->route);
            printf("\n    소요 %.0f분, 최소 안전 여유 ", h->route.travel_time_min);
            if (margin_is_unlimited(h->route.min_margin_min)) {
                printf("제한 없음 (경로 근처에 불이 오지 않음)\n");
            } else {
                printf("%.0f분\n", h->route.min_margin_min);
            }
        } else {
            printf("    경로: 안전한 대피 목적지까지 갈 수 있는 길이 없음 → 구조 요청\n");
        }
    }
    printf("\n 요약: %d팀 %d명 중 대피 %d팀, 대피 완료 %d팀, 고립 %d팀, 위험 %d팀 %d명\n",
           summary->hikers, summary->people, summary->evacuated, summary->safe, summary->trapped,
           summary->at_risk_hikers, summary->at_risk_people);
    printf("=================================================\n");
    fflush(stdout);
}
