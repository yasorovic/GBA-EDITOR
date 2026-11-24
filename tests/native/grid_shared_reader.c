/* grid_shared_reader.c - le "script d'acteur" : il LIT la grille partagée.
 *
 * Unité de traduction distincte de l'écrivain et du main : il voit le MÊME
 * tampon `g_grid_Arena_Flow`, par le seul `extern` de grids.h. Les expressions
 * de lecture sont celles que le traducteur émet pour `data.grid.Flow:at(...)` et
 * `data.grid.Flow[x][y]`. */
#include "grids.h"
#include "grid_inline.h"      /* grid_value_at */
#include "grid_shared_expr.h" /* GRID_READ_AT, GRID_CELL, du codegen */

int flow_at(int px, int py) {
    return GRID_READ_AT(px, py);
}

int flow_cell(int x, int y) {
    return GRID_CELL(x, y);
}
