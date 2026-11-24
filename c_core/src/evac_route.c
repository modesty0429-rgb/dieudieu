/*
 * evac_route.c
 * 불이 다가오는 상황에서 등산로 그래프 위의 "가장 안전한 대피 경로"를 찾는다.
 *
 * [안전 여유]
 *   어떤 지점의 안전 여유 = (그 지점 근처에 불이 오는 시각) − (내가 그 지점을 지나는 시각)
 *   여유가 클수록 안전하고, 음수면 불이 먼저 와 있다는 뜻이다.
 *   경로의 안전 여유 = 경로 위 모든 지점 중 가장 작은 여유 (가장 위험한 순간이 경로의 안전도를 정함)
 *
 * [탐색 방법] — 다익스트라 알고리즘의 변형 (우선순위 큐 직접 구현: pqueue.c)
 *   보통의 다익스트라는 "거리 합"이 가장 작은 길을 찾는다.
 *   여기서는 각 노드에 (경로 최소 여유, 도착 시각) 두 값을 기록하고
 *     1순위: 최소 여유가 큰 길
 *     2순위: 여유가 같으면 일찍 도착하는 길
 *   을 고른다. 다만 여유가 safe_margin_min(기본 30분) 이상이면 모두 "충분히 안전"하다고 보고
 *   그때부터는 빨리 도착하는 길을 고른다. (여유 1분을 더 얻으려고 크게 돌아가지 않도록)
 *
 * [한계]
 *   도착 시각이 경로에 따라 달라지므로 이 방법이 항상 수학적 최적을 보장하지는 않는다.
 *   (가상 등산로 크기에서는 결과를 눈으로 검증할 수 있다 — docs/model.md 참고)
 *
 * 출처: Dijkstra, E.W. (1959). A note on two problems in connexion with graphs.
 *       Numerische Mathematik 1. (최대 병목 경로 변형은 일반적인 그래프 알고리즘 응용)
 */
#include <stdlib.h>
#include <math.h>

#include "evac_route.h"
#include "hiker.h"
#include "pqueue.h"
#include "grid.h"
#include "util.h"
#include "log.h"

#define MARGIN_EPS     1e-6
#define NO_LABEL_TIME  1.0e18   /* 아직 도착하지 못한 노드의 시각 */

/* ================================================================
 * 위험 지도
 * ================================================================ */

/*
 * 위험 지도를 만든다: 불이 지나간 셀마다 반경 radius_m 안의 모든 셀에
 * "이 시각에 근처까지 불이 온다"고 기록한다(더 이른 시각이 남음).
 * 불이 지나간 셀에서 바깥으로 퍼뜨리므로, 모든 셀에서 주변을 검사하는 것보다 훨씬 빠르다.
 * 성공 1, 실패 0
 */
int build_danger_map(const Grid *grid, double radius_m, DangerMap *map)
{
    double radius_ceil = ceil(radius_m / grid->cell_size_m);
    int    radius_cells = (int)radius_ceil;
    double radius_sq = (radius_m / grid->cell_size_m) * (radius_m / grid->cell_size_m) + 1e-9;
    int    total = grid->width * grid->height;
    int    x, y, i;

    map->width = grid->width;
    map->height = grid->height;
    map->radius_m = radius_m;
    map->time = (double *)wf_malloc((size_t)total * sizeof(double), "위험 지도");
    if (map->time == NULL) {
        return 0;
    }
    for (i = 0; i < total; i++) {
        map->time[i] = DANGER_NONE;
    }

    for (y = 0; y < grid->height; y++) {
        for (x = 0; x < grid->width; x++) {
            double arrival = grid->cells[y][x].arrival_time;
            int    dx, dy;

            if (!time_is_set(arrival)) {
                continue;
            }
            /* 원 안의 셀들에 도착 시각 퍼뜨리기 */
            for (dy = -radius_cells; dy <= radius_cells; dy++) {
                for (dx = -radius_cells; dx <= radius_cells; dx++) {
                    int nx = x + dx;
                    int ny = y + dy;
                    if ((double)(dx * dx + dy * dy) > radius_sq || !grid_in_bounds(grid, nx, ny)) {
                        continue;
                    }
                    if (arrival < map->time[ny * map->width + nx]) {
                        map->time[ny * map->width + nx] = arrival;
                    }
                }
            }
        }
    }
    return 1;
}

double danger_time_at(const DangerMap *map, int x, int y)
{
    return map->time[y * map->width + x];
}

void free_danger_map(DangerMap *map)
{
    free(map->time);
    map->time = NULL;
}

/* 여유 값이 "불이 오지 않음"을 뜻할 만큼 크면 1 */
int margin_is_unlimited(double margin_min)
{
    return margin_min > DANGER_NONE / 2.0;
}

/* ================================================================
 * 경로 구조체
 * ================================================================ */

void route_init(Route *route)
{
    route->nodes = NULL;
    route->edges = NULL;
    route->node_count = 0;
    route->exit_node = -1;
    route->travel_time_min = 0.0;
    route->min_margin_min = 0.0;
    route->found = 0;
}

void route_free(Route *route)
{
    free(route->nodes);
    free(route->edges);
    route_init(route);
}

/*
 * 이 노드가 대피 목적지인가?
 *   목적지는 산 아래의 등산로 입구(주차장·들머리)뿐이다. 도착하면 차나 도로로 산불 지역을 벗어날 수 있다.
 *   산속 대피소는 불이 언제 올지 시뮬레이션 시간 뒤까지는 알 수 없으므로 목적지로 쓰지 않고 지나가기만 한다.
 *   목적지에 도착하는 순간까지의 안전(경로 위 모든 칸의 여유)은 find_safest_route 가 따진다.
 */
int node_is_safe_exit(const Scenario *sc, const DangerMap *danger, int node)
{
    (void)danger;
    return sc->trails.nodes[node].type == NODE_PARKING;
}

/* ================================================================
 * 간선 하나 걷기
 * ================================================================ */

/*
 * from_node 에서 출발해 edge_index 간선을 끝까지 걸을 때
 * 도착 시각(end_time)과 간선 위 최소 안전 여유(min_margin)를 계산한다.
 * 간선의 셀 목록은 edge.from → edge.to 순서이므로, 반대 방향이면 거꾸로 읽는다.
 */
static void walk_edge(const Scenario *sc, const DangerMap *danger, int edge_index, int from_node,
                      double start_time, double speed_kmh, double *end_time, double *min_margin)
{
    const TrailEdge *edge = &sc->trails.edges[edge_index];
    int              forward = (edge->from == from_node);
    double           t = start_time;
    double           margin = DANGER_NONE;
    int              i;

    for (i = 0; i < edge->path_count; i++) {
        GridPoint cur = forward ? edge->path[i] : edge->path[edge->path_count - 1 - i];
        double    cell_margin;

        if (i > 0) {
            GridPoint prev = forward ? edge->path[i - 1] : edge->path[edge->path_count - i];
            t += step_time_min(sc, prev, cur, speed_kmh, t);
        }
        cell_margin = danger_time_at(danger, cur.x, cur.y) - t;
        if (cell_margin < margin) {
            margin = cell_margin;
        }
    }
    *end_time = t;
    *min_margin = margin;
}

/* ================================================================
 * 가장 안전한 경로 찾기
 * ================================================================ */

/* 비교용 여유: safe_margin_min 이상은 모두 같은 값으로 본다 */
static double capped_margin(const Scenario *sc, double margin)
{
    return (margin > sc->alert.safe_margin_min) ? sc->alert.safe_margin_min : margin;
}

/* (여유 a, 시각 a)가 (여유 b, 시각 b)보다 좋은 경로이면 1 */
static int label_is_better(const Scenario *sc, double margin_a, double time_a, double margin_b, double time_b)
{
    double ca = capped_margin(sc, margin_a);
    double cb = capped_margin(sc, margin_b);

    if (ca > cb + MARGIN_EPS) {
        return 1;
    }
    if (ca < cb - MARGIN_EPS) {
        return 0;
    }
    return time_a < time_b - MARGIN_EPS;
}

/* prev_node/prev_edge 를 거꾸로 따라가 경로(노드·간선 목록)를 만든다. */
static int build_route_from_labels(const int *prev_node, const int *prev_edge, int exit_node, Route *route)
{
    int count = 1;
    int node, i;

    for (node = exit_node; prev_node[node] >= 0; node = prev_node[node]) {
        count++;
    }
    route->nodes = (int *)wf_malloc((size_t)count * sizeof(int), "대피 경로 노드");
    route->edges = (int *)wf_malloc((size_t)count * sizeof(int), "대피 경로 간선");
    if (route->nodes == NULL || route->edges == NULL) {
        return 0;
    }
    /* 끝에서부터 채우면 출발 → 도착 순서가 된다 */
    node = exit_node;
    for (i = count - 1; i >= 0; i--) {
        route->nodes[i] = node;
        if (i > 0) {
            route->edges[i - 1] = prev_edge[node];
        }
        node = prev_node[node];
    }
    route->node_count = count;
    return 1;
}

/*
 * 노드별 탐색 기록 (다익스트라의 "라벨")
 * 배열 5개를 하나로 묶어 함수에 넘기기 쉽게 했다. 모두 node_count 크기의 동적 배열.
 */
typedef struct {
    double *best_margin;   /* 그 노드까지 가는 가장 좋은 경로의 최소 안전 여유 */
    double *best_time;     /* 그때의 도착 시각 */
    int    *prev_node;     /* 그 경로에서 바로 앞 노드 (경로를 거꾸로 따라갈 때 사용) */
    int    *prev_edge;     /* 바로 앞 노드에서 온 간선 */
    int    *done;          /* 1이면 확정된 노드 (더 좋은 경로가 나올 수 없음) */
} RouteLabels;

/* 라벨 배열을 할당하고 "아직 도착 못 함"으로 초기화한다. 성공 1, 실패 0 */
static int labels_create(RouteLabels *labels, int n)
{
    int i;

    labels->best_margin = (double *)wf_malloc((size_t)n * sizeof(double), "경로 탐색 여유");
    labels->best_time = (double *)wf_malloc((size_t)n * sizeof(double), "경로 탐색 시각");
    labels->prev_node = (int *)wf_malloc((size_t)n * sizeof(int), "경로 탐색 이전 노드");
    labels->prev_edge = (int *)wf_malloc((size_t)n * sizeof(int), "경로 탐색 이전 간선");
    labels->done = (int *)wf_calloc((size_t)n, sizeof(int), "경로 탐색 완료 표시");
    if (labels->best_margin == NULL || labels->best_time == NULL || labels->prev_node == NULL ||
        labels->prev_edge == NULL || labels->done == NULL) {
        return 0;
    }
    for (i = 0; i < n; i++) {
        labels->best_margin[i] = -DANGER_NONE;
        labels->best_time[i] = NO_LABEL_TIME;
        labels->prev_node[i] = -1;
        labels->prev_edge[i] = -1;
    }
    return 1;
}

static void labels_free(RouteLabels *labels)
{
    free(labels->best_margin);
    free(labels->best_time);
    free(labels->prev_node);
    free(labels->prev_edge);
    free(labels->done);
}

/*
 * 확정된 노드 node 에서 연결된 간선을 하나씩 걸어 보고,
 * 이웃 노드의 기록보다 좋으면 기록을 바꾸고 우선순위 큐에 넣는다. ("완화" 단계)
 * 성공 1, 메모리 부족 0
 */
static int relax_neighbors(const Scenario *sc, const DangerMap *danger, int node, double speed_kmh,
                           RouteLabels *labels, PriorityQueue *pq)
{
    const TrailGraph *g = &sc->trails;
    int               k;

    for (k = 0; k < g->adjacent[node].count; k++) {
        int              edge_index = g->adjacent[node].data[k];
        const TrailEdge *edge = &g->edges[edge_index];
        int              other = (edge->from == node) ? edge->to : edge->from;
        double           end_time, edge_margin, new_margin;

        if (labels->done[other]) {
            continue;
        }
        walk_edge(sc, danger, edge_index, node, labels->best_time[node], speed_kmh, &end_time, &edge_margin);
        /* 경로의 최소 여유 = min(지금까지의 최소 여유, 이 간선의 최소 여유) */
        new_margin = (edge_margin < labels->best_margin[node]) ? edge_margin : labels->best_margin[node];

        if (label_is_better(sc, new_margin, end_time, labels->best_margin[other], labels->best_time[other])) {
            labels->best_margin[other] = new_margin;
            labels->best_time[other] = end_time;
            labels->prev_node[other] = node;
            labels->prev_edge[other] = edge_index;
            if (pq_push(pq, -capped_margin(sc, new_margin), end_time, other) != 0) {
                return 0;
            }
        }
    }
    return 1;
}

/* 도착할 수 있었던 안전한 목적지 중 기록이 가장 좋은 노드. 없으면 -1 */
static int pick_best_exit(const Scenario *sc, const DangerMap *danger, const RouteLabels *labels)
{
    int best_exit = -1;
    int i;

    for (i = 0; i < sc->trails.node_count; i++) {
        if (labels->best_time[i] >= NO_LABEL_TIME || !node_is_safe_exit(sc, danger, i)) {
            continue;
        }
        if (best_exit < 0 || label_is_better(sc, labels->best_margin[i], labels->best_time[i],
                                             labels->best_margin[best_exit], labels->best_time[best_exit])) {
            best_exit = i;
        }
    }
    return best_exit;
}

/*
 * find_safest_route: start_node 에서 start_time 에 출발해 안전한 대피 목적지까지 가는 경로를 찾는다.
 *   1) 출발 노드의 기록(여유, 시각)을 정하고 우선순위 큐에 넣는다.
 *      (키: -여유, 도착 시각 → 여유가 큰 것부터, 같으면 빠른 것부터 꺼냄)
 *   2) 큐에서 가장 좋은 노드를 꺼내 확정하고, 이웃 노드의 기록을 갱신한다. (relax_neighbors)
 *   3) 큐가 빌 때까지 반복한 뒤, 안전한 목적지 중 가장 좋은 기록을 고른다. (pick_best_exit)
 *   4) 앞 노드 기록을 거꾸로 따라가 경로를 만든다. (build_route_from_labels)
 * route 에 결과를 저장한다. 목적지에 갈 수 있으면 1, 없으면 0, 메모리 부족 -1
 */
int find_safest_route(const Scenario *sc, const DangerMap *danger, int start_node,
                      double start_time, double speed_kmh, Route *route)
{
    const TrailNode *start = &sc->trails.nodes[start_node];
    RouteLabels      labels;
    PriorityQueue    pq;
    PQItem           item;
    int              best_exit;
    int              status = 0;

    route_init(route);
    pq_init(&pq);
    if (!labels_create(&labels, sc->trails.node_count)) {
        labels_free(&labels);
        return -1;
    }

    /* 1) 출발 노드 */
    labels.best_margin[start_node] = danger_time_at(danger, start->x, start->y) - start_time;
    labels.best_time[start_node] = start_time;
    if (pq_push(&pq, -capped_margin(sc, labels.best_margin[start_node]), start_time, start_node) != 0) {
        status = -1;
    }

    /* 2)~3) 가장 좋은 노드부터 확정하며 이웃 갱신 */
    while (status == 0 && pq_pop(&pq, &item)) {
        if (labels.done[item.value]) {
            continue;   /* 이미 더 좋은 기록으로 확정한 노드 */
        }
        labels.done[item.value] = 1;
        if (!relax_neighbors(sc, danger, item.value, speed_kmh, &labels, &pq)) {
            status = -1;
        }
    }

    /* 4) 가장 좋은 목적지까지의 경로 */
    best_exit = (status == 0) ? pick_best_exit(sc, danger, &labels) : -1;
    if (best_exit >= 0) {
        if (build_route_from_labels(labels.prev_node, labels.prev_edge, best_exit, route)) {
            route->exit_node = best_exit;
            route->travel_time_min = labels.best_time[best_exit] - start_time;
            route->min_margin_min = labels.best_margin[best_exit];
            route->found = 1;
            status = 1;
        } else {
            status = -1;
        }
    }

    pq_free(&pq);
    labels_free(&labels);
    if (status < 0) {
        route_free(route);
    }
    return status;
}
