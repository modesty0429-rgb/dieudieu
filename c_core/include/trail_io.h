/*
 * trail_io.h
 * 등산로 그래프 파일과 등산객 파일 읽기.
 */
#ifndef TRAIL_IO_H
#define TRAIL_IO_H

#include "wf_types.h"

int  load_trail_graph(const char *path, const Grid *grid, TrailGraph *graph);
int  load_hikers(const char *path, const TrailGraph *graph, Hiker **hikers, int *hiker_count);
int  find_node_index_by_id(const TrailGraph *graph, int id);
int  check_exits_reachable(const TrailGraph *graph);
const char *node_type_name(NodeType type);

void free_trail_graph(TrailGraph *graph);
void free_hikers(Hiker *hikers, int hiker_count);

#endif /* TRAIL_IO_H */
