/*
 * map_io.h
 * 지형(고도)·연료 격자 파일 읽기와 경사 계산.
 * 파일 형식: ESRI ASCII Grid (.asc) — QGIS 등 GIS 프로그램이 내보낼 수 있는 표준 텍스트 형식.
 */
#ifndef MAP_IO_H
#define MAP_IO_H

#include "wf_types.h"

/* .asc 파일 머리말(헤더) 정보 */
typedef struct {
    int    ncols;         /* 가로 칸 수 */
    int    nrows;         /* 세로 칸 수 */
    double xll;           /* 좌하단 x 좌표 */
    double yll;           /* 좌하단 y 좌표 */
    double cellsize;      /* 칸 크기 (m) */
    double nodata;        /* "값 없음"을 뜻하는 숫자 */
    int    has_nodata;    /* 헤더에 NODATA_value가 있었으면 1 */
} AscHeader;

int  load_asc_grid(const char *path, AscHeader *header, double **values);
int  load_terrain(Scenario *sc);
int  load_fuel_map(Scenario *sc);
void compute_slope_aspect(Grid *grid);

#endif /* MAP_IO_H */
