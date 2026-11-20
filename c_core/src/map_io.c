/*
 * map_io.c
 * 지형(고도)·연료 격자 파일을 읽고, 고도로부터 경사와 경사 방향을 계산한다.
 *
 * [ESRI ASCII Grid (.asc) 형식]
 *   ncols        200        ← 가로 칸 수
 *   nrows        200        ← 세로 칸 수
 *   xllcorner    0.0        ← 좌하단 x 좌표 (xllcenter도 허용)
 *   yllcorner    0.0        ← 좌하단 y 좌표 (yllcenter도 허용)
 *   cellsize     30.0       ← 칸 크기 (m)
 *   NODATA_value -9999      ← "값 없음" 표시 (생략 가능)
 *   512.3 515.0 ...         ← 첫 데이터 줄 = 지도의 북쪽 끝 행
 *
 * QGIS에서 실제 DEM(수치표고모델)이나 임상도를 이 형식으로 내보내면 그대로 쓸 수 있다.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <math.h>

#include "map_io.h"
#include "grid.h"
#include "util.h"
#include "log.h"

/* 고도가 이 범위를 벗어나면 단위(m)가 잘못된 파일로 보고 오류 처리 */
#define ELEVATION_MIN_ALLOWED (-500.0)
#define ELEVATION_MAX_ALLOWED 9000.0

/* ================================================================
 * .asc 파일 읽기
 * ================================================================ */

/* 헤더 키 하나를 해석해 header에 넣는다. 알 수 있는 키면 1, 모르는 키면 0 */
static int apply_asc_header_key(const char *key, double value, AscHeader *header,
                                int *found_x_center, int *found_y_center)
{
    if (str_equals_ignore_case(key, "ncols")) {
        header->ncols = round_to_int(value);
    } else if (str_equals_ignore_case(key, "nrows")) {
        header->nrows = round_to_int(value);
    } else if (str_equals_ignore_case(key, "xllcorner")) {
        header->xll = value;
    } else if (str_equals_ignore_case(key, "yllcorner")) {
        header->yll = value;
    } else if (str_equals_ignore_case(key, "xllcenter")) {
        header->xll = value;
        *found_x_center = 1;
    } else if (str_equals_ignore_case(key, "yllcenter")) {
        header->yll = value;
        *found_y_center = 1;
    } else if (str_equals_ignore_case(key, "cellsize")) {
        header->cellsize = value;
    } else if (str_equals_ignore_case(key, "NODATA_value")) {
        header->nodata = value;
        header->has_nodata = 1;
    } else {
        return 0;
    }
    return 1;
}

/*
 * .asc 파일의 헤더 부분을 읽는다.
 * 글자로 시작하는 줄은 헤더, 숫자로 시작하는 줄이 나오면 데이터 시작으로 본다.
 * 데이터 줄을 이미 읽어 버렸으면 fseek로 그 줄의 처음으로 되돌아간다.
 */
static int read_asc_header(FILE *fp, const char *path, AscHeader *header)
{
    char line[WF_LINE_MAX];
    int  line_no = 0;
    int  found_x_center = 0;
    int  found_y_center = 0;
    int  i;

    header->ncols = 0;
    header->nrows = 0;
    header->xll = 0.0;
    header->yll = 0.0;
    header->cellsize = 0.0;
    header->nodata = -9999.0;
    header->has_nodata = 0;

    for (i = 0; i < 8; i++) {   /* 헤더는 최대 6줄이지만 빈 줄을 고려해 조금 여유 있게 */
        long  line_start = ftell(fp);
        char  key[64];
        char *text;
        double value;
        int   result = read_text_line(fp, line, (int)sizeof(line), &line_no);

        if (result == 0) {
            break;   /* 파일 끝 */
        }
        text = str_trim(line);
        if (text[0] == '\0') {
            continue;   /* 빈 줄 */
        }
        if (!isalpha((unsigned char)text[0])) {
            /* 숫자로 시작 → 데이터가 시작됨. 이 줄을 다시 읽을 수 있게 되돌린다. */
            fseek(fp, line_start, SEEK_SET);
            break;
        }
        if (sscanf(text, "%63s %lf", key, &value) != 2) {
            log_error("%s %d번째 줄: 헤더 형식은 '이름 값' 이어야 함 (읽은 내용: '%s')",
                      path, line_no, text);
            return 0;
        }
        if (!apply_asc_header_key(key, value, header, &found_x_center, &found_y_center)) {
            log_error("%s %d번째 줄: 알 수 없는 헤더 이름 '%s'", path, line_no, key);
            return 0;
        }
    }

    /* 필수 값 검사 */
    if (header->ncols <= 0 || header->nrows <= 0) {
        log_error("%s: 헤더에 ncols, nrows가 없거나 0 이하임", path);
        return 0;
    }
    if (header->ncols > WF_MAX_GRID_SIZE || header->nrows > WF_MAX_GRID_SIZE) {
        log_error("%s: 격자 %d x %d 가 너무 큼 (최대 %d)", path,
                  header->ncols, header->nrows, WF_MAX_GRID_SIZE);
        return 0;
    }
    if (header->cellsize <= 0.0) {
        log_error("%s: 헤더의 cellsize가 없거나 0 이하임", path);
        return 0;
    }

    /* xllcenter는 "좌하단 칸의 중심"이므로 반 칸 빼서 "모서리" 좌표로 통일 */
    if (found_x_center) {
        header->xll -= header->cellsize / 2.0;
    }
    if (found_y_center) {
        header->yll -= header->cellsize / 2.0;
    }
    return 1;
}

/*
 * .asc 파일 전체를 읽는다.
 * header: 헤더 정보가 저장된다.
 * values: nrows × ncols 크기의 1차원 배열을 새로 할당해 돌려준다.
 *         (row, col) 값은 values[row * ncols + col]. 사용 후 free 해야 한다.
 * 성공 1, 실패 0
 */
int load_asc_grid(const char *path, AscHeader *header, double **values)
{
    FILE   *fp;
    double *data;
    int     row, col;
    char    extra[64];

    *values = NULL;

    fp = fopen(path, "r");
    if (fp == NULL) {
        log_error("격자 파일을 열 수 없음: %s (경로와 파일 이름을 확인하세요)", path);
        return 0;
    }

    if (!read_asc_header(fp, path, header)) {
        fclose(fp);
        return 0;
    }

    data = (double *)wf_malloc((size_t)header->ncols * (size_t)header->nrows * sizeof(double),
                               "격자 값 배열");
    if (data == NULL) {
        fclose(fp);
        return 0;
    }

    /* 값은 줄바꿈과 상관없이 공백으로 구분되어 있으므로 fscanf로 하나씩 읽는다. */
    for (row = 0; row < header->nrows; row++) {
        for (col = 0; col < header->ncols; col++) {
            double v;
            int    result = fscanf(fp, "%lf", &v);

            if (result == 1) {
                data[row * header->ncols + col] = v;
                continue;
            }
            if (result == EOF) {
                log_error("%s: 값이 부족함 — 데이터 %d행 %d열에서 파일이 끝남 (필요한 값 %d x %d개)",
                          path, row + 1, col + 1, header->ncols, header->nrows);
            } else {
                char bad[64] = "";
                if (fscanf(fp, "%63s", bad) != 1) {
                    bad[0] = '\0';
                }
                log_error("%s: 데이터 %d행 %d열의 값 '%s'는 숫자가 아님", path, row + 1, col + 1, bad);
            }
            free(data);
            fclose(fp);
            return 0;
        }
    }

    if (fscanf(fp, "%63s", extra) == 1) {
        log_warn("%s: 필요한 값(%d x %d개) 뒤에 값이 더 있음 — 무시함 ('%s'...)",
                 path, header->ncols, header->nrows, extra);
    }

    fclose(fp);
    *values = data;
    return 1;
}

/* NODATA 값인지 검사 (실수는 == 비교 대신 아주 작은 차이를 허용) */
static int is_nodata(const AscHeader *header, double value)
{
    return header->has_nodata && fabs(value - header->nodata) < 1e-6;
}

/* ================================================================
 * 지형(고도) 격자
 * ================================================================ */

/*
 * 시나리오의 고도 파일을 읽어 격자(sc->grid)를 만들고 고도를 채운다.
 * NODATA 셀은 탈 수 없는 바위로 처리하고 경고를 출력한다.
 * 성공 1, 실패 0
 */
int load_terrain(Scenario *sc)
{
    AscHeader header;
    double   *values;
    double    min_valid = 1e30;
    int       nodata_count = 0;
    int       x, y;

    if (!load_asc_grid(sc->elevation_file, &header, &values)) {
        return 0;
    }

    /* 1) 값 범위 검사 + NODATA가 아닌 값 중 최솟값 찾기 */
    for (y = 0; y < header.nrows; y++) {
        for (x = 0; x < header.ncols; x++) {
            double v = values[y * header.ncols + x];
            if (is_nodata(&header, v)) {
                nodata_count++;
                continue;
            }
            if (v < ELEVATION_MIN_ALLOWED || v > ELEVATION_MAX_ALLOWED) {
                log_error("%s: (%d, %d) 고도 %.1f m 가 허용 범위(%.0f ~ %.0f m)를 벗어남. 단위가 m인지 확인하세요",
                          sc->elevation_file, x, y, v, ELEVATION_MIN_ALLOWED, ELEVATION_MAX_ALLOWED);
                free(values);
                return 0;
            }
            if (v < min_valid) {
                min_valid = v;
            }
        }
    }
    if (nodata_count == header.ncols * header.nrows) {
        log_error("%s: 모든 셀이 NODATA임", sc->elevation_file);
        free(values);
        return 0;
    }

    /* 2) 격자 만들기 */
    if (!grid_create(&sc->grid, header.ncols, header.nrows, header.cellsize)) {
        free(values);
        return 0;
    }
    sc->grid.xll = header.xll;
    sc->grid.yll = header.yll;

    /* 3) 고도 채우기. .asc의 첫 줄이 북쪽이고 우리 격자도 y = 0이 북쪽이라 그대로 복사한다. */
    for (y = 0; y < header.nrows; y++) {
        for (x = 0; x < header.ncols; x++) {
            double v = values[y * header.ncols + x];
            Cell  *cell = &sc->grid.cells[y][x];
            if (is_nodata(&header, v)) {
                cell->elevation = min_valid;
                cell->state = CELL_ROCK;
            } else {
                cell->elevation = v;
            }
        }
    }
    free(values);

    if (nodata_count > 0) {
        log_warn("%s: NODATA 셀 %d개는 탈 수 없는 바위로 처리함", sc->elevation_file, nodata_count);
    }
    log_info("지형 읽기 완료: %d x %d 칸, 칸 크기 %.1f m (%.1f km x %.1f km)",
             header.ncols, header.nrows, header.cellsize,
             header.ncols * header.cellsize / 1000.0, header.nrows * header.cellsize / 1000.0);
    return 1;
}

/* ================================================================
 * 연료 격자
 * ================================================================ */

/* 연료 코드에 맞게 셀 상태를 정한다. (물·바위는 처음부터 탈 수 없는 상태) */
static void set_cell_fuel(Cell *cell, int code)
{
    cell->fuel_code = code;
    if (cell->state == CELL_ROCK) {
        cell->fuel_code = FUEL_CODE_ROCK;   /* 고도가 NODATA였던 셀은 바위 유지 */
    } else if (code == FUEL_CODE_WATER) {
        cell->state = CELL_WATER;
    } else if (code == FUEL_CODE_ROCK) {
        cell->state = CELL_ROCK;
    } else {
        cell->state = CELL_UNBURNED;
    }
}

/*
 * 시나리오의 연료 파일을 읽어 각 셀의 연료 코드를 채운다.
 * load_terrain을 먼저 호출해 격자가 만들어져 있어야 한다.
 * 연료 격자는 고도 격자와 크기·칸 크기가 같아야 하고, 값은 0 ~ 31 정수여야 한다.
 * 성공 1, 실패 0
 */
int load_fuel_map(Scenario *sc)
{
    AscHeader header;
    double   *values;
    int       nodata_count = 0;
    int       x, y;

    if (!load_asc_grid(sc->fuel_file, &header, &values)) {
        return 0;
    }

    if (header.ncols != sc->grid.width || header.nrows != sc->grid.height ||
        fabs(header.cellsize - sc->grid.cell_size_m) > 1e-6) {
        log_error("연료 격자(%d x %d, %.1f m)와 지형 격자(%d x %d, %.1f m)의 크기가 다름: %s",
                  header.ncols, header.nrows, header.cellsize,
                  sc->grid.width, sc->grid.height, sc->grid.cell_size_m, sc->fuel_file);
        free(values);
        return 0;
    }

    for (y = 0; y < header.nrows; y++) {
        for (x = 0; x < header.ncols; x++) {
            double v = values[y * header.ncols + x];
            int    code;

            if (is_nodata(&header, v)) {
                nodata_count++;
                set_cell_fuel(&sc->grid.cells[y][x], FUEL_CODE_NONE);
                continue;
            }
            code = round_to_int(v);
            if (fabs(v - (double)code) > 1e-6) {
                log_error("%s: (%d, %d) 연료 코드 %.3f 는 정수가 아님", sc->fuel_file, x, y, v);
                free(values);
                return 0;
            }
            if (code < 0 || code >= WF_MAX_FUELS) {
                log_error("%s: (%d, %d) 연료 코드 %d 는 범위(0 ~ %d)를 벗어남",
                          sc->fuel_file, x, y, code, WF_MAX_FUELS - 1);
                free(values);
                return 0;
            }
            set_cell_fuel(&sc->grid.cells[y][x], code);
        }
    }
    free(values);

    if (nodata_count > 0) {
        log_warn("%s: NODATA 셀 %d개는 연료 없음(코드 0)으로 처리함", sc->fuel_file, nodata_count);
    }
    log_info("연료 지도 읽기 완료: %s", sc->fuel_file);
    return 1;
}

/* ================================================================
 * 경사·경사 방향 계산
 * ================================================================ */

/* 격자 밖 좌표는 가장 가까운 가장자리 셀의 고도를 쓴다. (가장자리 셀 계산용) */
static double elevation_clamped(const Grid *grid, int x, int y)
{
    if (x < 0) {
        x = 0;
    }
    if (x >= grid->width) {
        x = grid->width - 1;
    }
    if (y < 0) {
        y = 0;
    }
    if (y >= grid->height) {
        y = grid->height - 1;
    }
    return grid->cells[y][x].elevation;
}

/*
 * 모든 셀의 경사(도)와 경사 방향(내리막 방위)을 계산한다. — Horn(1981) 방법
 *
 * 주변 3×3 고도를   a b c     (위쪽 행 = 북쪽)
 *                   d e f
 *                   g h i     (아래쪽 행 = 남쪽)
 * 라고 하면
 *   동쪽으로 갈 때 고도 변화율  dz_east  = ((c + 2f + i) - (a + 2d + g)) / (8 × 칸크기)
 *   남쪽으로 갈 때 고도 변화율  dz_south = ((g + 2h + i) - (a + 2b + c)) / (8 × 칸크기)
 *   경사 = atan( √(dz_east² + dz_south²) )
 *   내리막 방향 = 고도가 가장 빨리 낮아지는 방향 = (동쪽 성분 -dz_east, 북쪽 성분 +dz_south)
 *
 * 출처: Horn, B.K.P. (1981). Hill shading and the reflectance map. Proc. IEEE 69(1).
 */
void compute_slope_aspect(Grid *grid)
{
    int x, y;

    for (y = 0; y < grid->height; y++) {
        for (x = 0; x < grid->width; x++) {
            double a = elevation_clamped(grid, x - 1, y - 1);
            double b = elevation_clamped(grid, x,     y - 1);
            double c = elevation_clamped(grid, x + 1, y - 1);
            double d = elevation_clamped(grid, x - 1, y);
            double f = elevation_clamped(grid, x + 1, y);
            double g = elevation_clamped(grid, x - 1, y + 1);
            double h = elevation_clamped(grid, x,     y + 1);
            double i = elevation_clamped(grid, x + 1, y + 1);
            double size8 = 8.0 * grid->cell_size_m;
            double dz_east  = ((c + 2.0 * f + i) - (a + 2.0 * d + g)) / size8;
            double dz_south = ((g + 2.0 * h + i) - (a + 2.0 * b + c)) / size8;
            double gradient = sqrt(dz_east * dz_east + dz_south * dz_south);
            Cell  *cell = &grid->cells[y][x];

            cell->slope_deg = rad_to_deg(atan(gradient));

            if (gradient < 1e-6) {
                cell->aspect_deg = -1.0;   /* 평지: 방향 없음 */
            } else {
                /* atan2(동쪽 성분, 북쪽 성분) → 북=0, 동=90 인 방위각 */
                double azimuth = rad_to_deg(atan2(-dz_east, dz_south));
                cell->aspect_deg = normalize_angle_deg(azimuth);
            }
        }
    }
}
