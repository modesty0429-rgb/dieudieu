/*
 * daylight.h
 * 낮/밤 계산: 시뮬레이션 시각의 태양 고도, 밝기, 야간 보행 속도, 헬기 운항 가능 여부,
 * 그리고 일몰·일출·박명 시각.
 */
#ifndef DAYLIGHT_H
#define DAYLIGHT_H

#include "wf_types.h"

/* 해가 떠 있다고 보는 기준 고도 (대기 굴절과 해의 반지름을 반영한 일출·일몰 기준) */
#define SUN_HORIZON_DEG   (-0.833)
/* 시민박명 기준: 해가 이보다 낮으면 조명 없이는 길이 잘 보이지 않는 "밤" */
#define CIVIL_TWILIGHT_DEG (-6.0)

/* 낮/밤이 바뀌는 사건 */
typedef enum {
    DAY_EVENT_SUNSET = 0,   /* 일몰 (해가 지평선 아래로) */
    DAY_EVENT_DUSK,         /* 저녁 박명 끝 (완전히 어두워짐) */
    DAY_EVENT_DAWN,         /* 새벽 박명 시작 (밝아지기 시작) */
    DAY_EVENT_SUNRISE       /* 일출 */
} DayEventType;

typedef struct {
    DayEventType type;
    double       time_min;  /* 시뮬레이션 시작 후 몇 분 */
} DayEvent;

#define MAX_DAY_EVENTS 16

double      solar_elevation_deg(const Scenario *sc, double t_min);
double      daylight_level(double elevation_deg);
double      walk_speed_factor(const Scenario *sc, double t_min);
int         helicopter_can_fly(const Scenario *sc, double t_min);
int         find_day_events(const Scenario *sc, double end_min, DayEvent *events, int max_events);
const char *day_event_key(DayEventType type);
const char *day_event_label(DayEventType type);
void        format_clock_at(const Scenario *sc, double t_min, char *out, size_t out_size);
void        log_day_events(const Scenario *sc, double end_min);

#endif /* DAYLIGHT_H */
