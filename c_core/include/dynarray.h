/*
 * dynarray.h
 * 동적 배열: 원소를 넣을수록 자동으로 크기가 늘어나는 배열.
 * C에는 이런 자료구조가 기본으로 없어서 malloc/realloc으로 직접 만든다.
 */
#ifndef DYNARRAY_H
#define DYNARRAY_H

/* 정수 동적 배열 */
typedef struct {
    int *data;      /* 실제 값이 저장된 메모리 */
    int  count;     /* 들어 있는 원소 수 */
    int  capacity;  /* 지금 확보된 칸 수 (count <= capacity) */
} IntArray;

/* 실수 동적 배열 */
typedef struct {
    double *data;
    int     count;
    int     capacity;
} DoubleArray;

void intarray_init(IntArray *arr);
int  intarray_push(IntArray *arr, int value);   /* 성공 0, 메모리 부족 -1 */
void intarray_clear(IntArray *arr);             /* 원소만 비움 (메모리는 유지) */
void intarray_free(IntArray *arr);

void doublearray_init(DoubleArray *arr);
int  doublearray_push(DoubleArray *arr, double value);
void doublearray_free(DoubleArray *arr);

#endif /* DYNARRAY_H */
