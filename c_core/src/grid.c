/*
 * grid.c
 * 2차원 격자의 생성·해제와 8방향 이웃 계산.
 *
 * [2차원 동적 배열 만드는 방법]
 *   1) 행 포인터 배열을 만든다:  cells = malloc(height × sizeof(Cell *))
 *   2) 각 행을 만든다:          cells[y] = malloc(width × sizeof(Cell))
 *   그러면 grid->cells[y][x] 처럼 일반 2차원 배열과 같은 모양으로 쓸 수 있다.
 *   해제는 반대 순서: 각 행을 free → 행 포인터 배열을 free.
 */
#include <stdlib.h>
#include <math.h>

#include "grid.h"
#include "util.h"
#include "log.h"

/*
 * 8방향 이웃의 x, y 변화량. 방향 번호는 북쪽(0)부터 시계방향.
 * y가 커질수록 남쪽이므로 북쪽은 dy = -1 이다.
 */
static const int DIR_DX[GRID_DIRECTIONS] = {  0,  1, 1, 1, 0, -1, -1, -1 };
static const int DIR_DY[GRID_DIRECTIONS] = { -1, -1, 0, 1, 1,  1,  0, -1 };
static const char *DIR_NAMES[GRID_DIRECTIONS] = {
    "북", "북동", "동", "남동", "남", "남서", "서", "북서"
};

/* 셀 하나를 "아무 일도 일어나지 않은" 상태로 초기화한다. */
static void reset_cell_fire_state(Cell *cell)
{
    int dir;

    cell->arrival_time = WF_NO_TIME;
    cell->burnout_time = WF_NO_TIME;
    for (dir = 0; dir < GRID_DIRECTIONS; dir++) {
        cell->progress[dir] = 0.0;
    }
    cell->parent_index = -1;
    cell->ignited_by_spot = 0;
    cell->wet_until = WF_NO_TIME;
}

/* 셀의 모든 값을 기본값으로 채운다. */
static void init_cell(Cell *cell)
{
    cell->elevation = 0.0;
    cell->slope_deg = 0.0;
    cell->aspect_deg = -1.0;
    cell->fuel_code = FUEL_CODE_NONE;
    cell->fuel_moisture = 0.0;
    cell->state = CELL_UNBURNED;
    reset_cell_fire_state(cell);
}

/*
 * width × height 크기의 격자를 만든다.
 * 성공 1, 실패 0 (실패하면 이미 할당한 메모리는 모두 해제된다)
 */
int grid_create(Grid *grid, int width, int height, double cell_size_m)
{
    int x, y;

    grid->width = 0;
    grid->height = 0;
    grid->cells = NULL;

    if (width <= 0 || height <= 0 || width > WF_MAX_GRID_SIZE || height > WF_MAX_GRID_SIZE) {
        log_error("격자 크기 %d x %d 는 허용 범위(1 ~ %d)를 벗어남", width, height, WF_MAX_GRID_SIZE);
        return 0;
    }

    /* 1) 행 포인터 배열 할당. calloc을 써서 모든 포인터를 NULL로 시작한다. */
    grid->cells = (Cell **)wf_calloc((size_t)height, sizeof(Cell *), "격자 행 포인터 배열");
    if (grid->cells == NULL) {
        return 0;
    }
    grid->width = width;
    grid->height = height;
    grid->cell_size_m = cell_size_m;
    grid->xll = 0.0;
    grid->yll = 0.0;

    /* 2) 각 행 할당 */
    for (y = 0; y < height; y++) {
        grid->cells[y] = (Cell *)wf_malloc((size_t)width * sizeof(Cell), "격자 행");
        if (grid->cells[y] == NULL) {
            grid_free(grid);   /* 중간에 실패하면 지금까지 만든 행을 모두 해제 */
            return 0;
        }
        for (x = 0; x < width; x++) {
            init_cell(&grid->cells[y][x]);
        }
    }
    return 1;
}

/* 격자 메모리를 모두 해제한다. 두 번 호출해도 안전하다. */
void grid_free(Grid *grid)
{
    int y;

    if (grid->cells != NULL) {
        for (y = 0; y < grid->height; y++) {
            free(grid->cells[y]);   /* free(NULL)은 아무 일도 하지 않으므로 안전 */
        }
        free(grid->cells);
    }
    grid->cells = NULL;
    grid->width = 0;
    grid->height = 0;
}

/* (x, y)가 격자 안이면 1 */
int grid_in_bounds(const Grid *grid, int x, int y)
{
    return x >= 0 && x < grid->width && y >= 0 && y < grid->height;
}

/* (x, y) 셀을 하나의 번호로 바꾼다. 셀을 정수 하나로 저장할 때 쓴다. */
int grid_cell_index(const Grid *grid, int x, int y)
{
    return y * grid->width + x;
}

int grid_neighbor_dx(int dir)
{
    return DIR_DX[dir];
}

int grid_neighbor_dy(int dir)
{
    return DIR_DY[dir];
}

/* dir 방향 이웃 셀 중심까지의 거리 (m). 상하좌우는 칸 크기, 대각선은 칸 크기 × √2 */
double grid_neighbor_distance(const Grid *grid, int dir)
{
    if (dir % 2 == 0) {
        return grid->cell_size_m;
    }
    return grid->cell_size_m * sqrt(2.0);
}

/* dir 방향의 방위각 (북=0, 동=90, 남=180, 서=270) */
double grid_direction_azimuth(int dir)
{
    return 45.0 * (double)dir;
}

/* dir 방향의 한국어 이름 */
const char *grid_direction_name(int dir)
{
    if (dir < 0 || dir >= GRID_DIRECTIONS) {
        return "?";
    }
    return DIR_NAMES[dir];
}

/*
 * 모든 셀의 화재 기록(도착 시각, 진행 거리 등)을 지운다.
 * 연소 중·전소 셀은 다시 "정상"으로 되돌린다. 물·바위·방화선은 그대로 둔다.
 * 같은 지도로 시뮬레이션을 여러 번 돌릴 때(몬테카를로, 진화 전략 비교) 사용한다.
 */
void grid_reset_fire_state(Grid *grid)
{
    int x, y;

    for (y = 0; y < grid->height; y++) {
        for (x = 0; x < grid->width; x++) {
            Cell *cell = &grid->cells[y][x];
            if (cell->state == CELL_BURNING || cell->state == CELL_BURNED) {
                cell->state = CELL_UNBURNED;
            }
            reset_cell_fire_state(cell);
        }
    }
}

/* 셀의 상태가 불이 붙을 수 있는 상태(정상)이면 1. 연료 종류는 따로 검사해야 한다. */
int cell_is_burnable_state(const Cell *cell)
{
    return cell->state == CELL_UNBURNED;
}
