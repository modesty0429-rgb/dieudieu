/*
 * suppression_eval.h
 * 진화 전략 비교: 대응 없음 / 방화선 / 헬기 / 방화선 + 헬기
 */
#ifndef SUPPRESSION_EVAL_H
#define SUPPRESSION_EVAL_H

#include "wf_types.h"
#include "evac_alert.h"
#include "suppression.h"

#define STRATEGY_COUNT 4

/* 전략 하나의 결과 */
typedef struct {
    const char *key;              /* 파일 이름용 영문 (none, firebreak, helicopter, both) */
    const char *name;             /* 화면 표시용 한국어 */
    int         use_firebreak;
    int         use_helicopters;
    double      burned_area_ha;   /* 피해 면적 */
    int         burned_cells;
    double      trail_burned_km;  /* 불이 지나간 등산로 길이 (셀 수 × 칸 크기, 근사) */
    int         spot_fires;
    double      reduction_pct;    /* 대응 없음 대비 피해 면적 감소율 (%) */
    EvacSummary evac;             /* 대피 결과 (위험 등산객 수 등) */
    HeliDrop   *drops;            /* 헬기 살수 기록 (동적 할당) */
    int         drop_count;
} StrategyResult;

/* 비교 전체 결과 */
typedef struct {
    FirebreakPlan  firebreak;
    StrategyResult strategies[STRATEGY_COUNT];
    double        *guide;         /* 헬기 목표 선택용 하위 가치 (기준 시뮬레이션) */
} SuppressionReport;

int  compare_strategies(Scenario *sc, unsigned int seed, SuppressionReport *report);
void free_suppression_report(SuppressionReport *report);
void print_strategy_table(const Scenario *sc, const SuppressionReport *report);

#endif /* SUPPRESSION_EVAL_H */
