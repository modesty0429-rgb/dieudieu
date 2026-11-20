/*
 * log.c
 * 진행 로그를 표준출력과 (선택적으로) 로그 파일에 동시에 쓴다.
 *
 * 모든 출력 뒤에 fflush(stdout)를 호출한다.
 * 그래야 Python GUI가 프로그램이 끝나기를 기다리지 않고 바로바로 읽을 수 있다.
 */
#ifdef _MSC_VER
/* 일부 Windows SDK 헤더가 C11 모드에서 내는 경고(C5105)를 끈다. 우리 코드와는 무관하다. */
#pragma warning(disable: 5105)
#endif

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>   /* SetConsoleOutputCP: 콘솔 한글 출력을 위해 사용 */
#endif

#include <stdio.h>
#include <stdarg.h>

#include "log.h"

#define LOG_MESSAGE_MAX 1024

static FILE *g_log_file = NULL;     /* 로그 파일 (열지 않았으면 NULL) */
static int   g_warning_count = 0;   /* 지금까지 출력한 경고 수 */

/*
 * 로그 출력을 준비한다. 프로그램 시작 시 한 번 호출한다.
 * Windows 콘솔은 기본 코드페이지가 CP949라서 UTF-8 한글이 깨진다.
 * 콘솔 출력 코드페이지를 UTF-8(65001)로 바꿔 한글이 제대로 보이게 한다.
 */
void log_init(void)
{
#ifdef _WIN32
    SetConsoleOutputCP(65001);
#endif
    g_warning_count = 0;
}

/* 로그 파일을 연다. 이후 모든 로그가 파일에도 기록된다. 성공 1, 실패 0 */
int log_open_file(const char *path)
{
    log_close();
    g_log_file = fopen(path, "w");
    return g_log_file != NULL;
}

/* 로그 파일을 닫는다. */
void log_close(void)
{
    if (g_log_file != NULL) {
        fclose(g_log_file);
        g_log_file = NULL;
    }
}

/*
 * 머리말(prefix)과 메시지를 합쳐 한 줄로 출력하는 공통 함수.
 * prefix 예: "[INFO]", "[PROGRESS] 35"
 * format, args: printf와 같은 형식 문자열과 가변 인자
 */
static void log_write(const char *prefix, const char *format, va_list args)
{
    char message[LOG_MESSAGE_MAX];

    vsnprintf(message, sizeof(message), format, args);

    printf("%s %s\n", prefix, message);
    fflush(stdout);

    if (g_log_file != NULL) {
        fprintf(g_log_file, "%s %s\n", prefix, message);
        fflush(g_log_file);
    }
}

void log_info(const char *format, ...)
{
    va_list args;
    va_start(args, format);
    log_write("[INFO]", format, args);
    va_end(args);
}

void log_warn(const char *format, ...)
{
    va_list args;
    g_warning_count++;
    va_start(args, format);
    log_write("[WARN]", format, args);
    va_end(args);
}

void log_error(const char *format, ...)
{
    va_list args;
    va_start(args, format);
    log_write("[ERROR]", format, args);
    va_end(args);
}

/* "[PROGRESS] 35 확산 시뮬레이션 126/360분" 형식으로 출력. percent는 0~100 */
void log_progress(int percent, const char *format, ...)
{
    char    prefix[32];
    va_list args;

    if (percent < 0) {
        percent = 0;
    }
    if (percent > 100) {
        percent = 100;
    }
    snprintf(prefix, sizeof(prefix), "[PROGRESS] %d", percent);

    va_start(args, format);
    log_write(prefix, format, args);
    va_end(args);
}

/* 결과 파일 경로를 GUI에 알린다. */
void log_result(const char *path)
{
    printf("[RESULT] %s\n", path);
    fflush(stdout);
    if (g_log_file != NULL) {
        fprintf(g_log_file, "[RESULT] %s\n", path);
    }
}

/* 프로그램이 정상적으로 끝났음을 알린다. */
void log_done(double seconds)
{
    printf("[DONE] %.2f초 (경고 %d개)\n", seconds, g_warning_count);
    fflush(stdout);
    if (g_log_file != NULL) {
        fprintf(g_log_file, "[DONE] %.2f초 (경고 %d개)\n", seconds, g_warning_count);
    }
}

int log_warning_count(void)
{
    return g_warning_count;
}
