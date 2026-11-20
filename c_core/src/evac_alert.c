/*
 * evac_alert.c
 * 등산객 위치별 경보 단계를 판정하고, 대피 안내 전체 과정을 실행한다.
 *
 * [경보 단계] — 기준 시간은 시나리오 [evacuation] 에서 바꿀 수 있다
 *   남은 시간 = (등산객 주변 check_radius_m 안에 불이 처음 오는 시각) − 지금 시각
 *     남은 시간 ≥ 주의 기준(120분)     → 정상
 *     남은 시간 < 주의 기준            → 주의
 *     남은 시간 < 대피 준비 기준(60분) → 대피 준비   ← 이때 대피 출발
 *     남은 시간 < 즉시 대피 기준(30분) → 즉시 대피
 *     안전한 경로가 없음(최소 여유 < 0) / 갇힘 → 고립 (구조 요청)
 *
 * [대피 안내 순서] run_evacuation
 *   1) 위험 지도 2개 만들기: 경보용(반경 500 m), 경로용(반경 60 m)
 *   2) 등산객마다: 출발 시각 → 가장 안전한 경로 → 이동 기록 → 시간별 경보 기록
 *   3) 위험 등산객 수 세기
 */
#include <stdlib.h>
#include <math.h>

#include "evac_alert.h"
#include "evac_route.h"
#include "hiker.h"
#include "util.h"
#include "log.h"

#define SAMPLE_INTERVAL_MIN 1.0   /* 등산객 상태를 기록하는 간격 */

/* ================================================================
 * 이름
 * ================================================================ */

const char *alert_level_name(AlertLevel level)
{
    switch (level) {
    case ALERT_NONE:      return "NONE";
    case ALERT_CAUTION:   return "CAUTION";
    case ALERT_PREPARE:   return "PREPARE";
    case ALERT_IMMEDIATE: return "IMMEDIATE";
    case ALERT_ISOLATED:  return "ISOLATED";
    default:              return "UNKNOWN";
    }
}

const char *alert_level_korean(AlertLevel level)
{
    switch (level) {
    case ALERT_NONE:      return "정상";
    case ALERT_CAUTION:   return "주의";
    case ALERT_PREPARE:   return "대피준비";
    case ALERT_IMMEDIATE: return "즉시대피";
    case ALERT_ISOLATED:  return "고립";
    default:              return "?";
    }
}

const char *hiker_status_name(HikerStatus status)
{
    switch (status) {
    case HIKER_HIKING:     return "HIKING";
    case HIKER_EVACUATING: return "EVACUATING";
    case HIKER_SAFE:       return "SAFE";
    case HIKER_TRAPPED:    return "TRAPPED";
    default:               return "UNKNOWN";
    }
}

const char *hiker_status_korean(HikerStatus status)
{
    switch (status) {
    case HIKER_HIKING:     return "대피 불필요";
    case HIKER_EVACUATING: return "대피 중";
    case HIKER_SAFE:       return "대피 완료";
    case HIKER_TRAPPED:    return "고립";
    default:               return "?";
    }
}

/* ================================================================
 * 경보 판정
 * ================================================================ */

/* 남은 시간(분)으로 경보 단계를 정한다. 남은 시간이 음수면 불이 오지 않는다는 뜻 */
AlertLevel alert_level_from_remaining(const AlertSettings *settings, double remaining_min)
{
    if (remaining_min < 0.0 || remaining_min >= settings->caution_min) {
        return ALERT_NONE;
    }
    if (remaining_min >= settings->prepare_min) {
        return ALERT_CAUTION;
    }
    if (remaining_min >= settings->immediate_min) {
        return ALERT_PREPARE;
    }
    return ALERT_IMMEDIATE;
}

/*
 * (x, y) 위치 주변에 불이 오기까지 남은 시간 (분).
 * 이미 주변에 불이 있으면 0, 끝까지 불이 오지 않으면 -1.
 */
double remaining_time_at(const DangerMap *alert_map, double x, double y, double time_min)
{
    int    cx = round_to_int(x);
    int    cy = round_to_int(y);
    double danger;

    if (cx < 0) cx = 0;
    if (cy < 0) cy = 0;
    if (cx >= alert_map->width) cx = alert_map->width - 1;
    if (cy >= alert_map->height) cy = alert_map->height - 1;

    danger = danger_time_at(alert_map, cx, cy);
    if (danger >= DANGER_NONE) {
        return -1.0;
    }
    return (danger > time_min) ? danger - time_min : 0.0;
}

/*
 * 대피 출발 시각
 *   = max(경보를 낼 수 있는 시각, 시작 위치가 "대피 준비" 단계가 되는 시각)
 *   경보를 낼 수 있는 시각 = 가장 이른 발화 시각 + 발견·통보 지연(notify_delay_min)
 * 시작 위치 주변에 불이 끝까지 오지 않으면 대피할 필요가 없으므로 WF_NO_TIME.
 */
double compute_departure_time(const Scenario *sc, const DangerMap *alert_map, const Hiker *hiker)
{
    const TrailNode *start = &sc->trails.nodes[hiker->start_node];
    double           danger = danger_time_at(alert_map, start->x, start->y);
    double           first_ignition = sc->ignitions[0].time_min;
    double           notify_time, prepare_time;
    int              i;

    if (danger >= DANGER_NONE) {
        return WF_NO_TIME;
    }
    for (i = 1; i < sc->ignition_count; i++) {
        if (sc->ignitions[i].time_min < first_ignition) {
            first_ignition = sc->ignitions[i].time_min;
        }
    }
    notify_time = first_ignition + sc->alert.notify_delay_min;
    prepare_time = danger - sc->alert.prepare_min;
    return (prepare_time > notify_time) ? prepare_time : notify_time;
}

/*
 * assess_alert_level: 시각 time_min 에 이 등산객의 경보 단계를 판정한다.
 *   대피 완료 후 → 정상 / 고립된 뒤 → 고립 / 그 외 → 현재 위치의 남은 시간으로 판정
 * remaining_min 에 남은 시간(불이 안 오면 -1)을 돌려준다.
 */
AlertLevel assess_alert_level(const Scenario *sc, const Hiker *hiker, const DangerMap *alert_map,
                              double time_min, double *remaining_min)
{
    double x, y;

    hiker_position_at(hiker, time_min, &x, &y);
    *remaining_min = remaining_time_at(alert_map, x, y, time_min);

    if (time_is_set(hiker->finish_time_min) && time_min >= hiker->finish_time_min) {
        return (hiker->status == HIKER_TRAPPED) ? ALERT_ISOLATED : ALERT_NONE;
    }
    /* 출발할 때 이미 안전한 경로가 없다면(최소 여유 < 0) 그때부터 "고립 — 구조 요청" */
    if (time_is_set(hiker->depart_time_min) && time_min >= hiker->depart_time_min &&
        (!hiker->route.found || hiker->route.min_margin_min < 0.0)) {
        return ALERT_ISOLATED;
    }
    return alert_level_from_remaining(&sc->alert, *remaining_min);
}

/* 시각 time_min 의 등산객 상태 (출발 전 / 대피 중 / 완료·고립) */
static HikerStatus status_at(const Hiker *hiker, double time_min)
{
    if (!time_is_set(hiker->depart_time_min) || time_min < hiker->depart_time_min) {
        return HIKER_HIKING;
    }
    if (time_is_set(hiker->finish_time_min) && time_min >= hiker->finish_time_min) {
        return hiker->status;
    }
    return HIKER_EVACUATING;
}

/* 시뮬레이션 시간 동안 1분 간격으로 위치·경보·남은 시간을 기록한다. 성공 1, 실패 0 */
static int build_hiker_samples(const Scenario *sc, Hiker *hiker, const DangerMap *alert_map)
{
    double steps = floor(sc->sim.duration_min / SAMPLE_INTERVAL_MIN);
    int    count = (int)steps + 1;
    int    i;

    hiker->samples = (HikerSample *)wf_malloc((size_t)count * sizeof(HikerSample), "등산객 상태 기록");
    if (hiker->samples == NULL) {
        return 0;
    }
    for (i = 0; i < count; i++) {
        HikerSample *s = &hiker->samples[i];
        s->time_min = i * SAMPLE_INTERVAL_MIN;
        hiker_position_at(hiker, s->time_min, &s->x, &s->y);
        s->alert = assess_alert_level(sc, hiker, alert_map, s->time_min, &s->remaining_min);
        s->status = status_at(hiker, s->time_min);
    }
    hiker->sample_count = count;
    hiker->alert = hiker->samples[count - 1].alert;
    return 1;
}

/* 위험 등산객: 고립되었거나, 대피했지만 최소 여유가 즉시 대피 기준보다 작은 경우 */
int hiker_is_at_risk(const Scenario *sc, const Hiker *hiker)
{
    if (hiker->status == HIKER_TRAPPED) {
        return 1;
    }
    if (time_is_set(hiker->depart_time_min) && hiker->route.found &&
        hiker->route.min_margin_min < sc->alert.immediate_min) {
        return 1;
    }
    return 0;
}

/* ================================================================
 * 대피 안내 전체 실행
 * ================================================================ */

/*
 * run_evacuation: 확산 시뮬레이션이 끝난 격자(불 도착 시각)를 보고 모든 등산객의 대피를 계산한다.
 * 성공 1, 실패(메모리 부족) 0
 */
int run_evacuation(Scenario *sc, EvacSummary *summary)
{
    DangerMap alert_map, route_map;
    int       ok = 1;
    int       i;

    summary->hikers = summary->people = summary->evacuated = 0;
    summary->safe = summary->trapped = summary->at_risk_hikers = summary->at_risk_people = 0;
    if (sc->hiker_count == 0) {
        log_warn("등산객이 없어 대피 안내를 계산하지 않음");
        return 1;
    }

    /* 1) 위험 지도 */
    alert_map.time = NULL;
    route_map.time = NULL;
    if (!build_danger_map(&sc->grid, sc->alert.check_radius_m, &alert_map) ||
        !build_danger_map(&sc->grid, sc->alert.danger_radius_m, &route_map)) {
        free_danger_map(&alert_map);
        free_danger_map(&route_map);
        return 0;
    }

    /* 2) 등산객마다 계산 */
    for (i = 0; i < sc->hiker_count && ok; i++) {
        Hiker *h = &sc->hikers[i];
        double search_time;

        reset_hiker(h);
        h->depart_time_min = compute_departure_time(sc, &alert_map, h);
        /* 대피가 필요 없어도 "만약 대피한다면" 경로를 참고로 계산해 둔다 (경보 가능 시각 기준) */
        search_time = time_is_set(h->depart_time_min) ? h->depart_time_min
                                                      : sc->ignitions[0].time_min + sc->alert.notify_delay_min;
        if (find_safest_route(sc, &route_map, h->start_node, search_time, h->speed_kmh, &h->route) < 0) {
            ok = 0;
            break;
        }
        ok = build_hiker_track(sc, h) && build_hiker_samples(sc, h, &alert_map);

        summary->hikers++;
        summary->people += h->group_size;
        if (time_is_set(h->depart_time_min)) {
            summary->evacuated++;
        }
        if (h->status == HIKER_SAFE) {
            summary->safe++;
        } else if (h->status == HIKER_TRAPPED) {
            summary->trapped++;
        }
        if (hiker_is_at_risk(sc, h)) {
            summary->at_risk_hikers++;
            summary->at_risk_people += h->group_size;
        }
    }

    free_danger_map(&alert_map);
    free_danger_map(&route_map);
    return ok;
}
