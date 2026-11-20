/*
 * weather.h
 * 기상 데이터 읽기와 시각별 보간.
 */
#ifndef WEATHER_H
#define WEATHER_H

#include "wf_types.h"

int    load_weather_csv(const char *path, const DateTime *start_time, WeatherSeries *series);
int    load_scenario_weather(Scenario *sc);
void   get_weather_at(const Scenario *sc, double time_min, const WeatherOffset *offset, WeatherRecord *out);
double interpolate_angle_deg(double from_deg, double to_deg, double ratio);
void   free_weather_series(WeatherSeries *series);

#endif /* WEATHER_H */
