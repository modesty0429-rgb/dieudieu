/*
 * spread_sim.h
 * 시간 단계별 산불 확산 시뮬레이션.
 */
#ifndef SPREAD_SIM_H
#define SPREAD_SIM_H

#include "wf_types.h"
#include "dynarray.h"
#include "rng.h"

/* 시뮬레이션 도중의 화재 상태 (어떤 셀이 타고 있는지 목록으로 관리) */
typedef struct {
    IntArray front;          /* 화선: 아직 이웃 셀로 불을 밀어내는 중인 셀 번호 목록 */
    IntArray burning;        /* 연소 중: 불꽃이 있는 셀 번호 목록 (비화의 출발점) */
    IntArray scheduled;      /* 이번 단계에 새로 불이 붙기로 정해진 셀 번호 목록 */
    int      ignited_count;  /* 지금까지 불이 붙은 셀 수 */
    unsigned int seed;       /* 비화 난수 시드 */
    double   dead_moisture;  /* 지역 공통 죽은 연료 수분 (%) */
    double   interval_max_rate; /* 이번 출력 구간의 최대 확산 속도 (m/분) */
} FireState;

void sim_result_init(SimResult *res);
void sim_result_free(SimResult *res);
void sim_options_default(SimOptions *opts);

int  fire_state_init(FireState *state);
void fire_state_free(FireState *state);

int  schedule_ignition(Scenario *sc, FireState *state, int x, int y, double time_min,
                       int parent_index, int by_spot);
int  cell_is_receptive(const Scenario *sc, const Cell *cell);
int  simulate_fire_step(Scenario *sc, FireState *state, double t, double dt,
                        const WeatherRecord *weather, SimResult *res, const SimOptions *opts);
int  run_fire_simulation(Scenario *sc, const SimOptions *opts, unsigned int seed, SimResult *res);

#endif /* SPREAD_SIM_H */
