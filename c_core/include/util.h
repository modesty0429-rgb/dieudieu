/*
 * util.h
 * 여러 모듈에서 함께 쓰는 작은 도우미 함수들.
 * (문자열 처리, 숫자 변환, 경로 처리, 각도 계산, 메모리 할당)
 */
#ifndef UTIL_H
#define UTIL_H

#include <stdio.h>
#include <stddef.h>
#include "wf_types.h"

/* ----- 메모리 ----- */
void *wf_malloc(size_t size, const char *what);
void *wf_calloc(size_t count, size_t size, const char *what);

/* ----- 문자열 ----- */
void  copy_string(char *dst, size_t dst_size, const char *src);
char *str_trim(char *text);
void  strip_comment(char *line);
int   str_equals_ignore_case(const char *a, const char *b);
int   str_starts_with(const char *text, const char *prefix);
int   split_by_char(char *line, char separator, char **parts, int max_parts);
int   split_whitespace(char *line, char **tokens, int max_tokens);
int   read_text_line(FILE *fp, char *buffer, int buffer_size, int *line_no);

/* ----- 숫자 변환 (문자열 전체가 올바른 숫자일 때만 성공) ----- */
int parse_int_strict(const char *text, int *out);
int parse_double_strict(const char *text, double *out);

/* ----- 날짜·시각 ----- */
int parse_datetime(const char *text, DateTime *out);
int days_in_month(int year, int month);
long datetime_to_minutes(const DateTime *dt);
void format_datetime(const DateTime *dt, char *out, size_t out_size);

/* ----- 파일 경로 ----- */
int  file_exists(const char *path);
int  make_directories(const char *path);
void get_directory_of(const char *path, char *out, size_t out_size);
void join_path(char *out, size_t out_size, const char *base_dir, const char *relative);

/* ----- 수학 ----- */
double deg_to_rad(double deg);
double rad_to_deg(double rad);
double clamp_double(double value, double min_value, double max_value);
double normalize_angle_deg(double deg);
int    round_to_int(double value);
int    min_int(int a, int b);
int    max_int(int a, int b);
int    abs_int(int value);
int    time_is_set(double time_min);

#endif /* UTIL_H */
