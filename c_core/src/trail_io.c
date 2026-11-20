/*
 * trail_io.c
 * 등산로 그래프 파일과 등산객 파일을 읽는다.
 *
 * [등산로 파일 형식] (# 뒤는 주석)
 *   NODE <번호> <종류> <x> <y> <이름>
 *   EDGE <시작노드번호> <끝노드번호> <경유점개수> [x1 y1 x2 y2 ...]
 *     - 종류: JUNCTION(갈림길) SHELTER(대피소) PARKING(주차장) SUMMIT(정상) POINT(기타)
 *     - 경유점: 두 노드 사이에서 길이 꺾이는 중간 지점. 0개면 두 노드를 직선으로 잇는다.
 *
 * [등산객 파일 형식]
 *   HIKER <번호> <이름> <시작노드번호> <보행속도km/h> <인원>
 *
 * 노드를 모두 읽어야 간선이 어느 노드를 잇는지 알 수 있으므로 파일을 세 번 읽는다.
 *   1번째: NODE, EDGE 줄 개수 세기 → 정확한 크기로 메모리 할당
 *   2번째: NODE 줄 읽기
 *   3번째: EDGE 줄 읽기
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "trail_io.h"
#include "hiker.h"
#include "grid.h"
#include "util.h"
#include "log.h"

#define TRAIL_MAX_TOKENS (4 + 2 * WF_MAX_WAYPOINTS)

/* ================================================================
 * 파일 한 줄씩 읽기 도우미
 * ================================================================ */

/*
 * 주석과 빈 줄을 건너뛰고, 내용이 있는 다음 줄을 단어 단위로 나눠 준다.
 * 반환값: 1 = 한 줄 읽음, 0 = 파일 끝, -1 = 오류(줄이 너무 김)
 */
static int read_next_record(FILE *fp, const char *path, char *line, int line_size,
                            int *line_no, char **tokens, int *token_count)
{
    for (;;) {
        int result = read_text_line(fp, line, line_size, line_no);
        if (result == 0) {
            return 0;
        }
        if (result < 0) {
            log_error("%s %d번째 줄: 줄이 너무 김 (최대 %d자)", path, *line_no, line_size - 1);
            return -1;
        }
        strip_comment(line);
        *token_count = split_whitespace(line, tokens, TRAIL_MAX_TOKENS);
        if (*token_count > TRAIL_MAX_TOKENS) {
            log_error("%s %d번째 줄: 값이 너무 많음 (경유점은 최대 %d개)", path, *line_no, WF_MAX_WAYPOINTS);
            return -1;
        }
        if (*token_count > 0) {
            return 1;
        }
    }
}

/* 문자열을 노드 종류로 바꾼다. 성공 1, 실패 0 */
static int parse_node_type(const char *text, NodeType *type)
{
    if (str_equals_ignore_case(text, "JUNCTION")) {
        *type = NODE_JUNCTION;
    } else if (str_equals_ignore_case(text, "SHELTER")) {
        *type = NODE_SHELTER;
    } else if (str_equals_ignore_case(text, "PARKING")) {
        *type = NODE_PARKING;
    } else if (str_equals_ignore_case(text, "SUMMIT")) {
        *type = NODE_SUMMIT;
    } else if (str_equals_ignore_case(text, "POINT")) {
        *type = NODE_POINT;
    } else {
        return 0;
    }
    return 1;
}

/* 노드 종류의 한국어 이름 */
const char *node_type_name(NodeType type)
{
    switch (type) {
    case NODE_JUNCTION: return "갈림길";
    case NODE_SHELTER:  return "대피소";
    case NODE_PARKING:  return "주차장";
    case NODE_SUMMIT:   return "정상";
    case NODE_POINT:    return "지점";
    default:            return "?";
    }
}

/* 파일 번호(id)로 노드 배열 인덱스를 찾는다. 없으면 -1 */
int find_node_index_by_id(const TrailGraph *graph, int id)
{
    int i;
    for (i = 0; i < graph->node_count; i++) {
        if (graph->nodes[i].id == id) {
            return i;
        }
    }
    return -1;
}

/* ================================================================
 * NODE 줄 해석
 * ================================================================ */

/*
 * "NODE id type x y 이름..." 을 해석해 graph->nodes[index]에 저장한다.
 * 이름에 공백이 있을 수 있으므로 5번째 단어부터 끝까지를 이어 붙인다.
 */
static int parse_node_record(char **tokens, int token_count, const char *path, int line_no,
                             const Grid *grid, TrailGraph *graph, int index)
{
    TrailNode *node = &graph->nodes[index];
    int        i;

    if (token_count < 6) {
        log_error("%s %d번째 줄: NODE 형식은 'NODE 번호 종류 x y 이름' 임", path, line_no);
        return 0;
    }
    if (!parse_int_strict(tokens[1], &node->id) ||
        !parse_int_strict(tokens[3], &node->x) ||
        !parse_int_strict(tokens[4], &node->y)) {
        log_error("%s %d번째 줄: 번호와 x, y는 정수여야 함", path, line_no);
        return 0;
    }
    if (!parse_node_type(tokens[2], &node->type)) {
        log_error("%s %d번째 줄: 알 수 없는 노드 종류 '%s' (JUNCTION, SHELTER, PARKING, SUMMIT, POINT 중 하나)",
                  path, line_no, tokens[2]);
        return 0;
    }
    if (!grid_in_bounds(grid, node->x, node->y)) {
        log_error("%s %d번째 줄: 노드 %d의 좌표 (%d, %d)가 지도(%d x %d) 밖임",
                  path, line_no, node->id, node->x, node->y, grid->width, grid->height);
        return 0;
    }
    if (find_node_index_by_id(graph, node->id) != index) {
        log_error("%s %d번째 줄: 노드 번호 %d 가 중복됨", path, line_no, node->id);
        return 0;
    }

    /* 이름 이어 붙이기 */
    copy_string(node->name, sizeof(node->name), tokens[5]);
    for (i = 6; i < token_count; i++) {
        size_t used = strlen(node->name);
        snprintf(node->name + used, sizeof(node->name) - used, " %s", tokens[i]);
    }

    node->is_exit = (node->type == NODE_SHELTER || node->type == NODE_PARKING);

    if (grid->cells[node->y][node->x].state == CELL_WATER) {
        log_warn("%s %d번째 줄: 노드 '%s'가 물 위에 있음", path, line_no, node->name);
    }
    return 1;
}

/* ================================================================
 * EDGE 줄 해석: 간선이 지나는 셀 목록 만들기
 * ================================================================ */

/*
 * 두 점 (x0, y0) → (x1, y1)을 잇는 직선 위의 셀을 out 배열에 차례로 넣는다.
 * — Bresenham 직선 알고리즘 (정수 덧셈만으로 직선 위의 칸을 고른다)
 * skip_first가 1이면 시작점은 넣지 않는다. (앞 구간의 끝점과 겹치지 않게)
 * 출처: Bresenham, J.E. (1965). Algorithm for computer control of a digital plotter.
 */
static void add_line_cells(int x0, int y0, int x1, int y1, int skip_first,
                           GridPoint *out, int *out_count)
{
    int dx = abs_int(x1 - x0);
    int dy = -abs_int(y1 - y0);
    int step_x = (x0 < x1) ? 1 : -1;
    int step_y = (y0 < y1) ? 1 : -1;
    int error = dx + dy;
    int is_first = 1;

    for (;;) {
        int double_error;

        if (!(is_first && skip_first)) {
            out[*out_count].x = x0;
            out[*out_count].y = y0;
            (*out_count)++;
        }
        is_first = 0;
        if (x0 == x1 && y0 == y1) {
            break;
        }
        /* 두 조건을 같은 값으로 판단해야 하므로 error를 바꾸기 전에 미리 계산해 둔다 */
        double_error = 2 * error;
        if (double_error >= dy) {   /* x 방향으로 한 칸 */
            error += dy;
            x0 += step_x;
        }
        if (double_error <= dx) {   /* y 방향으로 한 칸 */
            error += dx;
            y0 += step_y;
        }
    }
}

/*
 * 꺾인 선(points[0] → points[1] → ... )이 지나는 셀 목록을 만들어 edge->path에 저장한다.
 * 먼저 필요한 칸 수를 계산해 정확한 크기로 할당한 뒤 채운다.
 */
static int build_edge_path(const GridPoint *points, int point_count, TrailEdge *edge)
{
    int total = 1;
    int i;

    for (i = 1; i < point_count; i++) {
        int dx = abs_int(points[i].x - points[i - 1].x);
        int dy = abs_int(points[i].y - points[i - 1].y);
        total += max_int(dx, dy);   /* Bresenham 직선은 max(dx, dy) + 1 칸 */
    }

    edge->path = (GridPoint *)wf_malloc((size_t)total * sizeof(GridPoint), "등산로 경로 셀");
    if (edge->path == NULL) {
        return 0;
    }
    edge->path_count = 0;
    for (i = 1; i < point_count; i++) {
        add_line_cells(points[i - 1].x, points[i - 1].y, points[i].x, points[i].y,
                       (i > 1), edge->path, &edge->path_count);
    }
    return 1;
}

/*
 * 경로 셀의 고도를 따라가며 간선의 실제 길이, 오르막 합계, 내리막 합계를 계산한다.
 * 한 칸 이동 거리 = √(수평거리² + 고도차²)
 */
static void measure_edge(const Grid *grid, TrailEdge *edge)
{
    int i;

    edge->length_m = 0.0;
    edge->climb_m = 0.0;
    edge->descent_m = 0.0;

    for (i = 1; i < edge->path_count; i++) {
        GridPoint prev = edge->path[i - 1];
        GridPoint cur = edge->path[i];
        int       is_diagonal = (prev.x != cur.x) && (prev.y != cur.y);
        double    horizontal = grid->cell_size_m * (is_diagonal ? sqrt(2.0) : 1.0);
        double    dz = grid->cells[cur.y][cur.x].elevation - grid->cells[prev.y][prev.x].elevation;

        edge->length_m += sqrt(horizontal * horizontal + dz * dz);
        if (dz > 0.0) {
            edge->climb_m += dz;
        } else {
            edge->descent_m -= dz;
        }
    }
}

/*
 * "EDGE from to n x1 y1 ... xn yn" 을 해석해 graph->edges[index]에 저장한다.
 * 시작 노드 → 경유점들 → 끝 노드 순서로 점을 모아 경로 셀을 만든다.
 */
static int parse_edge_record(char **tokens, int token_count, const char *path, int line_no,
                             const Grid *grid, TrailGraph *graph, int index)
{
    TrailEdge *edge = &graph->edges[index];
    GridPoint  points[WF_MAX_WAYPOINTS + 2];
    int        from_id, to_id, waypoint_count;
    int        i;

    edge->path = NULL;
    edge->path_count = 0;

    if (token_count < 4 ||
        !parse_int_strict(tokens[1], &from_id) ||
        !parse_int_strict(tokens[2], &to_id) ||
        !parse_int_strict(tokens[3], &waypoint_count)) {
        log_error("%s %d번째 줄: EDGE 형식은 'EDGE 시작번호 끝번호 경유점개수 [x y ...]' 임", path, line_no);
        return 0;
    }
    if (waypoint_count < 0 || waypoint_count > WF_MAX_WAYPOINTS) {
        log_error("%s %d번째 줄: 경유점 개수 %d 는 0 ~ %d 이어야 함", path, line_no, waypoint_count, WF_MAX_WAYPOINTS);
        return 0;
    }
    if (token_count != 4 + 2 * waypoint_count) {
        log_error("%s %d번째 줄: 경유점 %d개에는 좌표 숫자 %d개가 필요한데 %d개가 있음",
                  path, line_no, waypoint_count, 2 * waypoint_count, token_count - 4);
        return 0;
    }

    edge->from = find_node_index_by_id(graph, from_id);
    edge->to = find_node_index_by_id(graph, to_id);
    if (edge->from < 0 || edge->to < 0) {
        log_error("%s %d번째 줄: 없는 노드 번호 %d 를 사용함", path, line_no, (edge->from < 0) ? from_id : to_id);
        return 0;
    }
    if (edge->from == edge->to) {
        log_error("%s %d번째 줄: 간선의 시작과 끝이 같은 노드(%d)임", path, line_no, from_id);
        return 0;
    }

    /* 점 목록 만들기: 시작 노드, 경유점들, 끝 노드 */
    points[0].x = graph->nodes[edge->from].x;
    points[0].y = graph->nodes[edge->from].y;
    for (i = 0; i < waypoint_count; i++) {
        GridPoint *p = &points[i + 1];
        if (!parse_int_strict(tokens[4 + 2 * i], &p->x) ||
            !parse_int_strict(tokens[5 + 2 * i], &p->y)) {
            log_error("%s %d번째 줄: %d번째 경유점 좌표가 정수가 아님", path, line_no, i + 1);
            return 0;
        }
        if (!grid_in_bounds(grid, p->x, p->y)) {
            log_error("%s %d번째 줄: %d번째 경유점 (%d, %d)가 지도 밖임", path, line_no, i + 1, p->x, p->y);
            return 0;
        }
    }
    points[waypoint_count + 1].x = graph->nodes[edge->to].x;
    points[waypoint_count + 1].y = graph->nodes[edge->to].y;

    if (!build_edge_path(points, waypoint_count + 2, edge)) {
        return 0;
    }
    measure_edge(grid, edge);
    return 1;
}

/* ================================================================
 * 등산로 그래프 읽기
 * ================================================================ */

/* 1번째 읽기: NODE, EDGE 줄의 개수를 센다. */
static int count_trail_records(FILE *fp, const char *path, int *node_count, int *edge_count)
{
    char  line[WF_LINE_MAX];
    char *tokens[TRAIL_MAX_TOKENS];
    int   token_count;
    int   line_no = 0;
    int   result;

    *node_count = 0;
    *edge_count = 0;
    while ((result = read_next_record(fp, path, line, (int)sizeof(line), &line_no, tokens, &token_count)) > 0) {
        if (str_equals_ignore_case(tokens[0], "NODE")) {
            (*node_count)++;
        } else if (str_equals_ignore_case(tokens[0], "EDGE")) {
            (*edge_count)++;
        } else {
            log_error("%s %d번째 줄: 'NODE' 또는 'EDGE'로 시작해야 함 (읽은 단어: '%s')", path, line_no, tokens[0]);
            return 0;
        }
    }
    return result == 0;
}

/* 2번째·3번째 읽기: keyword("NODE" 또는 "EDGE") 줄만 골라 해석한다. */
static int parse_trail_records(FILE *fp, const char *path, const char *keyword,
                               const Grid *grid, TrailGraph *graph)
{
    char  line[WF_LINE_MAX];
    char *tokens[TRAIL_MAX_TOKENS];
    int   token_count;
    int   line_no = 0;
    int   index = 0;
    int   result;
    int   is_node = str_equals_ignore_case(keyword, "NODE");

    rewind(fp);   /* 파일 처음으로 되돌아가기 */
    while ((result = read_next_record(fp, path, line, (int)sizeof(line), &line_no, tokens, &token_count)) > 0) {
        if (!str_equals_ignore_case(tokens[0], keyword)) {
            continue;
        }
        if (is_node) {
            /* 아직 안 읽은 노드의 id는 비교에 쓰이지 않도록 node_count를 하나씩 늘린다 */
            graph->node_count = index + 1;
            if (!parse_node_record(tokens, token_count, path, line_no, grid, graph, index)) {
                return 0;
            }
        } else {
            graph->edge_count = index + 1;
            if (!parse_edge_record(tokens, token_count, path, line_no, grid, graph, index)) {
                return 0;
            }
        }
        index++;
    }
    return result == 0;
}

/* 각 노드에 연결된 간선 목록(인접 리스트)을 만든다. 간선은 양방향이다. */
static int build_adjacency(TrailGraph *graph)
{
    int i;

    graph->adjacent = (IntArray *)wf_calloc((size_t)graph->node_count, sizeof(IntArray), "등산로 인접 리스트");
    if (graph->adjacent == NULL) {
        return 0;
    }
    for (i = 0; i < graph->node_count; i++) {
        intarray_init(&graph->adjacent[i]);
    }
    for (i = 0; i < graph->edge_count; i++) {
        if (intarray_push(&graph->adjacent[graph->edges[i].from], i) != 0 ||
            intarray_push(&graph->adjacent[graph->edges[i].to], i) != 0) {
            return 0;
        }
    }
    return 1;
}

/* 그래프를 비어 있는 상태로 초기화한다. */
static void init_trail_graph(TrailGraph *graph)
{
    graph->nodes = NULL;
    graph->node_count = 0;
    graph->edges = NULL;
    graph->edge_count = 0;
    graph->adjacent = NULL;
}

/*
 * 등산로 그래프 파일을 읽는다.
 * 노드 좌표가 지도 안인지, 간선이 존재하는 노드를 잇는지 검사하고,
 * 간선마다 지나가는 셀 목록과 실제 길이·오르막·내리막을 계산한다.
 * 성공 1, 실패 0 (실패해도 free_trail_graph로 안전하게 해제할 수 있다)
 */
int load_trail_graph(const char *path, const Grid *grid, TrailGraph *graph)
{
    FILE *fp;
    int   node_total, edge_total;
    int   ok;

    init_trail_graph(graph);

    fp = fopen(path, "r");
    if (fp == NULL) {
        log_error("등산로 파일을 열 수 없음: %s", path);
        return 0;
    }

    /* 1) 개수 세기 */
    if (!count_trail_records(fp, path, &node_total, &edge_total)) {
        fclose(fp);
        return 0;
    }
    if (node_total < 2 || edge_total < 1) {
        log_error("%s: 노드는 2개 이상, 간선은 1개 이상 있어야 함 (노드 %d, 간선 %d)", path, node_total, edge_total);
        fclose(fp);
        return 0;
    }

    /* 2) 메모리 할당 (calloc: 간선의 path 포인터가 NULL로 시작해 해제가 안전함) */
    graph->nodes = (TrailNode *)wf_calloc((size_t)node_total, sizeof(TrailNode), "등산로 노드");
    graph->edges = (TrailEdge *)wf_calloc((size_t)edge_total, sizeof(TrailEdge), "등산로 간선");
    if (graph->nodes == NULL || graph->edges == NULL) {
        fclose(fp);
        return 0;
    }

    /* 3) 노드 읽기 → 4) 간선 읽기 → 5) 인접 리스트 만들기 */
    ok = parse_trail_records(fp, path, "NODE", grid, graph) &&
         parse_trail_records(fp, path, "EDGE", grid, graph) &&
         build_adjacency(graph);
    fclose(fp);
    if (!ok) {
        return 0;
    }

    log_info("등산로 읽기 완료: 노드 %d개, 간선 %d개", graph->node_count, graph->edge_count);
    check_exits_reachable(graph);
    return 1;
}

/*
 * 모든 노드에서 대피 목적지(대피소·주차장)까지 갈 수 있는지 검사한다.
 * 모든 목적지에서 동시에 출발하는 너비 우선 탐색(BFS)을 해서
 * 한 번도 도달하지 못한 노드가 있으면 경고를 출력한다.
 * 반환값: 목적지까지 갈 수 없는 노드 수
 */
int check_exits_reachable(const TrailGraph *graph)
{
    IntArray queue;
    int     *visited;
    int      head = 0;
    int      unreachable = 0;
    int      i, k;

    visited = (int *)wf_calloc((size_t)graph->node_count, sizeof(int), "BFS 방문 표시");
    if (visited == NULL) {
        return -1;
    }
    intarray_init(&queue);

    /* 출발점: 모든 대피 목적지 */
    for (i = 0; i < graph->node_count; i++) {
        if (graph->nodes[i].is_exit) {
            visited[i] = 1;
            intarray_push(&queue, i);
        }
    }
    if (queue.count == 0) {
        log_warn("등산로에 대피 목적지(SHELTER 또는 PARKING)가 하나도 없음");
    }

    /* 큐에서 하나씩 꺼내 이웃 노드를 방문 */
    while (head < queue.count) {
        int node = queue.data[head];
        head++;
        for (k = 0; k < graph->adjacent[node].count; k++) {
            const TrailEdge *edge = &graph->edges[graph->adjacent[node].data[k]];
            int other = (edge->from == node) ? edge->to : edge->from;
            if (!visited[other]) {
                visited[other] = 1;
                if (intarray_push(&queue, other) != 0) {
                    break;
                }
            }
        }
    }

    for (i = 0; i < graph->node_count; i++) {
        if (!visited[i]) {
            log_warn("노드 %d '%s'에서 대피소·주차장으로 가는 길이 없음", graph->nodes[i].id, graph->nodes[i].name);
            unreachable++;
        }
    }

    intarray_free(&queue);
    free(visited);
    return unreachable;
}

/* 등산로 그래프의 메모리를 모두 해제한다. */
void free_trail_graph(TrailGraph *graph)
{
    int i;

    if (graph->edges != NULL) {
        for (i = 0; i < graph->edge_count; i++) {
            free(graph->edges[i].path);
        }
    }
    if (graph->adjacent != NULL) {
        for (i = 0; i < graph->node_count; i++) {
            intarray_free(&graph->adjacent[i]);
        }
    }
    free(graph->nodes);
    free(graph->edges);
    free(graph->adjacent);
    init_trail_graph(graph);
}

/* ================================================================
 * 등산객 파일 읽기
 * ================================================================ */

/* "HIKER id 이름 노드번호 속도 인원" 한 줄을 해석한다. */
static int parse_hiker_record(char **tokens, int token_count, const char *path, int line_no,
                              const TrailGraph *graph, Hiker *hikers, int index)
{
    Hiker *hiker = &hikers[index];
    int    node_id;
    int    i;

    if (token_count != 6 || !str_equals_ignore_case(tokens[0], "HIKER")) {
        log_error("%s %d번째 줄: 형식은 'HIKER 번호 이름 시작노드번호 속도(km/h) 인원' 임 (이름에 공백 불가)",
                  path, line_no);
        return 0;
    }
    if (!parse_int_strict(tokens[1], &hiker->id) ||
        !parse_int_strict(tokens[3], &node_id) ||
        !parse_double_strict(tokens[4], &hiker->speed_kmh) ||
        !parse_int_strict(tokens[5], &hiker->group_size)) {
        log_error("%s %d번째 줄: 번호·노드번호·인원은 정수, 속도는 숫자여야 함", path, line_no);
        return 0;
    }
    for (i = 0; i < index; i++) {
        if (hikers[i].id == hiker->id) {
            log_error("%s %d번째 줄: 등산객 번호 %d 가 중복됨", path, line_no, hiker->id);
            return 0;
        }
    }
    hiker->start_node = find_node_index_by_id(graph, node_id);
    if (hiker->start_node < 0) {
        log_error("%s %d번째 줄: 등산로에 없는 노드 번호 %d", path, line_no, node_id);
        return 0;
    }
    if (hiker->speed_kmh < 0.5 || hiker->speed_kmh > 10.0) {
        log_error("%s %d번째 줄: 보행 속도 %.1f km/h 는 0.5 ~ 10 사이여야 함", path, line_no, hiker->speed_kmh);
        return 0;
    }
    if (hiker->group_size < 1 || hiker->group_size > 500) {
        log_error("%s %d번째 줄: 인원 %d 는 1 ~ 500 사이여야 함", path, line_no, hiker->group_size);
        return 0;
    }

    copy_string(hiker->name, sizeof(hiker->name), tokens[2]);
    hiker->depart_time_min = WF_NO_TIME;
    hiker->pos_x = (double)graph->nodes[hiker->start_node].x;
    hiker->pos_y = (double)graph->nodes[hiker->start_node].y;
    hiker->status = HIKER_HIKING;
    hiker->alert = ALERT_NONE;
    hiker->finish_time_min = WF_NO_TIME;
    hiker->track = NULL;
    hiker->track_count = 0;
    hiker->samples = NULL;
    hiker->sample_count = 0;
    hiker->route.nodes = NULL;
    hiker->route.edges = NULL;
    hiker->route.node_count = 0;
    hiker->route.exit_node = -1;
    hiker->route.travel_time_min = 0.0;
    hiker->route.min_margin_min = 0.0;
    hiker->route.found = 0;
    return 1;
}

/*
 * 등산객 파일을 읽어 Hiker 배열을 새로 할당해 돌려준다.
 * 1번째 읽기로 개수를 세고, 2번째 읽기로 내용을 채운다.
 * 성공 1, 실패 0
 */
int load_hikers(const char *path, const TrailGraph *graph, Hiker **hikers, int *hiker_count)
{
    FILE  *fp;
    char   line[WF_LINE_MAX];
    char  *tokens[TRAIL_MAX_TOKENS];
    int    token_count;
    int    line_no = 0;
    int    total = 0;
    int    index = 0;
    int    result;
    Hiker *list;

    *hikers = NULL;
    *hiker_count = 0;

    fp = fopen(path, "r");
    if (fp == NULL) {
        log_error("등산객 파일을 열 수 없음: %s", path);
        return 0;
    }

    /* 1) 개수 세기 */
    while ((result = read_next_record(fp, path, line, (int)sizeof(line), &line_no, tokens, &token_count)) > 0) {
        total++;
    }
    if (result < 0) {
        fclose(fp);
        return 0;
    }
    if (total == 0) {
        log_warn("%s: 등산객이 한 명도 없음", path);
        fclose(fp);
        return 1;
    }

    /* 2) 할당 후 다시 읽기 */
    list = (Hiker *)wf_calloc((size_t)total, sizeof(Hiker), "등산객 배열");
    if (list == NULL) {
        fclose(fp);
        return 0;
    }
    rewind(fp);
    line_no = 0;
    while ((result = read_next_record(fp, path, line, (int)sizeof(line), &line_no, tokens, &token_count)) > 0) {
        if (!parse_hiker_record(tokens, token_count, path, line_no, graph, list, index)) {
            free(list);
            fclose(fp);
            return 0;
        }
        index++;
    }
    fclose(fp);

    *hikers = list;
    *hiker_count = index;
    log_info("등산객 읽기 완료: %d팀", index);
    return 1;
}

/* 등산객 배열과 각자의 경로·이동 기록 메모리를 해제한다. */
void free_hikers(Hiker *hikers, int hiker_count)
{
    int i;

    if (hikers == NULL) {
        return;
    }
    for (i = 0; i < hiker_count; i++) {
        free_hiker_data(&hikers[i]);
    }
    free(hikers);
}
