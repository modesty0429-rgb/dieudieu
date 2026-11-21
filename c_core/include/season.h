/*
 * season.h
 * 사계절 날씨 특징 (9단계)
 *   - 계절 평년 기상으로 하루 동안의 기온·습도·바람 변화를 만든다 ([weather] mode = season)
 *   - 겨울에는 높은 곳이 눈에 덮여 타지 않고, 눈길에서는 천천히 걷는다
 */
#ifndef SEASON_H
#define SEASON_H

#include "wf_types.h"

/* 계절 하나의 평년 기상 (하루 변화를 만드는 재료) */
typedef struct {
    const char *key;            /* spring / summer / autumn / winter */
    const char *label;          /* 한국어 이름 */
    int         month;          /* 대표 달 */
    double      temp_mean_c;    /* 하루 평균 기온 */
    double      temp_range_c;   /* 일교차 (최고 − 최저) */
    double      rh_mean_pct;    /* 하루 평균 상대습도 */
    double      wind_mean_ms;   /* 하루 평균 풍속 (산 능선 기준) */
    double      wind_dir_deg;   /* 주로 부는 바람이 불어오는 방위 */
    double      snow_line_m;    /* 이 고도 이상은 눈이 쌓여 있음 (0 = 눈 없음) */
} SeasonClimate;

const SeasonClimate *season_climate(int season);
int    season_effective(const Scenario *sc);
int    season_from_month(int month);
int    season_parse(const char *text, int *out);
const char *season_key(int season);
double season_snow_line(const Scenario *sc);
int    cell_has_snow(const Scenario *sc, const Cell *cell);
int    count_snow_cells(const Scenario *sc);
int    generate_season_weather(Scenario *sc);
void   season_weather_at_clock(const SeasonClimate *c, double clock_hour, WeatherRecord *out);

#endif /* SEASON_H */
