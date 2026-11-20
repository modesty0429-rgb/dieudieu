/*
 * spotting.c
 * 비화(불티가 날아가 새 불을 만드는 현상)를 확률로 처리한다.
 *
 * [모델] — 모든 계수는 가정값 (docs/model.md 참고)
 *   1) 발생 확률 (연소 중인 셀 하나, 1분당)
 *        p = spot_base_prob × spot_factor(연료) × (풍속 / 10)²
 *      바람이 강할수록, 소나무처럼 불티가 많은 연료일수록 많이 발생한다.
 *   2) 날아가는 거리 ~ 지수 분포, 평균 = spot_mean_dist_m × (풍속 / 5)
 *      가까운 곳에 많이 떨어지고 먼 곳은 드물다.
 *   3) 날아가는 방향 = 바람이 불어 가는 방향 ± 정규 분포(표준편차 15°)
 *   4) 떨어진 곳에서 불이 붙을 확률 = 그 셀의 수분 감쇠 η_M (젖은 연료에는 잘 안 붙음)
 *
 * 난수는 시드를 고정한 Rng를 쓰므로 같은 시드면 항상 같은 곳에 비화가 생긴다.
 */
#include <math.h>

#include "spotting.h"
#include "fuel_moisture.h"
#include "grid.h"
#include "util.h"

#define SPOT_MIN_WIND_MS        2.0   /* 이보다 약한 바람에서는 비화 없음 [가정] */
#define SPOT_DIRECTION_SD_DEG  15.0   /* 비화 방향 흩어짐 [가정] */
#define SPOT_MIN_DISTANCE_CELLS 1.5   /* 이보다 가까우면 일반 확산과 같으므로 무시 */

/*
 * source_index 셀(연소 중)에서 비화가 생기는지 확률로 정하고,
 * 생기면 떨어진 셀에 t + dt 시각의 점화를 예약한다.
 * 반환값: 비화로 새 불이 예약되면 1, 아니면 0
 */
int try_spotting(Scenario *sc, FireState *state, int source_index, double t, double dt,
                 const WeatherRecord *weather, Rng *rng)
{
    const Grid      *grid = &sc->grid;
    int              sx = source_index % grid->width;
    int              sy = source_index / grid->width;
    const FuelModel *fm = find_fuel_model(sc, grid->cells[sy][sx].fuel_code);
    double           wind = weather->wind_speed_ms;
    double           probability, distance_m, direction_deg, distance_cells;
    int              tx, ty;
    const Cell      *target;

    if (!sc->sim.spotting_enabled || fm == NULL || fm->spot_factor <= 0.0 || wind < SPOT_MIN_WIND_MS) {
        return 0;
    }

    /* 1) 발생 여부 */
    probability = sc->sim.spot_base_prob * fm->spot_factor * (wind / 10.0) * (wind / 10.0) * dt;
    if (rng_uniform(rng) >= probability) {
        return 0;
    }

    /* 2) 거리와 3) 방향 */
    distance_m = rng_exponential(rng, sc->sim.spot_mean_dist_m * wind / 5.0);
    direction_deg = weather->wind_dir_deg + 180.0 + rng_normal(rng, 0.0, SPOT_DIRECTION_SD_DEG);
    distance_cells = distance_m / grid->cell_size_m;
    if (distance_cells < SPOT_MIN_DISTANCE_CELLS) {
        return 0;
    }

    /* 방위각 → 격자 이동량 (북쪽이 y 감소 방향) */
    tx = sx + round_to_int(distance_cells * sin(deg_to_rad(direction_deg)));
    ty = sy - round_to_int(distance_cells * cos(deg_to_rad(direction_deg)));
    if (!grid_in_bounds(grid, tx, ty)) {
        return 0;
    }

    /* 4) 떨어진 곳에서 불이 붙는지 */
    target = &grid->cells[ty][tx];
    if (!cell_is_receptive(sc, target) || target->wet_until > t) {
        return 0;
    }
    fm = find_fuel_model(sc, target->fuel_code);
    if (rng_uniform(rng) >= moisture_damping(effective_moisture(sc, target), fm->moisture_ext_pct)) {
        return 0;
    }

    return schedule_ignition(sc, state, tx, ty, t + dt, source_index, 1);
}
