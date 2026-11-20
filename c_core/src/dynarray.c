/*
 * dynarray.c
 * 동적 배열 구현.
 *
 * 원리: 공간이 모자라면 realloc으로 지금 크기의 2배를 새로 확보한다.
 *       2배씩 늘리면 원소를 n개 넣을 때 복사 횟수가 전체적으로 n에 비례해 효율적이다.
 */
#include <stdlib.h>

#include "dynarray.h"
#include "log.h"

#define DYNARRAY_START_CAPACITY 8

/* ================================================================
 * 정수 배열
 * ================================================================ */

/* 빈 배열로 초기화한다. (아직 메모리는 할당하지 않음) */
void intarray_init(IntArray *arr)
{
    arr->data = NULL;
    arr->count = 0;
    arr->capacity = 0;
}

/* 배열 끝에 value를 추가한다. 성공 0, 메모리 부족 -1 */
int intarray_push(IntArray *arr, int value)
{
    if (arr->count == arr->capacity) {
        int  new_capacity = (arr->capacity == 0) ? DYNARRAY_START_CAPACITY : arr->capacity * 2;
        int *new_data = (int *)realloc(arr->data, (size_t)new_capacity * sizeof(int));
        if (new_data == NULL) {
            log_error("메모리 부족: 정수 배열을 %d칸으로 늘릴 수 없음", new_capacity);
            return -1;   /* 실패해도 기존 data는 그대로 남아 있다 */
        }
        arr->data = new_data;
        arr->capacity = new_capacity;
    }
    arr->data[arr->count] = value;
    arr->count++;
    return 0;
}

/* 원소만 비운다. 확보한 메모리는 다시 쓰기 위해 남겨 둔다. */
void intarray_clear(IntArray *arr)
{
    arr->count = 0;
}

/* 메모리를 해제하고 빈 배열 상태로 되돌린다. */
void intarray_free(IntArray *arr)
{
    free(arr->data);
    intarray_init(arr);
}

/* ================================================================
 * 실수 배열 (정수 배열과 같은 방식)
 * ================================================================ */

void doublearray_init(DoubleArray *arr)
{
    arr->data = NULL;
    arr->count = 0;
    arr->capacity = 0;
}

int doublearray_push(DoubleArray *arr, double value)
{
    if (arr->count == arr->capacity) {
        int     new_capacity = (arr->capacity == 0) ? DYNARRAY_START_CAPACITY : arr->capacity * 2;
        double *new_data = (double *)realloc(arr->data, (size_t)new_capacity * sizeof(double));
        if (new_data == NULL) {
            log_error("메모리 부족: 실수 배열을 %d칸으로 늘릴 수 없음", new_capacity);
            return -1;
        }
        arr->data = new_data;
        arr->capacity = new_capacity;
    }
    arr->data[arr->count] = value;
    arr->count++;
    return 0;
}

void doublearray_free(DoubleArray *arr)
{
    free(arr->data);
    doublearray_init(arr);
}
