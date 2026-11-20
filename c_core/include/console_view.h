/*
 * console_view.h
 * 콘솔(명령 프롬프트)에 지도와 시나리오 요약을 글자로 출력한다.
 * GUI 없이도 결과를 눈으로 확인할 수 있게 해 주는 디버그용 화면.
 */
#ifndef CONSOLE_VIEW_H
#define CONSOLE_VIEW_H

#include "wf_types.h"
#include "evac_alert.h"

void print_scenario_summary(const Scenario *sc);
void print_terrain_statistics(const Scenario *sc);
void print_map_fuel(const Scenario *sc, int step);
void print_map_elevation(const Scenario *sc, int step);
void print_map_fire(const Scenario *sc, int step, double time_min);
void print_sim_statistics(const SimResult *res, double every_min);
int  choose_map_step(const Grid *grid, int max_columns);
void print_evacuation_table(const Scenario *sc, const EvacSummary *summary);

#endif /* CONSOLE_VIEW_H */
