/*
 * weather.c
 * 기상 CSV 파일을 읽고, 시뮬레이션 중 원하는 시각의 기상 값을 계산(보간)한다.
 *
 * [기상 CSV 형식]
 *   datetime,temp_c,rh_pct,wind_speed_ms,wind_dir_deg     ← 머리줄 (있어도 되고 없어도 됨)
 *   2026-04-05 13:00,18.5,25,6.2,280
 *
 * 기상 기록은 보통 1시간 간격이지만 시뮬레이션은 1분 간격이다.
 * 그래서 두 기록 사이의 값은 "선형 보간"으로 구한다.
 *   예) 13시 풍속 6 m/s, 14시 풍속 8 m/s → 13시 30분은 7 m/s
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "weather.h"
#include "util.h"
#include "log.h"

#define WEATHER_FIELD_COUNT 5

/* ================================================================
 * 읽기
 * ================================================================ */

/* 기록 배열에 한 줄을 추가한다. 공간이 모자라면 2배로 늘린다. 성공 1, 실패 0 */
static int append_record(WeatherSeries *series, int *capacity, const WeatherRecord *record)
{
    if (series->count == *capacity) {
        int            new_capacity = (*capacity == 0) ? 32 : *capacity * 2;
        WeatherRecord *grown = (WeatherRecord *)realloc(series->records,
                                                        (size_t)new_capacity * sizeof(WeatherRecord));
        if (grown == NULL) {
            log_error("메모리 부족: 기상 기록 %d개", new_capacity);
            return 0;
        }
        series->records = grown;
        *capacity = new_capacity;
    }
    series->records[series->count] = *record;
    series->count++;
    return 1;
}

/*
 * 기상 CSV 한 줄(쉼표로 나뉜 5개 값)을 해석한다.
 * 날짜는 시뮬레이션 시작 시각 기준 "몇 분 뒤"로 바꿔 저장한다.
 */
static int parse_weather_line(char *text, const char *path, int line_no,
                              const DateTime *start_time, WeatherRecord *record)
{
    char    *fields[WEATHER_FIELD_COUNT + 1];
    DateTime when;
    int      count = split_by_char(text, ',', fields, WEATHER_FIELD_COUNT + 1);

    if (count != WEATHER_FIELD_COUNT) {
        log_error("%s %d번째 줄: 값이 %d개여야 하는데 %d개임 (datetime,temp_c,rh_pct,wind_speed_ms,wind_dir_deg)",
                  path, line_no, WEATHER_FIELD_COUNT, count);
        return 0;
    }
    if (!parse_datetime(fields[0], &when)) {
        log_error("%s %d번째 줄: 날짜 '%s'는 'YYYY-MM-DD HH:MM' 형식이어야 함", path, line_no, fields[0]);
        return 0;
    }
    if (!parse_double_strict(fields[1], &record->temp_c) ||
        !parse_double_strict(fields[2], &record->rh_pct) ||
        !parse_double_strict(fields[3], &record->wind_speed_ms) ||
        !parse_double_strict(fields[4], &record->wind_dir_deg)) {
        log_error("%s %d번째 줄: 기온·습도·풍속·풍향은 숫자여야 함", path, line_no);
        return 0;
    }

    /* 값 범위 검사 */
    if (record->temp_c < -40.0 || record->temp_c > 50.0) {
        log_error("%s %d번째 줄: 기온 %.1f°C 가 범위(-40 ~ 50)를 벗어남", path, line_no, record->temp_c);
        return 0;
    }
    if (record->rh_pct < 0.0 || record->rh_pct > 100.0) {
        log_error("%s %d번째 줄: 습도 %.1f%% 가 범위(0 ~ 100)를 벗어남", path, line_no, record->rh_pct);
        return 0;
    }
    if (record->wind_speed_ms < 0.0 || record->wind_speed_ms > 60.0) {
        log_error("%s %d번째 줄: 풍속 %.1f m/s 가 범위(0 ~ 60)를 벗어남", path, line_no, record->wind_speed_ms);
        return 0;
    }
    if (record->wind_dir_deg < 0.0 || record->wind_dir_deg > 360.0) {
        log_error("%s %d번째 줄: 풍향 %.1f° 가 범위(0 ~ 360)를 벗어남", path, line_no, record->wind_dir_deg);
        return 0;
    }

    record->time_min = (double)(datetime_to_minutes(&when) - datetime_to_minutes(start_time));
    return 1;
}

/*
 * 기상 CSV 파일을 읽는다.
 * start_time: 시뮬레이션 시작 시각 (각 기록을 "시작 후 몇 분"으로 바꾸는 기준)
 * 기록은 시간 순서대로 있어야 한다. 성공 1, 실패 0
 */
int load_weather_csv(const char *path, const DateTime *start_time, WeatherSeries *series)
{
    FILE *fp;
    char  line[WF_LINE_MAX];
    int   line_no = 0;
    int   capacity = 0;
    int   result;

    series->records = NULL;
    series->count = 0;

    fp = fopen(path, "r");
    if (fp == NULL) {
        log_error("기상 파일을 열 수 없음: %s", path);
        return 0;
    }

    while ((result = read_text_line(fp, line, (int)sizeof(line), &line_no)) != 0) {
        WeatherRecord record;
        char         *text;

        if (result < 0) {
            log_error("%s %d번째 줄: 줄이 너무 김", path, line_no);
            fclose(fp);
            return 0;
        }
        strip_comment(line);
        text = str_trim(line);
        if (text[0] == '\0' || str_starts_with(text, "datetime")) {
            continue;   /* 빈 줄, 머리줄 */
        }
        if (!parse_weather_line(text, path, line_no, start_time, &record)) {
            fclose(fp);
            return 0;
        }
        if (series->count > 0 && record.time_min <= series->records[series->count - 1].time_min) {
            log_error("%s %d번째 줄: 시각이 앞 줄보다 늦어야 함 (시간 순서로 정렬해 주세요)", path, line_no);
            fclose(fp);
            return 0;
        }
        if (!append_record(series, &capacity, &record)) {
            fclose(fp);
            return 0;
        }
    }
    fclose(fp);

    if (series->count == 0) {
        log_error("%s: 기상 기록이 하나도 없음", path);
        return 0;
    }
    return 1;
}

/*
 * 시나리오 설정에 맞게 기상을 준비한다.
 * 파일 모드면 CSV를 읽고, 시뮬레이션 시간 전체를 덮는지 확인한다.
 */
int load_scenario_weather(Scenario *sc)
{
    const WeatherSeries *w = &sc->weather;

    if (sc->weather_mode == WEATHER_FIXED) {
        log_info("기상: 고정값 사용 (풍속 %.1f m/s, 풍향 %.0f°, 습도 %.0f%%)",
                 sc->fixed_weather.wind_speed_ms, sc->fixed_weather.wind_dir_deg, sc->fixed_weather.rh_pct);
        return 1;
    }
    if (!load_weather_csv(sc->weather_file, &sc->start_time, &sc->weather)) {
        return 0;
    }
    if (w->records[0].time_min > 0.0) {
        log_warn("기상 기록이 시작 시각보다 %.0f분 늦게 시작함 — 그 전은 첫 기록 값을 사용", w->records[0].time_min);
    }
    if (w->records[w->count - 1].time_min < sc->sim.duration_min) {
        log_warn("기상 기록이 %.0f분까지만 있음 — 그 뒤(%.0f분까지)는 마지막 기록 값을 사용",
                 w->records[w->count - 1].time_min, sc->sim.duration_min);
    }
    log_info("기상 읽기 완료: 기록 %d개 (%s)", w->count, sc->weather_file);
    return 1;
}

/* ================================================================
 * 보간
 * ================================================================ */

/*
 * 각도를 보간한다. 350°와 10° 사이의 중간은 180°가 아니라 0°여야 하므로
 * 두 각도의 차이를 -180 ~ 180 범위로 바꾼 뒤(가까운 쪽으로 돌기) 비율만큼 더한다.
 */
double interpolate_angle_deg(double from_deg, double to_deg, double ratio)
{
    double diff = normalize_angle_deg(to_deg - from_deg);   /* 0 ~ 360 */
    if (diff > 180.0) {
        diff -= 360.0;                                       /* -180 ~ 180 */
    }
    return normalize_angle_deg(from_deg + diff * ratio);
}

/* 두 값 사이를 ratio(0 ~ 1) 비율로 보간한다. */
static double lerp(double a, double b, double ratio)
{
    return a + (b - a) * ratio;
}

/*
 * time_min 시각의 기상을 구한다.
 *   1) 고정 모드면 고정값
 *   2) 기록 범위 밖이면 가장 가까운 끝 기록
 *   3) 그 사이면 앞뒤 두 기록을 선형 보간
 * offset이 NULL이 아니면 몬테카를로용 오차를 더한다.
 */
void get_weather_at(const Scenario *sc, double time_min, const WeatherOffset *offset, WeatherRecord *out)
{
    const WeatherSeries *w = &sc->weather;

    if (sc->weather_mode == WEATHER_FIXED || w->count == 0) {
        *out = sc->fixed_weather;
    } else if (time_min <= w->records[0].time_min) {
        *out = w->records[0];
    } else if (time_min >= w->records[w->count - 1].time_min) {
        *out = w->records[w->count - 1];
    } else {
        /* time_min을 사이에 둔 두 기록 찾기 (기록 수가 적어 처음부터 찾아도 충분히 빠름) */
        int i = 0;
        double ratio;
        const WeatherRecord *a;
        const WeatherRecord *b;

        while (w->records[i + 1].time_min < time_min) {
            i++;
        }
        a = &w->records[i];
        b = &w->records[i + 1];
        ratio = (time_min - a->time_min) / (b->time_min - a->time_min);

        out->temp_c = lerp(a->temp_c, b->temp_c, ratio);
        out->rh_pct = lerp(a->rh_pct, b->rh_pct, ratio);
        out->wind_speed_ms = lerp(a->wind_speed_ms, b->wind_speed_ms, ratio);
        out->wind_dir_deg = interpolate_angle_deg(a->wind_dir_deg, b->wind_dir_deg, ratio);
    }
    out->time_min = time_min;

    if (offset != NULL) {
        out->wind_speed_ms = clamp_double(out->wind_speed_ms + offset->wind_speed_ms, 0.0, 60.0);
        out->wind_dir_deg = normalize_angle_deg(out->wind_dir_deg + offset->wind_dir_deg);
        out->rh_pct = clamp_double(out->rh_pct + offset->rh_pct, 1.0, 100.0);
    }
}

void free_weather_series(WeatherSeries *series)
{
    free(series->records);
    series->records = NULL;
    series->count = 0;
}
