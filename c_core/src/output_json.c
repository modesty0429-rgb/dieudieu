/*
 * output_json.c
 * 결과 요약을 JSON 파일로 저장한다.
 *
 * [JSON 작성기 원리]
 *   JSON은 { "이름": 값, ... } 객체와 [ 값, ... ] 배열이 겹겹이 들어 있는 형식이다.
 *   같은 겹 안에서 두 번째 항목부터는 앞에 쉼표를 찍어야 하므로,
 *   겹(depth)마다 "이미 항목을 썼는지"를 has_item 배열에 기억해 둔다.
 */
#include <stdio.h>
#include <math.h>

#include "output_json.h"
#include "wf_config.h"
#include "util.h"
#include "log.h"

/* ================================================================
 * JSON 작성기
 * ================================================================ */

/* JSON 파일을 연다. 성공 1, 실패 0 */
int json_open(JsonWriter *w, const char *path)
{
    int i;

    w->fp = fopen(path, "w");
    w->depth = 0;
    for (i = 0; i < JSON_MAX_DEPTH; i++) {
        w->has_item[i] = 0;
    }
    if (w->fp == NULL) {
        log_error("JSON 파일을 만들 수 없음: %s", path);
        return 0;
    }
    return 1;
}

/* 파일을 닫는다. 쓰는 중 오류가 있었으면 0 */
int json_close(JsonWriter *w)
{
    int had_error;

    if (w->fp == NULL) {
        return 0;
    }
    fputc('\n', w->fp);
    had_error = ferror(w->fp);
    if (fclose(w->fp) != 0) {
        had_error = 1;
    }
    w->fp = NULL;
    return !had_error;
}

/* 들여쓰기 (겹 하나당 공백 2칸) */
static void write_indent(JsonWriter *w)
{
    int i;
    for (i = 0; i < w->depth; i++) {
        fputs("  ", w->fp);
    }
}

/* 문자열을 JSON 규칙에 맞게 따옴표로 감싸 쓴다. (" \ 와 제어 문자는 이스케이프) */
static void write_escaped(JsonWriter *w, const char *text)
{
    const unsigned char *p = (const unsigned char *)text;

    fputc('"', w->fp);
    for (; *p != '\0'; p++) {
        if (*p == '"') {
            fputs("\\\"", w->fp);
        } else if (*p == '\\') {
            fputs("\\\\", w->fp);
        } else if (*p == '\n') {
            fputs("\\n", w->fp);
        } else if (*p < 0x20) {
            fprintf(w->fp, "\\u%04x", (unsigned int)*p);
        } else {
            fputc(*p, w->fp);   /* 한글 등 UTF-8 바이트는 그대로 쓴다 */
        }
    }
    fputc('"', w->fp);
}

/* 새 항목을 쓰기 전 준비: 필요하면 쉼표, 줄바꿈, 들여쓰기, "이름": */
static void begin_item(JsonWriter *w, const char *key)
{
    if (w->depth > 0) {
        if (w->has_item[w->depth]) {
            fputc(',', w->fp);
        }
        fputc('\n', w->fp);
        write_indent(w);
    }
    w->has_item[w->depth] = 1;
    if (key != NULL) {
        write_escaped(w, key);
        fputs(": ", w->fp);
    }
}

/* 겹을 하나 연다: { 또는 [ */
static void open_container(JsonWriter *w, const char *key, char bracket)
{
    begin_item(w, key);
    fputc(bracket, w->fp);
    if (w->depth < JSON_MAX_DEPTH - 1) {
        w->depth++;
        w->has_item[w->depth] = 0;
    }
}

/* 겹을 하나 닫는다: } 또는 ] */
static void close_container(JsonWriter *w, char bracket)
{
    int had_items = w->has_item[w->depth];
    if (w->depth > 0) {
        w->depth--;
    }
    if (had_items) {
        fputc('\n', w->fp);
        write_indent(w);
    }
    fputc(bracket, w->fp);
}

void json_begin_object(JsonWriter *w, const char *key) { open_container(w, key, '{'); }
void json_end_object(JsonWriter *w)                    { close_container(w, '}'); }
void json_begin_array(JsonWriter *w, const char *key)  { open_container(w, key, '['); }
void json_end_array(JsonWriter *w)                     { close_container(w, ']'); }

void json_string(JsonWriter *w, const char *key, const char *value)
{
    begin_item(w, key);
    write_escaped(w, value);
}

/* 실수 저장. JSON에는 NaN·무한대가 없으므로 null로 쓴다. */
void json_number(JsonWriter *w, const char *key, double value)
{
    begin_item(w, key);
    if (isfinite(value)) {
        fprintf(w->fp, "%.10g", value);
    } else {
        fputs("null", w->fp);
    }
}

void json_int(JsonWriter *w, const char *key, int value)
{
    begin_item(w, key);
    fprintf(w->fp, "%d", value);
}

void json_bool(JsonWriter *w, const char *key, int value)
{
    begin_item(w, key);
    fputs(value ? "true" : "false", w->fp);
}

/* ================================================================
 * 결과 요약 저장
 * ================================================================ */

/*
 * summary.json: 시나리오 정보, 격자 정보, 최종 결과, 생성한 파일 목록.
 * Python GUI는 이 파일을 먼저 읽고, 여기에 적힌 파일 이름으로 나머지 결과를 찾는다.
 */
int write_summary_json(const char *path, const Scenario *sc, const SimResult *res, double elapsed_sec)
{
    JsonWriter w;
    char       start_text[32];
    int        i;

    if (!json_open(&w, path)) {
        return 0;
    }
    format_datetime(&sc->start_time, start_text, sizeof(start_text));

    json_begin_object(&w, NULL);
    json_string(&w, "engine_version", WF_VERSION);

    json_begin_object(&w, "scenario");
    json_string(&w, "name", sc->name);
    json_string(&w, "scenario_file", sc->scenario_path);
    json_string(&w, "start_datetime", start_text);
    json_number(&w, "duration_min", sc->sim.duration_min);
    json_number(&w, "time_step_min", sc->sim.time_step_min);
    json_number(&w, "output_interval_min", sc->sim.output_interval_min);
    json_int(&w, "random_seed", (int)sc->sim.random_seed);
    json_bool(&w, "spotting_enabled", sc->sim.spotting_enabled);
    json_string(&w, "weather_mode", sc->weather_mode == WEATHER_FIXED ? "fixed" : "file");
    json_string(&w, "weather_file", sc->weather_file);
    json_end_object(&w);

    json_begin_object(&w, "grid");
    json_int(&w, "width", sc->grid.width);
    json_int(&w, "height", sc->grid.height);
    json_number(&w, "cell_size_m", sc->grid.cell_size_m);
    json_number(&w, "xll", sc->grid.xll);
    json_number(&w, "yll", sc->grid.yll);
    json_string(&w, "elevation_file", sc->elevation_file);
    json_string(&w, "fuel_file", sc->fuel_file);
    json_string(&w, "fuel_model_file", sc->fuel_model_file);
    json_end_object(&w);

    json_begin_object(&w, "trails");
    json_string(&w, "trail_file", sc->trail_file);
    json_string(&w, "hiker_file", sc->hiker_file);
    json_int(&w, "node_count", sc->trails.node_count);
    json_int(&w, "edge_count", sc->trails.edge_count);
    json_int(&w, "hiker_count", sc->hiker_count);
    json_end_object(&w);

    json_begin_array(&w, "ignitions");
    for (i = 0; i < sc->ignition_count; i++) {
        json_begin_object(&w, NULL);
        json_int(&w, "x", sc->ignitions[i].x);
        json_int(&w, "y", sc->ignitions[i].y);
        json_number(&w, "time_min", sc->ignitions[i].time_min);
        json_end_object(&w);
    }
    json_end_array(&w);

    json_begin_object(&w, "result");
    json_int(&w, "burned_cells", res->burned_cells);
    json_number(&w, "burned_area_ha", res->final_area_ha);
    json_int(&w, "spot_fires", res->spot_fire_count);
    json_number(&w, "max_spread_rate_m_min", res->max_spread_rate);
    json_number(&w, "end_time_min", res->end_time_min);
    json_bool(&w, "fire_out", res->fire_out);
    json_number(&w, "elapsed_sec", elapsed_sec);
    json_end_object(&w);

    json_begin_object(&w, "files");
    json_string(&w, "arrival_time", "arrival_time.csv");
    json_string(&w, "burnout_time", "burnout_time.csv");
    json_string(&w, "fire_events", "fire_events.csv");
    json_string(&w, "stats", "stats.csv");
    json_string(&w, "log", "run.log");
    json_end_object(&w);

    json_end_object(&w);

    if (!json_close(&w)) {
        log_error("JSON 저장 중 오류: %s", path);
        return 0;
    }
    return 1;
}
