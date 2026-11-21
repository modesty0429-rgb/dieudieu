/*
 * scenario_io.c
 * 시나리오 설정 파일(.ini)을 읽어 Scenario 구조체를 채우고,
 * 그 안에 적힌 지형·연료·등산로·등산객 파일까지 차례로 불러온다.
 *
 * [INI 파일 형식]
 *   # 주석
 *   [구역이름]
 *   키 = 값
 *
 * 오류가 있어도 바로 멈추지 않고 파일 끝까지 검사해서 오류를 한꺼번에 보여 준다.
 * (사용자가 한 번에 모두 고칠 수 있도록)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "scenario_io.h"
#include "map_io.h"
#include "trail_io.h"
#include "weather.h"
#include "fuel_moisture.h"
#include "grid.h"
#include "util.h"
#include "log.h"

/* 설정 한 줄을 처리할 때 오류 메시지에 쓸 정보 */
typedef struct {
    const char *path;      /* 시나리오 파일 경로 */
    int         line_no;   /* 줄 번호 */
    const char *section;   /* 구역 이름 */
    const char *key;       /* 키 이름 */
} SettingContext;

/* ================================================================
 * 기본값
 * ================================================================ */

/*
 * 모든 설정을 기본값으로 채운다. 시나리오 파일에 없는 값은 이 값이 쓰인다.
 * 각 값이 근거 있는 값인지 가정인지는 data/scenarios 폴더의 .ini 주석과 docs/model.md에 정리한다.
 */
void scenario_set_defaults(Scenario *sc)
{
    memset(sc, 0, sizeof(*sc));   /* 모든 포인터는 NULL, 숫자는 0으로 시작 */

    copy_string(sc->name, sizeof(sc->name), "scenario");
    sc->start_time.year = 2026;
    sc->start_time.month = 4;
    sc->start_time.day = 1;
    sc->start_time.hour = 13;
    sc->start_time.minute = 0;

    sc->sim.duration_min = 600.0;
    sc->sim.time_step_min = 1.0;
    sc->sim.output_interval_min = 10.0;
    sc->sim.random_seed = 42;
    sc->sim.spotting_enabled = 1;
    sc->sim.spot_base_prob = 0.002;
    sc->sim.spot_mean_dist_m = 150.0;

    sc->alert.caution_min = 120.0;
    sc->alert.prepare_min = 60.0;
    sc->alert.immediate_min = 30.0;
    sc->alert.check_radius_m = 500.0;
    sc->alert.notify_delay_min = 10.0;
    sc->alert.safe_margin_min = 30.0;
    sc->alert.danger_radius_m = 60.0;

    sc->supp.firebreak_cells = 40;
    sc->supp.firebreak_ready_min = 60.0;
    sc->supp.helicopters = 2;
    sc->supp.heli_radius_cells = 2;
    sc->supp.heli_interval_min = 30.0;
    sc->supp.heli_effect_min = 45.0;

    sc->mc.runs = 100;
    sc->mc.wind_speed_sd = 1.0;
    sc->mc.wind_dir_sd_deg = 15.0;
    sc->mc.rh_sd = 5.0;

    sc->moisture.initial_dead_moisture_pct = 8.0;
    sc->moisture.live_moisture_factor = 1.0;
    sc->moisture.south_slope_drying_pct = 2.0;
    sc->moisture.timelag_min = 60.0;

    /* 낮/밤 (8단계): 가상 산은 우리나라 중부 지방에 있다고 가정 */
    sc->daylight.enabled = 1;
    sc->daylight.latitude_deg = 37.5;
    sc->daylight.longitude_deg = 127.0;
    sc->daylight.utc_offset_h = 9.0;
    sc->daylight.night_walk_factor = 0.6;
    sc->daylight.heli_day_only = 1;

    sc->weather_mode = WEATHER_FROM_FILE;
    sc->fixed_weather.time_min = 0.0;
    sc->fixed_weather.temp_c = 18.0;
    sc->fixed_weather.rh_pct = 30.0;
    sc->fixed_weather.wind_speed_ms = 5.0;
    sc->fixed_weather.wind_dir_deg = 270.0;
}

/* ================================================================
 * 값 하나를 읽는 도우미 함수들
 * ================================================================ */

/* 실수 값을 읽고 [min_value, max_value] 범위인지 검사한다. 성공 1, 실패 0 */
static int read_double_setting(const SettingContext *ctx, const char *value,
                               double min_value, double max_value, double *out)
{
    double number;

    if (!parse_double_strict(value, &number)) {
        log_error("%s %d번째 줄: [%s] %s 의 값 '%s'는 숫자가 아님",
                  ctx->path, ctx->line_no, ctx->section, ctx->key, value);
        return 0;
    }
    if (number < min_value || number > max_value) {
        log_error("%s %d번째 줄: [%s] %s = %g 는 허용 범위(%g ~ %g)를 벗어남",
                  ctx->path, ctx->line_no, ctx->section, ctx->key, number, min_value, max_value);
        return 0;
    }
    *out = number;
    return 1;
}

/* 정수 값을 읽고 범위를 검사한다. 성공 1, 실패 0 */
static int read_int_setting(const SettingContext *ctx, const char *value,
                            int min_value, int max_value, int *out)
{
    int number;

    if (!parse_int_strict(value, &number)) {
        log_error("%s %d번째 줄: [%s] %s 의 값 '%s'는 정수가 아님",
                  ctx->path, ctx->line_no, ctx->section, ctx->key, value);
        return 0;
    }
    if (number < min_value || number > max_value) {
        log_error("%s %d번째 줄: [%s] %s = %d 는 허용 범위(%d ~ %d)를 벗어남",
                  ctx->path, ctx->line_no, ctx->section, ctx->key, number, min_value, max_value);
        return 0;
    }
    *out = number;
    return 1;
}

/* 파일 경로 값을 시나리오 폴더 기준 경로로 바꿔 저장한다. */
static int read_path_setting(const Scenario *sc, const char *value, char *out, size_t out_size)
{
    join_path(out, out_size, sc->base_dir, value);
    return 1;
}

/* 모르는 키는 오류 대신 경고만 한다. (오타일 수 있으니 알려 주기) */
static int warn_unknown_key(const SettingContext *ctx)
{
    log_warn("%s %d번째 줄: [%s] 구역에 알 수 없는 키 '%s' — 무시함 (오타인지 확인하세요)",
             ctx->path, ctx->line_no, ctx->section, ctx->key);
    return 1;
}

/* ================================================================
 * 구역별 설정 처리 (각 함수는 성공 1, 실패 0)
 * ================================================================ */

static int apply_general(Scenario *sc, const SettingContext *ctx, const char *value)
{
    if (str_equals_ignore_case(ctx->key, "name")) {
        if (value[0] == '\0') {
            log_error("%s %d번째 줄: name 이 비어 있음", ctx->path, ctx->line_no);
            return 0;
        }
        copy_string(sc->name, sizeof(sc->name), value);
        return 1;
    }
    if (str_equals_ignore_case(ctx->key, "output_dir")) {
        return read_path_setting(sc, value, sc->output_dir, sizeof(sc->output_dir));
    }
    return warn_unknown_key(ctx);
}

static int apply_map(Scenario *sc, const SettingContext *ctx, const char *value)
{
    if (str_equals_ignore_case(ctx->key, "elevation_file")) {
        return read_path_setting(sc, value, sc->elevation_file, sizeof(sc->elevation_file));
    }
    if (str_equals_ignore_case(ctx->key, "fuel_file")) {
        return read_path_setting(sc, value, sc->fuel_file, sizeof(sc->fuel_file));
    }
    if (str_equals_ignore_case(ctx->key, "fuel_models")) {
        return read_path_setting(sc, value, sc->fuel_model_file, sizeof(sc->fuel_model_file));
    }
    return warn_unknown_key(ctx);
}

static int apply_trails(Scenario *sc, const SettingContext *ctx, const char *value)
{
    if (str_equals_ignore_case(ctx->key, "trail_file")) {
        return read_path_setting(sc, value, sc->trail_file, sizeof(sc->trail_file));
    }
    if (str_equals_ignore_case(ctx->key, "hiker_file")) {
        return read_path_setting(sc, value, sc->hiker_file, sizeof(sc->hiker_file));
    }
    return warn_unknown_key(ctx);
}

static int apply_time(Scenario *sc, const SettingContext *ctx, const char *value)
{
    if (str_equals_ignore_case(ctx->key, "start_datetime")) {
        if (!parse_datetime(value, &sc->start_time)) {
            log_error("%s %d번째 줄: start_datetime '%s' 는 'YYYY-MM-DD HH:MM' 형식의 올바른 날짜여야 함",
                      ctx->path, ctx->line_no, value);
            return 0;
        }
        return 1;
    }
    if (str_equals_ignore_case(ctx->key, "duration_min")) {
        return read_double_setting(ctx, value, 1.0, 7.0 * 24.0 * 60.0, &sc->sim.duration_min);
    }
    if (str_equals_ignore_case(ctx->key, "time_step_min")) {
        return read_double_setting(ctx, value, 0.1, 10.0, &sc->sim.time_step_min);
    }
    if (str_equals_ignore_case(ctx->key, "output_interval_min")) {
        return read_double_setting(ctx, value, 1.0, 1440.0, &sc->sim.output_interval_min);
    }
    return warn_unknown_key(ctx);
}

/* "point1 = x, y, 발화시각" 형식. 발화 시각은 생략하면 0분 */
static int apply_ignition(Scenario *sc, const SettingContext *ctx, char *value)
{
    char          *parts[4];
    int            part_count;
    IgnitionPoint *point;

    if (!str_starts_with(ctx->key, "point")) {
        return warn_unknown_key(ctx);
    }
    if (sc->ignition_count >= WF_MAX_IGNITIONS) {
        log_error("%s %d번째 줄: 발화 지점은 최대 %d개까지 가능", ctx->path, ctx->line_no, WF_MAX_IGNITIONS);
        return 0;
    }

    part_count = split_by_char(value, ',', parts, 4);
    if (part_count < 2 || part_count > 3) {
        log_error("%s %d번째 줄: 발화 지점 형식은 'x, y' 또는 'x, y, 발화시각(분)' 임",
                  ctx->path, ctx->line_no);
        return 0;
    }

    point = &sc->ignitions[sc->ignition_count];
    point->time_min = 0.0;
    if (!parse_int_strict(parts[0], &point->x) || !parse_int_strict(parts[1], &point->y)) {
        log_error("%s %d번째 줄: 발화 지점 x, y는 정수여야 함", ctx->path, ctx->line_no);
        return 0;
    }
    if (part_count == 3 && !read_double_setting(ctx, parts[2], 0.0, 7.0 * 24.0 * 60.0, &point->time_min)) {
        return 0;
    }
    sc->ignition_count++;
    return 1;
}

static int apply_weather(Scenario *sc, const SettingContext *ctx, const char *value)
{
    WeatherRecord *w = &sc->fixed_weather;

    if (str_equals_ignore_case(ctx->key, "mode")) {
        if (str_equals_ignore_case(value, "file")) {
            sc->weather_mode = WEATHER_FROM_FILE;
        } else if (str_equals_ignore_case(value, "fixed")) {
            sc->weather_mode = WEATHER_FIXED;
        } else {
            log_error("%s %d번째 줄: weather mode 는 'file' 또는 'fixed' 여야 함 (읽은 값: '%s')",
                      ctx->path, ctx->line_no, value);
            return 0;
        }
        return 1;
    }
    if (str_equals_ignore_case(ctx->key, "file")) {
        return read_path_setting(sc, value, sc->weather_file, sizeof(sc->weather_file));
    }
    if (str_equals_ignore_case(ctx->key, "fixed_temp_c")) {
        return read_double_setting(ctx, value, -30.0, 45.0, &w->temp_c);
    }
    if (str_equals_ignore_case(ctx->key, "fixed_rh_pct")) {
        return read_double_setting(ctx, value, 1.0, 100.0, &w->rh_pct);
    }
    if (str_equals_ignore_case(ctx->key, "fixed_wind_speed_ms")) {
        return read_double_setting(ctx, value, 0.0, 40.0, &w->wind_speed_ms);
    }
    if (str_equals_ignore_case(ctx->key, "fixed_wind_dir_deg")) {
        return read_double_setting(ctx, value, 0.0, 360.0, &w->wind_dir_deg);
    }
    return warn_unknown_key(ctx);
}

static int apply_moisture(Scenario *sc, const SettingContext *ctx, const char *value)
{
    MoistureSettings *m = &sc->moisture;

    if (str_equals_ignore_case(ctx->key, "initial_dead_moisture_pct")) {
        return read_double_setting(ctx, value, 1.0, 40.0, &m->initial_dead_moisture_pct);
    }
    if (str_equals_ignore_case(ctx->key, "live_moisture_factor")) {
        return read_double_setting(ctx, value, 0.3, 3.0, &m->live_moisture_factor);
    }
    if (str_equals_ignore_case(ctx->key, "south_slope_drying_pct")) {
        return read_double_setting(ctx, value, 0.0, 10.0, &m->south_slope_drying_pct);
    }
    if (str_equals_ignore_case(ctx->key, "timelag_min")) {
        return read_double_setting(ctx, value, 1.0, 600.0, &m->timelag_min);
    }
    return warn_unknown_key(ctx);
}

static int apply_spread(Scenario *sc, const SettingContext *ctx, const char *value)
{
    if (str_equals_ignore_case(ctx->key, "random_seed")) {
        int seed;
        if (!read_int_setting(ctx, value, 0, 2147483647, &seed)) {
            return 0;
        }
        sc->sim.random_seed = (unsigned int)seed;
        return 1;
    }
    if (str_equals_ignore_case(ctx->key, "spotting_enabled")) {
        return read_int_setting(ctx, value, 0, 1, &sc->sim.spotting_enabled);
    }
    if (str_equals_ignore_case(ctx->key, "spot_base_prob")) {
        return read_double_setting(ctx, value, 0.0, 1.0, &sc->sim.spot_base_prob);
    }
    if (str_equals_ignore_case(ctx->key, "spot_mean_dist_m")) {
        return read_double_setting(ctx, value, 0.0, 5000.0, &sc->sim.spot_mean_dist_m);
    }
    return warn_unknown_key(ctx);
}

static int apply_evacuation(Scenario *sc, const SettingContext *ctx, const char *value)
{
    AlertSettings *a = &sc->alert;

    if (str_equals_ignore_case(ctx->key, "caution_min")) {
        return read_double_setting(ctx, value, 0.0, 1440.0, &a->caution_min);
    }
    if (str_equals_ignore_case(ctx->key, "prepare_min")) {
        return read_double_setting(ctx, value, 0.0, 1440.0, &a->prepare_min);
    }
    if (str_equals_ignore_case(ctx->key, "immediate_min")) {
        return read_double_setting(ctx, value, 0.0, 1440.0, &a->immediate_min);
    }
    if (str_equals_ignore_case(ctx->key, "check_radius_m")) {
        return read_double_setting(ctx, value, 0.0, 5000.0, &a->check_radius_m);
    }
    if (str_equals_ignore_case(ctx->key, "notify_delay_min")) {
        return read_double_setting(ctx, value, 0.0, 1440.0, &a->notify_delay_min);
    }
    if (str_equals_ignore_case(ctx->key, "safe_margin_min")) {
        return read_double_setting(ctx, value, 0.0, 600.0, &a->safe_margin_min);
    }
    if (str_equals_ignore_case(ctx->key, "danger_radius_m")) {
        return read_double_setting(ctx, value, 0.0, 1000.0, &a->danger_radius_m);
    }
    return warn_unknown_key(ctx);
}

static int apply_suppression(Scenario *sc, const SettingContext *ctx, const char *value)
{
    SuppressionSettings *s = &sc->supp;

    if (str_equals_ignore_case(ctx->key, "firebreak_cells")) {
        return read_int_setting(ctx, value, 0, 5000, &s->firebreak_cells);
    }
    if (str_equals_ignore_case(ctx->key, "firebreak_ready_min")) {
        return read_double_setting(ctx, value, 0.0, 7.0 * 24.0 * 60.0, &s->firebreak_ready_min);
    }
    if (str_equals_ignore_case(ctx->key, "helicopters")) {
        return read_int_setting(ctx, value, 0, 20, &s->helicopters);
    }
    if (str_equals_ignore_case(ctx->key, "heli_radius_cells")) {
        return read_int_setting(ctx, value, 0, 20, &s->heli_radius_cells);
    }
    if (str_equals_ignore_case(ctx->key, "heli_interval_min")) {
        return read_double_setting(ctx, value, 1.0, 600.0, &s->heli_interval_min);
    }
    if (str_equals_ignore_case(ctx->key, "heli_effect_min")) {
        return read_double_setting(ctx, value, 1.0, 600.0, &s->heli_effect_min);
    }
    return warn_unknown_key(ctx);
}

static int apply_montecarlo(Scenario *sc, const SettingContext *ctx, const char *value)
{
    MonteCarloSettings *m = &sc->mc;

    if (str_equals_ignore_case(ctx->key, "runs")) {
        return read_int_setting(ctx, value, 1, 10000, &m->runs);
    }
    if (str_equals_ignore_case(ctx->key, "wind_speed_sd")) {
        return read_double_setting(ctx, value, 0.0, 10.0, &m->wind_speed_sd);
    }
    if (str_equals_ignore_case(ctx->key, "wind_dir_sd_deg")) {
        return read_double_setting(ctx, value, 0.0, 90.0, &m->wind_dir_sd_deg);
    }
    if (str_equals_ignore_case(ctx->key, "rh_sd")) {
        return read_double_setting(ctx, value, 0.0, 30.0, &m->rh_sd);
    }
    return warn_unknown_key(ctx);
}

static int apply_daylight(Scenario *sc, const SettingContext *ctx, const char *value)
{
    DaylightSettings *d = &sc->daylight;

    if (str_equals_ignore_case(ctx->key, "enabled")) {
        return read_int_setting(ctx, value, 0, 1, &d->enabled);
    }
    if (str_equals_ignore_case(ctx->key, "latitude_deg")) {
        return read_double_setting(ctx, value, -89.0, 89.0, &d->latitude_deg);
    }
    if (str_equals_ignore_case(ctx->key, "longitude_deg")) {
        return read_double_setting(ctx, value, -180.0, 180.0, &d->longitude_deg);
    }
    if (str_equals_ignore_case(ctx->key, "utc_offset_h")) {
        return read_double_setting(ctx, value, -12.0, 14.0, &d->utc_offset_h);
    }
    if (str_equals_ignore_case(ctx->key, "night_walk_factor")) {
        return read_double_setting(ctx, value, 0.1, 1.0, &d->night_walk_factor);
    }
    if (str_equals_ignore_case(ctx->key, "heli_day_only")) {
        return read_int_setting(ctx, value, 0, 1, &d->heli_day_only);
    }
    return warn_unknown_key(ctx);
}

/* 구역 이름에 따라 알맞은 처리 함수를 부른다. */
static int apply_setting(Scenario *sc, const SettingContext *ctx, char *value)
{
    const char *s = ctx->section;

    if (str_equals_ignore_case(s, "general"))     return apply_general(sc, ctx, value);
    if (str_equals_ignore_case(s, "map"))         return apply_map(sc, ctx, value);
    if (str_equals_ignore_case(s, "trails"))      return apply_trails(sc, ctx, value);
    if (str_equals_ignore_case(s, "time"))        return apply_time(sc, ctx, value);
    if (str_equals_ignore_case(s, "ignition"))    return apply_ignition(sc, ctx, value);
    if (str_equals_ignore_case(s, "weather"))     return apply_weather(sc, ctx, value);
    if (str_equals_ignore_case(s, "moisture"))    return apply_moisture(sc, ctx, value);
    if (str_equals_ignore_case(s, "spread"))      return apply_spread(sc, ctx, value);
    if (str_equals_ignore_case(s, "evacuation"))  return apply_evacuation(sc, ctx, value);
    if (str_equals_ignore_case(s, "suppression")) return apply_suppression(sc, ctx, value);
    if (str_equals_ignore_case(s, "montecarlo"))  return apply_montecarlo(sc, ctx, value);
    if (str_equals_ignore_case(s, "daylight"))    return apply_daylight(sc, ctx, value);
    return 1;   /* 모르는 구역은 구역 줄에서 이미 경고했으므로 여기서는 조용히 넘어간다 */
}

/* 알고 있는 구역 이름이면 1 */
static int is_known_section(const char *name)
{
    static const char *known[] = {
        "general", "map", "trails", "time", "ignition", "weather",
        "moisture", "spread", "evacuation", "suppression", "montecarlo", "daylight"
    };
    int i;
    for (i = 0; i < (int)(sizeof(known) / sizeof(known[0])); i++) {
        if (str_equals_ignore_case(name, known[i])) {
            return 1;
        }
    }
    return 0;
}

/* ================================================================
 * INI 파일 읽기
 * ================================================================ */

/*
 * INI 파일을 한 줄씩 읽어 설정값을 채운다.
 * 반환값: 발견한 오류 수 (0이면 성공)
 */
static int parse_scenario_file(const char *path, Scenario *sc)
{
    FILE *fp;
    char  line[WF_LINE_MAX];
    char  section[WF_NAME_MAX] = "";
    int   line_no = 0;
    int   error_count = 0;
    int   result;

    fp = fopen(path, "r");
    if (fp == NULL) {
        log_error("시나리오 파일을 열 수 없음: %s (경로를 확인하세요)", path);
        return 1;
    }

    while ((result = read_text_line(fp, line, (int)sizeof(line), &line_no)) != 0) {
        char          *text;
        char          *equal_sign;
        SettingContext ctx;

        if (result < 0) {
            log_error("%s %d번째 줄: 줄이 너무 김 (최대 %d자)", path, line_no, WF_LINE_MAX - 1);
            error_count++;
            continue;
        }
        strip_comment(line);
        text = str_trim(line);
        if (text[0] == '\0') {
            continue;   /* 빈 줄 */
        }

        /* [구역] 줄 */
        if (text[0] == '[') {
            size_t length = strlen(text);
            if (text[length - 1] != ']') {
                log_error("%s %d번째 줄: 구역 이름은 [이름] 형식이어야 함", path, line_no);
                error_count++;
                continue;
            }
            text[length - 1] = '\0';
            copy_string(section, sizeof(section), str_trim(text + 1));
            if (!is_known_section(section)) {
                log_warn("%s %d번째 줄: 알 수 없는 구역 [%s] — 이 구역의 설정은 무시함", path, line_no, section);
            }
            continue;
        }

        /* 키 = 값 줄 */
        equal_sign = strchr(text, '=');
        if (equal_sign == NULL) {
            log_error("%s %d번째 줄: '키 = 값' 형식이 아님: '%s'", path, line_no, text);
            error_count++;
            continue;
        }
        if (section[0] == '\0') {
            log_error("%s %d번째 줄: 설정이 [구역] 밖에 있음", path, line_no);
            error_count++;
            continue;
        }
        *equal_sign = '\0';

        ctx.path = path;
        ctx.line_no = line_no;
        ctx.section = section;
        ctx.key = str_trim(text);
        if (!apply_setting(sc, &ctx, str_trim(equal_sign + 1))) {
            error_count++;
        }
    }

    fclose(fp);
    return error_count;
}

/* ================================================================
 * 설정값 사이의 관계 검사
 * ================================================================ */

/* 파일 경로 설정이 비어 있지 않고, 실제로 열 수 있는지 검사한다. */
static int check_required_file(const char *path_value, const char *setting_name)
{
    if (path_value[0] == '\0') {
        log_error("시나리오에 %s 설정이 없음", setting_name);
        return 0;
    }
    if (!file_exists(path_value)) {
        log_error("%s 파일을 찾을 수 없음: %s", setting_name, path_value);
        return 0;
    }
    return 1;
}

/*
 * 값 하나하나는 범위 안이지만 서로 맞지 않는 설정을 찾는다.
 * 예) 경보 기준은 즉시 대피 < 대피 준비 < 주의 순서여야 한다.
 * 반환값: 오류 수
 */
static int validate_settings(Scenario *sc)
{
    int errors = 0;

    if (!check_required_file(sc->elevation_file, "[map] elevation_file")) errors++;
    if (!check_required_file(sc->fuel_file, "[map] fuel_file")) errors++;
    if (!check_required_file(sc->fuel_model_file, "[map] fuel_models")) errors++;
    if (sc->weather_mode == WEATHER_FROM_FILE &&
        !check_required_file(sc->weather_file, "[weather] file")) errors++;
    if (sc->trail_file[0] != '\0' && !check_required_file(sc->trail_file, "[trails] trail_file")) errors++;
    if (sc->hiker_file[0] != '\0') {
        if (sc->trail_file[0] == '\0') {
            log_error("등산객 파일을 쓰려면 [trails] trail_file 도 있어야 함");
            errors++;
        } else if (!check_required_file(sc->hiker_file, "[trails] hiker_file")) {
            errors++;
        }
    }

    if (sc->sim.time_step_min > sc->sim.output_interval_min) {
        log_error("time_step_min(%g)은 output_interval_min(%g)보다 클 수 없음",
                  sc->sim.time_step_min, sc->sim.output_interval_min);
        errors++;
    }
    if (sc->sim.output_interval_min > sc->sim.duration_min) {
        log_error("output_interval_min(%g)은 duration_min(%g)보다 클 수 없음",
                  sc->sim.output_interval_min, sc->sim.duration_min);
        errors++;
    }
    if (!(sc->alert.immediate_min < sc->alert.prepare_min && sc->alert.prepare_min < sc->alert.caution_min)) {
        log_error("경보 기준은 immediate_min(%g) < prepare_min(%g) < caution_min(%g) 이어야 함",
                  sc->alert.immediate_min, sc->alert.prepare_min, sc->alert.caution_min);
        errors++;
    }
    if (sc->ignition_count == 0) {
        log_error("[ignition] 구역에 발화 지점(point1 = x, y)이 하나 이상 있어야 함");
        errors++;
    }
    if (sc->supp.firebreak_ready_min > sc->sim.duration_min) {
        log_warn("방화선 완성 시각(%g분)이 시뮬레이션 시간(%g분)보다 늦어 방화선 효과가 없음",
                 sc->supp.firebreak_ready_min, sc->sim.duration_min);
    }
    if (sc->output_dir[0] == '\0') {
        snprintf(sc->output_dir, sizeof(sc->output_dir), "output/%s", sc->name);
    }
    return errors;
}

/* 발화 지점이 지도 안에 있고 탈 수 있는 셀인지 검사한다. 반환값: 오류 수 */
static int validate_ignitions(const Scenario *sc)
{
    int errors = 0;
    int i;

    for (i = 0; i < sc->ignition_count; i++) {
        const IgnitionPoint *p = &sc->ignitions[i];
        const Cell          *cell;

        if (!grid_in_bounds(&sc->grid, p->x, p->y)) {
            log_error("발화 지점 %d (%d, %d)가 지도(%d x %d) 밖임",
                      i + 1, p->x, p->y, sc->grid.width, sc->grid.height);
            errors++;
            continue;
        }
        cell = &sc->grid.cells[p->y][p->x];
        if (!cell_is_burnable_state(cell) || !cell_fuel_is_burnable(sc, cell)) {
            log_error("발화 지점 %d (%d, %d)는 탈 수 없는 셀임 (연료 코드 %d)",
                      i + 1, p->x, p->y, cell->fuel_code);
            errors++;
        }
        if (p->time_min > sc->sim.duration_min) {
            log_warn("발화 지점 %d의 발화 시각(%g분)이 시뮬레이션 시간보다 늦음", i + 1, p->time_min);
        }
    }
    return errors;
}

/* ================================================================
 * 시나리오 전체 읽기
 * ================================================================ */

/*
 * 시나리오를 읽는 전체 과정:
 *   1) 기본값 채우기
 *   2) .ini 파일 읽기 (설정값)
 *   3) 설정값끼리 맞는지 검사, 필요한 파일이 있는지 검사
 *   4) 연료 모델 표 → 지형 → 연료 지도 → 경사 계산 → 발화 지점 검사
 *   5) 기상
 *   6) 등산로 → 등산객 (있을 때만)
 * 성공 1, 실패 0. 실패해도 free_scenario를 호출하면 안전하게 정리된다.
 */
int load_scenario(const char *path, Scenario *sc)
{
    int errors;

    scenario_set_defaults(sc);
    copy_string(sc->scenario_path, sizeof(sc->scenario_path), path);
    get_directory_of(path, sc->base_dir, sizeof(sc->base_dir));

    /* 1~3단계: 설정 읽기와 검사 */
    errors = parse_scenario_file(path, sc);
    if (errors == 0) {
        errors = validate_settings(sc);
    }
    if (errors > 0) {
        log_error("시나리오 설정 오류 %d개 — 위 메시지를 보고 %s 파일을 고쳐 주세요", errors, path);
        return 0;
    }
    log_info("시나리오 '%s' 설정 읽기 완료", sc->name);

    /* 4단계: 연료 모델과 지도 */
    if (!load_fuel_models(sc) || !load_terrain(sc) || !load_fuel_map(sc) || !check_map_fuels_defined(sc)) {
        return 0;
    }
    compute_slope_aspect(&sc->grid);
    if (validate_ignitions(sc) > 0) {
        return 0;
    }

    /* 5단계: 기상 */
    if (!load_scenario_weather(sc)) {
        return 0;
    }

    /* 6단계: 등산로와 등산객 */
    if (sc->trail_file[0] != '\0') {
        if (!load_trail_graph(sc->trail_file, &sc->grid, &sc->trails)) {
            return 0;
        }
    }
    if (sc->hiker_file[0] != '\0') {
        if (!load_hikers(sc->hiker_file, &sc->trails, &sc->hikers, &sc->hiker_count)) {
            return 0;
        }
    }
    return 1;
}

/* 시나리오가 가진 모든 동적 메모리를 해제한다. */
void free_scenario(Scenario *sc)
{
    grid_free(&sc->grid);
    free_weather_series(&sc->weather);
    free_trail_graph(&sc->trails);
    free_hikers(sc->hikers, sc->hiker_count);
    sc->hikers = NULL;
    sc->hiker_count = 0;
}
