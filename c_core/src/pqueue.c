/*
 * pqueue.c
 * 이진 힙으로 만든 우선순위 큐.
 *
 * [이진 힙]
 *   배열을 나무(트리)처럼 본다. i번 원소의 부모는 (i-1)/2, 자식은 2i+1, 2i+2.
 *   "부모는 항상 자식보다 작다"는 규칙을 지키면 맨 앞(0번)이 항상 가장 작은 원소가 된다.
 *   - 넣기: 맨 끝에 넣고, 부모보다 작으면 자리를 바꾸며 위로 올린다 (sift up)
 *   - 꺼내기: 0번을 꺼내고, 맨 끝 원소를 0번에 놓은 뒤 자식보다 크면 아래로 내린다 (sift down)
 *   둘 다 나무 높이(log n)만큼만 움직이므로 빠르다.
 */
#include <stdlib.h>

#include "pqueue.h"
#include "log.h"

/* a가 b보다 먼저 나와야 하면(더 작으면) 1 */
static int item_less(const PQItem *a, const PQItem *b)
{
    if (a->key1 < b->key1) {
        return 1;
    }
    if (a->key1 > b->key1) {
        return 0;
    }
    return a->key2 < b->key2;   /* key1이 같으면 key2로 비교 */
}

static void swap_items(PQItem *a, PQItem *b)
{
    PQItem temp = *a;
    *a = *b;
    *b = temp;
}

void pq_init(PriorityQueue *pq)
{
    pq->items = NULL;
    pq->count = 0;
    pq->capacity = 0;
}

/* 원소를 넣는다. 성공 0, 메모리 부족 -1 */
int pq_push(PriorityQueue *pq, double key1, double key2, int value)
{
    int i;

    if (pq->count == pq->capacity) {
        int     new_capacity = (pq->capacity == 0) ? 64 : pq->capacity * 2;
        PQItem *grown = (PQItem *)realloc(pq->items, (size_t)new_capacity * sizeof(PQItem));
        if (grown == NULL) {
            log_error("메모리 부족: 우선순위 큐 %d칸", new_capacity);
            return -1;
        }
        pq->items = grown;
        pq->capacity = new_capacity;
    }

    /* 맨 끝에 넣고 위로 올리기 */
    i = pq->count;
    pq->items[i].key1 = key1;
    pq->items[i].key2 = key2;
    pq->items[i].value = value;
    pq->count++;
    while (i > 0) {
        int parent = (i - 1) / 2;
        if (!item_less(&pq->items[i], &pq->items[parent])) {
            break;
        }
        swap_items(&pq->items[i], &pq->items[parent]);
        i = parent;
    }
    return 0;
}

/* 가장 작은 원소를 꺼내 out에 저장한다. 비어 있으면 0, 꺼냈으면 1 */
int pq_pop(PriorityQueue *pq, PQItem *out)
{
    int i = 0;

    if (pq->count == 0) {
        return 0;
    }
    *out = pq->items[0];
    pq->count--;
    pq->items[0] = pq->items[pq->count];

    /* 맨 위에서 아래로 내리기: 두 자식 중 더 작은 쪽과 비교 */
    for (;;) {
        int left = 2 * i + 1;
        int right = left + 1;
        int smallest = i;

        if (left < pq->count && item_less(&pq->items[left], &pq->items[smallest])) {
            smallest = left;
        }
        if (right < pq->count && item_less(&pq->items[right], &pq->items[smallest])) {
            smallest = right;
        }
        if (smallest == i) {
            break;
        }
        swap_items(&pq->items[i], &pq->items[smallest]);
        i = smallest;
    }
    return 1;
}

int pq_is_empty(const PriorityQueue *pq)
{
    return pq->count == 0;
}

void pq_free(PriorityQueue *pq)
{
    free(pq->items);
    pq_init(pq);
}
