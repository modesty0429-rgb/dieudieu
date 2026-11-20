# 줄 수 현황 (LINE_COUNT)

> `python tools/count_lines.py` 로 자동 생성 — 2026-11-20

| 언어 | 현재 | 목표 | 진행률 |
|---|---:|---:|---:|
| C | 7311 | 약 8,000 | 91% |
| Python | 2835 | 약 4,000 | 71% |
| **합계** | **10146** | **약 12,000** | **85%** |

## C

| 파일 | 전체 | 코드 | 주석 | 빈 줄 |
|---|---:|---:|---:|---:|
| `c_core/include/console_view.h` | 21 | 13 | 5 | 3 |
| `c_core/include/dynarray.h` | 32 | 20 | 7 | 5 |
| `c_core/include/evac_alert.h` | 35 | 25 | 5 | 5 |
| `c_core/include/evac_route.h` | 33 | 19 | 8 | 6 |
| `c_core/include/fuel_moisture.h` | 21 | 13 | 4 | 4 |
| `c_core/include/grid.h` | 31 | 16 | 9 | 6 |
| `c_core/include/hiker.h` | 17 | 10 | 4 | 3 |
| `c_core/include/log.h` | 26 | 13 | 9 | 4 |
| `c_core/include/map_io.h` | 27 | 17 | 6 | 4 |
| `c_core/include/output_csv.h` | 21 | 12 | 5 | 4 |
| `c_core/include/output_json.h` | 43 | 30 | 6 | 7 |
| `c_core/include/pqueue.h` | 29 | 18 | 7 | 4 |
| `c_core/include/rng.h` | 22 | 12 | 6 | 4 |
| `c_core/include/scenario_io.h` | 14 | 7 | 4 | 3 |
| `c_core/include/spotting.h` | 15 | 8 | 4 | 3 |
| `c_core/include/spread_rate.h` | 24 | 15 | 5 | 4 |
| `c_core/include/spread_sim.h` | 36 | 25 | 5 | 6 |
| `c_core/include/trail_io.h` | 19 | 11 | 4 | 4 |
| `c_core/include/util.h` | 54 | 35 | 11 | 8 |
| `c_core/include/weather.h` | 16 | 9 | 4 | 3 |
| `c_core/include/wf_config.h` | 46 | 26 | 13 | 7 |
| `c_core/include/wf_types.h` | 372 | 262 | 69 | 41 |
| `c_core/src/console_view.c` | 506 | 407 | 56 | 43 |
| `c_core/src/dynarray.c` | 90 | 62 | 17 | 11 |
| `c_core/src/evac_alert.c` | 285 | 203 | 53 | 29 |
| `c_core/src/evac_route.c` | 352 | 248 | 69 | 35 |
| `c_core/src/fuel_moisture.c` | 277 | 192 | 57 | 28 |
| `c_core/src/grid.c` | 183 | 127 | 34 | 22 |
| `c_core/src/hiker.c` | 191 | 137 | 38 | 16 |
| `c_core/src/log.c` | 145 | 101 | 23 | 21 |
| `c_core/src/main.c` | 328 | 252 | 45 | 31 |
| `c_core/src/map_io.c` | 440 | 322 | 77 | 41 |
| `c_core/src/output_csv.c` | 152 | 111 | 27 | 14 |
| `c_core/src/output_json.c` | 383 | 307 | 34 | 42 |
| `c_core/src/pqueue.c` | 118 | 89 | 16 | 13 |
| `c_core/src/rng.c` | 64 | 39 | 18 | 7 |
| `c_core/src/scenario_io.c` | 690 | 553 | 71 | 66 |
| `c_core/src/spotting.c` | 80 | 47 | 24 | 9 |
| `c_core/src/spread_rate.c` | 107 | 55 | 41 | 11 |
| `c_core/src/spread_sim.c` | 487 | 351 | 86 | 50 |
| `c_core/src/trail_io.c` | 697 | 535 | 97 | 65 |
| `c_core/src/util.c` | 527 | 380 | 91 | 56 |
| `c_core/src/weather.c` | 255 | 184 | 46 | 25 |
| **합계** | **7311** | **5318** | **1220** | **773** |

## Python

| 파일 | 전체 | 코드 | 주석 | 빈 줄 |
|---|---:|---:|---:|---:|
| `gui/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/main.py` | 36 | 18 | 7 | 11 |
| `gui/services/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/services/app_config.py` | 43 | 23 | 9 | 11 |
| `gui/services/engine_runner.py` | 154 | 100 | 23 | 31 |
| `gui/services/map_render.py` | 110 | 60 | 30 | 20 |
| `gui/services/result_loader.py` | 327 | 233 | 31 | 63 |
| `gui/services/scenario_writer.py` | 148 | 100 | 25 | 23 |
| `gui/services/terrain_generator.py` | 256 | 145 | 60 | 51 |
| `gui/services/trail_generator.py` | 112 | 76 | 15 | 21 |
| `gui/theme.py` | 188 | 155 | 19 | 14 |
| `gui/views/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/views/evacuation_view.py` | 174 | 141 | 9 | 24 |
| `gui/views/log_console.py` | 72 | 50 | 6 | 16 |
| `gui/views/main_window.py` | 254 | 191 | 29 | 34 |
| `gui/views/map_view.py` | 431 | 336 | 47 | 48 |
| `gui/views/playback_bar.py` | 112 | 80 | 9 | 23 |
| `gui/views/scenario_panel.py` | 299 | 233 | 25 | 41 |
| `tools/count_lines.py` | 119 | 92 | 9 | 18 |
| **합계** | **2835** | **2033** | **353** | **449** |
