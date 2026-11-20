/*
 * output_json.h
 * 작은 JSON 작성기와 결과 요약 저장.
 * (외부 라이브러리를 쓸 수 없으므로 필요한 만큼만 직접 만들었다)
 */
#ifndef OUTPUT_JSON_H
#define OUTPUT_JSON_H

#include <stdio.h>
#include "wf_types.h"
#include "evac_alert.h"

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

/* 이번 실행에서 만든 결과 파일 종류 (summary.json 의 files 목록에 들어감) */
typedef struct {
    int evacuation;    /* evacuation.json */
    int suppression;   /* suppression.json (5단계) */
    int montecarlo;    /* burn_probability.csv, mc_summary.json (6단계) */
} ResultFlags;

int  write_summary_json(const char *path, const Scenario *sc, const SimResult *res,
                        const ResultFlags *flags, double elapsed_sec);
int  write_evacuation_json(const char *path, const Scenario *sc, const EvacSummary *summary);

#endif /* OUTPUT_JSON_H */
