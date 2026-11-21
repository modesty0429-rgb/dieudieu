# 줄 수 현황 (LINE_COUNT)

> `python tools/count_lines.py` 로 자동 생성 — 2026-11-21

| 언어 | 현재 | 목표 | 진행률 |
|---|---:|---:|---:|
| C | 9899 | 약 8,000 | 124% |
| Python | 5085 | 약 4,000 | 127% |
| **합계** | **14984** | **약 12,000** | **125%** |

## C

| 파일 | 전체 | 코드 | 주석 | 빈 줄 |
|---|---:|---:|---:|---:|
| `c_core/include/console_view.h` | 21 | 13 | 5 | 3 |
| `c_core/include/daylight.h` | 41 | 26 | 8 | 7 |
| `c_core/include/dynarray.h` | 32 | 20 | 7 | 5 |
| `c_core/include/evac_alert.h` | 35 | 25 | 5 | 5 |
| `c_core/include/evac_route.h` | 33 | 19 | 8 | 6 |
| `c_core/include/fuel_moisture.h` | 21 | 13 | 4 | 4 |
| `c_core/include/grid.h` | 31 | 16 | 9 | 6 |
| `c_core/include/hiker.h` | 17 | 10 | 4 | 3 |
| `c_core/include/log.h` | 26 | 13 | 9 | 4 |
| `c_core/include/map_io.h` | 27 | 17 | 6 | 4 |
| `c_core/include/montecarlo.h` | 33 | 24 | 4 | 5 |
| `c_core/include/output_csv.h` | 22 | 13 | 5 | 4 |
| `c_core/include/output_json.h` | 48 | 35 | 6 | 7 |
| `c_core/include/pqueue.h` | 29 | 18 | 7 | 4 |
| `c_core/include/rng.h` | 23 | 13 | 6 | 4 |
| `c_core/include/scenario_io.h` | 14 | 7 | 4 | 3 |
| `c_core/include/season.h` | 36 | 25 | 7 | 4 |
| `c_core/include/spotting.h` | 15 | 8 | 4 | 3 |
| `c_core/include/spread_rate.h` | 24 | 15 | 5 | 4 |
| `c_core/include/spread_sim.h` | 38 | 27 | 5 | 6 |
| `c_core/include/suppression.h` | 53 | 39 | 6 | 8 |
| `c_core/include/suppression_eval.h` | 44 | 32 | 6 | 6 |
| `c_core/include/trail_io.h` | 19 | 11 | 4 | 4 |
| `c_core/include/util.h` | 54 | 35 | 11 | 8 |
| `c_core/include/weather.h` | 16 | 9 | 4 | 3 |
| `c_core/include/wf_config.h` | 46 | 26 | 13 | 7 |
| `c_core/include/wf_types.h` | 416 | 298 | 73 | 45 |
| `c_core/src/console_view.c` | 544 | 442 | 57 | 45 |
| `c_core/src/daylight.c` | 236 | 164 | 47 | 25 |
| `c_core/src/dynarray.c` | 90 | 62 | 17 | 11 |
| `c_core/src/evac_alert.c` | 284 | 202 | 53 | 29 |
| `c_core/src/evac_route.c` | 401 | 277 | 83 | 41 |
| `c_core/src/fuel_moisture.c` | 281 | 196 | 57 | 28 |
| `c_core/src/grid.c` | 183 | 127 | 34 | 22 |
| `c_core/src/hiker.c` | 213 | 149 | 48 | 16 |
| `c_core/src/log.c` | 145 | 101 | 23 | 21 |
| `c_core/src/main.c` | 465 | 365 | 59 | 41 |
| `c_core/src/map_io.c` | 447 | 322 | 84 | 41 |
| `c_core/src/montecarlo.c` | 280 | 213 | 40 | 27 |
| `c_core/src/output_csv.c` | 183 | 136 | 31 | 16 |
| `c_core/src/output_json.c` | 655 | 531 | 58 | 66 |
| `c_core/src/pqueue.c` | 118 | 89 | 16 | 13 |
| `c_core/src/rng.c` | 82 | 47 | 27 | 8 |
| `c_core/src/scenario_io.c` | 758 | 613 | 73 | 72 |
| `c_core/src/season.c` | 194 | 134 | 42 | 18 |
| `c_core/src/spotting.c` | 86 | 50 | 26 | 10 |
| `c_core/src/spread_rate.c` | 107 | 55 | 41 | 11 |
| `c_core/src/spread_sim.c` | 527 | 383 | 93 | 51 |
| `c_core/src/suppression.c` | 642 | 481 | 106 | 55 |
| `c_core/src/suppression_eval.c` | 281 | 215 | 39 | 27 |
| `c_core/src/trail_io.c` | 697 | 535 | 97 | 65 |
| `c_core/src/util.c` | 527 | 380 | 91 | 56 |
| `c_core/src/weather.c` | 259 | 188 | 46 | 25 |
| **합계** | **9899** | **7264** | **1623** | **1012** |

## Python

| 파일 | 전체 | 코드 | 주석 | 빈 줄 |
|---|---:|---:|---:|---:|
| `gui/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/main.py` | 36 | 18 | 7 | 11 |
| `gui/services/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/services/app_config.py` | 62 | 31 | 16 | 15 |
| `gui/services/daylight_render.py` | 92 | 54 | 21 | 17 |
| `gui/services/engine_runner.py` | 166 | 109 | 24 | 33 |
| `gui/services/map_render.py` | 115 | 64 | 31 | 20 |
| `gui/services/report_builder.py` | 162 | 37 | 100 | 25 |
| `gui/services/result_loader.py` | 480 | 353 | 43 | 84 |
| `gui/services/scenario_writer.py` | 152 | 104 | 25 | 23 |
| `gui/services/season_render.py` | 89 | 52 | 20 | 17 |
| `gui/services/terrain_generator.py` | 256 | 145 | 60 | 51 |
| `gui/services/trail_generator.py` | 112 | 76 | 15 | 21 |
| `gui/services/weather_api.py` | 236 | 153 | 46 | 37 |
| `gui/theme.py` | 188 | 155 | 19 | 14 |
| `gui/views/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/views/daylight_group.py` | 94 | 65 | 12 | 17 |
| `gui/views/evacuation_view.py` | 214 | 176 | 11 | 27 |
| `gui/views/log_console.py` | 72 | 50 | 6 | 16 |
| `gui/views/main_window.py` | 286 | 220 | 31 | 35 |
| `gui/views/map_view.py` | 500 | 395 | 52 | 53 |
| `gui/views/playback_bar.py` | 124 | 90 | 10 | 24 |
| `gui/views/report_view.py` | 91 | 69 | 8 | 14 |
| `gui/views/scenario_panel.py` | 438 | 352 | 39 | 47 |
| `gui/views/stats_view.py` | 226 | 181 | 18 | 27 |
| `gui/views/suppression_view.py` | 226 | 180 | 16 | 30 |
| `gui/views/weather_dialog.py` | 157 | 128 | 9 | 20 |
| `tools/count_lines.py` | 119 | 92 | 9 | 18 |
| `tools/run_tests.py` | 392 | 298 | 41 | 53 |
| **합계** | **5085** | **3647** | **689** | **749** |
