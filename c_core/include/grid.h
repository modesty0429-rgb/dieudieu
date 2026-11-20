/*
 * grid.h
 * 2차원 격자(Grid)의 생성·해제와 8방향 이웃 계산.
 *
 * 방향 번호 (북쪽에서 시계방향):
 *        7(북서) 0(북) 1(북동)
 *        6(서)    셀   2(동)
 *        5(남서) 4(남) 3(남동)
 */
#ifndef GRID_H
#define GRID_H

#include "wf_types.h"

#define GRID_DIRECTIONS 8

int    grid_create(Grid *grid, int width, int height, double cell_size_m);
void   grid_free(Grid *grid);
int    grid_in_bounds(const Grid *grid, int x, int y);
int    grid_cell_index(const Grid *grid, int x, int y);

int    grid_neighbor_dx(int dir);
int    grid_neighbor_dy(int dir);
double grid_neighbor_distance(const Grid *grid, int dir);
double grid_direction_azimuth(int dir);
const char *grid_direction_name(int dir);

void   grid_reset_fire_state(Grid *grid);
int    cell_is_burnable_state(const Cell *cell);

#endif /* GRID_H */
