/*
 * evac_route.h
 * 위험 지도와 가장 안전한 대피 경로 탐색.
 */
#ifndef EVAC_ROUTE_H
#define EVAC_ROUTE_H

#include "wf_types.h"

#define DANGER_NONE 1.0e9   /* 불이 끝까지 오지 않는 곳의 "위험 시각" */

/*
 * 위험 지도: 셀마다 "반경 R 안에 불이 처음 도착하는 시각" (분)
 * 불이 오지 않으면 DANGER_NONE.
 */
typedef struct {
    int     width, height;
    double  radius_m;
    double *time;           /* width × height 1차원 배열, (x, y) → time[y * width + x] */
} DangerMap;

int    build_danger_map(const Grid *grid, double radius_m, DangerMap *map);
double danger_time_at(const DangerMap *map, int x, int y);
void   free_danger_map(DangerMap *map);

int    node_is_safe_exit(const Scenario *sc, const DangerMap *danger, int node);
int    find_safest_route(const Scenario *sc, const DangerMap *danger, int start_node,
                         double start_time, double speed_kmh, Route *route);
void   route_init(Route *route);
void   route_free(Route *route);
int    margin_is_unlimited(double margin_min);

#endif /* EVAC_ROUTE_H */
