/*
 * suppression.h
 * 진화 전략: 방화선 배치 최적화(탐욕법)와 헬기 살수 목표 선택.
 */
#ifndef SUPPRESSION_H
#define SUPPRESSION_H

#include "wf_types.h"
#include "dynarray.h"
#include "spread_sim.h"

#define FIREBREAK_SEGMENT_LENGTH  5    /* 방화선 조각 하나의 길이 (칸) */
#define FIREBREAK_CANDIDATES      3    /* 매 단계 실제로 시뮬레이션해 볼 후보 수 */
#define TRAIL_CELL_WEIGHT        10.0  /* 등산로 셀의 가치 (일반 셀 = 1) [가정] */
#define MAX_FIREBREAK_STEPS     200

/* 방화선 최적화 한 단계의 기록 (발표·문서용) */
typedef struct {
    int    center_x, center_y;   /* 고른 조각의 중심 */
    int    cells_added;          /* 이번에 추가한 칸 수 */
    double score;                /* 점화 트리 점수 */
    double damage_before;        /* 추가 전 피해 가치 */
    double damage_after;         /* 추가 후 피해 가치 */
} FirebreakStep;

/* 방화선 배치 결과 */
typedef struct {
    IntArray      cells;                       /* 방화선 셀 번호 (y * width + x) */
    FirebreakStep steps[MAX_FIREBREAK_STEPS];  /* 단계별 기록 */
    int           step_count;
    double        damage_without;              /* 방화선 없을 때 피해 가치 */
    double        damage_with;                 /* 방화선 있을 때 피해 가치 */
    int           searched_with_helicopters;   /* 1이면 헬기 살수를 함께 시뮬레이션하며 고른 계획 */
} FirebreakPlan;

int    build_cell_weights(const Scenario *sc, double **weights);
int    compute_subtree_values(const Grid *grid, const double *weights, double *values);
double weighted_damage(const Grid *grid, const double *weights);

void   firebreak_plan_init(FirebreakPlan *plan);
void   firebreak_plan_free(FirebreakPlan *plan);
void   apply_firebreak(Grid *grid, const FirebreakPlan *plan);
void   remove_firebreak(Grid *grid, const FirebreakPlan *plan);
int    firebreak_plan_copy(FirebreakPlan *dst, const FirebreakPlan *src);
int    evaluate_firebreak_plan(Scenario *sc, const double *weights, unsigned int seed, const double *heli_guide,
                               const FirebreakPlan *plan, double *damage);
int    optimize_firebreak(Scenario *sc, const double *weights, unsigned int seed, const double *heli_guide,
                          FirebreakPlan *plan);

double first_helicopter_time(const Scenario *sc);
int    plan_helicopter_drops(Scenario *sc, FireState *state, double t, const double *guide, SimResult *res);

#endif /* SUPPRESSION_H */
