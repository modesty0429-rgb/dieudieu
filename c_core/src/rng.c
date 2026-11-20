/*
 * rng.c
 * xorshift32 난수 생성기와 여러 분포의 난수.
 *
 * xorshift32: 비트를 왼쪽·오른쪽으로 밀고(shift) XOR 하는 연산 3번으로 다음 난수를 만든다.
 * 매우 짧고 빠르며, 시뮬레이션용으로 충분한 품질을 가진다.
 * 출처: Marsaglia, G. (2003). Xorshift RNGs. Journal of Statistical Software 8(14).
 */
#include <math.h>

#include "rng.h"
#include "wf_config.h"

/* 시드로 난수 생성기를 초기화한다. */
void rng_seed(Rng *rng, unsigned int seed)
{
    int i;

    /* 시드를 섞어 비슷한 시드(1, 2, 3...)도 전혀 다른 난수열이 나오게 한다 */
    rng->state = (uint32_t)seed * 2654435761u + 0x9E3779B9u;
    if (rng->state == 0) {
        rng->state = 1;   /* 상태가 0이면 xorshift는 계속 0만 만든다 */
    }
    for (i = 0; i < 10; i++) {
        rng_next_u32(rng);   /* 처음 몇 개는 버려서 충분히 섞는다 */
    }
}

/*
 * "사건마다 정해진 난수": 시드와 사건 번호 두 개(a, b)를 섞어 난수 생성기를 초기화한다.
 * 예) a = 셀 번호, b = 시각 → "이 셀이 이 시각에 비화를 일으키는가"가 항상 같은 난수로 정해진다.
 *
 * 왜 필요한가 (공통 난수, common random numbers):
 *   난수 하나를 모든 셀이 차례로 꺼내 쓰면, 방화선 때문에 한 셀만 덜 타도 그 뒤의 모든 난수가
 *   밀려서 전혀 다른 비화가 생긴다. 그러면 전략 비교에서 "방화선 효과"보다 "운"의 차이가 커진다.
 *   사건마다 난수를 고정하면 같은 셀·같은 시각의 비화는 어느 전략에서나 같아 공정하게 비교된다.
 */
void rng_seed_for_event(Rng *rng, unsigned int seed, unsigned int a, unsigned int b)
{
    uint32_t mixed = (uint32_t)seed;
    mixed ^= (uint32_t)a * 0x85EBCA6Bu;      /* 서로 다른 큰 홀수를 곱해 섞는다 */
    mixed ^= (uint32_t)b * 0xC2B2AE35u;
    mixed ^= mixed >> 16;
    rng_seed(rng, (unsigned int)mixed);
}

/* 다음 32비트 난수 */
uint32_t rng_next_u32(Rng *rng)
{
    uint32_t x = rng->state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    rng->state = x;
    return x;
}

/* [0, 1) 범위의 균등 분포 실수 */
double rng_uniform(Rng *rng)
{
    /* 위쪽 24비트만 써서 0 이상 1 미만의 실수로 바꾼다 (2^24 = 16777216) */
    return (double)(rng_next_u32(rng) >> 8) / 16777216.0;
}

/*
 * 정규 분포(평균 mean, 표준편차 sd) 난수 — Box-Muller 변환
 * 균등 난수 두 개 u1, u2로  √(-2 ln u1) × cos(2π u2)  를 계산하면 표준 정규 분포가 된다.
 */
double rng_normal(Rng *rng, double mean, double sd)
{
    double u1 = 1.0 - rng_uniform(rng);   /* (0, 1] : log(0)을 피하기 위해 */
    double u2 = rng_uniform(rng);
    double z = sqrt(-2.0 * log(u1)) * cos(2.0 * WF_PI * u2);
    return mean + sd * z;
}

/* 지수 분포(평균 mean) 난수: 짧은 값이 많고 긴 값은 드물다. 비화 거리에 사용. */
double rng_exponential(Rng *rng, double mean)
{
    double u = 1.0 - rng_uniform(rng);   /* (0, 1] */
    return -mean * log(u);
}
