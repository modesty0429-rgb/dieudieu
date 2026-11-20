/*
 * fuel_moisture.h
 * 연료 모델 표 읽기와 연료 수분 계산.
 */
#ifndef FUEL_MOISTURE_H
#define FUEL_MOISTURE_H

#include "wf_types.h"

int    load_fuel_models(Scenario *sc);
int    check_map_fuels_defined(const Scenario *sc);
const FuelModel *find_fuel_model(const Scenario *sc, int fuel_code);
int    cell_fuel_is_burnable(const Scenario *sc, const Cell *cell);

double equilibrium_moisture(double temp_c, double rh_pct);
double moisture_damping(double moisture_pct, double extinction_pct);
double effective_moisture(const Scenario *sc, const Cell *cell);
void   init_fuel_moisture(Scenario *sc, double *dead_moisture);
void   update_fuel_moisture(Scenario *sc, double *dead_moisture, const WeatherRecord *weather, double dt_min);

#endif /* FUEL_MOISTURE_H */
