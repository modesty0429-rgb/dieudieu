/*
 * fuel_moisture.c
 * 1) 연료 모델 표(fuel_models.csv)를 읽는다.
 * 2) 기온·습도로 연료 수분을 계산한다.
 *
 * [연료 수분이 중요한 이유]
 *   젖은 나무는 잘 타지 않는다. 연료 수분이 "소화 수분"에 가까워질수록 확산 속도가 0에 가까워진다.
 *
 * [계산 방법]
 *   ① 평형 수분(EMC): 공기의 기온·습도가 오래 유지될 때 연료가 결국 도달하는 수분.
 *      Simard(1968)의 식을 사용 (미국 국가산불위험등급체계 NFDRS에서도 사용).
 *   ② 시간 지연: 연료는 공기 변화에 바로 따라가지 않고 천천히 변한다.
 *      M(다음) = M + (EMC - M) × (1 - e^(-dt/τ)),  τ = 반응 시간(1시간 지연 연료는 60분)
 *   ③ 사면 보정: 남향 사면은 햇빛을 많이 받아 더 건조하다. (가정)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#include "fuel_moisture.h"
#include "util.h"
#include "log.h"

#define FUEL_FIELD_COUNT 11   /* code ~ source 까지 열 개수 */
#define MIN_MOISTURE_PCT 1.0  /* 연료 수분은 이보다 낮아지지 않게 제한 */

/* ================================================================
 * 연료 모델 표 읽기
 * ================================================================ */

/* 숫자 열 하나를 읽고 범위를 검사한다. */
static int read_fuel_number(const char *text, const char *column, double min_value, double max_value,
                            const char *path, int line_no, double *out)
{
    if (!parse_double_strict(text, out)) {
        log_error("%s %d번째 줄: %s 값 '%s'는 숫자가 아님", path, line_no, column, text);
        return 0;
    }
    if (*out < min_value || *out > max_value) {
        log_error("%s %d번째 줄: %s = %g 는 범위(%g ~ %g)를 벗어남", path, line_no, column, *out, min_value, max_value);
        return 0;
    }
    return 1;
}

/* fuel_models.csv 한 줄을 FuelModel로 바꾼다. */
static int parse_fuel_line(char *text, const char *path, int line_no, FuelModel *fm)
{
    char *f[FUEL_FIELD_COUNT + 1];
    int   count = split_by_char(text, ',', f, FUEL_FIELD_COUNT + 1);
    int   ok;

    if (count != FUEL_FIELD_COUNT) {
        log_error("%s %d번째 줄: 열이 %d개여야 하는데 %d개임", path, line_no, FUEL_FIELD_COUNT, count);
        return 0;
    }
    if (!parse_int_strict(f[0], &fm->code) || fm->code < 0 || fm->code >= WF_MAX_FUELS) {
        log_error("%s %d번째 줄: 연료 코드 '%s'는 0 ~ %d 정수여야 함", path, line_no, f[0], WF_MAX_FUELS - 1);
        return 0;
    }
    copy_string(fm->name, sizeof(fm->name), f[1]);
    if (!parse_int_strict(f[2], &fm->burnable) || (fm->burnable != 0 && fm->burnable != 1)) {
        log_error("%s %d번째 줄: burnable 은 0 또는 1 이어야 함", path, line_no);
        return 0;
    }
    if (!fm->burnable) {
        /* 타지 않는 연료는 나머지 값을 쓰지 않으므로 0으로 둔다 */
        fm->base_rate_m_min = fm->moisture_ext_pct = fm->burn_duration_min = 0.0;
        fm->wind_coef = fm->wind_exp = fm->slope_coef = fm->spot_factor = 0.0;
        return 1;
    }
    ok = read_fuel_number(f[3], "base_rate_m_min", 0.01, 100.0, path, line_no, &fm->base_rate_m_min) &&
         read_fuel_number(f[4], "moisture_ext_pct", 5.0, 60.0, path, line_no, &fm->moisture_ext_pct) &&
         read_fuel_number(f[5], "burn_duration_min", 0.5, 600.0, path, line_no, &fm->burn_duration_min) &&
         read_fuel_number(f[6], "wind_coef", 0.0, 5.0, path, line_no, &fm->wind_coef) &&
         read_fuel_number(f[7], "wind_exp", 0.5, 3.0, path, line_no, &fm->wind_exp) &&
         read_fuel_number(f[8], "slope_coef", 0.0, 20.0, path, line_no, &fm->slope_coef) &&
         read_fuel_number(f[9], "spot_factor", 0.0, 10.0, path, line_no, &fm->spot_factor);
    return ok;
}

/*
 * 연료 모델 표를 읽어 sc->fuels 에 저장하고,
 * 연료 코드로 바로 찾을 수 있도록 sc->fuel_index[코드] 표를 만든다.
 * 성공 1, 실패 0
 */
int load_fuel_models(Scenario *sc)
{
    FILE *fp;
    char  line[WF_LINE_MAX];
    int   line_no = 0;
    int   result;
    int   i;

    for (i = 0; i < WF_MAX_FUELS; i++) {
        sc->fuel_index[i] = -1;
    }
    sc->fuel_count = 0;

    fp = fopen(sc->fuel_model_file, "r");
    if (fp == NULL) {
        log_error("연료 모델 파일을 열 수 없음: %s", sc->fuel_model_file);
        return 0;
    }

    while ((result = read_text_line(fp, line, (int)sizeof(line), &line_no)) != 0) {
        FuelModel fm;
        char     *text;

        if (result < 0) {
            log_error("%s %d번째 줄: 줄이 너무 김", sc->fuel_model_file, line_no);
            fclose(fp);
            return 0;
        }
        strip_comment(line);
        text = str_trim(line);
        if (text[0] == '\0' || str_starts_with(text, "code")) {
            continue;   /* 빈 줄, 머리줄 */
        }
        if (sc->fuel_count >= WF_MAX_FUELS) {
            log_error("%s: 연료 모델은 최대 %d개", sc->fuel_model_file, WF_MAX_FUELS);
            fclose(fp);
            return 0;
        }
        if (!parse_fuel_line(text, sc->fuel_model_file, line_no, &fm)) {
            fclose(fp);
            return 0;
        }
        if (sc->fuel_index[fm.code] >= 0) {
            log_error("%s %d번째 줄: 연료 코드 %d 가 중복됨", sc->fuel_model_file, line_no, fm.code);
            fclose(fp);
            return 0;
        }
        sc->fuels[sc->fuel_count] = fm;
        sc->fuel_index[fm.code] = sc->fuel_count;
        sc->fuel_count++;
    }
    fclose(fp);

    log_info("연료 모델 읽기 완료: %d종류 (%s)", sc->fuel_count, sc->fuel_model_file);
    return 1;
}

/* 연료 코드에 해당하는 연료 모델. 표에 없으면 NULL */
const FuelModel *find_fuel_model(const Scenario *sc, int fuel_code)
{
    if (fuel_code < 0 || fuel_code >= WF_MAX_FUELS || sc->fuel_index[fuel_code] < 0) {
        return NULL;
    }
    return &sc->fuels[sc->fuel_index[fuel_code]];
}

/* 셀의 연료가 탈 수 있는 종류이면 1 (상태는 따로 검사) */
int cell_fuel_is_burnable(const Scenario *sc, const Cell *cell)
{
    const FuelModel *fm = find_fuel_model(sc, cell->fuel_code);
    return fm != NULL && fm->burnable;
}

/* 지도에 쓰인 연료 코드가 모두 연료 모델 표에 있는지 검사한다. 성공 1, 실패 0 */
int check_map_fuels_defined(const Scenario *sc)
{
    int reported[WF_MAX_FUELS] = { 0 };
    int ok = 1;
    int x, y;

    for (y = 0; y < sc->grid.height; y++) {
        for (x = 0; x < sc->grid.width; x++) {
            int code = sc->grid.cells[y][x].fuel_code;
            if (find_fuel_model(sc, code) == NULL && !reported[code]) {
                log_error("연료 지도에 쓰인 코드 %d 가 연료 모델 표(%s)에 없음 (처음 나온 위치 %d, %d)",
                          code, sc->fuel_model_file, x, y);
                reported[code] = 1;
                ok = 0;
            }
        }
    }
    return ok;
}

/* ================================================================
 * 연료 수분
 * ================================================================ */

/*
 * 평형 수분 EMC (%) — Simard(1968)
 * 기온은 화씨(°F)로 바꿔 계산한다. 습도 구간마다 다른 식을 쓴다.
 * 출처: Simard, A.J. (1968). The moisture content of forest fuels.
 *       Canadian Department of Forestry and Rural Development. (NFDRS 1978에서 사용)
 */
double equilibrium_moisture(double temp_c, double rh_pct)
{
    double t = temp_c * 9.0 / 5.0 + 32.0;   /* 섭씨 → 화씨 */
    double h = clamp_double(rh_pct, 0.0, 100.0);
    double emc;

    if (h < 10.0) {
        emc = 0.03229 + 0.281073 * h - 0.000578 * h * t;
    } else if (h < 50.0) {
        emc = 2.22749 + 0.160107 * h - 0.01478 * t;
    } else {
        emc = 21.0606 + 0.005565 * h * h - 0.00035 * h * t - 0.483199 * h;
    }
    return clamp_double(emc, MIN_MOISTURE_PCT, 60.0);
}

/*
 * 수분 감쇠 계수 η_M (0 ~ 1) — Rothermel(1972)
 *   r = 연료 수분 / 소화 수분 (0 ~ 1로 제한)
 *   η_M = 1 - 2.59 r + 5.11 r² - 3.52 r³
 * 연료가 바싹 마르면(r=0) 1, 소화 수분에 도달하면(r=1) 0 → 확산 속도에 곱한다.
 */
double moisture_damping(double moisture_pct, double extinction_pct)
{
    double r;
    double eta;

    if (extinction_pct <= 0.0) {
        return 0.0;
    }
    r = clamp_double(moisture_pct / extinction_pct, 0.0, 1.0);
    if (r >= 1.0) {
        return 0.0;   /* 소화 수분 이상: 식으로는 0이지만 실수 계산 오차로 아주 작은 양수가 나올 수 있어 직접 0 */
    }
    eta = 1.0 - 2.59 * r + 5.11 * r * r - 3.52 * r * r * r;
    return clamp_double(eta, 0.0, 1.0);
}

/* 셀이 남향 사면(경사 방향 135° ~ 225°, 경사 5° 이상)이면 1 */
static int is_south_facing(const Cell *cell)
{
    return cell->slope_deg >= 5.0 && cell->aspect_deg >= 135.0 && cell->aspect_deg <= 225.0;
}

/* 지역 공통 죽은 연료 수분을 각 셀에 나눠 준다. (남향 사면 보정 포함) */
static void apply_moisture_to_cells(Scenario *sc, double dead_moisture)
{
    double south = clamp_double(dead_moisture - sc->moisture.south_slope_drying_pct,
                                MIN_MOISTURE_PCT, 100.0);
    int    x, y;

    for (y = 0; y < sc->grid.height; y++) {
        for (x = 0; x < sc->grid.width; x++) {
            Cell *cell = &sc->grid.cells[y][x];
            cell->fuel_moisture = is_south_facing(cell) ? south : dead_moisture;
        }
    }
}

/*
 * 확산 계산에 쓰는 "실효 수분" = 셀의 수분 × 계절 배율
 * 계절 배율(live_moisture_factor)은 살아 있는 잎·풀의 수분을 대신하는 단순화한 값이다. (가정)
 *   예) 봄 1.0 (새잎이 나기 전, 건조) / 여름 1.6 (잎이 무성하고 습함)
 */
double effective_moisture(const Scenario *sc, const Cell *cell)
{
    return cell->fuel_moisture * sc->moisture.live_moisture_factor;
}

/* 시뮬레이션 시작 시 연료 수분을 시나리오의 초기값으로 맞춘다. */
void init_fuel_moisture(Scenario *sc, double *dead_moisture)
{
    *dead_moisture = sc->moisture.initial_dead_moisture_pct;
    apply_moisture_to_cells(sc, *dead_moisture);
}

/*
 * dt_min 분 동안의 연료 수분 변화를 계산한다.
 * 수분이 평형 수분(EMC)을 향해 τ(timelag_min)의 속도로 천천히 따라간다.
 * dead_moisture: 지역 공통 죽은 연료 수분 (입력이자 출력)
 */
void update_fuel_moisture(Scenario *sc, double *dead_moisture, const WeatherRecord *weather, double dt_min)
{
    double emc = equilibrium_moisture(weather->temp_c, weather->rh_pct);
    double follow = 1.0 - exp(-dt_min / sc->moisture.timelag_min);   /* 이번 단계에 따라가는 비율 */

    *dead_moisture += (emc - *dead_moisture) * follow;
    apply_moisture_to_cells(sc, *dead_moisture);
}
