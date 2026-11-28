"""Bus de signaux différés, généré une fois dans main.c.

La RAM est partagée car une seule scène est active. Les identifiants, eux, sont
locaux à la scène : ils n'ont aucun sens après une transition.
"""
from __future__ import annotations


SIGNAL_CAPACITY = 16


def signal_runtime_lines() -> list[str]:
    return [
        "/* Scene-local signals: emitted on frame N, delivered on frame N+1. */",
        f"#define SIGNAL_CAPACITY {SIGNAL_CAPACITY}",
        "typedef struct { int id; Actor* emitter; int value; } Signal;",
        "static Signal g_signal_queue[2][SIGNAL_CAPACITY];",
        "static int g_signal_count[2];",
        "static int g_signal_read;",
        "static int g_signal_cursor;",
        "void signal_reset(void) { g_signal_count[0]=0; g_signal_count[1]=0; g_signal_read=0; g_signal_cursor=0; }",
        "int signal_emit(int id, Actor* emitter, int value) {",
        "    int write = g_signal_read ^ 1;",
        "    if(g_signal_count[write] >= SIGNAL_CAPACITY) return 0;",
        "    g_signal_queue[write][g_signal_count[write]++] = (Signal){id, emitter, value};",
        "    return 1;",
        "}",
        "static void signal_begin_frame(void) { g_signal_read ^= 1; g_signal_cursor = 0; g_signal_count[g_signal_read ^ 1] = 0; }",
        "static int signal_next(int* id, Actor** emitter, int* value) {",
        "    if(g_signal_cursor >= g_signal_count[g_signal_read]) return 0;",
        "    Signal* s = &g_signal_queue[g_signal_read][g_signal_cursor++];",
        "    *id=s->id; *emitter=(s->emitter && s->emitter->alive) ? s->emitter : 0; *value=s->value; return 1;",
        "}",
        "",
    ]
