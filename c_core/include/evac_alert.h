/*
 * evac_alert.h
 * 경보 단계 판정과 대피 안내 전체 실행.
 */
#ifndef EVAC_ALERT_H
#define EVAC_ALERT_H

#include "wf_types.h"
#include "evac_route.h"

/* 대피 결과 요약 */
typedef struct {
    int hikers;             /* 전체 팀 수 */
    int people;             /* 전체 인원 */
    int evacuated;          /* 대피가 필요했던 팀 수 */
    int safe;               /* 대피 완료 팀 수 */
    int trapped;            /* 고립 팀 수 */
    int at_risk_hikers;     /* 위험 팀 수: 고립 또는 최소 여유 < 즉시 대피 기준 */
    int at_risk_people;     /* 위험 인원 */
} EvacSummary;

const char *alert_level_name(AlertLevel level);
const char *alert_level_korean(AlertLevel level);
const char *hiker_status_name(HikerStatus status);
const char *hiker_status_korean(HikerStatus status);

AlertLevel alert_level_from_remaining(const AlertSettings *settings, double remaining_min);
double     remaining_time_at(const DangerMap *alert_map, double x, double y, double time_min);
double     compute_departure_time(const Scenario *sc, const DangerMap *alert_map, const Hiker *hiker);
AlertLevel assess_alert_level(const Scenario *sc, const Hiker *hiker, const DangerMap *alert_map,
                              double time_min, double *remaining_min);
int        hiker_is_at_risk(const Scenario *sc, const Hiker *hiker);
int        run_evacuation(Scenario *sc, EvacSummary *summary);

#endif /* EVAC_ALERT_H */
