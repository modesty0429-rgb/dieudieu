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
