/*
 * hiker.c
 * 등산객의 보행 속도와 대피 경로를 따라 걷는 이동을 계산한다.
 *
 * [보행 속도] — Tobler 보행 함수
 *   v = 6 × e^(−3.5 × |기울기 + 0.05|)   (km/h, 기울기 = 고도차 / 수평거리)
 *   평지(기울기 0)에서 약 5 km/h, 약간 내리막(−5%)에서 가장 빠르고 가파를수록 느려진다.
 *   여기서는 등산객마다 평지 속도가 다르므로 비율만 가져와 쓴다:
 *     v = 평지 속도 × e^(−3.5 × |기울기 + 0.05|) / e^(−3.5 × 0.05)
 *   출처: Tobler, W. (1993). Three presentations on geographical analysis and modeling.
 *         NCGIA Technical Report 93-1.
 *
 * [눈길 걷기] (9단계)
 *   겨울에 눈 덮인 칸으로 들어갈 때는 속도 × snow_walk_factor (기본 0.75) [가정]
 *
 * [밤에 걷기] (8단계)
 *   해가 지면 헤드랜턴에 의지해 걸으므로 속도가 줄어든다.
 *   속도 = Tobler 속도 × walk_speed_factor(시각)   (낮 1.0, 밤 0.6 [가정], 박명은 그 사이)
 *
 * [이동 기록]
 *   대피 경로의 셀을 하나씩 지나며 "몇 분에 어느 셀에 있는지"(TrackPoint)를 기록한다.
 *   걷다가 이미 불이 도착한 셀을 만나면 그 앞에서 멈추고 "고립"이 된다.
 */
#include <stdlib.h>
#include <math.h>

#include "hiker.h"
#include "daylight.h"
#include "season.h"
#include "evac_route.h"
#include "util.h"
#include "log.h"

#define MIN_WALK_SPEED_KMH 0.3   /* 아무리 가팔라도 이 속도 이상으로 걷는다고 가정 */

/* 기울기(slope = 고도차/수평거리)에서의 보행 속도 (km/h) */
double tobler_speed_kmh(double flat_speed_kmh, double slope)
{
    double ratio = exp(-3.5 * fabs(slope + 0.05)) / exp(-3.5 * 0.05);
    double speed = flat_speed_kmh * ratio;
    return (speed < MIN_WALK_SPEED_KMH) ? MIN_WALK_SPEED_KMH : speed;
}

/*
 * 이웃한 두 셀 사이를 시각 t_min 에 출발해 걷는 데 걸리는 시간 (분).
 * 경사(Tobler)와 밝기(낮/밤)를 함께 반영한다.
 */
double step_time_min(const Scenario *sc, GridPoint from, GridPoint to, double flat_speed_kmh, double t_min)
{
    const Grid *grid = &sc->grid;
    int    is_diagonal = (from.x != to.x) && (from.y != to.y);
    double horizontal_m = grid->cell_size_m * (is_diagonal ? sqrt(2.0) : 1.0);
    double rise_m = grid->cells[to.y][to.x].elevation - grid->cells[from.y][from.x].elevation;
    double speed_m_per_min = tobler_speed_kmh(flat_speed_kmh, rise_m / horizontal_m) * 1000.0 / 60.0;
    double factor = walk_speed_factor(sc, t_min);
    if (cell_has_snow(sc, &grid->cells[to.y][to.x])) {
        factor *= sc->season.snow_walk_factor;     /* (9단계) 눈길은 미끄러워 천천히 걷는다 */
    }
    return horizontal_m / (speed_m_per_min * factor);
}

/* ================================================================
 * 이동 기록
 * ================================================================ */

/* 이동 기록에 점 하나를 추가한다. 성공 1, 실패 0 */
static int push_track_point(Hiker *hiker, int *capacity, double time_min, int x, int y)
{
    if (hiker->track_count == *capacity) {
        int         new_capacity = (*capacity == 0) ? 128 : *capacity * 2;
        TrackPoint *grown = (TrackPoint *)realloc(hiker->track, (size_t)new_capacity * sizeof(TrackPoint));
        if (grown == NULL) {
            log_error("메모리 부족: 등산객 이동 기록");
            return 0;
        }
        hiker->track = grown;
        *capacity = new_capacity;
    }
    hiker->track[hiker->track_count].time_min = time_min;
    hiker->track[hiker->track_count].x = (double)x;
    hiker->track[hiker->track_count].y = (double)y;
    hiker->track_count++;
    return 1;
}

/*
 * 등산객이 대피 경로를 따라 걷는 과정을 셀 단위로 기록한다.
 *   - 출발 전: 시작 노드에 머무름
 *   - 출발 후: 경로의 셀을 하나씩 지나며 Tobler 속도로 시각 계산
 *   - 불이 이미 도착한 셀을 만나면 그 앞에서 멈추고 고립(HIKER_TRAPPED)
 *   - 끝까지 가면 대피 완료(HIKER_SAFE)
 * 출발 시각이 정해지지 않은 등산객(depart_time 없음)은 시작 위치 한 점만 기록한다.
 * 성공 1, 메모리 부족 0
 */
int build_hiker_track(const Scenario *sc, Hiker *hiker)
{
    const TrailGraph *g = &sc->trails;
    const TrailNode  *start = &g->nodes[hiker->start_node];
    int               capacity = 0;
    double            t;
    int               last_x = start->x, last_y = start->y;
    int               k, i;

    hiker->dark_walk_min = 0.0;
    if (!push_track_point(hiker, &capacity, 0.0, start->x, start->y)) {
        return 0;
    }
    if (!time_is_set(hiker->depart_time_min)) {
        hiker->status = HIKER_HIKING;          /* 아직 출발 시각을 정하지 않음 */
        return 1;
    }
    if (!hiker->route.found) {
        hiker->status = HIKER_TRAPPED;         /* 갈 수 있는 안전한 목적지가 없음 */
        hiker->finish_time_min = hiker->depart_time_min;
        return 1;
    }

    t = hiker->depart_time_min;
    if (!push_track_point(hiker, &capacity, t, start->x, start->y)) {
        return 0;
    }

    for (k = 0; k + 1 < hiker->route.node_count; k++) {
        const TrailEdge *edge = &g->edges[hiker->route.edges[k]];
        int              forward = (edge->from == hiker->route.nodes[k]);

        for (i = 1; i < edge->path_count; i++) {
            GridPoint prev = forward ? edge->path[i - 1] : edge->path[edge->path_count - i];
            GridPoint cur = forward ? edge->path[i] : edge->path[edge->path_count - 1 - i];
            double    arrival = sc->grid.cells[cur.y][cur.x].arrival_time;
            double    next_t = t + step_time_min(sc, prev, cur, hiker->speed_kmh, t);

            if (time_is_set(arrival) && arrival <= next_t) {
                /* 다음 셀에 불이 먼저 와 있음 → 지금 셀에서 고립 */
                hiker->status = HIKER_TRAPPED;
                hiker->finish_time_min = t;
                hiker->pos_x = last_x;
                hiker->pos_y = last_y;
                return 1;
            }
            if (walk_speed_factor(sc, t) < 1.0) {
                hiker->dark_walk_min += next_t - t;   /* 어두울 때 걸은 시간 */
            }
            t = next_t;
            last_x = cur.x;
            last_y = cur.y;
            if (!push_track_point(hiker, &capacity, t, cur.x, cur.y)) {
                return 0;
            }
        }
    }
    hiker->status = HIKER_SAFE;
    hiker->finish_time_min = t;
    hiker->pos_x = last_x;
    hiker->pos_y = last_y;
    return 1;
}

/*
 * time_min 시각의 등산객 위치. 이동 기록의 두 점 사이를 선형 보간한다.
 * 기록 전이면 첫 점, 기록 후(대피 완료·고립)면 마지막 점.
 */
void hiker_position_at(const Hiker *hiker, double time_min, double *x, double *y)
{
    const TrackPoint *track = hiker->track;
    int               n = hiker->track_count;
    int               i;

    if (n == 0) {
        *x = hiker->pos_x;
        *y = hiker->pos_y;
        return;
    }
    if (time_min <= track[0].time_min) {
        *x = track[0].x;
        *y = track[0].y;
        return;
    }
    for (i = 1; i < n; i++) {
        if (time_min <= track[i].time_min) {
            double span = track[i].time_min - track[i - 1].time_min;
            double ratio = (span > 0.0) ? (time_min - track[i - 1].time_min) / span : 1.0;
            *x = track[i - 1].x + (track[i].x - track[i - 1].x) * ratio;
            *y = track[i - 1].y + (track[i].y - track[i - 1].y) * ratio;
            return;
        }
    }
    *x = track[n - 1].x;
    *y = track[n - 1].y;
}

/* 이전 계산 결과(경로·기록)를 지우고 처음 상태로 되돌린다. (같은 등산객으로 다시 계산할 때) */
void reset_hiker(Hiker *hiker)
{
    free_hiker_data(hiker);
    hiker->depart_time_min = WF_NO_TIME;
    hiker->finish_time_min = WF_NO_TIME;
    hiker->status = HIKER_HIKING;
    hiker->alert = ALERT_NONE;
    hiker->dark_walk_min = 0.0;
}

/* 등산객 한 명이 가진 동적 메모리(경로, 이동 기록, 상태 기록)를 해제한다. */
void free_hiker_data(Hiker *hiker)
{
    route_free(&hiker->route);
    free(hiker->track);
    free(hiker->samples);
    hiker->track = NULL;
    hiker->track_count = 0;
    hiker->samples = NULL;
    hiker->sample_count = 0;
}
