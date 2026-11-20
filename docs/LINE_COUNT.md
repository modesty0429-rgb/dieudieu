# 줄 수 현황 (LINE_COUNT)

> `python tools/count_lines.py` 로 자동 생성 — 2026-11-20

| 언어 | 현재 | 목표 | 진행률 |
|---|---:|---:|---:|
| C | 3810 | 약 8,000 | 48% |
| Python | 487 | 약 4,000 | 12% |
| **합계** | **4297** | **약 12,000** | **36%** |

## C

| 파일 | 전체 | 코드 | 주석 | 빈 줄 |
|---|---:|---:|---:|---:|
| `c_core/include/console_view.h` | 17 | 9 | 5 | 3 |
| `c_core/include/dynarray.h` | 32 | 20 | 7 | 5 |
| `c_core/include/grid.h` | 31 | 16 | 9 | 6 |
| `c_core/include/log.h` | 26 | 13 | 9 | 4 |
| `c_core/include/map_io.h` | 27 | 17 | 6 | 4 |
| `c_core/include/scenario_io.h` | 14 | 7 | 4 | 3 |
| `c_core/include/trail_io.h` | 19 | 11 | 4 | 4 |
| `c_core/include/util.h` | 50 | 31 | 11 | 8 |
| `c_core/include/wf_config.h` | 46 | 26 | 13 | 7 |
| `c_core/include/wf_types.h` | 293 | 201 | 59 | 33 |
| `c_core/src/console_view.c` | 378 | 301 | 45 | 32 |
| `c_core/src/dynarray.c` | 90 | 62 | 17 | 11 |
| `c_core/src/grid.c` | 183 | 127 | 34 | 22 |
| `c_core/src/log.c` | 145 | 101 | 23 | 21 |
| `c_core/src/main.c` | 212 | 157 | 35 | 20 |
| `c_core/src/map_io.c` | 440 | 322 | 77 | 41 |
| `c_core/src/scenario_io.c` | 673 | 539 | 69 | 65 |
| `c_core/src/trail_io.c` | 690 | 528 | 97 | 65 |
| `c_core/src/util.c` | 444 | 321 | 76 | 47 |
| **합계** | **3810** | **2809** | **600** | **401** |

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
