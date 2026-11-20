/*
 * spotting.h
 * 비화(飛火): 불티가 바람에 날아가 떨어진 곳에서 새 불이 붙는 현상.
 */
#ifndef SPOTTING_H
#define SPOTTING_H

#include "wf_types.h"
#include "spread_sim.h"
#include "rng.h"

int try_spotting(Scenario *sc, FireState *state, int source_index, double t, double dt,
                 const WeatherRecord *weather, Rng *rng);

#endif /* SPOTTING_H */
