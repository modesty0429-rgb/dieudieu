/*
 * scenario_io.h
 * 시나리오 설정 파일(.ini) 읽기, 검사, 해제.
 */
#ifndef SCENARIO_IO_H
#define SCENARIO_IO_H

#include "wf_types.h"

void scenario_set_defaults(Scenario *sc);
int  load_scenario(const char *path, Scenario *sc);
void free_scenario(Scenario *sc);

#endif /* SCENARIO_IO_H */
