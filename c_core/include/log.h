/*
 * log.h
 * 진행 상황을 표준출력(stdout)에 한 줄씩 출력한다.
 * Python GUI는 줄 맨 앞의 태그([INFO], [PROGRESS] ...)를 보고 화면에 표시한다.
 *
 *   [INFO] 일반 정보          [WARN] 경고 (계속 진행)
 *   [ERROR] 오류 (중단)       [PROGRESS] 0~100 진행률
 *   [RESULT] 결과 파일 경로   [DONE] 걸린 시간
 */
#ifndef LOG_H
#define LOG_H

void log_init(void);
int  log_open_file(const char *path);
void log_close(void);

void log_info(const char *format, ...);
void log_warn(const char *format, ...);
void log_error(const char *format, ...);
void log_progress(int percent, const char *format, ...);
void log_result(const char *path);
void log_done(double seconds);

int  log_warning_count(void);

#endif /* LOG_H */
