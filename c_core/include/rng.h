/*
 * rng.h
 * 시드를 고정할 수 있는 난수 생성기.
 * 같은 시드로 시작하면 항상 같은 난수가 나오므로 시뮬레이션 결과를 재현할 수 있다.
 * (C 표준 rand()는 컴파일러마다 결과가 달라서 Windows와 다른 환경의 결과가 달라진다.)
 */
#ifndef RNG_H
#define RNG_H

#include <stdint.h>

typedef struct {
    uint32_t state;   /* 내부 상태 (0이면 안 됨) */
} Rng;

void     rng_seed(Rng *rng, unsigned int seed);
uint32_t rng_next_u32(Rng *rng);
double   rng_uniform(Rng *rng);
double   rng_normal(Rng *rng, double mean, double sd);
double   rng_exponential(Rng *rng, double mean);

#endif /* RNG_H */
