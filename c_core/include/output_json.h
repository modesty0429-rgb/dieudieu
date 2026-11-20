/*
 * output_json.h
 * 작은 JSON 작성기와 결과 요약 저장.
 * (외부 라이브러리를 쓸 수 없으므로 필요한 만큼만 직접 만들었다)
 */
#ifndef OUTPUT_JSON_H
#define OUTPUT_JSON_H

#include <stdio.h>
#include "wf_types.h"

#define JSON_MAX_DEPTH 16

typedef struct {
    FILE *fp;
    int   depth;                        /* 현재 몇 겹 안에 있는지 */
    int   has_item[JSON_MAX_DEPTH];     /* 각 겹에 이미 항목이 있으면 1 (쉼표를 찍어야 함) */
} JsonWriter;

int  json_open(JsonWriter *w, const char *path);
int  json_close(JsonWriter *w);
void json_begin_object(JsonWriter *w, const char *key);
void json_end_object(JsonWriter *w);
void json_begin_array(JsonWriter *w, const char *key);
void json_end_array(JsonWriter *w);
void json_string(JsonWriter *w, const char *key, const char *value);
void json_number(JsonWriter *w, const char *key, double value);
void json_int(JsonWriter *w, const char *key, int value);
void json_bool(JsonWriter *w, const char *key, int value);

int  write_summary_json(const char *path, const Scenario *sc, const SimResult *res, double elapsed_sec);

#endif /* OUTPUT_JSON_H */
