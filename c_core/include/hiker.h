/*
 * hiker.h
 * 등산객 보행 속도와 이동 시뮬레이션.
 */
#ifndef HIKER_H
#define HIKER_H

#include "wf_types.h"

double tobler_speed_kmh(double flat_speed_kmh, double slope);
double step_time_min(const Scenario *sc, GridPoint from, GridPoint to, double flat_speed_kmh, double t_min);
int    build_hiker_track(const Scenario *sc, Hiker *hiker);
void   hiker_position_at(const Hiker *hiker, double time_min, double *x, double *y);
void   reset_hiker(Hiker *hiker);
void   free_hiker_data(Hiker *hiker);

#endif /* HIKER_H */
