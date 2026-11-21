/*
 * daylight.c
 * 낮/밤 계산 (8단계)
 *
 * [왜 필요한가]
 *   산불은 밤에도 번지지만, 사람이 할 수 있는 일은 밤에 크게 줄어든다.
 *     1) 등산객: 어두운 산길은 헤드랜턴에 의지해 천천히 걸어야 한다 → 대피가 느려짐
 *     2) 진화 헬기: 국내 산불 진화 헬기는 해가 지면 철수하고 다음 날 일출 후 다시 뜬다
 *   그래서 "같은 불이라도 저녁에 나면 더 위험하다"를 계산에 반영한다.
 *   (밤에 기온이 내려가고 습도가 올라 불이 느려지는 효과는 기상 파일의 시간별 값으로 이미 반영된다)
 *
 * [태양 고도 계산] — NOAA "General Solar Position Calculations" 의 근사식
 *   1) 그해의 몇 번째 날인지(N)와 시각으로 "연중 각도" γ 를 구한다.
 *   2) γ 로 태양 적위 δ(태양이 적도에서 남북으로 얼마나 치우쳤나)와
 *      균시차 EoT(시계 시각과 실제 태양 시각의 차이, 분)를 구한다.
 *   3) 진태양시 = 시계 시각 + EoT + 4 × 경도 − 60 × 표준시(한국 +9)
 *      시간각 H = 진태양시 / 4 − 180   (정오면 0°, 1시간마다 15°)
 *   4) sin(고도) = sin(위도)·sin(δ) + cos(위도)·cos(δ)·cos(H)
 *   출처: NOAA Global Monitoring Laboratory, General Solar Position Calculations
 *         (Spencer, J.W. (1971) 의 푸리에 급수 근사를 사용)
 *
 * [밝기와 보행 속도]
 *   해 고도 ≥ −0.833°(해가 떠 있음)  → 낮: 보행 속도 그대로
 *   해 고도 ≤ −6°(시민박명 끝)       → 밤: 보행 속도 × night_walk_factor [가정 0.6]
 *   그 사이(박명)                     → 직선으로 이어 붙임
 */
#include <math.h>
#include <stdio.h>

#include "daylight.h"
#include "util.h"
#include "log.h"

#define MINUTES_PER_DAY 1440.0

/* 그해의 몇 번째 날인지 (1월 1일 = 1) */
static int day_of_year(int year, int month, int day)
{
    int n = day;
    int m;
    for (m = 1; m < month; m++) {
        n += days_in_month(year, m);
    }
    return n;
}

/*
 * 시뮬레이션 시각 t_min 의 (연중 날짜 N, 그날 0시부터 지난 분)을 구한다.
 * 자정을 넘기면 다음 날로 넘어간다.
 */
static void date_and_clock_at(const Scenario *sc, double t_min, int *doy, double *clock_min)
{
    const DateTime *s = &sc->start_time;
    double total = (double)(s->hour * 60 + s->minute) + t_min;   /* 시작 날 0시부터 지난 분 */
    double days = floor(total / MINUTES_PER_DAY);
    int    year_days = (days_in_month(s->year, 2) == 29) ? 366 : 365;
    int    n = day_of_year(s->year, s->month, s->day) + (int)days;

    while (n > year_days) {
        n -= year_days;          /* 해를 넘기면 1월로 (해마다 날짜 차이는 무시할 만큼 작음) */
    }
    while (n < 1) {
        n += year_days;
    }
    *doy = n;
    *clock_min = total - days * MINUTES_PER_DAY;
}

/* 시뮬레이션 시각 t_min 의 태양 고도 (도). 지평선 위 +, 아래 − */
double solar_elevation_deg(const Scenario *sc, double t_min)
{
    const DaylightSettings *d = &sc->daylight;
    int    doy;
    double clock_min, gamma, eot, decl, solar_min, hour_angle, lat, sin_elev;

    date_and_clock_at(sc, t_min, &doy, &clock_min);

    /* 1) 연중 각도 (라디안) */
    gamma = 2.0 * WF_PI / 365.0 * ((double)doy - 1.0 + (clock_min / 60.0 - 12.0) / 24.0);

    /* 2) 균시차 (분)와 태양 적위 (라디안) */
    eot = 229.18 * (0.000075 + 0.001868 * cos(gamma) - 0.032077 * sin(gamma)
                    - 0.014615 * cos(2.0 * gamma) - 0.040849 * sin(2.0 * gamma));
    decl = 0.006918 - 0.399912 * cos(gamma) + 0.070257 * sin(gamma)
           - 0.006758 * cos(2.0 * gamma) + 0.000907 * sin(2.0 * gamma)
           - 0.002697 * cos(3.0 * gamma) + 0.00148 * sin(3.0 * gamma);

    /* 3) 진태양시 (분)와 시간각 (도) */
    solar_min = clock_min + eot + 4.0 * d->longitude_deg - 60.0 * d->utc_offset_h;
    hour_angle = solar_min / 4.0 - 180.0;

    /* 4) 고도 */
    lat = deg_to_rad(d->latitude_deg);
    sin_elev = sin(lat) * sin(decl) + cos(lat) * cos(decl) * cos(deg_to_rad(hour_angle));
    return rad_to_deg(asin(clamp_double(sin_elev, -1.0, 1.0)));
}

/* 화면 밝기용 값: 해 고도 −6° 이하 0(밤) ~ +6° 이상 1(낮) */
double daylight_level(double elevation_deg)
{
    return clamp_double((elevation_deg - CIVIL_TWILIGHT_DEG) / 12.0, 0.0, 1.0);
}

/* 시각 t_min 에 걷는 속도 배율 (낮 1.0, 밤 night_walk_factor, 박명은 그 사이) */
double walk_speed_factor(const Scenario *sc, double t_min)
{
    const DaylightSettings *d = &sc->daylight;
    double elev, ratio;

    if (!d->enabled || d->night_walk_factor >= 1.0) {
        return 1.0;
    }
    elev = solar_elevation_deg(sc, t_min);
    if (elev >= SUN_HORIZON_DEG) {
        return 1.0;
    }
    if (elev <= CIVIL_TWILIGHT_DEG) {
        return d->night_walk_factor;
    }
    /* 박명: 일몰(1.0) → 시민박명 끝(night_walk_factor) 사이를 직선으로 */
    ratio = (elev - CIVIL_TWILIGHT_DEG) / (SUN_HORIZON_DEG - CIVIL_TWILIGHT_DEG);
    return d->night_walk_factor + (1.0 - d->night_walk_factor) * ratio;
}

/* 시각 t_min 에 헬기가 뜰 수 있으면 1 (해가 떠 있을 때만) */
int helicopter_can_fly(const Scenario *sc, double t_min)
{
    if (!sc->daylight.enabled || !sc->daylight.heli_day_only) {
        return 1;
    }
    return solar_elevation_deg(sc, t_min) > SUN_HORIZON_DEG;
}

/* 고도가 기준선을 지나간 정확한 시각 (두 시각 사이 선형 보간) */
static double crossing_time(double t0, double e0, double t1, double e1, double level)
{
    if (e1 == e0) {
        return t1;
    }
    return t0 + (level - e0) * (t1 - t0) / (e1 - e0);
}

/*
 * 0 ~ end_min 사이의 일몰·박명·일출 시각을 찾는다. (1분 간격으로 고도를 계산해 기준선을 지나는 곳)
 * 반환: 찾은 사건 수
 */
int find_day_events(const Scenario *sc, double end_min, DayEvent *events, int max_events)
{
    double prev_t = 0.0;
    double prev_e = solar_elevation_deg(sc, 0.0);
    double t;
    int    count = 0;

    for (t = 1.0; t <= end_min + 1e-9 && count < max_events; t += 1.0) {
        double e = solar_elevation_deg(sc, t);

        if (prev_e > SUN_HORIZON_DEG && e <= SUN_HORIZON_DEG && count < max_events) {
            events[count].type = DAY_EVENT_SUNSET;
            events[count++].time_min = crossing_time(prev_t, prev_e, t, e, SUN_HORIZON_DEG);
        }
        if (prev_e > CIVIL_TWILIGHT_DEG && e <= CIVIL_TWILIGHT_DEG && count < max_events) {
            events[count].type = DAY_EVENT_DUSK;
            events[count++].time_min = crossing_time(prev_t, prev_e, t, e, CIVIL_TWILIGHT_DEG);
        }
        if (prev_e < CIVIL_TWILIGHT_DEG && e >= CIVIL_TWILIGHT_DEG && count < max_events) {
            events[count].type = DAY_EVENT_DAWN;
            events[count++].time_min = crossing_time(prev_t, prev_e, t, e, CIVIL_TWILIGHT_DEG);
        }
        if (prev_e < SUN_HORIZON_DEG && e >= SUN_HORIZON_DEG && count < max_events) {
            events[count].type = DAY_EVENT_SUNRISE;
            events[count++].time_min = crossing_time(prev_t, prev_e, t, e, SUN_HORIZON_DEG);
        }
        prev_t = t;
        prev_e = e;
    }
    return count;
}

const char *day_event_key(DayEventType type)
{
    switch (type) {
    case DAY_EVENT_SUNSET:  return "sunset";
    case DAY_EVENT_DUSK:    return "dusk";
    case DAY_EVENT_DAWN:    return "dawn";
    case DAY_EVENT_SUNRISE: return "sunrise";
    }
    return "unknown";
}

const char *day_event_label(DayEventType type)
{
    switch (type) {
    case DAY_EVENT_SUNSET:  return "일몰";
    case DAY_EVENT_DUSK:    return "완전히 어두워짐";
    case DAY_EVENT_DAWN:    return "밝아지기 시작";
    case DAY_EVENT_SUNRISE: return "일출";
    }
    return "?";
}

/* 시뮬레이션 시각 t_min 의 시계 시각 "HH:MM" */
void format_clock_at(const Scenario *sc, double t_min, char *out, size_t out_size)
{
    int    doy;
    double clock_min;
    int    rounded;

    date_and_clock_at(sc, t_min, &doy, &clock_min);
    rounded = round_to_int(clock_min) % 1440;
    snprintf(out, out_size, "%02d:%02d", rounded / 60, rounded % 60);
}

/* 시뮬레이션 기간의 낮/밤 정보를 로그로 출력한다. */
void log_day_events(const Scenario *sc, double end_min)
{
    DayEvent events[MAX_DAY_EVENTS];
    int      count, i;
    char     clock[8];

    if (!sc->daylight.enabled) {
        log_info("낮/밤: 반영하지 않음 ([daylight] enabled = 0)");
        return;
    }
    count = find_day_events(sc, end_min, events, MAX_DAY_EVENTS);
    if (count == 0) {
        log_info("낮/밤: 시뮬레이션 동안 계속 %s (위도 %.2f°)",
                 solar_elevation_deg(sc, 0.0) > SUN_HORIZON_DEG ? "낮" : "밤", sc->daylight.latitude_deg);
        return;
    }
    for (i = 0; i < count; i++) {
        format_clock_at(sc, events[i].time_min, clock, sizeof(clock));
        log_info("낮/밤: %s %s (T+%.0f분)", clock, day_event_label(events[i].type), events[i].time_min);
    }
    log_info("낮/밤: 밤에는 보행 속도 %.0f%%%s", sc->daylight.night_walk_factor * 100.0,
             sc->daylight.heli_day_only ? ", 해가 진 뒤 헬기 출동 중지" : "");
}
