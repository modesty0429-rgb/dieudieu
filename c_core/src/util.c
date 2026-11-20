/*
 * util.c
 * 여러 모듈에서 함께 쓰는 작은 도우미 함수 모음.
 */
#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L   /* macOS/Linux에서 mkdir 함수를 쓰기 위해 필요 */
#endif

#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <math.h>

#ifdef _WIN32
#include <direct.h>       /* _mkdir (Windows 기본 라이브러리) */
#else
#include <sys/stat.h>     /* mkdir (macOS/Linux) */
#endif

#include "util.h"
#include "log.h"

/* ================================================================
 * 메모리
 * ================================================================ */

/*
 * malloc을 감싼 함수. 실패하면 "무엇을 할당하다 실패했는지" 오류를 출력한다.
 * what: 오류 메시지에 쓸 설명 (예: "격자 행")
 */
void *wf_malloc(size_t size, const char *what)
{
    void *memory;

    if (size == 0) {
        size = 1;   /* malloc(0)의 동작은 컴파일러마다 달라서 최소 1바이트를 요청 */
    }
    memory = malloc(size);
    if (memory == NULL) {
        log_error("메모리 부족: %s (%lu 바이트) 할당 실패", what, (unsigned long)size);
    }
    return memory;
}

/* calloc을 감싼 함수. 할당한 메모리를 0으로 채워 준다. */
void *wf_calloc(size_t count, size_t size, const char *what)
{
    void *memory;

    if (count == 0 || size == 0) {
        count = 1;
        size = 1;
    }
    memory = calloc(count, size);
    if (memory == NULL) {
        log_error("메모리 부족: %s (%lu개) 할당 실패", what, (unsigned long)count);
    }
    return memory;
}

/* ================================================================
 * 문자열
 * ================================================================ */

/*
 * src를 dst에 안전하게 복사한다. dst 크기를 넘으면 잘라내고 항상 '\0'으로 끝낸다.
 * (strcpy는 크기를 검사하지 않아 메모리를 침범할 수 있다.)
 */
void copy_string(char *dst, size_t dst_size, const char *src)
{
    size_t i = 0;

    if (dst_size == 0) {
        return;
    }
    if (src != NULL) {
        while (src[i] != '\0' && i < dst_size - 1) {
            dst[i] = src[i];
            i++;
        }
    }
    dst[i] = '\0';
}

/*
 * 문자열 앞뒤의 공백을 제거한다.
 * 뒤쪽 공백은 '\0'으로 지우고, 앞쪽 공백을 건너뛴 위치의 포인터를 돌려준다.
 */
char *str_trim(char *text)
{
    size_t length;

    while (*text != '\0' && isspace((unsigned char)*text)) {
        text++;
    }
    length = strlen(text);
    while (length > 0 && isspace((unsigned char)text[length - 1])) {
        text[length - 1] = '\0';
        length--;
    }
    return text;
}

/* '#' 뒤의 내용(주석)을 지운다. */
void strip_comment(char *line)
{
    char *mark = strchr(line, '#');
    if (mark != NULL) {
        *mark = '\0';
    }
}

/* 대소문자를 구분하지 않고 두 문자열이 같으면 1 */
int str_equals_ignore_case(const char *a, const char *b)
{
    while (*a != '\0' && *b != '\0') {
        if (tolower((unsigned char)*a) != tolower((unsigned char)*b)) {
            return 0;
        }
        a++;
        b++;
    }
    return *a == '\0' && *b == '\0';
}

/* text가 prefix로 시작하면 1 */
int str_starts_with(const char *text, const char *prefix)
{
    return strncmp(text, prefix, strlen(prefix)) == 0;
}

/*
 * line을 separator 문자로 나눈다. 원본 문자열을 직접 수정한다.
 * 나눈 조각(앞뒤 공백 제거)은 parts 배열에 최대 max_parts개 저장된다.
 * 반환값: 실제 조각 수 (max_parts보다 크면 조각이 너무 많다는 뜻)
 */
int split_by_char(char *line, char separator, char **parts, int max_parts)
{
    int   count = 0;
    char *start = line;
    char *p = line;

    for (;;) {
        if (*p == separator || *p == '\0') {
            int is_end = (*p == '\0');
            *p = '\0';
            if (count < max_parts) {
                parts[count] = str_trim(start);
            }
            count++;
            if (is_end) {
                break;
            }
            start = p + 1;
        }
        p++;
    }
    return count;
}

/*
 * line을 공백(스페이스·탭)으로 나눈다. 연속된 공백은 하나로 본다.
 * 반환값: 단어 수 (max_tokens보다 크면 단어가 너무 많다는 뜻)
 */
int split_whitespace(char *line, char **tokens, int max_tokens)
{
    int   count = 0;
    char *p = line;

    while (*p != '\0') {
        /* 1) 공백 건너뛰기 */
        while (*p != '\0' && isspace((unsigned char)*p)) {
            p++;
        }
        if (*p == '\0') {
            break;
        }
        /* 2) 단어 시작 위치 저장 */
        if (count < max_tokens) {
            tokens[count] = p;
        }
        count++;
        /* 3) 단어 끝까지 이동 후 '\0'으로 끊기 */
        while (*p != '\0' && !isspace((unsigned char)*p)) {
            p++;
        }
        if (*p != '\0') {
            *p = '\0';
            p++;
        }
    }
    return count;
}

/*
 * 파일에서 한 줄을 읽어 끝의 줄바꿈(\n, \r\n)을 제거한다.
 * 첫 줄에 UTF-8 BOM(메모장이 붙이는 보이지 않는 3바이트)이 있으면 지운다.
 * line_no는 1씩 증가시켜 오류 메시지에 줄 번호를 쓸 수 있게 한다.
 * 반환값: 1 = 읽음, 0 = 파일 끝, -1 = 줄이 너무 김
 */
int read_text_line(FILE *fp, char *buffer, int buffer_size, int *line_no)
{
    size_t length;

    if (fgets(buffer, buffer_size, fp) == NULL) {
        return 0;
    }
    (*line_no)++;

    length = strlen(buffer);
    if (length > 0 && buffer[length - 1] == '\n') {
        buffer[length - 1] = '\0';
        length--;
    } else if (!feof(fp)) {
        /* 줄바꿈이 없는데 파일 끝도 아니면 버퍼보다 긴 줄이다. 나머지는 버린다. */
        int c = fgetc(fp);
        while (c != '\n' && c != EOF) {
            c = fgetc(fp);
        }
        return -1;
    }
    if (length > 0 && buffer[length - 1] == '\r') {
        buffer[length - 1] = '\0';
    }

    if (*line_no == 1 && (unsigned char)buffer[0] == 0xEF &&
        (unsigned char)buffer[1] == 0xBB && (unsigned char)buffer[2] == 0xBF) {
        memmove(buffer, buffer + 3, strlen(buffer + 3) + 1);
    }
    return 1;
}

/* ================================================================
 * 숫자 변환
 * ================================================================ */

/*
 * 문자열 전체가 정수일 때만 성공(1)한다. "12abc", "" 같은 값은 실패(0).
 * atoi는 실패를 알려 주지 않으므로 strtol을 사용한다.
 */
int parse_int_strict(const char *text, int *out)
{
    char *end;
    long  value;

    while (isspace((unsigned char)*text)) {
        text++;
    }
    if (*text == '\0') {
        return 0;
    }
    errno = 0;
    value = strtol(text, &end, 10);
    while (isspace((unsigned char)*end)) {
        end++;
    }
    if (*end != '\0' || errno == ERANGE || value < INT_MIN || value > INT_MAX) {
        return 0;
    }
    *out = (int)value;
    return 1;
}

/* 문자열 전체가 실수일 때만 성공(1)한다. */
int parse_double_strict(const char *text, double *out)
{
    char  *end;
    double value;

    while (isspace((unsigned char)*text)) {
        text++;
    }
    if (*text == '\0') {
        return 0;
    }
    errno = 0;
    value = strtod(text, &end);
    while (isspace((unsigned char)*end)) {
        end++;
    }
    if (*end != '\0' || errno == ERANGE || !isfinite(value)) {
        return 0;
    }
    *out = value;
    return 1;
}

/* ================================================================
 * 날짜·시각
 * ================================================================ */

/* 해당 월의 날짜 수 (윤년 고려) */
int days_in_month(int year, int month)
{
    static const int days[12] = { 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
    int is_leap = (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);

    if (month < 1 || month > 12) {
        return 0;
    }
    if (month == 2 && is_leap) {
        return 29;
    }
    return days[month - 1];
}

/* "2026-04-05 13:00" 형식을 읽는다. 성공 1, 실패 0 */
int parse_datetime(const char *text, DateTime *out)
{
    DateTime dt;

    if (sscanf(text, "%d-%d-%d %d:%d", &dt.year, &dt.month, &dt.day,
               &dt.hour, &dt.minute) != 5) {
        return 0;
    }
    if (dt.year < 1900 || dt.year > 2200 || dt.month < 1 || dt.month > 12 ||
        dt.day < 1 || dt.day > days_in_month(dt.year, dt.month) ||
        dt.hour < 0 || dt.hour > 23 || dt.minute < 0 || dt.minute > 59) {
        return 0;
    }
    *out = dt;
    return 1;
}

/*
 * 1900-01-01 00:00 부터 dt 까지 몇 분이 지났는지 계산한다.
 * 두 시각의 차이(분)를 구할 때 쓴다. 예) 기상 기록 시각 - 시뮬레이션 시작 시각
 */
long datetime_to_minutes(const DateTime *dt)
{
    long days = 0;
    int  year, month;

    for (year = 1900; year < dt->year; year++) {
        days += (days_in_month(year, 2) == 29) ? 366 : 365;
    }
    for (month = 1; month < dt->month; month++) {
        days += days_in_month(dt->year, month);
    }
    days += dt->day - 1;
    return days * 24L * 60L + dt->hour * 60L + dt->minute;
}

/* DateTime을 "2026-04-05 13:00" 형식 문자열로 만든다. */
void format_datetime(const DateTime *dt, char *out, size_t out_size)
{
    snprintf(out, out_size, "%04d-%02d-%02d %02d:%02d",
             dt->year, dt->month, dt->day, dt->hour, dt->minute);
}

/* ================================================================
 * 파일 경로
 * ================================================================ */

/* 폴더 하나를 만든다. 이미 있어도 성공으로 본다. */
static int make_one_directory(const char *path)
{
    int result;
#ifdef _WIN32
    result = _mkdir(path);
#else
    result = mkdir(path, 0755);
#endif
    return result == 0 || errno == EEXIST;
}

/*
 * 중간 폴더까지 모두 만든다. 예: "output/run1/frames" → output, output/run1, output/run1/frames
 * 경로를 앞에서부터 훑으며 '/' 나 '\' 를 만날 때마다 그 앞부분까지 폴더를 만든다.
 * 성공 1, 실패 0
 */
int make_directories(const char *path)
{
    char   partial[WF_PATH_MAX];
    size_t i;
    size_t length = strlen(path);

    if (length == 0 || length >= sizeof(partial)) {
        return 0;
    }
    for (i = 0; i < length; i++) {
        partial[i] = path[i];
        partial[i + 1] = '\0';
        if ((path[i] == '/' || path[i] == '\\') && i > 0 && path[i - 1] != ':') {
            partial[i] = '\0';
            make_one_directory(partial);
            partial[i] = path[i];
        }
    }
    return make_one_directory(path);
}

/* 파일을 읽기용으로 열 수 있으면 1 */
int file_exists(const char *path)
{
    FILE *fp = fopen(path, "rb");
    if (fp == NULL) {
        return 0;
    }
    fclose(fp);
    return 1;
}

/* 경로에서 폴더 부분만 꺼낸다. "data/a.ini" → "data", "a.ini" → "." */
void get_directory_of(const char *path, char *out, size_t out_size)
{
    const char *last_slash = NULL;
    const char *p;
    size_t      length;

    for (p = path; *p != '\0'; p++) {
        if (*p == '/' || *p == '\\') {
            last_slash = p;
        }
    }
    if (last_slash == NULL) {
        copy_string(out, out_size, ".");
        return;
    }
    length = (size_t)(last_slash - path);
    if (length == 0) {
        length = 1;   /* "/a.ini" 처럼 루트 폴더인 경우 */
    }
    if (length >= out_size) {
        length = out_size - 1;
    }
    memcpy(out, path, length);
    out[length] = '\0';
}

/* 절대 경로(/로 시작, \로 시작, C: 처럼 드라이브 문자로 시작)이면 1 */
static int is_absolute_path(const char *path)
{
    if (path[0] == '/' || path[0] == '\\') {
        return 1;
    }
    if (isalpha((unsigned char)path[0]) && path[1] == ':') {
        return 1;
    }
    return 0;
}

/*
 * 시나리오 파일 안의 상대 경로를 실제로 열 수 있는 경로로 만든다.
 * 예: base_dir = "data/scenarios", relative = "../maps/a.asc"
 *     → "data/scenarios/../maps/a.asc"
 * relative가 절대 경로면 그대로 쓴다. ('/'는 Windows에서도 경로 구분자로 동작한다.)
 */
void join_path(char *out, size_t out_size, const char *base_dir, const char *relative)
{
    if (relative[0] == '\0') {
        copy_string(out, out_size, "");
    } else if (is_absolute_path(relative) || base_dir[0] == '\0') {
        copy_string(out, out_size, relative);
    } else {
        snprintf(out, out_size, "%s/%s", base_dir, relative);
    }
}

/* ================================================================
 * 수학
 * ================================================================ */

double deg_to_rad(double deg)
{
    return deg * WF_PI / 180.0;
}

double rad_to_deg(double rad)
{
    return rad * 180.0 / WF_PI;
}

/* value를 [min_value, max_value] 범위로 제한한다. */
double clamp_double(double value, double min_value, double max_value)
{
    if (value < min_value) {
        return min_value;
    }
    if (value > max_value) {
        return max_value;
    }
    return value;
}

/* 각도를 0 이상 360 미만으로 바꾼다. 예: -90 → 270, 370 → 10 */
double normalize_angle_deg(double deg)
{
    double result = fmod(deg, 360.0);
    if (result < 0.0) {
        result += 360.0;
    }
    return result;
}

/* 반올림해서 정수로 만든다. (2.5 → 3, -2.5 → -2) */
int round_to_int(double value)
{
    double rounded = floor(value + 0.5);
    return (int)rounded;
}

int min_int(int a, int b)
{
    return (a < b) ? a : b;
}

int max_int(int a, int b)
{
    return (a > b) ? a : b;
}

int abs_int(int value)
{
    return (value < 0) ? -value : value;
}

/*
 * 시각 값이 기록돼 있으면 1. "아직 없음"은 WF_NO_TIME(-1)으로 저장하므로 0 이상인지 본다.
 * (실수는 == 로 비교하면 작은 오차 때문에 틀릴 수 있어 크기 비교를 쓴다)
 */
int time_is_set(double time_min)
{
    return time_min >= 0.0;
}
