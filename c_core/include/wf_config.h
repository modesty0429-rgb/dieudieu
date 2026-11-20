/*
 * wf_config.h
 * 프로그램 전체에서 쓰는 상수와 열거형을 모아 둔 파일.
 * 숫자를 코드 곳곳에 직접 쓰지 않고, 여기서 이름을 붙여 한 곳에서 관리한다.
 */
#ifndef WF_CONFIG_H
#define WF_CONFIG_H

/* ===== 프로그램 정보 ===== */
#define WF_VERSION "0.6.0 (6단계)"

/* ===== 크기 제한 ===== */
#define WF_PATH_MAX       260   /* 파일 경로 최대 길이 (Windows MAX_PATH와 같음) */
#define WF_LINE_MAX       1024  /* 설정·등산로 파일 한 줄의 최대 길이 */
#define WF_NAME_MAX       64    /* 이름 문자열 최대 길이 */
#define WF_MAX_IGNITIONS  16    /* 발화 지점 최대 개수 */
#define WF_MAX_FUELS      32    /* 연료 코드 최대 개수 (0 ~ 31) */
#define WF_MAX_GRID_SIZE  2000  /* 격자 가로·세로 최대 칸 수 */
#define WF_MAX_WAYPOINTS  64    /* 등산로 간선 하나의 중간 경유점 최대 개수 */

/* ===== 수학 상수 ===== */
/* MSVC는 M_PI를 기본으로 정의하지 않으므로 직접 정의한다. */
#define WF_PI 3.14159265358979323846

/* "아직 일어나지 않음"을 뜻하는 시각 값 (불이 도착하지 않은 셀 등) */
#define WF_NO_TIME (-1.0)

/* ===== 지도에서 특별한 의미가 있는 연료 코드 ===== */
/* 연료 코드의 전체 목록과 파라미터는 data/scenarios/fuel_models.csv 에 있다. */
#define FUEL_CODE_NONE      0   /* 연료 없음 */
#define FUEL_CODE_GRASS     1   /* 초지 */
#define FUEL_CODE_SHRUB     2   /* 관목 */
#define FUEL_CODE_CONIFER   3   /* 침엽수 */
#define FUEL_CODE_BROADLEAF 4   /* 활엽수 */
#define FUEL_CODE_MIXED     5   /* 혼효림 */
#define FUEL_CODE_ROAD      7   /* 도로 */
#define FUEL_CODE_WATER     8   /* 물 (하천·저수지) */
#define FUEL_CODE_ROCK      9   /* 바위·나지 */

/* ===== 프로그램 종료 코드 (Python GUI가 이 값으로 성공/실패를 판단) ===== */
#define WF_OK          0   /* 성공 */
#define WF_ERR_INPUT   1   /* 입력 파일 오류 */
#define WF_ERR_MEMORY  2   /* 메모리 부족 */
#define WF_ERR_OTHER   3   /* 그 밖의 오류 */

#endif /* WF_CONFIG_H */
