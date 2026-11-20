# 줄 수 현황 (LINE_COUNT)

> `python tools/count_lines.py` 로 자동 생성 — 2026-11-20

| 언어 | 현재 | 목표 | 진행률 |
|---|---:|---:|---:|
| C | 5983 | 약 8,000 | 75% |
| Python | 487 | 약 4,000 | 12% |
| **합계** | **6470** | **약 12,000** | **54%** |

## C

| 파일 | 전체 | 코드 | 주석 | 빈 줄 |
|---|---:|---:|---:|---:|
| `c_core/include/console_view.h` | 19 | 11 | 5 | 3 |
| `c_core/include/dynarray.h` | 32 | 20 | 7 | 5 |
| `c_core/include/fuel_moisture.h` | 21 | 13 | 4 | 4 |
| `c_core/include/grid.h` | 31 | 16 | 9 | 6 |
| `c_core/include/log.h` | 26 | 13 | 9 | 4 |
| `c_core/include/map_io.h` | 27 | 17 | 6 | 4 |
| `c_core/include/output_csv.h` | 21 | 12 | 5 | 4 |
| `c_core/include/output_json.h` | 33 | 22 | 5 | 6 |
| `c_core/include/rng.h` | 22 | 12 | 6 | 4 |
| `c_core/include/scenario_io.h` | 14 | 7 | 4 | 3 |
| `c_core/include/spotting.h` | 15 | 8 | 4 | 3 |
| `c_core/include/spread_rate.h` | 24 | 15 | 5 | 4 |
| `c_core/include/spread_sim.h` | 36 | 25 | 5 | 6 |
| `c_core/include/trail_io.h` | 19 | 11 | 4 | 4 |
| `c_core/include/util.h` | 54 | 35 | 11 | 8 |
| `c_core/include/weather.h` | 16 | 9 | 4 | 3 |
| `c_core/include/wf_config.h` | 46 | 26 | 13 | 7 |
| `c_core/include/wf_types.h` | 348 | 242 | 67 | 39 |
| `c_core/src/console_view.c` | 448 | 359 | 51 | 38 |
| `c_core/src/dynarray.c` | 90 | 62 | 17 | 11 |
| `c_core/src/fuel_moisture.c` | 277 | 192 | 57 | 28 |
| `c_core/src/grid.c` | 183 | 127 | 34 | 22 |
| `c_core/src/log.c` | 145 | 101 | 23 | 21 |
| `c_core/src/main.c` | 304 | 230 | 45 | 29 |
| `c_core/src/map_io.c` | 440 | 322 | 77 | 41 |
| `c_core/src/output_csv.c` | 152 | 111 | 27 | 14 |
| `c_core/src/output_json.c` | 252 | 196 | 27 | 29 |
| `c_core/src/rng.c` | 64 | 39 | 18 | 7 |
| `c_core/src/scenario_io.c` | 678 | 541 | 71 | 66 |
| `c_core/src/spotting.c` | 80 | 47 | 24 | 9 |
| `c_core/src/spread_rate.c` | 107 | 55 | 41 | 11 |
| `c_core/src/spread_sim.c` | 487 | 351 | 86 | 50 |
| `c_core/src/trail_io.c` | 690 | 528 | 97 | 65 |
| `c_core/src/util.c` | 527 | 380 | 91 | 56 |
| `c_core/src/weather.c` | 255 | 184 | 46 | 25 |
| **합계** | **5983** | **4339** | **1005** | **639** |

## Python

| 파일 | 전체 | 코드 | 주석 | 빈 줄 |
|---|---:|---:|---:|---:|
| `gui/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/services/__init__.py` | 0 | 0 | 0 | 0 |
| `gui/services/terrain_generator.py` | 256 | 145 | 60 | 51 |
| `gui/services/trail_generator.py` | 112 | 76 | 15 | 21 |
| `gui/views/__init__.py` | 0 | 0 | 0 | 0 |
| `tools/count_lines.py` | 119 | 92 | 9 | 18 |
| **합계** | **487** | **313** | **84** | **90** |
