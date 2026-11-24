/*
 * season.c
 * 사계절 날씨 특징 (9단계)
 *
 * [왜 필요한가]
 *   같은 산, 같은 발화 지점이라도 계절에 따라 산불은 전혀 다르게 번진다.
 *     봄   : 건조하고 바람이 강하다 → 국내 산불이 가장 많은 계절
 *     여름 : 덥고 습하며 잎이 무성하다 → 잘 번지지 않는다 (장마철은 제외하고 8월을 대표로)
 *     가을 : 다시 건조해지고 낙엽이 쌓인다 → 두 번째 산불 시기
 *     겨울 : 건조하지만 춥고, 높은 곳은 눈에 덮인다 → 눈 덮인 곳은 타지 않고 걷기도 힘들다
 *
 * [하루 동안의 변화]  — 계절 평년값 하나로 24시간 기상을 만든다
 *   기온  : T(h) = 평균 + 일교차/2 × cos(2π(h − 15)/24)       → 오후 3시 최고, 새벽 3시 최저 [가정]
 *   습도  : 하루 동안 이슬점(공기 속 수증기 양)이 같다고 보고, 기온에서 상대습도를 다시 계산한다
 *           → 기온이 오르는 낮에는 습도가 내려가고 밤에는 올라간다 (산불이 낮에 잘 번지는 이유)
 *           Magnus 식: es(T) = 6.1094 · exp(17.625·T / (T + 243.04))  [근거: Alduchov & Eskridge 1996]
 *           RH = 100 · es(이슬점) / es(T)
 *   바람  : 평균 × (1 + 0.35 cos(2π(h − 14)/24))                → 낮에 강하고 밤에 약함 [가정]
 *   풍향  : 계절풍 방향으로 고정 (겨울·가을 북서풍, 여름 남서풍, 봄 서풍) [근거: 우리나라 계절풍의 일반적 특징]
 *
 * [평년값 근거] 기상청 서울 기후평년값 1991~2020
 *   1월 평균기온 −1.9℃(가장 추운 달), 8월 26.1℃(가장 더운 달), 연평균 12.8℃
 *   평균 상대습도: 봄 56.3%, 여름 71.8%, 겨울 56.3%
 *   평균풍속은 3·4월이 연중 가장 크다
 *   나머지(일교차, 가을 값, 산 능선 풍속, 눈 경계 고도)는 [가정]
 */
#include <math.h>
#include <stdlib.h>

#include "season.h"
#include "util.h"
#include "log.h"

#define MAGNUS_A 17.625
#define MAGNUS_B 243.04    /* °C */

/*                 키        이름                     대표달  평균기온 일교차  습도   풍속  풍향   눈 경계 */
static const SeasonClimate CLIMATES[SEASON_COUNT] = {
    { "spring", "봄 (4월, 건조·강풍)",        4, 13.0, 11.0, 56.0, 6.0, 270.0,   0.0 },
    { "summer", "여름 (8월, 덥고 습함)",       8, 26.1,  7.0, 72.0, 2.5, 225.0,   0.0 },
    { "autumn", "가을 (10월, 건조·낙엽)",     10, 15.0, 10.0, 60.0, 4.0, 315.0,   0.0 },
    { "winter", "겨울 (1월, 건조·추위·눈)",    1, -1.9,  8.0, 56.0, 5.0, 315.0, 600.0 }
};

const SeasonClimate *season_climate(int season)
{
    if (season < 0 || season >= SEASON_COUNT) {
        return NULL;
    }
    return &CLIMATES[season];
}

const char *season_key(int season)
{
    const SeasonClimate *c = season_climate(season);
    return c != NULL ? c->key : "none";
}

/* 달 → 계절 (3~5 봄, 6~8 여름, 9~11 가을, 12~2 겨울) */
int season_from_month(int month)
{
    if (month >= 3 && month <= 5)  return SEASON_SPRING;
    if (month >= 6 && month <= 8)  return SEASON_SUMMER;
    if (month >= 9 && month <= 11) return SEASON_AUTUMN;
    return SEASON_WINTER;
}

/* "spring" / "봄" / "auto" / "none" → 계절 번호. 성공 1 */
int season_parse(const char *text, int *out)
{
    static const char *korean[SEASON_COUNT] = { "봄", "여름", "가을", "겨울" };
    int i;

    if (str_equals_ignore_case(text, "none")) {
        *out = SEASON_NONE;
        return 1;
    }
    if (str_equals_ignore_case(text, "auto")) {
        *out = SEASON_AUTO;
        return 1;
    }
    for (i = 0; i < SEASON_COUNT; i++) {
        if (str_equals_ignore_case(text, CLIMATES[i].key) || str_equals_ignore_case(text, korean[i])) {
            *out = i;
            return 1;
        }
    }
    return 0;
}

/*
 * 실제로 적용할 계절.
 *   season = auto 이거나, 기상 방식이 "season"인데 계절을 정하지 않았으면 시작 날짜의 달로 정한다.
 */
int season_effective(const Scenario *sc)
{
    int s = sc->season.season;
    if (s == SEASON_AUTO || (s == SEASON_NONE && sc->weather_mode == WEATHER_SEASON)) {
        return season_from_month(sc->start_time.month);
    }
    return s;
}

/*
 * 눈 경계 고도 (m). 0 이면 눈 없음.
 *   1) snow_line_m 을 직접 적으면 그 값 (어느 계절이든)
 *   2) 겨울이고 이 산의 winter_snow_line_m 이 있으면 그 값 (실제 산마다 눈 덮이는 높이가 다름)
 *   3) 아니면 계절 기본값 (겨울 600 m, 나머지 0)
 */
double season_snow_line(const Scenario *sc)
{
    int season = season_effective(sc);
    const SeasonClimate *c = season_climate(season);
    if (c == NULL) {
        return 0.0;
    }
    if (sc->season.snow_line_m >= 0.0) {
        return sc->season.snow_line_m;
    }
    if (season == SEASON_WINTER && sc->season.winter_snow_line_m >= 0.0) {
        return sc->season.winter_snow_line_m;
    }
    return c->snow_line_m;
}

/* 이 셀이 눈에 덮여 있으면 1 (겨울, 눈 경계보다 높은 곳) */
int cell_has_snow(const Scenario *sc, const Cell *cell)
{
    double line = season_snow_line(sc);
    return line > 0.0 && cell->elevation >= line;
}

int count_snow_cells(const Scenario *sc)
{
    int x, y, count = 0;
    if (season_snow_line(sc) <= 0.0) {
        return 0;
    }
    for (y = 0; y < sc->grid.height; y++) {
        for (x = 0; x < sc->grid.width; x++) {
            count += cell_has_snow(sc, &sc->grid.cells[y][x]);
        }
    }
    return count;
}

/* 포화 수증기압 (hPa) — Magnus 식 */
static double saturation_vapor_hpa(double temp_c)
{
    return 6.1094 * exp(MAGNUS_A * temp_c / (temp_c + MAGNUS_B));
}

/* 하루 평균 기온·습도로 이슬점 (°C)을 구한다 */
static double dew_point_c(double temp_c, double rh_pct)
{
    double alpha = log(rh_pct / 100.0) + MAGNUS_A * temp_c / (MAGNUS_B + temp_c);
    return MAGNUS_B * alpha / (MAGNUS_A - alpha);
}

/* 계절 평년값으로 시계 시각 clock_hour (0 ~ 24) 의 기상을 만든다 */
void season_weather_at_clock(const SeasonClimate *c, double clock_hour, WeatherRecord *out)
{
    double dew = dew_point_c(c->temp_mean_c, c->rh_mean_pct);
    double temp = c->temp_mean_c + 0.5 * c->temp_range_c * cos(2.0 * WF_PI * (clock_hour - 15.0) / 24.0);
    double rh = 100.0 * saturation_vapor_hpa(dew) / saturation_vapor_hpa(temp);

    out->temp_c = temp;
    out->rh_pct = clamp_double(rh, 5.0, 100.0);
    out->wind_speed_ms = c->wind_mean_ms * (1.0 + 0.35 * cos(2.0 * WF_PI * (clock_hour - 14.0) / 24.0));
    out->wind_dir_deg = c->wind_dir_deg;
}

/*
 * [weather] mode = season: 시뮬레이션 기간(+1시간)의 기상을 30분 간격으로 만들어
 * 기상 파일을 읽은 것과 똑같이 sc->weather 에 넣는다. (이후 보간·몬테카를로 흔들기는 그대로)
 */
int generate_season_weather(Scenario *sc)
{
    const SeasonClimate *c = season_climate(season_effective(sc));
    double start_hour = (double)sc->start_time.hour + (double)sc->start_time.minute / 60.0;
    double end_min = sc->sim.duration_min + 60.0;
    int    count = (int)(end_min / 30.0) + 1;
    int    i;

    if (c == NULL) {
        log_error("계절 기상: 계절을 정할 수 없음");
        return 0;
    }
    sc->weather.records = (WeatherRecord *)wf_malloc((size_t)count * sizeof(WeatherRecord), "계절 기상");
    if (sc->weather.records == NULL) {
        return 0;
    }
    for (i = 0; i < count; i++) {
        double t = 30.0 * i;
        WeatherRecord *r = &sc->weather.records[i];
        season_weather_at_clock(c, fmod(start_hour + t / 60.0, 24.0), r);
        r->time_min = t;
    }
    sc->weather.count = count;
    log_info("기상: %s 평년 기상으로 하루 변화 생성 (평균 %.1f°C, 일교차 %.0f°C, 습도 %.0f%%, 풍속 %.1f m/s, 풍향 %.0f°)",
             c->label, c->temp_mean_c, c->temp_range_c, c->rh_mean_pct, c->wind_mean_ms, c->wind_dir_deg);
    return 1;
}
