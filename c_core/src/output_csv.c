/*
 * output_csv.c
 * 시뮬레이션 결과를 CSV(쉼표로 구분한 텍스트) 파일로 저장한다.
 * Python GUI가 이 파일들을 읽어 애니메이션과 그래프를 그린다.
 *
 *   arrival_time.csv : 셀별 불 도착 시각 (분), 도착하지 않았으면 -1   ← 행 = y (첫 행이 북쪽)
 *   burnout_time.csv : 셀별 전소 시각 (분), 전소되지 않았으면 -1
 *   fire_events.csv  : time_min,x,y,state — 상태가 바뀐 셀만 시간순으로 기록
 *   stats.csv        : 출력 간격마다의 통계
 *
 * GUI는 "도착 시각 ≤ t < 전소 시각 → 연소 중", "전소 시각 ≤ t → 전소" 규칙으로
 * 아무 시각 t의 화재 모습을 바로 다시 그릴 수 있다.
 */
#include <stdio.h>
#include <stdlib.h>

#include "output_csv.h"
#include "util.h"
#include "log.h"

/* 셀 상태의 영문 이름 (CSV에 저장할 때 사용) */
const char *cell_state_name(CellState state)
{
    switch (state) {
    case CELL_UNBURNED:  return "unburned";
    case CELL_BURNING:   return "burning";
    case CELL_BURNED:    return "burned";
    case CELL_FIREBREAK: return "firebreak";
    case CELL_WATER:     return "water";
    case CELL_ROCK:      return "rock";
    default:             return "unknown";
    }
}

/* 쓰기용으로 파일을 열고, 실패하면 오류를 출력한다. */
static FILE *open_for_write(const char *path)
{
    FILE *fp = fopen(path, "w");
    if (fp == NULL) {
        log_error("결과 파일을 만들 수 없음: %s (폴더가 있는지, 다른 프로그램이 열고 있지 않은지 확인)", path);
    }
    return fp;
}

/* 파일을 닫고, 쓰는 도중 오류(디스크 가득 참 등)가 있었는지 확인한다. */
static int close_checked(FILE *fp, const char *path)
{
    int had_error = ferror(fp);
    if (fclose(fp) != 0 || had_error) {
        log_error("결과 파일 저장 중 오류: %s", path);
        return 0;
    }
    return 1;
}

/*
 * 격자 값을 CSV로 저장한다. 한 줄 = 격자 한 행(y), 첫 줄이 북쪽.
 * 값이 없는 셀은 -1, 있는 셀은 소수 둘째 자리까지 저장한다.
 */
int write_grid_csv(const char *path, const Grid *grid, GridValueKind kind)
{
    FILE *fp = open_for_write(path);
    int   x, y;

    if (fp == NULL) {
        return 0;
    }
    for (y = 0; y < grid->height; y++) {
        for (x = 0; x < grid->width; x++) {
            const Cell *cell = &grid->cells[y][x];
            double      value = (kind == GRID_VALUE_ARRIVAL) ? cell->arrival_time : cell->burnout_time;

            if (x > 0) {
                fputc(',', fp);
            }
            if (!time_is_set(value)) {
                fputs("-1", fp);
            } else {
                fprintf(fp, "%.2f", value);
            }
        }
        fputc('\n', fp);
    }
    return close_checked(fp, path);
}

/* 비교 함수: 이벤트를 시각 순서로 정렬하기 위해 qsort에 넘긴다. */
static int compare_events(const void *a, const void *b)
{
    const FireEvent *ea = (const FireEvent *)a;
    const FireEvent *eb = (const FireEvent *)b;

    if (ea->time_min < eb->time_min) return -1;
    if (ea->time_min > eb->time_min) return 1;
    return (int)ea->new_state - (int)eb->new_state;   /* 같은 시각이면 점화가 먼저 */
}

/*
 * 화재 이벤트(상태 변화)를 시간순으로 저장한다.
 * 한 단계 안에서도 셀마다 도착 시각이 달라 기록 순서가 시간순이 아닐 수 있으므로 정렬한다.
 * (정렬은 결과 구조체를 바꾸지 않도록 복사본에서 한다)
 */
int write_fire_events_csv(const char *path, const SimResult *res)
{
    FireEvent *sorted;
    FILE      *fp;
    int        i;

    sorted = (FireEvent *)malloc((size_t)(res->event_count > 0 ? res->event_count : 1) * sizeof(FireEvent));
    if (sorted == NULL) {
        log_error("메모리 부족: 이벤트 정렬");
        return 0;
    }
    for (i = 0; i < res->event_count; i++) {
        sorted[i] = res->events[i];
    }
    qsort(sorted, (size_t)res->event_count, sizeof(FireEvent), compare_events);

    fp = open_for_write(path);
    if (fp == NULL) {
        free(sorted);
        return 0;
    }
    fprintf(fp, "time_min,x,y,state\n");
    for (i = 0; i < res->event_count; i++) {
        fprintf(fp, "%.2f,%d,%d,%s\n", sorted[i].time_min, sorted[i].x, sorted[i].y,
                cell_state_name(sorted[i].new_state));
    }
    free(sorted);
    return close_checked(fp, path);
}

/* 출력 간격별 통계를 저장한다. (GUI의 그래프용) */
int write_stats_csv(const char *path, const SimResult *res)
{
    FILE *fp = open_for_write(path);
    int   i;

    if (fp == NULL) {
        return 0;
    }
    fprintf(fp, "time_min,burning_cells,burned_cells,burned_area_ha,max_spread_rate_m_min,"
                "spot_fires,temp_c,rh_pct,wind_speed_ms,wind_dir_deg,dead_moisture_pct\n");
    for (i = 0; i < res->step_count; i++) {
        const StepStats *s = &res->steps[i];
        fprintf(fp, "%.1f,%d,%d,%.2f,%.3f,%d,%.1f,%.1f,%.2f,%.1f,%.2f\n",
                s->time_min, s->burning_cells, s->burned_cells, s->burned_area_ha,
                s->max_spread_rate_m_min, s->spot_fires, s->weather.temp_c, s->weather.rh_pct,
                s->weather.wind_speed_ms, s->weather.wind_dir_deg, s->dead_moisture_pct);
    }
    return close_checked(fp, path);
}
