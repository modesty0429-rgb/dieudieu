/*
 * pqueue.h
 * 우선순위 큐 (최소 힙). 가장 작은 키를 가진 원소를 빠르게 꺼낼 수 있다.
 * 대피 경로 탐색(다익스트라)에서 "다음에 확인할 노드"를 고를 때 쓴다.
 *
 * 키를 두 개(key1, key2) 가진다. key1이 작은 것이 먼저, key1이 같으면 key2가 작은 것이 먼저.
 */
#ifndef PQUEUE_H
#define PQUEUE_H

typedef struct {
    double key1;    /* 첫째 기준 */
    double key2;    /* 둘째 기준 (key1이 같을 때) */
    int    value;   /* 저장할 값 (노드 번호 등) */
} PQItem;

typedef struct {
    PQItem *items;     /* 힙 배열: items[0]이 항상 가장 작은 원소 */
    int     count;
    int     capacity;
} PriorityQueue;

void pq_init(PriorityQueue *pq);
int  pq_push(PriorityQueue *pq, double key1, double key2, int value);
int  pq_pop(PriorityQueue *pq, PQItem *out);
int  pq_is_empty(const PriorityQueue *pq);
void pq_free(PriorityQueue *pq);

#endif /* PQUEUE_H */
