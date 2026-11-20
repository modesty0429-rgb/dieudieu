/*
 * output_csv.h
 * 격자·이벤트·통계를 CSV 파일로 저장한다.
 */
#ifndef OUTPUT_CSV_H
#define OUTPUT_CSV_H

#include "wf_types.h"

/* 격자 CSV로 저장할 값의 종류 */
typedef enum {
    GRID_VALUE_ARRIVAL = 0,   /* 불 도착 시각 */
    GRID_VALUE_BURNOUT        /* 전소 시각 */
} GridValueKind;

int write_grid_csv(const char *path, const Grid *grid, GridValueKind kind);
int write_fire_events_csv(const char *path, const SimResult *res);
int write_stats_csv(const char *path, const SimResult *res);
const char *cell_state_name(CellState state);

#endif /* OUTPUT_CSV_H */
