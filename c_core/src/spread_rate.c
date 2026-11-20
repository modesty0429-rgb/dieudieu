/*
 * spread_rate.c
 * 불이 한 셀에서 이웃 셀 방향으로 번지는 속도(m/분)를 계산한다.
 *
 * [확산 속도 공식] — Rothermel(1972) 지표화 모델을 단순화
 *
 *     R = R0 × η_M × (1 + φw + φs)
 *
 *   R0  : 연료별 기본 속도. 평지·무풍·바싹 마른 상태 (fuel_models.csv)
 *   η_M : 수분 감쇠. 연료가 젖을수록 0에 가까워짐 (fuel_moisture.c)
 *   φw  : 바람 계수. 바람이 불어 가는 방향으로 크게 빨라짐
 *   φs  : 경사 계수. 오르막으로 빨라지고 내리막으로 느려짐
 *
 * [원래 Rothermel 모델과 다른 점 (단순화)]
 *   - 원래 모델은 연료 입자 크기·밀도·열량 등 10여 개 값으로 R0와 계수를 계산한다.
 *     여기서는 연료별로 R0, kw, bw, ks 네 값만 표로 주고 나머지는 생략했다.
 *   - 바람·경사 계수의 "모양"(바람은 거듭제곱, 경사는 tan²)은 원래 모델을 따랐다.
 *   - 맞바람·내리막 감속은 원래 모델에 없는 부분을 가정으로 추가했다.
 *
 * 출처: Rothermel, R.C. (1972). A mathematical model for predicting fire spread in wildland fuels.
 *       USDA Forest Service Research Paper INT-115.
 */
#include <math.h>

#include "spread_rate.h"
#include "fuel_moisture.h"
#include "grid.h"
#include "util.h"

#define MIN_MULTIPLIER      0.05  /* (1 + φw + φs)의 최솟값: 맞바람·내리막이어도 아주 천천히는 번짐 [가정] */
#define BACKING_WIND_MAX    0.5   /* 맞바람일 때 최대 감속 비율 [가정] */
#define BACKING_WIND_SCALE  3.0   /* 맞바람 감속이 커지는 속도 기준 (m/s) [가정] */
#define DOWNHILL_MAX        0.5   /* 내리막일 때 최대 감속 비율 [가정] */

/*
 * 바람 계수 φw
 * 1) 바람이 "불어 가는" 방향 = 풍향 + 180° (풍향은 불어오는 방향이므로)
 * 2) 확산 방향과 이루는 각 θ에 대해 이 방향의 바람 성분 U·cosθ 를 구한다.
 * 3) 순풍(성분 > 0)이면 φw = kw × (U·cosθ)^bw
 *    맞바람(성분 < 0)이면 최대 50%까지 감속
 */
double wind_factor(const FuelModel *fm, const WeatherRecord *weather, int dir)
{
    double blow_to = normalize_angle_deg(weather->wind_dir_deg + 180.0);
    double theta = deg_to_rad(grid_direction_azimuth(dir) - blow_to);
    double along = weather->wind_speed_ms * cos(theta);   /* 이 방향 바람 성분 (m/s) */

    if (along > 0.0) {
        return fm->wind_coef * pow(along, fm->wind_exp);
    }
    return -BACKING_WIND_MAX * (1.0 - exp(along / BACKING_WIND_SCALE));
}

/*
 * 경사 계수 φs
 * 두 셀의 고도 차이 / 수평 거리 = tan(경사각)
 *   오르막: φs = ks × tan²   (불꽃이 위쪽 연료를 미리 데워 빨라짐)
 *   내리막: 최대 50%까지 감속
 */
double slope_factor(const FuelModel *fm, const Grid *grid, int x, int y, int dir)
{
    int    nx = x + grid_neighbor_dx(dir);
    int    ny = y + grid_neighbor_dy(dir);
    double rise = grid->cells[ny][nx].elevation - grid->cells[y][x].elevation;
    double tan_slope = rise / grid_neighbor_distance(grid, dir);
    double effect = fm->slope_coef * tan_slope * tan_slope;

    if (rise >= 0.0) {
        return effect;
    }
    return -DOWNHILL_MAX * clamp_double(effect, 0.0, 1.0);
}

/*
 * (x, y) 셀에서 dir 방향 이웃 셀로 불이 번지는 속도 (m/분)
 * 연료와 수분은 "불이 들어갈 이웃 셀"의 값을 쓴다. (그 연료를 태우며 나아가므로)
 * factors가 NULL이 아니면 계산 과정의 각 요소를 저장한다.
 * 이웃이 지도 밖이면 호출하지 않아야 한다.
 */
double compute_spread_rate(const Scenario *sc, int x, int y, int dir,
                           const WeatherRecord *weather, SpreadFactors *factors)
{
    const Grid      *grid = &sc->grid;
    const Cell      *target = &grid->cells[y + grid_neighbor_dy(dir)][x + grid_neighbor_dx(dir)];
    const FuelModel *fm = find_fuel_model(sc, target->fuel_code);
    SpreadFactors    f = { 0.0, 0.0, 0.0, 0.0, 0.0 };

    if (fm != NULL && fm->burnable) {
        double multiplier;

        f.base_rate = fm->base_rate_m_min;
        f.moisture_damping = moisture_damping(effective_moisture(sc, target), fm->moisture_ext_pct);
        f.wind_factor = wind_factor(fm, weather, dir);
        f.slope_factor = slope_factor(fm, grid, x, y, dir);

        multiplier = 1.0 + f.wind_factor + f.slope_factor;
        if (multiplier < MIN_MULTIPLIER) {
            multiplier = MIN_MULTIPLIER;
        }
        f.rate = f.base_rate * f.moisture_damping * multiplier;
    }

    if (factors != NULL) {
        *factors = f;
    }
    return f.rate;
}
