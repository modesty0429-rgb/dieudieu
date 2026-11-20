/*
 * spread_rate.h
 * 산불 확산 속도 계산 (Rothermel 모델을 단순화).
 */
#ifndef SPREAD_RATE_H
#define SPREAD_RATE_H

#include "wf_types.h"

/* 확산 속도를 이루는 각 요소 (발표·디버그 때 "왜 이 속도인지" 보여 주기 위해 따로 저장) */
typedef struct {
    double base_rate;         /* 기본 속도 R0 (m/분) */
    double moisture_damping;  /* 수분 감쇠 η_M (0 ~ 1) */
    double wind_factor;       /* 바람 계수 φw */
    double slope_factor;      /* 경사 계수 φs */
    double rate;              /* 최종 확산 속도 (m/분) */
} SpreadFactors;

double wind_factor(const FuelModel *fm, const WeatherRecord *weather, int dir);
double slope_factor(const FuelModel *fm, const Grid *grid, int x, int y, int dir);
double compute_spread_rate(const Scenario *sc, int x, int y, int dir,
                           const WeatherRecord *weather, SpreadFactors *factors);

#endif /* SPREAD_RATE_H */
