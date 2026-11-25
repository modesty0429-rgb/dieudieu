# 줄 수 현황 (LINE_COUNT)

> `python tools/count_lines.py` 로 자동 생성 — 2026-11-25

| 언어 | 현재 | 목표 | 진행률 |
|---|---:|---:|---:|
| C | 9982 | 약 8,000 | 125% |
| Python | 9439 | 약 4,000 | 236% |
| **합계** | **19421** | **약 12,000** | **162%** |

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
| `c_core/include/wf_types.h` | 417 | 299 | 73 | 45 |
| `c_core/src/console_view.c` | 544 | 442 | 57 | 45 |
| `c_core/src/daylight.c` | 236 | 164 | 47 | 25 |
| `c_core/src/dynarray.c` | 90 | 62 | 17 | 11 |
| `c_core/src/evac_alert.c` | 276 | 193 | 54 | 29 |
| `c_core/src/evac_route.c` | 394 | 271 | 83 | 40 |
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
| `c_core/src/scenario_io.c` | 846 | 688 | 81 | 77 |
| `c_core/src/season.c` | 203 | 138 | 47 | 18 |
| `c_core/src/spotting.c` | 86 | 50 | 26 | 10 |
| `c_core/src/spread_rate.c` | 107 | 55 | 41 | 11 |
| `c_core/src/spread_sim.c` | 527 | 383 | 93 | 51 |
| `c_core/src/suppression.c` | 642 | 481 | 106 | 55 |
| `c_core/src/suppression_eval.c` | 281 | 215 | 39 | 27 |
| `c_core/src/trail_io.c` | 697 | 535 | 97 | 65 |
| `c_core/src/util.c` | 527 | 380 | 91 | 56 |
| `c_core/src/weather.c` | 259 | 188 | 46 | 25 |
| **합계** | **9982** | **7329** | **1637** | **1016** |

## Python

| 파일 | 전체 | 코드 | 주석 | 빈 줄 |
|---|---:|---:|---:|---:|
| `gui/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/main.py` | 77 | 50 | 12 | 15 |
| `gui/services/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/services/app_config.py` | 73 | 38 | 19 | 16 |
| `gui/services/daylight_render.py` | 92 | 54 | 21 | 17 |
| `gui/services/engine_runner.py` | 166 | 109 | 24 | 33 |
| `gui/services/forest_import.py` | 1154 | 845 | 149 | 160 |
| `gui/services/hiker_setup.py` | 230 | 151 | 40 | 39 |
| `gui/services/map_render.py` | 118 | 67 | 31 | 20 |
| `gui/services/mobile_link.py` | 76 | 49 | 10 | 17 |
| `gui/services/mountain_builder.py` | 461 | 266 | 115 | 80 |
| `gui/services/overture_trails.py` | 195 | 130 | 28 | 37 |
| `gui/services/report_builder.py` | 162 | 37 | 100 | 25 |
| `gui/services/result_loader.py` | 482 | 355 | 43 | 84 |
| `gui/services/scenario_writer.py` | 152 | 104 | 25 | 23 |
| `gui/services/season_render.py` | 238 | 155 | 48 | 35 |
| `gui/services/terrain_generator.py` | 256 | 145 | 60 | 51 |
| `gui/services/trail_generator.py` | 112 | 76 | 15 | 21 |
| `gui/services/weather_api.py` | 376 | 249 | 66 | 61 |
| `gui/theme.py` | 188 | 155 | 19 | 14 |
| `gui/views/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/views/daylight_group.py` | 94 | 65 | 12 | 17 |
| `gui/views/evacuation_view.py` | 205 | 167 | 11 | 27 |
| `gui/views/hiker_group.py` | 239 | 175 | 28 | 36 |
| `gui/views/log_console.py` | 72 | 50 | 6 | 16 |
| `gui/views/main_window.py` | 360 | 282 | 36 | 42 |
| `gui/views/map_view.py` | 532 | 419 | 57 | 56 |
| `gui/views/mobile_dialog.py` | 120 | 99 | 7 | 14 |
| `gui/views/playback_bar.py` | 124 | 90 | 10 | 24 |
| `gui/views/report_view.py` | 91 | 69 | 8 | 14 |
| `gui/views/scenario_panel.py` | 484 | 385 | 48 | 51 |
| `gui/views/stats_view.py` | 226 | 181 | 18 | 27 |
| `gui/views/suppression_view.py` | 226 | 180 | 16 | 30 |
| `gui/views/weather_dialog.py` | 246 | 205 | 16 | 25 |
| `tools/_wasi-sdk/wasi-sdk-24.0-x86_64-linux/share/clang/clang-format-diff.py` | 193 | 146 | 31 | 16 |
| `tools/_wasi-sdk/wasi-sdk-24.0-x86_64-linux/share/clang/clang-format-sublime.py` | 73 | 49 | 19 | 5 |
| `tools/_wasi-sdk/wasi-sdk-24.0-x86_64-linux/share/clang/clang-format.py` | 168 | 95 | 58 | 15 |
| `tools/_wasi-sdk/wasi-sdk-24.0-x86_64-linux/share/clang/clang-tidy-diff.py` | 382 | 241 | 96 | 45 |
| `tools/build_mobile.py` | 84 | 59 | 10 | 15 |
| `tools/count_lines.py` | 119 | 92 | 9 | 18 |
| `tools/make_test_shp.py` | 112 | 80 | 10 | 22 |
| `tools/run_tests.py` | 681 | 542 | 58 | 81 |
| **합계** | **9439** | **6706** | **1389** | **1344** |
